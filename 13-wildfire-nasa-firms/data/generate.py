"""WILDFIRE synthetic data generator — 200-pixel FIRMS-shape fire pixels + wind grid.

This is a Bucket A template: the data shape is real, the values are synthetic.
Outputs match NASA FIRMS NRT CSV columns exactly so swapping in a live pull is a
one-line path change.

Generates (all under data/, seed 1776 for reproducibility):
    fire_pixels.json       200 fire pixels biased near western Marine bases
    fire_pixels_firms.csv  Same data in NASA FIRMS NRT CSV shape
    wind_grid.csv          Sparse wind vector grid (lat, lon, u_mps, v_mps, valid_at)
    installations.json     5 installation polygons + inventory blocks
    timeline.json          6-hour synthetic growth — list of {step, t, fire_ids, label}

Real-FIRMS swap pointer:
    1. Get a free MAP_KEY: https://firms.modaps.eosdis.nasa.gov/api/map_key/
    2. Pull a CSV from the FIRMS Area or Country API:
       https://firms.modaps.eosdis.nasa.gov/api/area/
    3. Drop it in data/ and update the path constant in src/api.py.

Required FIRMS columns (this generator emits all of them):
    latitude, longitude, brightness, scan, track, acq_date, acq_time,
    satellite, confidence, frp, daynight
"""
from __future__ import annotations

import csv
import json
import math
import random
from datetime import datetime, timedelta, timezone
from pathlib import Path

SEED = 1776
N_PIXELS = 200
OUT = Path(__file__).parent

# ---------------------------------------------------------------------------
# Installations — verbatim names + real-ish lat/lon centroids.
# Each polygon is a rough rectangle around the centroid.
# ---------------------------------------------------------------------------
INSTALLATIONS = [
    {
        "id": "pendleton",
        "name": "MCB Camp Pendleton",
        "state": "CA",
        "centroid": [33.3858, -117.5631],
        "polygon": [
            [33.55, -117.71],
            [33.55, -117.32],
            [33.21, -117.32],
            [33.21, -117.71],
        ],
        "personnel": 70000,
        "inventory": {
            "family_housing_units": 6800,
            "barracks": 140,
            "ammo_storage_bunkers": 24,
            "aviation_parking_aircraft": 64,
            "motor_pools": 28,
            "fuel_storage_gal": 3_200_000,
            "critical_c2_nodes": 6,
        },
        "fire_history": (
            "Burned 6+ times in the last decade — Las Pulgas (2014), "
            "Talega (2017), De Luz (2018, 2020, 2022, 2024). 2014 fire forced "
            "evacuation of family housing in Las Pulgas and San Onofre."
        ),
        "evacuation_routes": ["Vandegrift Blvd", "Stuart Mesa Rd", "Basilone Rd", "I-5 South"],
        "assembly_areas": ["DelMar Beach AAA", "Camp Horno LZ", "23 Area Parade Deck"],
    },
    {
        "id": "twentynine-palms",
        "name": "MCAGCC Twentynine Palms",
        "state": "CA",
        "centroid": [34.2378, -116.0542],
        "polygon": [
            [34.55, -116.40],
            [34.55, -115.65],
            [33.92, -115.65],
            [33.92, -116.40],
        ],
        "personnel": 11000,
        "inventory": {
            "family_housing_units": 2200,
            "barracks": 48,
            "ammo_storage_bunkers": 36,
            "aviation_parking_aircraft": 22,
            "motor_pools": 14,
            "fuel_storage_gal": 1_900_000,
            "critical_c2_nodes": 4,
        },
        "fire_history": (
            "Largest USMC training installation. Range fires from live-fire "
            "exercises are routine; high desert fuel loads spike Jun-Sep."
        ),
        "evacuation_routes": ["SR-62 West", "Adobe Rd", "Condor Rd"],
        "assembly_areas": ["Camp Wilson MEDEVAC LZ", "Mainside Parade Field"],
    },
    {
        "id": "yuma",
        "name": "MCAS Yuma",
        "state": "AZ",
        "centroid": [32.6566, -114.6058],
        "polygon": [
            [32.74, -114.69],
            [32.74, -114.51],
            [32.57, -114.51],
            [32.57, -114.69],
        ],
        "personnel": 5600,
        "inventory": {
            "family_housing_units": 1100,
            "barracks": 22,
            "ammo_storage_bunkers": 14,
            "aviation_parking_aircraft": 48,
            "motor_pools": 4,
            "fuel_storage_gal": 1_400_000,
            "critical_c2_nodes": 2,
        },
        "fire_history": (
            "Sonoran Desert grass fires after wet winters; F-35B + AV-8B "
            "flightline parking is the protect-priority asset."
        ),
        "evacuation_routes": ["32nd St", "Avenue 3E", "I-8 East"],
        "assembly_areas": ["Mainside Parade Deck", "BX Parking"],
    },
    {
        "id": "lejeune-training",
        "name": "MCB Camp Lejeune Training Area",
        "state": "NC",
        "centroid": [34.6840, -77.3464],
        "polygon": [
            [34.86, -77.55],
            [34.86, -77.15],
            [34.51, -77.15],
            [34.51, -77.55],
        ],
        "personnel": 47000,
        "inventory": {
            "family_housing_units": 4500,
            "barracks": 92,
            "ammo_storage_bunkers": 18,
            "aviation_parking_aircraft": 0,
            "motor_pools": 12,
            "fuel_storage_gal": 2_400_000,
            "critical_c2_nodes": 4,
        },
        "fire_history": (
            "Prescribed burns + lightning-ignited longleaf pine fires; "
            "~3,000 ac/yr historical. Greater Sandy Run burns adjacent."
        ),
        "evacuation_routes": ["Holcomb Blvd", "Sneads Ferry Rd", "NC-172"],
        "assembly_areas": ["Onslow Beach AAA", "Tarawa Terrace LZ"],
    },
    {
        "id": "quantico",
        "name": "MCB Quantico",
        "state": "VA",
        "centroid": [38.5223, -77.3047],
        "polygon": [
            [38.62, -77.45],
            [38.62, -77.20],
            [38.40, -77.20],
            [38.40, -77.45],
        ],
        "personnel": 16000,
        "inventory": {
            "family_housing_units": 1400,
            "barracks": 36,
            "ammo_storage_bunkers": 8,
            "aviation_parking_aircraft": 12,
            "motor_pools": 8,
            "fuel_storage_gal": 800_000,
            "critical_c2_nodes": 5,
        },
        "fire_history": (
            "Mid-Atlantic hardwood; range fires occasional. TBS / OCS "
            "schools represent high-density personnel risk."
        ),
        "evacuation_routes": ["Russell Rd", "Fuller Rd", "I-95 North"],
        "assembly_areas": ["Butler Stadium", "TBS Parade Deck"],
    },
]

# ---------------------------------------------------------------------------
# Bias centers for fire pixel placement — heavy bias toward Pendleton + 29P + Yuma
# (this is the demo hero), light bias near Lejeune & Quantico, scattered CONUS.
# (lat, lon, weight, label, base_radius_mi, hot)
# 'hot' means pixels here are part of the actively-growing fire complex
# ---------------------------------------------------------------------------
BIAS_CENTERS = [
    # PENDLETON COMPLEX — the demo hero. Three fires upwind of base.
    (33.55, -117.42, 9.0, "PENDLETON-RIVERSIDE", 8, True),    # NE of base, ~8 mi
    (33.30, -117.32, 6.0, "PENDLETON-CHRISTIANITOS", 5, True),# E of base, ~5 mi
    (33.62, -117.78, 3.0, "PENDLETON-SAN-MATEO", 12, True),   # NW of base, ~12 mi
    # 29 PALMS — desert range fires
    (34.42, -116.20, 4.0, "29P-COTTONWOOD", 15, True),
    (34.10, -115.90, 3.0, "29P-PINTO-BASIN", 18, True),
    # YUMA — Sonoran grass
    (32.85, -114.45, 3.0, "YUMA-LAGUNA", 14, True),
    # LEJEUNE — prescribed-burn escape proximate
    (34.78, -77.45, 2.5, "LEJEUNE-GSR", 10, False),
    # Quantico — light
    (38.55, -77.32, 1.5, "QUANTICO-MARINE-CORPS-HERITAGE", 6, False),
    # Background CONUS scatter (real wildfire-prone areas)
    (40.5, -121.5, 2.0, "CA-LASSEN", 60, False),
    (39.0, -120.0, 2.0, "CA-TAHOE-NF", 50, False),
    (37.5, -119.5, 1.5, "CA-SIERRA-NF", 50, False),
    (44.5, -113.0, 1.2, "ID-SALMON", 60, False),
    (47.0, -120.0, 1.2, "WA-CASCADES", 60, False),
    (45.5, -121.0, 1.2, "OR-MT-HOOD", 50, False),
    (35.5, -106.5, 1.5, "NM-SANTA-FE", 50, False),
    (39.5, -106.0, 1.2, "CO-WHITE-RIVER", 50, False),
    (46.0, -110.5, 1.0, "MT-YELLOWSTONE", 50, False),
    (32.0, -83.0, 1.0, "GA-OCONEE-NF", 40, False),
    (33.0, -82.0, 0.8, "SC-COASTAL", 40, False),
]

SATELLITES = ["VIIRS_SNPP", "VIIRS_NOAA20", "VIIRS_NOAA21", "MODIS_TERRA", "MODIS_AQUA"]
DAYNIGHT = ["D", "N"]


def jitter_around(rng: random.Random, lat: float, lon: float, miles: float):
    """Return random lat/lon within `miles` of (lat, lon)."""
    r = rng.random() * miles / 69.0
    theta = rng.random() * 2 * math.pi
    dlat = r * math.cos(theta)
    dlon = r * math.sin(theta) / max(0.2, math.cos(math.radians(lat)))
    return lat + dlat, lon + dlon


def gen_fire_pixels(rng: random.Random) -> list[dict]:
    """Generate N_PIXELS FIRMS-shaped pixels."""
    weights = [c[2] for c in BIAS_CENTERS]
    total = sum(weights)
    norm = [w / total for w in weights]

    # Fixed observation window: T-6h .. T0 (now). All pixels in this window.
    t_now = datetime(2026, 4, 24, 18, 0, tzinfo=timezone.utc)
    t_start = t_now - timedelta(hours=6)

    rows = []
    for i in range(N_PIXELS):
        # Pick bias center.
        r = rng.random()
        acc = 0.0
        center = BIAS_CENTERS[-1]
        for c, w in zip(BIAS_CENTERS, norm):
            acc += w
            if r <= acc:
                center = c
                break
        clat, clon, _, label, base_r, hot = center

        # Tighter cluster for hot fires; broader for background.
        radius = rng.uniform(base_r * 0.2, base_r * 1.0)
        lat, lon = jitter_around(rng, clat, clon, radius)

        # Time within the 6-hr window — hot fires skew later (fire growing).
        if hot:
            frac = rng.betavariate(2.5, 1.5)  # late-skewed
        else:
            frac = rng.random()
        t = t_start + (t_now - t_start) * frac

        # Brightness 305-420 K (typical FIRMS), FRP 1-450 MW (lognormal).
        brightness = round(rng.uniform(305, 420), 1)
        frp = round(min(rng.lognormvariate(2.6, 1.0), 450.0), 1)
        # Hot pixels burn brighter on average.
        if hot:
            brightness = round(min(brightness + rng.uniform(5, 35), 420.0), 1)
            frp = round(min(frp * rng.uniform(1.4, 3.0), 450.0), 1)

        # Confidence: nominal/low/high (VIIRS) or numeric (MODIS).
        sat = rng.choice(SATELLITES)
        if sat.startswith("VIIRS"):
            confidence = rng.choices(["n", "h", "l"], weights=[0.65, 0.30, 0.05])[0]
        else:
            confidence = rng.randint(30, 100)

        rows.append({
            "id": f"FIRMS-{SEED}-{i:04d}",
            "latitude": round(lat, 4),
            "longitude": round(lon, 4),
            "brightness": brightness,
            "scan": round(rng.uniform(0.35, 0.85), 2),
            "track": round(rng.uniform(0.35, 0.75), 2),
            "acq_date": t.strftime("%Y-%m-%d"),
            "acq_time": t.strftime("%H%M"),
            "acq_datetime": t.isoformat(),
            "satellite": sat,
            "confidence": confidence,
            "frp": frp,
            "daynight": rng.choices(DAYNIGHT, weights=[0.62, 0.38])[0],
            "biasCluster": label,
            "hot": hot,
        })
    # Sort by time so the timeline can window them.
    rows.sort(key=lambda r: r["acq_datetime"])
    return rows


def gen_wind_grid(rng: random.Random) -> list[dict]:
    """Sparse synthetic wind grid — lat/lon, u_mps (east+), v_mps (north+).

    Centered around the four heavy-fire installations + a few background
    points. Pendleton dominant pattern: Santa Ana (E to W, dry, ~10-15 m/s).
    """
    t_now = datetime(2026, 4, 24, 18, 0, tzinfo=timezone.utc)
    grid = []

    # Helper
    def add(lat, lon, u, v, label):
        grid.append({
            "latitude": round(lat, 3),
            "longitude": round(lon, 3),
            "u_mps": round(u, 2),
            "v_mps": round(v, 2),
            "speed_mps": round(math.hypot(u, v), 2),
            "from_dir_deg": round((math.degrees(math.atan2(-u, -v)) + 360) % 360, 1),
            "valid_at": t_now.isoformat(),
            "label": label,
        })

    # Pendleton — Santa Ana flow E -> W (negative u), light southerly (positive v)
    for dlat in (-0.4, -0.2, 0.0, 0.2, 0.4):
        for dlon in (-0.4, -0.2, 0.0, 0.2, 0.4):
            base_u = rng.uniform(-15.0, -8.0)
            base_v = rng.uniform(-1.5, 2.5)
            add(33.40 + dlat, -117.50 + dlon, base_u, base_v, "PENDLETON-SANTA-ANA")
    # 29P — westerlies aloft, gusty surface
    for dlat in (-0.3, 0.0, 0.3):
        for dlon in (-0.4, 0.0, 0.4):
            add(34.24 + dlat, -116.05 + dlon,
                rng.uniform(6.0, 11.0), rng.uniform(-2.0, 4.0), "29P-WESTERLY")
    # Yuma — light variable
    for dlat in (-0.2, 0.0, 0.2):
        for dlon in (-0.2, 0.0, 0.2):
            add(32.65 + dlat, -114.60 + dlon,
                rng.uniform(-3.0, 4.0), rng.uniform(-3.0, 3.0), "YUMA-LIGHT")
    # Lejeune — onshore SE flow
    for dlat in (-0.2, 0.0, 0.2):
        for dlon in (-0.2, 0.0, 0.2):
            add(34.68 + dlat, -77.35 + dlon,
                rng.uniform(-6.0, -2.0), rng.uniform(2.0, 6.0), "LEJEUNE-SE-ONSHORE")
    # Quantico — westerly
    for dlat in (-0.2, 0.0, 0.2):
        for dlon in (-0.2, 0.0, 0.2):
            add(38.52 + dlat, -77.30 + dlon,
                rng.uniform(3.0, 7.0), rng.uniform(-1.0, 3.0), "QUANTICO-W")
    return grid


def gen_timeline(fire_pixels: list[dict]) -> list[dict]:
    """Walk the 6-hour observation window in 30-min steps.

    Each step includes the cumulative set of fire pixel IDs visible by then.
    The hero demo slider replays the burn growth.
    """
    if not fire_pixels:
        return []
    t_first = datetime.fromisoformat(fire_pixels[0]["acq_datetime"])
    t_last = datetime.fromisoformat(fire_pixels[-1]["acq_datetime"])
    total_min = max(60, int((t_last - t_first).total_seconds() / 60) + 30)
    steps = []
    n_steps = 12  # 6 hr / 30 min
    for i in range(n_steps + 1):
        t_step = t_first + timedelta(minutes=i * total_min / n_steps)
        visible = [p["id"] for p in fire_pixels
                   if datetime.fromisoformat(p["acq_datetime"]) <= t_step]
        # Rough label
        h = i * total_min / n_steps / 60.0
        steps.append({
            "step": i,
            "t": t_step.isoformat(),
            "elapsed_hr": round(h, 1),
            "fire_ids": visible,
            "n_visible": len(visible),
        })
    return steps


def main() -> None:
    rng = random.Random(SEED)
    fire_pixels = gen_fire_pixels(rng)
    wind = gen_wind_grid(rng)
    timeline = gen_timeline(fire_pixels)

    fp_path = OUT / "fire_pixels.json"
    wg_path = OUT / "wind_grid.csv"
    in_path = OUT / "installations.json"
    tl_path = OUT / "timeline.json"

    fp_path.write_text(json.dumps(fire_pixels, indent=2))
    in_path.write_text(json.dumps(INSTALLATIONS, indent=2))
    tl_path.write_text(json.dumps(timeline, indent=2))
    with wg_path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(wind[0].keys()))
        w.writeheader()
        w.writerows(wind)

    # Also write a FIRMS-shaped CSV for plug-in compat demos
    fp_csv = OUT / "fire_pixels_firms.csv"
    cols = ["latitude", "longitude", "brightness", "scan", "track",
            "acq_date", "acq_time", "satellite", "confidence", "frp", "daynight"]
    with fp_csv.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        for p in fire_pixels:
            w.writerow({k: p[k] for k in cols})

    print(f"Wrote synthetic FIRMS-style data:")
    print(f"  {fp_path}    ({len(fire_pixels)} pixels)")
    print(f"  {fp_csv}    (FIRMS-compatible CSV)")
    print(f"  {wg_path}    ({len(wind)} wind grid points)")
    print(f"  {in_path}    ({len(INSTALLATIONS)} installations)")
    print(f"  {tl_path}    ({len(timeline)} timeline steps)")

    # Summary stats
    hot = sum(1 for p in fire_pixels if p["hot"])
    by_cluster = {}
    for p in fire_pixels:
        by_cluster[p["biasCluster"]] = by_cluster.get(p["biasCluster"], 0) + 1
    print()
    print(f"Hot pixels (active fire complex): {hot}")
    print(f"Pixels per cluster:")
    for k, v in sorted(by_cluster.items(), key=lambda x: -x[1]):
        print(f"  {k:<35s} {v:3d}")


if __name__ == "__main__":
    main()
