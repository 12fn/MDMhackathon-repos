"""Real-data ingestion stub for QUEUE — Depot Maintenance Throughput Optimizer.

To plug in real data, implement load_real() to read from GCSS-MC depot extracts
and emit the same shape as data/generate.py produces. Required schemas:

  backlog (CSV) — one row per inducted-or-pending end item:
    bumper_no              : unique end-item identifier (e.g. MTVR-1024)
    family                 : one of {MTVR, AAV, LAV, MV-22, M1A1}
    family_long            : long-form name
    depot                  : one of {ALB, BAR, BIC} (Albany / Barstow / Blount Island)
    priority               : int 1-4 (FAD/FD code; 1 = combat-essential)
    priority_label         : human-readable priority band
    labor_hours_est        : estimated direct labor hours for full induction
    skills_needed          : comma-separated skill codes (hydraulics, powertrain,
                             armor, avionics, weapons)
    required_parts_nsn     : comma-separated NSNs needed to complete induction
    induct_date            : ISO YYYY-MM-DD date end item was received
    status                 : PENDING | INDUCTED

  parts_availability (CSV) — one row per NSN:
    nsn                    : 13-char National Stock Number
    nomenclature           : human-readable part name
    used_by                : comma-separated end-item families
    on_hand                : integer count on hand
    eta_days               : integer days until next expected receipt
    eta_date               : ISO YYYY-MM-DD or empty if on hand
    long_pole              : Y | N (whether NSN is a known schedule constraint)
    unit_cost_usd          : integer USD
    source                 : DLA Land | DLA Aviation | OEM (...)

  depot_capacity (JSON) — list of 3 depot objects:
    id                     : ALB | BAR | BIC
    name                   : full depot name
    location               : city, state
    bays                   : integer bay count
    shifts_per_day         : 1, 2, or 3
    skills                 : {skill_code: int_capacity, ...}
    specialty              : list of end-item families primarily worked

Then point src/app.py at it via env: QUEUE_REAL_DATA_DIR=/path/to/dir
(directory must contain backlog.csv, parts_availability.csv, depot_capacity.json).

Suggested real sources:
  - GCSS-MC (Global Combat Support System — Marine Corps) ad-hoc reports
  - DLA WebFlis NSN catalog cross-reference for parts metadata
  - MARCORLOGCOM industrial-base directorate weekly capacity reports
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import pandas as pd


def load_real() -> dict:
    """Return {'backlog': DataFrame, 'parts': DataFrame, 'depots': list}.

    Raises NotImplementedError when QUEUE_REAL_DATA_DIR is not set.
    """
    real_dir = os.getenv("QUEUE_REAL_DATA_DIR")
    if not real_dir:
        raise NotImplementedError(
            "QUEUE_REAL_DATA_DIR not set. See module docstring for required schema. "
            "Until then the app reads from data/backlog.csv, data/parts_availability.csv, "
            "and data/depot_capacity.json (synthetic but plausible)."
        )
    base = Path(real_dir)
    return {
        "backlog": pd.read_csv(base / "backlog.csv"),
        "parts": pd.read_csv(base / "parts_availability.csv"),
        "depots": json.loads((base / "depot_capacity.json").read_text()),
    }
