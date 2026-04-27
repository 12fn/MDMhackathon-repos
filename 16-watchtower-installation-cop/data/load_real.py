"""Real-data ingestion stub for WATCHTOWER (I-COP Aggregator).

The synthetic generator in `data/generate.py` shapes its output to match
three real-world data sources. To plug in real data, point the env vars
below at the corresponding files / API endpoints and implement the loader
function for that stream. The fused-event schema downstream of these
loaders is consistent: every record is `{stream, ts_iso, id, label,
is_anomaly?, anomaly_note?, lat?, lon?, ...stream-specific...}`.

------------------------------------------------------------------------
Stream → real source → expected file/API → required fields
------------------------------------------------------------------------

1) HIFLD Critical Infrastructure (gates, water/power/fuel, magazines):
     Source : Homeland Infrastructure Foundation-Level Data (HIFLD Open).
              https://hifld-geoplatform.opendata.arcgis.com/
     Format : ESRI shapefile or GeoJSON (one per layer: water_towers,
              power_substations, fuel_depots, magazines, comms_towers,
              hospitals).
     Drop at: REAL_HIFLD_DIR=/path/to/hifld/dir/ with:
                hifld_water_towers.geojson
                hifld_power_substations.geojson
                hifld_fuel_depots.geojson
                hifld_magazines.geojson
                hifld_comms_towers.geojson
                hifld_hospitals.geojson
     Fields : id, kind, name, lat, lon, owner, fips_state, fips_county, status

2) NASA Earthdata Hourly Weather (MERRA-2 / GEOS-FP):
     Source : NASA EOSDIS Earthdata. Two viable products:
                MERRA-2 reanalysis (hourly, 0.5x0.625 deg) — best for back-fill.
                GEOS-FP near-real-time (hourly, 0.25x0.3125 deg).
              https://earthdata.nasa.gov/  (free login required)
     Format : NetCDF4 / HDF5 (one daily file per product).
     Drop at: REAL_WEATHER_PATH=/path/to/MERRA2_400.tavg1_2d_slv_Nx.20260427.nc4
     Fields : valid_iso, lat, lon, temp_c, wind_speed_mps, wind_from_dir_deg,
              precip_mm_hr, rh_pct
     Notes  : You need to subset to the installation lat/lon bbox before
              feeding the I-COP. xarray does this in 5 lines.

3) GCSS-MC Maintenance Status:
     Source : Global Combat Support System - Marine Corps. Authoritative
              maintenance system of record for ground equipment readiness.
              Marine Corps Logistics Command (LOGCOM) produces a daily
              CSV / report extract per unit / cost-center.
     Format : CSV (one row per asset). Real prod field names vary by report.
     Drop at: REAL_GCSS_PATH=/path/to/gcss_mc_pendleton_2026-04-27.csv
     Fields : eic, nomenclature, serial, unit, location, status (FMC|PMC|NMC),
              defect_summary, est_repair_hours, last_pmcs_iso

4) Gate Access (PACS):
     Source : Installation Physical Access Control System (typically a
              Defense Manpower Data Center DBIDS extract). Per-gate hourly
              ingress/egress counts.
     Drop at: REAL_GATE_PATH=/path/to/dbids_pendleton_24h.csv

5) Utility Readings (DPW SCADA):
     Source : Installation DPW SCADA / utility-monitoring system (per
              substation, per water tower). 15-min rolled to hourly.
     Drop at: REAL_UTILITY_PATH=/path/to/dpw_scada_24h.csv

6) Fire/EMS Dispatches (CAD):
     Source : Installation Fire Department CAD (Computer-Aided Dispatch),
              typically Tyler New World, Motorola, Hexagon, or local CAD.
     Drop at: REAL_CAD_PATH=/path/to/cad_dispatches_24h.csv

7) Mass-Notification (AtHoc / Giant Voice):
     Source : Installation AtHoc instance + Giant Voice activations log.
     Drop at: REAL_ATHOC_PATH=/path/to/athoc_log_24h.csv

------------------------------------------------------------------------
Quick start
------------------------------------------------------------------------

    export REAL_HIFLD_DIR=~/data/hifld
    export REAL_WEATHER_PATH=~/data/merra2/MERRA2_400.tavg1_2d_slv_Nx.20260427.nc4
    export REAL_GCSS_PATH=~/data/gcss/pendleton_2026-04-27.csv
    export REAL_GATE_PATH=~/data/dbids/pendleton_24h.csv
    export REAL_UTILITY_PATH=~/data/dpw/scada_24h.csv
    export REAL_CAD_PATH=~/data/cad/dispatches_24h.csv
    export REAL_ATHOC_PATH=~/data/athoc/log_24h.csv
    python data/load_real.py     # populates data/*.json with real values

The Streamlit and FastAPI surfaces consume the `data/*.json` files; nothing
above the loader cares whether the source was synthetic or real.
"""
from __future__ import annotations

import os
from pathlib import Path


def _require(env: str) -> str:
    val = os.getenv(env)
    if not val:
        raise NotImplementedError(
            f"{env} not set. See module docstring for required schema "
            f"and source URL."
        )
    return val


def load_hifld_infrastructure() -> list[dict]:
    """Load HIFLD critical-infrastructure layers and emit the same shape as
    INSTALLATION['critical_infrastructure'] in data/generate.py."""
    base = Path(_require("REAL_HIFLD_DIR"))
    if not base.exists():
        raise FileNotFoundError(f"HIFLD dir not found: {base}")
    raise NotImplementedError(
        "Implement: read GeoJSON layers (geopandas.read_file), filter to "
        "the installation polygon, map fields to {id, kind, name, lat, lon, "
        "owner, fips_state, fips_county, status}."
    )


def load_nasa_earthdata_weather() -> list[dict]:
    """Load NASA Earthdata MERRA-2/GEOS-FP NetCDF4 hourly weather and emit
    the same hourly-record shape as data/generate.py's _weather()."""
    path = Path(_require("REAL_WEATHER_PATH"))
    if not path.exists():
        raise FileNotFoundError(f"Weather file not found: {path}")
    raise NotImplementedError(
        "Implement: xarray.open_dataset(path), subset to installation bbox, "
        "convert U10M/V10M to wind_speed_mps + wind_from_dir_deg, T2M to "
        "temp_c, PRECTOT to precip_mm_hr, RH from QV2M+T2M+PS, emit one row "
        "per hour."
    )


def load_gcss_mc_maintenance() -> list[dict]:
    """Load a GCSS-MC CSV extract and emit MAINTENANCE_ASSETS-shape records."""
    path = Path(_require("REAL_GCSS_PATH"))
    if not path.exists():
        raise FileNotFoundError(f"GCSS-MC file not found: {path}")
    raise NotImplementedError(
        "Implement: pandas.read_csv(path), normalize column names, map "
        "EIC/nomenclature/serial/unit/status/defect to the synth schema."
    )


def load_gate_access() -> list[dict]:
    path = Path(_require("REAL_GATE_PATH"))
    if not path.exists():
        raise FileNotFoundError(f"Gate access file not found: {path}")
    raise NotImplementedError(
        "Implement: pandas.read_csv(path), aggregate to hourly, emit "
        "{stream:'gate', gate_id, gate_name, lat, lon, ts_iso, "
        "ingress_count, egress_count}."
    )


def load_utility_scada() -> list[dict]:
    path = Path(_require("REAL_UTILITY_PATH"))
    if not path.exists():
        raise FileNotFoundError(f"Utility SCADA file not found: {path}")
    raise NotImplementedError(
        "Implement: pandas.read_csv(path), per-node hourly aggregation, "
        "emit {stream:'utility', node_id, node_kind, node_name, lat, lon, "
        "ts_iso, pressure_psi/load_mw/inventory_gal, ...}."
    )


def load_cad_dispatches() -> list[dict]:
    path = Path(_require("REAL_CAD_PATH"))
    if not path.exists():
        raise FileNotFoundError(f"CAD file not found: {path}")
    raise NotImplementedError(
        "Implement: pandas.read_csv(path), emit {stream:'ems', type, ts_iso, "
        "unit_id, unit_name, lat, lon, narrative, location, priority}."
    )


def load_athoc_log() -> list[dict]:
    path = Path(_require("REAL_ATHOC_PATH"))
    if not path.exists():
        raise FileNotFoundError(f"AtHoc log file not found: {path}")
    raise NotImplementedError(
        "Implement: pandas.read_csv(path), emit {stream:'massnotify', "
        "ts_iso, severity, message, system}."
    )


def load_real():
    """Convenience wrapper — call every loader and write data/*.json so the
    rest of the app does not need to change."""
    raise NotImplementedError(
        "Wire each load_* function to the corresponding data/*.json file; "
        "see module docstring for required env vars."
    )


if __name__ == "__main__":
    load_real()
