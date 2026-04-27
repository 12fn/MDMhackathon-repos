"""Real-data ingestion stub for DISPATCH.

To plug in real 911 + CAD data, implement load_real_calls() to read from one of
the canonical defense / public-safety sources and emit the same shape as
data/generate.py produces in calls.json.

Sources (pick one or combine):

  1. NG911 ANI/ALI feed (from your installation 911 PSAP)
     - Format: NENA i3 SIP-INVITE + Location Object (PIDF-LO) +
       call recordings -> Whisper / wav2vec2 transcription
     - Required fields per call:
         id              str  unique call id (CAD CFS number is fine)
         received_at     ISO-8601 with TZ
         transcript      list[{speaker:str, t:float, text:str}]
                         (segmented by VAD; speaker can be "Dispatcher"/"Caller")
         address         str  human-readable street + structure name
         lat_lon         [float, float]  WGS84

  2. CAD export (Tyler Spillman / Hexagon CAD / Mark43 / Motorola Premier One)
     - Format: nightly NIEM-CAD XML or CSV
     - Map: incident_number->id, recv_time->received_at, prem_address->address,
            cfs_lat/cfs_lon->lat_lon
     - Pair with the audio feed above to get transcript[]

  3. USCG Rescue 21 voice / OpsCenter feeds (for joint installations)
     - Pair the comms log with the radio audio for transcription

  4. Marine Corps Computer-Aided Dispatch (MC-CAD), where deployed (limited)
     - Same shape as commercial CAD above; ReBAC-gated through Kamiwaza
       Tool Shed for ICS-209 / NIMS exports.

Then point the FastAPI backend at the loader via env:
    DISPATCH_REAL_DATA=1 python -m src.api

`load_real_units()` should produce the same shape as units.json (one row per
station-resourced unit) — typically pulled from the unit-status MDT feed.
"""
import os
import json
from pathlib import Path


def load_real_calls() -> list[dict]:
    src = os.getenv("DISPATCH_CALLS_SRC")
    if not src:
        raise NotImplementedError(
            "DISPATCH_CALLS_SRC not set. See module docstring for the required "
            "schema and the canonical source list (NG911 ANI/ALI, NIEM-CAD, "
            "USCG Rescue 21, MC-CAD)."
        )
    p = Path(src)
    if not p.exists():
        raise FileNotFoundError(f"DISPATCH_CALLS_SRC={src} does not exist")
    return json.loads(p.read_text())


def load_real_units() -> list[dict]:
    src = os.getenv("DISPATCH_UNITS_SRC")
    if not src:
        raise NotImplementedError(
            "DISPATCH_UNITS_SRC not set. Expects unit-status MDT feed "
            "(callsign, type, status, lat, lon, capabilities[])."
        )
    p = Path(src)
    if not p.exists():
        raise FileNotFoundError(f"DISPATCH_UNITS_SRC={src} does not exist")
    return json.loads(p.read_text())
