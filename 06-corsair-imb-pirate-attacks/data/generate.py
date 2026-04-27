"""Synthetic ASAM-shape pirate-attack generator (1993-2025).

This script produces ~3,000 reproducible (seed=1776) records that mirror the
schema of the real **IMB Piracy Reporting Centre** / **NGA Worldwide Threats
to Shipping (ASAM)** export. Records cluster around the six canonical
hostile-maritime basins (Gulf of Aden, Strait of Malacca, Gulf of Guinea,
Sulu Sea, Caribbean/Venezuelan, South China Sea), with peak-year biasing per
basin and basin-specific actor / MOA narrative pools.

Schema written to ``data/pirate_attacks.csv`` (full) and ``data/pirate_attacks.json``
(200-row sample):
  attack_id, datetime, year, month, lat, lon, basin, vessel_type, attack_type,
  crew_injured, hostages_taken, weapons, narrative

Real-IMB swap pointer
---------------------
To run CORSAIR on real data instead of this synthetic CSV, replace
``data/pirate_attacks.csv`` with the real IMB / NGA ASAM export. Required
columns the rest of the app reads (see ``src/forecaster.py``):
  datetime (ISO-8601), lat, lon, basin, attack_type, vessel_type, narrative,
  month, year
Public mirror: kaggle.com/datasets/dryad/global-maritime-pirate-attacks
(1993-2020 ASAM mirror). NGA ASAM export at: msi.nga.mil/Piracy
"""
from __future__ import annotations

import json
import math
import random
from datetime import datetime, timedelta
from pathlib import Path

OUT_DIR = Path(__file__).parent
SEED = 1776
N_RECORDS = 3000

# Canonical piracy hotspot centroids + half-axes (degrees) + activity weight
# weights inform the share of synthetic records in each basin.
BASINS = [
    {
        "name": "Gulf of Aden",
        "lat": 13.0, "lon": 49.0,
        "spread_lat": 2.6, "spread_lon": 4.5,
        "weight": 0.27,
        "peak_years": (2008, 2012),  # Somali piracy peak
        "actor_pool": ["Somali pirate skiff network", "Puntland-based PAG", "Hobyo-Harardhere PAG"],
        "moa_pool": ["mothership-launched skiff swarm", "RPG warning shot then boarding",
                     "AK-47 small arms suppression", "grappling hook boarding at low freeboard"],
    },
    {
        "name": "Strait of Malacca",
        "lat": 3.5, "lon": 100.5,
        "spread_lat": 2.2, "spread_lon": 3.0,
        "weight": 0.20,
        "peak_years": (2003, 2006),
        "actor_pool": ["Riau Archipelago armed robbers", "Indonesian coastal gang",
                       "Free Aceh splinter (historical)"],
        "moa_pool": ["nighttime stealth boarding at anchorage", "crew rob & flee in <30 min",
                     "knife-armed boarders, no firearms", "fast skiff rob at narrow channel"],
    },
    {
        "name": "Gulf of Guinea",
        "lat": 4.0, "lon": 5.5,
        "spread_lat": 4.0, "spread_lon": 5.0,
        "weight": 0.25,
        "peak_years": (2018, 2021),  # MEND/Niger Delta piracy peak
        "actor_pool": ["Niger Delta militant offshoot", "Nigerian kidnap-for-ransom cell",
                       "Bakassi Strike Force remnant"],
        "moa_pool": ["kidnap-for-ransom of officers", "fast attack craft >150nm offshore",
                     "AK-47 + GPMG armed boarding", "tanker product theft (siphon)"],
    },
    {
        "name": "Sulu Sea",
        "lat": 6.0, "lon": 120.5,
        "spread_lat": 1.6, "spread_lon": 2.5,
        "weight": 0.15,
        "peak_years": (2016, 2018),
        "actor_pool": ["Abu Sayyaf maritime cell", "BIFF splinter group",
                       "Sulu archipelago kidnapping ring"],
        "moa_pool": ["abduction of fishing crew", "speedboat intercept tug & barge",
                     "M16 + RPG armed boarding", "hostage transfer to Jolo island camps"],
    },
    {
        "name": "Caribbean / Venezuelan",
        "lat": 11.0, "lon": -65.0,
        "spread_lat": 2.5, "spread_lon": 3.5,
        "weight": 0.06,
        "peak_years": (2017, 2019),
        "actor_pool": ["Venezuelan coastal gang", "Trinidad-Tobago smuggler crew"],
        "moa_pool": ["yacht boarding at anchorage", "crew theft + minor injuries",
                     "small arms intimidation"],
    },
    {
        "name": "South China Sea",
        "lat": 9.5, "lon": 113.0,
        "spread_lat": 3.5, "spread_lon": 4.5,
        "weight": 0.07,
        "peak_years": (2014, 2016),
        "actor_pool": ["Vietnamese coastal robbers", "Filipino anchor-rob crew"],
        "moa_pool": ["product theft (diesel siphoning)", "stealth anchorage boarding"],
    },
]

VESSEL_TYPES = [
    ("Bulk Carrier", 0.18), ("Container Ship", 0.16), ("Chemical Tanker", 0.12),
    ("Crude Oil Tanker", 0.11), ("General Cargo", 0.10), ("Fishing Vessel", 0.10),
    ("Tug & Barge", 0.07), ("LPG/LNG Tanker", 0.05), ("Yacht", 0.04),
    ("RoRo Vehicle Carrier", 0.04), ("Offshore Supply", 0.03),
]

ATTACK_TYPES = [
    ("Boarded", 0.42), ("Attempted", 0.28), ("Hijacked", 0.10),
    ("Fired Upon", 0.12), ("Suspicious Approach", 0.08),
]


def weighted_choice(rng: random.Random, items: list[tuple[str, float]]) -> str:
    r = rng.random()
    acc = 0.0
    for name, w in items:
        acc += w
        if r <= acc:
            return name
    return items[-1][0]


def datetime_for_basin(rng: random.Random, basin: dict) -> datetime:
    """Bias the date toward the basin's peak years but allow full 1993-2025 range."""
    if rng.random() < 0.55:
        peak_lo, peak_hi = basin["peak_years"]
        year = rng.randint(peak_lo, peak_hi)
    else:
        year = rng.randint(1993, 2025)
    month = rng.randint(1, 12)
    day = rng.randint(1, 28)
    hour = rng.choices(range(24), weights=[3, 4, 5, 6, 5, 3, 2, 1, 1, 1, 1, 1,
                                            1, 1, 1, 1, 1, 2, 3, 4, 5, 5, 4, 3])[0]
    minute = rng.randint(0, 59)
    return datetime(year, month, day, hour, minute)


def gaussian_offset(rng: random.Random, sigma: float) -> float:
    return rng.gauss(0, sigma / 2.5)  # 2.5 sigmas inside the half-axis


def generate_narrative(rng: random.Random, basin: dict, vessel: str, attack_type: str,
                        injured: bool, hostages: int) -> str:
    actor = rng.choice(basin["actor_pool"])
    moa = rng.choice(basin["moa_pool"])
    weapons = rng.choice(["AK-47", "RPG-7", "knives/machetes", "small arms", "M16 + RPG"])
    distance = rng.choice(["at anchorage", "underway in transit lane",
                            f"approx {rng.randint(15, 280)}nm offshore",
                            "in narrow channel"])
    outcome_bits = []
    if attack_type == "Hijacked":
        outcome_bits.append(f"vessel hijacked, crew of {rng.randint(12,28)} taken to coastal anchorage")
    elif attack_type == "Boarded":
        outcome_bits.append(f"boarders rifled bridge & masters cabin, stole cash and electronics")
    elif attack_type == "Fired Upon":
        outcome_bits.append("master engaged evasive maneuvers, RPG and small arms fire received")
    elif attack_type == "Attempted":
        outcome_bits.append("approach broken off after master sounded alarm and engaged firehoses")
    else:
        outcome_bits.append("unidentified skiff shadowed vessel for 18 minutes before withdrawing")
    if injured:
        outcome_bits.append(f"{rng.randint(1,4)} crew sustained injuries")
    if hostages > 0:
        outcome_bits.append(f"{hostages} crew taken hostage; ransom demand transmitted within 72h")
    return (f"{vessel} attacked by {actor} {distance}. MOA: {moa}. Weapons observed: {weapons}. "
            + "; ".join(outcome_bits) + ".")


def main() -> Path:
    rng = random.Random(SEED)
    rows = []
    # weighted basin allocation
    basin_weights = [b["weight"] for b in BASINS]
    for i in range(N_RECORDS):
        basin = rng.choices(BASINS, weights=basin_weights)[0]
        lat = basin["lat"] + gaussian_offset(rng, basin["spread_lat"])
        lon = basin["lon"] + gaussian_offset(rng, basin["spread_lon"])
        dt = datetime_for_basin(rng, basin)
        vessel = weighted_choice(rng, VESSEL_TYPES)
        attack_type = weighted_choice(rng, ATTACK_TYPES)
        injured = rng.random() < (0.22 if attack_type in ("Boarded", "Hijacked", "Fired Upon") else 0.05)
        hostages = 0
        if attack_type == "Hijacked":
            hostages = rng.randint(8, 26)
        elif attack_type == "Boarded" and rng.random() < 0.18:
            hostages = rng.randint(1, 6)
        weapons = rng.choice(["AK-47", "RPG", "Knives", "Small arms", "Unknown"])
        narrative = generate_narrative(rng, basin, vessel, attack_type, injured, hostages)
        rows.append({
            "attack_id": f"ASAM-{1993 + i % 33}-{i:05d}",
            "datetime": dt.isoformat(),
            "year": dt.year,
            "month": dt.month,
            "lat": round(lat, 4),
            "lon": round(lon, 4),
            "basin": basin["name"],
            "vessel_type": vessel,
            "attack_type": attack_type,
            "crew_injured": int(injured),
            "hostages_taken": hostages,
            "weapons": weapons,
            "narrative": narrative,
        })
    # write CSV + JSON
    import csv
    csv_path = OUT_DIR / "pirate_attacks.csv"
    with csv_path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)

    json_path = OUT_DIR / "pirate_attacks.json"
    json_path.write_text(json.dumps(rows[:200], indent=2))  # sample
    print(f"Wrote {len(rows)} records to {csv_path}")
    print(f"Sample (first 200) at {json_path}")
    # basin counts
    from collections import Counter
    c = Counter(r["basin"] for r in rows)
    for b, n in c.most_common():
        print(f"  {b}: {n}")
    return csv_path


if __name__ == "__main__":
    main()
