"""Real-data ingestion stub for TRACE / LogTRACE.

Two real datasets plug in here:

  1. **GCSS-MC depot inventory** — real CSV export from the Global Combat Support
     System – Marine Corps. Replace `gcssmc_depots.csv` with the live pull. Required
     columns:
       - depot_id     (string)              e.g. MCLB-ALB
       - name         (string)              human-readable depot name
       - location     (string)              City, State/Country
       - lat, lon     (float)               for the sources panel map
       - role         (string)              short description
       - on_hand_<C>  (numeric, C in I..IX) on-hand quantity for each supply class
       - unit_<C>     (string,  C in I..IX) unit-of-issue label per class
                                            (lbs / gal / ea)

  2. **Logistics-and-supply-chain-dataset (California)** — public Kaggle dataset
     of supply-chain transactions. Used to derive realistic *consumption-rate*
     baselines per supply class (overrides synthetic doctrine_rates.json values).
     Required columns:
       - product_category   → mapped to Class I-IX
       - quantity_shipped   (numeric)
       - ship_date          (date)
       - shipped_to         (region; for regional-rate refinement)

To plug in real data, set:
    REAL_DEPOT_CSV=/path/to/gcssmc_depots.csv
    REAL_LSC_CSV=/path/to/logistics-and-supply-chain.csv

Then point src/app.py at it via these env vars; the rest of the pipeline runs
unchanged.
"""
from __future__ import annotations

import os
from pathlib import Path

import pandas as pd


def load_real_depots() -> pd.DataFrame:
    """Load real GCSS-MC depot inventory CSV. Same shape as data/gcssmc_depots.csv."""
    path = os.getenv("REAL_DEPOT_CSV")
    if not path:
        raise NotImplementedError(
            "REAL_DEPOT_CSV not set. See module docstring for required schema. "
            "Falling back to synthetic data/gcssmc_depots.csv shipped in this app."
        )
    p = Path(path).expanduser().resolve()
    if not p.exists():
        raise FileNotFoundError(f"REAL_DEPOT_CSV={p} does not exist on disk.")
    return pd.read_csv(p)


def load_real_lsc() -> pd.DataFrame:
    """Load Kaggle Logistics-and-supply-chain-dataset (California)."""
    path = os.getenv("REAL_LSC_CSV")
    if not path:
        raise NotImplementedError(
            "REAL_LSC_CSV not set. See module docstring for required schema."
        )
    p = Path(path).expanduser().resolve()
    if not p.exists():
        raise FileNotFoundError(f"REAL_LSC_CSV={p} does not exist on disk.")
    return pd.read_csv(p)


def derive_rates_from_lsc(df: pd.DataFrame) -> dict:
    """Optional: derive empirical consumption rates from a real LSC export.

    Stub — implement the category-to-class mapping for your local schema. Returns
    a dict in the same shape as data/doctrine_rates.json so downstream code is
    unchanged.
    """
    raise NotImplementedError(
        "derive_rates_from_lsc() not implemented. Map your LSC product_category "
        "column to USMC Class I-IX, group by (climate, opscale), and emit a dict "
        "matching the shape of data/doctrine_rates.json."
    )
