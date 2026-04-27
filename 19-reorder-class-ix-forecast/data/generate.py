"""REORDER synthetic data generator.

Produces:
  data/maintenance_history.csv  - 90 days of work-order records across MTVR/LAV/
                                   JLTV/M88A2/HMMWV with NSN consumed
  data/nsn_catalog.json          - 200 synthetic NSNs with descriptions
  data/forward_nodes.json        - 5 expeditionary depots with on-hand stock
  data/scenarios.json            - 3 OPTEMPO/environment scenarios

Seeded with random.Random(1776) for reproducibility.

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

# Subsystem-to-NSN-class category map for realistic part naming.
SUBSYSTEM_PARTS = {
    "engine":      ["fuel injector", "turbocharger", "oil cooler", "EGR valve", "starter motor",
                    "fuel pump", "alternator", "water pump", "cylinder head gasket"],
    "transmission":["torque converter", "clutch pack", "transmission filter", "shift solenoid",
                    "transfer case seal", "drive shaft U-joint"],
    "brakes":      ["brake caliper", "brake pad set", "brake rotor", "ABS sensor",
                    "master cylinder", "brake line"],
    "electrical":  ["battery 6TL", "wiring harness", "ignition coil", "voltage regulator",
                    "headlight assembly", "ECM module"],
    "tires":       ["radial tire 395/85R20", "tire valve stem", "wheel bearing",
                    "tire pressure sensor", "lug nut set"],
    "hydraulics":  ["hydraulic pump", "hydraulic filter", "actuator cylinder",
                    "high-pressure hose", "reservoir cap"],
    "turret":      ["turret drive motor", "turret bearing race", "elevation gear",
                    "stabilization gyro"],
    "wheels":      ["wheel hub assembly", "wheel bearing", "wheel stud", "tire 12.00R20"],
    "weapons":     ["barrel assembly M242", "feed chute", "extractor assembly",
                    "firing pin"],
    "suspension":  ["shock absorber", "control arm bushing", "leaf spring", "tie-rod end",
                    "ball joint"],
    "armor":       ["armor panel kit", "ballistic glass insert", "underbody armor plate"],
    "tracks":      ["track shoe assembly", "drive sprocket", "road wheel", "track pin",
                    "torsion bar"],
    "winch":       ["winch motor", "winch cable 200ft", "winch drum brake"],
    "boom":        ["boom hydraulic ram", "boom pivot pin", "boom hoist cable"],
}

# Environmental modifiers — multiplicative on baseline part-failure rate by subsystem.
ENV_MODIFIERS = {
    "desert":   {"engine": 1.6, "tires": 2.1, "hydraulics": 1.3, "electrical": 1.2,
                 "brakes": 1.0, "turret": 1.1, "wheels": 1.4, "weapons": 1.2,
                 "tracks": 1.3, "suspension": 1.2, "transmission": 1.2,
                 "armor": 1.0, "winch": 1.0, "boom": 1.0},
    "jungle":   {"engine": 1.2, "tires": 1.1, "hydraulics": 1.5, "electrical": 1.7,
                 "brakes": 1.3, "turret": 1.2, "wheels": 1.0, "weapons": 1.3,
                 "tracks": 1.4, "suspension": 1.5, "transmission": 1.2,
                 "armor": 1.1, "winch": 1.4, "boom": 1.2},
    "maritime": {"engine": 1.1, "tires": 1.0, "hydraulics": 1.2, "electrical": 2.0,
                 "brakes": 1.4, "turret": 1.3, "wheels": 1.1, "weapons": 1.5,
                 "tracks": 1.0, "suspension": 1.0, "transmission": 1.1,
                 "armor": 1.6, "winch": 1.5, "boom": 1.4},
    "cold":     {"engine": 1.4, "tires": 1.1, "hydraulics": 1.6, "electrical": 1.3,
                 "brakes": 1.5, "turret": 1.0, "wheels": 1.2, "weapons": 1.3,
                 "tracks": 1.4, "suspension": 1.3, "transmission": 1.5,
                 "armor": 1.0, "winch": 1.2, "boom": 1.3},
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


def _make_nsn(rng: random.Random) -> str:
    """Synthetic NSN (federal stock-class style: NNNN-NN-NNN-NNNN)."""
    fsc = rng.choice(["2540", "2520", "2510", "5340", "6135", "2805", "2815",
                      "2920", "2930", "5305", "1015", "1240", "5895", "4720"])
    niin = f"{rng.randint(0,99):02d}-{rng.randint(0,999):03d}-{rng.randint(0,9999):04d}"
    return f"{fsc}-01-{niin[3:]}"  # always US country code 01


def build_nsn_catalog(rng: random.Random) -> list[dict]:
    """Return ~200 NSN catalog entries spread across the platforms/subsystems.
    Each entry: nsn, part_name, primary_platform, subsystem, base_daily_per_vehicle."""
    catalog: list[dict] = []
    target = 200
    while len(catalog) < target:
        plat = rng.choice(PLATFORMS)
        subsys = rng.choice(plat["subsystems"])
        part = rng.choice(SUBSYSTEM_PARTS[subsys])
        nsn = _make_nsn(rng)
        # Base failure rate per vehicle per day at OPTEMPO=medium, env baseline.
        # Tunable so MEU @ medium produces ~5-50 of the top NSNs over 90 days.
        base = round(rng.uniform(0.0009, 0.012), 5)
        catalog.append({
            "nsn": nsn,
            "part_name": f"{part} ({plat['id']})",
            "primary_platform": plat["id"],
            "subsystem": subsys,
            "base_daily_per_vehicle": base,
            "unit_price_usd": rng.choice([45, 120, 380, 850, 1400, 3200, 7800, 18500]),
        })
    return catalog


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
