"""Real-data ingestion stub for REORDER.

To plug in real data, implement load_real() to read GCSS-MC work-order extracts
+ NASA Predictive Maintenance / Microsoft Azure Predictive Maintenance feeds
and emit the same shape as data/generate.py produces.

Required columns in the work-order CSV (see data/maintenance_history.csv):
  - date            (YYYY-MM-DD)
  - work_order_id   (string)
  - platform        (one of: MTVR, LAV, JLTV, M88A2, HMMWV)
  - vehicle_id      (string)
  - environment     (one of: desert, jungle, maritime, cold)
  - optempo         (one of: low, medium, high)
  - magtf_size      (one of: MEU, MEB, MEF)
  - nsn             (NSN format NNNN-NN-NNN-NNNN)
  - part_name       (string)
  - qty_consumed    (int)
  - subsystem       (string, e.g. "engine", "tracks", "electrical")

Required structure for the NSN catalog JSON:
  list of {nsn, part_name, primary_platform, subsystem,
           base_daily_per_vehicle, unit_price_usd}

Required structure for the forward-nodes JSON:
  list of {id, name, kind, lat, lon, tier, on_hand_by_nsn: {nsn: int}}

Then point src/app.py at it via env: REAL_DATA_PATH=/path/to/file.csv
(the app will fall back to data/maintenance_history.csv when this is unset).
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import pandas as pd

DATA_DIR = Path(__file__).resolve().parent


def load_real() -> pd.DataFrame:
    """Load a real GCSS-MC work-order CSV from REAL_DATA_PATH.

    Raises NotImplementedError with a pointer to the schema docstring when
    REAL_DATA_PATH is unset. Returns a DataFrame with the schema documented
    above.
    """
    path = os.getenv("REAL_DATA_PATH")
    if not path:
        raise NotImplementedError(
            "REAL_DATA_PATH not set. See data/load_real.py docstring for the "
            "required GCSS-MC work-order schema."
        )
    df = pd.read_csv(path)
    required = {"date", "platform", "nsn", "qty_consumed", "subsystem"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"Real-data CSV missing required columns: {missing}")
    return df


def load_nsn_catalog() -> list[dict]:
    """Load NSN catalog (synthetic by default; override via env)."""
    path = os.getenv("REAL_NSN_CATALOG_PATH",
                     str(DATA_DIR / "nsn_catalog.json"))
    return json.loads(Path(path).read_text())


def load_forward_nodes() -> list[dict]:
    """Load forward-node inventory (synthetic by default; override via env)."""
    path = os.getenv("REAL_FORWARD_NODES_PATH",
                     str(DATA_DIR / "forward_nodes.json"))
    return json.loads(Path(path).read_text())
