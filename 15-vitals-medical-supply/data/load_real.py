"""Real-data ingestion stub for VITALS.

This app ships with seeded synthetic data (`data/generate.py`) but is wired so
the real LOGCOM-portal datasets drop in with no code changes:

  1. **Medical Supply Inventory**
     Source: USMC LOGCOM AI Forum Hackathon 2026 portal
             (sponsor: DLA Troop Support / NAVMED)
     Expected file: medical_supply_inventory.csv
     Required columns:
       - site_id            : ASCII id matching `data/spokes.json[].id`
                              or `data/hub.json.id` (e.g. "APRA-MED", "LHA-6")
       - product            : one of {PRBC, PLASMA, PLT, LTOWB, ...}
       - units              : integer units on hand
       - expires_iso        : ISO-8601 expiration timestamp
       - cold_chain_status  : one of {GREEN, AMBER, RED}
       - daily_consumption  : float units/day
       - days_of_supply     : float days remaining at current consumption rate

  2. **Medical Supply Network Data Model**
     Source: same portal
     Expected file: medical_supply_network.json (or .csv)
     Required hub-and-spoke shape:
       - hub:    {id, name, lat, lon, cold_chain_units, cold_chain_health,
                  lab_reagent_days, dry_ice_kg, max_daily_throughput_units}
       - spokes: [{id, name, kind, country, lat, lon, personnel,
                   fridges, fridge_health}, ...]
       - routes: [{spoke_id, mode, distance_nm, leg_hours, lift_status,
                   cold_chain_transit_risk, last_resupply_h_ago}, ...]

To plug in:
    export REAL_INVENTORY_PATH=/secure/path/medical_supply_inventory.csv
    export REAL_NETWORK_PATH=/secure/path/medical_supply_network.json
    streamlit run src/app.py --server.port 3015

Column mapping notes (LOGCOM portal -> our schema):

| LOGCOM column           | Our field               | Transform                            |
|-------------------------|-------------------------|--------------------------------------|
| MTF_ID / UIC            | site_id                 | uppercase, strip dashes -> hyphenate |
| PRODUCT_CODE            | product                 | NDC/ISBT-128 lookup -> {PRBC,PLT,...}|
| ON_HAND_QTY             | units                   | int cast                             |
| EXP_DT (YYYYMMDD)       | expires_iso             | parse + isoformat                    |
| COLD_CHAIN_FLAG (0/1/2) | cold_chain_status       | 0->GREEN, 1->AMBER, 2->RED           |
| DAILY_USE_RATE          | daily_consumption       | float                                |
| DOS                     | days_of_supply          | derived if missing: units/daily_use  |

The Network Data Model from the portal includes a hub-and-spoke graph in JSON
already; the only mapping required is to pin lat/lon (use the portal's GEO_LAT
/ GEO_LON columns) and to translate STATUS_CODE -> {GREEN, AMBER, RED}.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

try:
    import pandas as pd  # noqa: F401  (only required for the real path)
except ImportError:
    pd = None  # type: ignore


def load_real_inventory() -> list[dict]:
    """Return inventory rows in the schema generate.py emits."""
    path = os.getenv("REAL_INVENTORY_PATH")
    if not path:
        raise NotImplementedError(
            "REAL_INVENTORY_PATH not set. See module docstring for the "
            "expected LOGCOM 'Medical Supply Inventory' column schema."
        )
    if pd is None:
        raise RuntimeError("pandas required for real-data ingest. `pip install pandas`.")
    df = pd.read_csv(path)
    # Apply the column mapping documented above
    rename = {
        "MTF_ID": "site_id", "UIC": "site_id",
        "PRODUCT_CODE": "product",
        "ON_HAND_QTY": "units",
        "EXP_DT": "expires_iso",
        "COLD_CHAIN_FLAG": "cold_chain_status",
        "DAILY_USE_RATE": "daily_consumption",
        "DOS": "days_of_supply",
    }
    df = df.rename(columns={k: v for k, v in rename.items() if k in df.columns})
    if "cold_chain_status" in df.columns and df["cold_chain_status"].dtype != object:
        df["cold_chain_status"] = df["cold_chain_status"].map(
            {0: "GREEN", 1: "AMBER", 2: "RED"}
        )
    if "days_of_supply" not in df.columns and "daily_consumption" in df.columns:
        df["days_of_supply"] = (df["units"] / df["daily_consumption"]).round(1)
    return df.to_dict(orient="records")


def load_real_network() -> dict:
    """Return {hub, spokes, routes} in the shape generate.py emits."""
    path = os.getenv("REAL_NETWORK_PATH")
    if not path:
        raise NotImplementedError(
            "REAL_NETWORK_PATH not set. See module docstring for the "
            "expected LOGCOM 'Medical Supply Network Data Model' shape."
        )
    p = Path(path)
    if p.suffix.lower() == ".json":
        return json.loads(p.read_text())
    raise NotImplementedError(
        "Only JSON network model parsing implemented in stub. "
        "For CSV variants, add per-table reads here."
    )
