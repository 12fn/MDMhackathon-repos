"""Synthesize a 30-day hourly fused Earth-observation timeseries for 4 named AOIs.

Emits one flat CSV per AOI plus a manifest. Variables per location:

  * hs_m         — significant wave height (m)        [WAVEWATCH III analog]
  * wind_kn      — 10-m wind speed (knots)            [MERRA-2 analog]
  * precip_mmhr  — precipitation rate (mm/hr)         [GPM IMERG analog]
  * sst_c        — sea-surface temperature (deg C)    [GHRSST analog]
  * cloud_pct    — cloud cover (%)                    [MODIS analog]

Generation: sinusoid (diurnal + multi-day swell) + Gaussian noise + occasional
storm events with bell-curve intensity. Deterministic seed.

Bucket C swap: this file emits flat per-AOI hourly CSV. Real NASA Earthdata is
multi-dimensional HDF / NetCDF rasters served from Earthdata Cloud
(https://search.earthdata.nasa.gov). To go live, replace `gen_location` with an
xarray / rioxarray loader that pulls MERRA-2 (M2T1NXSLV), GPM IMERG
(GPM_3IMERGHH), GHRSST (MUR), MODIS (MOD06_L2), and a WW3 ensemble for the AOI
bbox + horizon, reduces each grid to an hourly point/mean timeseries, and
writes the same {timestamp, hs_m, wind_kn, precip_mmhr, sst_c, cloud_pct}
schema the agent already consumes — no agent changes required.
"""
from __future__ import annotations

import math
import random
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

OUT = Path(__file__).resolve().parent
HOURS = 24 * 30  # 30 days
START = datetime(2026, 5, 1, 0, 0, tzinfo=timezone.utc)

# (slug, display name, lat, lon, climate profile)
LOCATIONS = [
    {
        "slug": "subic_bay",
        "name": "Subic Bay, Philippines",
        "lat": 14.79, "lon": 120.27,
        "hs_base": 1.1, "hs_amp": 0.6,
        "wind_base": 8.0, "wind_amp": 4.0,
        "precip_base": 0.15, "storm_p": 0.010,
        "sst_base": 28.5, "sst_amp": 0.6,
        "cloud_base": 55, "cloud_amp": 25,
    },
    {
        "slug": "yemen_coast",
        "name": "Yemen Coast (Bab-el-Mandeb)",
        "lat": 12.59, "lon": 43.32,
        "hs_base": 0.7, "hs_amp": 0.4,
        "wind_base": 14.0, "wind_amp": 6.0,
        "precip_base": 0.0, "storm_p": 0.002,
        "sst_base": 30.2, "sst_amp": 0.4,
        "cloud_base": 18, "cloud_amp": 14,
    },
    {
        "slug": "norway_fjord",
        "name": "Vestfjorden, Norway",
        "lat": 68.10, "lon": 14.30,
        "hs_base": 1.6, "hs_amp": 1.2,
        "wind_base": 16.0, "wind_amp": 9.0,
        "precip_base": 0.30, "storm_p": 0.020,
        "sst_base": 7.2, "sst_amp": 0.5,
        "cloud_base": 70, "cloud_amp": 20,
    },
    {
        "slug": "marforpac_training",
        "name": "MARFORPAC Training Area (PMRF, Kauai)",
        "lat": 22.02, "lon": -159.78,
        "hs_base": 1.4, "hs_amp": 0.7,
        "wind_base": 12.0, "wind_amp": 5.0,
        "precip_base": 0.10, "storm_p": 0.008,
        "sst_base": 25.4, "sst_amp": 0.5,
        "cloud_base": 45, "cloud_amp": 22,
    },
]


def diurnal(hour: int, amp: float, phase: float = 0.0) -> float:
    return amp * math.sin(2 * math.pi * (hour / 24.0) + phase)


def synodic(day: float, amp: float, period_days: float = 7.0) -> float:
    return amp * math.sin(2 * math.pi * day / period_days)


def gen_location(loc: dict, rng: random.Random) -> pd.DataFrame:
    rows = []
    storm_remaining = 0
    storm_intensity = 1.0

    for h in range(HOURS):
        ts = START + timedelta(hours=h)
        day = h / 24.0

        # base + diurnal + multi-day swell pattern
        hs = loc["hs_base"] + 0.5 * synodic(day, loc["hs_amp"], 6.5) + rng.gauss(0, 0.08)
        wind = loc["wind_base"] + diurnal(h, 1.5) + synodic(day, loc["wind_amp"], 5.0) + rng.gauss(0, 1.2)
        precip = max(0.0, loc["precip_base"] + rng.gauss(0, 0.05))
        sst = loc["sst_base"] + diurnal(h, loc["sst_amp"], phase=-math.pi / 3) + synodic(day, 0.2, 14) + rng.gauss(0, 0.05)
        cloud = loc["cloud_base"] + diurnal(h, 8.0) + synodic(day, loc["cloud_amp"], 4.0) + rng.gauss(0, 4)

        # Storm onset?
        if storm_remaining == 0 and rng.random() < loc["storm_p"]:
            storm_remaining = rng.randint(8, 36)  # 8 to 36 hours of weather event
            storm_intensity = rng.uniform(1.5, 3.0)

        if storm_remaining > 0:
            # Bell-curve modulation across storm duration so peak is mid-event
            phase = 1.0 - abs((storm_remaining - 12) / 24.0)  # peak around mid
            storm_factor = max(0.4, phase) * storm_intensity
            hs += 1.4 * storm_factor + rng.gauss(0, 0.15)
            wind += 12 * storm_factor + rng.gauss(0, 1.5)
            precip += 3.5 * storm_factor + rng.gauss(0, 0.4)
            cloud = min(100, cloud + 25 * storm_factor)
            storm_remaining -= 1

        cloud = max(0, min(100, cloud))
        wind = max(0, wind)
        hs = max(0.05, hs)
        precip = max(0, precip)

        rows.append({
            "timestamp": ts.isoformat(),
            "hs_m": round(hs, 2),
            "wind_kn": round(wind, 1),
            "precip_mmhr": round(precip, 2),
            "sst_c": round(sst, 2),
            "cloud_pct": round(cloud, 1),
        })

    return pd.DataFrame(rows)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    rng = random.Random(1776)
    manifest = []
    for loc in LOCATIONS:
        # Use a per-location offset of the seed so each AOI has distinct weather
        local_rng = random.Random(rng.randint(0, 10**9))
        df = gen_location(loc, local_rng)
        out_path = OUT / f"{loc['slug']}.csv"
        df.to_csv(out_path, index=False)
        manifest.append({
            "slug": loc["slug"],
            "name": loc["name"],
            "lat": loc["lat"],
            "lon": loc["lon"],
            "rows": len(df),
            "csv": out_path.name,
        })
        print(f"wrote {out_path.name} ({len(df)} rows)")

    import json
    (OUT / "manifest.json").write_text(json.dumps({
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "horizon_start_utc": START.isoformat(),
        "hours": HOURS,
        "locations": manifest,
        "sources_simulated": [
            "NASA MERRA-2 (10-m winds)",
            "NASA GPM IMERG (precipitation rate)",
            "NASA GHRSST (sea-surface temperature)",
            "NASA MODIS Terra/Aqua (cloud cover)",
            "WAVEWATCH III ensemble (significant wave height)",
        ],
    }, indent=2))
    print("wrote manifest.json")


if __name__ == "__main__":
    main()
