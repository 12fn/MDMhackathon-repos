"""Real-data ingestion stub for VOUCHER.

This app ships with seeded synthetic data (`data/generate.py`) but is wired so
the real DTS / Citi Manager exports drop in with no code changes:

  1. **Defense Travel System (DTS) authorizations + vouchers**
     Source: DTS Reporting Tool (DTS-RT) per-unit per-quarter export.
             (operator persona: unit S-1 / Travel Approving Official)
     Expected file: dts_records.csv
     Required columns:
       - record_id          : DTS document ID (e.g. "K1Z3LR4-V001")
       - unit_code          : MARFORPAC / IIMEF / 1MARDIV / etc.
       - unit               : long unit name
       - quarter            : "FYxx-Qy"
       - traveler_rank      : "LCpl" .. "Col"
       - traveler_name      : "F. LASTNAME"
       - card_last4         : last 4 of the traveler's GTC
       - trip_reason        : free text (TAD reason)
       - tdy_city           : GSA per-diem city key
       - depart_date        : YYYY-MM-DD
       - return_date        : YYYY-MM-DD
       - nights             : integer
       - transport_mode     : "AIR" | "POV"
       - per_diem_lodging_ceiling : int $/night (GSA)
       - per_diem_mie       : int $/day (GSA)
       - voucher_total      : float $ (sum of voucher_lines)
       - voucher_lines_json : JSON-encoded list of:
           {"category":"lodging|mie|airfare|rental_car|ground_trans|incidentals",
            "rate_per_unit":float, "units":int, "amount":float,
            "note":optional str ("receipt_missing"|"claimed_no_card_match")}
       - auth_status        : "APPROVED" | "REJECTED" | "PENDING"
       - voucher_status     : "SUBMITTED" | "PAID" | "RETURNED"
       - seeded_issues      : (synth-only — leave blank for real data)

  2. **Citi Manager Government Travel Card statements**
     Source: Citi Card Management System per-unit export
             (Bank of America for some Marines — same schema)
     Expected file: citi_statements.csv
     Required columns:
       - txn_id             : bank-issued transaction id
       - card_last4         : matches dts_records.card_last4
       - traveler_rank      : (denormalized from cardholder profile)
       - traveler_name      : (denormalized from cardholder profile)
       - unit_code          : (denormalized via APC mapping)
       - unit               : (denormalized)
       - post_date          : YYYY-MM-DD
       - merchant           : merchant DBA (uppercase)
       - merchant_category  : one of {lodging, airfare, rental_car,
                                       ground_trans, meals, non_authorized, other}
                              (derived from MCC; see column-mapping table below)
       - amount             : float $ (settled amount)
       - linked_dts_record  : (will be populated by VOUCHER's reconciler;
                               leave blank in the raw bank export)

  3. **GSA per-diem rates**
     Source: https://www.gsa.gov/travel/plan-book/per-diem-rates  (CONUS)
             https://www.travel.dod.mil/Allowances/Per-Diem-Rate-Lookup/
             (OCONUS through DOD JTR)
     Expected file: per_diem_rates.json
     Shape: {"rates": [{"city": str, "state": str,
                        "lodging_per_night": int, "mie_per_day": int}, ...]}

To plug in:
    export REAL_DTS_PATH=/secure/dts_records.csv
    export REAL_CITI_PATH=/secure/citi_statements.csv
    export REAL_PER_DIEM_PATH=/secure/per_diem_rates.json
    streamlit run src/app.py --server.port 3034

Column mapping notes (raw DTS-RT / Citi export -> our schema):

| Raw column (DTS-RT)        | Our field             | Transform                                |
|----------------------------|-----------------------|------------------------------------------|
| TANUM (Travel Auth Number) | record_id             | strip dashes                             |
| AOREP                      | unit_code             | uppercase                                |
| AONAME                     | unit                  | titlecase                                |
| FY_Q                       | quarter               | "FY" + value                             |
| TRAV_RANK                  | traveler_rank         | normalize                                |
| TRAV_LNAME, TRAV_FI        | traveler_name         | "F. LASTNAME"                            |
| GTC_LAST4                  | card_last4            | str pad-4                                |
| TDY_LOC                    | tdy_city              | GSA city key lookup                      |
| TDY_DEP_DT, TDY_RTN_DT     | depart_date/return    | parse YYYY-MM-DD                         |
| LODGE_RT, LODGE_QTY        | per_diem ceiling      | join to GSA rate table on tdy_city       |
| TOT_VCHR_AMT               | voucher_total         | float                                    |
| LINE_ITEMS (XML / JSON)    | voucher_lines_json    | parse → unified line list                |

| Raw column (Citi export)   | Our field             | Transform                                |
|----------------------------|-----------------------|------------------------------------------|
| TRANS_REF_NO               | txn_id                | uppercase                                |
| CARD_LAST_4                | card_last4            | str pad-4                                |
| POST_DT                    | post_date             | parse YYYY-MM-DD                         |
| MERCHANT_NM                | merchant              | uppercase, strip extra spaces            |
| MCC                        | merchant_category     | MCC bucket lookup (see MCC_MAP below)    |
| TRANS_AMT                  | amount                | float                                    |

MCC_MAP (illustrative — extend in your APC's data dictionary):
    7011        -> "lodging"     (hotels)
    4511        -> "airfare"     (airlines)
    7512        -> "rental_car"  (auto rental)
    4121, 4111  -> "ground_trans" (taxi, rail, transit)
    5812, 5814  -> "meals"       (restaurants, fast food)
    7995        -> "non_authorized" (gambling)
    5944        -> "non_authorized" (jewelry)
    5921        -> "non_authorized" (liquor)
    7832        -> "non_authorized" (motion picture theaters)
    others      -> "other"
"""
from __future__ import annotations

import json
import os
from pathlib import Path

try:
    import pandas as pd  # noqa: F401  (only required for the real path)
except ImportError:
    pd = None  # type: ignore


def load_real_dts() -> list[dict]:
    """Return DTS rows in the schema generate.py emits."""
    path = os.getenv("REAL_DTS_PATH")
    if not path:
        raise NotImplementedError(
            "REAL_DTS_PATH not set. See module docstring for the expected "
            "DTS Reporting Tool export column schema and MCC mapping."
        )
    if pd is None:
        raise RuntimeError("pandas required for real-data ingest. `pip install pandas`.")
    df = pd.read_csv(path)
    # Apply documented column mapping if raw column names are present
    rename = {
        "TANUM": "record_id", "AOREP": "unit_code", "AONAME": "unit",
        "FY_Q": "quarter", "TRAV_RANK": "traveler_rank",
        "GTC_LAST4": "card_last4", "TDY_LOC": "tdy_city",
        "TDY_DEP_DT": "depart_date", "TDY_RTN_DT": "return_date",
        "TOT_VCHR_AMT": "voucher_total",
    }
    df = df.rename(columns={k: v for k, v in rename.items() if k in df.columns})
    return df.to_dict(orient="records")


def load_real_citi() -> list[dict]:
    path = os.getenv("REAL_CITI_PATH")
    if not path:
        raise NotImplementedError(
            "REAL_CITI_PATH not set. See module docstring for the Citi "
            "Manager export column schema and MCC mapping."
        )
    if pd is None:
        raise RuntimeError("pandas required for real-data ingest. `pip install pandas`.")
    df = pd.read_csv(path)
    rename = {
        "TRANS_REF_NO": "txn_id", "CARD_LAST_4": "card_last4",
        "POST_DT": "post_date", "MERCHANT_NM": "merchant",
        "TRANS_AMT": "amount",
    }
    df = df.rename(columns={k: v for k, v in rename.items() if k in df.columns})
    return df.to_dict(orient="records")


def load_real_per_diem() -> dict:
    path = os.getenv("REAL_PER_DIEM_PATH")
    if not path:
        raise NotImplementedError(
            "REAL_PER_DIEM_PATH not set. See module docstring."
        )
    return json.loads(Path(path).read_text())
