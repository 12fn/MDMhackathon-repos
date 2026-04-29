"""Real-data ingestion stubs for STORM-SHIFT.

STORM-SHIFT fuses FIVE public datasets. Each loader below documents the source,
required schema, and where to drop the file. Implement any one and the app
swaps in real data without further code changes.

Set the corresponding env var (see .env.example) and re-run the app.
"""
from __future__ import annotations

import os
from pathlib import Path

import pandas as pd

DATA_DIR = Path(__file__).parent


# ─── 1. NASA Earthdata (GPM IMERG / MERRA-2) ────────────────────────────────
def load_real_nasa_earthdata() -> pd.DataFrame:
    """Load NASA Earthdata hourly precipitation + wind grids.

    Source: https://earthdata.nasa.gov/  (GES DISC GPM IMERG L3 v07)
    Required columns (rename to match):
        timestamp, lat, lon, precip_mm_hr, wind_u_mps, wind_v_mps, temp_c
    File format: NetCDF (.nc) or CSV (post-conversion). Set REAL_NASA_EARTHDATA_PATH.

    To swap: implement xarray.open_dataset(path).to_dataframe().reset_index()
    and rename columns to the required schema.
    """
    path = os.getenv("REAL_NASA_EARTHDATA_PATH")
    if not path:
        raise NotImplementedError(
            "REAL_NASA_EARTHDATA_PATH not set. Download GPM IMERG L3 from GES DISC; "
            "convert NetCDF to the documented schema."
        )
    return pd.read_csv(path)


# ─── 2. NASA FIRMS (active fire pixels) ─────────────────────────────────────
def load_real_nasa_firms() -> pd.DataFrame:
    """Load NASA FIRMS active-fire thermal anomalies (MODIS C6 / VIIRS).

    Source: https://firms.modaps.eosdis.nasa.gov/active_fire/ (NRT 24h CSV)
    Required columns (real FIRMS schema is already a superset):
        latitude, longitude, brightness, scan, track, acq_date, acq_time,
        satellite, confidence, version, bright_t31, frp, daynight
    Set REAL_NASA_FIRMS_PATH to a downloaded CSV (24h or 7d window).
    """
    path = os.getenv("REAL_NASA_FIRMS_PATH")
    if not path:
        raise NotImplementedError(
            "REAL_NASA_FIRMS_PATH not set. Download from FIRMS Active Fire CSV API."
        )
    return pd.read_csv(path)


# ─── 3. FIMA NFIP Redacted Claims v2 ────────────────────────────────────────
def load_real_nfip() -> pd.DataFrame:
    """Load FEMA OpenFEMA NFIP Redacted Claims v2.

    Source: https://www.fema.gov/openfema-data-page/fima-nfip-redacted-claims-v2
    Required columns:
        id, state, dateOfLoss, yearOfLoss, floodZone, eventDesignation,
        buildingDamageAmount, contentsDamageAmount, amountPaidOnBuildingClaim,
        amountPaidOnContentsClaim, latitude, longitude
    Format: parquet (the OpenFEMA bulk download). Set REAL_NFIP_PATH.
    """
    path = os.getenv("REAL_NFIP_PATH")
    if not path:
        raise NotImplementedError(
            "REAL_NFIP_PATH not set. OpenFEMA bulk parquet from "
            "https://www.fema.gov/openfema-data-page/fima-nfip-redacted-claims-v2"
        )
    return pd.read_parquet(path)


# ─── 4. FEMA Supply Chain Climate Resilience ────────────────────────────────
def load_real_fema_sc_climate() -> pd.DataFrame:
    """Load FEMA Supply Chain Climate Resilience dataset (sponsored by Qlik).

    Source: FEMA / Qlik Open Data — supply chain disruption events tagged to
            climate hazards.
    Required columns:
        id, event_year, hazard_type, product_category,
        supplier_count_affected, lead_time_baseline_days, lead_time_disrupted_days,
        outage_duration_days, estimated_cost_usd, latitude, longitude,
        criticality_to_dod
    Set REAL_FEMA_SC_CLIMATE_PATH.
    """
    path = os.getenv("REAL_FEMA_SC_CLIMATE_PATH")
    if not path:
        raise NotImplementedError(
            "REAL_FEMA_SC_CLIMATE_PATH not set. See FEMA / Qlik Supply Chain "
            "Climate Resilience open dataset for download."
        )
    return pd.read_csv(path)


# ─── 5. Logistics-and-supply-chain-dataset (California) ─────────────────────
def load_real_logistics_ca() -> pd.DataFrame:
    """Load California logistics + supply chain shipment records.

    Source: Kaggle 'logistics-and-supply-chain-dataset' (or DOT California
            freight movement open data).
    Required columns:
        shipment_id, origin_city, origin_lat, origin_lon, destination_city,
        destination_lat, destination_lon, ship_date, mode, weight_lbs,
        transit_days_planned, transit_days_actual, warehouse_type,
        carrier_score, fuel_surcharge_pct
    Set REAL_LOGISTICS_CA_PATH.
    """
    path = os.getenv("REAL_LOGISTICS_CA_PATH")
    if not path:
        raise NotImplementedError(
            "REAL_LOGISTICS_CA_PATH not set. See Kaggle 'logistics-and-supply-chain-dataset' "
            "or California DOT freight movement open data."
        )
    return pd.read_csv(path)
