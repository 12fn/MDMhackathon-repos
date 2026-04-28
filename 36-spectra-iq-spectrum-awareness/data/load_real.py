"""Real-data ingestion stub for SPECTRA.

To plug in real I/Q captures from the **NIST Wi-Fi & Bluetooth I/Q RF
Recordings (2.4 / 5 GHz)** corpus
(https://data.nist.gov/od/id/mds2-2731 — 900 one-second I/Q captures at
30 MS/s with SigMF-compatible CSV metadata), do the following:

1. Download the NIST corpus tarball (~200 GB total — pick a subset).
2. For each .sigmf-data file, re-save as a numpy `.npy` complex64 array
   into a directory of your choice (e.g. /data/nist_iq/captures/).
3. Build a metadata CSV alongside the captures dir matching this schema
   (already SigMF-compatible — these are the names NIST uses):

   - scenario_id              : str  (any unique id, e.g. the file stem)
   - label                    : str  (human description)
   - filename                 : str  (relative path to the .npy)
   - synth_sample_rate_MSPS   : float (8.0 if you keep our 8 MS/s synth rate;
                                       or the rate you actually decimated to)
   - nist_sample_rate_MSPS    : float (30.0 — the canonical NIST rate)
   - center_freq_GHz          : float
   - bw_MHz                   : float
   - gain_dB                  : int
   - hardware                 : str  (e.g. "USRP-X300/UBX160/VERT2450")
   - noise_floor_dBm          : int
   - calibration              : str
   - expected_anomaly         : str  ("nominal" if you have no ground truth)

4. Set REAL_DATA_PATH=/path/to/nist_iq and re-launch:

       REAL_DATA_PATH=/data/nist_iq streamlit run src/app.py ...

The app's data loader checks `REAL_DATA_PATH/captures_metadata.csv` first;
if missing it falls back to the synthetic captures in `data/captures/`.

Citation:
  Souryal, M. R. and Caromi, R. *NIST Wi-Fi & Bluetooth I/Q RF
  Recordings (2.4 / 5 GHz)*. NIST Public Data Repository, 2024.
  https://data.nist.gov/od/id/mds2-2731
"""
from __future__ import annotations

import os
from pathlib import Path

import pandas as pd

REQUIRED_COLS = {
    "scenario_id", "label", "filename",
    "synth_sample_rate_MSPS", "nist_sample_rate_MSPS",
    "center_freq_GHz", "bw_MHz", "gain_dB",
    "hardware", "noise_floor_dBm", "calibration", "expected_anomaly",
}


def load_real() -> pd.DataFrame:
    path = os.getenv("REAL_DATA_PATH")
    if not path:
        raise NotImplementedError(
            "REAL_DATA_PATH not set. See module docstring for the required "
            "schema and the NIST I/Q corpus extraction recipe."
        )
    p = Path(path)
    md = p / "captures_metadata.csv"
    if not md.exists():
        raise FileNotFoundError(
            f"Expected {md} not found. Build a captures_metadata.csv per the "
            "schema documented in this module's docstring."
        )
    df = pd.read_csv(md)
    missing = REQUIRED_COLS - set(df.columns)
    if missing:
        raise ValueError(
            f"Real metadata {md} missing required columns: {sorted(missing)}. "
            "See module docstring for the canonical SigMF-compatible schema."
        )
    return df
