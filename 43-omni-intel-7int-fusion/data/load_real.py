"""Real-data ingestion stubs for OMNI-INTEL -- 7 ISR streams.

The OMNI fusion pipeline is source-agnostic: every input is normalized to the
common observation envelope before the cross-source correlator runs. To plug in
real data, implement the corresponding `load_*()` for each stream and ensure
the returned records match `data/generate.py`'s `_envelope()` output:

    {source_type, observation_id, dtg, lat, lon, raw_signature, confidence}

All swap paths are listed below. Set the env vars for each source you want to
plug in; sources without env vars stay on synthetic data, so partial-real
operation works.

-------------------------------------------------------------------------------
1. AIS  (vessel position pings)                       env: REAL_AIS_PATH
   Source:  AIS Data Aug-2024 (Marine Cadastre, NOAA / NMEA)
            https://marinecadastre.gov/ais/
   Native:  CSV {MMSI, BaseDateTime, LAT, LON, SOG, COG, VesselType, Status, Length}
   Map:     mmsi->raw.mmsi, BaseDateTime->dtg, LAT/LON->lat/lon, SOG->raw.speed_kn

2. ASAM Pirate Attacks                                env: REAL_ASAM_PATH
   Source:  NGA ASAM database (Anti-Shipping Activity Messages)
            https://msi.nga.mil/Piracy
   Native:  GeoJSON / shapefile of attack points + narrative text
   Map:     Reference -> raw.report_id, EventDate -> dtg, LAT/LON -> lat/lon,
            Description -> raw.narrative_excerpt

3. Military Object Detection (IMINT)                  env: REAL_MILOBJ_PATH
   Source:  Roboflow "Military Object Detection v3" or USGS EarthExplorer tiles
            https://universe.roboflow.com/.../military-objects
   Native:  COCO/YOLO annotations + tile metadata (UTM zone -> WGS84)
   Map:     image_id -> raw.tile_id, class -> raw.platform_class,
            tile-center -> lat/lon, score -> confidence

4. HIT-UAV Thermal                                    env: REAL_HITUAV_PATH
   Source:  HIT-UAV Infrared Thermal Dataset (Mendeley Data)
            https://data.mendeley.com/datasets/vt2j7b8k7y
   Native:  PNG IR frames + YOLO labels (person, car, bicycle, otherperson)
   Map:     frame stem -> raw.frame_id, class -> raw.blob_type,
            telemetry-derived ground-projection -> lat/lon

5. DroneRF Spectrogram                                env: REAL_DRONERF_PATH
   Source:  DroneRF Database (Mendeley)
            https://data.mendeley.com/datasets/f4c2b4n755
   Native:  CSV of I/Q samples + class label (background, bebop, parrot)
   Map:     window timestamp -> dtg, controller class -> raw.rf_class,
            collection antenna -> lat/lon

6. IEEE WiFi/BT RF Fingerprinting                     env: REAL_WIFIBT_PATH
   Source:  IEEE DataPort Wi-Fi/Bluetooth RF Fingerprinting
            https://ieee-dataport.org/...
   Native:  PCAP parsed to per-frame {timestamp, MAC, RSSI, channel}
   Map:     MAC OUI lookup -> raw.mac_oui, channel -> raw.band, ts -> dtg

7. NASA FIRMS Ukraine (or any region)                 env: REAL_FIRMS_PATH
   Source:  NASA FIRMS active-fire archive
            https://firms.modaps.eosdis.nasa.gov/country/
   Native:  CSV {latitude, longitude, brightness, scan, track, acq_date,
            acq_time, satellite, confidence, frp, daynight}
   Map:     direct -- already in our envelope shape after rename
            brightness -> raw.brightness_k, frp -> raw.frp_mw

-------------------------------------------------------------------------------
USAGE

    from data.load_real import load_all_real
    sources = load_all_real()  # dict[source_type] -> list[envelope dict]

    # then drop into the same fusion pipeline:
    from src.fusion import correlate_clusters
    clusters = correlate_clusters([o for v in sources.values() for o in v])

If an env var is unset, that source returns []. The fusion pipeline tolerates
missing sources (just produces fewer / lower-confidence clusters).
"""
from __future__ import annotations

import os
from typing import Callable

import pandas as pd


def _gap(env: str) -> str | None:
    p = os.getenv(env)
    return p if p and os.path.exists(p) else None


def load_real_ais() -> list[dict]:
    p = _gap("REAL_AIS_PATH")
    if not p:
        return []
    df = pd.read_csv(p)
    out = []
    for _, r in df.iterrows():
        out.append({
            "source_type": "ais",
            "observation_id": f"AIS-{r['MMSI']}-{r['BaseDateTime']}",
            "dtg": pd.to_datetime(r["BaseDateTime"]).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "lat": float(r["LAT"]), "lon": float(r["LON"]),
            "raw_signature": {
                "mmsi": int(r["MMSI"]),
                "vessel_type": str(r.get("VesselType", "unknown")),
                "speed_kn": float(r.get("SOG", 0)),
                "course_deg": float(r.get("COG", 0)),
            },
            "confidence": 0.85,
        })
    return out


def load_real_asam() -> list[dict]:
    p = _gap("REAL_ASAM_PATH")
    if not p:
        return []
    raise NotImplementedError(
        "ASAM swap not yet wired. Read the GeoJSON, project to WGS84, and emit "
        "the OMNI envelope with raw.incident_type, raw.narrative_excerpt."
    )


def load_real_milobj() -> list[dict]:
    if not _gap("REAL_MILOBJ_PATH"):
        return []
    raise NotImplementedError(
        "MilObj swap: read COCO/YOLO + tile metadata; emit OMNI envelope. See "
        "docstring at top of this file."
    )


def load_real_hituav() -> list[dict]:
    if not _gap("REAL_HITUAV_PATH"):
        return []
    raise NotImplementedError("HIT-UAV swap stub.")


def load_real_dronerf() -> list[dict]:
    if not _gap("REAL_DRONERF_PATH"):
        return []
    raise NotImplementedError("DroneRF swap stub.")


def load_real_wifibt() -> list[dict]:
    if not _gap("REAL_WIFIBT_PATH"):
        return []
    raise NotImplementedError("WiFi/BT swap stub.")


def load_real_firms() -> list[dict]:
    p = _gap("REAL_FIRMS_PATH")
    if not p:
        return []
    df = pd.read_csv(p)
    out = []
    for i, r in df.iterrows():
        out.append({
            "source_type": "firms",
            "observation_id": f"FIRMS-{i:06d}",
            "dtg": f"{r['acq_date']}T{int(r['acq_time']):04d}00Z".replace(" ", ""),
            "lat": float(r["latitude"]), "lon": float(r["longitude"]),
            "raw_signature": {
                "brightness_k": float(r["brightness"]),
                "frp_mw": float(r.get("frp", 0)),
                "satellite": str(r.get("satellite", "VIIRS")),
                "daynight": str(r.get("daynight", "D")),
                "confidence_native": str(r.get("confidence", "nominal")),
            },
            "confidence": 0.8,
        })
    return out


LOADERS: dict[str, Callable[[], list[dict]]] = {
    "ais":     load_real_ais,
    "asam":    load_real_asam,
    "milobj":  load_real_milobj,
    "hituav":  load_real_hituav,
    "dronerf": load_real_dronerf,
    "wifibt":  load_real_wifibt,
    "firms":   load_real_firms,
}


def load_all_real() -> dict[str, list[dict]]:
    """Best-effort load. Sources without env vars (or unimplemented) return []."""
    out: dict[str, list[dict]] = {}
    for k, fn in LOADERS.items():
        try:
            out[k] = fn()
        except NotImplementedError:
            out[k] = []
    return out
