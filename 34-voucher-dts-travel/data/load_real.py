"""Real-data ingestion stub for VOUCHER.

Governing doctrine: **Joint Travel Regulations (JTR)**, issued by the Defense
Travel Management Office (DTMO). CONUS per-diem rates flow from GSA per JTR
Ch 2; OCONUS per-diem rates are published by DoD/DTMO under JTR Ch 3.
Government Travel Charge Card (GTCC) oversight is governed by **DoDFMR
Volume 9, Chapter 5** with unit-level oversight performed by the
**Agency/Organization Program Coordinator (APC)** per **DoDI 5154.31**.

This app ships with seeded synthetic data (`data/generate.py`) but is wired so
the real DTS / Citi Manager exports drop in with no code changes:

  1. **Defense Travel System (DTS) authorizations + vouchers**
     Source: DTS Reporting Tool (per-unit per-quarter export pulled by the
             unit S-1 / Travel Approving Official (AO)).
     Expected file: dts_records.csv
     Required columns (real DTS schema, snake_case here, JTR-aligned):
       - doc_number         : DTS document number, 6-letter+6-digit form
                              (e.g. "EJVQTR123456") — JTR-aligned travel doc id
       - ta_number          : Travel Authorization (TA) Number
       - traveler_edipi     : 10-digit DoD EDIPI of the traveler
       - traveler_name      : "F. LASTNAME"
       - traveler_grade     : pay grade ("E-3" .. "O-6") — JTR uses grade,
                              not rank, for per-diem entitlement bands
       - ao_edipi           : EDIPI of the Approving Official (AO) per JTR
       - ao_name            : "F. LASTNAME" of the AO
       - trip_purpose       : free text (TAD purpose)
       - trip_start         : YYYY-MM-DD (depart date)
       - trip_end           : YYYY-MM-DD (return date)
       - status             : DTS document status ("APPROVED" | "PENDING" |
                              "RETURNED" | "PAID" | "REJECTED")
       - total_authorized   : float $ — TA total authorized
       - total_voucher      : float $ — voucher total submitted
       - mode_of_travel     : "AIR" | "POV" | "GOV" | "RAIL" | "BUS"
       - unit_code          : MARFORPAC / IIMEF / 1MARDIV / etc.
       - unit               : long unit name
       - quarter            : "FYxx-Qy"
       - card_last4         : last 4 of the traveler's GTCC
       - tdy_city           : per-diem locality key (GSA CONUS / DTMO OCONUS)
       - nights             : integer
       - per_diem_lodging_ceiling : int $/night (per JTR-published locality rate)
       - per_diem_mie       : int $/day (per JTR-published locality rate)
       - voucher_lines_json : JSON-encoded list of:
           {"category":"lodging|mie|airfare|rental_car|ground_trans|incidentals",
            "rate_per_unit":float, "units":int, "amount":float,
            "note":optional str ("receipt_missing"|"claimed_no_card_match")}
       - seeded_issues      : (synth-only — leave blank for real data)

  2. **Citi Manager Government Travel Charge Card (GTCC) statements**
     Source: Citi Card Management System per-unit export pulled by the APC
             (Bank of America for some Marines — same schema).
     Expected file: citi_statements.csv
     Required columns (real Citi export schema, snake_case here):
       - txn_id             : bank-issued transaction id
       - card_last4         : matches dts_records.card_last4
       - traveler_edipi     : (denormalized from cardholder profile)
       - traveler_name      : (denormalized from cardholder profile)
       - traveler_grade     : (denormalized — used for grade-band reporting)
       - unit_code          : (denormalized via APC mapping)
       - unit               : (denormalized)
       - post_date          : YYYY-MM-DD
       - merchant           : merchant DBA (uppercase)
       - mcc                : 4-digit Merchant Category Code (real)
       - merchant_category  : one of {lodging, airfare, rental_car,
                                       ground_trans, meals, non_authorized, other}
                              (derived from MCC; see MCC_MAP below)
       - amount             : float $ (settled amount)
       - linked_doc_number  : (will be populated by VOUCHER's reconciler;
                               leave blank in the raw bank export)

  3. **Per-diem rates (GSA CONUS / DTMO OCONUS, governed by JTR)**
     Source: https://www.gsa.gov/travel/plan-book/per-diem-rates  (CONUS, per JTR Ch 2)
             https://www.travel.dod.mil/Allowances/Per-Diem-Rate-Lookup/
             (OCONUS, published by DTMO per JTR Ch 3)
     Expected file: per_diem_rates.json
     Shape: {"rates": [{"city": str, "state": str,
                        "lodging_per_night": int, "mie_per_day": int}, ...]}

To plug in:
    export REAL_DTS_PATH=/secure/dts_records.csv
    export REAL_CITI_PATH=/secure/citi_statements.csv
    export REAL_PER_DIEM_PATH=/secure/per_diem_rates.json
    streamlit run src/app.py --server.port 3034

Real DTS Reporting Tool exports do not always arrive with these exact header
strings — column names vary slightly by report template. The mapping below
covers the common DTS Reporting Tool report headers; extend as needed for
your unit's export template.

| Raw column (DTS Reporting Tool)    | Our field             | Transform                           |
|------------------------------------|-----------------------|-------------------------------------|
| Document Number                    | doc_number            | uppercase, strip spaces             |
| Travel Authorization Number        | ta_number             | uppercase                           |
| Traveler EDIPI                     | traveler_edipi        | 10-digit string                     |
| Traveler Name                      | traveler_name         | "F. LASTNAME"                       |
| Pay Grade                          | traveler_grade        | normalize ("E-3", "O-4", ...)       |
| Approving Official EDIPI           | ao_edipi              | 10-digit string                     |
| Approving Official Name            | ao_name               | "F. LASTNAME"                       |
| Trip Purpose                       | trip_purpose          | as-is                               |
| Departure Date / Return Date       | trip_start / trip_end | parse YYYY-MM-DD                    |
| Document Status                    | status                | uppercase                           |
| Total Authorized Amount            | total_authorized      | float                               |
| Total Voucher Amount               | total_voucher         | float                               |
| Mode of Travel                     | mode_of_travel        | "AIR" | "POV" | "GOV" | "RAIL"     |
| Org Code                           | unit_code             | uppercase                           |
| Org Name                           | unit                  | titlecase                           |
| FY / Quarter                       | quarter               | "FY" + value                        |
| GTCC Last 4                        | card_last4            | str pad-4                           |
| TDY Location                       | tdy_city              | per-diem locality key lookup        |
| Lodging Rate / Lodging Qty         | per_diem ceiling      | join to JTR locality table          |
| Voucher Line Items (XML / JSON)    | voucher_lines_json    | parse → unified line list           |

| Raw column (Citi Manager export)   | Our field             | Transform                           |
|------------------------------------|-----------------------|-------------------------------------|
| Transaction Reference Number       | txn_id                | uppercase                           |
| Card Last 4                        | card_last4            | str pad-4                           |
| Posting Date                       | post_date             | parse YYYY-MM-DD                    |
| Merchant Name                      | merchant              | uppercase, strip extra spaces       |
| Merchant Category Code             | mcc                   | 4-digit string                      |
| MCC                                | merchant_category     | MCC bucket lookup (see MCC_MAP)     |
| Transaction Amount                 | amount                | float                               |

MCC_MAP (real MCCs — extend in your APC's data dictionary):
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

A non_authorized merchant_category trip yields a **GTCC misuse flag per
DoDFMR Vol 9 Chapter 5** which is referred to the unit APC for cardholder
counseling per DoDI 5154.31.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

try:
    import pandas as pd  # noqa: F401  (only required for the real path)
except ImportError:
    pd = None  # type: ignore


# Mapping from common DTS Reporting Tool report headers -> our canonical
# snake_case schema. The DTS Reporting Tool emits human-readable headers in
# most templates; see module docstring for full table.
DTS_HEADER_RENAME = {
    "Document Number": "doc_number",
    "Travel Authorization Number": "ta_number",
    "Traveler EDIPI": "traveler_edipi",
    "Traveler Name": "traveler_name",
    "Pay Grade": "traveler_grade",
    "Approving Official EDIPI": "ao_edipi",
    "Approving Official Name": "ao_name",
    "Trip Purpose": "trip_purpose",
    "Departure Date": "trip_start",
    "Return Date": "trip_end",
    "Document Status": "status",
    "Total Authorized Amount": "total_authorized",
    "Total Voucher Amount": "total_voucher",
    "Mode of Travel": "mode_of_travel",
    "Org Code": "unit_code",
    "Org Name": "unit",
    "GTCC Last 4": "card_last4",
    "TDY Location": "tdy_city",
}

CITI_HEADER_RENAME = {
    "Transaction Reference Number": "txn_id",
    "Card Last 4": "card_last4",
    "Posting Date": "post_date",
    "Merchant Name": "merchant",
    "Merchant Category Code": "mcc",
    "Transaction Amount": "amount",
}


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
    df = df.rename(columns={k: v for k, v in DTS_HEADER_RENAME.items() if k in df.columns})
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
    df = df.rename(columns={k: v for k, v in CITI_HEADER_RENAME.items() if k in df.columns})
    return df.to_dict(orient="records")


def load_real_per_diem() -> dict:
    path = os.getenv("REAL_PER_DIEM_PATH")
    if not path:
        raise NotImplementedError(
            "REAL_PER_DIEM_PATH not set. See module docstring."
        )
    return json.loads(Path(path).read_text())
