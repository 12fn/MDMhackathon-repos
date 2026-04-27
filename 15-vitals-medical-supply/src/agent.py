"""VITALS agent — two-step LLM pipeline for blood-logistics decision support.

Step 1 (chat_json):  Score every spoke 0-10 with a strict JSON schema:
                       {node_id, days_of_supply, projected_stockout_date,
                        viability_index, top_constraint, confidence}.
Step 2 (chat):       Hero "Commander's Decision Brief" (BLUF + top-3 risk
                     spokes + secondary cascades + 3-5 mitigation actions
                     citing approved buy-on-market vendors).

Hero call uses model="gpt-5.4" with a 35s wall-clock timeout. Deterministic
`baseline_scores()` and `baseline_brief()` always render the right shape so
the UI never sits frozen on a spinner.
"""
from __future__ import annotations

import concurrent.futures
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

# Make the repo root importable so we can use shared.kamiwaza_client
ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from shared.kamiwaza_client import chat, chat_json  # noqa: E402

DATA_DIR = Path(__file__).resolve().parents[1] / "data"
CACHED_BRIEFS_PATH = DATA_DIR / "cached_briefs.json"

HERO_CALL_TIMEOUT_S = 35.0
SCORING_CALL_TIMEOUT_S = 25.0


# ---- I/O --------------------------------------------------------------------

def load_hub() -> dict:
    return json.loads((DATA_DIR / "hub.json").read_text())


def load_spokes() -> list[dict]:
    return json.loads((DATA_DIR / "spokes.json").read_text())


def load_inventory() -> list[dict]:
    return json.loads((DATA_DIR / "inventory.json").read_text())


def load_routes() -> list[dict]:
    return json.loads((DATA_DIR / "routes.json").read_text())


def load_casualties() -> list[dict]:
    return json.loads((DATA_DIR / "casualty_assumptions.json").read_text())


def load_vendors() -> list[dict]:
    return json.loads((DATA_DIR / "vendors.json").read_text())


def load_cached_briefs() -> dict:
    if not CACHED_BRIEFS_PATH.exists():
        return {}
    try:
        return json.loads(CACHED_BRIEFS_PATH.read_text())
    except Exception:
        return {}


# ---- Scenario application ---------------------------------------------------

SCENARIOS = {
    "baseline": {
        "label": "Baseline (current posture)",
        "constraint": "Hub at full lift availability; cold-chain stable at all spokes.",
    },
    "airlift_loss": {
        "label": "Hub airlift loss (typhoon CPA <48h)",
        "constraint": "All hub fixed-wing lift suspended for 48h. Rotary-only resupply to L-class amphibs.",
    },
    "cold_chain_breach": {
        "label": "Cold-chain breach at EABO sites",
        "constraint": "Two EABO refrigeration units fail. Lab-reagent shipment delayed 36h.",
    },
    "mass_cas_event": {
        "label": "Mass-cas event at LHD-1",
        "constraint": "Surface action group engagement: projected WIA at LHD-1 doubles for 24h.",
    },
}


def apply_scenario(scenario_id: str, spokes: list[dict], inventory: list[dict],
                   routes: list[dict]) -> tuple[list[dict], list[dict]]:
    """Return scenario-adjusted (inventory, routes). Pure function."""
    inv = [dict(r) for r in inventory]
    rts = [dict(r) for r in routes]
    if scenario_id == "airlift_loss":
        for r in rts:
            if r["lift_status"] == "GREEN":
                r["lift_status"] = "AMBER"
            elif r["lift_status"] == "AMBER":
                r["lift_status"] = "RED"
        for row in inv:
            row["days_of_supply"] = max(0.3, row.get("days_of_supply", 5) - 1.5)
    elif scenario_id == "cold_chain_breach":
        eabo_ids = {s["id"] for s in spokes if s["kind"] == "rotc-frwd"}
        for row in inv:
            if row["site_id"] in eabo_ids:
                row["cold_chain_status"] = "RED"
                row["days_of_supply"] = max(0.3, row.get("days_of_supply", 5) - 1.0)
    elif scenario_id == "mass_cas_event":
        for row in inv:
            if row["site_id"] == "LHD-1":
                row["days_of_supply"] = max(0.3, row.get("days_of_supply", 5) / 2.0)
                row["daily_consumption"] = row.get("daily_consumption", 1) * 2.0
    return inv, rts


# ---- Step 1: deterministic baseline scoring (no LLM) -----------------------

def baseline_scores(spokes: list[dict], inventory: list[dict],
                    routes: list[dict]) -> list[dict]:
    """Heuristic spoke scoring — instant, never hangs.

    Output schema matches the LLM step exactly so the UI is agnostic to source:
      {node_id, days_of_supply, projected_stockout_date, viability_index,
       top_constraint, confidence}
    """
    inv_by_site: dict[str, list[dict]] = {}
    for r in inventory:
        inv_by_site.setdefault(r["site_id"], []).append(r)
    rt_by_site = {r["spoke_id"]: r for r in routes}

    out = []
    now = datetime.now(timezone.utc)
    for s in spokes:
        rows = inv_by_site.get(s["id"], [])
        if not rows:
            continue
        # Min DOS across all products held -> the bottleneck product
        min_dos = min(r.get("days_of_supply", 99) for r in rows)
        # Worst cold-chain status across products
        cc = min((r["cold_chain_status"] for r in rows),
                 key=lambda c: ["RED", "AMBER", "GREEN"].index(c))
        rt = rt_by_site.get(s["id"], {})
        lift = rt.get("lift_status", "GREEN")

        # Viability: combine days-of-supply + cold-chain + lift into 0..10
        cc_score = {"GREEN": 3.0, "AMBER": 1.5, "RED": 0.0}[cc]
        lift_score = {"GREEN": 2.0, "AMBER": 1.0, "RED": 0.0}[lift]
        viability = max(0.0, min(10.0, min_dos * 1.0 + cc_score + lift_score))

        # Stockout date: now + min_dos days
        stockout_dt = now + timedelta(days=min_dos)

        # Top constraint
        if cc == "RED":
            constraint = "Cold-chain refrigeration RED — product condemnation imminent"
        elif min_dos < 1.5:
            constraint = f"Critical days-of-supply ({min_dos:.1f}d)"
        elif lift == "RED" and min_dos < 4:
            constraint = "Lift suspended + low days-of-supply"
        elif min_dos < 3:
            constraint = f"Low days-of-supply ({min_dos:.1f}d)"
        elif cc == "AMBER":
            constraint = "Cold-chain degraded (refrigeration AMBER)"
        else:
            constraint = "Within sustainment window"

        if min_dos < 2 or cc == "RED":
            conf = "HIGH"
        elif min_dos < 5 or cc == "AMBER":
            conf = "MODERATE"
        else:
            conf = "LOW"

        out.append({
            "node_id": s["id"],
            "days_of_supply": round(min_dos, 1),
            "projected_stockout_date": stockout_dt.strftime("%d%H%MZ %b %Y").upper(),
            "viability_index": round(viability, 1),
            "top_constraint": constraint,
            "confidence": conf,
            "_source": "baseline",
        })
    return out


def nodes_at_critical_risk(scores: list[dict], threshold: float = 4.0) -> int:
    """Count of spokes with viability_index <= threshold."""
    return sum(1 for s in scores if float(s.get("viability_index", 10.0)) <= threshold)


# ---- Step 1: LLM JSON-mode scoring ----------------------------------------

SCORING_SYSTEM = """You are VITALS, the Joint Blood Logistics Decision-Support
agent for USMC LOGCOM and the Defense Health Agency, supporting USINDOPACOM
Distributed Maritime Operations (DMO).

You will receive (a) a hub-and-spoke network of one regional medical depot and
12 distributed Marine spoke nodes, (b) blood-component inventory rows per spoke
(PRBC / PLASMA / PLT / LTOWB), (c) hub<->spoke route status with lift and
cold-chain transit risk, (d) per-spoke casualty planning factors.

For EVERY spoke node, produce a structured JSON entry with EXACTLY these keys:
  - "node_id":                str   (matches spoke id verbatim)
  - "days_of_supply":         float (min across products held at that spoke)
  - "projected_stockout_date":str   (DTG format e.g. "281430Z APR 2026")
  - "viability_index":        float (0.0=mission-failure imminent, 10.0=robust)
  - "top_constraint":         str   (single short phrase, e.g. "Cold-chain RED",
                                     "PRBC stockout <36h", "Lift suspended")
  - "confidence":             str   ("HIGH" | "MODERATE" | "LOW")

Return a single JSON object: {"scores": [ ... 12 entries ... ]}.

Be calibrated: do not assign multiple spokes 9+/10 viability unless the data
supports it. Score every spoke even if its inventory is healthy."""


def build_scoring_prompt(hub: dict, spokes: list[dict], inventory: list[dict],
                         routes: list[dict], casualties: list[dict]) -> list[dict]:
    inv_by_site: dict[str, list[dict]] = {}
    for r in inventory:
        inv_by_site.setdefault(r["site_id"], []).append(r)
    cas_by_site = {c["spoke_id"]: c for c in casualties}
    rt_by_site = {r["spoke_id"]: r for r in routes}

    payload = []
    for s in spokes:
        payload.append({
            "id": s["id"], "name": s["name"], "kind": s["kind"],
            "personnel": s["personnel"],
            "fridge_health": s["fridge_health"],
            "inventory": inv_by_site.get(s["id"], []),
            "route": rt_by_site.get(s["id"], {}),
            "casualty": cas_by_site.get(s["id"], {}),
        })

    user = (
        f"HUB: {json.dumps(hub, indent=2)}\n\n"
        f"SPOKES + INVENTORY + ROUTE + CASUALTY (12):\n{json.dumps(payload, indent=2)}\n\n"
        "Return JSON: {\"scores\":[{node_id,days_of_supply,projected_stockout_date,"
        "viability_index,top_constraint,confidence}, ...]}"
    )
    return [
        {"role": "system", "content": SCORING_SYSTEM},
        {"role": "user", "content": user},
    ]


def _chat_json_with_timeout(msgs: list[dict], timeout_s: float) -> dict | None:
    def _go() -> dict:
        return chat_json(
            msgs,
            schema_hint='{"scores":[{"node_id":str,"days_of_supply":float,'
                        '"projected_stockout_date":str,"viability_index":float,'
                        '"top_constraint":str,"confidence":str}]}',
            temperature=0.2,
        )
    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
            return ex.submit(_go).result(timeout=timeout_s)
    except (concurrent.futures.TimeoutError, Exception):
        return None


def score_spokes(hub: dict, spokes: list[dict], inventory: list[dict],
                 routes: list[dict], casualties: list[dict]) -> list[dict]:
    """LLM-overlay over deterministic baseline; baseline always present."""
    base = {b["node_id"]: b for b in baseline_scores(spokes, inventory, routes)}
    msgs = build_scoring_prompt(hub, spokes, inventory, routes, casualties)
    raw = _chat_json_with_timeout(msgs, SCORING_CALL_TIMEOUT_S) or {}
    llm_scores = raw.get("scores") or raw.get("nodes") or []
    by_id = {s.get("node_id"): s for s in llm_scores if isinstance(s, dict)}
    out = []
    for s in spokes:
        b = dict(base.get(s["id"], {}))
        if not b:
            continue
        ll = by_id.get(s["id"])
        if ll:
            for key in ("days_of_supply", "viability_index"):
                try:
                    if key in ll:
                        b[key] = max(0.0, min(10.0 if key == "viability_index" else 365.0,
                                              float(ll[key])))
                except (TypeError, ValueError):
                    pass
            for key in ("projected_stockout_date", "top_constraint", "confidence"):
                if ll.get(key):
                    b[key] = ll[key]
            b["_source"] = "llm"
        out.append(b)
    return out


# ---- Step 2: Hero brief (chat) ---------------------------------------------

BRIEF_SYSTEM = """You are VITALS, the Joint Blood Logistics Decision-Support
agent. Compose a polished one-page COMMANDER'S DECISION BRIEF in markdown
with these EXACT section headers in order:

  - A bold one-line **BLUF:** at the top
  - ## Top 3 Spoke Nodes at Risk    (bullet list of 3, named + viability + DOS)
  - ## Secondary-Effect Cascades    (bullet list of 3: cold-chain, transport, lab-reagent)
  - ## Recommended Mitigation Actions (numbered list, 3-5 items)
  - ## Posture                       (one paragraph: on-prem Kamiwaza Stack, IL5/IL6 ready)

Constraints:
  - Cite specific spoke names + days-of-supply numbers from the data.
  - Each mitigation action MUST name a specific approved vendor by id
    (V-DRYICE-01 / V-REAGENT-02 / V-LIFT-03 / V-DONOR-04 / V-COURIER-05 /
    V-FRIDGE-06) when sourcing on the commercial / host-nation market. Use
    the contract_vehicle field verbatim where applicable.
  - Mention cold-chain loss, transport delays, and lab-reagent shortage as
    the three secondary cascades.
  - Total length <= 500 words.
  - Classification line: UNCLASSIFIED // FOR OFFICIAL USE."""


def build_brief_prompt(hub: dict, spokes: list[dict], scores: list[dict],
                       vendors: list[dict], scenario_id: str) -> list[dict]:
    by_id = {s["id"]: s for s in spokes}
    ranked = sorted(scores, key=lambda s: s["viability_index"])
    top3 = ranked[:3]
    top3_lines = [
        f"- {by_id[s['node_id']]['name']} ({s['node_id']}): viability "
        f"{s['viability_index']:.1f}/10, DOS {s['days_of_supply']:.1f}d, "
        f"top_constraint=\"{s['top_constraint']}\", conf={s['confidence']}"
        for s in top3 if s["node_id"] in by_id
    ]
    full_table = "\n".join(
        f"  {s['node_id']:8s} viability={s['viability_index']:4.1f}  "
        f"DOS={s['days_of_supply']:4.1f}d  {s['top_constraint'][:60]}"
        for s in ranked
    )
    scn = SCENARIOS.get(scenario_id, SCENARIOS["baseline"])
    user = (
        f"SCENARIO: {scn['label']}\n"
        f"CONSTRAINT: {scn['constraint']}\n"
        f"DTG: {datetime.now(timezone.utc).strftime('%d%H%MZ %b %Y').upper()}\n\n"
        f"HUB: {hub['name']} ({hub['id']}) — {hub['cold_chain_units']} cold-chain units, "
        f"{hub['dry_ice_kg']} kg dry ice, {hub['lab_reagent_days']}-day reagent supply.\n\n"
        f"Top-3 spokes at risk:\n" + "\n".join(top3_lines) + "\n\n"
        f"Full ranking:\n{full_table}\n\n"
        f"APPROVED VENDORS:\n{json.dumps(vendors, indent=2)}\n\n"
        f"Compose the Commander's Decision Brief now."
    )
    return [
        {"role": "system", "content": BRIEF_SYSTEM},
        {"role": "user", "content": user},
    ]


def _chat_with_timeout(msgs: list[dict], timeout_s: float, **kw) -> str | None:
    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
            return ex.submit(lambda: chat(msgs, **kw)).result(timeout=timeout_s)
    except (concurrent.futures.TimeoutError, Exception):
        return None


def write_brief(hub: dict, spokes: list[dict], scores: list[dict],
                vendors: list[dict], scenario_id: str = "baseline",
                *, hero: bool = True, use_cache: bool = True) -> str:
    """Cache-first hero brief generation.

    Strategy:
      1. If `data/cached_briefs.json` has the scenario, serve instantly.
      2. Otherwise call gpt-5.4 under HERO_CALL_TIMEOUT_S timeout.
      3. Fall back to mini chain under timeout.
      4. Last resort: deterministic baseline brief from generate.py.
    """
    if use_cache:
        cached = load_cached_briefs().get(scenario_id)
        if cached and cached.get("brief"):
            return cached["brief"]

    msgs = build_brief_prompt(hub, spokes, scores, vendors, scenario_id)
    if hero:
        text = _chat_with_timeout(
            msgs, HERO_CALL_TIMEOUT_S, model="gpt-5.4", temperature=0.4,
        )
        if text and "BLUF" in text:
            return text
    text = _chat_with_timeout(msgs, HERO_CALL_TIMEOUT_S, temperature=0.4)
    if text and "BLUF" in text:
        return text
    # last resort — call into generate._baseline_brief
    from data import generate as _g  # type: ignore
    return _g._baseline_brief(
        hub, spokes,
        load_inventory(), load_casualties(), load_routes(), vendors,
        {"id": scenario_id, **SCENARIOS.get(scenario_id, SCENARIOS["baseline"])},
    )


# ---- One-shot pipeline -----------------------------------------------------

def run_pipeline(scenario_id: str = "baseline", *, hero: bool = True) -> dict[str, Any]:
    hub = load_hub()
    spokes = load_spokes()
    inventory = load_inventory()
    routes = load_routes()
    casualties = load_casualties()
    vendors = load_vendors()

    inv_s, rts_s = apply_scenario(scenario_id, spokes, inventory, routes)
    scores = score_spokes(hub, spokes, inv_s, rts_s, casualties)
    brief = write_brief(hub, spokes, scores, vendors, scenario_id, hero=hero)

    return {
        "hub": hub, "spokes": spokes, "inventory": inv_s,
        "routes": rts_s, "casualties": casualties, "vendors": vendors,
        "scores": scores, "brief": brief,
        "scenario_id": scenario_id,
        "scenario": SCENARIOS.get(scenario_id, SCENARIOS["baseline"]),
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


if __name__ == "__main__":
    out = run_pipeline("airlift_loss", hero=False)
    print(json.dumps([{"id": s["node_id"], "viability": s["viability_index"],
                       "dos": s["days_of_supply"], "constraint": s["top_constraint"]}
                      for s in sorted(out["scores"], key=lambda s: s["viability_index"])],
                     indent=2))
    print("\n---\n")
    print(out["brief"])
