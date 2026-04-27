"""Real-data ingestion stub for GHOST.

To plug in real data, implement load_real() to read from the
**IEEE Real-world Commercial WiFi and Bluetooth Dataset for RF Fingerprinting**
(IEEE DataPort) and emit the same shape as data/generate.py produces.

Required columns (after transform):
  - event_id     : str           (any unique id)
  - timestamp    : ISO-8601 UTC  (e.g. 2026-04-26T10:32:14+00:00)
  - hour         : int 0-23      (derived from timestamp)
  - lat          : float         (decimal degrees)
  - lon          : float         (decimal degrees)
  - signal_type  : "WiFi" | "BT"
  - mac          : str           ("AA:BB:CC:DD:EE:FF")
  - oui          : str           (first 3 octets, e.g. "3C:22:FB")
  - vendor       : str           (resolved from oui via vendor_oui.csv;
                                  use "Unknown" if not found)
  - rssi         : int           (negative dBm, typically -100..-30)
  - channel      : int           (Wi-Fi 1-165 / BLE 37-39)
  - pattern      : str           (optional; "" or your own labelling)

Then point src/app.py at it via env var:
    REAL_DATA_PATH=/path/to/ieee_rf_capture.csv streamlit run src/app.py ...

Notes on the IEEE source:
  - The IEEE set publishes per-device captures (often as JSON or per-pcap CSVs).
    You'll typically need to (a) extract MAC + RSSI + timestamps via
    `tshark -T fields -e wlan.sa -e radiotap.dbm_antsignal -e frame.time_epoch`
    for Wi-Fi and `btsnoop_hci`/`hcidump`-derived CSVs for BLE,
    (b) join GPS waypoints from the capture log to interpolate lat/lon,
    (c) lookup vendor against IEEE OUI list (we ship a 30-row sample at
    data/vendor_oui.csv; for production, swap in the full IEEE OUI list).
"""
from __future__ import annotations

import os
from pathlib import Path

import pandas as pd

REQUIRED_COLS = {
    "event_id", "timestamp", "hour", "lat", "lon",
    "signal_type", "mac", "oui", "vendor", "rssi", "channel", "pattern",
}


def load_real() -> pd.DataFrame:
    path = os.getenv("REAL_DATA_PATH")
    if not path:
        raise NotImplementedError(
            "REAL_DATA_PATH not set. See module docstring for the required "
            "schema and IEEE Wi-Fi/BT dataset extraction recipe."
        )
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"REAL_DATA_PATH does not exist: {p}")
    df = pd.read_csv(p)
    missing = REQUIRED_COLS - set(df.columns)
    if missing:
        raise ValueError(
            f"Real dataset {p} is missing required columns: {sorted(missing)}. "
            f"See module docstring for the canonical schema."
        )
    return df
