"""Synthetic CENTCOM logistics dataset generator for VANGUARD.

Builds a plausible-but-fake stand-in for the real AFCENT TMR archive so the
demo is reproducible without sensitive data:

  - bases.csv      — 50 CENTCOM-area nodes (air / sea / land / joint) with
                     lat/lon, country, and theater
  - assets.csv     — 200 transport assets (C-17, C-130J, KC-46, C-5M, MV-22B,
                     M1083 / M1120 truck convoys, T-AKE / MV / CSS sealift)
                     with pallet capacity, cruise speed, and fuel burn
  - graph.json     — typed adjacency list of plausible great-circle legs;
                     edges are tagged by mode (`air` / `sea` / `road`)

Reproducible: random.Random(1776).

Real-AFCENT swap pointer
------------------------
To plug in real data, replace the three artifacts above with feeds from the
AFCENT Logistics Data archive (Air / Land / Sea):

  - `bases.csv`   ← AFCENT base + port roster (must keep columns:
                    code, name, country, lat, lon, type, theater)
  - `assets.csv`  ← live AMC TACC / USTRANSCOM IGC / USMC DTCI rosters
                    (must keep: asset_id, class, mode, cap_pallets,
                    cruise_kn, fuel_lb_hr, current_base, readiness)
  - `graph.json`  ← JOPES-approved leg list rebuilt from those feeds, or
                    re-run `build_graph()` against the new bases

The four agent tools in `src/tools.py` read these files only via the
documented column names, so swapping data does not require code changes.
"""
from __future__ import annotations

import json
import math
import random
import sys
from pathlib import Path

# Allow `from shared.synth import ...` when run from app dir
ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from shared.synth import seeded, write_csv, write_json  # noqa: E402


# ---------------------------------------------------------------------------
# Fixed inventory of CENTCOM-relevant nodes (real-world plausible coords).
# ---------------------------------------------------------------------------

BASES_RAW: list[tuple[str, str, str, float, float, str]] = [
    # code, name, country, lat, lon, type (air/sea/land/joint)
    ("ARIFJAN", "Camp Arifjan",         "Kuwait",        29.043,  47.910, "joint"),
    ("ALIASAL", "Ali Al Salem AB",      "Kuwait",        29.347,  47.520, "air"),
    ("ALUDEID", "Al Udeid AB",          "Qatar",         25.117,  51.315, "air"),
    ("ALDHAFR", "Al Dhafra AB",         "UAE",           24.248,  54.547, "air"),
    ("FUJAIRH", "Port of Fujairah",     "UAE",           25.142,  56.346, "sea"),
    ("JEBELALI","Port Jebel Ali",       "UAE",           25.012,  55.062, "sea"),
    ("MUSCAT",  "Muscat Intl",          "Oman",          23.593,  58.284, "air"),
    ("DUQM",    "Port of Duqm",         "Oman",          19.660,  57.700, "sea"),
    ("MASIRAH", "Masirah Island AB",    "Oman",          20.675,  58.890, "air"),
    ("THUMRT",  "Thumrait AB",          "Oman",          17.666,  54.025, "air"),
    ("ESEEB",   "Es-Sayd / Seeb",       "Oman",          23.589,  58.284, "joint"),
    ("BAGRAM",  "Bagram (legacy)",      "Afghanistan",   34.946,  69.265, "air"),
    ("KANDHR",  "Kandahar (legacy)",    "Afghanistan",   31.506,  65.847, "air"),
    ("BAHRAIN", "NSA Bahrain",          "Bahrain",       26.209,  50.612, "sea"),
    ("ISABAH",  "Isa Air Base",         "Bahrain",       25.946,  50.595, "air"),
    ("PSAB",    "Prince Sultan AB",     "Saudi Arabia",  24.063,  47.581, "air"),
    ("KKIA",    "King Khalid Intl",     "Saudi Arabia",  24.957,  46.699, "air"),
    ("JEDDAH",  "Jeddah Islamic Port",  "Saudi Arabia",  21.491,  39.150, "sea"),
    ("DAMMAM",  "King Abdulaziz Port",  "Saudi Arabia",  26.508,  50.205, "sea"),
    ("TABUK",   "Tabuk RSAF",           "Saudi Arabia",  28.366,  36.619, "air"),
    ("MUWAFAQ", "Muwaffaq Salti AB",    "Jordan",        32.358,  36.259, "air"),
    ("AQABA",   "Port of Aqaba",        "Jordan",        29.518,  34.997, "sea"),
    ("ERBIL",   "Erbil Intl",           "Iraq",          36.237,  43.963, "joint"),
    ("BAGHDAD", "Baghdad Intl",         "Iraq",          33.262,  44.234, "air"),
    ("BASRAH",  "Basrah Port",          "Iraq",          30.534,  47.836, "sea"),
    ("ALASAD",  "Al Asad AB",           "Iraq",          33.785,  42.441, "air"),
    ("INCIRLK", "Incirlik AB",          "Turkey",        37.002,  35.426, "air"),
    ("DOHA",    "Doha Port",            "Qatar",         25.286,  51.568, "sea"),
    ("SOUDA",   "Souda Bay",            "Greece",        35.539,  24.149, "joint"),
    ("AVIANO",  "Aviano AB",            "Italy",         46.032,  12.596, "air"),
    ("RAMSTN",  "Ramstein AB",          "Germany",       49.437,   7.600, "air"),
    ("ROTA",    "Naval Station Rota",   "Spain",         36.645,  -6.349, "sea"),
    ("DJIBSEA", "Port of Djibouti",     "Djibouti",      11.595,  43.143, "sea"),
    ("LEMONNR", "Camp Lemonnier",       "Djibouti",      11.546,  43.159, "joint"),
    ("DIEGOGR", "Diego Garcia",         "BIOT",         -7.313,   72.411, "joint"),
    ("MANAMA",  "Manama Logistics Hub", "Bahrain",       26.227,  50.586, "land"),
    ("SHARM",   "Sharm el-Sheikh Intl", "Egypt",         27.977,  34.395, "air"),
    ("CAIROW",  "Cairo West AB",        "Egypt",         30.115,  30.917, "air"),
    ("LARNACA", "Larnaca Intl",         "Cyprus",        34.875,  33.624, "air"),
    ("MORON",   "Moron AB",             "Spain",         37.175,  -5.616, "air"),
    ("KARACHI", "Karachi Port",         "Pakistan",      24.846,  66.989, "sea"),
    ("MANAS",   "Manas (legacy)",       "Kyrgyzstan",    43.061,  74.477, "air"),
    ("SALALAH", "Port of Salalah",      "Oman",          16.943,  54.005, "sea"),
    ("MUHARRQ", "Muharraq Bahrain",     "Bahrain",       26.270,  50.633, "air"),
    ("ABUDHB",  "Zayed Port AUH",       "UAE",           24.519,  54.378, "sea"),
    ("HARGEISA","Hargeisa Intl",        "Somaliland",    9.518,   44.088, "air"),
    ("MOMBASA", "Port of Mombasa",      "Kenya",         -4.044,  39.668, "sea"),
    ("KUWAIT",  "Kuwait Intl",          "Kuwait",        29.227,  47.972, "air"),
    ("DOHAINT", "Hamad Intl Doha",      "Qatar",         25.273,  51.608, "air"),
    ("RIYADH",  "Riyadh Intl Cargo",    "Saudi Arabia",  24.961,  46.701, "air"),
]
assert len(BASES_RAW) == 50, f"expected 50 bases, got {len(BASES_RAW)}"


# Asset class definitions: capacity in pallets, fuel burn lb/hr cruise, speed kn
ASSET_CLASSES = [
    {"class": "C-17 Globemaster III", "mode": "air", "cap_pallets": 18,
     "cruise_kn": 450, "fuel_lb_hr": 20000, "max_pax": 102, "range_nm": 2400},
    {"class": "C-130J Super Hercules", "mode": "air", "cap_pallets": 6,
     "cruise_kn": 348, "fuel_lb_hr": 5500, "max_pax": 92, "range_nm": 1800},
    {"class": "KC-46 Pegasus", "mode": "air", "cap_pallets": 18,
     "cruise_kn": 461, "fuel_lb_hr": 16000, "max_pax": 58, "range_nm": 6385},
    {"class": "C-5M Super Galaxy", "mode": "air", "cap_pallets": 36,
     "cruise_kn": 450, "fuel_lb_hr": 28000, "max_pax": 73, "range_nm": 4400},
    {"class": "M1083 MTV Convoy (8x)", "mode": "land", "cap_pallets": 32,
     "cruise_kn": 30, "fuel_lb_hr": 480, "max_pax": 16, "range_nm": 300},
    {"class": "M1120 LHS Convoy (6x)", "mode": "land", "cap_pallets": 24,
     "cruise_kn": 32, "fuel_lb_hr": 420, "max_pax": 12, "range_nm": 320},
    {"class": "MV-22B Osprey", "mode": "air", "cap_pallets": 2,
     "cruise_kn": 240, "fuel_lb_hr": 4500, "max_pax": 24, "range_nm": 870},
    {"class": "CSS Bobo-class MPS", "mode": "sea", "cap_pallets": 1200,
     "cruise_kn": 18, "fuel_lb_hr": 32000, "max_pax": 26, "range_nm": 11000},
    {"class": "MV-class Container Ship", "mode": "sea", "cap_pallets": 2400,
     "cruise_kn": 22, "fuel_lb_hr": 36000, "max_pax": 24, "range_nm": 12000},
    {"class": "T-AKE Lewis-class Dry Cargo", "mode": "sea", "cap_pallets": 800,
     "cruise_kn": 20, "fuel_lb_hr": 24000, "max_pax": 124, "range_nm": 14000},
]

READINESS_STATES = ["FMC", "FMC", "FMC", "FMC", "PMC", "PMC", "NMC"]  # weighted


def haversine_nm(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R_nm = 3440.065
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * R_nm * math.asin(math.sqrt(a))


def build_bases() -> list[dict]:
    return [
        {"code": code, "name": name, "country": country,
         "lat": lat, "lon": lon, "type": kind, "theater": "CENTCOM"}
        for (code, name, country, lat, lon, kind) in BASES_RAW
    ]


def build_assets(bases: list[dict], rng: random.Random, n: int = 200) -> list[dict]:
    assets: list[dict] = []
    air_bases = [b["code"] for b in bases if b["type"] in ("air", "joint")]
    sea_bases = [b["code"] for b in bases if b["type"] in ("sea", "joint")]
    land_bases = [b["code"] for b in bases if b["type"] in ("land", "joint", "air")]
    for i in range(1, n + 1):
        klass = rng.choice(ASSET_CLASSES)
        if klass["mode"] == "air":
            base = rng.choice(air_bases)
        elif klass["mode"] == "sea":
            base = rng.choice(sea_bases)
        else:
            base = rng.choice(land_bases)
        readiness = rng.choice(READINESS_STATES)
        # cap_pallets variance ±15%
        cap = max(1, int(klass["cap_pallets"] * rng.uniform(0.85, 1.15)))
        burn = int(klass["fuel_lb_hr"] * rng.uniform(0.92, 1.08))
        assets.append({
            "asset_id": f"AST-{i:03d}",
            "callsign": f"{klass['mode'][0].upper()}{rng.randint(100,999)}",
            "class": klass["class"],
            "mode": klass["mode"],
            "cap_pallets": cap,
            "max_pax": klass["max_pax"],
            "cruise_kn": klass["cruise_kn"],
            "fuel_lb_hr": burn,
            "range_nm": klass["range_nm"],
            "current_base": base,
            "readiness": readiness,
            "theater": "CENTCOM",
        })
    return assets


def build_graph(bases: list[dict], rng: random.Random) -> dict:
    """Adjacency list. Air edges: any two air/joint nodes < 2400 nm.
    Sea edges: any two sea/joint nodes < 4000 nm. Land edges: < 700 nm + same/adjacent country."""
    by_code = {b["code"]: b for b in bases}
    adj: dict[str, list[dict]] = {b["code"]: [] for b in bases}

    # ---- air ----
    air_nodes = [b for b in bases if b["type"] in ("air", "joint")]
    for a in air_nodes:
        for b in air_nodes:
            if a["code"] == b["code"]:
                continue
            d = haversine_nm(a["lat"], a["lon"], b["lat"], b["lon"])
            if d < 2400:
                adj[a["code"]].append({"to": b["code"], "mode": "air",
                                       "distance_nm": round(d, 1)})

    # ---- sea ----
    sea_nodes = [b for b in bases if b["type"] in ("sea", "joint")]
    for a in sea_nodes:
        for b in sea_nodes:
            if a["code"] == b["code"]:
                continue
            d = haversine_nm(a["lat"], a["lon"], b["lat"], b["lon"])
            if d < 4500:
                adj[a["code"]].append({"to": b["code"], "mode": "sea",
                                       "distance_nm": round(d, 1)})

    # ---- land ----
    land_nodes = [b for b in bases if b["type"] in ("land", "joint", "air")]
    for a in land_nodes:
        for b in land_nodes:
            if a["code"] == b["code"]:
                continue
            d = haversine_nm(a["lat"], a["lon"], b["lat"], b["lon"])
            # same country OR neighbor pair list
            same_country = a["country"] == b["country"]
            neighbor_pair = {a["country"], b["country"]} in [
                {"Kuwait", "Iraq"}, {"Iraq", "Saudi Arabia"}, {"Saudi Arabia", "UAE"},
                {"Saudi Arabia", "Jordan"}, {"Jordan", "Iraq"}, {"UAE", "Oman"},
                {"Saudi Arabia", "Bahrain"}, {"Saudi Arabia", "Qatar"},
                {"Qatar", "UAE"}, {"Iraq", "Turkey"}, {"Turkey", "Greece"},
                {"Bahrain", "Qatar"},
            ]
            if d < 750 and (same_country or neighbor_pair):
                adj[a["code"]].append({
                    "to": b["code"], "mode": "road",
                    "distance_nm": round(d, 1),
                })
    # dedupe per (to, mode)
    for code, edges in adj.items():
        seen = set()
        unique = []
        for e in edges:
            k = (e["to"], e["mode"])
            if k in seen:
                continue
            seen.add(k)
            unique.append(e)
        adj[code] = unique
    return {"nodes": [b["code"] for b in bases], "adj": adj}


def main() -> None:
    rng = seeded(1776)
    out = Path(__file__).parent
    bases = build_bases()
    assets = build_assets(bases, rng, n=200)
    graph = build_graph(bases, rng)

    write_csv(out / "bases.csv", bases)
    write_csv(out / "assets.csv", assets)
    write_json(out / "graph.json", graph)

    print(f"Wrote {len(bases)} bases -> {out/'bases.csv'}")
    print(f"Wrote {len(assets)} assets -> {out/'assets.csv'}")
    edge_count = sum(len(v) for v in graph["adj"].values())
    print(f"Wrote graph with {edge_count} directed edges -> {out/'graph.json'}")


if __name__ == "__main__":
    main()
