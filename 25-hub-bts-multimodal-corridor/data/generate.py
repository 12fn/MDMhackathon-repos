"""HUB synthetic data generator.

Produces the BTS NTAD-shaped corpus the app reads:
  data/nodes.json          - 30 named CONUS hubs (MCLBs, POEs, rail terminals, airports, river ports)
  data/edges.csv           - typed edges (road / rail / waterway / air) with capacity, clearance, weight limit
  data/end_items.json      - 10 USMC platforms with dim/weight/clearance constraints
  data/cached_briefs.json  - pre-computed POE Movement Plan briefs for 3 hero scenarios

Seed = 1776 for reproducibility.

Real-data swap: replace this module with a load of the Bureau of Transportation
Statistics National Transportation Atlas Database (NTAD) shapefiles + the
Freight Analysis Framework flow tables. See data/load_real.py.
"""
from __future__ import annotations

import csv
import json
import random
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
RNG = random.Random(1776)

# ---------------------------------------------------------------------------
# 30 named CONUS hubs (Marine logistics relevant)
#   kind ∈ {"mclb","poe","rail_term","intermodal","river_port","airport"}
#   ccdr ∈ {"USMARFORCOM","USMARFORPAC","CENTCOM","NORTHCOM"}
# ---------------------------------------------------------------------------
NODES: list[dict] = [
    # Marine Corps Logistics Bases (origins)
    {"id": "MCLB-ALB", "name": "MCLB Albany",          "kind": "mclb",       "state": "GA", "lat": 31.547, "lon": -84.062, "throughput_tpd": 4200, "ccdr": "USMARFORCOM"},
    {"id": "MCLB-BAR", "name": "MCLB Barstow",         "kind": "mclb",       "state": "CA", "lat": 34.907, "lon": -117.039,"throughput_tpd": 3800, "ccdr": "USMARFORPAC"},
    {"id": "BIC-JAX",  "name": "Blount Island Cmd",    "kind": "mclb",       "state": "FL", "lat": 30.394, "lon": -81.520, "throughput_tpd": 5100, "ccdr": "USMARFORCOM"},
    {"id": "MCB-LEJ",  "name": "MCB Camp Lejeune",     "kind": "mclb",       "state": "NC", "lat": 34.689, "lon": -77.341, "throughput_tpd": 2900, "ccdr": "USMARFORCOM"},
    {"id": "MCB-PEN",  "name": "MCB Camp Pendleton",   "kind": "mclb",       "state": "CA", "lat": 33.391, "lon": -117.532,"throughput_tpd": 3300, "ccdr": "USMARFORPAC"},
    {"id": "29P",      "name": "MCAGCC 29 Palms",      "kind": "mclb",       "state": "CA", "lat": 34.232, "lon": -116.062,"throughput_tpd": 1700, "ccdr": "USMARFORPAC"},

    # Strategic Ports of Embarkation (POEs)
    {"id": "POE-BMT",  "name": "Port of Beaumont",     "kind": "poe",        "state": "TX", "lat": 30.080, "lon": -94.103, "throughput_tpd": 9200, "ccdr": "CENTCOM"},
    {"id": "POE-CHS",  "name": "Port of Charleston",   "kind": "poe",        "state": "SC", "lat": 32.781, "lon": -79.929, "throughput_tpd": 8600, "ccdr": "USMARFORCOM"},
    {"id": "POE-HRO",  "name": "Port of Hampton Roads","kind": "poe",        "state": "VA", "lat": 36.946, "lon": -76.330, "throughput_tpd": 9800, "ccdr": "USMARFORCOM"},
    {"id": "POE-LGB",  "name": "Port of Long Beach",   "kind": "poe",        "state": "CA", "lat": 33.754, "lon": -118.216,"throughput_tpd": 9500, "ccdr": "USMARFORPAC"},
    {"id": "POE-OAK",  "name": "Port of Oakland",      "kind": "poe",        "state": "CA", "lat": 37.795, "lon": -122.279,"throughput_tpd": 7400, "ccdr": "USMARFORPAC"},
    {"id": "POE-JAX",  "name": "Port of Jacksonville", "kind": "poe",        "state": "FL", "lat": 30.394, "lon": -81.620, "throughput_tpd": 7100, "ccdr": "USMARFORCOM"},
    {"id": "POE-SAV",  "name": "Port of Savannah",     "kind": "poe",        "state": "GA", "lat": 32.130, "lon": -81.144, "throughput_tpd": 8800, "ccdr": "USMARFORCOM"},
    {"id": "POE-TAC",  "name": "Port of Tacoma",       "kind": "poe",        "state": "WA", "lat": 47.272, "lon": -122.418,"throughput_tpd": 6800, "ccdr": "USMARFORPAC"},
    {"id": "POE-COR",  "name": "Port of Corpus Christi","kind":"poe",        "state": "TX", "lat": 27.812, "lon": -97.396, "throughput_tpd": 6400, "ccdr": "CENTCOM"},

    # Rail terminals / Class-I intermodal hubs
    {"id": "RT-ATL",   "name": "Atlanta Inman Yard",   "kind": "rail_term",  "state": "GA", "lat": 33.789, "lon": -84.434, "throughput_tpd": 5500, "ccdr": "USMARFORCOM"},
    {"id": "RT-MEM",   "name": "Memphis BNSF Yard",    "kind": "rail_term",  "state": "TN", "lat": 35.116, "lon": -90.054, "throughput_tpd": 6200, "ccdr": "USMARFORCOM"},
    {"id": "RT-DAL",   "name": "Dallas UP Mesquite",   "kind": "rail_term",  "state": "TX", "lat": 32.762, "lon": -96.616, "throughput_tpd": 5800, "ccdr": "CENTCOM"},
    {"id": "RT-KCK",   "name": "Kansas City KCS",      "kind": "rail_term",  "state": "KS", "lat": 39.114, "lon": -94.628, "throughput_tpd": 7100, "ccdr": "NORTHCOM"},
    {"id": "RT-CHI",   "name": "Chicago Corwith",      "kind": "rail_term",  "state": "IL", "lat": 41.831, "lon": -87.722, "throughput_tpd": 8400, "ccdr": "NORTHCOM"},
    {"id": "RT-LAX",   "name": "ICTF Los Angeles",     "kind": "intermodal", "state": "CA", "lat": 33.832, "lon": -118.221,"throughput_tpd": 6900, "ccdr": "USMARFORPAC"},
    {"id": "RT-NOR",   "name": "Norfolk Lambert's Pt", "kind": "rail_term",  "state": "VA", "lat": 36.876, "lon": -76.323, "throughput_tpd": 4700, "ccdr": "USMARFORCOM"},

    # Inland river ports (waterway leg)
    {"id": "RP-MEM",   "name": "Port of Memphis",      "kind": "river_port", "state": "TN", "lat": 35.131, "lon": -90.075, "throughput_tpd": 3200, "ccdr": "USMARFORCOM"},
    {"id": "RP-NOL",   "name": "Port NOLA",            "kind": "river_port", "state": "LA", "lat": 29.946, "lon": -90.064, "throughput_tpd": 5400, "ccdr": "CENTCOM"},
    {"id": "RP-STL",   "name": "Port of St Louis",     "kind": "river_port", "state": "MO", "lat": 38.625, "lon": -90.184, "throughput_tpd": 2900, "ccdr": "NORTHCOM"},
    {"id": "RP-LCH",   "name": "Port of Lake Charles", "kind": "river_port", "state": "LA", "lat": 30.227, "lon": -93.218, "throughput_tpd": 3100, "ccdr": "CENTCOM"},

    # Strategic airports (air leg / outsize cargo)
    {"id": "AP-DOV",   "name": "Dover AFB",            "kind": "airport",    "state": "DE", "lat": 39.130, "lon": -75.466, "throughput_tpd": 1600, "ccdr": "USMARFORCOM"},
    {"id": "AP-CHS",   "name": "JB Charleston",        "kind": "airport",    "state": "SC", "lat": 32.899, "lon": -80.041, "throughput_tpd": 1800, "ccdr": "USMARFORCOM"},
    {"id": "AP-TRA",   "name": "Travis AFB",           "kind": "airport",    "state": "CA", "lat": 38.263, "lon": -121.927,"throughput_tpd": 1900, "ccdr": "USMARFORPAC"},
    {"id": "AP-MAR",   "name": "March ARB",            "kind": "airport",    "state": "CA", "lat": 33.881, "lon": -117.259,"throughput_tpd": 1100, "ccdr": "USMARFORPAC"},
]

# ---------------------------------------------------------------------------
# Typed edges. Each edge has:
#   mode ∈ {road, rail, waterway, air}
#   miles
#   capacity_tpd     - design daily throughput in short-tons
#   clearance_in     - minimum vertical clearance (in)  (relevant for rail, road bridges)
#   weight_limit_lbs - lowest weight class on the corridor (HS-20 ≈ 80,000 lb gross)
#   bottleneck_named - human-friendly named choke-point on the leg ("" if clean)
# ---------------------------------------------------------------------------
EDGES: list[dict] = [
    # ---- ROAD edges (interstate / DOD STRAHNET) ----
    {"a": "MCLB-ALB", "b": "POE-JAX",  "mode": "road",     "miles": 240,  "capacity_tpd": 3200, "clearance_in": 192, "weight_limit_lbs": 80000,  "bottleneck_named": ""},
    {"a": "MCLB-ALB", "b": "POE-SAV",  "mode": "road",     "miles": 230,  "capacity_tpd": 3400, "clearance_in": 198, "weight_limit_lbs": 88000,  "bottleneck_named": ""},
    {"a": "MCLB-ALB", "b": "POE-CHS",  "mode": "road",     "miles": 360,  "capacity_tpd": 2900, "clearance_in": 186, "weight_limit_lbs": 80000,  "bottleneck_named": "I-95 Charleston Connector"},
    {"a": "MCLB-ALB", "b": "POE-BMT",  "mode": "road",     "miles": 770,  "capacity_tpd": 2200, "clearance_in": 168, "weight_limit_lbs": 70000,  "bottleneck_named": "I-10 Lake Charles bridge"},
    {"a": "MCLB-ALB", "b": "POE-HRO",  "mode": "road",     "miles": 700,  "capacity_tpd": 2400, "clearance_in": 192, "weight_limit_lbs": 80000,  "bottleneck_named": ""},
    {"a": "BIC-JAX",  "b": "POE-JAX",  "mode": "road",     "miles": 12,   "capacity_tpd": 6100, "clearance_in": 198, "weight_limit_lbs": 96000,  "bottleneck_named": ""},
    {"a": "MCB-LEJ",  "b": "POE-HRO",  "mode": "road",     "miles": 215,  "capacity_tpd": 2700, "clearance_in": 192, "weight_limit_lbs": 80000,  "bottleneck_named": ""},
    {"a": "MCB-LEJ",  "b": "POE-CHS",  "mode": "road",     "miles": 285,  "capacity_tpd": 2500, "clearance_in": 186, "weight_limit_lbs": 80000,  "bottleneck_named": ""},
    {"a": "MCB-PEN",  "b": "POE-LGB",  "mode": "road",     "miles": 75,   "capacity_tpd": 5200, "clearance_in": 198, "weight_limit_lbs": 88000,  "bottleneck_named": ""},
    {"a": "MCLB-BAR", "b": "POE-LGB",  "mode": "road",     "miles": 145,  "capacity_tpd": 4100, "clearance_in": 192, "weight_limit_lbs": 80000,  "bottleneck_named": "I-15 Cajon Pass grade"},
    {"a": "MCLB-BAR", "b": "RT-LAX",   "mode": "road",     "miles": 150,  "capacity_tpd": 4400, "clearance_in": 192, "weight_limit_lbs": 80000,  "bottleneck_named": ""},
    {"a": "29P",      "b": "MCB-PEN",  "mode": "road",     "miles": 130,  "capacity_tpd": 2600, "clearance_in": 186, "weight_limit_lbs": 80000,  "bottleneck_named": ""},
    {"a": "29P",      "b": "AP-MAR",   "mode": "road",     "miles": 90,   "capacity_tpd": 2400, "clearance_in": 186, "weight_limit_lbs": 80000,  "bottleneck_named": ""},
    {"a": "MCLB-ALB", "b": "POE-COR",  "mode": "road",     "miles": 1090, "capacity_tpd": 1900, "clearance_in": 174, "weight_limit_lbs": 72000,  "bottleneck_named": "I-10 Atchafalaya Basin trestle"},
    {"a": "RT-DAL",   "b": "POE-BMT",  "mode": "road",     "miles": 280,  "capacity_tpd": 3500, "clearance_in": 192, "weight_limit_lbs": 88000,  "bottleneck_named": ""},
    {"a": "RT-MEM",   "b": "POE-BMT",  "mode": "road",     "miles": 580,  "capacity_tpd": 2700, "clearance_in": 186, "weight_limit_lbs": 80000,  "bottleneck_named": ""},
    {"a": "RT-NOR",   "b": "POE-HRO",  "mode": "road",     "miles": 22,   "capacity_tpd": 5800, "clearance_in": 198, "weight_limit_lbs": 96000,  "bottleneck_named": ""},

    # ---- RAIL edges (Class-I corridors; DOD-STRACNET-style) ----
    {"a": "MCLB-ALB", "b": "RT-ATL",   "mode": "rail",     "miles": 175,  "capacity_tpd": 5400, "clearance_in": 240, "weight_limit_lbs": 286000, "bottleneck_named": ""},
    {"a": "RT-ATL",   "b": "RT-MEM",   "mode": "rail",     "miles": 395,  "capacity_tpd": 6800, "clearance_in": 245, "weight_limit_lbs": 286000, "bottleneck_named": ""},
    {"a": "RT-MEM",   "b": "RT-DAL",   "mode": "rail",     "miles": 470,  "capacity_tpd": 7100, "clearance_in": 240, "weight_limit_lbs": 286000, "bottleneck_named": ""},
    {"a": "RT-DAL",   "b": "POE-BMT",  "mode": "rail",     "miles": 290,  "capacity_tpd": 6400, "clearance_in": 234, "weight_limit_lbs": 286000, "bottleneck_named": "Devers Sub single-track"},
    {"a": "RT-MEM",   "b": "RT-KCK",   "mode": "rail",     "miles": 510,  "capacity_tpd": 7300, "clearance_in": 245, "weight_limit_lbs": 286000, "bottleneck_named": ""},
    {"a": "RT-KCK",   "b": "RT-CHI",   "mode": "rail",     "miles": 510,  "capacity_tpd": 8100, "clearance_in": 245, "weight_limit_lbs": 286000, "bottleneck_named": ""},
    {"a": "RT-CHI",   "b": "RT-NOR",   "mode": "rail",     "miles": 870,  "capacity_tpd": 6700, "clearance_in": 240, "weight_limit_lbs": 286000, "bottleneck_named": "Horseshoe Curve gradient"},
    {"a": "RT-NOR",   "b": "POE-HRO",  "mode": "rail",     "miles": 25,   "capacity_tpd": 5200, "clearance_in": 240, "weight_limit_lbs": 286000, "bottleneck_named": ""},
    {"a": "RT-ATL",   "b": "POE-SAV",  "mode": "rail",     "miles": 250,  "capacity_tpd": 6300, "clearance_in": 240, "weight_limit_lbs": 286000, "bottleneck_named": ""},
    {"a": "RT-ATL",   "b": "POE-CHS",  "mode": "rail",     "miles": 300,  "capacity_tpd": 5800, "clearance_in": 240, "weight_limit_lbs": 286000, "bottleneck_named": ""},
    {"a": "RT-LAX",   "b": "POE-LGB",  "mode": "rail",     "miles": 22,   "capacity_tpd": 7900, "clearance_in": 245, "weight_limit_lbs": 286000, "bottleneck_named": ""},
    {"a": "RT-LAX",   "b": "RT-DAL",   "mode": "rail",     "miles": 1430, "capacity_tpd": 5600, "clearance_in": 240, "weight_limit_lbs": 286000, "bottleneck_named": "Sunset Route Tehachapi"},
    {"a": "MCLB-BAR", "b": "RT-LAX",   "mode": "rail",     "miles": 130,  "capacity_tpd": 6200, "clearance_in": 240, "weight_limit_lbs": 286000, "bottleneck_named": ""},
    {"a": "RT-CHI",   "b": "POE-TAC",  "mode": "rail",     "miles": 2070, "capacity_tpd": 5100, "clearance_in": 240, "weight_limit_lbs": 286000, "bottleneck_named": "Stampede Pass clearance"},
    {"a": "MCB-PEN",  "b": "RT-LAX",   "mode": "rail",     "miles": 90,   "capacity_tpd": 4800, "clearance_in": 240, "weight_limit_lbs": 286000, "bottleneck_named": ""},

    # ---- WATERWAY edges (inland barge / coastal) ----
    {"a": "RP-MEM",   "b": "RP-NOL",   "mode": "waterway", "miles": 695,  "capacity_tpd": 9800, "clearance_in": 0,   "weight_limit_lbs": 0,      "bottleneck_named": "Old River Control Structure"},
    {"a": "RP-STL",   "b": "RP-MEM",   "mode": "waterway", "miles": 480,  "capacity_tpd": 8400, "clearance_in": 0,   "weight_limit_lbs": 0,      "bottleneck_named": ""},
    {"a": "RP-NOL",   "b": "POE-COR",  "mode": "waterway", "miles": 460,  "capacity_tpd": 7600, "clearance_in": 0,   "weight_limit_lbs": 0,      "bottleneck_named": "GIWW Houma lock queue"},
    {"a": "RP-NOL",   "b": "RP-LCH",   "mode": "waterway", "miles": 230,  "capacity_tpd": 6900, "clearance_in": 0,   "weight_limit_lbs": 0,      "bottleneck_named": ""},
    {"a": "RP-LCH",   "b": "POE-BMT",  "mode": "waterway", "miles": 30,   "capacity_tpd": 7400, "clearance_in": 0,   "weight_limit_lbs": 0,      "bottleneck_named": "Sabine-Neches Waterway draft"},

    # ---- AIR edges (outsize / time-critical) ----
    {"a": "AP-DOV",   "b": "POE-HRO",  "mode": "air",      "miles": 175,  "capacity_tpd": 850,  "clearance_in": 0,   "weight_limit_lbs": 290000, "bottleneck_named": ""},
    {"a": "AP-CHS",   "b": "POE-CHS",  "mode": "air",      "miles": 12,   "capacity_tpd": 1200, "clearance_in": 0,   "weight_limit_lbs": 290000, "bottleneck_named": ""},
    {"a": "AP-TRA",   "b": "POE-OAK",  "mode": "air",      "miles": 55,   "capacity_tpd": 1100, "clearance_in": 0,   "weight_limit_lbs": 290000, "bottleneck_named": ""},
    {"a": "AP-MAR",   "b": "POE-LGB",  "mode": "air",      "miles": 65,   "capacity_tpd": 950,  "clearance_in": 0,   "weight_limit_lbs": 290000, "bottleneck_named": ""},
    {"a": "AP-DOV",   "b": "AP-CHS",   "mode": "air",      "miles": 540,  "capacity_tpd": 800,  "clearance_in": 0,   "weight_limit_lbs": 290000, "bottleneck_named": ""},
    {"a": "AP-TRA",   "b": "AP-MAR",   "mode": "air",      "miles": 380,  "capacity_tpd": 850,  "clearance_in": 0,   "weight_limit_lbs": 290000, "bottleneck_named": ""},
]

# ---------------------------------------------------------------------------
# 10 USMC end-items with movement constraints
# (dimensions and weights are realistic published figures for the platform)
# ---------------------------------------------------------------------------
END_ITEMS: list[dict] = [
    {"id": "M1A1",   "name": "M1A1 Abrams Main Battle Tank", "weight_lbs": 138000, "length_in": 388, "width_in": 144, "height_in": 114, "category": "armor",       "permit_required": True,  "rail_compatible": True,  "air_compatible_c17": False, "notes": "Outsize: requires special permit road moves; HET on STRAHNET; rail-shippable on heavy flatcar; C-5 only for air."},
    {"id": "AAV",    "name": "AAV-7A1 Amphibious Assault Vehicle", "weight_lbs": 56000, "length_in": 312, "width_in": 128, "height_in": 130, "category": "amphib",       "permit_required": False, "rail_compatible": True,  "air_compatible_c17": True,  "notes": "Standard road-legal with HET; rail-clearance plate F."},
    {"id": "LAV-25", "name": "LAV-25 Light Armored Vehicle",  "weight_lbs": 28200, "length_in": 252, "width_in": 98,  "height_in": 106, "category": "wheeled-armor","permit_required": False, "rail_compatible": True,  "air_compatible_c17": True,  "notes": "Self-deployable on highway; C-130 transportable."},
    {"id": "JLTV",   "name": "Joint Light Tactical Vehicle",  "weight_lbs": 14000, "length_in": 246, "width_in": 98,  "height_in": 102, "category": "wheeled",      "permit_required": False, "rail_compatible": True,  "air_compatible_c17": True,  "notes": "Highway-legal; multiple per C-17."},
    {"id": "MTVR",   "name": "MTVR 7-ton Truck",              "weight_lbs": 26000, "length_in": 348, "width_in": 96,  "height_in": 110, "category": "wheeled",      "permit_required": False, "rail_compatible": True,  "air_compatible_c17": True,  "notes": "Standard MAGTF prime mover."},
    {"id": "HIMARS", "name": "M142 HIMARS Launcher",          "weight_lbs": 36000, "length_in": 280, "width_in": 96,  "height_in": 130, "category": "wheeled-armor","permit_required": False, "rail_compatible": True,  "air_compatible_c17": True,  "notes": "C-130 / C-17 air-deployable; STRAHNET road OK."},
    {"id": "M777",   "name": "M777 155mm Howitzer + prime mover", "weight_lbs": 21000, "length_in": 420, "width_in": 110, "height_in": 100, "category": "towed",   "permit_required": False, "rail_compatible": True,  "air_compatible_c17": True,  "notes": "Slung under MV-22 / CH-53; road-towable."},
    {"id": "MV-22",  "name": "MV-22B Osprey (rotors folded)",  "weight_lbs": 33000, "length_in": 768, "width_in": 220, "height_in": 222, "category": "aircraft",     "permit_required": True,  "rail_compatible": False, "air_compatible_c17": True,  "notes": "Self-deploys; ground move requires de-rotor disassembly."},
    {"id": "F-35B",  "name": "F-35B Lightning II",            "weight_lbs": 32500, "length_in": 624, "width_in": 420, "height_in": 174, "category": "aircraft",     "permit_required": True,  "rail_compatible": False, "air_compatible_c17": True,  "notes": "Self-deploys; ground move only on flat-bed in low-vis."},
    {"id": "CONEX",  "name": "ISO TRICON / 20-ft Container",  "weight_lbs": 52000, "length_in": 240, "width_in": 96,  "height_in": 96,  "category": "container",    "permit_required": False, "rail_compatible": True,  "air_compatible_c17": True,  "notes": "Standard intermodal; rail / sea / road / air all native."},
]


# ---------------------------------------------------------------------------
# Hero scenarios — pre-computed brief cache so the demo never waits
# ---------------------------------------------------------------------------
SCENARIOS: list[dict] = [
    {
        "id": "alb-bmt-m1a1",
        "origin_id": "MCLB-ALB",
        "destination_id": "POE-BMT",
        "end_item_id": "M1A1",
        "label": "MCLB Albany → Port of Beaumont · M1A1 Abrams (CENTCOM surge)",
    },
    {
        "id": "pen-lgb-aav",
        "origin_id": "MCB-PEN",
        "destination_id": "POE-LGB",
        "end_item_id": "AAV",
        "label": "Camp Pendleton → Port of Long Beach · AAV-7A1 (PACOM rotation)",
    },
    {
        "id": "lej-hro-himars",
        "origin_id": "MCB-LEJ",
        "destination_id": "POE-HRO",
        "end_item_id": "HIMARS",
        "label": "Camp Lejeune → Port of Hampton Roads · HIMARS battery",
    },
]


# ---------------------------------------------------------------------------
# Writers
# ---------------------------------------------------------------------------
def write_nodes() -> Path:
    p = ROOT / "nodes.json"
    p.write_text(json.dumps(NODES, indent=2))
    return p


def write_edges() -> Path:
    p = ROOT / "edges.csv"
    fields = ["a", "b", "mode", "miles", "capacity_tpd",
              "clearance_in", "weight_limit_lbs", "bottleneck_named"]
    with p.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for e in EDGES:
            w.writerow(e)
    return p


def write_end_items() -> Path:
    p = ROOT / "end_items.json"
    p.write_text(json.dumps(END_ITEMS, indent=2))
    return p


def _generate_data() -> None:
    print("HUB synth:", write_nodes())
    print("HUB synth:", write_edges())
    print("HUB synth:", write_end_items())


# ---------------------------------------------------------------------------
# Pre-compute cached briefs (cache-first hero pattern)
# ---------------------------------------------------------------------------
def _precompute_briefs() -> Path:
    """Run the hero pipeline once for each SCENARIO and persist results so the
    Streamlit demo never has to block on the LLM call.

    Falls back to a deterministic baseline brief if the LLM is unavailable.
    """
    import sys
    sys.path.insert(0, str(ROOT.parent.parent.parent))  # repo root
    sys.path.insert(0, str(ROOT.parent))                 # app root
    from src import agent  # noqa: E402

    briefs: dict[str, dict] = {}
    for sc in SCENARIOS:
        plan = agent.compute_corridor(sc["origin_id"], sc["destination_id"], sc["end_item_id"])
        try:
            json_brief = agent.hero_chat_json(plan)
        except Exception:
            json_brief = agent.baseline_chat_json(plan)
        try:
            text_brief = agent.hero_chat_narrative(plan, json_brief)
        except Exception:
            text_brief = agent.baseline_narrative(plan, json_brief)
        briefs[sc["id"]] = {
            "scenario": sc,
            "plan": plan,
            "json_brief": json_brief,
            "narrative": text_brief,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }

    p = ROOT / "cached_briefs.json"
    p.write_text(json.dumps(briefs, indent=2, default=str))
    print(f"HUB cache: {p} ({len(briefs)} scenarios)")
    return p


if __name__ == "__main__":
    _generate_data()
    try:
        _precompute_briefs()
    except Exception as e:  # noqa: BLE001
        print(f"HUB warn: precompute_briefs skipped — {e}")
