"""Real-data ingestion stub for STOCKROOM.

The LOGCOM portal publishes the **Inventory Control Management** workbook —
a spread of disconnected Excel docs across which Marines manually track over
5,000 items daily. To plug in real data, drop the latest workbook at the path
named by the `REAL_DATA_PATH` env var and call `load_real()`.

Required columns (case-insensitive; load_real renames to the synthetic schema):
  - NSN                      -> nsn
  - Nomenclature             -> nomenclature
  - Quantity / OnHand        -> qty_on_hand
  - Required / RequiredOnHand-> qty_required        (optional)
  - Location / Bin           -> location_id
  - Responsible Marine       -> responsible_marine
  - Sensitivity / Class      -> sensitivity_class   (ROUTINE/SENSITIVE/CCI/ARMS/HAZMAT)
  - Last Inventoried         -> last_inventoried_date (YYYY-MM-DD)
  - Last Lateral Transfer    -> last_lateral_transfer_date (optional, YYYY-MM-DD)
  - Condition Code           -> condition_code      (optional)

Then point src/app.py at it via env: REAL_DATA_PATH=/abs/path/to/icm.xlsx
"""
from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd


COLUMN_RENAMES = {
    "nsn":                       "nsn",
    "nomenclature":              "nomenclature",
    "quantity":                  "qty_on_hand",
    "qty":                       "qty_on_hand",
    "onhand":                    "qty_on_hand",
    "qty on hand":               "qty_on_hand",
    "required":                  "qty_required",
    "qty required":              "qty_required",
    "requiredonhand":            "qty_required",
    "location":                  "location_id",
    "location_id":               "location_id",
    "bin":                       "location_id",
    "responsible marine":        "responsible_marine",
    "custodian":                 "responsible_marine",
    "responsible_marine":        "responsible_marine",
    "sensitivity":               "sensitivity_class",
    "sensitivity class":         "sensitivity_class",
    "class":                     "category",
    "category":                  "category",
    "last inventoried":          "last_inventoried_date",
    "last_inventoried":          "last_inventoried_date",
    "last_inventoried_date":     "last_inventoried_date",
    "last lateral transfer":     "last_lateral_transfer_date",
    "last_lateral_transfer":     "last_lateral_transfer_date",
    "last_lateral_transfer_date":"last_lateral_transfer_date",
    "condition code":            "condition_code",
    "condition_code":            "condition_code",
    "serial":                    "serial_number",
    "serial number":             "serial_number",
    "serial_number":             "serial_number",
    "unit of issue":             "unit_of_issue",
    "uom":                       "unit_of_issue",
    "uoi":                       "unit_of_issue",
}


def load_real() -> pd.DataFrame:
    path = os.getenv("REAL_DATA_PATH")
    if not path:
        raise NotImplementedError(
            "REAL_DATA_PATH not set. See docstring for required schema. "
            "For demo data, run `python data/generate.py` first and the app "
            "will load data/inventory.xlsx automatically."
        )
    p = Path(path)
    if p.suffix.lower() in (".xlsx", ".xlsm", ".xls"):
        df = pd.read_excel(p, engine="openpyxl")
    else:
        df = pd.read_csv(p)
    # case-insensitive column rename to the synthetic schema
    df.columns = [c.strip() for c in df.columns]
    rename_map = {
        c: COLUMN_RENAMES[c.lower()]
        for c in df.columns
        if c.lower() in COLUMN_RENAMES
    }
    df = df.rename(columns=rename_map)
    # derive helper columns the app expects
    now = datetime.now(timezone.utc)
    if "last_inventoried_date" in df.columns:
        d = pd.to_datetime(df["last_inventoried_date"], errors="coerce", utc=True)
        df["days_since_inventory"] = (now - d).dt.days.fillna(9999).astype(int)
    if "last_lateral_transfer_date" in df.columns:
        d = pd.to_datetime(df["last_lateral_transfer_date"], errors="coerce", utc=True)
        df["days_since_lateral_transfer"] = (now - d).dt.days.fillna(9999).astype(int)
    if "qty_on_hand" in df.columns and "qty_required" in df.columns:
        df["shortage"] = (df["qty_required"] - df["qty_on_hand"]).clip(lower=0)
    return df
