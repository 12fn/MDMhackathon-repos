"""CHAIN synthetic data generator.

Produces:
  data/suppliers.json        - 30 supply-chain nodes (suppliers, chokepoints, USMC end-items)
  data/edges.json            - weighted flow edges between nodes
  data/chokepoints.json      - 4 maritime chokepoints with current status
  data/disruption_events.csv - 60-day synthetic events feed
  data/cached_briefs.json    - 3 pre-computed hero scenario briefs

Seeded with random.Random(1776) for reproducibility.

Real-data swap recipe: see data/load_real.py for plug-in to:
  - Global Supply Chain Disruption & Resilience (Kaggle)
  - Global supply chain risk and logistics (Kaggle)
  - Global trade 2024-2026 dataset (Kaggle)
"""
from __future__ import annotations

import csv
import json
import random
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
REPO_ROOT = ROOT.parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


# ─────────────────────────────────────────────────────────────────────────────
# 30 named nodes — suppliers, chokepoints, USMC end-items
# ─────────────────────────────────────────────────────────────────────────────
SUPPLIERS: list[dict] = [
    # Tier-1 foreign / commercial suppliers (rare-earth, chips, optics)
    {"id": "TSMC",     "name": "TSMC Fab 18",                    "kind": "supplier",  "country": "Taiwan",        "category": "semiconductors",   "lat": 22.998, "lon": 120.293, "annual_value_musd": 4200, "criticality": 10},
    {"id": "ASML",     "name": "ASML Veldhoven",                 "kind": "supplier",  "country": "Netherlands",   "category": "lithography",      "lat": 51.418, "lon": 5.480,   "annual_value_musd": 980,  "criticality": 8},
    {"id": "SMIC",     "name": "Samsung Pyeongtaek",             "kind": "supplier",  "country": "South Korea",   "category": "semiconductors",   "lat": 37.013, "lon": 127.115, "annual_value_musd": 2100, "criticality": 7},
    {"id": "MAXAR",    "name": "Maxar Westminster",              "kind": "supplier",  "country": "USA (CO)",      "category": "satellite optics", "lat": 39.836, "lon": -105.038,"annual_value_musd": 320,  "criticality": 9},
    {"id": "RAREEARTH","name": "Lynas Mt Weld",                  "kind": "supplier",  "country": "Australia",     "category": "rare-earth oxides","lat": -28.85, "lon": 122.55,  "annual_value_musd": 410,  "criticality": 9},
    {"id": "MPMATERIAL","name": "MP Materials Mountain Pass",    "kind": "supplier",  "country": "USA (CA)",      "category": "rare-earth oxides","lat": 35.478, "lon": -115.532,"annual_value_musd": 290,  "criticality": 8},
    {"id": "BAOTOU",   "name": "Baotou Steel Rare-Earth",        "kind": "supplier",  "country": "China",         "category": "rare-earth magnets","lat": 40.652,"lon": 109.840, "annual_value_musd": 1850, "criticality": 10},
    {"id": "SHINETSU", "name": "Shin-Etsu Takefu",               "kind": "supplier",  "country": "Japan",         "category": "silicon wafers",   "lat": 35.901, "lon": 136.171, "annual_value_musd": 760,  "criticality": 8},
    {"id": "GLOBALWAF","name": "GlobalWafers Hsinchu",           "kind": "supplier",  "country": "Taiwan",        "category": "silicon wafers",   "lat": 24.776, "lon": 120.997, "annual_value_musd": 540,  "criticality": 7},

    # Tier-1 US prime / sub-assembly contractors (Marine end-item assemblers)
    {"id": "NORTHROP", "name": "Northrop Palmdale",              "kind": "supplier",  "country": "USA (CA)",      "category": "airframe sub-assy","lat": 34.629, "lon": -118.084,"annual_value_musd": 1480, "criticality": 9},
    {"id": "BAE",      "name": "BAE Systems York",               "kind": "supplier",  "country": "USA (PA)",      "category": "armored hulls",    "lat": 39.962, "lon": -76.728, "annual_value_musd": 920,  "criticality": 9},
    {"id": "OSHKOSH",  "name": "Oshkosh Defense",                "kind": "supplier",  "country": "USA (WI)",      "category": "tactical wheeled", "lat": 44.024, "lon": -88.541, "annual_value_musd": 1100, "criticality": 9},
    {"id": "GDLS",     "name": "GD Land Systems Lima",           "kind": "supplier",  "country": "USA (OH)",      "category": "armored hulls",    "lat": 40.748, "lon": -84.116, "annual_value_musd": 870,  "criticality": 8},
    {"id": "ROLLS",    "name": "Rolls-Royce Indianapolis",       "kind": "supplier",  "country": "USA (IN)",      "category": "turbine engines",  "lat": 39.766, "lon": -86.171, "annual_value_musd": 640,  "criticality": 8},
    {"id": "PWHITNEY", "name": "Pratt & Whitney East Hartford",  "kind": "supplier",  "country": "USA (CT)",      "category": "turbine engines",  "lat": 41.762, "lon": -72.642, "annual_value_musd": 1320, "criticality": 9},
    {"id": "RAYTHEON", "name": "Raytheon Andover",               "kind": "supplier",  "country": "USA (MA)",      "category": "missile seekers",  "lat": 42.658, "lon": -71.137, "annual_value_musd": 1840, "criticality": 9},
    {"id": "LMARTIN",  "name": "Lockheed Marietta",              "kind": "supplier",  "country": "USA (GA)",      "category": "airframe sub-assy","lat": 33.913, "lon": -84.515, "annual_value_musd": 2100, "criticality": 9},

    # Maritime chokepoints (treated as transit nodes — flow through)
    {"id": "MALACCA",  "name": "Strait of Malacca",              "kind": "chokepoint","country": "Malaysia/Sing", "category": "sea lane",         "lat": 2.500,  "lon": 101.500, "annual_value_musd": 5500, "criticality": 10},
    {"id": "SUEZ",     "name": "Suez Canal",                     "kind": "chokepoint","country": "Egypt",         "category": "sea lane",         "lat": 30.000, "lon": 32.580,  "annual_value_musd": 4900, "criticality": 10},
    {"id": "PANAMA",   "name": "Panama Canal",                   "kind": "chokepoint","country": "Panama",        "category": "sea lane",         "lat": 9.080,  "lon": -79.680, "annual_value_musd": 3200, "criticality": 9},
    {"id": "BABMANDEB","name": "Bab-el-Mandeb",                  "kind": "chokepoint","country": "Yemen/Djibouti","category": "sea lane",         "lat": 12.580, "lon": 43.330,  "annual_value_musd": 2800, "criticality": 9},
    {"id": "TWNSTRAIT","name": "Taiwan Strait",                  "kind": "chokepoint","country": "Taiwan/PRC",    "category": "sea lane",         "lat": 24.500, "lon": 119.500, "annual_value_musd": 6100, "criticality": 10},

    # USMC end-item programs (PEO Land Systems / PEO Aviation downstream consumers)
    {"id": "ACV",      "name": "ACV — Amphibious Combat Vehicle","kind": "end_item",  "country": "USMC",          "category": "PEO Land Systems", "lat": 38.881, "lon": -77.018, "annual_value_musd": 1450, "criticality": 10},
    {"id": "AMPV",     "name": "AMPV — Armored Multi-Purpose",   "kind": "end_item",  "country": "USMC",          "category": "PEO Land Systems", "lat": 38.881, "lon": -77.018, "annual_value_musd": 980,  "criticality": 9},
    {"id": "JLTV",     "name": "JLTV — Joint Light Tactical",    "kind": "end_item",  "country": "USMC",          "category": "PEO Land Systems", "lat": 38.881, "lon": -77.018, "annual_value_musd": 1640, "criticality": 9},
    {"id": "MV22",     "name": "MV-22B Osprey",                  "kind": "end_item",  "country": "USMC",          "category": "PEO Aviation",     "lat": 38.881, "lon": -77.018, "annual_value_musd": 2200, "criticality": 10},
    {"id": "M88A2",    "name": "M88A2 HERCULES Recovery",        "kind": "end_item",  "country": "USMC",          "category": "PEO Land Systems", "lat": 38.881, "lon": -77.018, "annual_value_musd": 410,  "criticality": 8},
    {"id": "F35B",     "name": "F-35B Lightning II",             "kind": "end_item",  "country": "USMC",          "category": "PEO Aviation",     "lat": 38.881, "lon": -77.018, "annual_value_musd": 4800, "criticality": 10},
    {"id": "HIMARS",   "name": "HIMARS / NMESIS",                "kind": "end_item",  "country": "USMC",          "category": "PEO Land Systems", "lat": 38.881, "lon": -77.018, "annual_value_musd": 880,  "criticality": 9},
    {"id": "CH53K",    "name": "CH-53K King Stallion",           "kind": "end_item",  "country": "USMC",          "category": "PEO Aviation",     "lat": 38.881, "lon": -77.018, "annual_value_musd": 2900, "criticality": 9},
]


# Weighted edges = annual flow in $M USD
EDGES: list[dict] = [
    # Rare-earth flow (mines -> magnet processor -> primes -> end-items)
    {"a": "BAOTOU",    "b": "MALACCA",  "mode": "sea",  "annual_value_musd": 1700},
    {"a": "RAREEARTH", "b": "MALACCA",  "mode": "sea",  "annual_value_musd": 380},
    {"a": "MPMATERIAL","b": "PANAMA",   "mode": "sea",  "annual_value_musd": 270},
    {"a": "MALACCA",   "b": "RAYTHEON", "mode": "sea",  "annual_value_musd": 950},
    {"a": "MALACCA",   "b": "LMARTIN",  "mode": "sea",  "annual_value_musd": 720},
    {"a": "PANAMA",    "b": "RAYTHEON", "mode": "sea",  "annual_value_musd": 240},

    # Semiconductor flow
    {"id": "tsmc-strait", "a": "TSMC",     "b": "TWNSTRAIT","mode": "sea",  "annual_value_musd": 3800},
    {"a": "GLOBALWAF", "b": "TWNSTRAIT","mode": "sea",  "annual_value_musd": 510},
    {"a": "SMIC",      "b": "MALACCA",  "mode": "sea",  "annual_value_musd": 1900},
    {"a": "TWNSTRAIT", "b": "MALACCA",  "mode": "sea",  "annual_value_musd": 4100},
    {"a": "ASML",      "b": "SUEZ",     "mode": "sea",  "annual_value_musd": 880},
    {"a": "SUEZ",      "b": "MALACCA",  "mode": "sea",  "annual_value_musd": 2400},
    {"a": "SUEZ",      "b": "RAYTHEON", "mode": "sea",  "annual_value_musd": 410},
    {"a": "SHINETSU",  "b": "MALACCA",  "mode": "sea",  "annual_value_musd": 720},

    # Bab-el-Mandeb feeds Suez
    {"a": "BABMANDEB", "b": "SUEZ",     "mode": "sea",  "annual_value_musd": 2700},

    # Sub-assembly to end-items
    {"a": "RAYTHEON",  "b": "F35B",     "mode": "road", "annual_value_musd": 980},
    {"a": "RAYTHEON",  "b": "HIMARS",   "mode": "road", "annual_value_musd": 540},
    {"a": "RAYTHEON",  "b": "MV22",     "mode": "road", "annual_value_musd": 220},
    {"a": "LMARTIN",   "b": "F35B",     "mode": "road", "annual_value_musd": 1900},
    {"a": "NORTHROP",  "b": "F35B",     "mode": "road", "annual_value_musd": 1400},
    {"a": "NORTHROP",  "b": "MV22",     "mode": "road", "annual_value_musd": 740},
    {"a": "BAE",       "b": "ACV",      "mode": "road", "annual_value_musd": 870},
    {"a": "BAE",       "b": "AMPV",     "mode": "road", "annual_value_musd": 540},
    {"a": "GDLS",      "b": "AMPV",     "mode": "road", "annual_value_musd": 410},
    {"a": "GDLS",      "b": "M88A2",    "mode": "road", "annual_value_musd": 380},
    {"a": "OSHKOSH",   "b": "JLTV",     "mode": "road", "annual_value_musd": 1500},
    {"a": "OSHKOSH",   "b": "HIMARS",   "mode": "road", "annual_value_musd": 290},
    {"a": "ROLLS",     "b": "MV22",     "mode": "road", "annual_value_musd": 480},
    {"a": "ROLLS",     "b": "CH53K",    "mode": "road", "annual_value_musd": 920},
    {"a": "PWHITNEY",  "b": "F35B",     "mode": "road", "annual_value_musd": 1300},
    {"a": "PWHITNEY",  "b": "CH53K",    "mode": "road", "annual_value_musd": 670},

    # Maxar optics & semiconductor through-flows to seekers / sensors
    {"a": "MAXAR",     "b": "RAYTHEON", "mode": "road", "annual_value_musd": 280},
    {"a": "MAXAR",     "b": "LMARTIN",  "mode": "road", "annual_value_musd": 190},
    {"a": "TSMC",      "b": "RAYTHEON", "mode": "sea",  "annual_value_musd": 410},
    {"a": "TSMC",      "b": "LMARTIN",  "mode": "sea",  "annual_value_musd": 380},
]


# Maritime chokepoints with current status
CHOKEPOINTS: list[dict] = [
    {"id": "MALACCA",  "name": "Strait of Malacca",   "lat": 2.500,  "lon": 101.500, "status": "ELEVATED",  "daily_transit_musd": 15068, "current_event": "Tropical depression 06W approaching; pilot delays"},
    {"id": "SUEZ",     "name": "Suez Canal",          "lat": 30.000, "lon": 32.580,  "status": "DEGRADED",  "daily_transit_musd": 13425, "current_event": "Houthi standoff in BAB-EL-MANDEB diverting 38% of inbound tonnage"},
    {"id": "PANAMA",   "name": "Panama Canal",        "lat": 9.080,  "lon": -79.680, "status": "DEGRADED",  "daily_transit_musd": 8767,  "current_event": "Gatun Lake drought — daily transits capped at 24"},
    {"id": "BABMANDEB","name": "Bab-el-Mandeb",       "lat": 12.580, "lon": 43.330,  "status": "CRITICAL",  "daily_transit_musd": 7671,  "current_event": "Houthi UAS / ASBM launches; 67% of liners rerouting"},
    {"id": "TWNSTRAIT","name": "Taiwan Strait",       "lat": 24.500, "lon": 119.500, "status": "WATCH",     "daily_transit_musd": 16712, "current_event": "PLAN exercise window 28-30 APR; J2 watching for live-fire NOTAM"},
]


# 60-day synthetic disruption events feed
EVENT_TYPES = [
    ("typhoon",       "TYPHOON BAVI-26C CPA <72h to {target}"),
    ("typhoon",       "TROPICAL STORM HAIKUI-26D — port closure {target}"),
    ("cyber",         "Ransomware on {target} ICS — production halted 36h"),
    ("cyber",         "Wiper malware on supplier-tier ERP at {target}"),
    ("export_ctrl",   "PRC export licensing freeze on neodymium-iron-boron magnets ({target})"),
    ("export_ctrl",   "EU Dual-Use Reg update — ASML EUV tooling licenses delayed ({target})"),
    ("labor",         "Work-stoppage at {target} — IBEW Local 2150 strike vote"),
    ("labor",         "Customs slowdown at {target} — 14-day backlog"),
    ("kinetic",       "PRC Coast Guard harassment of inbound tanker via {target}"),
    ("kinetic",       "Houthi ASBM launch toward Liberian-flagged hull transiting {target}"),
    ("kinetic",       "Drone strike on storage tanks adjacent to {target}"),
    ("infrastructure","Pier-7 STS crane catastrophic failure at {target}"),
    ("infrastructure","Drought-driven Gatun Lake transit cap tightened at {target}"),
    ("infrastructure","Submarine cable cut SE of {target} — comms via SATCOM failover"),
    ("regulatory",    "DCMA Tier-3 audit finding at {target} — 21-day shipment hold"),
    ("regulatory",    "Section 232 tariff bump on rare-earth imports through {target}"),
    ("financial",     "Tier-2 supplier insolvency — {target} sole-source for FN-MAG mounts"),
    ("financial",     "Force majeure declared by {target} on Q3 deliveries"),
]


def _rand_event(rng: random.Random, day: datetime, all_nodes: list[dict]) -> dict:
    kind, template = rng.choice(EVENT_TYPES)
    target = rng.choice(all_nodes)
    severity = rng.choice(["LOW", "MODERATE", "MODERATE", "HIGH", "HIGH", "CRITICAL"])
    impact_days = {
        "LOW": rng.randint(1, 3),
        "MODERATE": rng.randint(3, 10),
        "HIGH": rng.randint(10, 30),
        "CRITICAL": rng.randint(20, 60),
    }[severity]
    value_at_risk = int(target["annual_value_musd"] * impact_days / 365 * rng.uniform(0.6, 1.4))
    return {
        "date": day.strftime("%Y-%m-%d"),
        "event_type": kind,
        "target_id": target["id"],
        "target_name": target["name"],
        "headline": template.format(target=target["name"]),
        "severity": severity,
        "estimated_impact_days": impact_days,
        "value_at_risk_musd": value_at_risk,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Cached scenarios — pre-computed hero briefs (no LLM in demo path)
# ─────────────────────────────────────────────────────────────────────────────
SCENARIOS: list[dict] = [
    {
        "id": "taiwan_strait",
        "title": "Taiwan Strait closure (PLAN exercise → quarantine)",
        "primary_chokepoint": "TWNSTRAIT",
        "headline": "PLAN live-fire box closes Taiwan Strait for 14 days; TSMC export tonnage drops 92%.",
    },
    {
        "id": "suez_bab_compound",
        "title": "Suez + Bab-el-Mandeb compound disruption",
        "primary_chokepoint": "SUEZ",
        "headline": "Houthi escalation reroutes 67% of Asia-Europe-CONUS tonnage around Cape of Good Hope.",
    },
    {
        "id": "rareearth_export",
        "title": "PRC rare-earth export freeze",
        "primary_chokepoint": "BAOTOU",
        "headline": "Beijing suspends NdFeB magnet export licenses; Marine seekers and motors at single-source risk.",
    },
]


def _baseline_brief(scenario: dict, suppliers: list[dict], edges: list[dict],
                    chokepoints: list[dict]) -> str:
    """Deterministic brief used when pre-computation can't reach the LLM.

    Generates a real PARA 1-5-style risk brief from the synthetic data so the
    demo path never sees a spinner.
    """
    by_id = {n["id"]: n for n in suppliers}
    cp = next((c for c in chokepoints if c["id"] == scenario["primary_chokepoint"]), None)
    affected_nodes: set[str] = set()
    for e in edges:
        if e["a"] == scenario["primary_chokepoint"] or e["b"] == scenario["primary_chokepoint"]:
            affected_nodes.add(e["a"]); affected_nodes.add(e["b"])
    end_items = [by_id[i] for i in affected_nodes if i in by_id and by_id[i]["kind"] == "end_item"]
    # Walk one more hop to find downstream programs through prime contractors.
    primes = [i for i in affected_nodes if i in by_id and by_id[i]["kind"] == "supplier"]
    for e in edges:
        if e["a"] in primes:
            tgt = by_id.get(e["b"])
            if tgt and tgt["kind"] == "end_item" and tgt not in end_items:
                end_items.append(tgt)
    program_names = ", ".join(p["name"] for p in end_items[:6]) or "ACV, JLTV, MV-22, F-35B"
    return (
        f"# Critical-Component Risk Brief — {scenario['title']}\n"
        f"**Audience:** USMC PEO Land Systems / PEO Aviation\n"
        f"**Classification:** UNCLASSIFIED // FOR OFFICIAL USE ONLY\n\n"
        f"## BLUF\n"
        f"{scenario['headline']} Estimated 14-30 day delay to USMC procurement programs "
        f"with cumulative cost exposure in the low billions absent mitigation.\n\n"
        f"## Exposed Programs\n"
        f"- Affected Marine programs: {program_names}.\n"
        f"- Primary chokepoint: {cp['name'] if cp else scenario['primary_chokepoint']} "
        f"({cp['status'] if cp else 'STATUS UNKNOWN'}).\n"
        f"- Single-source dependencies on rare-earth magnet, EUV tooling, and silicon-wafer "
        f"flows traversing the affected node.\n\n"
        f"## Mitigation Playbook\n"
        f"1. **Immediate (0-72h):** Activate stockpile draw against DPAS-DX rated orders; "
        f"engage DLA Strategic Materials for NdFeB magnet stockpile release.\n"
        f"2. **Short-term (3-30d):** Re-route via secondary chokepoint (Cape of Good Hope add "
        f"+12d steaming); request CFIUS waiver for emergency MP Materials offtake expansion.\n"
        f"3. **Mid-term (30-90d):** Spin up alternate Tier-2 suppliers under the Defense Production "
        f"Act Title III authority; warm-start MP Materials Mountain Pass second magnet line.\n"
        f"4. **Long-term (90d+):** Codify second-source qualification on next ACV / AMPV / JLTV "
        f"competitive procurement cycle. Formalize standing letters of credit with Lynas Mt Weld "
        f"and JOGMEC offtake.\n\n"
        f"## Decision Required\n"
        f"PEO Land Systems and PEO Aviation review by 72h; recommend Title III invocation if "
        f"delay exposure exceeds 21 days at any chokepoint.\n"
    )


def _baseline_chat_json(scenario: dict, suppliers: list[dict], edges: list[dict]) -> dict:
    """Deterministic structured analysis used as a fallback."""
    by_id = {n["id"]: n for n in suppliers}
    affected: set[str] = set()
    for e in edges:
        if e["a"] == scenario["primary_chokepoint"] or e["b"] == scenario["primary_chokepoint"]:
            affected.add(e["a"]); affected.add(e["b"])
    primes = [i for i in affected if by_id.get(i, {}).get("kind") == "supplier"]
    for e in edges:
        if e["a"] in primes and by_id.get(e["b"], {}).get("kind") == "end_item":
            affected.add(e["b"])
    programs = [by_id[i]["name"] for i in affected if by_id.get(i, {}).get("kind") == "end_item"]
    subs = [by_id[i]["name"] for i in affected if by_id.get(i, {}).get("kind") == "supplier"]
    if scenario["id"] == "rareearth_export":
        substitutes = ["MP Materials (Mountain Pass, USA)", "Lynas Mt Weld (Australia)",
                       "Energy Fuels Wash. (USA)"]
    elif scenario["id"] == "suez_bab_compound":
        substitutes = ["Cape of Good Hope re-route", "Trans-Siberian rail (sanctions-bounded)",
                       "Air-freight surge for highest-priority FMS lots"]
    else:
        substitutes = ["Samsung Pyeongtaek (KOR)", "Intel Ocotillo (AZ)",
                       "GlobalFoundries Malta (NY) (legacy nodes only)"]
    return {
        "affected_marine_program": programs[:6],
        "substitute_supplier": substitutes,
        "lead_time_impact_days": {"taiwan_strait": 60, "suez_bab_compound": 28,
                                   "rareearth_export": 90}.get(scenario["id"], 30),
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


def _precompute_briefs(suppliers: list[dict], edges: list[dict],
                       chokepoints: list[dict]) -> dict:
    """Try the live LLM for hero briefs; fall back deterministically on any error."""
    out: dict[str, dict] = {}
    try:
        from shared.kamiwaza_client import chat, chat_json  # type: ignore
        live = True
    except Exception:
        live = False

    for scenario in SCENARIOS:
        baseline_struct = _baseline_chat_json(scenario, suppliers, edges)
        baseline_text = _baseline_brief(scenario, suppliers, edges, chokepoints)
        struct = baseline_struct
        text = baseline_text
        if live:
            try:
                # Step 1 — structured network analysis
                cp = next((c for c in chokepoints if c["id"] == scenario["primary_chokepoint"]), None)
                affected: set[str] = set()
                for e in edges:
                    if e["a"] == scenario["primary_chokepoint"] or e["b"] == scenario["primary_chokepoint"]:
                        affected.add(e["a"]); affected.add(e["b"])
                affected_brief = [
                    {"id": s["id"], "name": s["name"], "kind": s["kind"],
                     "country": s["country"], "category": s["category"],
                     "annual_value_musd": s["annual_value_musd"]}
                    for s in suppliers if s["id"] in affected
                ]
                json_msgs = [
                    {"role": "system",
                     "content": "You are a USMC LOGCOM critical-component sourcing analyst. "
                                "Given a disrupted node and the affected supply network, return JSON "
                                "with keys: affected_marine_program (list of program names), "
                                "substitute_supplier (list), lead_time_impact_days (int), "
                                "mitigation_actions (list of <=5 strings)."},
                    {"role": "user",
                     "content": f"Disruption scenario: {scenario['title']}\n"
                                f"Headline: {scenario['headline']}\n"
                                f"Primary chokepoint: {cp}\n"
                                f"Affected nodes:\n{json.dumps(affected_brief, indent=2)}"},
                ]
                struct = chat_json(  # type: ignore[assignment]
                    json_msgs,
                    schema_hint='{"affected_marine_program":[str],"substitute_supplier":[str],'
                                '"lead_time_impact_days":int,"mitigation_actions":[str]}',
                    temperature=0.2,
                )
                struct["primary_chokepoint"] = scenario["primary_chokepoint"]
                struct["scenario_id"] = scenario["id"]
                struct["_source"] = "llm"
            except Exception as e:
                print(f"[chain] structured-output LLM failed for {scenario['id']}: {e}",
                      file=sys.stderr)
                struct = baseline_struct

            try:
                # Step 2 — hero narrative brief (gpt-5.4 if available)
                hero_msgs = [
                    {"role": "system",
                     "content": "You are CHAIN, a USMC global-supply-chain disruption analyst writing a "
                                "Critical-Component Risk Brief for PEO Land Systems and PEO Aviation. "
                                "Compose a polished one-page brief with these EXACT markdown headers in order:\n"
                                "  # Critical-Component Risk Brief — <scenario title>\n"
                                "  **Audience:** USMC PEO Land Systems / PEO Aviation\n"
                                "  ## BLUF\n  ## Exposed Programs\n  ## Mitigation Playbook\n  ## Decision Required\n"
                                "Cite specific Marine programs (ACV, AMPV, JLTV, MV-22, F-35B, CH-53K, HIMARS) and "
                                "name specific component dependencies (rare-earth magnets, EUV optics, silicon wafers). "
                                "Keep total length under ~450 words. Classification line: UNCLASSIFIED // FOR OFFICIAL USE ONLY."},
                    {"role": "user",
                     "content": f"Scenario: {scenario['title']}\nHeadline: {scenario['headline']}\n\n"
                                f"Structured analysis (your input from step 1):\n{json.dumps(struct, indent=2)}\n\n"
                                "Compose the Critical-Component Risk Brief now."},
                ]
                hero = chat(hero_msgs, model="gpt-5.4", temperature=0.45)
                if hero and "BLUF" in hero:
                    text = hero
            except Exception as e:
                print(f"[chain] hero LLM failed for {scenario['id']}: {e}", file=sys.stderr)
                text = baseline_text

        out[scenario["id"]] = {
            "scenario": scenario,
            "structured": struct,
            "brief": text,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "source": struct.get("_source", "baseline"),
        }
    return out


def main() -> None:
    rng = random.Random(1776)
    (ROOT / "suppliers.json").write_text(json.dumps(SUPPLIERS, indent=2))
    (ROOT / "edges.json").write_text(json.dumps(EDGES, indent=2))
    (ROOT / "chokepoints.json").write_text(json.dumps(CHOKEPOINTS, indent=2))

    # Disruption events feed — 60 days, ~2 events/day weighted to the present
    events = []
    base_day = datetime(2026, 4, 27, tzinfo=timezone.utc)
    for d in range(60):
        day = base_day - timedelta(days=d)
        n_events = rng.choices([0, 1, 2, 3, 4], weights=[5, 18, 28, 22, 12])[0]
        for _ in range(n_events):
            events.append(_rand_event(rng, day, SUPPLIERS))
    events.sort(key=lambda e: e["date"], reverse=True)
    with (ROOT / "disruption_events.csv").open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(events[0].keys()))
        w.writeheader()
        w.writerows(events)

    # Pre-computed hero briefs (cache-first pattern)
    briefs = _precompute_briefs(SUPPLIERS, EDGES, CHOKEPOINTS)
    (ROOT / "cached_briefs.json").write_text(json.dumps(briefs, indent=2))

    print(f"[chain] wrote {len(SUPPLIERS)} suppliers, {len(EDGES)} edges, "
          f"{len(CHOKEPOINTS)} chokepoints, {len(events)} disruption events.")
    print(f"[chain] cached {len(briefs)} hero scenario briefs to cached_briefs.json.")
    print(f"[chain]  -> {ROOT}")


if __name__ == "__main__":
    main()
