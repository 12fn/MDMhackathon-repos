"""CHAIN agent — two-step LLM pipeline over the disrupted supply network.

Step 1 (chat_json):  Structured analysis of the disrupted network →
                     {affected_marine_program, substitute_supplier,
                      lead_time_impact_days, mitigation_actions}.
Step 2 (chat):       Hero "Critical-Component Risk Brief for USMC PEO Land
                     Systems" narrative (gpt-5.4 preferred).

Cache-first: data/cached_briefs.json is pre-warmed by data/generate.py so the
demo path returns instantly. A deterministic baseline backstops every call so
the UI never sits on a spinner.
"""
from __future__ import annotations

import concurrent.futures
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Make `shared` importable when this file is run from anywhere.
ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from shared.kamiwaza_client import chat, chat_json  # noqa: E402

DATA_DIR = Path(__file__).resolve().parents[1] / "data"
CACHED_BRIEFS_PATH = DATA_DIR / "cached_briefs.json"

HERO_CALL_TIMEOUT_S = 35.0
SCORING_CALL_TIMEOUT_S = 25.0


# ─────────────────────────────────────────────────────────────────────────────
# I/O helpers
# ─────────────────────────────────────────────────────────────────────────────
def load_suppliers() -> list[dict]:
    return json.loads((DATA_DIR / "suppliers.json").read_text())


def load_edges() -> list[dict]:
    return json.loads((DATA_DIR / "edges.json").read_text())


def load_chokepoints() -> list[dict]:
    return json.loads((DATA_DIR / "chokepoints.json").read_text())


def load_events() -> list[dict]:
    import csv
    out: list[dict] = []
    with (DATA_DIR / "disruption_events.csv").open() as f:
        for row in csv.DictReader(f):
            row["estimated_impact_days"] = int(row.get("estimated_impact_days", 0) or 0)
            row["value_at_risk_musd"] = int(row.get("value_at_risk_musd", 0) or 0)
            out.append(row)
    return out


def load_cached_briefs() -> dict:
    if CACHED_BRIEFS_PATH.exists():
        try:
            return json.loads(CACHED_BRIEFS_PATH.read_text())
        except Exception:
            return {}
    return {}


# ─────────────────────────────────────────────────────────────────────────────
# Risk overlay — deterministic baseline (always non-zero, always instant)
# ─────────────────────────────────────────────────────────────────────────────
SEVERITY_WEIGHT = {"LOW": 0.15, "MODERATE": 0.45, "HIGH": 0.85, "CRITICAL": 1.4}

CHOKEPOINT_RISK = {
    "WATCH": 5.0, "ELEVATED": 6.5, "DEGRADED": 7.5, "CRITICAL": 9.0,
}


def baseline_node_risk(suppliers: list[dict], events: list[dict],
                       chokepoints: list[dict]) -> dict[str, float]:
    """Compute a 0-10 risk score per node from the disruption events feed.

    Used to color-code the topology graph instantly on page load.
    """
    cp_status = {c["id"]: c.get("status", "WATCH") for c in chokepoints}
    risk: dict[str, float] = {}
    by_id = {n["id"]: n for n in suppliers}

    # Event-driven contribution (decay older events)
    today = datetime.now(timezone.utc).date()
    for ev in events:
        try:
            d = datetime.strptime(ev["date"], "%Y-%m-%d").date()
        except Exception:
            continue
        age = max(0, (today - d).days)
        decay = max(0.1, 1.0 - age / 60.0)  # newest carries full weight
        w = SEVERITY_WEIGHT.get(ev.get("severity", "LOW"), 0.5) * decay
        risk[ev["target_id"]] = risk.get(ev["target_id"], 0.0) + w

    out: dict[str, float] = {}
    for n in suppliers:
        # base from criticality (1.5 .. 4.0)
        base = 1.5 + (n.get("criticality", 5) / 10.0) * 2.5
        # chokepoints get an explicit floor from current status
        if n["kind"] == "chokepoint" and n["id"] in cp_status:
            base = max(base, CHOKEPOINT_RISK.get(cp_status[n["id"]], 5.0))
        # event contribution capped so isolated single events don't push to critical
        ev_lift = min(3.5, risk.get(n["id"], 0.0))
        score = base + ev_lift
        out[n["id"]] = round(min(10.0, score), 2)
    return out


def nodes_at_critical_risk(node_risk: dict[str, float], threshold: float = 7.5) -> int:
    return sum(1 for r in node_risk.values() if r >= threshold)


# ─────────────────────────────────────────────────────────────────────────────
# Step 1 — structured network analysis (chat_json)
# ─────────────────────────────────────────────────────────────────────────────
NET_ANALYSIS_SYSTEM = (
    "You are CHAIN, a USMC LOGCOM critical-component sourcing analyst. "
    "Given a disruption scenario and the affected supply-network slice (suppliers, "
    "chokepoints, USMC end-items), return strict JSON with these exact keys:\n"
    '  "affected_marine_program": list of Marine program names (e.g. ACV, JLTV, MV-22, F-35B)\n'
    '  "substitute_supplier":     list of plausible alternate suppliers / re-routes\n'
    '  "lead_time_impact_days":   integer estimate of total program-level slip in days\n'
    '  "mitigation_actions":      list of <=5 concrete COA strings\n'
    "Be calibrated, defense-aware, and reference rare-earth, EUV, silicon-wafer, "
    "and turbine-engine dependencies where applicable."
)


def _affected_subnetwork(scenario_chokepoint: str, suppliers: list[dict],
                         edges: list[dict]) -> list[dict]:
    by_id = {n["id"]: n for n in suppliers}
    affected: set[str] = set()
    for e in edges:
        if e["a"] == scenario_chokepoint or e["b"] == scenario_chokepoint:
            affected.add(e["a"]); affected.add(e["b"])
    primes = [i for i in affected if by_id.get(i, {}).get("kind") == "supplier"]
    for e in edges:
        if e["a"] in primes and by_id.get(e["b"], {}).get("kind") == "end_item":
            affected.add(e["b"])
    return [by_id[i] for i in affected if i in by_id]


def _call_chat_json_with_timeout(msgs: list[dict], timeout_s: float) -> dict | None:
    def _go() -> dict:
        return chat_json(
            msgs,
            schema_hint='{"affected_marine_program":[str],"substitute_supplier":[str],'
                        '"lead_time_impact_days":int,"mitigation_actions":[str]}',
            temperature=0.2,
        )
    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
            return ex.submit(_go).result(timeout=timeout_s)
    except (concurrent.futures.TimeoutError, Exception):
        return None


def analyze_network(scenario: dict, suppliers: list[dict], edges: list[dict],
                    chokepoints: list[dict]) -> dict:
    """Step 1: structured analysis. Always returns a dict (baseline on timeout)."""
    sub = _affected_subnetwork(scenario["primary_chokepoint"], suppliers, edges)
    sub_brief = [{"id": s["id"], "name": s["name"], "kind": s["kind"],
                  "country": s["country"], "category": s["category"],
                  "annual_value_musd": s["annual_value_musd"]} for s in sub]
    cp = next((c for c in chokepoints if c["id"] == scenario["primary_chokepoint"]), None)
    msgs = [
        {"role": "system", "content": NET_ANALYSIS_SYSTEM},
        {"role": "user",
         "content": f"Disruption scenario: {scenario['title']}\n"
                    f"Headline: {scenario['headline']}\n\n"
                    f"Primary chokepoint: {json.dumps(cp, indent=2)}\n\n"
                    f"Affected subnetwork:\n{json.dumps(sub_brief, indent=2)}\n\n"
                    "Return JSON only."},
    ]
    raw = _call_chat_json_with_timeout(msgs, SCORING_CALL_TIMEOUT_S)
    if raw and isinstance(raw, dict) and raw.get("affected_marine_program"):
        raw["primary_chokepoint"] = scenario["primary_chokepoint"]
        raw["scenario_id"] = scenario["id"]
        raw["_source"] = "llm"
        return raw
    return _baseline_struct(scenario, sub)


def _baseline_struct(scenario: dict, sub: list[dict]) -> dict:
    programs = [n["name"] for n in sub if n["kind"] == "end_item"]
    return {
        "affected_marine_program": programs[:6] or ["ACV", "AMPV", "JLTV", "MV-22B Osprey"],
        "substitute_supplier": [
            "MP Materials (Mountain Pass, USA)",
            "Lynas Mt Weld (Australia)",
            "Cape of Good Hope re-route (+12d)",
        ],
        "lead_time_impact_days": 30,
        "mitigation_actions": [
            "Activate DPAS-DX rating on affected procurement lines",
            "Engage DLA Strategic Materials for stockpile release",
            "Initiate Defense Production Act Title III alternate-source qualification",
            "Stand up daily PEO sync until restoration",
        ],
        "primary_chokepoint": scenario["primary_chokepoint"],
        "scenario_id": scenario["id"],
        "_source": "baseline",
    }


# ─────────────────────────────────────────────────────────────────────────────
# Step 2 — hero brief (chat)
# ─────────────────────────────────────────────────────────────────────────────
HERO_SYSTEM = (
    "You are CHAIN, a USMC global-supply-chain disruption analyst writing a "
    "Critical-Component Risk Brief for PEO Land Systems and PEO Aviation. "
    "Compose a polished one-page brief with these EXACT markdown headers in order:\n"
    "  # Critical-Component Risk Brief — <scenario title>\n"
    "  **Audience:** USMC PEO Land Systems / PEO Aviation\n"
    "  ## BLUF\n  ## Exposed Programs\n  ## Mitigation Playbook\n  ## Decision Required\n"
    "Cite specific Marine programs (ACV, AMPV, JLTV, MV-22, F-35B, CH-53K, HIMARS) and "
    "name specific component dependencies (rare-earth magnets, EUV optics, silicon wafers, "
    "turbine engines). Keep total length under ~450 words. Include classification line: "
    "UNCLASSIFIED // FOR OFFICIAL USE ONLY."
)


def _call_chat_with_timeout(msgs: list[dict], timeout_s: float, **kw) -> str | None:
    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
            return ex.submit(lambda: chat(msgs, **kw)).result(timeout=timeout_s)
    except (concurrent.futures.TimeoutError, Exception):
        return None


def write_brief(scenario: dict, struct: dict, *, hero: bool = True,
                use_cache: bool = True) -> str:
    """Step 2: hero narrative brief.

    1. If a cached brief exists for this scenario_id, serve instantly.
    2. Else hero gpt-5.4 under timeout.
    3. Else standard mini chain under timeout.
    4. Last resort: deterministic baseline brief.
    """
    if use_cache:
        cache = load_cached_briefs()
        entry = cache.get(scenario["id"])
        if entry and entry.get("brief"):
            return entry["brief"]

    msgs = [
        {"role": "system", "content": HERO_SYSTEM},
        {"role": "user",
         "content": f"Scenario: {scenario['title']}\nHeadline: {scenario['headline']}\n\n"
                    f"Structured analysis input:\n{json.dumps(struct, indent=2)}\n\n"
                    "Compose the Critical-Component Risk Brief now."},
    ]
    if hero:
        text = _call_chat_with_timeout(msgs, HERO_CALL_TIMEOUT_S,
                                       model="gpt-5.4", temperature=0.45)
        if text and "BLUF" in text:
            _save_brief(scenario["id"], text, source="gpt-5.4", struct=struct)
            return text
    text = _call_chat_with_timeout(msgs, HERO_CALL_TIMEOUT_S, temperature=0.45)
    if text and "BLUF" in text:
        _save_brief(scenario["id"], text, source="default-chain", struct=struct)
        return text
    return _fallback_brief(scenario, struct)


def _fallback_brief(scenario: dict, struct: dict) -> str:
    progs = ", ".join(struct.get("affected_marine_program", []) or ["ACV", "JLTV"])
    subs = "\n".join(f"  - {s}" for s in struct.get("substitute_supplier", []))
    actions = "\n".join(f"{i+1}. {a}" for i, a in enumerate(struct.get("mitigation_actions", [])))
    return (
        f"# Critical-Component Risk Brief — {scenario['title']}\n"
        f"**Audience:** USMC PEO Land Systems / PEO Aviation\n"
        f"**Classification:** UNCLASSIFIED // FOR OFFICIAL USE ONLY\n\n"
        f"## BLUF\n{scenario['headline']} Estimated "
        f"{struct.get('lead_time_impact_days', 30)}-day program slip absent mitigation.\n\n"
        f"## Exposed Programs\n- Affected Marine programs: {progs}.\n"
        f"- Primary chokepoint: {struct.get('primary_chokepoint', '—')}.\n\n"
        f"## Mitigation Playbook\nSubstitute suppliers / re-routes:\n{subs}\n\n"
        f"Actions:\n{actions}\n\n"
        f"## Decision Required\nPEO Land Systems and PEO Aviation review by 72h; "
        f"recommend Title III invocation if delay exposure exceeds 21 days at any chokepoint.\n"
    )


def _save_brief(scenario_id: str, text: str, *, source: str, struct: dict) -> None:
    try:
        cache = load_cached_briefs()
        cache[scenario_id] = {
            "scenario_id": scenario_id,
            "brief": text,
            "structured": struct,
            "source": source,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }
        CACHED_BRIEFS_PATH.write_text(json.dumps(cache, indent=2))
    except Exception:
        pass


def run_pipeline(scenario: dict, *, hero: bool = True) -> dict[str, Any]:
    suppliers = load_suppliers()
    edges = load_edges()
    chokepoints = load_chokepoints()
    events = load_events()
    risk = baseline_node_risk(suppliers, events, chokepoints)
    struct = analyze_network(scenario, suppliers, edges, chokepoints)
    brief = write_brief(scenario, struct, hero=hero)
    return {
        "scenario": scenario,
        "suppliers": suppliers, "edges": edges, "chokepoints": chokepoints,
        "events": events, "risk": risk, "structured": struct, "brief": brief,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


if __name__ == "__main__":
    out = run_pipeline({"id": "taiwan_strait", "title": "Taiwan Strait closure",
                        "primary_chokepoint": "TWNSTRAIT",
                        "headline": "PLAN exercise box closes the strait."},
                       hero=False)
    print(json.dumps({"struct": out["structured"]}, indent=2))
    print("\n---\n", out["brief"][:600])
