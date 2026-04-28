"""Real-data ingestion stub for CUAS-DETECT.

Two real datasets pair into this app:

  1. Drone Recognition based on RF Spectrogram (DroneRF-B Spectra)
     https://ieee-dataport.org/  (search for "DroneRF-B Spectra")
     Distribution: per-recording .png spectrogram tiles (or pre-computed .npy
     intensity arrays) labeled by UAS class (DJI Mavic, Parrot, etc.).

  2. Drone RF Identification dataset (DroneRC RF Signal)
     https://ieee-dataport.org/  (search for "DroneRC RF Signal")
     Distribution: CSV of decoded controller frames labeled by manufacturer +
     controller model, paired with raw I/Q captures.

To plug in:

  Drop spectrogram tiles (.png + matching .npy with the same stem) into
      apps/35-cuas-detect/data/spectra/
  and a paired CSV at
      apps/35-cuas-detect/data/dronerc.csv  (or set REAL_RC_CSV)
  with columns:
    - id              str  (matches the .png/.npy stem)
    - manufacturer    str
    - controller      str
    - band_ghz        str  ("2.4", "5.8", "0.9", "2.4 / 5.8")
    - hopping         str  ("FHSS 1.4ms", "WiFi 802.11n", ...)
    - protocol        str  ("OcuSync", "WiFi", "LoRa", "DSMX", ...)

Then either set:
    REAL_DATA_PATH=/path/to/data/spectra
    REAL_RC_CSV=/path/to/data/dronerc.csv
or just leave the files in the default locations above and the app will
auto-discover them.

The same multi-stage classifier (heuristic features → vision LLM → engagement
brief) runs unchanged — only the ingestion path changes.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Iterator

import numpy as np
import pandas as pd


REQUIRED_RC_COLS = {
    "id", "manufacturer", "controller", "band_ghz", "hopping", "protocol",
}


def load_real_spectra(spectra_dir: str | None = None) -> Iterator[dict]:
    """Yield {id, png_path, npy_path, label_meta?} for every spectrogram tile."""
    p = Path(spectra_dir or os.getenv("REAL_DATA_PATH") or "data/spectra")
    if not p.exists():
        raise NotImplementedError(
            f"Real spectra dir not found: {p}\n"
            "Set REAL_DATA_PATH or drop DroneRF-B Spectra .png/.npy files there. "
            "See module docstring."
        )
    for png in sorted(p.glob("*.png")):
        npy = png.with_suffix(".npy")
        if not npy.exists():
            # If we only have a PNG, allow loading via Pillow + grayscale convert
            yield {"id": png.stem, "png_path": str(png), "npy_path": None}
            continue
        yield {"id": png.stem, "png_path": str(png), "npy_path": str(npy)}


def load_real_rc(csv_path: str | None = None) -> pd.DataFrame:
    """Load DroneRC controller fingerprint CSV."""
    p = Path(csv_path or os.getenv("REAL_RC_CSV") or "data/dronerc.csv")
    if not p.exists():
        raise NotImplementedError(
            f"DroneRC CSV not found: {p}\n"
            "Set REAL_RC_CSV or drop the controller-fingerprint CSV there. "
            "Required columns: " + ", ".join(sorted(REQUIRED_RC_COLS))
        )
    df = pd.read_csv(p)
    missing = REQUIRED_RC_COLS - set(df.columns)
    if missing:
        raise ValueError(
            f"DroneRC CSV {p} is missing required columns: {sorted(missing)}"
        )
    return df


def load_npy_intensity(npy_path: str) -> np.ndarray:
    """Load a spectrogram .npy as the same float32 [0,1] HxW array shape we use."""
    arr = np.load(npy_path).astype(np.float32)
    # min-max normalize
    mn, mx = float(arr.min()), float(arr.max())
    if mx > mn:
        arr = (arr - mn) / (mx - mn)
    return arr
