"""Real-data ingestion stub for OMNI.

OMNI fuses six external feeds. To plug real data in, implement each
loader to emit the same JSON shape that data/generate.py produces, then
set the corresponding env var and the FastAPI backend will hot-swap.

  HIFLD critical infrastructure
    Source: https://hifld-geoplatform.opendata.arcgis.com (ArcGIS shapefile / GeoJSON)
    Required fields per asset: id, kind, name, lat, lon, owner, status
    Env: OMNI_HIFLD_PATH=/path/to/hifld_export.geojson

  NASA Earthdata weather
    Source: https://earthdata.nasa.gov (MERRA-2 HDF5 / NetCDF granules)
    Required fields per hour: ts_iso, lat, lon, temp_c, wind_speed_mps,
        wind_from_dir_deg, precip_mm_hr, rh_pct
    Env: OMNI_EARTHDATA_PATH=/path/to/merra2_subset.nc4

  NASA FIRMS thermal
    Source: https://firms.modaps.eosdis.nasa.gov (CSV/JSON near-real-time pings)
    Required fields per ping: ts_iso, lat, lon, satellite, brightness_k,
        frp_mw, confidence
    Env: OMNI_FIRMS_CSV=/path/to/MODIS_C6_Global_24h.csv

  GCSS-MC maintenance
    Source: SIPR/GCSS-MC export, typical CSV:
      eic, nomenclature, serial, unit, location, status, defect, est_repair_hours, last_pmcs
    Env: OMNI_GCSS_PATH=/path/to/gcss_mc_export.csv

  IEEE WiFi/BT RF fingerprinting
    Source: IEEE-DataPort WiFi / Bluetooth RF Fingerprinting datasets
    Required fields per observation: ts_iso, device_id, device_kind, label,
        rssi_dbm, channel, lat, lon
    Env: OMNI_RF_PATH=/path/to/rf_traces.parquet

  Drone RF detections
    Source: DroneRF dataset (Mendeley) or DJI Aeroscope log export
    Required fields per detection: ts_iso, protocol, make, model,
        rid_serial (nullable), rssi_dbm, altitude_m, lat, lon
    Env: OMNI_DRONE_RF_PATH=/path/to/drone_rf_capture.csv
"""
from __future__ import annotations

import os


def load_hifld():
    path = os.getenv("OMNI_HIFLD_PATH")
    if not path:
        raise NotImplementedError(
            "OMNI_HIFLD_PATH not set. See module docstring for required schema."
        )
    raise NotImplementedError("Plug your HIFLD GeoJSON parser here.")


def load_earthdata():
    path = os.getenv("OMNI_EARTHDATA_PATH")
    if not path:
        raise NotImplementedError(
            "OMNI_EARTHDATA_PATH not set. See module docstring for required schema."
        )
    raise NotImplementedError("Plug your NASA Earthdata HDF/NetCDF parser here.")


def load_firms():
    path = os.getenv("OMNI_FIRMS_CSV")
    if not path:
        raise NotImplementedError(
            "OMNI_FIRMS_CSV not set. See module docstring for required schema."
        )
    raise NotImplementedError("Plug your NASA FIRMS CSV parser here.")


def load_gcss():
    path = os.getenv("OMNI_GCSS_PATH")
    if not path:
        raise NotImplementedError(
            "OMNI_GCSS_PATH not set. See module docstring for required schema."
        )
    raise NotImplementedError("Plug your GCSS-MC CSV parser here.")


def load_rf():
    path = os.getenv("OMNI_RF_PATH")
    if not path:
        raise NotImplementedError(
            "OMNI_RF_PATH not set. See module docstring for required schema."
        )
    raise NotImplementedError("Plug your IEEE WiFi/BT RF parser here.")


def load_drone_rf():
    path = os.getenv("OMNI_DRONE_RF_PATH")
    if not path:
        raise NotImplementedError(
            "OMNI_DRONE_RF_PATH not set. See module docstring for required schema."
        )
    raise NotImplementedError("Plug your DroneRF / Aeroscope log parser here.")
