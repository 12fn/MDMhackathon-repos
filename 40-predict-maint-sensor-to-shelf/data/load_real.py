"""Real-data ingestion stubs for PREDICT-MAINT.

PREDICT-MAINT covers FOUR LOGCOM use cases on FIVE real datasets. Each dataset
is documented below with the swap path, expected schema, and the env var that
points at it. No real data is shipped — set the env var, drop the file, and
the same downstream pipeline runs.

------------------------------------------------------------------------------
1. CWRU Bearing Fault Data
   Source : https://engineering.case.edu/bearingdatacenter/download-data-file
   Format : MATLAB .mat per fault condition (12k_DriveEnd_Bearing_Fault_Data)
   Schema : Each .mat file contains a variable named like "X097_DE_time" — a
            1-D float array of accelerometer samples at 12 kHz drive-end.
            File naming convention encodes (load HP, fault diameter, fault type,
            position). Healthy baseline files are 097.mat-100.mat.
   Env    : REAL_CWRU_MAT_DIR=/abs/path/to/12k_DriveEnd_Bearing_Fault_Data

2. NASA Predictive Maintenance — CMAPSS Turbofan RUL
   Source : https://data.nasa.gov/dataset/cmapss-jet-engine-simulated-data
   Format : ASCII tables; train_FD00X.txt / test_FD00X.txt / RUL_FD00X.txt
   Schema : columns = [unit, cycle, op_set_1, op_set_2, op_set_3,
            sensor_1 ... sensor_21]. RUL targets in RUL_FD00X.txt.
   Env    : REAL_CMAPSS_DIR=/abs/path/to/CMAPSSData

3. Microsoft Azure Predictive Maintenance (synthetic but real schema)
   Source : https://github.com/microsoft/AzureML-fastai/tree/master/data/PdM
            (or any of the Azure PdM tutorial mirrors)
   Format : 5 CSVs — telemetry / errors / maint / failures / machines
   Schema : telemetry: datetime, machineID, volt, rotate, pressure, vibration
            failures: datetime, machineID, failure
   Env    : REAL_AZURE_PDM_DIR=/abs/path/to/PdM

4. GCSS-MC Supply & Maintenance extract
   Source : USMC LOGCOM portal (controlled). LOGCOM publishes a sanitised
            workorder + parts extract for hackathons.
   Format : .zip containing CSV (workorders.csv, parts_consumed.csv)
   Schema : workorders: wo_id, date, platform, vehicle_id, pmcs_code,
                        nsn_consumed, qty
            parts_consumed: nsn, fsc, part_name, primary_platform, unit_price
   Env    : REAL_GCSSMC_ZIP=/abs/path/to/gcssmc_extract.zip

5. Inventory Control Management (ICM) workbook
   Source : LOGCOM published Excel workbook (the "5,000-item Excel hell")
   Format : .xlsx; ~5,000 rows; columns map to (NSN / Nomenclature / Qty /
            Required / Location / Custodian / Sensitivity / Last Inventoried)
   Env    : REAL_ICM_XLSX=/abs/path/to/icm_inventory.xlsx
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import numpy as np
import pandas as pd

DATA_DIR = Path(__file__).resolve().parent


# ---- 1. CWRU Bearing Fault ------------------------------------------------
def load_cwru() -> dict:
    """Read CWRU MAT files into the same shape as data/vibration_corpus.npz."""
    root = os.getenv("REAL_CWRU_MAT_DIR")
    if not root:
        raise NotImplementedError(
            "REAL_CWRU_MAT_DIR not set. See module docstring for the schema. "
            "Run `python data/generate.py` to use the synthetic corpus."
        )
    try:
        from scipy.io import loadmat
    except ImportError as e:
        raise RuntimeError("scipy is required to read CWRU .mat files") from e
    signals, labels = [], []
    label_for_file = {  # map CWRU file prefixes -> our 4-class scheme
        "097": 0, "098": 0, "099": 0, "100": 0,           # healthy
        "105": 1, "106": 1, "107": 1, "108": 1,           # inner race
        "118": 3, "119": 3, "120": 3, "121": 3,           # ball
        "130": 2, "131": 2, "132": 2, "133": 2,           # outer race
    }
    for mat_path in sorted(Path(root).glob("*.mat")):
        prefix = mat_path.stem[:3]
        if prefix not in label_for_file:
            continue
        mat = loadmat(mat_path)
        de_keys = [k for k in mat if k.endswith("_DE_time")]
        if not de_keys:
            continue
        sig = np.asarray(mat[de_keys[0]]).flatten().astype(np.float32)
        # Slice into 1-second windows (12 kHz)
        win = 12_000
        for i in range(0, len(sig) - win, win):
            signals.append(sig[i:i + win])
            labels.append(label_for_file[prefix])
    return {
        "signals": np.stack(signals).astype(np.float32),
        "labels": np.array(labels, dtype=np.int32),
        "fs": np.int32(12_000),
    }


# ---- 2. NASA CMAPSS turbofan RUL -----------------------------------------
def load_cmapss(subset: str = "FD001") -> pd.DataFrame:
    root = os.getenv("REAL_CMAPSS_DIR")
    if not root:
        raise NotImplementedError(
            "REAL_CMAPSS_DIR not set. See module docstring for the schema."
        )
    cols = ["unit", "cycle", "op1", "op2", "op3"] + [f"s{i}" for i in range(1, 22)]
    train = pd.read_csv(Path(root) / f"train_{subset}.txt",
                        sep=r"\s+", header=None, names=cols)
    return train


# ---- 3. Microsoft Azure Predictive Maintenance ---------------------------
def load_azure_pdm() -> dict[str, pd.DataFrame]:
    root = os.getenv("REAL_AZURE_PDM_DIR")
    if not root:
        raise NotImplementedError(
            "REAL_AZURE_PDM_DIR not set. See module docstring for the schema."
        )
    rp = Path(root)
    return {
        "telemetry": pd.read_csv(rp / "PdM_telemetry.csv"),
        "errors":    pd.read_csv(rp / "PdM_errors.csv"),
        "maint":     pd.read_csv(rp / "PdM_maint.csv"),
        "failures":  pd.read_csv(rp / "PdM_failures.csv"),
        "machines":  pd.read_csv(rp / "PdM_machines.csv"),
    }


# ---- 4. GCSS-MC Supply & Maintenance extract -----------------------------
def load_gcssmc() -> pd.DataFrame:
    """Unzip + load the GCSS-MC workorders.csv into the maintenance_history.csv shape."""
    path = os.getenv("REAL_GCSSMC_ZIP")
    if not path:
        raise NotImplementedError(
            "REAL_GCSSMC_ZIP not set. See module docstring for the schema."
        )
    import zipfile
    with zipfile.ZipFile(path) as z:
        with z.open("workorders.csv") as f:
            df = pd.read_csv(f)
    rename = {
        "wo_id": "work_order_id",
        "nsn_consumed": "nsn",
        "qty": "qty_consumed",
    }
    return df.rename(columns={k: v for k, v in rename.items() if k in df.columns})


# ---- 5. Inventory Control Management workbook ----------------------------
ICM_RENAMES = {
    "nsn": "nsn", "nomenclature": "nomenclature",
    "quantity": "qty_on_hand", "qty": "qty_on_hand",
    "required": "qty_required", "qty required": "qty_required",
    "location": "location_id", "bin": "location_id",
    "responsible marine": "responsible_marine", "custodian": "responsible_marine",
    "sensitivity": "sensitivity_class", "sensitivity class": "sensitivity_class",
    "class": "category",
    "last inventoried": "last_inventoried_date",
    "condition code": "condition_code",
}


def load_icm() -> pd.DataFrame:
    path = os.getenv("REAL_ICM_XLSX")
    if not path:
        raise NotImplementedError(
            "REAL_ICM_XLSX not set. See module docstring for the schema."
        )
    p = Path(path)
    if p.suffix.lower() in (".xlsx", ".xls", ".xlsm"):
        df = pd.read_excel(p, engine="openpyxl")
    else:
        df = pd.read_csv(p)
    df.columns = [c.strip() for c in df.columns]
    rename_map = {c: ICM_RENAMES[c.lower()] for c in df.columns if c.lower() in ICM_RENAMES}
    return df.rename(columns=rename_map)


# ---- Convenience: load everything that's pointed at -----------------------
def load_real() -> dict[str, object]:
    """Best-effort multi-dataset loader. Each dataset is loaded if its env var
    is set, otherwise NotImplementedError carries forward the schema doc."""
    out: dict[str, object] = {}
    for name, fn in [
        ("cwru", load_cwru),
        ("cmapss", load_cmapss),
        ("azure_pdm", load_azure_pdm),
        ("gcssmc", load_gcssmc),
        ("icm", load_icm),
    ]:
        try:
            out[name] = fn()
        except NotImplementedError:
            continue
    if not out:
        raise NotImplementedError(
            "No REAL_* env vars set. See module docstring; pick at least one of "
            "REAL_CWRU_MAT_DIR / REAL_CMAPSS_DIR / REAL_AZURE_PDM_DIR / "
            "REAL_GCSSMC_ZIP / REAL_ICM_XLSX."
        )
    return out
