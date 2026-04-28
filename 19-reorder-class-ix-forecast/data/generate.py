"""REORDER synthetic data generator.

Produces:
  data/maintenance_history.csv  - 90 days of work-order records across MTVR/LAV/
                                   JLTV/M88A2/HMMWV with NSN consumed
  data/nsn_catalog.json          - ~36 FSC-coherent NSNs with realistic prices
  data/forward_nodes.json        - 5 expeditionary depots with on-hand stock
  data/scenarios.json            - 3 OPTEMPO/environment scenarios

Seeded with random.Random(1776) for reproducibility.

NSN catalog policy: every entry uses a Federal Supply Class (FSC, the first 4
digits of the NSN) that is coherent with the part name. Real FSC anchors used:

  2520 Power Transmission              2920 Engine Electrical Equipment
  2530 Vehicular Brake/Steering/Axle   2930 Engine Fuel System Components
  2540 Vehicular Furniture/Accessories 2940 Engine Air & Oil Filters
  2610 Tires & Tubes (pneumatic)       3110 Bearings, Antifriction
  2815 Diesel Engines                  5305 Screws
  2895 Misc Vehicular Components       5306 Bolts
  4720 Hose, Pipe, Tube                5965 Headsets, Handsets, Microphones
  5995 Cable, Cord & Wire Assys        6135 Batteries, Non-Rechargeable
  6140 Batteries, Rechargeable

Real-data swap: replace this with ingest of GCSS-MC work-order extracts
(see data/load_real.py for the exact required schema).
"""
from __future__ import annotations

import csv
import json
import random
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent

# ---------- Platforms (deployed MAGTF rolling stock) -------------------------

PLATFORMS = [
    {"id": "MTVR",  "name": "MTVR (Medium Tactical Vehicle Replacement)",
     "subsystems": ["engine", "transmission", "brakes", "electrical", "tires", "hydraulics"]},
    {"id": "LAV",   "name": "LAV-25 (Light Armored Vehicle)",
     "subsystems": ["engine", "transmission", "turret", "electrical", "wheels", "weapons"]},
    {"id": "JLTV",  "name": "JLTV (Joint Light Tactical Vehicle)",
     "subsystems": ["engine", "transmission", "suspension", "electrical", "armor", "tires"]},
    {"id": "M88A2", "name": "M88A2 HERCULES Recovery Vehicle",
     "subsystems": ["engine", "tracks", "winch", "boom", "hydraulics", "electrical"]},
    {"id": "HMMWV", "name": "HMMWV (M1151/M1152)",
     "subsystems": ["engine", "transmission", "brakes", "electrical", "tires", "suspension"]},
]

# Environmental modifiers — multiplicative on baseline part-failure rate by subsystem.
ENV_MODIFIERS = {
    "desert":   {"engine": 1.6, "tires": 2.1, "hydraulics": 1.3, "electrical": 1.2,
                 "brakes": 1.0, "turret": 1.1, "wheels": 1.4, "weapons": 1.2,
                 "tracks": 1.3, "suspension": 1.2, "transmission": 1.2,
                 "armor": 1.0, "winch": 1.0, "boom": 1.0, "comms": 1.0,
                 "fasteners": 1.0},
    "jungle":   {"engine": 1.2, "tires": 1.1, "hydraulics": 1.5, "electrical": 1.7,
                 "brakes": 1.3, "turret": 1.2, "wheels": 1.0, "weapons": 1.3,
                 "tracks": 1.4, "suspension": 1.5, "transmission": 1.2,
                 "armor": 1.1, "winch": 1.4, "boom": 1.2, "comms": 1.6,
                 "fasteners": 1.1},
    "maritime": {"engine": 1.1, "tires": 1.0, "hydraulics": 1.2, "electrical": 2.0,
                 "brakes": 1.4, "turret": 1.3, "wheels": 1.1, "weapons": 1.5,
                 "tracks": 1.0, "suspension": 1.0, "transmission": 1.1,
                 "armor": 1.6, "winch": 1.5, "boom": 1.4, "comms": 1.8,
                 "fasteners": 1.3},
    "cold":     {"engine": 1.4, "tires": 1.1, "hydraulics": 1.6, "electrical": 1.3,
                 "brakes": 1.5, "turret": 1.0, "wheels": 1.2, "weapons": 1.3,
                 "tracks": 1.4, "suspension": 1.3, "transmission": 1.5,
                 "armor": 1.0, "winch": 1.2, "boom": 1.3, "comms": 1.2,
                 "fasteners": 1.0},
}

# OPTEMPO scaling — multiplicative on the base daily consumption rate per platform.
OPTEMPO_SCALE = {"low": 0.55, "medium": 1.0, "high": 1.85}

# MAGTF size scaling — number of vehicles of each platform deployed.
# (Order-of-magnitude sketches; not authoritative.)
MAGTF_FLEETS = {
    "MEU": {"MTVR":  60, "LAV":  25, "JLTV":  85, "M88A2":  4, "HMMWV":  90},
    "MEB": {"MTVR": 320, "LAV":  90, "JLTV": 410, "M88A2": 16, "HMMWV": 380},
    "MEF": {"MTVR":1100, "LAV": 320, "JLTV":1300, "M88A2": 55, "HMMWV":1200},
}

# 5 forward / pre-positioning nodes (lat/lon for the map).
FORWARD_NODES = [
    {"id": "MCLB-PEN",  "name": "MCLB Pendleton",         "kind": "CONUS depot",
     "lat": 33.387, "lon": -117.566, "tier": "primary"},
    {"id": "MCLB-ALB",  "name": "MCLB Albany",            "kind": "CONUS depot",
     "lat": 31.547, "lon": -84.063, "tier": "primary"},
    {"id": "BLOUNT",    "name": "Blount Island Command",  "kind": "MPF support",
     "lat": 30.397, "lon": -81.516, "tier": "primary"},
    {"id": "OKI-FWD",   "name": "Okinawa Forward Node",   "kind": "Forward depot",
     "lat": 26.355, "lon": 127.768, "tier": "forward"},
    {"id": "GUAM-FWD",  "name": "Apra Harbor Forward",    "kind": "Forward depot",
     "lat": 13.443, "lon": 144.660, "tier": "forward"},
]


# ---------- Curated FSC-coherent NSN catalog --------------------------------
#
# Each entry: nsn, part_name, primary_platform, subsystem,
#             base_daily_per_vehicle, unit_price_usd.
#
# NSNs use the "01" country code (US) and a stable NIIN that is identifiable as
# REORDER demo data. Where a real DLA NIIN is widely published in open sources
# (e.g. wheel-bearing 3110-01-413-2691, MTVR-class tire NIINs in FSC 2610) we
# use it; remaining NIINs are assigned within the correct FSC. The first four
# digits (the FSC) ALWAYS match the part name's federal supply class, which is
# the defect that the audit flagged.
#
# Pricing is grounded in published FedMall / DLA price-band ranges for the
# part class — no more $45 starter motors or $18,500 valve stems.

NSN_CATALOG: list[dict] = [
    # ---- 2610 Tires & Tubes, Pneumatic --------------------------------------
    {"nsn": "2610-01-541-1929", "part_name": "radial tire 37x12.5R16.5 (HMMWV)",
     "primary_platform": "HMMWV", "subsystem": "tires",
     "base_daily_per_vehicle": 0.0034, "unit_price_usd": 295},
    {"nsn": "2610-01-561-7748", "part_name": "radial tire 395/85R20 (MTVR)",
     "primary_platform": "MTVR", "subsystem": "tires",
     "base_daily_per_vehicle": 0.0028, "unit_price_usd": 690},
    {"nsn": "2610-01-647-5106", "part_name": "run-flat radial tire 37x12.5R17 (JLTV)",
     "primary_platform": "JLTV", "subsystem": "tires",
     "base_daily_per_vehicle": 0.0026, "unit_price_usd": 540},
    {"nsn": "2610-01-388-2086", "part_name": "tire 12.00R20 (LAV-25 wheels)",
     "primary_platform": "LAV", "subsystem": "wheels",
     "base_daily_per_vehicle": 0.0022, "unit_price_usd": 720},
    {"nsn": "2610-01-330-4488", "part_name": "tire valve stem assembly (MTVR)",
     "primary_platform": "MTVR", "subsystem": "tires",
     "base_daily_per_vehicle": 0.0090, "unit_price_usd": 9},

    # ---- 2530 Vehicular Brake / Steering / Axle / Wheel ---------------------
    {"nsn": "2530-01-466-0822", "part_name": "brake pad set (HMMWV front)",
     "primary_platform": "HMMWV", "subsystem": "brakes",
     "base_daily_per_vehicle": 0.0061, "unit_price_usd": 78},
    {"nsn": "2530-01-621-3107", "part_name": "brake rotor (MTVR)",
     "primary_platform": "MTVR", "subsystem": "brakes",
     "base_daily_per_vehicle": 0.0019, "unit_price_usd": 215},
    {"nsn": "2530-01-487-5511", "part_name": "hydraulic brake caliper (JLTV)",
     "primary_platform": "JLTV", "subsystem": "brakes",
     "base_daily_per_vehicle": 0.0014, "unit_price_usd": 320},
    {"nsn": "2530-01-356-7711", "part_name": "power steering pump (MTVR)",
     "primary_platform": "MTVR", "subsystem": "brakes",
     "base_daily_per_vehicle": 0.0009, "unit_price_usd": 1180},
    {"nsn": "2530-01-577-9919", "part_name": "tie-rod end assembly (JLTV)",
     "primary_platform": "JLTV", "subsystem": "suspension",
     "base_daily_per_vehicle": 0.0021, "unit_price_usd": 95},

    # ---- 2920 Engine Electrical Equipment, Non-Aircraft ---------------------
    {"nsn": "2920-01-446-5219", "part_name": "alternator 200A 28V (MTVR)",
     "primary_platform": "MTVR", "subsystem": "electrical",
     "base_daily_per_vehicle": 0.0017, "unit_price_usd": 410},
    {"nsn": "2920-01-396-9234", "part_name": "starter motor 24V (HMMWV)",
     "primary_platform": "HMMWV", "subsystem": "engine",
     "base_daily_per_vehicle": 0.0013, "unit_price_usd": 605},
    {"nsn": "2920-01-432-7789", "part_name": "ignition coil pack (JLTV)",
     "primary_platform": "JLTV", "subsystem": "electrical",
     "base_daily_per_vehicle": 0.0024, "unit_price_usd": 145},
    {"nsn": "2920-01-540-1188", "part_name": "voltage regulator 28V (LAV)",
     "primary_platform": "LAV", "subsystem": "electrical",
     "base_daily_per_vehicle": 0.0016, "unit_price_usd": 220},
    {"nsn": "2920-01-512-6677", "part_name": "ECM engine control module (HMMWV)",
     "primary_platform": "HMMWV", "subsystem": "electrical",
     "base_daily_per_vehicle": 0.0007, "unit_price_usd": 1850},

    # ---- 2940 Engine Air & Oil Filters --------------------------------------
    {"nsn": "2940-01-389-2196", "part_name": "primary fuel/oil filter element (MTVR)",
     "primary_platform": "MTVR", "subsystem": "engine",
     "base_daily_per_vehicle": 0.0095, "unit_price_usd": 24},
    {"nsn": "2940-01-413-1984", "part_name": "engine air filter element (HMMWV)",
     "primary_platform": "HMMWV", "subsystem": "engine",
     "base_daily_per_vehicle": 0.0082, "unit_price_usd": 58},
    {"nsn": "2940-01-510-2207", "part_name": "transmission oil filter (JLTV)",
     "primary_platform": "JLTV", "subsystem": "transmission",
     "base_daily_per_vehicle": 0.0048, "unit_price_usd": 36},

    # ---- 2930 Engine Fuel System Components ---------------------------------
    {"nsn": "2930-01-477-0631", "part_name": "fuel filter / water separator (MTVR)",
     "primary_platform": "MTVR", "subsystem": "engine",
     "base_daily_per_vehicle": 0.0070, "unit_price_usd": 47},
    {"nsn": "2930-01-329-9842", "part_name": "fuel injector (HMMWV 6.5L)",
     "primary_platform": "HMMWV", "subsystem": "engine",
     "base_daily_per_vehicle": 0.0033, "unit_price_usd": 305},
    {"nsn": "2930-01-552-4104", "part_name": "electric fuel pump assembly (JLTV)",
     "primary_platform": "JLTV", "subsystem": "engine",
     "base_daily_per_vehicle": 0.0014, "unit_price_usd": 480},
    {"nsn": "2930-01-296-1144", "part_name": "engine water pump (LAV)",
     "primary_platform": "LAV", "subsystem": "engine",
     "base_daily_per_vehicle": 0.0011, "unit_price_usd": 360},

    # ---- 2520 Power Transmission --------------------------------------------
    {"nsn": "2520-01-449-2287", "part_name": "transfer case assembly (HMMWV)",
     "primary_platform": "HMMWV", "subsystem": "transmission",
     "base_daily_per_vehicle": 0.00045, "unit_price_usd": 3450},
    {"nsn": "2520-01-365-7104", "part_name": "drive shaft U-joint (MTVR)",
     "primary_platform": "MTVR", "subsystem": "transmission",
     "base_daily_per_vehicle": 0.0033, "unit_price_usd": 175},
    {"nsn": "2520-01-528-3166", "part_name": "torque converter (JLTV)",
     "primary_platform": "JLTV", "subsystem": "transmission",
     "base_daily_per_vehicle": 0.00055, "unit_price_usd": 2900},

    # ---- 2540 Vehicular Furniture / Accessories -----------------------------
    {"nsn": "2540-01-565-2210", "part_name": "ballistic glass window panel (JLTV)",
     "primary_platform": "JLTV", "subsystem": "armor",
     "base_daily_per_vehicle": 0.00060, "unit_price_usd": 2400},
    {"nsn": "2540-01-491-7728", "part_name": "underbody armor plate (HMMWV)",
     "primary_platform": "HMMWV", "subsystem": "armor",
     "base_daily_per_vehicle": 0.00048, "unit_price_usd": 1850},

    # ---- 3110 Bearings, Antifriction ----------------------------------------
    {"nsn": "3110-01-413-2691", "part_name": "wheel bearing assembly (HMMWV)",
     "primary_platform": "HMMWV", "subsystem": "tires",
     "base_daily_per_vehicle": 0.0042, "unit_price_usd": 82},
    {"nsn": "3110-01-587-2018", "part_name": "wheel bearing race (LAV)",
     "primary_platform": "LAV", "subsystem": "wheels",
     "base_daily_per_vehicle": 0.0024, "unit_price_usd": 110},

    # ---- 4720 Hose, Pipe, Tube ----------------------------------------------
    {"nsn": "4720-01-471-9951", "part_name": "high-pressure hydraulic hose 1/2 in. (M88A2)",
     "primary_platform": "M88A2", "subsystem": "hydraulics",
     "base_daily_per_vehicle": 0.0061, "unit_price_usd": 95},
    {"nsn": "4720-01-329-4512", "part_name": "coolant hose (MTVR engine)",
     "primary_platform": "MTVR", "subsystem": "engine",
     "base_daily_per_vehicle": 0.0044, "unit_price_usd": 38},

    # ---- 2815 Diesel Engines / 2895 Misc Vehicular --------------------------
    {"nsn": "2895-01-462-3318", "part_name": "winch cable assembly 200ft (M88A2)",
     "primary_platform": "M88A2", "subsystem": "winch",
     "base_daily_per_vehicle": 0.0029, "unit_price_usd": 410},
    {"nsn": "2815-01-377-2184", "part_name": "cylinder head gasket (HMMWV 6.5L)",
     "primary_platform": "HMMWV", "subsystem": "engine",
     "base_daily_per_vehicle": 0.00072, "unit_price_usd": 220},

    # ---- 5305 Screws / 5306 Bolts -------------------------------------------
    {"nsn": "5305-01-188-1057", "part_name": "machine screw, hex-head 3/8-16 (general)",
     "primary_platform": "MTVR", "subsystem": "fasteners",
     "base_daily_per_vehicle": 0.022, "unit_price_usd": 2},
    {"nsn": "5306-01-204-9033", "part_name": "structural bolt 1/2-13 grade-8 (general)",
     "primary_platform": "JLTV", "subsystem": "fasteners",
     "base_daily_per_vehicle": 0.018, "unit_price_usd": 3},

    # ---- 6135 Batteries, Non-Rechargeable -----------------------------------
    {"nsn": "6135-01-301-8776", "part_name": "BA-5590 lithium primary battery (radio)",
     "primary_platform": "JLTV", "subsystem": "comms",
     "base_daily_per_vehicle": 0.012, "unit_price_usd": 26},

    # ---- 6140 Batteries, Rechargeable ---------------------------------------
    {"nsn": "6140-01-446-9512", "part_name": "vehicle battery 6TL 12V (HMMWV/MTVR)",
     "primary_platform": "MTVR", "subsystem": "electrical",
     "base_daily_per_vehicle": 0.0024, "unit_price_usd": 138},
    {"nsn": "6140-01-490-4316", "part_name": "BB-2590/U rechargeable Li-ion battery",
     "primary_platform": "JLTV", "subsystem": "comms",
     "base_daily_per_vehicle": 0.0072, "unit_price_usd": 305},

    # ---- 5995 Cable Assemblies, Coaxial -------------------------------------
    {"nsn": "5995-01-538-7726", "part_name": "RF coaxial cable assembly, vehicle SINCGARS",
     "primary_platform": "LAV", "subsystem": "comms",
     "base_daily_per_vehicle": 0.0036, "unit_price_usd": 84},

    # ---- 5965 Headphones / Microphones --------------------------------------
    {"nsn": "5965-01-411-7783", "part_name": "intercom headset H-250/U",
     "primary_platform": "LAV", "subsystem": "comms",
     "base_daily_per_vehicle": 0.0058, "unit_price_usd": 165},
]


def build_nsn_catalog(rng: random.Random | None = None) -> list[dict]:
    """Return the curated FSC-coherent NSN catalog.

    `rng` is accepted for API compatibility with the prior random generator
    but is unused — the catalog is fully static so an NSN's part name and
    unit price are CONSISTENT across all nodes and runs.
    """
    return [dict(c) for c in NSN_CATALOG]


def synth_maintenance_history(
    catalog: list[dict],
    *,
    days: int = 90,
    magtf_size: str = "MEB",
    optempo: str = "medium",
    environment: str = "desert",
    rng: random.Random | None = None,
) -> list[dict]:
    """Generate work-order records over `days` days of operations.

    Each record:
      date, work_order_id, platform, vehicle_id, environment, optempo,
      magtf_size, nsn, part_name, qty_consumed, subsystem
    """
    rng = rng or random.Random(1776)
    fleet = MAGTF_FLEETS[magtf_size]
    optempo_mult = OPTEMPO_SCALE[optempo]
    env_table = ENV_MODIFIERS[environment]

    # Index catalog by primary_platform for fast lookup.
    by_plat: dict[str, list[dict]] = {}
    for c in catalog:
        by_plat.setdefault(c["primary_platform"], []).append(c)

    base_date = datetime(2026, 1, 26)  # 90 days back from 2026-04-26 demo date
    records: list[dict] = []
    wo_seq = 0
    for day in range(days):
        day_date = base_date + timedelta(days=day)
        # Add a weekly OPTEMPO ripple: +25% on Mon/Tue, -15% on weekend.
        dow = day_date.weekday()
        ripple = 1.25 if dow in (0, 1) else (0.85 if dow in (5, 6) else 1.0)

        for plat_id, fleet_size in fleet.items():
            plat_parts = by_plat.get(plat_id, [])
            if not plat_parts:
                continue
            for part in plat_parts:
                env_mult = env_table.get(part["subsystem"], 1.0)
                # Expected consumption today (Poisson-shaped via uniform rounding).
                lam = (
                    part["base_daily_per_vehicle"]
                    * fleet_size
                    * optempo_mult
                    * env_mult
                    * ripple
                )
                # Noise: scale by sqrt(lam) so variance grows with mean
                noisy = max(0.0, lam + rng.gauss(0, max(0.4, lam ** 0.5)))
                qty = int(round(noisy))
                if qty <= 0:
                    continue
                wo_seq += 1
                records.append({
                    "date": day_date.strftime("%Y-%m-%d"),
                    "work_order_id": f"WO-{day_date.strftime('%y%m%d')}-{wo_seq:05d}",
                    "platform": plat_id,
                    "vehicle_id": f"{plat_id}-{rng.randint(1, fleet_size):04d}",
                    "environment": environment,
                    "optempo": optempo,
                    "magtf_size": magtf_size,
                    "nsn": part["nsn"],
                    "part_name": part["part_name"],
                    "qty_consumed": qty,
                    "subsystem": part["subsystem"],
                })
    return records


def build_forward_nodes(catalog: list[dict], rng: random.Random) -> list[dict]:
    """Attach an on-hand-by-NSN inventory to each forward node.

    Forward (OKI / GUAM) nodes hold less than CONUS depots — that's the whole
    contested-logistics story.
    """
    out = []
    for node in FORWARD_NODES:
        on_hand = {}
        for c in catalog:
            base = max(0, int(rng.gauss(8, 5))) if node["tier"] == "forward" \
                   else max(0, int(rng.gauss(35, 18)))
            on_hand[c["nsn"]] = base
        out.append({**node, "on_hand_by_nsn": on_hand})
    return out


SCENARIOS = [
    {"id": "INDOPAC-MEB-HIGH-MARITIME",
     "label": "INDOPACOM MEB · High OPTEMPO · Maritime",
     "magtf_size": "MEB", "optempo": "high", "environment": "maritime",
     "narrative_hint": "First Island Chain stand-in force, 30-day contested resupply window."},
    {"id": "CENTCOM-MEU-MED-DESERT",
     "label": "CENTCOM MEU · Medium OPTEMPO · Desert",
     "magtf_size": "MEU", "optempo": "medium", "environment": "desert",
     "narrative_hint": "MEU sustainment ashore, brownwater LOC, persistent drone harassment."},
    {"id": "AFRICOM-MEB-HIGH-JUNGLE",
     "label": "AFRICOM MEB · High OPTEMPO · Jungle",
     "magtf_size": "MEB", "optempo": "high", "environment": "jungle",
     "narrative_hint": "Crisis response into littoral jungle environment, 60-day resupply pipeline."},
]


def main() -> None:
    rng = random.Random(1776)
    catalog = build_nsn_catalog(rng)
    (ROOT / "nsn_catalog.json").write_text(json.dumps(catalog, indent=2))

    forward_nodes = build_forward_nodes(catalog, rng)
    (ROOT / "forward_nodes.json").write_text(json.dumps(forward_nodes, indent=2))

    (ROOT / "scenarios.json").write_text(json.dumps(SCENARIOS, indent=2))

    # Default 90-day maintenance history is the INDOPAC MEB / high / maritime
    # scenario (matches the lead demo flow). The app can re-synthesize at
    # runtime for other profiles via synth_maintenance_history().
    records = synth_maintenance_history(
        catalog, days=90,
        magtf_size="MEB", optempo="high", environment="maritime",
        rng=random.Random(1776),
    )
    csv_path = ROOT / "maintenance_history.csv"
    with csv_path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(records[0].keys()))
        w.writeheader()
        w.writerows(records)

    print(f"Wrote {len(catalog)} NSNs, {len(forward_nodes)} forward nodes, "
          f"{len(records)} work orders, {len(SCENARIOS)} cached scenarios.")
    print(f"  -> {ROOT}")


if __name__ == "__main__":
    main()
