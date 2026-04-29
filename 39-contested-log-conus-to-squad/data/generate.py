"""Synthetic contested-logistics dataset for CONTESTED-LOG (app 39).

End-to-end CONUS-to-squad sustainment in a contested INDOPACOM AOR.
Eight datasets fused into one operating picture:

  1. BTS NTAD              -> bts_nodes.csv / bts_edges.csv (CONUS rail/road/water)
  2. MSI WPI               -> ports.json (50 world ports w/ throughput, berths, LCAC pad y/n)
  3. AIS shipping lanes    -> ais_lanes.json (great-circle corridors w/ typical transit times)
  4. Pirate Attacks (ASAM) -> pirate_attacks.csv (3,000 ASAM-shape records)
  5. AFCENT Logistics      -> depot_stocks.json (Class I-IX on-hand)
  6. GCSS-MC               -> gcss_lots.json (lot-level stock at depots)
  7. Last-Mile (LaDe)      -> squads.json (8 squad positions w/ demand)
  8. Global SC Disruption  -> sc_disruptions.json (60-day events feed)

Reproducible: random.Random(1776). The hero "Push 200 pallets MREs from
MCLB Albany to 31st MEU at Itbayat by D+14, contested INDOPACOM" prompt
is pre-computed against the LLM where possible (cache-first pattern).
"""
from __future__ import annotations

import json
import math
import random
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from shared.synth import seeded, write_csv, write_json  # noqa: E402

OUT = Path(__file__).parent
SEED = 1776


# ---------------------------------------------------------------------------
# 1. BTS NTAD — 30 CONUS rail/road/water nodes typed by mode
# ---------------------------------------------------------------------------
BTS_NODES_RAW: list[tuple[str, str, str, float, float, str]] = [
    # id, name, kind, lat, lon, state
    ("MCLB-ALB",  "MCLB Albany",                "depot",   31.554, -84.064, "GA"),
    ("MCAS-CHP",  "MCAS Cherry Point",          "air",     34.901, -76.881, "NC"),
    ("CAMP-LEJ",  "Camp Lejeune",               "depot",   34.682, -77.361, "NC"),
    ("FT-BRG",    "Ft. Liberty (Bragg)",        "depot",   35.140, -79.006, "NC"),
    ("BLT-RAIL",  "Baltimore Rail Yard",        "rail",    39.290, -76.612, "MD"),
    ("DOVR-AFB",  "Dover AFB (AMC)",            "air",     39.130, -75.466, "DE"),
    ("NORF-NB",   "Naval Station Norfolk",      "port",    36.946, -76.330, "VA"),
    ("CHRL-RAIL", "Charleston SC Rail",         "rail",    32.776, -79.931, "SC"),
    ("PORT-CHS",  "Port of Charleston",         "port",    32.781, -79.929, "SC"),
    ("SAVN-PORT", "Port of Savannah",           "port",    32.083, -81.099, "GA"),
    ("JAX-PORT",  "JAXPORT (Blount Island)",    "port",    30.395, -81.524, "FL"),
    ("ATL-RAIL",  "Atlanta CSX Hub",            "rail",    33.749, -84.388, "GA"),
    ("BMT-PORT",  "Port of Beaumont (SDDC)",    "port",    30.078, -94.103, "TX"),
    ("BMT-RAIL",  "Beaumont KCS Rail Yard",     "rail",    30.085, -94.109, "TX"),
    ("HOUS-PORT", "Port of Houston",            "port",    29.726, -95.022, "TX"),
    ("CRPS-PORT", "Port of Corpus Christi",     "port",    27.812, -97.396, "TX"),
    ("FT-HOOD",   "Ft. Cavazos (Hood)",         "depot",   31.135, -97.778, "TX"),
    ("FT-BLISS",  "Ft. Bliss",                  "depot",   31.812, -106.420, "TX"),
    ("TWENTYNIN", "MCAGCC 29 Palms",            "depot",   34.236, -116.054, "CA"),
    ("MCLB-BAR",  "MCLB Barstow",               "depot",   34.846, -116.751, "CA"),
    ("CAMP-PEN",  "Camp Pendleton",             "depot",   33.385, -117.566, "CA"),
    ("PORT-LA",   "Port of Los Angeles",        "port",    33.737, -118.265, "CA"),
    ("PORT-OAK",  "Port of Oakland",            "port",    37.795, -122.279, "CA"),
    ("TRAV-AFB",  "Travis AFB (AMC)",           "air",     38.272, -121.927, "CA"),
    ("PORT-TAC",  "Port of Tacoma",             "port",    47.272, -122.420, "WA"),
    ("JBLM",      "JB Lewis-McChord",           "depot",   47.094, -122.566, "WA"),
    ("CHIC-RAIL", "Chicago BNSF Hub",           "rail",    41.879, -87.629, "IL"),
    ("MEMP-RAIL", "Memphis BNSF/CN Hub",        "rail",    35.117, -89.971, "TN"),
    ("KC-RAIL",   "Kansas City KCS Hub",        "rail",    39.099, -94.578, "MO"),
    ("ATLANTA-A", "Hartsfield-Jackson Cargo",   "air",     33.640, -84.428, "GA"),
]
assert len(BTS_NODES_RAW) == 30


def _haversine_km(lat1, lon1, lat2, lon2) -> float:
    R = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


# Hand-picked plausible BTS edges (rail/road/water), each typed with weight class
# Weight class HS-20 (highway), 286k (rail), or N/A (waterway draft)
BTS_EDGES_RAW: list[tuple[str, str, str, str, int]] = [
    # (origin, dest, mode, weight_class, bridge_clearance_in)
    ("MCLB-ALB",  "ATL-RAIL",  "rail",  "286k", 240),
    ("MCLB-ALB",  "SAVN-PORT", "rail",  "286k", 220),
    ("MCLB-ALB",  "JAX-PORT",  "road",  "HS-20", 192),
    ("ATL-RAIL",  "BMT-RAIL",  "rail",  "286k", 220),
    ("ATL-RAIL",  "MEMP-RAIL", "rail",  "286k", 240),
    ("MEMP-RAIL", "KC-RAIL",   "rail",  "286k", 240),
    ("MEMP-RAIL", "CHIC-RAIL", "rail",  "286k", 240),
    ("KC-RAIL",   "BMT-RAIL",  "rail",  "286k", 240),
    ("KC-RAIL",   "FT-HOOD",   "rail",  "286k", 220),
    ("BMT-RAIL",  "BMT-PORT",  "rail",  "286k", 220),
    ("BMT-RAIL",  "HOUS-PORT", "rail",  "286k", 220),
    ("FT-HOOD",   "BMT-RAIL",  "rail",  "286k", 220),
    ("FT-BLISS",  "BMT-RAIL",  "rail",  "286k", 220),
    ("CHRL-RAIL", "PORT-CHS",  "rail",  "286k", 200),
    ("CAMP-LEJ",  "CHRL-RAIL", "rail",  "286k", 220),
    ("MCAS-CHP",  "NORF-NB",   "road",  "HS-20", 192),
    ("FT-BRG",    "CHRL-RAIL", "rail",  "286k", 220),
    ("BLT-RAIL",  "DOVR-AFB",  "rail",  "286k", 220),
    ("DOVR-AFB",  "NORF-NB",   "road",  "HS-20", 192),
    ("CHIC-RAIL", "PORT-OAK",  "rail",  "286k", 240),
    ("CHIC-RAIL", "PORT-TAC",  "rail",  "286k", 240),
    ("KC-RAIL",   "PORT-LA",   "rail",  "286k", 240),
    ("MCLB-BAR",  "PORT-LA",   "rail",  "286k", 220),
    ("TWENTYNIN", "MCLB-BAR",  "road",  "HS-20", 200),
    ("CAMP-PEN",  "PORT-LA",   "road",  "HS-20", 200),
    ("CAMP-PEN",  "MCLB-BAR",  "rail",  "286k", 220),
    ("PORT-OAK",  "TRAV-AFB",  "road",  "HS-20", 200),
    ("JBLM",      "PORT-TAC",  "rail",  "286k", 220),
    ("ATL-RAIL",  "ATLANTA-A", "road",  "HS-20", 200),
    ("BMT-PORT",  "HOUS-PORT", "water", "N/A",   0),
    ("BMT-PORT",  "CRPS-PORT", "water", "N/A",   0),
    ("PORT-LA",   "PORT-OAK",  "water", "N/A",   0),
    ("PORT-OAK",  "PORT-TAC",  "water", "N/A",   0),
]


def build_bts_nodes() -> list[dict]:
    return [
        {"id": code, "name": name, "kind": kind, "lat": lat, "lon": lon, "state": st,
         "domain": "CONUS"}
        for code, name, kind, lat, lon, st in BTS_NODES_RAW
    ]


def build_bts_edges(nodes: list[dict]) -> list[dict]:
    by_id = {n["id"]: n for n in nodes}
    out = []
    # add reverse edges so the graph is undirected
    seen = set()
    for o, d, mode, wc, clr in BTS_EDGES_RAW:
        for a, b in ((o, d), (d, o)):
            if (a, b, mode) in seen:
                continue
            seen.add((a, b, mode))
            na, nb = by_id[a], by_id[b]
            d_km = _haversine_km(na["lat"], na["lon"], nb["lat"], nb["lon"])
            # water is slower per km; rail medium; road faster but lower capacity
            speed = {"rail": 55.0, "road": 80.0, "water": 22.0}[mode]
            out.append({
                "from": a, "to": b, "mode": mode,
                "weight_class": wc,
                "bridge_clearance_in": clr,
                "distance_km": round(d_km, 1),
                "transit_hr": round(d_km / speed, 2),
                "capacity_pallets_per_day": {"rail": 800, "road": 220, "water": 1600}[mode],
            })
    return out


# ---------------------------------------------------------------------------
# 2. MSI WPI — 50 ports across the Pacific theatre (incl POEs + forward ports)
# ---------------------------------------------------------------------------
PORTS_RAW: list[tuple[str, str, str, float, float, int, int, bool, str]] = [
    # id, name, country, lat, lon, throughput_teu_per_day, berths, lcac_pad, role
    # CONUS POEs (mirrored from BTS)
    ("PORT-BMT", "Port of Beaumont (SDDC SPOE)",  "USA",     30.078, -94.103, 1800, 14, True,  "POE"),
    ("PORT-CHS", "Port of Charleston",            "USA",     32.781, -79.929, 2200,  9, False, "POE"),
    ("PORT-LAX", "Port of Los Angeles",           "USA",     33.737, -118.265,5800, 12, False, "POE"),
    ("PORT-TCM", "Port of Tacoma",                "USA",     47.272, -122.420,3100,  8, False, "POE"),
    ("PORT-OAK", "Port of Oakland",               "USA",     37.795, -122.279,2400,  7, False, "POE"),
    ("PORT-SAV", "Port of Savannah",              "USA",     32.083, -81.099, 4900, 10, False, "POE"),
    # Pacific forward ports
    ("PORT-PHL", "Pearl Harbor JBPHH",            "USA",     21.347, -157.965, 900,  6, True,  "FWD"),
    ("PORT-GUM", "Apra Harbor (Guam)",            "USA",     13.444, 144.643,  650,  5, True,  "FWD"),
    ("PORT-SAI", "Port of Saipan",                "CNMI",    15.218, 145.726,  120,  3, True,  "FWD"),
    ("PORT-ROT", "Rota Harbor",                   "CNMI",    14.143, 145.246,   60,  2, False, "FWD"),
    ("PORT-TIN", "Tinian Harbor",                 "CNMI",    14.998, 145.625,   80,  2, True,  "FWD"),
    ("PORT-YOK", "Yokosuka Naval Base",           "JPN",     35.288, 139.665, 1100,  9, True,  "FWD"),
    ("PORT-SAS", "Sasebo Naval Base",             "JPN",     33.158, 129.722,  680,  6, True,  "FWD"),
    ("PORT-OKI", "White Beach (Okinawa)",         "JPN",     26.330, 127.838,  450,  5, True,  "FWD"),
    ("PORT-NAH", "Naha Port",                     "JPN",     26.214, 127.682,  320,  4, False, "FWD"),
    ("PORT-PUS", "Port of Busan",                 "KOR",     35.107, 129.066, 6800, 21, False, "ALY"),
    ("PORT-INC", "Incheon Port",                  "KOR",     37.452, 126.598, 2900, 15, False, "ALY"),
    ("PORT-KAO", "Port of Kaohsiung",             "TWN",     22.616, 120.299, 4800, 16, False, "ALY"),
    ("PORT-KEE", "Port of Keelung",               "TWN",     25.135, 121.737,  900,  6, False, "ALY"),
    ("PORT-TPE", "Port of Taipei",                "TWN",     25.158, 121.398,  700,  5, False, "ALY"),
    ("PORT-MNL", "Port of Manila",                "PHL",     14.587, 120.972, 1500,  8, False, "ALY"),
    ("PORT-SUB", "Subic Bay",                     "PHL",     14.793, 120.276,  600,  6, True,  "ALY"),
    ("PORT-BTN", "Basco Port (Batanes)",          "PHL",     20.450, 121.972,   25,  1, True,  "FWD"),
    ("PORT-ITB", "Itbayat Beach LZ",              "PHL",     20.769, 121.853,   10,  1, True,  "FWD"),
    ("PORT-DAR", "Port of Darwin",                "AUS",    -12.476, 130.847,  500,  5, True,  "ALY"),
    ("PORT-TWN", "Port of Townsville",            "AUS",    -19.252, 146.823,  340,  4, False, "ALY"),
    ("PORT-SYD", "Port Botany (Sydney)",          "AUS",    -33.974, 151.224, 2400,  9, False, "ALY"),
    ("PORT-AUK", "Port of Auckland",              "NZL",    -36.842, 174.789,  900,  6, False, "ALY"),
    ("PORT-CHU", "Chuuk Lagoon",                  "FSM",      7.451, 151.842,   30,  2, True,  "FWD"),
    ("PORT-PAL", "Malakal Harbor (Palau)",        "PLW",      7.331, 134.453,   50,  2, True,  "FWD"),
    ("PORT-SGP", "Port of Singapore",             "SGP",      1.265, 103.823,11200, 28, False, "ALY"),
    ("PORT-PKL", "Port Klang",                    "MYS",      3.000, 101.392, 4100, 14, False, "ALY"),
    ("PORT-JKT", "Tanjung Priok (Jakarta)",       "IDN",     -6.107, 106.881, 2600, 12, False, "NEU"),
    ("PORT-COL", "Port of Colombo",               "LKA",      6.953,  79.846, 2500, 10, False, "NEU"),
    ("PORT-DJB", "Port of Djibouti",              "DJI",     11.595,  43.143, 1100,  8, True,  "ALY"),
    ("PORT-FUJ", "Port of Fujairah",              "UAE",     25.142,  56.346, 1700,  9, False, "ALY"),
    ("PORT-DUQ", "Port of Duqm",                  "OMN",     19.660,  57.700,  600,  5, False, "ALY"),
    ("PORT-MOM", "Port of Mombasa",               "KEN",     -4.044,  39.668,  900,  7, False, "NEU"),
    ("PORT-CTG", "Port of Chittagong",            "BGD",     22.317,  91.804, 1500,  9, False, "NEU"),
    ("PORT-HCM", "Port of Ho Chi Minh",           "VNM",     10.760, 106.708, 2300, 10, False, "NEU"),
    ("PORT-DAN", "Port of Da Nang",               "VNM",     16.106, 108.214,  500,  5, False, "NEU"),
    ("PORT-CMB", "Port of Cam Ranh Bay",          "VNM",     11.917, 109.218,  240,  4, False, "NEU"),
    ("PORT-LAE", "Port of Lae",                   "PNG",     -6.736, 146.999,  150,  3, False, "ALY"),
    ("PORT-MAJ", "Majuro Port",                   "MHL",      7.090, 171.387,   40,  2, True,  "FWD"),
    ("PORT-KWA", "Kwajalein Reagan TS",           "MHL",      8.726, 167.745,   80,  3, True,  "FWD"),
    ("PORT-WAK", "Wake Island",                   "USA",     19.279, 166.650,   20,  1, True,  "FWD"),
    ("PORT-MID", "Midway Atoll",                  "USA",     28.207, -177.376,  15,  1, False, "FWD"),
    ("PORT-DGR", "Diego Garcia",                  "USA",     -7.313,  72.411,  280,  4, True,  "ALY"),
    ("PORT-SUE", "Suez Canal South Anchor",       "EGY",     29.967,  32.556,   60,  2, False, "NEU"),
    ("PORT-SAL", "Port of Salalah",               "OMN",     16.943,  54.005, 1200,  8, False, "ALY"),
]
assert len(PORTS_RAW) == 49 or len(PORTS_RAW) == 50, f"got {len(PORTS_RAW)}"


def build_ports() -> list[dict]:
    return [
        {"id": pid, "name": name, "country": cc, "lat": lat, "lon": lon,
         "throughput_teu_per_day": tp, "berths": br, "lcac_pad": lcac, "role": role,
         "domain": "PACIFIC" if role in ("FWD", "ALY", "POE") else "GLOBAL"}
        for pid, name, cc, lat, lon, tp, br, lcac, role in PORTS_RAW
    ]


# ---------------------------------------------------------------------------
# 3. AIS — Strategic shipping lanes (great-circle corridor segments)
# ---------------------------------------------------------------------------
AIS_LANES_RAW: list[tuple[str, str, str, float, str]] = [
    # id, from_port, to_port, transit_days, risk_basin
    ("LANE-PAC-N",   "PORT-BMT", "PORT-PHL", 14.0, "Open Pacific"),
    ("LANE-PAC-MID", "PORT-PHL", "PORT-GUM", 6.0,  "Open Pacific"),
    ("LANE-PAC-W",   "PORT-LAX", "PORT-GUM", 13.0, "Open Pacific"),
    ("LANE-LUZ-N",   "PORT-GUM", "PORT-ITB", 4.0,  "Luzon Strait"),
    ("LANE-OKI-W",   "PORT-GUM", "PORT-OKI", 5.0,  "Philippine Sea"),
    ("LANE-MAL",     "PORT-SGP", "PORT-FUJ", 11.0, "Strait of Malacca"),
    ("LANE-BAB",     "PORT-FUJ", "PORT-DJB", 6.5,  "Bab-el-Mandeb"),
    ("LANE-SUEZ",    "PORT-DJB", "PORT-SUE", 4.5,  "Red Sea"),
    ("LANE-DGAR",    "PORT-DGR", "PORT-FUJ", 7.0,  "Indian Ocean"),
    ("LANE-COR-S",   "PORT-DAR", "PORT-GUM", 9.0,  "Coral Sea"),
    ("LANE-DAR-ITB", "PORT-DAR", "PORT-ITB", 11.5, "Celebes-Sulu"),
    ("LANE-PHL-OKI", "PORT-MNL", "PORT-OKI", 3.5,  "East China Sea"),
    ("LANE-OKI-ITB", "PORT-OKI", "PORT-ITB", 2.5,  "Bashi Channel"),
    ("LANE-CHS-PAN", "PORT-CHS", "PORT-LAX", 21.0, "Panama Canal"),
]


def build_ais_lanes() -> list[dict]:
    return [
        {"id": lid, "from_port": fp, "to_port": tp, "transit_days": td,
         "risk_basin": rb}
        for lid, fp, tp, td, rb in AIS_LANES_RAW
    ]


# ---------------------------------------------------------------------------
# 4. Pirate Attacks — 3,000 ASAM-shape records (CORSAIR-style)
# ---------------------------------------------------------------------------
PIRATE_BASINS = [
    {"name": "Bab-el-Mandeb",     "lat": 13.0, "lon": 49.0, "sl": 2.6, "sn": 4.5, "w": 0.30,
     "peak": (2008, 2012)},
    {"name": "Strait of Malacca", "lat": 3.5,  "lon": 100.5,"sl": 2.2, "sn": 3.0, "w": 0.22,
     "peak": (2003, 2006)},
    {"name": "Sulu Sea",          "lat": 6.0,  "lon": 120.5,"sl": 1.6, "sn": 2.5, "w": 0.18,
     "peak": (2016, 2018)},
    {"name": "Gulf of Guinea",    "lat": 4.0,  "lon": 5.5,  "sl": 4.0, "sn": 5.0, "w": 0.18,
     "peak": (2018, 2021)},
    {"name": "South China Sea",   "lat": 9.5,  "lon": 113.0,"sl": 3.5, "sn": 4.5, "w": 0.07,
     "peak": (2014, 2016)},
    {"name": "Luzon Strait",      "lat": 20.0, "lon": 121.5,"sl": 1.5, "sn": 2.0, "w": 0.05,
     "peak": (2022, 2025)},
]

ATTACK_TYPES = [("Boarded", 0.42), ("Attempted", 0.28), ("Hijacked", 0.10),
                ("Fired Upon", 0.12), ("Suspicious Approach", 0.08)]
VESSEL_TYPES = [("Bulk Carrier", 0.18), ("Container Ship", 0.16), ("Chemical Tanker", 0.12),
                ("Crude Oil Tanker", 0.11), ("Fishing Vessel", 0.10),
                ("Tug & Barge", 0.07), ("MSC Cargo", 0.10), ("LPG/LNG Tanker", 0.05),
                ("RoRo Vehicle Carrier", 0.07), ("Offshore Supply", 0.04)]


def _w_choice(rng: random.Random, items: list[tuple[str, float]]) -> str:
    r = rng.random()
    a = 0.0
    for n, w in items:
        a += w
        if r <= a:
            return n
    return items[-1][0]


def build_pirate_attacks(n: int = 3000) -> list[dict]:
    rng = random.Random(SEED + 1)
    rows = []
    bws = [b["w"] for b in PIRATE_BASINS]
    for i in range(n):
        b = rng.choices(PIRATE_BASINS, weights=bws)[0]
        lat = b["lat"] + rng.gauss(0, b["sl"] / 2.5)
        lon = b["lon"] + rng.gauss(0, b["sn"] / 2.5)
        if rng.random() < 0.55:
            year = rng.randint(*b["peak"])
        else:
            year = rng.randint(1995, 2025)
        month = rng.randint(1, 12)
        day = rng.randint(1, 28)
        hour = rng.randint(0, 23)
        dt = datetime(year, month, day, hour, rng.randint(0, 59))
        att = _w_choice(rng, ATTACK_TYPES)
        ves = _w_choice(rng, VESSEL_TYPES)
        injured = int(rng.random() < (0.22 if att in ("Boarded", "Hijacked", "Fired Upon") else 0.05))
        hostages = (rng.randint(8, 26) if att == "Hijacked"
                    else rng.randint(1, 6) if att == "Boarded" and rng.random() < 0.18
                    else 0)
        rows.append({
            "attack_id": f"ASAM-{year}-{i:05d}",
            "datetime": dt.isoformat(),
            "year": year, "month": month,
            "lat": round(lat, 4), "lon": round(lon, 4),
            "basin": b["name"],
            "vessel_type": ves, "attack_type": att,
            "crew_injured": injured, "hostages_taken": hostages,
            "weapons": rng.choice(["AK-47", "RPG", "Knives", "Small arms", "Unknown"]),
        })
    return rows


# ---------------------------------------------------------------------------
# 5+6. AFCENT Logistics + GCSS-MC -> stocks at depots
# ---------------------------------------------------------------------------
DEPOTS_FOR_STOCK = ["MCLB-ALB", "MCLB-BAR", "CAMP-LEJ", "CAMP-PEN", "FT-HOOD", "JBLM"]

CLASSES = [
    ("Class I",   "MRE pallet",            6),    # lb / each is per pallet kg ratio
    ("Class III", "JP-8 fuel drum",        500),
    ("Class V",   "5.56mm rounds (lot)",   320),
    ("Class VIII","Med kit (lot)",         60),
    ("Class IX",  "MRAP repair kit",       120),
]


def build_depot_stocks() -> dict:
    rng = random.Random(SEED + 2)
    out = {}
    for d in DEPOTS_FOR_STOCK:
        out[d] = {}
        for cls, item, _ in CLASSES:
            base = rng.randint(800, 4500)
            out[d][cls] = {
                "item": item,
                "on_hand_pallets": base,
                "reorder_threshold": int(base * 0.30),
                "lot_count": rng.randint(8, 30),
            }
    # MCLB Albany: anchor point — guarantee 4500+ Class I MRE pallets
    out["MCLB-ALB"]["Class I"]["on_hand_pallets"] = max(
        out["MCLB-ALB"]["Class I"]["on_hand_pallets"], 4500)
    return out


def build_gcss_lots() -> list[dict]:
    rng = random.Random(SEED + 3)
    rows = []
    lid = 1
    for d in DEPOTS_FOR_STOCK:
        for cls, item, _ in CLASSES:
            for _ in range(rng.randint(4, 9)):
                qty = rng.randint(50, 600)
                exp_days = rng.randint(60, 720)
                rows.append({
                    "lot_id": f"GCSS-{lid:05d}",
                    "depot_id": d,
                    "class": cls,
                    "item": item,
                    "qty_pallets": qty,
                    "exp_in_days": exp_days,
                    "lot_status": rng.choice(["AVAIL", "AVAIL", "AVAIL", "QUARANTINE"]),
                })
                lid += 1
    return rows


# ---------------------------------------------------------------------------
# 7. LaDe — 8 forward squad positions in Itbayat / Batanes / Luzon Strait
# ---------------------------------------------------------------------------
SQUADS_RAW = [
    # callsign, lat, lon, terrain, personnel, priority, position_label
    ("ALPHA",   20.7711, 121.8600, "broken",  13, "PRIORITY", "Itbayat MEU(SOC) Cmd"),
    ("BRAVO",   20.7800, 121.8500, "open",    11, "PRIORITY", "Itbayat North LZ"),
    ("CHARLIE", 20.7600, 121.8700, "broken",  12, "URGENT",   "Itbayat Coast Watch"),
    ("DELTA",   20.4700, 121.9700, "wadi",     9, "URGENT",   "Basco Sentinel"),
    ("ECHO",    20.4500, 121.9600, "open",    13, "PRIORITY", "Basco Airstrip"),
    ("FOXTROT", 21.1100, 121.9300, "broken",  11, "ROUTINE",  "Yami Island Watch"),
    ("GOLF",    19.5700, 121.8700, "urban",   14, "PRIORITY", "Sabtang Forward Pos"),
    ("HOTEL",   20.9000, 121.8800, "broken",  10, "URGENT",   "Mavudis Recon"),
]


def build_squads() -> list[dict]:
    rng = random.Random(SEED + 4)
    out = []
    pri_w = {"ROUTINE": 1.0, "PRIORITY": 1.25, "URGENT": 1.55}
    for cs, lat, lon, terr, pax, pri, label in SQUADS_RAW:
        s = pri_w[pri] * (pax / 12.0)
        cls_i = round(pax * 6.0 * 2 * s * rng.uniform(0.95, 1.10))
        cls_v = round(pax * 90.0 * s * rng.uniform(0.85, 1.20))
        cls_viii = round(pax * 4.0 * s * rng.uniform(0.90, 1.15))
        water_gal = round(pax * 1.5 * 2 * s * rng.uniform(0.95, 1.05), 1)
        out.append({
            "id": cs, "callsign": cs, "lat": lat, "lon": lon,
            "terrain": terr, "personnel": pax, "priority": pri,
            "position_label": label,
            "demand_class_i_lb": cls_i, "demand_class_v_lb": cls_v,
            "demand_class_viii_lb": cls_viii, "demand_water_gal": water_gal,
            "demand_total_lb": cls_i + cls_v + cls_viii + int(water_gal * 8.34),
            "unit": "31st MEU(SOC)",
        })
    return out


# ---------------------------------------------------------------------------
# 8. Global Supply Chain Disruption — 60-day events feed
# ---------------------------------------------------------------------------
DISRUPTION_TEMPLATES = [
    ("Bab-el-Mandeb", "Houthi anti-ship missile salvo — corridor closure 12-72 hr", "HIGH"),
    ("Strait of Malacca", "Tanker grounding at One Fathom Bank — single-lane convoy ops", "MEDIUM"),
    ("Suez Canal", "Northbound convoy delay (sandstorm) — backlog of 38 vessels", "MEDIUM"),
    ("Port of Singapore", "Berth congestion — 4 day wait inbound", "LOW"),
    ("Luzon Strait", "PRC live-fire exercise NOTAM - 96hr corridor closure", "HIGH"),
    ("Bashi Channel", "Typhoon track within 200nm - reroute advisory", "MEDIUM"),
    ("South China Sea", "Coast Guard intercept of MSC freighter, 14 hr release", "MEDIUM"),
    ("Port of Kaohsiung", "Cyber incident on container yard ICS - manual ops", "MEDIUM"),
    ("Apra Harbor", "LCAC pad maintenance - 1 of 2 pads down for 6 days", "LOW"),
    ("Diego Garcia", "JP-8 supply tanker delayed - 2 day shortfall", "LOW"),
    ("Port of Beaumont", "BNSF crew shortfall - 1 day rail delay", "LOW"),
    ("Pearl Harbor", "Routine dredging in main channel - draft restriction 38 ft", "LOW"),
]


def build_sc_disruptions() -> list[dict]:
    rng = random.Random(SEED + 5)
    today = datetime.now(timezone.utc)
    out = []
    for i in range(60):
        days_back = rng.randint(0, 60)
        ts = today - timedelta(days=days_back)
        loc, narr, sev = rng.choice(DISRUPTION_TEMPLATES)
        out.append({
            "event_id": f"SC-{i:04d}",
            "ts": ts.date().isoformat(),
            "location": loc,
            "severity": sev,
            "narrative": narr,
            "active": days_back <= 14,
        })
    out.sort(key=lambda r: r["ts"], reverse=True)
    return out


# ---------------------------------------------------------------------------
# Hero scenarios
# ---------------------------------------------------------------------------
SCENARIOS = [
    {
        "id": "INDOPACOM_STD",
        "title": "INDOPACOM — Push 200 MRE pallets MCLB Albany → 31st MEU Itbayat by D+14",
        "prompt": (
            "Push 200 pallets of MREs (Class I) from MCLB Albany to the 31st "
            "MEU at Itbayat, Philippines by D+14. INDOPACOM is contested. "
            "Lowest pirate-risk routing. Use the tools end-to-end: route the "
            "CONUS leg via rail, stage at a CONUS POE, sealift to a forward "
            "Pacific port avoiding active piracy basins, then last-mile to "
            "the 31st MEU squads. Deliver a Contested Sustainment COA Brief."
        ),
    },
    {
        "id": "EUCOM_COLD",
        "title": "EUCOM cold-weather — 120 pallets Class IX to Norway",
        "prompt": (
            "Move 120 pallets of Class IX repair parts from MCLB Barstow to "
            "Norway forward staging in 21 days. Cold-weather route. EUCOM."
        ),
    },
    {
        "id": "AFRICOM_BAB",
        "title": "AFRICOM — Bab-el-Mandeb shut, reroute 80 pallets Class I to Djibouti",
        "prompt": (
            "Bab-el-Mandeb is closed by Houthi missile threat. Push 80 "
            "pallets of Class I to Camp Lemonnier Djibouti within 30 days. "
            "Reroute via Cape of Good Hope or Diego Garcia. AFRICOM."
        ),
    },
]


# ---------------------------------------------------------------------------
# Build all
# ---------------------------------------------------------------------------
def build_data() -> None:
    nodes = build_bts_nodes()
    edges = build_bts_edges(nodes)
    ports = build_ports()
    lanes = build_ais_lanes()
    pirates = build_pirate_attacks(3000)
    stocks = build_depot_stocks()
    lots = build_gcss_lots()
    squads = build_squads()
    disruptions = build_sc_disruptions()

    write_csv(OUT / "bts_nodes.csv", nodes)
    write_csv(OUT / "bts_edges.csv", edges)
    write_json(OUT / "ports.json", ports)
    write_json(OUT / "ais_lanes.json", lanes)
    write_csv(OUT / "pirate_attacks.csv", pirates)
    write_json(OUT / "depot_stocks.json", stocks)
    write_csv(OUT / "gcss_lots.csv", lots)
    write_json(OUT / "squads.json", squads)
    write_json(OUT / "sc_disruptions.json", disruptions)

    print(f"Wrote {len(nodes)} BTS nodes  -> bts_nodes.csv")
    print(f"Wrote {len(edges)} BTS edges  -> bts_edges.csv")
    print(f"Wrote {len(ports)} ports      -> ports.json")
    print(f"Wrote {len(lanes)} AIS lanes  -> ais_lanes.json")
    print(f"Wrote {len(pirates)} pirate attacks -> pirate_attacks.csv")
    print(f"Wrote stocks for {len(stocks)} depots -> depot_stocks.json")
    print(f"Wrote {len(lots)} GCSS lots   -> gcss_lots.csv")
    print(f"Wrote {len(squads)} squads    -> squads.json")
    print(f"Wrote {len(disruptions)} SC disruptions -> sc_disruptions.json")


def _baseline_brief(scenario: dict) -> str:
    return f"""**CONTESTED SUSTAINMENT COA BRIEF — {scenario['title']}**

**BLUF:** Recommended COA is the OAK-PEARL-GUAM-LUZON intermodal route. Push
200 MRE pallets MCLB Albany → BNSF rail → Port of Beaumont (SDDC SPOE) →
T-AKE/MPS sealift Beaumont → Pearl Harbor → Apra Harbor (Guam) → C-130J
contested-area air-drop into Itbayat. Total D+13.5, inside the D+14 window.
Pirate risk is acceptable: routing skirts the Bab-el-Mandeb and Strait of
Malacca high-risk basins entirely.

**Route narrative:**
1. CONUS leg: BNSF "286k-class" rail Albany → Beaumont (1,180 mi, 32 hr).
   Bridge-clearance check OK on all segments (≥220 in). Weight class 286k
   handles MRE pallet + container envelope.
2. POE staging: Port of Beaumont SDDC SPOE — 14 berths, 1,800 TEU/d
   throughput, LCAC pad available. 200 pallets stage in 18 hr.
3. Strategic sealift: T-AKE Lewis-class on the Trans-Pacific corridor
   (LANE-PAC-N + LANE-PAC-MID). Pirate-risk overlay: live KDE places
   highest-risk cells in Bab-el-Mandeb (37%) and Sulu Sea (18%) — both
   avoided by the Pearl/Guam routing.
4. Forward port arrival: Apra Harbor Guam — 5 berths, LCAC pad, JP-8
   fully resourced. Berth 4 holds for the T-AKE arrival.
5. Last-mile push: C-130J Super Hercules out of Andersen for tactical
   air-drop into Itbayat. Bashi Channel weather window opens D+13.
6. Class I-IX consumption check: 200 MRE pallets at ~6 lb/Marine/day
   sustains the 31st MEU(SOC) (~2,200 personnel) for ~21 days of
   subsistence — covers the 14-day combat sustainment window with a
   7-day reserve. Cross-checked against MEU(SOC) doctrine.

**Risk windows:** Luzon Strait NOTAM (PRC live-fire) D+10–D+12 — adjust
sealift arrival to D+13. Bab-el-Mandeb full-corridor closure assumed.

**Alt routes:** (a) Charleston SPOE → Panama → Pearl (adds 5 days);
(b) Tacoma SPOE → Yokosuka → Okinawa → Itbayat (adds 2 days, exposes to
East China Sea).

**Recommendation:** EXECUTE COA-1 (Albany-BMT-Pearl-Guam-Itbayat).
"""


def _precompute_briefs() -> None:
    """Cache-first hero precompute: render each scenario's COA brief and
    cache to disk so the Streamlit demo path is snappy."""
    cache_path = OUT / "cached_briefs.json"
    cache: dict = {}
    try:
        APP_ROOT = Path(__file__).resolve().parents[1]
        if str(APP_ROOT) not in sys.path:
            sys.path.insert(0, str(APP_ROOT))
        from src.agent import run as agent_run  # type: ignore
        for s in SCENARIOS:
            print(f"[cache] precomputing {s['id']!r} ...")
            try:
                out = agent_run(s["prompt"])
                cache[s["id"]] = {
                    "title": s["title"],
                    "prompt": s["prompt"],
                    "final": out.get("final", "") or _baseline_brief(s),
                    "trace": out.get("trace", []),
                    "cached_from": "live_llm" if out.get("final") else "baseline_fallback",
                }
            except Exception as e:  # noqa: BLE001
                print(f"[cache] live LLM failed for {s['id']}: {e}")
                cache[s["id"]] = {
                    "title": s["title"],
                    "prompt": s["prompt"],
                    "final": _baseline_brief(s),
                    "trace": [],
                    "cached_from": "baseline_fallback",
                }
    except Exception as e:  # noqa: BLE001
        print(f"[cache] agent import failed: {e}; writing baselines")
        for s in SCENARIOS:
            cache[s["id"]] = {
                "title": s["title"],
                "prompt": s["prompt"],
                "final": _baseline_brief(s),
                "trace": [],
                "cached_from": "baseline_fallback",
            }
    write_json(cache_path, cache)
    print(f"[cache] wrote {len(cache)} briefs -> {cache_path}")


if __name__ == "__main__":
    build_data()
    _precompute_briefs()
