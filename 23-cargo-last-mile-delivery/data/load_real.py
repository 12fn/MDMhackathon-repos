"""Real-data ingestion stub for CARGO.

Real dataset: **Last Mile Delivery (LaDe)** — public last-mile delivery
dataset released by Cainiao / Alibaba. CSV exports include:
  - order-level: order_id, courier_id, ts, lat, lon, accept_time, delivery_time
  - courier-level: courier_id, region, vehicle_type
  - geographic: AOI/grid features

To plug LaDe into CARGO without changing src/ code:

  1. Download a city slice (e.g. `LaDe_pickup_Shanghai.csv`).
  2. Group by `region` → these become "squad positions" (8 dispersed nodes).
  3. Sum `weight` (or `parcel_count` x avg_weight) per region → demand_total_lb.
  4. The earliest `accept_time` in each region → priority window.
  5. Vehicle table stays synthetic (LaDe doesn't carry military platforms);
     only the *demand* shape comes from LaDe.
  6. Threat zones — none in the public dataset; keep the synthetic file or
     overlay a per-deployment intel feed (RFF/RTI) at runtime.

Set REAL_DATA_PATH=/path/to/LaDe_pickup_<city>.csv and call load_real().
"""
from __future__ import annotations

import os
from pathlib import Path

import pandas as pd


def load_real() -> dict:
    """Returns {"squads": [...], "depots": [...]} in the same shape as
    data/generate.py emits. Vehicle + threat-zone files are reused unchanged.
    """
    path = os.getenv("REAL_DATA_PATH")
    if not path:
        raise NotImplementedError(
            "REAL_DATA_PATH not set. Download LaDe (Cainiao/Alibaba) and "
            "point REAL_DATA_PATH at a city CSV. See module docstring "
            "for the schema mapping."
        )
    df = pd.read_csv(path)
    # Fold into ~8 region "squads" — pick top-8 by parcel count
    if "region_id" not in df.columns:
        raise ValueError(
            f"{path} has no 'region_id' column — not a LaDe-style export?"
        )
    grp = df.groupby("region_id").agg(
        lat=("lat", "mean"),
        lon=("lng", "mean") if "lng" in df.columns else ("lon", "mean"),
        parcels=("order_id", "count"),
    ).nlargest(8, "parcels").reset_index()
    callsigns = ["ALPHA", "BRAVO", "CHARLIE", "DELTA", "ECHO", "FOXTROT", "GOLF", "HOTEL"]
    squads = []
    for i, row in grp.iterrows():
        squads.append({
            "id": callsigns[i],
            "callsign": callsigns[i],
            "lat": float(row["lat"]),
            "lon": float(row["lon"]),
            "terrain": "urban",
            "personnel": 12,
            "priority": "ROUTINE",
            # parcel_count proxy for demand (assume 5 lb / parcel)
            "demand_total_lb": int(row["parcels"]) * 5,
            "demand_class_i_lb": int(row["parcels"]) * 3,
            "demand_class_v_lb": 0,
            "demand_class_viii_lb": int(row["parcels"]) * 2,
            "demand_water_gal": 0,
            "dist_from_depot_km": 0.0,  # caller fills in vs new depot lat/lon
        })
    # Depot = centroid of all squads
    centroid_lat = sum(s["lat"] for s in squads) / len(squads)
    centroid_lon = sum(s["lon"] for s in squads) / len(squads)
    depot = {
        "id": "DEPOT-LADE",
        "name": "Forward Depot (LaDe centroid)",
        "type": "austere",
        "lat": centroid_lat,
        "lon": centroid_lon,
        "elev_m": 0,
        "lz_grade": "paved",
        "fuel_capacity_gal": 3200,
        "notes": f"Auto-derived from {Path(path).name}",
    }
    return {"squads": squads, "depots": [depot]}
