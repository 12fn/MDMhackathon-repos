"""Real-data ingestion stubs for DRONE-DOMINANCE.

Five real datasets feed this app — all five swap into the same shape
data/generate.py emits, so the rest of the pipeline is unchanged:

  1. Drone Dataset (UAV) — visual EO photos
     Source: Kaggle "drone-detection" (Mehdi Özel) and HIT-UAV's RGB pair
     URL:    https://www.kaggle.com/datasets/dasmehdixtr/drone-dataset-uav
     Drop into apps/42-drone-dominance/data/visual/<scenario_id>.png and
     point at it via REAL_VISUAL_DIR. One PNG per threat scenario id.

  2. HIT-UAV — High-altitude Infrared Thermal Dataset for UAV-based Detection
     Source: HIT-UAV authors (Sun et al., 2023)
     URL:    https://github.com/suojiashun/HIT-UAV-Infrared-Thermal-Dataset
     Drop *.png thermal frames into REAL_THERMAL_DIR plus matching
     <name>.bboxes.json files (YOLO format converted; see schema below).

  3. DroneRF-B Spectra — RF spectrogram tiles
     Source: IEEE DataPort
     URL:    https://ieee-dataport.org/  (search: "DroneRF-B Spectra")
     Drop pre-computed .png + .npy intensity tiles into REAL_RF_SPECTRA_DIR
     with stems matching scenario ids.

  4. Drone RC RF Identification — controller fingerprints
     Source: IEEE DataPort
     URL:    https://ieee-dataport.org/  (search: "DroneRC RF Signal")
     Provide a CSV at REAL_RC_CSV with the columns documented below.

  5. Xperience-10M — egocentric helmet-cam stills (a curated subset)
     Source: Embodied AI / multimodal world-model dataset
     URL:    https://github.com/THUDM/Xperience-10M  (or the published mirror)
     Drop a small set of helmet-cam JPEG stills into REAL_XPERIENCE_DIR.
     One per AAR scenario (4 by default).
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Iterator

import numpy as np
import pandas as pd
from PIL import Image


REQUIRED_RC_COLS = {
    "id", "manufacturer", "controller", "band_ghz", "hopping", "protocol",
}


def load_real_rf_spectra(dir_path: str | None = None) -> Iterator[dict]:
    """Yield {id, png_path, npy_path} for every spectrogram tile.

    Each tile must have either a .png alone (Pillow grayscale conversion will
    happen at runtime) or a paired .png + .npy with the same stem.
    """
    p = Path(dir_path or os.getenv("REAL_RF_SPECTRA_DIR") or "data/rf_spectra")
    if not p.exists():
        raise NotImplementedError(
            f"Real spectra dir not found: {p}\n"
            "Set REAL_RF_SPECTRA_DIR or drop DroneRF-B Spectra .png/.npy files there."
        )
    for png in sorted(p.glob("*.png")):
        npy = png.with_suffix(".npy")
        yield {
            "id": png.stem,
            "png_path": str(png),
            "npy_path": str(npy) if npy.exists() else None,
        }


def load_real_thermal(dir_path: str | None = None) -> Iterator[dict]:
    """Yield {id, png_path, bboxes} for every HIT-UAV thermal frame.

    bboxes is a list of dicts with keys cls/conf/bbox where bbox is
    [x0, y0, x1, y1] in image pixels.
    """
    p = Path(dir_path or os.getenv("REAL_THERMAL_DIR") or "data/thermal")
    if not p.exists():
        raise NotImplementedError(
            f"Real thermal dir not found: {p}\n"
            "Set REAL_THERMAL_DIR or drop HIT-UAV PNG frames + .bboxes.json files."
        )
    for png in sorted(p.glob("*.png")):
        bbox_path = png.with_suffix(".bboxes.json")
        bboxes: list[dict] = []
        if bbox_path.exists():
            try:
                bboxes = json.loads(bbox_path.read_text())
            except Exception:  # noqa: BLE001
                bboxes = []
        yield {
            "id": png.stem,
            "png_path": str(png),
            "bboxes": bboxes,
        }


def load_real_visual(dir_path: str | None = None) -> Iterator[dict]:
    """Yield {id, png_path} for every Drone-Dataset visual EO photo."""
    p = Path(dir_path or os.getenv("REAL_VISUAL_DIR") or "data/visual")
    if not p.exists():
        raise NotImplementedError(
            f"Real visual dir not found: {p}\n"
            "Set REAL_VISUAL_DIR or drop Drone Dataset (UAV) JPG/PNG files there."
        )
    for png in sorted(list(p.glob("*.png")) + list(p.glob("*.jpg"))):
        yield {"id": png.stem, "png_path": str(png)}


def load_real_rc(csv_path: str | None = None) -> pd.DataFrame:
    """Load DroneRC controller-fingerprint CSV (30+ rows expected)."""
    p = Path(csv_path or os.getenv("REAL_RC_CSV") or "data/dronerc.csv")
    if not p.exists():
        raise NotImplementedError(
            f"DroneRC CSV not found: {p}\n"
            "Set REAL_RC_CSV. Required columns: " + ", ".join(sorted(REQUIRED_RC_COLS))
        )
    df = pd.read_csv(p)
    missing = REQUIRED_RC_COLS - set(df.columns)
    if missing:
        raise ValueError(f"DroneRC CSV {p} missing columns: {sorted(missing)}")
    return df


def load_real_xperience(dir_path: str | None = None) -> Iterator[dict]:
    """Yield {id, png_path} for every Xperience-10M helmet-cam still."""
    p = Path(dir_path or os.getenv("REAL_XPERIENCE_DIR") or "data/xperience")
    if not p.exists():
        raise NotImplementedError(
            f"Real Xperience-10M dir not found: {p}\n"
            "Set REAL_XPERIENCE_DIR or drop curated helmet-cam stills there."
        )
    for png in sorted(list(p.glob("*.png")) + list(p.glob("*.jpg"))):
        yield {"id": png.stem, "png_path": str(png)}


def load_npy_intensity(npy_path: str) -> np.ndarray:
    """Load a spectrogram .npy and min-max normalize to [0, 1] float32."""
    arr = np.load(npy_path).astype(np.float32)
    mn, mx = float(arr.min()), float(arr.max())
    if mx > mn:
        arr = (arr - mn) / (mx - mn)
    return arr


def png_to_intensity(png_path: str) -> np.ndarray:
    """Fallback when only a PNG is available — convert to grayscale [0, 1]."""
    img = Image.open(png_path).convert("L")
    return np.asarray(img, dtype=np.float32) / 255.0
