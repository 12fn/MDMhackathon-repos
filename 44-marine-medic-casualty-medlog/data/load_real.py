"""Real-data ingestion stub for MARINE-MEDIC.

This app ships with seeded synthetic data (`data/generate.py`) but is wired so
the real LOGCOM-portal datasets drop in with no code changes.

DATASETS PLUGGED IN HERE (4):

  1. **Medical Supply Inventory v1**
     Source: USMC LOGCOM AI Forum Hackathon 2026 portal
             (sponsor: DLA Troop Support / NAVMED)
     Expected file: medical_supply_inventory_v1.csv
     Required columns:
       - site_id            : ASCII id (e.g. "APRA-MED", "LHA-6", "EABO-PA")
       - product            : one of {PRBC, FFP, PLASMA, PLT, LTOWB}
       - units              : integer units on hand
       - lot                : lot id string
       - expires_iso        : ISO-8601 expiration timestamp
       - cold_chain_status  : one of {GREEN, AMBER, RED}
       - daily_consumption  : float units/day
       - days_of_supply     : float days remaining
       - iso_donor_screened : bool

  2. **Medical Supply Inventory v2**
     Source: same portal
     Expected file: medical_supply_inventory_v2.xlsx (or .csv)
     Required columns:
       - item_id            : ASCII id
       - nsn                : National Stock Number "NNNN-NN-NNN-NNNN"
       - nomenclature       : full description string
       - unit               : unit-of-issue code (vial/bag/ea/set)
       - site_id            : ASCII id matching spokes/hub
       - qty_on_hand, qty_required, shortage : integers
       - condition_code     : "A","B","C","F"
       - sensitivity_class  : "ROUTINE","CONTROLLED","SENSITIVE"
       - burn_rate_per_day  : float
       - days_of_supply     : float
       - expires_iso        : ISO-8601
       - lot                : lot id string
       - nmc_impacting      : bool

  3. **Medical Supply Network Data Model**
     Source: same portal
     Expected file: medical_supply_network.json
     Shape:
       - hub:    {id, name, lat, lon, cold_chain_units, cold_chain_health,
                  lab_reagent_days, dry_ice_kg, max_daily_throughput_units, role}
       - spokes: [{id, name, kind, role, country, lat, lon, personnel,
                   fridges, fridge_health}, ...]
       - edges:  [{edge_id, source, target, mode, distance_nm, leg_hours,
                   lift_status, cold_chain_transit_risk, last_resupply_h_ago}]

  4. **GCSS-MC Supply & Maintenance**
     Source: GCSS-MC export (CSV or JSON via secure connector)
     Expected file: gcss_mc_class_viii.json
     Required columns per row:
       - doc_id, nsn, nomenclature, ric_to, ship_to_uic, qty, uoi,
         status (BO/OPN/REC/SHP/CLS), priority (FAD I-V codes),
         submitted_iso, lead_time_h_estimate, source_depot

To plug in:
    export REAL_INVENTORY_V1=/secure/path/medical_supply_inventory_v1.csv
    export REAL_INVENTORY_V2=/secure/path/medical_supply_inventory_v2.xlsx
    export REAL_NETWORK_PATH=/secure/path/medical_supply_network.json
    export REAL_GCSS_PATH=/secure/path/gcss_mc_class_viii.json
    streamlit run src/app.py --server.port 3044

Column mapping notes (LOGCOM portal -> our schema):

| LOGCOM column           | Our field               | Transform                            |
|-------------------------|-------------------------|--------------------------------------|
| MTF_ID / UIC            | site_id                 | uppercase, normalize hyphens         |
| PRODUCT_CODE            | product                 | NDC/ISBT-128 lookup -> {PRBC,FFP,...}|
| ON_HAND_QTY             | units / qty_on_hand     | int                                  |
| EXP_DT (YYYYMMDD)       | expires_iso             | parse + isoformat                    |
| COLD_CHAIN_FLAG (0/1/2) | cold_chain_status       | 0->GREEN, 1->AMBER, 2->RED           |
| DAILY_USE_RATE          | daily_consumption / burn_rate_per_day | float                |
| DOS                     | days_of_supply          | derived if missing: units/daily_use  |
| FAD_CODE                | priority                | I->01, II->03, III->06, ...          |

Run `python data/generate.py` to regenerate the synthetic dataset (seed=1776).
"""
from __future__ import annotations

import json
import os
from pathlib import Path

try:
    import pandas as pd  # noqa: F401
except ImportError:
    pd = None  # type: ignore


def _require_pd() -> None:
    if pd is None:
        raise RuntimeError("pandas required for real-data ingest. `pip install pandas openpyxl`.")


def load_real_inventory_v1() -> list[dict]:
    """Return v1 blood inventory rows in the schema generate.py emits."""
    path = os.getenv("REAL_INVENTORY_V1")
    if not path:
        raise NotImplementedError(
            "REAL_INVENTORY_V1 not set. See module docstring for the expected "
            "LOGCOM 'Medical Supply Inventory v1' schema."
        )
    _require_pd()
    df = pd.read_csv(path)
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
        df["cold_chain_status"] = df["cold_chain_status"].map({0: "GREEN", 1: "AMBER", 2: "RED"})
    if "days_of_supply" not in df.columns and "daily_consumption" in df.columns:
        df["days_of_supply"] = (df["units"] / df["daily_consumption"]).round(1)
    return df.to_dict(orient="records")


def load_real_inventory_v2() -> list[dict]:
    """Return v2 broader Class VIII rows in the schema generate.py emits."""
    path = os.getenv("REAL_INVENTORY_V2")
    if not path:
        raise NotImplementedError(
            "REAL_INVENTORY_V2 not set. See module docstring for the expected "
            "LOGCOM 'Medical Supply Inventory v2' schema."
        )
    _require_pd()
    p = Path(path)
    if p.suffix.lower() in (".xlsx", ".xls"):
        df = pd.read_excel(path)
    else:
        df = pd.read_csv(path)
    rename = {
        "NSN": "nsn", "NOMENCLATURE": "nomenclature",
        "UOI": "unit", "UNIT_OF_ISSUE": "unit",
        "MTF_ID": "site_id", "UIC": "site_id",
        "ON_HAND_QTY": "qty_on_hand", "QTY_ON_HAND": "qty_on_hand",
        "QTY_REQUIRED": "qty_required", "REQ_QTY": "qty_required",
        "CONDITION_CODE": "condition_code",
        "SENSITIVITY": "sensitivity_class",
        "BURN_RATE": "burn_rate_per_day", "DAILY_USE_RATE": "burn_rate_per_day",
        "DOS": "days_of_supply",
        "EXP_DT": "expires_iso",
    }
    df = df.rename(columns={k: v for k, v in rename.items() if k in df.columns})
    if "shortage" not in df.columns and {"qty_on_hand", "qty_required"}.issubset(df.columns):
        df["shortage"] = (df["qty_required"] - df["qty_on_hand"]).clip(lower=0)
    return df.to_dict(orient="records")


def load_real_network() -> dict:
    """Return {hub, spokes, edges} in the shape generate.py emits."""
    path = os.getenv("REAL_NETWORK_PATH")
    if not path:
        raise NotImplementedError(
            "REAL_NETWORK_PATH not set. See module docstring for the expected "
            "LOGCOM 'Medical Supply Network Data Model' shape."
        )
    p = Path(path)
    if p.suffix.lower() == ".json":
        return json.loads(p.read_text())
    raise NotImplementedError(
        "Only JSON network model parsing implemented in stub. "
        "For CSV variants, add per-table reads here."
    )


def load_real_gcss_mc() -> list[dict]:
    """Return GCSS-MC requisition rows."""
    path = os.getenv("REAL_GCSS_PATH")
    if not path:
        raise NotImplementedError(
            "REAL_GCSS_PATH not set. See module docstring for the expected "
            "GCSS-MC Class VIII requisition shape."
        )
    p = Path(path)
    if p.suffix.lower() == ".json":
        return json.loads(p.read_text())
    _require_pd()
    return pd.read_csv(path).to_dict(orient="records")
