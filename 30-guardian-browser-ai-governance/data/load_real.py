"""Real-data ingestion stub for GUARDIAN.

To plug in real data, implement load_real() to read a JSONL of
browser-intercept events from a real source (Express middleware, ZTNA broker,
SASE access log, browser-isolation telemetry) and emit the same shape as
data/generate.py produces. Required fields per row:

  - event_id: unique string
  - timestamp_utc: ISO8601 UTC
  - session_id: opaque session identifier
  - client_ip: source IP (string)
  - internal_app: short name of the protected internal app
  - endpoint: URL path
  - method: GET | POST | PUT | DELETE
  - data_class: CUI | PII | PHI | AUTH | OTHER
  - payload_bytes: int
  - signals: {
        user_agent: str,
        ai_headers_present: list[str],   # e.g. ["X-Sec-Comet"]
        dom_markers: list[str],          # CSS-selector-style markers
        navigator_webdriver: bool,
        mouse_movement_entropy: float,   # 0..1
        keystroke_inter_arrival_ms_median: int,
        screenshot_api_calls_30s: int,
        tls_ja4: str,
    }

Then point the app at it via env: REAL_DATA_PATH=/path/to/intercepts.jsonl

Likely real sources:
  - Custom Express middleware in front of an internal app
  - Cloudflare Worker / Akamai EdgeWorker emitting structured logs
  - ZTNA broker (Zscaler ZIA, Netskope, Cloudflare Access, Island Browser)
  - Browser fingerprinting service (FingerprintJS Pro)
"""
from __future__ import annotations

import json
import os
from pathlib import Path


def load_real() -> list[dict]:
    path = os.getenv("REAL_DATA_PATH")
    if not path:
        raise NotImplementedError(
            "REAL_DATA_PATH not set. See docstring for required schema."
        )
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(p)
    out: list[dict] = []
    with p.open() as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            out.append(json.loads(line))
    return out
