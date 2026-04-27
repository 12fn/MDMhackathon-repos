"""Synthetic NFIP-shape flood-claim generator for the RIPTIDE template.

Emits 5,000 records whose schema mirrors the public FIMA NFIP Redacted Claims
dataset, so the rest of the app (`backend/app.py`, `frontend/app.py`) can run
end-to-end without network access. Density is biased toward Gulf + East Coast
counties near the 5 reference USMC installations. Seed is fixed for repeatable
demos.

Output:
    data/nfip_claims.json       (one big list)
    data/nfip_claims.parquet    (efficient analytics)
    data/installations.json     (5 reference USMC installations + inventories)

Real-FIMA swap (Bucket A):
    1. Download the live CSV from FEMA:
       https://www.fema.gov/openfema-data-page/fima-nfip-redacted-claims-v2
    2. Drop it into `data/raw/` (create the dir).
    3. Edit `backend/app.py::_load()` to read your CSV (keep the same column
       names — building/contents paid amounts, lat/lon, state, eventDesignation,
       yearOfLoss, etc.) instead of the generated parquet.
    The aggregation, projection math, and LLM prompts work unchanged.
"""
from __future__ import annotations

import json
import math
import random
from pathlib import Path

import pandas as pd

SEED = 1776
N = 5_000
OUT = Path(__file__).parent

# 5 reference installations (real lat/lon, real-ish inventories).
INSTALLATIONS = [
    {
        "id": "lejeune",
        "name": "MCB Camp Lejeune",
        "state": "NC",
        "lat": 34.6840,
        "lon": -77.3464,
        "personnel": 47000,
        "high_risk_storm_categories": [1, 2, 3, 4],
        "inventory": {
            "aircraft_hangars": 0,
            "motor_pools": 12,
            "ammo_storage_bunkers": 18,
            "family_housing_units": 4500,
            "barracks": 92,
            "generators_kw": 18000,
            "fuel_storage_gal": 2_400_000,
            "wharf_meters": 1850,
            "runways": 0,
            "critical_c2_nodes": 4,
        },
        "notable_history": "Hurricane Florence (2018) caused $3.6B+ in damage; recovery took 18 months.",
    },
    {
        "id": "cherry-point",
        "name": "MCAS Cherry Point",
        "state": "NC",
        "lat": 34.9009,
        "lon": -76.8809,
        "personnel": 9300,
        "high_risk_storm_categories": [1, 2, 3, 4],
        "inventory": {
            "aircraft_hangars": 14,
            "motor_pools": 6,
            "ammo_storage_bunkers": 12,
            "family_housing_units": 1750,
            "barracks": 28,
            "generators_kw": 9500,
            "fuel_storage_gal": 1_800_000,
            "wharf_meters": 0,
            "runways": 2,
            "critical_c2_nodes": 3,
        },
        "notable_history": "Hurricane Florence flooded 800+ buildings; Marine Air Group 14 relocated for weeks.",
    },
    {
        "id": "albany",
        "name": "MCLB Albany",
        "state": "GA",
        "lat": 31.5460,
        "lon": -84.0633,
        "personnel": 3200,
        "high_risk_storm_categories": [2, 3, 4],
        "inventory": {
            "aircraft_hangars": 0,
            "motor_pools": 22,
            "ammo_storage_bunkers": 6,
            "family_housing_units": 0,
            "barracks": 8,
            "generators_kw": 14000,
            "fuel_storage_gal": 900_000,
            "wharf_meters": 0,
            "runways": 0,
            "critical_c2_nodes": 5,
            "depot_warehouses_sqft": 2_800_000,
        },
        "notable_history": "Tornado outbreak (Jan 2017) damaged 60% of LOGCOM HQ buildings; tropical storm flooding common.",
    },
    {
        "id": "yuma",
        "name": "MCAS Yuma",
        "state": "AZ",
        "lat": 32.6566,
        "lon": -114.6058,
        "personnel": 5600,
        "high_risk_storm_categories": [],  # tropical storms only, but flash floods
        "inventory": {
            "aircraft_hangars": 9,
            "motor_pools": 4,
            "ammo_storage_bunkers": 14,
            "family_housing_units": 1100,
            "barracks": 22,
            "generators_kw": 7200,
            "fuel_storage_gal": 1_400_000,
            "wharf_meters": 0,
            "runways": 2,
            "critical_c2_nodes": 2,
        },
        "notable_history": "Monsoon flash floods damage flightline drainage annually; Hurricane Hilary (2023) closed I-8.",
    },
    {
        "id": "pendleton",
        "name": "MCB Camp Pendleton",
        "state": "CA",
        "lat": 33.3858,
        "lon": -117.5631,
        "personnel": 70000,
        "high_risk_storm_categories": [],  # atmospheric rivers, not hurricanes
        "inventory": {
            "aircraft_hangars": 6,
            "motor_pools": 28,
            "ammo_storage_bunkers": 24,
            "family_housing_units": 6800,
            "barracks": 140,
            "generators_kw": 24000,
            "fuel_storage_gal": 3_200_000,
            "wharf_meters": 720,
            "runways": 1,
            "critical_c2_nodes": 6,
        },
        "notable_history": "Atmospheric rivers (2023, 2024) flooded San Onofre Creek; Las Pulgas housing repeatedly damaged.",
    },
]

# Coastal bias zones — (lat, lon, weight, label) — pull most claims toward these.
# More weight near Marine installations, plus broad coastal weight.
BIAS_CENTERS = [
    (34.6, -77.3, 6.0, "NC-Lejeune"),
    (34.9, -76.9, 5.0, "NC-CherryPoint"),
    (31.5, -84.1, 3.0, "GA-Albany"),
    (32.7, -114.6, 2.0, "AZ-Yuma"),
    (33.4, -117.6, 3.0, "CA-Pendleton"),
    # Background coastal density.
    (29.5, -94.8, 4.0, "TX-Houston"),
    (30.0, -90.1, 4.0, "LA-NewOrleans"),
    (30.4, -88.9, 3.0, "MS-Gulfport"),
    (27.8, -82.7, 3.5, "FL-Tampa"),
    (25.8, -80.2, 3.5, "FL-Miami"),
    (32.8, -79.9, 2.5, "SC-Charleston"),
    (39.3, -74.5, 2.0, "NJ-AtlanticCity"),
    (40.7, -73.9, 2.0, "NY-NewYork"),
]

STATES_BY_BIAS = {
    "NC-Lejeune": "NC", "NC-CherryPoint": "NC",
    "GA-Albany": "GA", "AZ-Yuma": "AZ", "CA-Pendleton": "CA",
    "TX-Houston": "TX", "LA-NewOrleans": "LA", "MS-Gulfport": "MS",
    "FL-Tampa": "FL", "FL-Miami": "FL", "SC-Charleston": "SC",
    "NJ-AtlanticCity": "NJ", "NY-NewYork": "NY",
}

EVENT_TYPES = [
    ("Hurricane / Tropical Cyclone", 0.42),
    ("Heavy Rain / Flash Flood", 0.25),
    ("Storm Surge / Coastal", 0.18),
    ("Riverine Flood", 0.10),
    ("Other Flood", 0.05),
]
FLOOD_ZONES = [
    ("AE", 0.30), ("VE", 0.10), ("X", 0.30),
    ("AO", 0.10), ("A", 0.15), ("X500", 0.05),
]
BUILDING_TYPES = [
    ("Single Family", 0.55),
    ("Multi-Family", 0.10),
    ("Mobile Home", 0.08),
    ("Non-Residential", 0.20),
    ("Other Residential", 0.07),
]
OCCUPANCY = [
    (1, 0.58), (2, 0.10), (3, 0.05), (4, 0.20), (6, 0.07),
]


def weighted_pick(rng: random.Random, options):
    r = rng.random()
    acc = 0.0
    for v, w in options:
        acc += w
        if r <= acc:
            return v
    return options[-1][0]


def jitter_around(rng: random.Random, lat: float, lon: float, miles: float):
    """Random point within `miles` of (lat,lon)."""
    # 1 deg lat ~ 69 mi
    r = rng.random() * miles / 69.0
    theta = rng.random() * 2 * math.pi
    dlat = r * math.cos(theta)
    dlon = r * math.sin(theta) / max(0.2, math.cos(math.radians(lat)))
    return lat + dlat, lon + dlon


def synth_zip(rng: random.Random, state: str) -> str:
    # Crude but consistent: state-prefix + rng.
    base = {
        "NC": 28, "GA": 31, "AZ": 85, "CA": 92, "TX": 77,
        "LA": 70, "MS": 39, "FL": 33, "SC": 29, "NJ": 8, "NY": 11,
    }.get(state, 50)
    return f"{base:02d}{rng.randint(100,999)}"


def main() -> None:
    rng = random.Random(SEED)
    rows = []
    bias_weights = [b[2] for b in BIAS_CENTERS]
    bias_total = sum(bias_weights)
    bias_norm = [w / bias_total for w in bias_weights]

    for i in range(N):
        # Pick bias center.
        r = rng.random()
        acc = 0.0
        center = BIAS_CENTERS[-1]
        for c, w in zip(BIAS_CENTERS, bias_norm):
            acc += w
            if r <= acc:
                center = c
                break
        clat, clon, _, label = center
        state = STATES_BY_BIAS[label]

        # Jitter ~25 miles around the bias center (smaller for installation centers, bigger for cities).
        radius = rng.uniform(8, 35)
        lat, lon = jitter_around(rng, clat, clon, radius)

        # Year 2010-2025, recent years slightly heavier (climate skew).
        year = rng.choices(
            list(range(2010, 2026)),
            weights=[1.0, 1.05, 1.1, 1.15, 1.2, 1.3, 1.45, 1.6, 1.5, 1.4, 1.55, 1.7, 1.65, 1.75, 1.8, 1.85],
            k=1,
        )[0]
        date_of_loss = f"{year}-{rng.randint(5,11):02d}-{rng.randint(1,28):02d}"

        # Log-normal damage; bias higher for hurricanes & VE zones.
        flood_zone = weighted_pick(rng, FLOOD_ZONES)
        event_type = weighted_pick(rng, EVENT_TYPES)
        bldg_type = weighted_pick(rng, BUILDING_TYPES)
        occupancy = weighted_pick(rng, OCCUPANCY)

        mu, sigma = 9.6, 1.05  # exp(9.6) ~ $14.7k median
        amt = rng.lognormvariate(mu, sigma)
        if event_type.startswith("Hurricane"):
            amt *= rng.uniform(1.3, 2.5)
        if flood_zone == "VE":
            amt *= rng.uniform(1.2, 1.8)
        amt = min(amt, 500_000)
        building_damage = round(amt, 2)
        contents_damage = round(amt * rng.uniform(0.05, 0.45), 2)

        row = {
            "id": f"NFIP-{SEED}-{i:05d}",
            "reportedZipcode": synth_zip(rng, state),
            "state": state,
            "countyCode": f"{state}-{rng.randint(1, 99):03d}",
            "dateOfLoss": date_of_loss,
            "yearOfLoss": year,
            "floodZone": flood_zone,
            "eventDesignation": event_type,
            "buildingPropertyValue": round(amt * rng.uniform(2.5, 5.0), 2),
            "buildingDamageAmount": building_damage,
            "contentsDamageAmount": contents_damage,
            "amountPaidOnBuildingClaim": round(building_damage * rng.uniform(0.55, 0.92), 2),
            "amountPaidOnContentsClaim": round(contents_damage * rng.uniform(0.45, 0.88), 2),
            "totalBuildingInsuranceCoverage": round(amt * rng.uniform(3.0, 6.0), 2),
            "totalContentsInsuranceCoverage": round(amt * rng.uniform(0.5, 1.5), 2),
            "occupancyType": occupancy,
            "buildingType": bldg_type,
            "primaryResidence": rng.choice([True, False]),
            "elevatedBuildingIndicator": rng.random() < 0.15,
            "latitude": round(lat, 4),
            "longitude": round(lon, 4),
            "biasCluster": label,
        }
        rows.append(row)

    # Write JSON + Parquet.
    json_path = OUT / "nfip_claims.json"
    parquet_path = OUT / "nfip_claims.parquet"
    inst_path = OUT / "installations.json"

    with json_path.open("w") as f:
        json.dump(rows, f)
    df = pd.DataFrame(rows)
    df.to_parquet(parquet_path, index=False)
    with inst_path.open("w") as f:
        json.dump(INSTALLATIONS, f, indent=2)

    print(f"Wrote {len(rows)} synthetic claims:")
    print(f"  {json_path}  ({json_path.stat().st_size/1024:.1f} KB)")
    print(f"  {parquet_path}  ({parquet_path.stat().st_size/1024:.1f} KB)")
    print(f"  {inst_path}  ({len(INSTALLATIONS)} installations)")
    print()
    print("Top states by claim count:")
    print(df["state"].value_counts().to_string())
    print()
    print(f"Total $ paid (building+contents): "
          f"${(df.amountPaidOnBuildingClaim.sum() + df.amountPaidOnContentsClaim.sum())/1e6:,.1f}M")


if __name__ == "__main__":
    main()
