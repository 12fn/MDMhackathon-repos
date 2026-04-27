"""Real-data ingestion stub for CHAIN.

To plug in real data, implement load_real() to fuse the three real datasets that
inspired this synthetic stand-in and emit the same shape as data/generate.py:

  Datasets (Kaggle):
    1. Global Supply Chain Disruption & Resilience
       https://www.kaggle.com/datasets/datasetengineer/global-supply-chain-disruption-and-resilience
       Required columns: event_date, region, event_type, severity, sector, days_impact

    2. Global supply chain risk and logistics dataset
       https://www.kaggle.com/datasets/dshahidul/global-supply-chain-risk-and-logistics
       Required columns: supplier_id, country, category, annual_value_usd, lead_time_days

    3. Global trade 2024-2026 dataset
       https://www.kaggle.com/datasets/kanchana1990/global-trade-2024
       Required columns: origin, destination, mode, annual_value_usd, hs_code_class

Output shape (consumed by src/agent.py + src/graph.py):
  suppliers.json      list of {id, name, kind, country, category, lat, lon,
                       annual_value_musd, criticality}
  edges.json          list of {a, b, mode, annual_value_musd}
  chokepoints.json    list of {id, name, lat, lon, status, daily_transit_musd,
                       current_event}
  disruption_events.csv  date, event_type, target_id, target_name, headline,
                       severity, estimated_impact_days, value_at_risk_musd

Then point src/app.py at the real data via env var:
    REAL_DATA_DIR=/path/to/real/data/dir
"""
from __future__ import annotations

import os
import json
from pathlib import Path

import pandas as pd


def load_real() -> dict:
    """Load + reshape the three real datasets into CHAIN's normalized format.

    Returns a dict with keys: suppliers, edges, chokepoints, events. Caller
    persists those alongside the synthetic generate.py output.
    """
    base = os.getenv("REAL_DATA_DIR")
    if not base:
        raise NotImplementedError(
            "REAL_DATA_DIR not set. Drop the three CSVs in a directory and set "
            "REAL_DATA_DIR=/path/to/dir. Schema: see module docstring."
        )
    base = Path(base)

    # 1. Risk + logistics → suppliers + criticality
    risk_csv = base / "global_supply_chain_risk_and_logistics.csv"
    if not risk_csv.exists():
        raise FileNotFoundError(f"Missing {risk_csv}")
    risk_df = pd.read_csv(risk_csv)

    # 2. Disruption + resilience → events feed
    disrupt_csv = base / "global_supply_chain_disruption_and_resilience.csv"
    if not disrupt_csv.exists():
        raise FileNotFoundError(f"Missing {disrupt_csv}")
    disrupt_df = pd.read_csv(disrupt_csv)

    # 3. Global trade → edges (annual flow $ between origin/destination)
    trade_csv = base / "global_trade_2024_2026.csv"
    if not trade_csv.exists():
        raise FileNotFoundError(f"Missing {trade_csv}")
    trade_df = pd.read_csv(trade_csv)

    # NOTE: Implementer maps real columns to CHAIN's normalized shape here.
    # The synthetic generator already documents target columns; this stub just
    # surfaces the real frames and lets you proceed.
    return {
        "suppliers_raw": risk_df,
        "events_raw": disrupt_df,
        "edges_raw": trade_df,
    }


if __name__ == "__main__":
    print(load_real())
