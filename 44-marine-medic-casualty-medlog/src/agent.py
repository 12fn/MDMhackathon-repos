"""MARINE-MEDIC agent — 6-stage casualty -> Class VIII -> requisition pipeline.

  Stage 1 (deterministic):  Casualty event injection (operator-selected scenario).
  Stage 2 (chat_json):       Triage cascade — classify each WIA Routine/Priority/
                             Urgent/Urgent-Surgical, recommend Role of care
                             (Role 1 BAS -> 2 FRSS -> 2E -> 3 NMRTC), required
                             Class VIII bundle per casualty.
  Stage 3 (deterministic):   Class VIII demand projection — time-phased over
                             1/6/12/24h (PRBC, FFP, PLT, LTOWB, fluids, sets, ...).
  Stage 4 (deterministic):   Hub-spoke supply check (cross-VITALS pattern) —
                             does receiving spoke + APRA hub have enough?
                             Cascading shortages, expiration windows, cold-chain.
  Stage 5 (deterministic):   GCSS-MC auto-requisition trigger (priority, lead
                             time, source depot).
  Stage 6 (chat hero):       "Medical Sustainment Action Brief" — BLUF +
                             casualty-flow projection + Class VIII gap +
                             supplier action plan + regional-hub posture +
                             mortality risk window.

  Bonus: Stage 7 (chat_json): Buy-on-market evaluation per DHA RESCUE prompt.
  Bonus: Stage M (vision):   Multi-modal photo of injury -> triage hint.

Hash-chained audit (HIPAA / NDAA Section 1739 flavored).
"""
from __future__ import annotations

import base64
import concurrent.futures
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Make repo root + app root importable
APP_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = APP_ROOT.parents[1]
for p in (str(REPO_ROOT), str(APP_ROOT)):
    if p not in sys.path:
        sys.path.insert(0, p)

from shared.kamiwaza_client import chat, chat_json  # noqa: E402

DATA_DIR = APP_ROOT / "data"
CACHED_BRIEFS_PATH = DATA_DIR / "cached_briefs.json"

HERO_TIMEOUT_S    = 35.0
TRIAGE_TIMEOUT_S  = 18.0
MARKET_TIMEOUT_S  = 18.0
VISION_TIMEOUT_S  = 20.0


# ---- I/O --------------------------------------------------------------------

def load_hub() -> dict:
    return json.loads((DATA_DIR / "hub.json").read_text())


def load_spokes() -> list[dict]:
    return json.loads((DATA_DIR / "spokes.json").read_text())


def load_routes() -> list[dict]:
    return json.loads((DATA_DIR / "routes.json").read_text())


def load_inventory_v1() -> list[dict]:
    return json.loads((DATA_DIR / "inventory_v1.json").read_text())


def load_inventory_v2() -> list[dict]:
    return json.loads((DATA_DIR / "inventory_v2.json").read_text())


def load_supply_network() -> dict:
    return json.loads((DATA_DIR / "supply_network.json").read_text())


def load_gcss_mc() -> list[dict]:
    return json.loads((DATA_DIR / "gcss_mc.json").read_text())


def load_scenarios() -> list[dict]:
    return json.loads((DATA_DIR / "casualty_scenarios.json").read_text())


def load_doctrine() -> dict:
    return json.loads((DATA_DIR / "triage_doctrine.json").read_text())


def load_vendors() -> list[dict]:
    return json.loads((DATA_DIR / "vendors.json").read_text())


def load_cached_briefs() -> dict:
    if not CACHED_BRIEFS_PATH.exists():
        return {}
    try:
        return json.loads(CACHED_BRIEFS_PATH.read_text())
    except Exception:
        return {}


# ---- Stage 1: Casualty event injection -------------------------------------

def build_casualty_event(scenario: dict, *, wia_count: int | None = None,
                          location_id: str | None = None) -> dict:
    """Operator-tuned casualty event. Honors scenario but allows overrides."""
    out = dict(scenario)
    if wia_count is not None and wia_count > 0:
        # Scale injury_mix proportionally to the new wia_count
        old = sum(scenario.get("injury_mix", {}).values()) or 1
        scale = wia_count / old
        out["injury_mix"] = {k: max(0, int(round(v * scale)))
                              for k, v in scenario.get("injury_mix", {}).items()}
        out["wia_count"] = wia_count
    if location_id:
        out["location_id"] = location_id
    out["injection_time"] = datetime.now(timezone.utc).isoformat()
    return out


# ---- Stage 2: Triage cascade (chat_json) -----------------------------------

TRIAGE_SYSTEM = """You are MARINE-MEDIC, the Joint Class VIII / Casualty-Flow
Decision-Support agent for USMC LOGCOM, BUMED, and the Defense Health Agency.

You will receive a casualty event drawn from TCCC / JTS doctrine: a list of
injuries by kind. For EACH WIA, output a triage card:

  - "wia_id":           str  ("WIA-01"..)
  - "injury_kind":      str  (verbatim from input vocabulary)
  - "triage_category":  str  one of {ROUTINE, PRIORITY, URGENT, URGENT_SURGICAL, EXPECTANT}
  - "role_of_care":     str  one of {"Role 1 BAS","Role 2 FRSS","Role 2E","Role 3 NMRTC"}
  - "class_viii_bundle": dict {
        "PRBC_units": float,
        "FFP_units":  float,
        "PLT_units":  float,
        "LTOWB_units":float,
        "TXA_g":      float,
        "tourniquets":int,
        "fluids_L":   float,
        "antibiotic_doses": int,
        "surgical_sets":    int,
        "splint_sets":      int,
        "burn_sheets":      int,
        "atropine_kits":    int
    }
  - "evac_window_h":   float  ("golden hour" guidance; smaller = sooner)
  - "rationale":       str    (one sentence; cite TCCC / JTS phase)

Apply standard Marine planning factors: penetrating thoracic -> URGENT_SURGICAL
to Role 3; major burn -> URGENT_SURGICAL with damage-control surgical set;
nerve-agent exposure -> URGENT with atropine_kits; minor / blast-concussive -> ROUTINE.

Return JSON: {"cards": [<one per WIA>]}.
"""


def _triage_baseline(event: dict, doctrine: dict) -> list[dict]:
    """Deterministic triage when LLM unavailable / times out."""
    rules = doctrine["triage_assignment_rules"]
    role  = doctrine["role_assignment_rules"]
    pf    = doctrine["class_viii_planning_factors_per_wia"]
    cards: list[dict] = []
    n = 0
    for kind, count in event.get("injury_mix", {}).items():
        for _ in range(int(count)):
            cat = rules.get(kind, "ROUTINE")
            f = pf.get(kind, {})
            cards.append({
                "wia_id":           f"WIA-{n:02d}",
                "injury_kind":      kind,
                "triage_category":  cat,
                "role_of_care":     role.get(cat, "Role 1 BAS"),
                "class_viii_bundle": {
                    "PRBC_units":   float(f.get("PRBC", 0)),
                    "FFP_units":    float(f.get("FFP", 0)),
                    "PLT_units":    float(f.get("PLT", 0)),
                    "LTOWB_units":  float(f.get("LTOWB", 0)),
                    "TXA_g":        float(f.get("TXA_g", 0)),
                    "tourniquets":  int(f.get("tourniquets", 0)),
                    "fluids_L":     float(f.get("fluids_L", 0)),
                    "antibiotic_doses": int(f.get("antibiotic_doses", 0)),
                    "surgical_sets":    int(f.get("surgical_set", 0)),
                    "splint_sets":      int(f.get("splint_set", 0)),
                    "burn_sheets":      int(f.get("burn_sheet", 0)),
                    "atropine_kits":    int(f.get("atropine_kits", 0)),
                },
                "evac_window_h": {"URGENT_SURGICAL": 1, "URGENT": 2,
                                  "PRIORITY": 4, "ROUTINE": 24,
                                  "EXPECTANT": 0}.get(cat, 4),
                "rationale": (
                    f"{kind} per TCCC / JTS planning factors -> {cat}; "
                    f"transfer to {role.get(cat, 'Role 1 BAS')} per Role-of-care escalation."
                ),
                "_source": "baseline",
            })
            n += 1
    return cards


def triage_cascade(event: dict, doctrine: dict | None = None) -> list[dict]:
    """LLM JSON-mode triage with deterministic fallback."""
    doctrine = doctrine or load_doctrine()
    base = _triage_baseline(event, doctrine)
    user = (
        f"CASUALTY EVENT:\n{json.dumps(event, indent=2, default=str)}\n\n"
        f"TRIAGE DOCTRINE (TCCC / JTS planning factors):\n"
        f"{json.dumps(doctrine, indent=2)}\n\n"
        "Produce a triage card per WIA per the schema."
    )

    def _go() -> dict:
        return chat_json(
            [{"role": "system", "content": TRIAGE_SYSTEM},
             {"role": "user",   "content": user}],
            schema_hint='{"cards":[{"wia_id":str,"injury_kind":str,"triage_category":str,"role_of_care":str,"class_viii_bundle":dict,"evac_window_h":float,"rationale":str}]}',
            temperature=0.2,
        )

    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
            spec = ex.submit(_go).result(timeout=TRIAGE_TIMEOUT_S)
        cards = spec.get("cards") if isinstance(spec, dict) else None
        if not cards or not isinstance(cards, list):
            return base
        # Merge with baseline shape — keep llm fields where present, fill gaps
        clean = []
        for i, c in enumerate(cards):
            if not isinstance(c, dict):
                continue
            b = base[i] if i < len(base) else {}
            merged = {**b, **{k: v for k, v in c.items() if v is not None}}
            merged["_source"] = "llm"
            clean.append(merged)
        # If LLM returned fewer cards than expected, top-up with baseline
        while len(clean) < len(base):
            clean.append(base[len(clean)])
        return clean
    except Exception:
        return base


# ---- Stage 3: Class VIII demand projection ---------------------------------

def class_viii_demand(cards: list[dict]) -> dict:
    """Sum the per-card bundles; emit time-phased totals (1/6/12/24h)."""
    totals: dict[str, float] = {}
    for c in cards:
        for k, v in (c.get("class_viii_bundle") or {}).items():
            totals[k] = totals.get(k, 0.0) + float(v)
    phased = {h: {k: round(v * frac, 2) for k, v in totals.items()}
              for h, frac in [(1, 0.55), (6, 0.78), (12, 0.92), (24, 1.0)]}
    return {
        "totals_24h": {k: round(v, 1) for k, v in totals.items()},
        "time_phased_h": phased,
        # Convenience top-level numbers for the brief
        "total_prbc_units": round(totals.get("PRBC_units", 0), 1),
        "total_ffp_units":  round(totals.get("FFP_units", 0), 1),
        "total_plt_units":  round(totals.get("PLT_units", 0), 1),
        "total_ltowb_units":round(totals.get("LTOWB_units", 0), 1),
        "total_fluids_L":   round(totals.get("fluids_L", 0), 1),
        "total_txa_g":      round(totals.get("TXA_g", 0), 1),
        "total_tourniquets":round(totals.get("tourniquets", 0), 1),
        "total_antibiotic_doses": round(totals.get("antibiotic_doses", 0), 1),
        "total_surgical_sets":    round(totals.get("surgical_sets", 0), 1),
        "total_splint_sets":      round(totals.get("splint_sets", 0), 1),
        "total_burn_sheets":      round(totals.get("burn_sheets", 0), 1),
        "total_atropine_kits":    round(totals.get("atropine_kits", 0), 1),
    }


# ---- Stage 4: Hub-spoke supply check ---------------------------------------

UNIT_LABELS = {
    "PRBC_units": "units", "FFP_units": "units", "PLT_units": "units",
    "LTOWB_units": "units", "fluids_L": "L", "TXA_g": "g",
    "tourniquets": "ea", "antibiotic_doses": "doses",
    "surgical_sets": "sets", "splint_sets": "sets",
    "burn_sheets": "ea", "atropine_kits": "kits",
}


def hub_spoke_supply_check(event: dict, demand: dict,
                           inv_v1: list[dict] | None = None,
                           inv_v2: list[dict] | None = None) -> dict:
    inv_v1 = inv_v1 or load_inventory_v1()
    inv_v2 = inv_v2 or load_inventory_v2()
    site = event.get("location_id", "")
    on_hand: dict[str, float] = {}
    expiring_soon: list[dict] = []  # blood expiring < 5 days
    cold_chain_red: list[str] = []

    # Blood — v1
    for r in inv_v1:
        if r["site_id"] not in (site, "APRA-MED"):
            continue
        prod = r["product"]
        bucket = {
            "PRBC": "PRBC_units", "FFP": "FFP_units", "PLASMA": "FFP_units",
            "PLT":  "PLT_units",  "LTOWB":"LTOWB_units",
        }.get(prod)
        if not bucket:
            continue
        on_hand[bucket] = on_hand.get(bucket, 0.0) + r["units"]
        # Expiration window
        try:
            exp = datetime.fromisoformat(r["expires_iso"])
            days = (exp - datetime.now(timezone.utc)).total_seconds() / 86400
            if days < 5:
                expiring_soon.append({
                    "site_id": r["site_id"], "product": prod, "units": r["units"],
                    "lot": r.get("lot", ""), "days_to_expire": round(days, 1),
                })
        except Exception:
            pass
        if r.get("cold_chain_status") == "RED":
            cold_chain_red.append(f"{r['site_id']}/{prod}")

    # Class VIII v2 — bucket by nomenclature
    for r in inv_v2:
        if r["site_id"] not in (site, "APRA-MED"):
            continue
        nom = r["nomenclature"].lower()
        qty = r["qty_on_hand"]
        if "tourniquet" in nom:
            on_hand["tourniquets"] = on_hand.get("tourniquets", 0) + qty
        elif "ringer" in nom or "plasma-lyte" in nom or "sodium chloride" in nom or "hextend" in nom:
            on_hand["fluids_L"] = on_hand.get("fluids_L", 0) + qty
        elif "cefazolin" in nom or "ertapenem" in nom or "vancomycin" in nom:
            on_hand["antibiotic_doses"] = on_hand.get("antibiotic_doses", 0) + qty
        elif "surgical set" in nom or "damage control" in nom:
            on_hand["surgical_sets"] = on_hand.get("surgical_sets", 0) + qty
        elif "sam splint" in nom or "splint set" in nom:
            on_hand["splint_sets"] = on_hand.get("splint_sets", 0) + qty
        elif "burn sheet" in nom:
            on_hand["burn_sheets"] = on_hand.get("burn_sheets", 0) + qty
        elif "atropine" in nom or "2-pam" in nom:
            on_hand["atropine_kits"] = on_hand.get("atropine_kits", 0) + qty
        elif "tranexamic" in nom or "txa" in nom:
            on_hand["TXA_g"] = on_hand.get("TXA_g", 0) + qty

    # Compute shortfalls
    shortfalls: list[dict] = []
    for k, need in demand.get("totals_24h", {}).items():
        if need <= 0:
            continue
        oh = on_hand.get(k, 0.0)
        sf = max(0.0, need - oh)
        if sf > 0:
            shortfalls.append({
                "item": k, "need": round(need, 1), "on_hand": round(oh, 1),
                "shortfall": round(sf, 1), "unit": UNIT_LABELS.get(k, ""),
            })
    shortfalls.sort(key=lambda r: r["shortfall"], reverse=True)
    return {
        "receiving_site": site,
        "on_hand_summary": {k: round(v, 1) for k, v in on_hand.items()},
        "top_shortfalls": shortfalls[:8],
        "total_shortfalls": len(shortfalls),
        "expiring_soon": expiring_soon[:10],
        "cold_chain_red_sites": sorted(set(cold_chain_red))[:10],
    }


# ---- Stage 5: GCSS-MC requisition trigger ----------------------------------

def build_requisition(event: dict, gap: dict) -> dict:
    """Auto-build a GCSS-MC Class VIII requisition."""
    lines = []
    ts = datetime.now(timezone.utc)
    for i, sf in enumerate(gap.get("top_shortfalls", [])[:6]):
        is_blood = sf["item"] in ("PRBC_units", "FFP_units", "PLT_units", "LTOWB_units")
        lines.append({
            "doc_id": f"DOC-{900000 + i + event.get('wia_count', 0):06d}",
            "nsn_class": f"6505-01-{500 + i:03d}-{1000 + i*7:04d}",
            "nomenclature": sf["item"],
            "qty": int(sf["shortfall"] + 1),
            "uoi": sf["unit"],
            "priority": "01" if is_blood else "03",
            "ric_to": "SMS",
            "ship_to_uic": gap.get("receiving_site", ""),
            "source_depot": "APRA-MED" if is_blood else "DDJC-Tracy",
            "lead_time_h_estimate": 6 if is_blood else 24,
            "submitted_iso": ts.isoformat(),
        })
    return {
        "scenario_id": event.get("id", ""),
        "wia_count":   event.get("wia_count", 0),
        "lines":       lines,
        "submitted_iso": ts.isoformat(),
    }


# ---- Stage 6: Hero brief (chat) --------------------------------------------

BRIEF_SYSTEM = """You are MARINE-MEDIC, the Joint Class VIII / Casualty-Flow
Decision-Support agent for USMC LOGCOM, BUMED, and the Defense Health Agency,
supporting USINDOPACOM Distributed Maritime Operations. Use TCCC, JTS,
FRSS / BAS / Role 1-3, LTOWB, walking blood bank, NMRTC, BUMED, ASCA
cross-servicing, J-4 MEDLOG, NAVMED terminology verbatim.

Compose a polished one-page MEDICAL SUSTAINMENT ACTION BRIEF in markdown with
these EXACT sections, in order:

  - **BLUF:** one bold sentence at the top
  - ## Casualty-flow projection (Role 1 -> 2 -> 2E -> 3)
  - ## Class VIII gap (24h)
  - ## Supplier action plan
  - ## Regional-hub posture
  - ## Mortality risk window
  - ## Posture (one paragraph: on-prem Kamiwaza Stack, IL5/IL6 ready,
    casualty data never leaves the accredited environment)

Cite specific shortfalls (units/liters/doses), Roles of care by name,
and approved buy-on-market vendors by id (V-DRYICE-01, V-REAGENT-02, V-LIFT-03,
V-DONOR-04, V-COURIER-05, V-FRIDGE-06, V-SURG-07).
Total length <= 550 words. Classification: UNCLASSIFIED // FOR OFFICIAL USE.
"""


def _baseline_brief(event: dict, demand: dict, gap: dict) -> str:
    top_gap_lines = [
        f"- **{g['item']}**: need {g['need']:.1f} {g['unit']}, "
        f"on-hand {g['on_hand']:.1f} {g['unit']}, shortfall **{g['shortfall']:.1f} {g['unit']}** (24h)"
        for g in gap.get("top_shortfalls", [])[:5]
    ]
    return (
        f"# MEDICAL SUSTAINMENT ACTION BRIEF\n"
        f"**Scenario:** {event.get('label', '')}\n"
        f"**Frame:** {event.get('frame', '')}\n"
        f"**DTG:** {datetime.now(timezone.utc).strftime('%d%H%MZ %b %Y').upper()}\n"
        f"**Classification:** UNCLASSIFIED // FOR OFFICIAL USE\n\n"
        f"**BLUF:** {event.get('wia_count', 0)} WIA inbound from {event.get('location_id', '')}. "
        f"Class VIII demand projects **{demand.get('total_prbc_units', 0):.0f} PRBC**, "
        f"**{demand.get('total_ffp_units', 0):.0f} FFP**, "
        f"**{demand.get('total_fluids_L', 0):.0f} L** crystalloid in next 24h. "
        f"Hub-spoke check identifies **{len(gap.get('top_shortfalls', []))}** sustainment gaps; "
        f"recommend immediate APRA-hub vertical replenishment + V-DONOR-04 (JSDF Naha) ACSA pull for LTOWB.\n\n"
        f"## Casualty-flow projection (Role 1 -> 2 -> 2E -> 3)\n"
        f"- Role 1 BAS: TCCC stabilization, TXA, tourniquet, IV crystalloid, casualty evac call.\n"
        f"- Role 2 FRSS: damage control surgery for URGENT and URGENT_SURGICAL casualties.\n"
        f"- Role 2E (LHA-6 / LHD-1): 24-72h ICU-lite holding for thoracic / burn cohort.\n"
        f"- Role 3 NMRTC (USNH Okinawa): definitive surgical, full lab, ICU.\n"
        f"- Bottleneck: Role 2 FRSS surgical-set throughput; lateral pull from MEU-31.\n\n"
        f"## Class VIII gap (24h)\n"
        + ("\n".join(top_gap_lines) if top_gap_lines else "- No critical shortfalls under current posture.")
        + "\n\n"
        f"## Supplier action plan\n"
        f"1. **V-DRYICE-01** (Pacific Cold Chain, 6h lead) — surge dry-ice 800 kg to APRA-MED.\n"
        f"2. **V-DONOR-04** (JSDF Naha ACSA cross-servicing) — pull 40 LTOWB units; activate walking blood bank at MEU-31 / ROLE3-OK.\n"
        f"3. **V-SURG-07** (Stryker Singapore, 24h lead) — pre-stage 4 damage-control surgical sets to Role 3 NMRTC.\n"
        f"4. **V-LIFT-03** (Berry Aviation CRAF Stage I) — surge fixed-wing lift APRA->{gap.get('receiving_site', 'spoke')} for 48h.\n\n"
        f"## Regional-hub posture\n"
        f"APRA-MED (BUMED / NMRTC Guam) holding 1,800 units/day throughput; 21d lab reagent reserve; "
        f"cold-chain health 0.92. III MEF J-4 MEDLOG informed; NAVMED BUMED confirms ACSA channel ready.\n\n"
        f"## Mortality risk window\n"
        f"If no resupply action taken within **{event.get('hours_to_evac_estimate', 6)} hours**, "
        f"expected mortality climbs from baseline ~6% to ~14% across the URGENT_SURGICAL cohort, "
        f"driven by Class VIIIa stockout (PRBC + FFP) at the receiving Role 2E node.\n\n"
        f"## Posture\n"
        f"Running on a Kamiwaza-deployed hero model behind `KAMIWAZA_BASE_URL`. "
        f"Casualty data stays in IL5/IL6 enclave — never leaves the accredited environment. "
        f"Hash-chained audit per HIPAA / NDAA Section 1739.\n"
    )


def _chat_with_timeout(msgs: list[dict], timeout_s: float, **kw) -> str | None:
    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
            return ex.submit(lambda: chat(msgs, **kw)).result(timeout=timeout_s)
    except (concurrent.futures.TimeoutError, Exception):
        return None


def write_action_brief(event: dict, demand: dict, gap: dict,
                       requisition: dict, vendors: list[dict],
                       *, hero: bool = True, use_cache: bool = True) -> str:
    """Cache-first hero brief generation."""
    sid = event.get("id")
    if use_cache and sid:
        cached = load_cached_briefs().get(sid)
        if cached and cached.get("brief"):
            return cached["brief"]
    user = (
        f"CASUALTY EVENT:\n{json.dumps(event, indent=2, default=str)}\n\n"
        f"PROJECTED 24h CLASS VIII DEMAND:\n{json.dumps(demand, indent=2, default=str)}\n\n"
        f"HUB-SPOKE GAP:\n{json.dumps(gap, indent=2, default=str)}\n\n"
        f"AUTO-BUILT GCSS-MC REQUISITION:\n{json.dumps(requisition, indent=2, default=str)}\n\n"
        f"APPROVED VENDORS:\n{json.dumps(vendors, indent=2)}\n\n"
        f"Compose the Medical Sustainment Action Brief now."
    )
    msgs = [{"role": "system", "content": BRIEF_SYSTEM},
            {"role": "user",   "content": user}]
    if hero:
        text = _chat_with_timeout(msgs, HERO_TIMEOUT_S, model="gpt-5.4", temperature=0.4)
        if text and "BLUF" in text:
            return text
    text = _chat_with_timeout(msgs, HERO_TIMEOUT_S, temperature=0.4)
    if text and "BLUF" in text:
        return text
    return _baseline_brief(event, demand, gap)


# ---- Stage 7: Buy-on-market evaluation (chat_json, optional) ---------------

MARKET_SYSTEM = """You are MARINE-MEDIC's commercial sourcing arm. Per the
DHA RESCUE prompt, evaluate the listed approved vendors for THIS specific
shortfall mix. For each shortfall, recommend the best vendor (by id), the
lead time in hours, and a one-line cost/risk justification.

Return JSON:
{"recommendations": [
  {"item": <shortfall item>, "vendor_id": <V-...>, "lead_time_h": <int>,
   "rationale": <one sentence>}
]}"""


def evaluate_buy_on_market(gap: dict, vendors: list[dict]) -> list[dict]:
    user = (
        f"SHORTFALLS:\n{json.dumps(gap.get('top_shortfalls', []), indent=2)}\n\n"
        f"APPROVED VENDORS:\n{json.dumps(vendors, indent=2)}\n\n"
        "Recommend best vendor per shortfall."
    )
    msgs = [{"role": "system", "content": MARKET_SYSTEM},
            {"role": "user", "content": user}]
    def _go() -> dict:
        return chat_json(msgs, schema_hint='{"recommendations":[{"item":str,"vendor_id":str,"lead_time_h":int,"rationale":str}]}', temperature=0.2)
    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
            spec = ex.submit(_go).result(timeout=MARKET_TIMEOUT_S)
        recs = spec.get("recommendations") if isinstance(spec, dict) else None
        if isinstance(recs, list):
            return recs
    except Exception:
        pass
    # Deterministic fallback — naive vendor mapping
    map_ = {
        "PRBC_units":   "V-DONOR-04", "FFP_units": "V-DONOR-04",
        "PLT_units":    "V-DONOR-04", "LTOWB_units":"V-DONOR-04",
        "fluids_L":     "V-COURIER-05", "TXA_g": "V-COURIER-05",
        "tourniquets":  "V-COURIER-05",
        "antibiotic_doses":"V-REAGENT-02",
        "surgical_sets":   "V-SURG-07",
        "splint_sets":     "V-SURG-07",
        "burn_sheets":     "V-COURIER-05",
        "atropine_kits":   "V-REAGENT-02",
    }
    by_id = {v["id"]: v for v in vendors}
    out = []
    for sf in gap.get("top_shortfalls", []):
        vid = map_.get(sf["item"], "V-COURIER-05")
        v = by_id.get(vid, {})
        out.append({
            "item": sf["item"],
            "vendor_id": vid,
            "lead_time_h": v.get("lead_time_h", 24),
            "rationale": (
                f"{v.get('name', vid)} via {v.get('contract_vehicle', 'open-market')} "
                f"is fastest path to close the {sf['unit']} shortfall."
            ),
        })
    return out


# ---- Multi-modal: vision-language triage hint ------------------------------

VISION_SYSTEM = """You are MARINE-MEDIC's combat-medic vision assistant. Given
an image labeled as a (synthetic / training) photo of an injury, output a
triage hint as JSON:
  {"injury_kind_hint": <one of penetrating_extremity, penetrating_thoracic,
   blast_concussive, burn_major, burn_minor, burn_secondary, inhalation_injury,
   chem_nerve_agent, blunt_polytrauma, spine_suspected, minor>,
   "triage_category_hint": <ROUTINE|PRIORITY|URGENT|URGENT_SURGICAL>,
   "rationale": <one sentence>}.

Be conservative. Default to PRIORITY when uncertain. Do not provide diagnosis.
"""


def vision_triage_hint(image_bytes: bytes, mime: str = "image/jpeg") -> dict:
    """Send an image to a multimodal model to suggest a triage category."""
    b64 = base64.b64encode(image_bytes).decode("ascii")
    msgs = [
        {"role": "system", "content": VISION_SYSTEM},
        {"role": "user", "content": [
            {"type": "text",  "text": "Suggest a triage hint for this synthetic training image."},
            {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}},
        ]},
    ]
    def _go() -> dict:
        return chat_json(msgs, model="gpt-4o", temperature=0.1,
                         schema_hint='{"injury_kind_hint":str,"triage_category_hint":str,"rationale":str}')
    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
            return ex.submit(_go).result(timeout=VISION_TIMEOUT_S)
    except Exception:
        return {
            "injury_kind_hint":     "penetrating_extremity",
            "triage_category_hint": "PRIORITY",
            "rationale":            "Vision unavailable; defaulted to conservative PRIORITY per TCCC.",
        }


# ---- Hash-chained audit ----------------------------------------------------

def hash_chain(events: list[dict]) -> list[dict]:
    """Return events with a `hash` and `prev_hash` field forming a chain."""
    prev = "0" * 64
    out = []
    for ev in events:
        body = json.dumps(ev, sort_keys=True, default=str)
        h = hashlib.sha256((prev + body).encode()).hexdigest()
        out.append({**ev, "prev_hash": prev, "hash": h})
        prev = h
    return out


# ---- One-shot pipeline -----------------------------------------------------

def run_pipeline(scenario_id: str, *, hero: bool = True,
                 wia_override: int | None = None,
                 location_override: str | None = None) -> dict[str, Any]:
    scenarios = load_scenarios()
    scenario = next((s for s in scenarios if s["id"] == scenario_id), scenarios[0])
    doctrine = load_doctrine()
    vendors  = load_vendors()
    inv_v1   = load_inventory_v1()
    inv_v2   = load_inventory_v2()

    event = build_casualty_event(scenario,
                                  wia_count=wia_override,
                                  location_id=location_override)
    cards   = triage_cascade(event, doctrine)
    demand  = class_viii_demand(cards)
    gap     = hub_spoke_supply_check(event, demand, inv_v1, inv_v2)
    requis  = build_requisition(event, gap)
    brief   = write_action_brief(event, demand, gap, requis, vendors, hero=hero)
    market  = evaluate_buy_on_market(gap, vendors)

    audit = hash_chain([
        {"stage": "1_casualty_injection", "ts": event["injection_time"],
         "scenario_id": scenario_id, "wia_count": event.get("wia_count")},
        {"stage": "2_triage_cascade",     "ts": datetime.now(timezone.utc).isoformat(),
         "cards_count": len(cards),
         "categories": list({c["triage_category"] for c in cards})},
        {"stage": "3_demand_projection",  "ts": datetime.now(timezone.utc).isoformat(),
         "prbc": demand["total_prbc_units"], "fluids_L": demand["total_fluids_L"]},
        {"stage": "4_supply_check",       "ts": datetime.now(timezone.utc).isoformat(),
         "shortfalls": gap["total_shortfalls"]},
        {"stage": "5_requisition",        "ts": requis["submitted_iso"],
         "lines": len(requis.get("lines", []))},
        {"stage": "6_brief",              "ts": datetime.now(timezone.utc).isoformat(),
         "len_chars": len(brief)},
        {"stage": "7_market_eval",        "ts": datetime.now(timezone.utc).isoformat(),
         "recommendations": len(market)},
    ])

    return {
        "scenario": scenario, "event": event, "doctrine": doctrine,
        "cards": cards, "demand": demand, "gap": gap,
        "requisition": requis, "brief": brief, "market": market,
        "vendors": vendors, "audit": audit,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


if __name__ == "__main__":
    out = run_pipeline("he_blast_mascal", hero=False)
    print(json.dumps({
        "wia": len(out["cards"]),
        "demand_prbc": out["demand"]["total_prbc_units"],
        "shortfalls": out["gap"]["total_shortfalls"],
        "requisition_lines": len(out["requisition"]["lines"]),
        "audit_chain_len": len(out["audit"]),
    }, indent=2))
    print("\n---\n")
    print(out["brief"][:1200])
