"""MARLIN synthetic AIS generator.

Produces 8-10 vessel tracks in/around the Luzon Strait — the chokepoint
between Taiwan and the Philippines that dominates INDOPACOM contested logistics.

Plants 3 anomalies:
  1. AIS gap (dark period): vessel CARGO_DARK_01 stops broadcasting for ~3 hrs
  2. Loiter near denied area: FISHING_LOITER_01 circles tightly inside DENIED_AREA_BASHI
  3. Midnight rendezvous: SUSPECT_GRAY_01 + SUSPECT_GRAY_02 meet within 0.5 nm

Outputs:
  - tracks.json   : full per-vessel ping arrays
  - vessels.json  : vessel metadata (mmsi, name, type, flag)
  - denied_areas.json : polygon zones (denied / restricted)
  - anomalies.json    : pre-computed anomaly records (the backend can also re-detect)
  - timeline.json     : 100 evenly-spaced timestamps for the time slider

──────────────────────────────────────────────────────────────────────────────
SWAPPING IN REAL AIS DATA
──────────────────────────────────────────────────────────────────────────────
This is a "Bucket A" (drop-in CSV) swap per the repo-level DATA_INGESTION.md
(see ../../DATA_INGESTION.md → "MARLIN").

Suggested real source: NOAA / MarineCadastre.gov public AIS archive.
Required canonical columns: MMSI, lat, lon, timestamp (ISO 8601 UTC),
sog (knots), cog (degrees), vessel type.

To swap, replace the synth body of this file with a thin loader that:
  1. Reads your AIS CSV / Parquet (e.g. via pandas).
  2. Groups pings by MMSI.
  3. Emits the same five JSON files into this folder, matching shape:
       tracks.json   : [{mmsi, name, type, flag, color,
                         pings: [{t, lat, lon, course, speed_kn, mmsi}, ...]}, ...]
       vessels.json  : [{mmsi, name, type, flag, color, ping_count}, ...]
       denied_areas.json : [{id, name, kind, polygon: [[lat,lon], ...], rationale}, ...]
       anomalies.json    : [{id, kind, mmsi, vessel, severity, summary,
                             t_start, t_end, lat, lon, ...}, ...]
       timeline.json     : ["2024-08-14T18:00:00+00:00", ...]  # N evenly-spaced ISO ts

The backend (backend/app.py) just reads these JSON files at startup, so once
the loader emits them, restart `uvicorn` and the same UI/SSE pipeline runs
against your real feed unchanged.
"""
from __future__ import annotations

import json
import math
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Import shared synth utility
THIS = Path(__file__).resolve()
ROOT = THIS.parent.parent.parent.parent  # repo root
sys.path.insert(0, str(ROOT))

from shared.synth import seeded, jitter_track  # noqa: E402

OUT = THIS.parent
RNG = seeded(1776)
T0 = datetime(2024, 8, 14, 18, 0, 0, tzinfo=timezone.utc)  # Aug 14 2024 18:00Z

# --- Geographic playground: Luzon Strait / Bashi Channel -----------------
# Luzon Strait: ~20.5N 121E. Batanes ~20.4N 121.97E. Yonaguni ~24.4N 123E.
# Bashi Channel between Y'ami Is. (Philippines) and Orchid Is. (Taiwan): ~21N 121.5E

DENIED_AREAS = [
    {
        "id": "BASHI_DENIED",
        "name": "Bashi Channel Restricted Op Area",
        "kind": "denied",
        # Roughly a box across the channel
        "polygon": [
            [21.20, 121.20],
            [21.20, 121.85],
            [20.55, 121.85],
            [20.55, 121.20],
            [21.20, 121.20],
        ],
        "rationale": "PRC PLAN exercise area declared 12 Aug 2024",
    },
    {
        "id": "MIYAKO_RESTRICTED",
        "name": "Miyako Strait Caution Zone",
        "kind": "caution",
        "polygon": [
            [25.10, 124.20],
            [25.10, 125.30],
            [24.40, 125.30],
            [24.40, 124.20],
            [25.10, 124.20],
        ],
        "rationale": "Adjacent to JS Yonaguni radar; high foreign vessel transit",
    },
]

# --- Vessel roster --------------------------------------------------------
VESSELS = [
    # name, mmsi, type, flag, start_lat, start_lon, course_deg, speed_kn, color
    ("MAERSK SENTOSA",      "232017854", "Cargo",        "GBR", 20.30, 120.40, 70,  16.5, "#3aa0ff"),
    ("OOCL HONG KONG",      "477123456", "Cargo",        "HKG", 22.10, 119.80, 95,  17.2, "#3aa0ff"),
    ("EVER GIVEN",          "353136000", "Cargo",        "PAN", 19.80, 122.50, 280, 14.0, "#3aa0ff"),
    ("HAI LU 88",           "412888001", "Fishing",      "CHN", 20.95, 121.55, 40,   3.2, "#f5b942"),
    ("HAI LU 92",           "412888092", "Fishing",      "CHN", 21.05, 121.60, 220,  3.0, "#f5b942"),
    ("PHL FV BANGUS",       "548112233", "Fishing",      "PHL", 20.20, 121.90, 110,  4.5, "#f5b942"),
    ("DARK STAR",           "636019887", "Tanker",       "LBR", 22.40, 121.00, 180, 11.8, "#9d6bff"),
    ("YANTAI SPIRIT",       "413555012", "Tanker",       "CHN", 21.80, 122.40, 250, 12.5, "#9d6bff"),
    ("SHEN ZHEN HAO",       "413700777", "Research",     "CHN", 20.85, 121.40, 350,  6.0, "#ff5577"),
    ("USNS CHARLES DREW",   "338910001", "Mil Sealift",  "USA", 19.50, 121.10, 30,  18.0, "#00FFA7"),
]

# --- Build base tracks ----------------------------------------------------
# 100 pings @ 5-min cadence = ~8 hr observation window
PING_COUNT = 100
DT_MIN = 5.0


def build_track(name, mmsi, vtype, flag, lat0, lon0, course, speed, color):
    pings = jitter_track(
        lat0, lon0, PING_COUNT,
        rng=RNG, speed_kn=speed, course_deg=course,
        dt_minutes=DT_MIN,
        course_jitter_deg=6.0 if vtype != "Fishing" else 14.0,
        speed_jitter=1.0 if vtype != "Fishing" else 0.6,
    )
    # Re-time pings on a deterministic timeline starting at T0
    for i, p in enumerate(pings):
        p["t"] = (T0 + timedelta(minutes=DT_MIN * i)).isoformat()
        p["mmsi"] = mmsi
    return {
        "mmsi": mmsi,
        "name": name,
        "type": vtype,
        "flag": flag,
        "color": color,
        "pings": pings,
    }


tracks = [build_track(*v) for v in VESSELS]
by_name = {t["name"]: t for t in tracks}
anomalies: list[dict] = []


# --- Anomaly 1: AIS GAP on EVER GIVEN --------------------------------------
ever = by_name["EVER GIVEN"]
gap_start, gap_end = 30, 65  # drop pings 30..65 (~3 hours dark)
ever["pings"] = [p for i, p in enumerate(ever["pings"]) if not (gap_start <= i < gap_end)]
anomalies.append({
    "id": "ANOM_GAP_EVER_GIVEN",
    "kind": "ais_gap",
    "mmsi": ever["mmsi"],
    "vessel": ever["name"],
    "severity": "high",
    "summary": f"AIS broadcast gap of {(gap_end-gap_start)*DT_MIN:.0f} min while transiting Bashi Channel approach.",
    "t_start": (T0 + timedelta(minutes=DT_MIN * gap_start)).isoformat(),
    "t_end": (T0 + timedelta(minutes=DT_MIN * gap_end)).isoformat(),
    "lat": ever["pings"][gap_start - 1]["lat"] if gap_start > 0 else ever["pings"][0]["lat"],
    "lon": ever["pings"][gap_start - 1]["lon"] if gap_start > 0 else ever["pings"][0]["lon"],
})

# --- Anomaly 2: LOITER on HAI LU 88 inside Bashi denied area ---------------
hai88 = by_name["HAI LU 88"]
# Replace pings 20..70 with a tight circle inside Bashi
loiter_center = (20.85, 121.55)
loiter_radius_nm = 0.6
loiter_pings = []
for i in range(20, 70):
    angle = (i - 20) * (2 * math.pi / 25)  # ~2 full circles over the loiter window
    d_lat = (loiter_radius_nm / 60.0) * math.cos(angle)
    d_lon = (loiter_radius_nm / 60.0) * math.sin(angle) / math.cos(math.radians(loiter_center[0]))
    loiter_pings.append({
        "t": (T0 + timedelta(minutes=DT_MIN * i)).isoformat(),
        "lat": round(loiter_center[0] + d_lat, 5),
        "lon": round(loiter_center[1] + d_lon, 5),
        "course": round((angle * 180 / math.pi) % 360, 1),
        "speed_kn": round(2.0 + RNG.uniform(-0.3, 0.3), 2),
        "mmsi": hai88["mmsi"],
    })
hai88["pings"] = hai88["pings"][:20] + loiter_pings + hai88["pings"][70:]
anomalies.append({
    "id": "ANOM_LOITER_HAILU88",
    "kind": "loiter_denied",
    "mmsi": hai88["mmsi"],
    "vessel": hai88["name"],
    "severity": "high",
    "summary": "Sustained tight-radius loiter inside Bashi Channel restricted op area.",
    "t_start": loiter_pings[0]["t"],
    "t_end": loiter_pings[-1]["t"],
    "lat": loiter_center[0],
    "lon": loiter_center[1],
    "denied_area": "BASHI_DENIED",
})

# --- Anomaly 3: RENDEZVOUS — DARK STAR meets YANTAI SPIRIT -----------------
dark = by_name["DARK STAR"]
yan = by_name["YANTAI SPIRIT"]
# Force convergence at index 55..60 at midnight UTC (~22:35Z + 5*55min ≈ 03:35Z next day; close enough)
rdv_idx = 55
meet_lat, meet_lon = 21.95, 121.70
for i in range(rdv_idx, rdv_idx + 6):
    if i < len(dark["pings"]):
        dark["pings"][i]["lat"] = round(meet_lat + (i - rdv_idx) * 0.001, 5)
        dark["pings"][i]["lon"] = round(meet_lon + (i - rdv_idx) * 0.001, 5)
        dark["pings"][i]["speed_kn"] = round(1.5 + RNG.uniform(-0.3, 0.3), 2)
    if i < len(yan["pings"]):
        yan["pings"][i]["lat"] = round(meet_lat - (i - rdv_idx) * 0.001, 5)
        yan["pings"][i]["lon"] = round(meet_lon + (i - rdv_idx) * 0.0008, 5)
        yan["pings"][i]["speed_kn"] = round(1.7 + RNG.uniform(-0.3, 0.3), 2)
anomalies.append({
    "id": "ANOM_RDV_DARKSTAR_YANTAI",
    "kind": "rendezvous",
    "mmsi": dark["mmsi"],
    "vessel": f"{dark['name']} <-> {yan['name']}",
    "partners": [dark["mmsi"], yan["mmsi"]],
    "severity": "critical",
    "summary": "Two flagged tankers converged to <0.5 nm in open ocean for ~30 min — pattern consistent with covert STS transfer.",
    "t_start": dark["pings"][rdv_idx]["t"],
    "t_end": dark["pings"][min(rdv_idx + 5, len(dark["pings"]) - 1)]["t"],
    "lat": meet_lat,
    "lon": meet_lon,
})

# --- Build timeline (100 evenly spaced steps over the data window) ---------
all_ts = sorted({p["t"] for tr in tracks for p in tr["pings"]})
# Ensure exactly 100 evenly-spaced labels (use the original 100-step base grid)
timeline = [(T0 + timedelta(minutes=DT_MIN * i)).isoformat() for i in range(PING_COUNT)]


# --- Vessel-only metadata for sidebar -------------------------------------
vessels_meta = [{
    "mmsi": t["mmsi"],
    "name": t["name"],
    "type": t["type"],
    "flag": t["flag"],
    "color": t["color"],
    "ping_count": len(t["pings"]),
} for t in tracks]


# --- Write outputs --------------------------------------------------------
def w(name, obj):
    p = OUT / name
    p.write_text(json.dumps(obj, indent=2))
    print(f"  wrote {p.name:24s} {p.stat().st_size/1024:6.1f} KB")


print(f"MARLIN synth generator → {OUT}")
w("tracks.json", tracks)
w("vessels.json", vessels_meta)
w("denied_areas.json", DENIED_AREAS)
w("anomalies.json", anomalies)
w("timeline.json", timeline)
print(f"  vessels: {len(tracks)}   anomalies: {len(anomalies)}   timeline_steps: {len(timeline)}")
