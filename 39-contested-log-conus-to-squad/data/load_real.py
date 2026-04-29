"""Real-data ingestion stubs for CONTESTED-LOG.

Eight datasets are fused in this app. Each `load_real_<X>()` documents the
swap recipe so the synthetic generator can be replaced piecemeal without
touching src/.

Dataset → swap path:

  1. **BTS NTAD (Bureau of Transportation Statistics — National
     Transportation Atlas Database)**
       URL:    https://geodata.bts.gov/datasets/national-transportation-atlas-database
       Files:  ntad-rail.shp, ntad-roads.shp, ntad-waterways.shp
       Map →   bts_nodes.csv (junctions) + bts_edges.csv (typed segments,
               weight_class + bridge_clearance_in)

  2. **MSI WPI (World Port Index — National Geospatial-Intelligence Agency)**
       URL:    https://msi.nga.mil/Publications/WPI
       File:   WPI.csv (3,800+ ports worldwide, depth, berth count, services)
       Map →   ports.json (id, name, country, lat, lon,
               throughput_teu_per_day, berths, lcac_pad, role)

  3. **AIS (Automatic Identification System) shipping lanes**
       Source: MarineCadastre.gov "AIS Vessel Tracks"
       Format: Parquet/CSV, ~150M points/year
       Map →   ais_lanes.json (corridor segments + median transit_days)

  4. **Pirate Attacks — ASAM (NGA Anti-Shipping Activity Messages)**
       URL:    https://msi.nga.mil/Piracy
       Mirror: kaggle.com/datasets/dryad/global-maritime-pirate-attacks
       Map →   pirate_attacks.csv (attack_id, datetime, lat, lon, basin,
               vessel_type, attack_type)

  5. **AFCENT Logistics Data** (CENTCOM logistics common operating picture)
       Source: AFCENT/MARCENT internal feed (LMDC / TMR system)
       Map →   depot_stocks.json (per-depot Class I-IX on-hand pallets)

  6. **GCSS-MC (Global Combat Support System — Marine Corps)**
       Source: GCSS-MC enterprise data warehouse exports
       Map →   gcss_lots.csv (lot-level inventory: lot_id, depot_id, class,
               qty_pallets, exp_in_days, lot_status)

  7. **LaDe (Last-Mile Delivery, Cainiao/Alibaba)**
       URL:    https://github.com/cainiao-AI/LaDe
       Map →   squads.json (8 dispersed forward positions w/ demand profile)

  8. **Global SC Disruption + Risk + Logistics**
       Source: Resilinc EventWatchAI / Everstream IQ feed
       Map →   sc_disruptions.json (rolling 60-day events feed)

To plug each in: implement the corresponding load_real_<X>() and set the
matching env var (REAL_NTAD_PATH, REAL_WPI_PATH, etc.). The Streamlit app
imports `data/loader.load()` which prefers real if env is set.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import pandas as pd


def _need(env_var: str, hint: str) -> str:
    p = os.getenv(env_var)
    if not p:
        raise NotImplementedError(
            f"{env_var} not set. {hint}"
        )
    return p


def load_real_ntad() -> dict[str, Any]:
    """BTS NTAD shapefiles → nodes + typed edges."""
    path = _need("REAL_NTAD_PATH",
                 "Download NTAD rail/road/water shapefiles, then point at the dir.")
    raise NotImplementedError(
        f"Implement BTS NTAD shapefile → bts_nodes.csv + bts_edges.csv at {path}."
    )


def load_real_wpi() -> list[dict]:
    """NGA WPI CSV → ports.json."""
    path = _need("REAL_WPI_PATH", "Download NGA WPI.csv, point REAL_WPI_PATH at it.")
    df = pd.read_csv(path)
    out = []
    for _, r in df.iterrows():
        out.append({
            "id": str(r.get("PORT_NAME", "?"))[:24].upper().replace(" ", "-"),
            "name": str(r.get("PORT_NAME", "?")),
            "country": str(r.get("COUNTRY", "?")),
            "lat": float(r.get("LATITUDE", 0.0)),
            "lon": float(r.get("LONGITUDE", 0.0)),
            "throughput_teu_per_day": int(r.get("THROUGHPUT", 100)),
            "berths": int(r.get("HARBOR_SIZE_CODE", 1) or 1),
            "lcac_pad": False,  # WPI doesn't track LCAC pads — overlay separately
            "role": "ALY",
            "domain": "GLOBAL",
        })
    return out


def load_real_ais() -> list[dict]:
    """MarineCadastre AIS → lane corridor segments (use H3 cell density)."""
    raise NotImplementedError(
        "Implement AIS Parquet → corridor segmentation. Recommend H3 cell "
        "density + corridor extraction pipeline; downsample to ~100 lanes."
    )


def load_real_pirate(path: str | None = None) -> pd.DataFrame:
    """ASAM pirate attacks CSV (Kaggle mirror) → identical schema."""
    p = path or _need("REAL_PIRATE_PATH", "Point at ASAM CSV mirror.")
    return pd.read_csv(p)


def load_real_afcent_stocks() -> dict:
    """AFCENT/MARCENT TMR feed → depot_stocks.json."""
    raise NotImplementedError(
        "Implement AFCENT LMDC export → per-depot Class I-IX pallet counts."
    )


def load_real_gcss(path: str | None = None) -> pd.DataFrame:
    """GCSS-MC export → identical lot schema."""
    p = path or _need("REAL_GCSS_PATH", "Point at GCSS-MC enterprise CSV export.")
    return pd.read_csv(p)


def load_real_lade(path: str | None = None) -> list[dict]:
    """LaDe city slice → 8 squad positions (top-8 regions by parcel count)."""
    p = path or _need("REAL_LADE_PATH", "Download LaDe city CSV.")
    df = pd.read_csv(p)
    grp = df.groupby("region_id").agg(
        lat=("lat", "mean"),
        lon=("lng", "mean") if "lng" in df.columns else ("lon", "mean"),
        parcels=("order_id", "count"),
    ).nlargest(8, "parcels").reset_index()
    callsigns = ["ALPHA", "BRAVO", "CHARLIE", "DELTA",
                 "ECHO", "FOXTROT", "GOLF", "HOTEL"]
    return [
        {
            "id": callsigns[i], "callsign": callsigns[i],
            "lat": float(row["lat"]), "lon": float(row["lon"]),
            "terrain": "urban", "personnel": 12, "priority": "ROUTINE",
            "demand_total_lb": int(row["parcels"]) * 5,
        }
        for i, row in grp.iterrows()
    ]


def load_real_sc_disruption() -> list[dict]:
    """Resilinc / Everstream IQ feed → 60-day events."""
    raise NotImplementedError(
        "Implement Resilinc/Everstream API ingest → sc_disruptions.json schema."
    )
