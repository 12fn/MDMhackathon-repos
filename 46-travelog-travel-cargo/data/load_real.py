"""Real-data ingestion stubs for TRAVELOG.

TRAVELOG fuses FOUR datasets in a single agent. Each loader below documents
its real upstream source, the columns/shape required, and where to drop the
file inside this app's `data/` directory. Everything raises NotImplementedError
until you point the env var at a real file.

────────────────────────────────────────────────────────────────────────────
1) DTS authorizations (synthetic VOUCHER schema)
   Source: Defense Travel System (DTS) — DTMO / Sabre TripCase backend.
   How an MDM officer would land it locally:
     - Export from DTS Reporting → "Authorization Detail" → CSV
     - Or pull from the DTS data extract feed your unit S-1 already runs
   Required columns (snake_case, JTR-aligned):
     doc_number, ta_number, traveler_edipi, traveler_name, traveler_grade,
     ao_edipi, ao_name, trip_purpose, trip_start, trip_end, status,
     tdy_city, nights, per_diem_lodging_ceiling, per_diem_mie,
     total_authorized, total_voucher, mode_of_travel, origin_id, dest_id

2) AFCENT Logistics Data (asset/lift inventory)
   Source: AFCENT consolidated logistics readiness extract — asset class,
     mode, capacity, fuel burn rate, current home-station base.
   Required columns:
     class, mode, cap_lbs, cap_pallets, cruise_mph, fuel_lb_hr,
     current_base, readiness

3) Bureau of Transportation Statistics — National Transportation Atlas (NTAD)
   Source: https://geodata.bts.gov/  (CSV / Shapefile / GeoJSON)
   We use the multimodal corridor extracts for road, rail, sea, air.
   Required nodes columns: id, name, lat, lon, kind
   Required edges columns: from, to, mode, distance_mi, transit_hr,
                            cost_per_mile_usd

4) Last Mile Delivery (LaDe)
   Source: LaDe public dataset — Cainiao Network (Alibaba) ICDM 2023.
     https://github.com/wenhaomin/LaDe
   Required columns (mapped to LaDe field names in parens):
     parcel_id (waybill_id), courier (courier_id), pickup_lat (lat_pickup),
     pickup_lon (lng_pickup), delivery_lat (lat_drop), delivery_lon
     (lng_drop), eta_pickup, eta_delivery, weight_lbs, status

────────────────────────────────────────────────────────────────────────────
Usage:
  REAL_DTS_PATH=/path/to/dts.csv \\
  REAL_ASSETS_PATH=/path/to/assets.csv \\
  REAL_BTS_NODES=/path/to/nodes.geojson \\
  REAL_BTS_EDGES=/path/to/edges.csv \\
  REAL_LADE_PATH=/path/to/lade.csv \\
  python -m src.app
"""
from __future__ import annotations

import os
from pathlib import Path

import pandas as pd


def _require(env: str) -> Path:
    p = os.getenv(env)
    if not p:
        raise NotImplementedError(
            f"{env} env var not set. See docstring above for required schema."
        )
    return Path(p)


def load_real_dts() -> pd.DataFrame:
    return pd.read_csv(_require("REAL_DTS_PATH"))


def load_real_assets() -> pd.DataFrame:
    return pd.read_csv(_require("REAL_ASSETS_PATH"))


def load_real_bts_nodes() -> pd.DataFrame:
    p = _require("REAL_BTS_NODES")
    if str(p).endswith(".geojson") or str(p).endswith(".json"):
        import json
        raw = json.loads(p.read_text())
        if isinstance(raw, dict) and "features" in raw:
            rows = []
            for feat in raw["features"]:
                props = feat.get("properties", {})
                geom = feat.get("geometry", {})
                lon, lat = (geom.get("coordinates") or [None, None])[:2]
                rows.append({**props, "lat": lat, "lon": lon})
            return pd.DataFrame(rows)
        return pd.DataFrame(raw)
    return pd.read_csv(p)


def load_real_bts_edges() -> pd.DataFrame:
    return pd.read_csv(_require("REAL_BTS_EDGES"))


def load_real_lade() -> pd.DataFrame:
    return pd.read_csv(_require("REAL_LADE_PATH"))
