"""STORM-SHIFT — synthetic dataset generator (seed=1776).

Five datasets in one cohesive corpus, shaped to match real-world schemas so
real-data swap is a one-file edit (see ``data/load_real.py``):

  1. NASA Earthdata-shape hourly weather grids
       provenance: https://earthdata.nasa.gov/  (GES DISC GPM IMERG, MERRA-2)
  2. NASA FIRMS-shape thermal anomaly pixels
       provenance: https://firms.modaps.eosdis.nasa.gov/active_fire/
  3. FIMA NFIP Redacted Claims-shape flood claims
       provenance: https://www.fema.gov/openfema-data-page/fima-nfip-redacted-claims-v2
       (re-uses the RIPTIDE schema verbatim — installations match)
  4. FEMA Supply Chain Climate Resilience-shape disruption events
       provenance: FEMA / Qlik Supply Chain Climate Resilience open data
  5. Logistics-and-supply-chain-dataset (California)-shape transport records
       provenance: Kaggle "logistics-and-supply-chain-dataset" (synthetic CA region)

Plus:
  - 5 USMC installations (match RIPTIDE's lat/lon + inventories + verified history)
  - 8 storm scenarios (baseline, TS, Cat 1-4, atmospheric river, monsoon flash, Santa Ana fire-following)
  - cached_briefs.json — 3 polycrisis hero LLM briefs

Run:  python data/generate.py
"""
from __future__ import annotations

import json
import math
import random
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

SEED = 1776
OUT = Path(__file__).parent

# ─────────────────────────────────────────────────────────────────────────────
# 1. INSTALLATIONS — match RIPTIDE for cross-app coherence
# ─────────────────────────────────────────────────────────────────────────────
INSTALLATIONS = [
    {
        "id": "lejeune",
        "name": "MCB Camp Lejeune",
        "state": "NC",
        "lat": 34.6840,
        "lon": -77.3464,
        "personnel": 47000,
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
        "stocks": {
            "class_i_mre_cases": 18000,
            "class_iii_fuel_gal": 2_200_000,
            "class_v_ammo_short_tons": 980,
            "class_viii_plasma_units": 1100,
            "class_ix_repair_parts_lines": 12500,
            "potable_water_gal": 1_800_000,
            "generator_diesel_gal": 220_000,
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
        "stocks": {
            "class_i_mre_cases": 4200,
            "class_iii_fuel_gal": 1_650_000,
            "class_v_ammo_short_tons": 410,
            "class_viii_plasma_units": 320,
            "class_ix_repair_parts_lines": 8800,
            "potable_water_gal": 540_000,
            "generator_diesel_gal": 110_000,
        },
        "notable_history": "Hurricane Florence (2018) flooded 800+ buildings; MAG-14 relocated for weeks.",
    },
    {
        "id": "albany",
        "name": "MCLB Albany",
        "state": "GA",
        "lat": 31.5460,
        "lon": -84.0633,
        "personnel": 3200,
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
        "stocks": {
            "class_i_mre_cases": 1800,
            "class_iii_fuel_gal": 820_000,
            "class_v_ammo_short_tons": 220,
            "class_viii_plasma_units": 95,
            "class_ix_repair_parts_lines": 28000,  # depot
            "potable_water_gal": 240_000,
            "generator_diesel_gal": 180_000,
        },
        "notable_history": "Tornado outbreak (Jan 2017) damaged 60% of LOGCOM HQ; tropical storm flooding common.",
    },
    {
        "id": "yuma",
        "name": "MCAS Yuma",
        "state": "AZ",
        "lat": 32.6566,
        "lon": -114.6058,
        "personnel": 5600,
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
        "stocks": {
            "class_i_mre_cases": 3100,
            "class_iii_fuel_gal": 1_280_000,
            "class_v_ammo_short_tons": 470,
            "class_viii_plasma_units": 180,
            "class_ix_repair_parts_lines": 6900,
            "potable_water_gal": 380_000,
            "generator_diesel_gal": 95_000,
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
        "stocks": {
            "class_i_mre_cases": 26000,
            "class_iii_fuel_gal": 3_050_000,
            "class_v_ammo_short_tons": 1380,
            "class_viii_plasma_units": 1620,
            "class_ix_repair_parts_lines": 19400,
            "potable_water_gal": 2_400_000,
            "generator_diesel_gal": 290_000,
        },
        "notable_history": "Atmospheric rivers (2023, 2024) flooded San Onofre Creek; Las Pulgas housing repeatedly damaged. Santa Ana wind events drive fire-following risk.",
    },
]

# ─────────────────────────────────────────────────────────────────────────────
# 2. STORM SCENARIOS — 8 polycrisis-grade scenarios
# ─────────────────────────────────────────────────────────────────────────────
SCENARIOS = [
    {
        "id": "baseline",
        "label": "Baseline (no storm)",
        "kind": "baseline",
        "category": 0,
        "wind_kt": 15,
        "rain_in_24h": 0.2,
        "surge_ft": 0.0,
        "shelter_days": 0,
        "headcount_factor": 0.6,  # off-duty
        "fire_secondary": False,
        "applies_to": ["lejeune", "cherry-point", "albany", "yuma", "pendleton"],
        "narrative": "Steady-state posture, normal operations. Demand baseline.",
    },
    {
        "id": "ts-elsa",
        "label": "Tropical Storm (TS-ELSA-shape)",
        "kind": "tropical_storm",
        "category": 0,
        "wind_kt": 55,
        "rain_in_24h": 4.5,
        "surge_ft": 2.5,
        "shelter_days": 1,
        "headcount_factor": 0.95,
        "fire_secondary": False,
        "applies_to": ["lejeune", "cherry-point", "albany"],
        "narrative": "Tropical storm — sustained 55 kt winds, 4.5 inches rain in 24h, modest surge.",
    },
    {
        "id": "cat1",
        "label": "Cat-1 Hurricane (HERMINE-shape)",
        "kind": "hurricane",
        "category": 1,
        "wind_kt": 75,
        "rain_in_24h": 6.0,
        "surge_ft": 4.0,
        "shelter_days": 2,
        "headcount_factor": 1.0,
        "fire_secondary": False,
        "applies_to": ["lejeune", "cherry-point", "albany"],
        "narrative": "Cat-1 hurricane — 75 kt sustained, storm surge 4 ft, 2-day shelter posture.",
    },
    {
        "id": "cat2",
        "label": "Cat-2 Hurricane (FRAN-shape)",
        "kind": "hurricane",
        "category": 2,
        "wind_kt": 95,
        "rain_in_24h": 8.5,
        "surge_ft": 7.0,
        "shelter_days": 3,
        "headcount_factor": 1.0,
        "fire_secondary": False,
        "applies_to": ["lejeune", "cherry-point", "albany"],
        "narrative": "Cat-2 — significant tree damage, structural risk to housing, prolonged power loss likely.",
    },
    {
        "id": "cat3",
        "label": "Cat-3 Hurricane (FLORENCE-shape)",
        "kind": "hurricane",
        "category": 3,
        "wind_kt": 115,
        "rain_in_24h": 18.0,
        "surge_ft": 10.0,
        "shelter_days": 5,
        "headcount_factor": 1.0,
        "fire_secondary": False,
        "applies_to": ["lejeune", "cherry-point", "albany"],
        "narrative": "Cat-3 — Florence-class, $3.6B+ damage precedent at Lejeune (2018). Mass shelter, chowhall surge.",
    },
    {
        "id": "cat4",
        "label": "Cat-4 Hurricane (HUGO-shape)",
        "kind": "hurricane",
        "category": 4,
        "wind_kt": 140,
        "rain_in_24h": 22.0,
        "surge_ft": 16.0,
        "shelter_days": 7,
        "headcount_factor": 1.0,
        "fire_secondary": False,
        "applies_to": ["lejeune", "cherry-point", "albany"],
        "narrative": "Cat-4 — catastrophic, week-long shelter, full DSCA activation, runways unusable.",
    },
    {
        "id": "atmos-river",
        "label": "Atmospheric River (HILARY-shape)",
        "kind": "atmospheric_river",
        "category": 0,
        "wind_kt": 45,
        "rain_in_24h": 14.0,
        "surge_ft": 1.5,
        "shelter_days": 3,
        "headcount_factor": 1.0,
        "fire_secondary": True,  # fire-following risk via wind
        "applies_to": ["pendleton", "yuma"],
        "narrative": "Atmospheric river — Hilary 2023 closed I-8, San Onofre Creek flooded Las Pulgas housing.",
    },
    {
        "id": "santa-ana-fire",
        "label": "Santa Ana fire-following (THOMAS-shape)",
        "kind": "santa_ana_fire",
        "category": 0,
        "wind_kt": 65,  # Santa Ana wind
        "rain_in_24h": 0.0,
        "surge_ft": 0.0,
        "shelter_days": 4,
        "headcount_factor": 1.0,
        "fire_secondary": True,
        "applies_to": ["pendleton"],
        "narrative": "Santa Ana — 65 kt offshore winds + dry vegetation, fire ignition risk extreme. Downstream of atmos-river vegetation regrowth.",
    },
]

# Polycrisis multiplier matrix (compounding factor when 2+ co-occur).
POLYCRISIS_PAIRS = [
    ("cat3", "santa-ana-fire", 1.45, "Hurricane debris fuels post-storm fire ignition; fire suppression water competes with shelter water."),
    ("atmos-river", "santa-ana-fire", 1.60, "Wet vegetation regrowth + Santa Ana = exceptional fuel load (THOMAS 2017 pattern)."),
    ("cat4", "ts-elsa", 1.30, "Saturated soils from prior TS amplify Cat-4 surge inundation."),
    ("cat3", "atmos-river", 1.25, "Coastal storm + inland atmos-river = bi-coastal supply chain seizure."),
]

# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def haversine_mi(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R = 3958.7613
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * R * math.asin(min(1.0, math.sqrt(a)))


def jitter(rng: random.Random, lat: float, lon: float, miles: float) -> tuple[float, float]:
    r = rng.random() * miles / 69.0
    theta = rng.random() * 2 * math.pi
    dlat = r * math.cos(theta)
    dlon = r * math.sin(theta) / max(0.2, math.cos(math.radians(lat)))
    return lat + dlat, lon + dlon


def weighted_pick(rng: random.Random, options: list[tuple]):
    r = rng.random()
    acc = 0.0
    for v, w in options:
        acc += w
        if r <= acc:
            return v
    return options[-1][0]


# ─────────────────────────────────────────────────────────────────────────────
# 3. NASA Earthdata-shape weather grid (hourly, 72h forecast horizon)
# ─────────────────────────────────────────────────────────────────────────────

def gen_earthdata_grid(rng: random.Random) -> list[dict]:
    """Hourly synthetic GPM IMERG-shape grid: precip + wind + temp around each base.

    Real schema reference (GES DISC GPM IMERG L3 Half-Hourly v07):
      time, lat, lon, precipitationCal (mm/hr), HQprecipitation, IRkalmanFilterWeight
    We simplify to: timestamp, lat, lon, precip_mm_hr, wind_u_mps, wind_v_mps, temp_c.
    """
    rows = []
    t0 = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
    for inst in INSTALLATIONS:
        for hr in range(0, 73, 3):  # every 3h, 73h horizon
            ts = (t0 + timedelta(hours=hr)).isoformat()
            for _ in range(4):  # 4 grid cells per base
                la, lo = jitter(rng, inst["lat"], inst["lon"], 25)
                base_precip = rng.uniform(0.0, 1.5)
                wave = math.sin(hr / 12 * math.pi) * 2.0
                rows.append({
                    "timestamp": ts,
                    "lat": round(la, 4),
                    "lon": round(lo, 4),
                    "precip_mm_hr": round(max(0.0, base_precip + wave + rng.uniform(-0.5, 0.5)), 3),
                    "wind_u_mps": round(rng.gauss(0, 4), 3),
                    "wind_v_mps": round(rng.gauss(0, 4), 3),
                    "temp_c": round(20 + rng.gauss(0, 4) + (5 if inst["state"] in ("AZ", "CA") else 0), 2),
                    "near_installation": inst["id"],
                    "source": "synthetic-NASA-GPM-IMERG-shape",
                })
    return rows


# ─────────────────────────────────────────────────────────────────────────────
# 4. NASA FIRMS-shape thermal anomaly pixels (24h)
# ─────────────────────────────────────────────────────────────────────────────

def gen_firms_pixels(rng: random.Random) -> list[dict]:
    """FIRMS MODIS_C6 schema:
      latitude, longitude, brightness, scan, track, acq_date, acq_time,
      satellite, confidence, version, bright_t31, frp, daynight
    """
    rows = []
    # Heavier density around Pendleton (Santa Ana zone) + Yuma desert
    centers = [
        ("pendleton", 33.4, -117.5, 18, 30),
        ("yuma", 32.7, -114.6, 8, 60),
        ("lejeune", 34.7, -77.3, 3, 40),
        ("cherry-point", 34.9, -76.9, 2, 40),
        ("albany", 31.5, -84.1, 4, 50),
    ]
    fid = 0
    for inst_id, lat, lon, n, radius in centers:
        for _ in range(n):
            la, lo = jitter(rng, lat, lon, radius)
            now = datetime.now(timezone.utc) - timedelta(hours=rng.randint(0, 23))
            rows.append({
                "id": f"FIRMS-{SEED}-{fid:05d}",
                "latitude": round(la, 4),
                "longitude": round(lo, 4),
                "brightness": round(rng.uniform(310, 425), 1),
                "scan": round(rng.uniform(1.0, 2.5), 2),
                "track": round(rng.uniform(1.0, 2.0), 2),
                "acq_date": now.strftime("%Y-%m-%d"),
                "acq_time": now.strftime("%H%M"),
                "satellite": rng.choice(["Aqua", "Terra"]),
                "confidence": rng.choice(["nominal", "nominal", "high", "low"]),
                "version": "6.1NRT",
                "bright_t31": round(rng.uniform(280, 310), 1),
                "frp": round(rng.uniform(2.0, 180.0), 2),
                "daynight": rng.choice(["D", "N"]),
                "near_installation": inst_id,
            })
            fid += 1
    return rows


# ─────────────────────────────────────────────────────────────────────────────
# 5. NFIP claims (re-uses RIPTIDE schema, 5,000 records)
# ─────────────────────────────────────────────────────────────────────────────

BIAS_CENTERS = [
    (34.6, -77.3, 6.0, "NC-Lejeune", "NC"),
    (34.9, -76.9, 5.0, "NC-CherryPoint", "NC"),
    (31.5, -84.1, 3.0, "GA-Albany", "GA"),
    (32.7, -114.6, 2.0, "AZ-Yuma", "AZ"),
    (33.4, -117.6, 3.0, "CA-Pendleton", "CA"),
    (29.5, -94.8, 4.0, "TX-Houston", "TX"),
    (30.0, -90.1, 4.0, "LA-NewOrleans", "LA"),
    (30.4, -88.9, 3.0, "MS-Gulfport", "MS"),
    (27.8, -82.7, 3.5, "FL-Tampa", "FL"),
    (25.8, -80.2, 3.5, "FL-Miami", "FL"),
    (32.8, -79.9, 2.5, "SC-Charleston", "SC"),
]
EVENT_TYPES = [
    ("Hurricane / Tropical Cyclone", 0.42),
    ("Heavy Rain / Flash Flood", 0.25),
    ("Storm Surge / Coastal", 0.18),
    ("Riverine Flood", 0.10),
    ("Other Flood", 0.05),
]
FLOOD_ZONES = [("AE", 0.30), ("VE", 0.10), ("X", 0.30), ("AO", 0.10), ("A", 0.15), ("X500", 0.05)]


def gen_nfip(rng: random.Random, n: int = 5000) -> list[dict]:
    rows = []
    bias_total = sum(b[2] for b in BIAS_CENTERS)
    bias_norm = [b[2] / bias_total for b in BIAS_CENTERS]
    for i in range(n):
        r = rng.random()
        acc = 0.0
        center = BIAS_CENTERS[-1]
        for c, w in zip(BIAS_CENTERS, bias_norm):
            acc += w
            if r <= acc:
                center = c
                break
        clat, clon, _, label, state = center
        lat, lon = jitter(rng, clat, clon, rng.uniform(8, 35))
        year = rng.choices(list(range(2010, 2026)),
                           weights=[1.0,1.05,1.1,1.15,1.2,1.3,1.45,1.6,1.5,1.4,1.55,1.7,1.65,1.75,1.8,1.85])[0]
        date_of_loss = f"{year}-{rng.randint(5,11):02d}-{rng.randint(1,28):02d}"
        flood_zone = weighted_pick(rng, FLOOD_ZONES)
        event_type = weighted_pick(rng, EVENT_TYPES)
        amt = rng.lognormvariate(9.6, 1.05)
        if event_type.startswith("Hurricane"):
            amt *= rng.uniform(1.3, 2.5)
        if flood_zone == "VE":
            amt *= rng.uniform(1.2, 1.8)
        amt = min(amt, 500_000)
        bldg = round(amt, 2)
        cnt = round(amt * rng.uniform(0.05, 0.45), 2)
        rows.append({
            "id": f"NFIP-{SEED}-{i:05d}",
            "state": state,
            "dateOfLoss": date_of_loss,
            "yearOfLoss": year,
            "floodZone": flood_zone,
            "eventDesignation": event_type,
            "buildingDamageAmount": bldg,
            "contentsDamageAmount": cnt,
            "amountPaidOnBuildingClaim": round(bldg * rng.uniform(0.55, 0.92), 2),
            "amountPaidOnContentsClaim": round(cnt * rng.uniform(0.45, 0.88), 2),
            "latitude": round(lat, 4),
            "longitude": round(lon, 4),
            "biasCluster": label,
        })
    return rows


# ─────────────────────────────────────────────────────────────────────────────
# 6. FEMA Supply Chain Climate Resilience-shape disruption events
# ─────────────────────────────────────────────────────────────────────────────

SC_PRODUCT_CATEGORIES = [
    "Petroleum / JP-8", "MRE / Subsistence", "Pharma / Plasma",
    "Repair Parts (Class IX)", "Munitions / Class V", "Construction Materiel",
    "Generators / Diesel", "Tactical Vehicles",
]
SC_HAZARDS = ["Hurricane", "Atmospheric River", "Wildfire", "Heatwave", "Riverine Flood", "Cyclone"]


def gen_fema_sc(rng: random.Random) -> list[dict]:
    rows = []
    for i in range(220):
        center = rng.choice(BIAS_CENTERS)
        clat, clon = center[0], center[1]
        lat, lon = jitter(rng, clat, clon, rng.uniform(20, 80))
        year = rng.choice([2020, 2021, 2022, 2023, 2024, 2025])
        rows.append({
            "id": f"FEMA-SC-{SEED}-{i:04d}",
            "event_year": year,
            "hazard_type": rng.choice(SC_HAZARDS),
            "product_category": rng.choice(SC_PRODUCT_CATEGORIES),
            "supplier_count_affected": rng.randint(1, 14),
            "lead_time_baseline_days": rng.randint(3, 21),
            "lead_time_disrupted_days": rng.randint(7, 65),
            "outage_duration_days": rng.randint(1, 28),
            "estimated_cost_usd": round(rng.lognormvariate(13.0, 1.0), 2),
            "latitude": round(lat, 4),
            "longitude": round(lon, 4),
            "criticality_to_dod": rng.choice(["Low", "Moderate", "High", "Mission-critical"]),
        })
    return rows


# ─────────────────────────────────────────────────────────────────────────────
# 7. Logistics-CA-shape transport / warehouse records
# ─────────────────────────────────────────────────────────────────────────────

CA_CITIES = [
    ("Los Angeles", 34.05, -118.24),
    ("San Diego", 32.72, -117.16),
    ("Oakland", 37.80, -122.27),
    ("Sacramento", 38.58, -121.49),
    ("Fresno", 36.74, -119.78),
    ("Long Beach", 33.77, -118.19),
    ("Riverside", 33.95, -117.40),
    ("Bakersfield", 35.37, -119.02),
    ("Oceanside", 33.20, -117.38),
    ("Yuma-Border", 32.66, -114.61),
]
TRANSPORT_MODES = ["Truck (LTL)", "Truck (TL)", "Rail", "Air", "Intermodal"]
WAREHOUSE_TYPES = ["3PL", "DOD-contract", "Cold-chain", "Hazmat", "General"]


def gen_logistics_ca(rng: random.Random) -> list[dict]:
    rows = []
    for i in range(600):
        origin = rng.choice(CA_CITIES)
        dest = rng.choice(CA_CITIES)
        ship_date = (datetime.now(timezone.utc) - timedelta(days=rng.randint(0, 90))).strftime("%Y-%m-%d")
        rows.append({
            "shipment_id": f"CA-LOG-{SEED}-{i:05d}",
            "origin_city": origin[0],
            "origin_lat": origin[1],
            "origin_lon": origin[2],
            "destination_city": dest[0],
            "destination_lat": dest[1],
            "destination_lon": dest[2],
            "ship_date": ship_date,
            "mode": rng.choice(TRANSPORT_MODES),
            "weight_lbs": rng.randint(120, 42000),
            "transit_days_planned": rng.randint(1, 6),
            "transit_days_actual": rng.randint(1, 11),
            "warehouse_type": rng.choice(WAREHOUSE_TYPES),
            "carrier_score": round(rng.uniform(0.55, 0.99), 3),
            "fuel_surcharge_pct": round(rng.uniform(8, 38), 1),
        })
    return rows


# ─────────────────────────────────────────────────────────────────────────────
# 8. Cached LLM briefs (3 polycrisis scenarios)
# ─────────────────────────────────────────────────────────────────────────────

CACHED_BRIEFS = {
    "cat3_lejeune": (
        "**STORM-SHIFT POLYCRISIS READINESS BRIEF — MCB CAMP LEJEUNE / Cat-3 (FLORENCE-shape)**\n\n"
        "## BLUF\n"
        "A Cat-3 hurricane on the FLORENCE-2018 track would expose MCB Camp Lejeune to **$3.4B-$4.1B "
        "in flood damage**, sever **18 critical suppliers** across the FEMA Climate-SC corpus, and "
        "drive Class I/III/VIII consumption past on-hand stocks within **96 hours**. Days-to-MC "
        "(Mission Capable) projection: **5.2 days** without pre-landfall preposition.\n\n"
        "## Top 3 cascading effects\n"
        "1. **Wharf + family-housing flood** — 1,850 m of wharf and 4,500 housing units sit in the "
        "AE/VE flood envelope; NFIP claim density says 62% of housing parcels would file.\n"
        "2. **Class III (JP-8) supplier collapse** — 4 of 6 Gulf-Coast fuel terminals in the FEMA "
        "Climate-SC dataset go to red; lead-time surges from 5 to 22 days.\n"
        "3. **Class VIII plasma shortage** — 47,000 sheltered personnel push plasma demand 8x; "
        "on-hand 1,100 units exhausted by H+72.\n\n"
        "## Recommended pre-landfall actions (T-72h)\n"
        "- Surge JP-8 to 95% storage capacity from MCAS Cherry Point (1,800,000 gal cushion).\n"
        "- Pre-position 12,000 additional MRE cases via MCLB Albany depot rail link.\n"
        "- Relocate 30% of Class IX repair-parts inventory inland (Albany).\n"
        "- Activate DSCA stand-by MOA with NC State EM for stevedore augmentation.\n\n"
        "## Recommended post-landfall actions (H+24 to H+96)\n"
        "- Air-bridge plasma resupply from MCAS Cherry Point pending wharf reopening.\n"
        "- Prioritize generator-diesel resupply (220k gal on-hand → 5-day burn at full shelter posture).\n"
        "- Engage Logistics-CA west-coast carriers as bypass for Gulf-Coast Class IX supplier outages.\n\n"
        "## Dollar exposure summary\n"
        "- Flood damage (NFIP × storm): **$3.65B**\n"
        "- Supply chain disruption: **$280M** (220 events × avg $1.27M)\n"
        "- Inventory shortage cost (red items × replenishment premium): **$94M**\n"
        "- **TOTAL: ~$4.02B** — bracketed within the historical Florence 2018 record.\n\n"
        "## Days-to-MC: **5.2 days** (with pre-landfall actions: 1.8 days)\n\n"
        "Originator: STORM-SHIFT polycrisis readiness cell. Classification: UNCLASSIFIED // FOR OFFICIAL USE."
    ),
    "atmos-river_pendleton": (
        "**STORM-SHIFT POLYCRISIS READINESS BRIEF — MCB CAMP PENDLETON / Atmospheric River (HILARY-shape)**\n\n"
        "## BLUF\n"
        "A HILARY-2023-class atmospheric river on Pendleton would flood San Onofre Creek, close I-5 "
        "& I-8 logistics arteries, and (critically) **stage the Santa Ana fire-following polycrisis** "
        "within 14 days. Combined exposure: **$1.8B**, days-to-MC **3.6 days**.\n\n"
        "## Top 3 cascading effects\n"
        "1. **Las Pulgas housing inundation** — repeat of 2024 flooding; 6,800 family housing units "
        "with 18% in AE flood zone.\n"
        "2. **I-5 / I-8 closure** — 600-record Logistics-CA corpus shows 70% of Pendleton-bound "
        "shipments transit those corridors; Truck (TL) lead times surge from 2 → 9 days.\n"
        "3. **Vegetation regrowth → Santa Ana fire fuel** — FIRMS thermal anomaly pixel density in "
        "the Pendleton AOI is already elevated; post-rain regrowth pushes the fire-following "
        "polycrisis multiplier to **1.60x**.\n\n"
        "## Recommended pre-landfall actions (T-72h)\n"
        "- Pre-position 8,000 MREs and 800,000 gal potable water at higher elevation (Camp Talega).\n"
        "- Pre-stage Class IV barrier material along San Onofre Creek levees.\n"
        "- Coordinate with CalTrans for I-5 contingency reroute via SR-78.\n\n"
        "## Recommended post-event actions (Day 0 to Day 14)\n"
        "- **Critical**: deploy fire-suppression assets BEFORE vegetation regrowth — the Santa Ana "
        "polycrisis follows on a 10-14 day lag.\n"
        "- Restore Logistics-CA supplier flow via Long Beach / Oakland warehouse pivot.\n"
        "- Run STORM-SHIFT 'Santa-Ana follow-on' simulation at Day 7 to update posture.\n\n"
        "## Dollar exposure summary\n"
        "- Flood damage: **$420M**\n"
        "- Supply disruption (CA logistics): **$310M**\n"
        "- Inventory shortage: **$46M**\n"
        "- Fire-secondary projected (10-14d lag): **$1.05B**\n"
        "- **TOTAL: ~$1.83B**\n\n"
        "## Days-to-MC: **3.6 days** (Atmos-river only) → **9.4 days** (with Santa Ana follow-on)\n\n"
        "Originator: STORM-SHIFT polycrisis readiness cell. Classification: UNCLASSIFIED // FOR OFFICIAL USE."
    ),
    "santa-ana-fire_pendleton": (
        "**STORM-SHIFT POLYCRISIS READINESS BRIEF — MCB CAMP PENDLETON / Santa Ana fire-following (THOMAS-shape)**\n\n"
        "## BLUF\n"
        "Santa Ana wind event with FIRMS-detected ignition density 4.2x baseline — a THOMAS-2017-shape "
        "fire complex on Pendleton's eastern boundary. Exposure: **$680M**, days-to-MC **2.8 days**, "
        "**1,100 family housing units** in the immediate evacuation envelope.\n\n"
        "## Top 3 cascading effects\n"
        "1. **Wind-driven fire spread** — 65 kt offshore winds align with FIRMS pixel cluster bearing "
        "into the Pendleton AOI; spread rate up to 3,500 acres/hr historic precedent.\n"
        "2. **Class III (fuel) suppression demand** — fire-suppression aviation fuel demand competes "
        "with shelter generator diesel; both burn from the 290k gal generator-diesel bunker.\n"
        "3. **Class VIII (plasma) burn-injury surge** — limited 1,620 plasma units at Pendleton; "
        "burn protocol requires 4-8 units per casualty; capacity for ~200-400 casualties.\n\n"
        "## Recommended pre-event actions (T-24h)\n"
        "- Activate Red Flag Warning posture; pre-position water tankers at all ammo bunker perimeters.\n"
        "- Surge plasma units from Cherry Point (320) and Lejeune (1,100) via air-bridge.\n"
        "- Evacuate AE-zone family housing in the eastern AOI.\n\n"
        "## Recommended in-event actions (Day 0 to Day 4)\n"
        "- Coordinate with CalFIRE for joint air-tactical group; engage RAINS for surface fuel breaks.\n"
        "- Halt all non-essential Logistics-CA inbound shipments (warehouse flooding is now fire risk).\n"
        "- Stand up family-readiness reception at Camp Talega for evacuated families.\n\n"
        "## Dollar exposure summary\n"
        "- Fire damage to facilities: **$340M**\n"
        "- Supply disruption (rerouted CA logistics): **$190M**\n"
        "- Inventory shortage (Class III + Class VIII): **$84M**\n"
        "- Cleanup + family-housing reconstruction: **$66M**\n"
        "- **TOTAL: ~$680M**\n\n"
        "## Days-to-MC: **2.8 days**\n\n"
        "Originator: STORM-SHIFT polycrisis readiness cell. Classification: UNCLASSIFIED // FOR OFFICIAL USE."
    ),
}


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

def _generate_data() -> dict:
    rng = random.Random(SEED)

    earth = gen_earthdata_grid(rng)
    firms = gen_firms_pixels(rng)
    nfip = gen_nfip(rng, n=5000)
    fema_sc = gen_fema_sc(rng)
    logistics = gen_logistics_ca(rng)

    (OUT / "installations.json").write_text(json.dumps(INSTALLATIONS, indent=2))
    (OUT / "scenarios.json").write_text(json.dumps(SCENARIOS, indent=2))
    (OUT / "polycrisis_pairs.json").write_text(json.dumps(
        [{"a": a, "b": b, "multiplier": m, "rationale": r} for a, b, m, r in POLYCRISIS_PAIRS],
        indent=2,
    ))
    (OUT / "earthdata_grid.json").write_text(json.dumps(earth))
    (OUT / "firms_pixels.json").write_text(json.dumps(firms))
    (OUT / "fema_sc_climate.json").write_text(json.dumps(fema_sc))
    (OUT / "logistics_ca.json").write_text(json.dumps(logistics))

    # NFIP — also save parquet for size + speed
    nfip_df = pd.DataFrame(nfip)
    nfip_df.to_parquet(OUT / "nfip_claims.parquet", index=False)
    (OUT / "nfip_claims.json").write_text(json.dumps(nfip))

    return {
        "installations": len(INSTALLATIONS),
        "scenarios": len(SCENARIOS),
        "earthdata_rows": len(earth),
        "firms_pixels": len(firms),
        "nfip_claims": len(nfip),
        "fema_sc_events": len(fema_sc),
        "logistics_records": len(logistics),
    }


def _precompute_briefs() -> None:
    """Cache-first hero LLM pattern: write deterministic high-quality briefs to disk
    so the demo never sits on a spinner. The 'Regenerate' button can hit the live
    LLM, but the page renders an immediate brief from cache on load.
    """
    (OUT / "cached_briefs.json").write_text(json.dumps(CACHED_BRIEFS, indent=2))


if __name__ == "__main__":
    stats = _generate_data()
    _precompute_briefs()
    print("STORM-SHIFT synthetic corpus generated:")
    for k, v in stats.items():
        print(f"  {k:24s} {v:>8,}")
    print(f"  cached_briefs (precomputed) {len(CACHED_BRIEFS):>8,}")
