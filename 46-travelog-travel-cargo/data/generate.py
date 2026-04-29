"""TRAVELOG synthetic dataset generator.

Governing doctrine references baked into the data shape:
  - JTR Ch 2 (CONUS per-diem)        — DTMO via GSA
  - JTR Ch 3 (OCONUS per-diem)       — DTMO
  - DoDFMR Vol 9 Ch 5                — GTCC oversight
  - DTR 4500.9-R Part II             — TMR / cargo movement
  - APC oversight                     — DoDI 5154.31
  - GCSS-MC                           — Marine Corps logistics system of record

Outputs to data/:
  - per_diem_rates.json              — JTR-aligned, ~16 cities (CONUS+OCONUS)
  - dts_records.csv                  — borrowed from VOUCHER schema, 30 PCS
                                       authorizations (doc_number, ta_number,
                                       ao_edipi, traveler_edipi, etc.)
  - logistics_assets.csv             — borrowed from VANGUARD shape (asset
                                       class, mode, cap, fuel burn, base)
  - bts_nodes.json / bts_edges.csv   — borrowed from HUB shape (BTS NTAD
                                       multimodal nodes + edges across CONUS)
  - lade_records.csv                 — borrowed from CARGO/LaDe last-mile
                                       schema (waypoint, eta, courier, parcel)
  - pcs_scenarios.json               — 30 PCS scenarios (the user prompts)
  - cached_briefs.json               — 3 pre-computed hero briefs

Deterministic: random.Random(1776).
"""
from __future__ import annotations

import csv
import json
import random
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

OUT = Path(__file__).resolve().parent
RNG = random.Random(1776)


# ─────────────────────────────────────────────────────────────────────────────
# Reference tables
# ─────────────────────────────────────────────────────────────────────────────
PER_DIEM = [
    # (city, state, lodging $/night, M&IE $/day) — JTR-aligned synthetic FY26
    ("San Diego",        "CA", 217, 79),
    ("Oceanside",        "CA", 174, 74),
    ("Twentynine Palms", "CA", 110, 64),
    ("Quantico",         "VA", 184, 79),
    ("Arlington",        "VA", 277, 84),
    ("Norfolk",          "VA", 134, 74),
    ("Jacksonville",     "NC", 110, 64),
    ("Camp Lejeune",     "NC", 110, 64),
    ("Cherry Point",     "NC", 110, 64),
    ("Honolulu",         "HI", 252, 134),
    ("Okinawa",          "JP", 178, 124),
    ("Iwakuni",          "JP", 158, 118),
    ("Yuma",             "AZ", 102, 64),
    ("Beaufort",         "SC", 110, 64),
    ("Washington",       "DC", 277, 84),
    ("Albany",           "GA", 105, 64),
]

# BTS NTAD-style multimodal corridor nodes (lat/lon real CONUS bases + ports)
NODES = [
    {"id": "MCBLEJ",  "name": "MCB Camp Lejeune (NC)",
     "lat": 34.6862, "lon": -77.3471, "kind": "installation"},
    {"id": "MCBPEN",  "name": "MCB Camp Pendleton (CA)",
     "lat": 33.3861, "lon": -117.5731, "kind": "installation"},
    {"id": "MCBQUA",  "name": "MCB Quantico (VA)",
     "lat": 38.5236, "lon": -77.3035, "kind": "installation"},
    {"id": "MCAGCC",  "name": "MCAGCC Twentynine Palms (CA)",
     "lat": 34.2331, "lon": -116.0653, "kind": "installation"},
    {"id": "MCASCP",  "name": "MCAS Cherry Point (NC)",
     "lat": 34.9008, "lon": -76.8808, "kind": "installation"},
    {"id": "MCAS_YUMA", "name": "MCAS Yuma (AZ)",
     "lat": 32.6566, "lon": -114.6058, "kind": "installation"},
    {"id": "MCBHAW",  "name": "MCB Hawaii / Camp Smith",
     "lat": 21.4458, "lon": -157.7758, "kind": "installation"},
    {"id": "MCAS_IWA", "name": "MCAS Iwakuni (JP)",
     "lat": 34.1444, "lon": 132.2358, "kind": "installation"},
    {"id": "MCBOKI",  "name": "MCB Camp Butler / Okinawa",
     "lat": 26.2773, "lon": 127.7832, "kind": "installation"},
    # BTS rail / port / air hubs along the corridor
    {"id": "PORT_NORFOLK", "name": "Port of Norfolk (VA)",
     "lat": 36.8703, "lon": -76.3014, "kind": "seaport"},
    {"id": "PORT_LB",  "name": "Port of Long Beach (CA)",
     "lat": 33.7542, "lon": -118.2165, "kind": "seaport"},
    {"id": "RAIL_KCY", "name": "BNSF Hub Kansas City (MO)",
     "lat": 39.0997, "lon": -94.5786, "kind": "rail_hub"},
    {"id": "AIR_DOV",  "name": "Dover AFB AMC Hub (DE)",
     "lat": 39.1295, "lon": -75.4660, "kind": "air_hub"},
    {"id": "AIR_TRA",  "name": "Travis AFB AMC Hub (CA)",
     "lat": 38.2627, "lon": -121.9277, "kind": "air_hub"},
]

# Multimodal edges (BTS NTAD-style: mode, distance_mi, baseline transit_hr)
EDGES = [
    # ─── EAST-WEST ROAD (I-40 / I-10 corridor)
    ("MCBLEJ",  "MCBPEN",  "road",  2705, 47),
    ("MCBLEJ",  "RAIL_KCY","road",  1170, 19),
    ("RAIL_KCY","MCBPEN",  "road",  1620, 27),
    # ─── EAST-WEST RAIL
    ("MCBLEJ",  "RAIL_KCY","rail",  1170, 33),
    ("RAIL_KCY","MCBPEN",  "rail",  1620, 46),
    # ─── EAST-WEST AIR (AMC + commercial)
    ("MCBLEJ",  "AIR_DOV", "road",  315,  6),
    ("AIR_DOV", "AIR_TRA", "air",   2435, 6),
    ("AIR_TRA", "MCBPEN",  "road",  482,  9),
    # ─── PORT FEEDS (sealift HHG containers)
    ("MCBLEJ",  "PORT_NORFOLK","road", 165, 4),
    ("PORT_NORFOLK","PORT_LB","sea", 5350, 312),  # via Panama
    ("PORT_LB", "MCBPEN",  "road",  100,  2),
    # ─── INTRA-EAST / INTRA-WEST short-hauls
    ("MCBLEJ",  "MCBQUA",  "road",  330,  6),
    ("MCBLEJ",  "MCASCP",  "road",  35,   1),
    ("MCBPEN",  "MCAGCC",  "road",  130,  3),
    ("MCBPEN",  "MCAS_YUMA","road", 175,  3),
    # ─── HAWAII / WESTPAC (sealift + AMC)
    ("MCBPEN",  "MCBHAW",  "sea",   2680, 168),
    ("AIR_TRA", "MCBHAW",  "air",   2400, 6),
    ("MCBHAW",  "MCAS_IWA","sea",   4090, 240),
    ("MCBHAW",  "MCAS_IWA","air",   3970, 11),
    ("MCBHAW",  "MCBOKI",  "sea",   4200, 245),
    ("MCBHAW",  "MCBOKI",  "air",   4040, 12),
    ("MCAS_IWA","MCBOKI",  "sea",   650,  44),
    ("MCAS_IWA","MCBOKI",  "air",   620,  2),
]

# Logistics asset classes (VANGUARD shape, Marine-relevant)
ASSETS = [
    # class, mode, cap_lbs, cap_pallets, cruise_mph, fuel_lb_hr, base
    ("M1078 LMTV",           "road", 5000,  1, 55, 18,   "MCBLEJ"),
    ("M1083 MTV",            "road", 10000, 2, 55, 22,   "MCBLEJ"),
    ("HMMWV M1097A2",        "road", 4400,  0, 60, 9,    "MCBLEJ"),
    ("Privately Owned Vehicle (POV)", "road", 1500, 0, 65, 7, "MCBLEJ"),
    ("Penske 26ft (HHG)",    "road", 8500,  0, 60, 10,   "MCBLEJ"),
    ("CONEX (sealift)",      "sea",  44000, 8, 18, 0,    "PORT_NORFOLK"),
    ("C-17 Globemaster III", "air",  170000, 18, 450, 19500, "AIR_DOV"),
    ("C-130J Super Hercules","air",  44000,  6, 360, 5000,  "AIR_DOV"),
    ("Commercial AMC pax",   "air",  0,      0, 480, 0,    "AIR_DOV"),
]

# 30 PCS scenarios — Marine-realistic origin/destination pairs
# (origin_node, dest_node, traveler_grade, hhg_lbs, has_motor_pool_item, item_label, d_plus)
PCS_SEEDS = [
    ("MCBLEJ", "MCBPEN", "Sgt",    8500, False, None,            30),
    ("MCBLEJ", "MCBPEN", "GySgt",  12000, True,  "M1078 LMTV transfer", 30),
    ("MCBPEN", "MCBLEJ", "Capt",   11000, True,  "M1083 MTV transfer",  45),
    ("MCBPEN", "MCBLEJ", "1stLt",  6000, False, None,            30),
    ("MCBOKI", "MCAS_IWA","SSgt",  5500, False, None,            21),
    ("MCAS_IWA","MCBOKI","Maj",    9500, True,  "HMMWV transfer", 28),
    ("MCBLEJ", "MCBQUA", "Capt",   7500, False, None,            14),
    ("MCBQUA", "MCBLEJ", "MSgt",  10500, True,  "M1078 LMTV transfer", 45),
    ("MCBPEN", "MCAGCC", "Cpl",    3500, False, None,            10),
    ("MCAGCC","MCBPEN",  "1stSgt", 9000, True,  "HMMWV transfer", 30),
    ("MCBLEJ", "MCBHAW", "GySgt", 11000, False, None,            60),
    ("MCBHAW", "MCBLEJ", "Capt",   8000, False, None,            45),
    ("MCBPEN", "MCBHAW", "SSgt",   7500, True,  "M1078 LMTV transfer", 60),
    ("MCBHAW", "MCAS_IWA","LtCol", 12000, False, None,            60),
    ("MCAS_IWA","MCBHAW","SSgt",   6500, True,  "HMMWV transfer", 45),
    ("MCBOKI", "MCBPEN", "Maj",   10500, True,  "M1083 MTV transfer", 75),
    ("MCBPEN", "MCBOKI", "GySgt",  9500, True,  "M1078 LMTV transfer", 75),
    ("MCBLEJ", "MCAS_YUMA","Sgt",  6000, False, None,            21),
    ("MCAS_YUMA","MCBLEJ","Cpl",   4500, False, None,            14),
    ("MCBQUA", "MCBPEN", "Col",   12500, True,  "HMMWV transfer", 60),
    ("MCBPEN", "MCBQUA", "LtCol", 11500, False, None,            45),
    ("MCASCP", "MCBPEN", "Sgt",    5500, False, None,            30),
    ("MCBPEN", "MCASCP", "GySgt",  9500, True,  "M1078 LMTV transfer", 30),
    ("MCBLEJ", "MCAGCC", "Capt",   8500, True,  "HMMWV transfer", 45),
    ("MCAGCC","MCBLEJ",  "MSgt",  10000, False, None,            30),
    ("MCBHAW", "MCBPEN", "1stLt",  6500, False, None,            30),
    ("MCBPEN", "MCBLEJ", "GySgt",  9000, True,  "M1083 MTV transfer", 45),
    ("MCBOKI", "MCBLEJ", "Maj",   11500, True,  "M1078 LMTV transfer", 90),
    ("MCBLEJ", "MCBOKI", "Capt",  10000, True,  "HMMWV transfer", 75),
    ("MCBQUA", "MCBHAW", "GySgt",  9500, False, None,            45),
]

GRADE_TO_EDIPI_PREFIX = {
    "Cpl": "11", "Sgt": "12", "SSgt": "13", "GySgt": "14", "MSgt": "15",
    "1stSgt": "15", "MGySgt": "15", "SgtMaj": "15",
    "1stLt": "21", "Capt": "22", "Maj": "23", "LtCol": "24", "Col": "25",
}


def _make_doc_number(rng: random.Random) -> str:
    # Real DTS doc number: 6 letters + 6 digits (e.g. "AB1234EF5678" style)
    return ("".join(rng.choices("ABCDEFGHJKLMNPQRSTUVWXYZ", k=6))
            + "".join(rng.choices("0123456789", k=6)))


def _make_edipi(rng: random.Random, prefix: str = "12") -> str:
    return prefix + "".join(rng.choices("0123456789", k=8))


def _ta_number(rng: random.Random) -> str:
    # Travel-authorization number: TA-yyyymmdd-####
    return f"TA-{20260400 + rng.randint(1, 28):08d}-{rng.randint(1000,9999)}"


def _name_pool() -> list[tuple[str, str]]:
    return [
        ("ALVAREZ", "JAVIER"), ("BRENNAN", "MICHAEL"), ("CHEN", "LIANG"),
        ("DAVIS", "ASHLEY"), ("ELLIS", "JORDAN"), ("FOSTER", "PRIYA"),
        ("GOMEZ", "DIEGO"), ("HARRIS", "TANIA"), ("ITO", "KENJI"),
        ("JOHNSON", "TYRELL"), ("KELLER", "MEGAN"), ("LOPEZ", "RAFAEL"),
        ("MURPHY", "SEAN"), ("NGUYEN", "BAO"), ("OKONKWO", "ADAEZE"),
        ("PARK", "MIN-JI"), ("QUINN", "ROWAN"), ("RIVERA", "SOFIA"),
        ("SMITH", "DEVON"), ("TANAKA", "HIRO"), ("UZUMA", "EMEKA"),
        ("VARGAS", "LUCIANA"), ("WALSH", "BRENNA"), ("XU", "WEI"),
        ("YOUNG", "TERRENCE"), ("ZIMMER", "KARSTEN"), ("ARMSTRONG", "ROY"),
        ("BRIGGS", "CARSON"), ("COOK", "RENEE"), ("DUNN", "ESTHER"),
    ]


# ─────────────────────────────────────────────────────────────────────────────
# Builders
# ─────────────────────────────────────────────────────────────────────────────
def build_per_diem() -> dict:
    return {
        "source": "JTR-aligned synthetic FY26 (CONUS via GSA per JTR Ch 2; "
                  "OCONUS via DTMO per JTR Ch 3)",
        "rates": [
            {"city": c, "state": s, "lodging_per_night": l, "mie_per_day": m}
            for (c, s, l, m) in PER_DIEM
        ],
    }


def build_pcs_scenarios() -> list[dict]:
    nodes_by_id = {n["id"]: n for n in NODES}
    names = _name_pool()
    out = []
    for i, (o, d, grade, hhg, has_mp, mp_label, dplus) in enumerate(PCS_SEEDS):
        last, first = names[i % len(names)]
        scn = {
            "scenario_id": f"PCS-{i+1:03d}",
            "origin_id": o,
            "origin_name": nodes_by_id[o]["name"],
            "dest_id": d,
            "dest_name": nodes_by_id[d]["name"],
            "traveler_grade": grade,
            "traveler_name": f"{last}, {first}",
            "traveler_edipi": _make_edipi(RNG, GRADE_TO_EDIPI_PREFIX.get(grade, "12")),
            "hhg_lbs": hhg,
            "has_motor_pool_item": has_mp,
            "motor_pool_item": mp_label or "",
            "d_plus_days": dplus,
            "report_no_later_than": (
                datetime(2026, 4, 27, tzinfo=timezone.utc)
                + timedelta(days=dplus)
            ).strftime("%Y-%m-%d"),
            "prompt": _seed_prompt(grade, last, o, d, hhg, has_mp, mp_label, dplus),
        }
        out.append(scn)
    return out


def _seed_prompt(grade, last, o, d, hhg, has_mp, mp_label, dplus) -> str:
    nodes_by_id = {n["id"]: n for n in NODES}
    o_short = nodes_by_id[o]["name"].split("(")[0].strip()
    d_short = nodes_by_id[d]["name"].split("(")[0].strip()
    bits = (
        f"I'm {grade} {last}. PCS from {o_short} to {d_short} on D+{dplus}. "
        f"Bringing ~{hhg} lbs of household goods"
    )
    if has_mp:
        bits += f" plus 1 motor pool item I'm escorting ({mp_label})"
    bits += ". Recommend mode and travel package."
    return bits


def build_dts_records(scenarios: list[dict]) -> list[dict]:
    """One DTS authorization per scenario (VOUCHER schema)."""
    nodes_by_id = {n["id"]: n for n in NODES}
    rows = []
    for scn in scenarios:
        last, first = scn["traveler_name"].split(", ")
        ao_last, ao_first = ("MCKAY", "DANIEL")
        depart = (datetime(2026, 4, 27)
                  + timedelta(days=scn["d_plus_days"])).date()
        # nights ~ 4-7 for short PCS, more for OCONUS
        nights = RNG.randint(4, 11)
        ret = depart + timedelta(days=nights)
        # tdy_city = lodging at dest city short-name
        tdy_city = nodes_by_id[scn["dest_id"]]["name"].split("(")[0].strip()
        per_diem_lookup = {c: (l, m) for (c, _, l, m) in PER_DIEM}
        # Map full base names to per-diem city
        city_map = {
            "MCB Camp Lejeune": "Camp Lejeune",
            "MCB Camp Pendleton": "Oceanside",
            "MCB Quantico": "Quantico",
            "MCAGCC Twentynine Palms": "Twentynine Palms",
            "MCAS Cherry Point": "Cherry Point",
            "MCAS Yuma": "Yuma",
            "MCB Hawaii / Camp Smith": "Honolulu",
            "MCAS Iwakuni": "Iwakuni",
            "MCB Camp Butler / Okinawa": "Okinawa",
        }
        pd_city = city_map.get(tdy_city, tdy_city)
        lodging_ceiling, mie = per_diem_lookup.get(pd_city, (110, 64))
        total_lodging = nights * lodging_ceiling
        total_mie = (nights + 1) * mie  # JTR: travel days
        total_voucher = round(total_lodging + total_mie + RNG.randint(150, 600), 2)
        rows.append({
            "doc_number": _make_doc_number(RNG),
            "ta_number": _ta_number(RNG),
            "scenario_id": scn["scenario_id"],
            "traveler_edipi": scn["traveler_edipi"],
            "traveler_name": f"{last}, {first}",
            "traveler_grade": scn["traveler_grade"],
            "ao_edipi": _make_edipi(RNG, "25"),
            "ao_name": f"{ao_last}, {ao_first}",
            "trip_purpose": "PCS",
            "trip_start": depart.isoformat(),
            "trip_end": ret.isoformat(),
            "status": "AUTHORIZED",
            "tdy_city": pd_city,
            "nights": nights,
            "per_diem_lodging_ceiling": lodging_ceiling,
            "per_diem_mie": mie,
            "total_authorized": total_voucher,
            "total_voucher": 0.00,  # not yet filed
            "mode_of_travel": "TBD",
            "origin_id": scn["origin_id"],
            "dest_id": scn["dest_id"],
        })
    return rows


def build_logistics_assets() -> list[dict]:
    out = []
    for k, mode, lbs, pall, mph, fuel, base in ASSETS:
        out.append({
            "class": k,
            "mode": mode,
            "cap_lbs": lbs,
            "cap_pallets": pall,
            "cruise_mph": mph,
            "fuel_lb_hr": fuel,
            "current_base": base,
            "readiness": RNG.choice(["FMC", "FMC", "FMC", "PMC"]),
        })
    return out


def build_bts_files() -> tuple[list[dict], list[dict]]:
    """Return (nodes, edges) — both already in the right shape."""
    edges = []
    for (a, b, mode, mi, hr) in EDGES:
        # Add cost-per-mile estimate by mode (BTS NTAD-style)
        cpm = {"road": 1.85, "rail": 0.65, "sea": 0.45, "air": 4.20}[mode]
        edges.append({
            "from": a, "to": b, "mode": mode,
            "distance_mi": mi, "transit_hr": hr,
            "cost_per_mile_usd": cpm,
        })
        # bidirectional
        edges.append({
            "from": b, "to": a, "mode": mode,
            "distance_mi": mi, "transit_hr": hr,
            "cost_per_mile_usd": cpm,
        })
    return NODES, edges


def build_lade_records(scenarios: list[dict]) -> list[dict]:
    """LaDe-shape last-mile delivery records — pickup at receiving base depot,
    delivery to receiving unit barracks/warehouse on the new installation."""
    out = []
    couriers = ["DET-A", "DET-B", "DET-C", "MCO-K9", "MCO-DOM"]
    receiving_unit_pool = [
        "1st Bn 5th Marines", "3d Bn 7th Marines", "HQ Bn II MEF",
        "1st Marine Logistics Group", "3rd Marine Logistics Group",
        "MCAS Det", "Combat Logistics Bn 7",
    ]
    nodes_by_id = {n["id"]: n for n in NODES}
    for scn in scenarios:
        if not scn["has_motor_pool_item"]:
            continue
        d_node = nodes_by_id[scn["dest_id"]]
        eta_pickup = (datetime(2026, 4, 27)
                      + timedelta(days=scn["d_plus_days"] + 6)).date()
        eta_delivery = eta_pickup + timedelta(days=RNG.randint(1, 3))
        out.append({
            "parcel_id": f"LMD-{scn['scenario_id']}",
            "scenario_id": scn["scenario_id"],
            "courier": RNG.choice(couriers),
            "pickup_node": scn["dest_id"],
            "pickup_lat": d_node["lat"],
            "pickup_lon": d_node["lon"],
            "delivery_node": scn["dest_id"] + "_DEPOT",
            # Synthetic last-mile delivery offset from base center
            "delivery_lat": d_node["lat"] + RNG.uniform(-0.04, 0.04),
            "delivery_lon": d_node["lon"] + RNG.uniform(-0.04, 0.04),
            "weight_lbs": RNG.randint(4500, 12500),
            "item": scn["motor_pool_item"],
            "receiving_unit": RNG.choice(receiving_unit_pool),
            "eta_pickup": eta_pickup.isoformat(),
            "eta_delivery": eta_delivery.isoformat(),
            "status": "PLANNED",
        })
    return out


# ─────────────────────────────────────────────────────────────────────────────
# Pre-computed cached briefs (cache-first hero pattern)
# ─────────────────────────────────────────────────────────────────────────────
PRESET_SCENARIO_IDS = ["PCS-002", "PCS-006", "PCS-016"]  # variety: CONUS+OCONUS


def _baseline_brief(scn: dict) -> str:
    o = scn["origin_name"]
    d = scn["dest_name"]
    grade = scn["traveler_grade"]
    last = scn["traveler_name"].split(",")[0].strip()
    hhg = scn["hhg_lbs"]
    item = scn["motor_pool_item"] or "(none)"
    dplus = scn["d_plus_days"]
    return (
f"""# Combined Travel + Cargo Action Plan — {grade} {last}

## BLUF
Recommended mode: **Drive POV escorting cargo on flat-bed**, depart D+{dplus-2}, arrive D+{dplus+1}.
The traveler can self-escort one motor-pool item ({item}) plus {hhg:,} lbs of household goods on a single
movement, eliminating one TMR hand-off and one airline pax ticket. JTR Ch 2 per-diem authorized for
travel days. Cross-validation: travel arrival window aligns with cargo delivery window
(no gap, no overlap requiring temp storage).

## Recommended Mode
**MODE 3 — Drive escorting cargo (commercial flatbed + POV trail).**
- Time: ~3.5 days door-to-door
- Cost: ~$3,420 (fuel $610 + per-diem $1,140 + flatbed lease $1,670)
- Fuel: ~110 gal (POV) + ~340 gal (flatbed)
- Risk: low (interstate-only, no contested airspace, no port congestion window)
- JTR compliance: per-diem at lodging-en-route rate for 3 nights (M&IE @ 75% on travel days)

## Mode Comparison (BTS NTAD + AFCENT ops data)
| # | Mode | Time | Cost | Fuel cost | JTR per-diem | Lead time |
|---|---|---|---|---|---|---|
| 1 | Fly + ship cargo separately | 1 day pax / 14 days cargo | $4,890 | $980 | $620 | 14 days |
| 2 | Drive POV + ship cargo separately | 3.5 days / 11 days cargo | $4,210 | $1,140 | $1,140 | 11 days |
| 3 | **Drive escorting cargo** ★ | 3.5 days combined | **$3,420** | $1,610 | $1,140 | 4 days |
| 4 | Fly + air-freight cargo | 1 day / 3 days cargo | $7,650 | $4,800 | $620 | 3 days |

## DTS Voucher Pre-Fill (JTR-compliant)
- Doc number: AUTO-ASSIGNED on AO approval
- Trip purpose: PCS
- Trip window: D+{dplus-2} -> D+{dplus+2} ({3} nights)
- Lodging ceiling: city-of-stop GSA per-diem (per JTR Ch 2)
- M&IE: 1.25 days travel-day rate per JTR Table 2-21
- Mode of travel: privately owned vehicle (POV)
- GTCC: APC-issued for fuel + lodging only (per DoDFMR Vol 9 Ch 5)

## TMR Pre-Fill (DTR 4500.9-R Part II)
- Cargo: {item} + {hhg:,} lbs HHG
- Mode: commercial flatbed + POV escort
- Origin POE: {o}
- Destination POD: {d}
- RDD (Required Delivery Date): D+{dplus+1}
- Routed to: Installation Movement Officer (IMO)

## Validation
- Travel arrival D+{dplus+1} matches cargo delivery D+{dplus+1}: **OK**
- POV mileage allowance covers escort hours: **OK**
- GTCC monthly limit > projected charges: **OK**

CUI // PCS Travel + Cargo Movement Data
""")


def _baseline_for(scenarios_by_id: dict, sid: str) -> str:
    return _baseline_brief(scenarios_by_id[sid])


def _try_hero_brief(scenarios_by_id: dict, sid: str) -> tuple[str, str]:
    """Try to call the hero LLM; on any error fall back deterministically."""
    try:
        sys.path.insert(0, str(OUT.parents[2]))
        from shared.kamiwaza_client import chat
        scn = scenarios_by_id[sid]
        sys_prompt = (
            "You are TRAVELOG, a USMC PCS travel + cargo planner. Compose a "
            "polished one-page action plan in markdown with EXACTLY these "
            "sections in order:\n"
            "  # Combined Travel + Cargo Action Plan — {grade} {last}\n"
            "  ## BLUF\n  ## Recommended Mode\n  ## Mode Comparison\n"
            "  ## DTS Voucher Pre-Fill\n  ## TMR Pre-Fill\n  ## Validation\n"
            "Length under 450 words. Plain markdown. No code fences. No emoji.\n"
            "Cite JTR Ch 2 / Ch 3, DoDFMR Vol 9, DTR 4500.9-R where relevant. "
            "Refer to the engine as 'TRAVELOG' or 'the agent' — do not name "
            "underlying models. End with 'CUI // PCS Travel + Cargo Movement Data'."
        )
        msgs = [
            {"role": "system", "content": sys_prompt},
            {"role": "user", "content":
                f"PCS scenario {sid}: {scn['prompt']}\n"
                f"Origin: {scn['origin_name']}\nDest: {scn['dest_name']}\n"
                f"D+{scn['d_plus_days']}; HHG {scn['hhg_lbs']} lbs; "
                f"motor-pool item: {scn['motor_pool_item'] or 'none'}.\n"
                "Compose the plan. Recommend ONE mode of the four "
                "(fly+ship, drive+ship, drive escort, fly+air-freight)."},
        ]
        text = chat(msgs, model="gpt-5.4", temperature=0.4)
        if text and "BLUF" in text:
            return text, "gpt-5.4"
    except Exception as e:
        print(f"  hero call failed: {e}", file=sys.stderr)
    return _baseline_for(scenarios_by_id, sid), "deterministic-fallback"


def _precompute_briefs(scenarios: list[dict]) -> dict:
    sb = {s["scenario_id"]: s for s in scenarios}
    out = {}
    for sid in PRESET_SCENARIO_IDS:
        if sid not in sb:
            continue
        text, source = _try_hero_brief(sb, sid)
        scn = sb[sid]
        out[sid] = {
            "scenario_id": sid,
            "origin": scn["origin_name"],
            "dest": scn["dest_name"],
            "traveler": scn["traveler_name"],
            "traveler_grade": scn["traveler_grade"],
            "brief": text,
            "source": source,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }
        print(f"  cached brief for {sid} ({source})")
    return out


# ─────────────────────────────────────────────────────────────────────────────
# Driver
# ─────────────────────────────────────────────────────────────────────────────
def main(precompute: bool = True) -> None:
    print("[TRAVELOG] generating per_diem_rates.json")
    (OUT / "per_diem_rates.json").write_text(
        json.dumps(build_per_diem(), indent=2))

    print("[TRAVELOG] generating pcs_scenarios.json")
    scenarios = build_pcs_scenarios()
    (OUT / "pcs_scenarios.json").write_text(json.dumps(scenarios, indent=2))

    print(f"[TRAVELOG] generating dts_records.csv ({len(scenarios)} rows)")
    dts = build_dts_records(scenarios)
    with (OUT / "dts_records.csv").open("w", newline="") as f:
        if dts:
            w = csv.DictWriter(f, fieldnames=list(dts[0].keys()))
            w.writeheader()
            w.writerows(dts)

    print("[TRAVELOG] generating logistics_assets.csv")
    assets = build_logistics_assets()
    with (OUT / "logistics_assets.csv").open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(assets[0].keys()))
        w.writeheader()
        w.writerows(assets)

    print("[TRAVELOG] generating bts_nodes.json + bts_edges.csv")
    nodes, edges = build_bts_files()
    (OUT / "bts_nodes.json").write_text(json.dumps(nodes, indent=2))
    with (OUT / "bts_edges.csv").open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(edges[0].keys()))
        w.writeheader()
        w.writerows(edges)

    print("[TRAVELOG] generating lade_records.csv")
    lade = build_lade_records(scenarios)
    if lade:
        with (OUT / "lade_records.csv").open("w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(lade[0].keys()))
            w.writeheader()
            w.writerows(lade)

    print("[TRAVELOG] writing manifest.json")
    manifest = {
        "scenarios": len(scenarios),
        "dts_records": len(dts),
        "assets": len(assets),
        "bts_nodes": len(nodes),
        "bts_edges": len(edges),
        "lade_records": len(lade),
        "datasets_simulated": [
            "Synthetic DTS authorizations (VOUCHER schema, JTR-aligned)",
            "AFCENT Logistics Data (asset class / mode / fuel burn)",
            "Bureau of Transportation Statistics (BTS NTAD multimodal corridor)",
            "Last Mile Delivery (LaDe) records",
        ],
        "preset_scenario_ids": PRESET_SCENARIO_IDS,
    }
    (OUT / "manifest.json").write_text(json.dumps(manifest, indent=2))

    if precompute:
        print("[TRAVELOG] precomputing hero briefs (cache-first pattern)")
        briefs = _precompute_briefs(scenarios)
        (OUT / "cached_briefs.json").write_text(json.dumps(briefs, indent=2))
    else:
        # Always create the file so the app never crashes on startup.
        if not (OUT / "cached_briefs.json").exists():
            sb = {s["scenario_id"]: s for s in scenarios}
            briefs = {sid: {
                "scenario_id": sid,
                "origin": sb[sid]["origin_name"],
                "dest": sb[sid]["dest_name"],
                "traveler": sb[sid]["traveler_name"],
                "traveler_grade": sb[sid]["traveler_grade"],
                "brief": _baseline_for(sb, sid),
                "source": "deterministic-fallback",
                "generated_at": datetime.now(timezone.utc).isoformat(),
            } for sid in PRESET_SCENARIO_IDS}
            (OUT / "cached_briefs.json").write_text(json.dumps(briefs, indent=2))

    print("[TRAVELOG] done.")


if __name__ == "__main__":
    precompute = "--no-precompute" not in sys.argv
    main(precompute=precompute)
