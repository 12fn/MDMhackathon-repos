"""OMNI-INTEL synthetic dataset generator -- 7 ISR sources fused into one schema.

Source-by-source synthesis, with planted multi-source fusion truth labels so the
cross-source correlator has signal to find. Real-data swap paths documented in
load_real.py.

Schema: every observation, regardless of native source, is normalized to the
common envelope:

    {
      source_type:    one of {ais, asam, milobj, hituav, dronerf, wifibt, firms}
      observation_id: stable string id
      dtg:            ISO-8601 UTC ZULU
      lat / lon:      WGS84
      raw_signature: dict (source-native attributes -- vessel mmsi, fire frp,
                      RF MAC OUI, IR blob area, etc.)
      confidence:    0..1 source-native confidence weighted by collection priority
    }

INTs touched: SIGINT (RF/WiFi/Drone), MASINT (thermal IR, FIRMS radiative power),
IMINT (mil-object detection on satellite tiles), GEOINT (AIS tracks, FIRMS
geolocation), OSINT (ASAM pirate-attack reporting), HUMINT (none -- placeholder
for live ingest).
"""
from __future__ import annotations

import hashlib
import json
import math
import random
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
SEED = 1776

# -----------------------------------------------------------------------------
# Operational area (Sulu Sea / Western Philippine Sea -- contested logistics
# AOR matching the Marine Stand-In-Forces concept). All synthetic.
# -----------------------------------------------------------------------------
AOR_BBOX = (4.0, 18.0, 116.0, 128.0)  # (lat_min, lat_max, lon_min, lon_max)

# Fusion truth anchors: 5 hand-planted multi-source events the correlator
# should find. Each anchor records (id, lat, lon, dtg_iso, sources_present,
# narrative). The correlator must independently rediscover them.
FUSION_ANCHORS = [
    {
        "fusion_id": "F-001",
        "name": "Covert vessel - Sulu Sea",
        "lat": 6.450, "lon": 121.080,
        "dtg": "2026-04-26T14:05:00Z",
        "sources": ["ais", "hituav", "dronerf", "asam"],
        "narrative": (
            "AIS gap on a Panamanian-flagged tanker overlapped with a thermal-IR "
            "blob 12 km off Jolo, drone-control RF spike on 2.4 GHz, and an ASAM "
            "boarding-attempt advisory from the same coordinates 90 min later."
        ),
    },
    {
        "fusion_id": "F-002",
        "name": "Suspected covert UAS launch - Mindoro",
        "lat": 13.420, "lon": 120.890,
        "dtg": "2026-04-26T03:18:00Z",
        "sources": ["hituav", "dronerf", "milobj"],
        "narrative": (
            "HIT-UAV thermal frame caught a launch-rail signature on a coastal "
            "fishing platform; DroneRF spectrogram tagged DJI OcuSync at -68 dBm; "
            "IMINT tile classified small-boat-with-mast as 'unidentified UAS LRC'."
        ),
    },
    {
        "fusion_id": "F-003",
        "name": "Cross-INT industrial fire - Subic",
        "lat": 14.797, "lon": 120.272,
        "dtg": "2026-04-26T08:42:00Z",
        "sources": ["firms", "milobj", "wifibt"],
        "narrative": (
            "FIRMS pixel cluster (FRP 78 MW) at a fuel-storage farm; IMINT shows "
            "POL tank thermal blooming; WiFi/BT density abruptly cratered at the "
            "facility (worker evacuation signature)."
        ),
    },
    {
        "fusion_id": "F-004",
        "name": "Pirate skiff swarm - Sibutu Passage",
        "lat": 4.820, "lon": 119.500,
        "dtg": "2026-04-26T22:55:00Z",
        "sources": ["asam", "ais", "dronerf"],
        "narrative": (
            "ASAM advisory: 4 skiffs trailing a bulk carrier through Sibutu; "
            "AIS shows the carrier executing evasive S-turns; DroneRF picked up "
            "non-DJI 433 MHz handheld telemetry consistent with skiff coordination."
        ),
    },
    {
        "fusion_id": "F-005",
        "name": "Beach reconnaissance signature - Palawan",
        "lat": 10.180, "lon": 119.060,
        "dtg": "2026-04-26T19:34:00Z",
        "sources": ["wifibt", "hituav", "milobj"],
        "narrative": (
            "Burst of Espressif (ESP32) WiFi MACs on an otherwise dark beach; "
            "HIT-UAV captured 3 warm bodies prone in vegetation; IMINT tile "
            "found 'small inflatable craft' partially camouflaged 40 m inland."
        ),
    },
]

# -----------------------------------------------------------------------------
# Per-source synthesizers -- each emits native records + fusion-anchored hits.
# -----------------------------------------------------------------------------

def _envelope(source_type: str, obs_id: str, dtg: str, lat: float, lon: float,
              raw: dict, confidence: float) -> dict:
    return {
        "source_type": source_type,
        "observation_id": obs_id,
        "dtg": dtg,
        "lat": round(float(lat), 5),
        "lon": round(float(lon), 5),
        "raw_signature": raw,
        "confidence": round(float(confidence), 3),
    }


def _jitter_dtg(rng: random.Random, base_iso: str, max_minutes: int) -> str:
    base = datetime.fromisoformat(base_iso.rstrip("Z"))
    drift = rng.randint(-max_minutes, max_minutes)
    return (base + timedelta(minutes=drift)).strftime("%Y-%m-%dT%H:%M:%SZ")


def _jitter_geo(rng: random.Random, lat: float, lon: float, max_km: float) -> tuple[float, float]:
    # ~111 km / deg lat; lon scaled by cos(lat)
    deg_lat = max_km / 111.0
    deg_lon = max_km / (111.0 * max(0.2, math.cos(math.radians(lat))))
    return lat + rng.uniform(-deg_lat, deg_lat), lon + rng.uniform(-deg_lon, deg_lon)


def _random_aor_point(rng: random.Random) -> tuple[float, float]:
    return (rng.uniform(AOR_BBOX[0], AOR_BBOX[1]),
            rng.uniform(AOR_BBOX[2], AOR_BBOX[3]))


def _random_dtg_24h(rng: random.Random) -> str:
    base = datetime(2026, 4, 26, 0, 0, 0)
    return (base + timedelta(seconds=rng.randint(0, 86399))).strftime("%Y-%m-%dT%H:%M:%SZ")


# -----------------------------------------------------------------------------
# AIS  (1,000 vessel pings, MARLIN shape)
# -----------------------------------------------------------------------------
def gen_ais(rng: random.Random) -> list[dict]:
    out: list[dict] = []
    flags = ["PHL", "PAN", "LBR", "MHL", "SGP", "VCT", "CYM", "CHN", "USA"]
    types = ["cargo", "tanker", "fishing", "passenger", "tug"]

    # Ambient pings
    for i in range(940):
        lat, lon = _random_aor_point(rng)
        mmsi = 200_000_000 + rng.randint(0, 99_999_999)
        is_gap = rng.random() < 0.08
        out.append(_envelope(
            "ais",
            obs_id=f"AIS-{i:05d}",
            dtg=_random_dtg_24h(rng),
            lat=lat, lon=lon,
            raw={
                "mmsi": mmsi,
                "vessel_type": rng.choice(types),
                "flag": rng.choice(flags),
                "speed_kn": round(abs(rng.gauss(11, 5)), 1),
                "course_deg": rng.randint(0, 359),
                "ais_gap_min": rng.randint(45, 240) if is_gap else 0,
                "anomaly": "gap" if is_gap else None,
            },
            confidence=0.82 if not is_gap else 0.55,
        ))

    # Fusion hits -- vessels at anchor coords with AIS gap or evasive pattern
    for anchor in FUSION_ANCHORS:
        if "ais" not in anchor["sources"]:
            continue
        lat, lon = _jitter_geo(rng, anchor["lat"], anchor["lon"], 1.5)
        gap = anchor["fusion_id"] in ("F-001", "F-004")
        out.append(_envelope(
            "ais",
            obs_id=f"AIS-FUSION-{anchor['fusion_id']}",
            dtg=_jitter_dtg(rng, anchor["dtg"], 12),
            lat=lat, lon=lon,
            raw={
                "mmsi": 357_000_000 + rng.randint(0, 9999),
                "vessel_type": rng.choice(["tanker", "cargo", "fishing"]),
                "flag": "PAN" if gap else "PHL",
                "speed_kn": 0.4 if gap else round(abs(rng.gauss(7, 2)), 1),
                "course_deg": rng.randint(0, 359),
                "ais_gap_min": 95 if gap else 0,
                "anomaly": "gap" if gap else "evasive_s_turn",
                "fusion_anchor": anchor["fusion_id"],
            },
            confidence=0.65,
        ))
    return out


# -----------------------------------------------------------------------------
# ASAM Pirate Attacks  (500 records, CORSAIR shape)
# -----------------------------------------------------------------------------
def gen_asam(rng: random.Random) -> list[dict]:
    out: list[dict] = []
    types = ["boarding", "approach", "robbery", "kidnap_attempt", "missile_threat"]

    for i in range(495):
        lat, lon = _random_aor_point(rng)
        out.append(_envelope(
            "asam",
            obs_id=f"ASAM-{i:04d}",
            dtg=_random_dtg_24h(rng),
            lat=lat, lon=lon,
            raw={
                "incident_type": rng.choice(types),
                "victim_vessel_type": rng.choice(["bulk_carrier", "tanker", "yacht", "fishing"]),
                "weapons": rng.choice(["small_arms", "rpg", "knives", "none_seen"]),
                "outcome": rng.choice(["repelled", "boarded", "evaded", "robbed"]),
                "narrative_excerpt": "Skiff(s) approached at high speed; bridge sounded alarm.",
                "reporting_agency": rng.choice(["NGA-ASAM", "IMB-PRC", "MARLO"]),
            },
            confidence=0.78,
        ))

    for anchor in FUSION_ANCHORS:
        if "asam" not in anchor["sources"]:
            continue
        lat, lon = _jitter_geo(rng, anchor["lat"], anchor["lon"], 5.0)
        out.append(_envelope(
            "asam",
            obs_id=f"ASAM-FUSION-{anchor['fusion_id']}",
            dtg=_jitter_dtg(rng, anchor["dtg"], 90),
            lat=lat, lon=lon,
            raw={
                "incident_type": "boarding" if anchor["fusion_id"] == "F-001" else "approach",
                "victim_vessel_type": "tanker" if anchor["fusion_id"] == "F-001" else "bulk_carrier",
                "weapons": "small_arms",
                "outcome": "boarded" if anchor["fusion_id"] == "F-001" else "evaded",
                "narrative_excerpt": "Multiple skiffs observed shadowing; advisory issued.",
                "reporting_agency": "NGA-ASAM",
                "fusion_anchor": anchor["fusion_id"],
            },
            confidence=0.85,
        ))
    return out


# -----------------------------------------------------------------------------
# Military Object Detection  (10 sample tile detections + 30-platform ref lib,
# borrowed from SENTINEL shape)
# -----------------------------------------------------------------------------
PLATFORM_LIB = [
    "T-90", "T-72B3", "BMP-3", "BMP-2", "BTR-82A", "BTR-80",
    "M1A2", "Leopard-2A6", "Challenger-2", "Type-99A", "Type-15",
    "Su-30MKK", "Su-34", "J-11", "J-16", "J-20", "Y-20",
    "Type-052D", "Type-055", "Type-056", "Type-022_FAC",
    "Pantsir-S1", "Tor-M2", "S-400 launcher", "HQ-9", "DF-26 TEL",
    "Mi-24 Hind", "Z-10 Zhou", "Z-20", "AS532 Cougar",
]

def gen_milobj(rng: random.Random) -> list[dict]:
    out: list[dict] = []
    # 10 tile detections at random AOR points
    for i in range(8):
        lat, lon = _random_aor_point(rng)
        plat = rng.choice(PLATFORM_LIB)
        out.append(_envelope(
            "milobj",
            obs_id=f"MILOBJ-{i:03d}",
            dtg=_random_dtg_24h(rng),
            lat=lat, lon=lon,
            raw={
                "tile_id": f"WV3-{rng.randint(10000,99999)}",
                "platform_class": plat,
                "platform_int": "IMINT",
                "bbox_pixels": [rng.randint(40,200), rng.randint(40,200),
                                rng.randint(220,400), rng.randint(220,400)],
                "detector_score": round(rng.uniform(0.62, 0.93), 2),
                "ref_library_size": len(PLATFORM_LIB),
            },
            confidence=round(rng.uniform(0.62, 0.93), 2),
        ))

    for anchor in FUSION_ANCHORS:
        if "milobj" not in anchor["sources"]:
            continue
        lat, lon = _jitter_geo(rng, anchor["lat"], anchor["lon"], 0.8)
        plat_map = {
            "F-002": "Type-022_FAC",
            "F-003": "POL_storage_tank",
            "F-005": "small_inflatable_craft",
        }
        plat = plat_map.get(anchor["fusion_id"], "unknown_vehicle")
        out.append(_envelope(
            "milobj",
            obs_id=f"MILOBJ-FUSION-{anchor['fusion_id']}",
            dtg=_jitter_dtg(rng, anchor["dtg"], 25),
            lat=lat, lon=lon,
            raw={
                "tile_id": f"WV3-{rng.randint(10000,99999)}",
                "platform_class": plat,
                "platform_int": "IMINT",
                "bbox_pixels": [120, 130, 240, 260],
                "detector_score": 0.88,
                "ref_library_size": len(PLATFORM_LIB),
                "fusion_anchor": anchor["fusion_id"],
            },
            confidence=0.88,
        ))
    return out


# -----------------------------------------------------------------------------
# HIT-UAV Thermal  (30 thermal frames, RAPTOR shape)
# -----------------------------------------------------------------------------
def gen_hituav(rng: random.Random) -> list[dict]:
    out: list[dict] = []
    blob_types = ["person_warm", "vehicle_warm", "vessel_wake", "engine_block",
                  "ir_blob_unidentified", "fire_signature"]
    for i in range(27):
        lat, lon = _random_aor_point(rng)
        out.append(_envelope(
            "hituav",
            obs_id=f"HITUAV-{i:03d}",
            dtg=_random_dtg_24h(rng),
            lat=lat, lon=lon,
            raw={
                "frame_id": f"IR-{rng.randint(1000,9999)}",
                "blob_type": rng.choice(blob_types),
                "blob_area_px": rng.randint(40, 1800),
                "delta_T_celsius": round(rng.uniform(2.5, 18.0), 1),
                "platform": "HIT-UAV-Mavic3T",
                "altitude_m": rng.choice([60, 90, 120, 180]),
                "platform_int": "MASINT",
            },
            confidence=round(rng.uniform(0.7, 0.95), 2),
        ))

    for anchor in FUSION_ANCHORS:
        if "hituav" not in anchor["sources"]:
            continue
        lat, lon = _jitter_geo(rng, anchor["lat"], anchor["lon"], 0.4)
        blob_map = {
            "F-001": "vessel_wake",
            "F-002": "engine_block",
            "F-005": "person_warm",
        }
        out.append(_envelope(
            "hituav",
            obs_id=f"HITUAV-FUSION-{anchor['fusion_id']}",
            dtg=_jitter_dtg(rng, anchor["dtg"], 10),
            lat=lat, lon=lon,
            raw={
                "frame_id": f"IR-{rng.randint(1000,9999)}",
                "blob_type": blob_map.get(anchor["fusion_id"], "ir_blob_unidentified"),
                "blob_area_px": 720,
                "delta_T_celsius": 14.6,
                "platform": "HIT-UAV-Mavic3T",
                "altitude_m": 120,
                "platform_int": "MASINT",
                "fusion_anchor": anchor["fusion_id"],
            },
            confidence=0.92,
        ))
    return out


# -----------------------------------------------------------------------------
# Drone RF Spectrogram  (6 spectrograms, CUAS-DETECT shape)
# -----------------------------------------------------------------------------
def gen_dronerf(rng: random.Random) -> list[dict]:
    out: list[dict] = []
    classes = ["DJI_OcuSync_2.4", "DJI_OcuSync_5.8", "Lightbridge_2.4",
               "Autel_Skylink_5.8", "433MHz_handheld_telemetry", "FPV_5.8_analog"]
    for i in range(3):
        lat, lon = _random_aor_point(rng)
        out.append(_envelope(
            "dronerf",
            obs_id=f"DRF-{i:03d}",
            dtg=_random_dtg_24h(rng),
            lat=lat, lon=lon,
            raw={
                "spectrogram_id": f"SPEC-{rng.randint(100,999)}",
                "rf_class": rng.choice(classes),
                "center_freq_ghz": rng.choice([2.4, 5.8, 0.433]),
                "rssi_dbm": rng.randint(-95, -55),
                "burst_duration_ms": rng.randint(20, 240),
                "platform_int": "SIGINT",
            },
            confidence=round(rng.uniform(0.65, 0.92), 2),
        ))

    for anchor in FUSION_ANCHORS:
        if "dronerf" not in anchor["sources"]:
            continue
        lat, lon = _jitter_geo(rng, anchor["lat"], anchor["lon"], 0.6)
        cls_map = {
            "F-001": "Lightbridge_2.4",
            "F-002": "DJI_OcuSync_2.4",
            "F-004": "433MHz_handheld_telemetry",
        }
        out.append(_envelope(
            "dronerf",
            obs_id=f"DRF-FUSION-{anchor['fusion_id']}",
            dtg=_jitter_dtg(rng, anchor["dtg"], 8),
            lat=lat, lon=lon,
            raw={
                "spectrogram_id": f"SPEC-{rng.randint(100,999)}",
                "rf_class": cls_map.get(anchor["fusion_id"], "DJI_OcuSync_2.4"),
                "center_freq_ghz": 2.4 if "2.4" in cls_map.get(anchor["fusion_id"], "2.4") else 0.433,
                "rssi_dbm": -68,
                "burst_duration_ms": 145,
                "platform_int": "SIGINT",
                "fusion_anchor": anchor["fusion_id"],
            },
            confidence=0.91,
        ))
    return out


# -----------------------------------------------------------------------------
# WiFi / BT  (5,000 events, GHOST shape)
# -----------------------------------------------------------------------------
def gen_wifibt(rng: random.Random) -> list[dict]:
    out: list[dict] = []
    ouis = ["Apple", "Samsung", "Huawei", "Xiaomi", "Espressif", "TP-Link",
            "Estimote", "Locally-administered", "Unknown"]
    bands = ["2.4GHz_WiFi", "5GHz_WiFi", "BLE_2.4"]

    for i in range(4995):
        lat, lon = _random_aor_point(rng)
        out.append(_envelope(
            "wifibt",
            obs_id=f"RF-{i:05d}",
            dtg=_random_dtg_24h(rng),
            lat=lat, lon=lon,
            raw={
                "mac_oui": rng.choice(ouis),
                "band": rng.choice(bands),
                "rssi_dbm": rng.randint(-95, -45),
                "frame_type": rng.choice(["probe_req", "beacon", "ble_adv"]),
                "platform_int": "SIGINT",
            },
            confidence=round(rng.uniform(0.4, 0.85), 2),
        ))

    for anchor in FUSION_ANCHORS:
        if "wifibt" not in anchor["sources"]:
            continue
        # plant a small burst
        for k in range(5):
            lat, lon = _jitter_geo(rng, anchor["lat"], anchor["lon"], 0.05)
            out.append(_envelope(
                "wifibt",
                obs_id=f"RF-FUSION-{anchor['fusion_id']}-{k}",
                dtg=_jitter_dtg(rng, anchor["dtg"], 4),
                lat=lat, lon=lon,
                raw={
                    "mac_oui": "Espressif" if anchor["fusion_id"] == "F-005" else "Locally-administered",
                    "band": "2.4GHz_WiFi",
                    "rssi_dbm": -78,
                    "frame_type": "probe_req",
                    "platform_int": "SIGINT",
                    "fusion_anchor": anchor["fusion_id"],
                },
                confidence=0.7,
            ))
    return out


# -----------------------------------------------------------------------------
# FIRMS Ukraine -- repurposed as "FIRMS WestPac"  (5,000 fire pixels, EMBER shape)
# -----------------------------------------------------------------------------
def gen_firms(rng: random.Random) -> list[dict]:
    out: list[dict] = []
    for i in range(4995):
        lat, lon = _random_aor_point(rng)
        out.append(_envelope(
            "firms",
            obs_id=f"FIRMS-{i:05d}",
            dtg=_random_dtg_24h(rng),
            lat=lat, lon=lon,
            raw={
                "brightness_k": round(rng.gauss(330, 25), 1),
                "frp_mw": round(abs(rng.gauss(15, 12)), 2),
                "satellite": rng.choice(["VIIRS-NOAA20", "VIIRS-NPP", "MODIS-Aqua"]),
                "daynight": rng.choice(["D", "N"]),
                "confidence_native": rng.choice(["low", "nominal", "high"]),
                "platform_int": "GEOINT",
            },
            confidence=round(rng.uniform(0.55, 0.9), 2),
        ))

    for anchor in FUSION_ANCHORS:
        if "firms" not in anchor["sources"]:
            continue
        # tight cluster of 6 hot pixels
        for k in range(6):
            lat, lon = _jitter_geo(rng, anchor["lat"], anchor["lon"], 0.3)
            out.append(_envelope(
                "firms",
                obs_id=f"FIRMS-FUSION-{anchor['fusion_id']}-{k}",
                dtg=_jitter_dtg(rng, anchor["dtg"], 18),
                lat=lat, lon=lon,
                raw={
                    "brightness_k": 372.0 + k,
                    "frp_mw": 78.0,
                    "satellite": "VIIRS-NOAA20",
                    "daynight": "D",
                    "confidence_native": "high",
                    "platform_int": "GEOINT",
                    "fusion_anchor": anchor["fusion_id"],
                },
                confidence=0.91,
            ))
    return out


# -----------------------------------------------------------------------------
# Emit everything
# -----------------------------------------------------------------------------
def _hash_chain(records: list[dict]) -> list[dict]:
    """Append a hash-chained provenance line to every record (audit log seed)."""
    prev = "0" * 16
    for r in records:
        body = f"{prev}|{r['source_type']}|{r['observation_id']}|{r['dtg']}|{r['lat']}|{r['lon']}"
        h = hashlib.sha256(body.encode()).hexdigest()[:16]
        r["audit_prev"] = prev
        r["audit_hash"] = h
        prev = h
    return records


def _generate_data() -> dict[str, Any]:
    rng = random.Random(SEED)
    random.seed(SEED)

    sources: dict[str, list[dict]] = {
        "ais":     gen_ais(rng),
        "asam":    gen_asam(rng),
        "milobj":  gen_milobj(rng),
        "hituav":  gen_hituav(rng),
        "dronerf": gen_dronerf(rng),
        "wifibt":  gen_wifibt(rng),
        "firms":   gen_firms(rng),
    }

    # Sort each source by dtg then hash-chain it (per-stream audit log).
    for k in sources:
        sources[k].sort(key=lambda r: r["dtg"])
        _hash_chain(sources[k])

    # Combined observation file
    all_obs = []
    for k, v in sources.items():
        all_obs.extend(v)
    all_obs.sort(key=lambda r: r["dtg"])

    (ROOT / "ais.json").write_text(json.dumps(sources["ais"], indent=2))
    (ROOT / "asam.json").write_text(json.dumps(sources["asam"], indent=2))
    (ROOT / "milobj.json").write_text(json.dumps(sources["milobj"], indent=2))
    (ROOT / "hituav.json").write_text(json.dumps(sources["hituav"], indent=2))
    (ROOT / "dronerf.json").write_text(json.dumps(sources["dronerf"], indent=2))
    (ROOT / "wifibt.json").write_text(json.dumps(sources["wifibt"], indent=2))
    (ROOT / "firms.json").write_text(json.dumps(sources["firms"], indent=2))

    (ROOT / "all_observations.json").write_text(json.dumps({
        "schema_version": "omni-intel-v1",
        "envelope": ["source_type", "observation_id", "dtg", "lat", "lon",
                     "raw_signature", "confidence", "audit_prev", "audit_hash"],
        "generated_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "n_observations": len(all_obs),
        "sources": {k: len(v) for k, v in sources.items()},
        "observations": all_obs,
    }, indent=2))

    (ROOT / "platform_library.json").write_text(json.dumps({
        "library": PLATFORM_LIB,
        "n": len(PLATFORM_LIB),
        "note": "Per-INT reference library used by the IMINT classifier.",
    }, indent=2))

    (ROOT / "planted_fusions.json").write_text(json.dumps({
        "anchors": FUSION_ANCHORS,
        "note": "Ground-truth multi-source fusion events. The correlator must "
                "rediscover these without seeing the labels.",
    }, indent=2))

    return {"sources": sources, "all_obs": all_obs}


# -----------------------------------------------------------------------------
# Cached briefs -- pre-computed ASIB scenarios so the demo never blocks on LLM
# -----------------------------------------------------------------------------
def _baseline_brief(scenario_label: str, n_obs: int, n_fusion: int) -> str:
    """Deterministic fallback brief used if pre-compute LLM call fails."""
    today = datetime.now(timezone.utc).strftime("%d%H%MZ %b %Y").upper()
    return f"""# DAILY ALL-SOURCE INTELLIGENCE BRIEF -- OMNI-INTEL
**DTG:** {today}  **CLASS:** UNCLASSIFIED//FOUO (DEMO)
**ORIGIN:** USMC LOGCOM CDAO / OMNI-INTEL  **SCENARIO:** {scenario_label}

## 1. BLUF
Multi-INT fusion across 7 collection streams produced {n_fusion} cross-source
clusters of intelligence interest within the 24h window. Highest-confidence
event indicates a covert vessel signature in the Sulu Sea (F-001) supported by
GEOINT (AIS gap), MASINT (thermal IR blob), SIGINT (drone-control RF), and
OSINT (ASAM advisory). Recommend Stand-In-Force ISR re-task to confirm.

## 2. OBSERVED ACTIVITY BY SOURCE-TYPE
- **GEOINT (AIS):** vessel-traffic baseline normal; 1 high-priority gap event.
- **OSINT (ASAM):** boarding advisories trending upward in Sulu / Sibutu.
- **IMINT (mil-object):** 2 fusion-supporting tile detections.
- **MASINT (HIT-UAV thermal):** 3 anomalous IR blobs at fusion coordinates.
- **SIGINT (DroneRF + WiFi/BT):** non-DJI 433 MHz handheld + ESP32 burst signatures.
- **GEOINT (FIRMS):** industrial fire cluster at Subic POL farm (78 MW).

## 3. FUSED-SOURCE HIGHLIGHTS
- F-001 (HIGH conf): covert-vessel cluster, 4 INTs concur within 90 min / 2 km.
- F-002 (MED-HIGH): UAS launch signature, MASINT + SIGINT + IMINT concur.
- F-003 (MED): industrial fire with secondary WiFi/BT evac signature.
- F-004 (MED): pirate skiff swarm, OSINT + GEOINT + SIGINT concur.
- F-005 (HIGH): beach-recon signature, SIGINT + MASINT + IMINT concur.

## 4. NAMED THREATS
- Skiff-borne boarding parties in Sibutu Passage (ASAM trend).
- Suspected covert UAS LRC operating from coastal fishing platform off Mindoro.
- Beach reconnaissance element in vicinity of Palawan with covert RF discipline.

## 5. COLLECTION RECOMMENDATIONS (CCIR-aligned)
- Re-task MQ-9A onto F-001 coordinates 6.45N/121.08E for IR confirmation.
- Cue P-8A MAD/EO at F-002 launch-rail coordinates next dark-cycle pass.
- Request HUMINT from Subic harbor master on F-003 facility evacuation status.
- Direct Stand-In-Force squad to investigate F-005 RF/IR coordinates within 6h.

## 6. CONFIDENCE STATEMENT
HIGH on event detection -- multi-INT corroboration reduces single-source error.
MED on attribution -- 4 of 5 fused events lack HUMINT/SIGINT linguistic confirm.

## 7. CCDR DISTRIBUTION
USMC LOGCOM CDAO // INDOPACOM J2 // MARFORPAC G-2 // 1st MEF G-2
"""


def _precompute_briefs() -> None:
    """Run the hero LLM call now and cache its output. Cache-first pattern."""
    try:
        import sys as _sys
        _sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[2]))
        from shared.kamiwaza_client import chat  # type: ignore
    except Exception:
        chat = None  # type: ignore

    scenarios = [
        ("Daily Wide-Area ISR (24h, all sources)", 16500, 5),
        ("South-China-Sea Surge (12h, AIS + RF + IMINT prioritized)", 9200, 3),
        ("Pirate Threat Window (Sibutu Passage, 6h)", 4100, 2),
    ]

    SYSTEM = """You are a USMC LOGCOM CDAO all-source intelligence analyst.
Doctrine: BLUF first, EEFI awareness, CCIR-driven recommendations. INTs cited:
GEOINT, IMINT, SIGINT, MASINT, OSINT, HUMINT. Voice: terse, declarative, US
military, ZULU times. Use OPLAN-style headers. Round numbers. Never fabricate.
"""

    out: dict[str, str] = {}
    for label, n_obs, n_fusion in scenarios:
        if chat is None:
            out[label] = _baseline_brief(label, n_obs, n_fusion)
            continue
        prompt = f"""Compose a SIPR-style DAILY ALL-SOURCE INTELLIGENCE BRIEF for the
following scenario. Use this skeleton verbatim:

# DAILY ALL-SOURCE INTELLIGENCE BRIEF -- OMNI-INTEL
**DTG:** <ZULU>  **CLASS:** UNCLASSIFIED//FOUO (DEMO)
**ORIGIN:** USMC LOGCOM CDAO / OMNI-INTEL  **SCENARIO:** {label}

## 1. BLUF
## 2. OBSERVED ACTIVITY BY SOURCE-TYPE
## 3. FUSED-SOURCE HIGHLIGHTS
## 4. NAMED THREATS
## 5. COLLECTION RECOMMENDATIONS (CCIR-aligned)
## 6. CONFIDENCE STATEMENT
## 7. CCDR DISTRIBUTION

DATA:
- 7 fused INT streams (GEOINT-AIS, OSINT-ASAM, IMINT-milobj, MASINT-HIT-UAV
  thermal, SIGINT-DroneRF, SIGINT-WiFi/BT, GEOINT-FIRMS).
- {n_obs} normalized observations in the window.
- {n_fusion} cross-source fusion clusters detected by the OMNI correlator,
  of which the highest-confidence is F-001: AIS gap + thermal IR blob + RF
  spike + ASAM boarding-attempt advisory at 6.45N/121.08E in the Sulu Sea.
- Other fusion clusters: F-002 covert UAS launch (Mindoro coast),
  F-003 industrial fire (Subic POL farm, 78 MW),
  F-004 pirate skiff swarm (Sibutu Passage),
  F-005 beach-recon signature (Palawan).
- AOR: Sulu Sea / Western Philippine Sea -- contested logistics / Stand-In Force
  AOR in line with MARADMIN 131/26 and the WestPac Marine Littoral concept.

CCDR distribution line: USMC LOGCOM CDAO // INDOPACOM J2 // MARFORPAC G-2 // 1st MEF G-2.
Markdown only. No preamble. ~600 words max.
"""
        text = None
        # Try with several call shapes -- newer reasoning models reject
        # max_tokens / temperature parameters that older chat models accept.
        for kwargs in (
            {"model": "gpt-5.4", "temperature": 0.3},
            {"model": "gpt-5.4-mini"},
            {"model": "gpt-4o-mini", "temperature": 0.3, "max_tokens": 1800},
        ):
            try:
                text = chat(
                    [{"role": "system", "content": SYSTEM},
                     {"role": "user", "content": prompt}],
                    **kwargs,
                ).strip()
                if text:
                    break
            except Exception as e:
                last = e
                continue
        if text:
            out[label] = text
        else:
            print(f"  WARN: LLM precompute for '{label}' failed; using baseline.")
            out[label] = _baseline_brief(label, n_obs, n_fusion)

    (ROOT / "cached_briefs.json").write_text(json.dumps(out, indent=2))
    print(f"Wrote {len(out)} cached briefs -> {ROOT/'cached_briefs.json'}")


def main() -> None:
    bundle = _generate_data()
    src_counts = {k: len(v) for k, v in bundle["sources"].items()}
    print("OMNI-INTEL synthetic dataset")
    print("----------------------------")
    print(f"Total normalized observations: {len(bundle['all_obs'])}")
    for k, v in src_counts.items():
        print(f"  {k:8s} {v}")
    print(f"Planted fusion anchors: {len(FUSION_ANCHORS)}")
    print()
    print("Pre-computing cached ASIB briefs (hero LLM, cache-first)...")
    _precompute_briefs()
    print("Done.")


if __name__ == "__main__":
    main()
