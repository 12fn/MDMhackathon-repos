"""CUAS-DETECT — synthetic RF spectrogram + UAS signature generator.

Real datasets referenced (would plug in via data/load_real.py):
  1. Drone Recognition based on RF Spectrogram (DroneRF-B Spectra)
     https://ieee-dataport.org/  (search: "DroneRF-B Spectra")
  2. Drone RF Identification dataset (DroneRC RF Signal)
     https://ieee-dataport.org/  (search: "DroneRC RF Signal")

This synthesizer produces:

  - sample_spectra/*.png          : 6 procedurally-generated spectrograms
                                    (frequency on Y, time on X, intensity color)
                                    representing distinct UAS RF signatures.
  - data/rf_id_db.csv             : 30 known controller signature fingerprints
                                    (manufacturer, model, band, hopping, protocol)
  - data/engagement_options.json  : 8 named engagement options with ROE annotations
  - data/cached_briefs.json       : 6 pre-computed CUAS engagement briefs (one per
                                    sample spectrogram) for cache-first demo.

Seed = 1776 for reproducibility.
"""
from __future__ import annotations

import csv
import json
import math
import os
import random
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

OUT_DIR = Path(__file__).parent
APP_DIR = OUT_DIR.parent
SPECTRA_DIR = APP_DIR / "sample_spectra"

SEED = 1776
SPEC_W, SPEC_H = 720, 360  # time x freq pixels


# ─────────────────────────────────────────────────────────────────────────────
# UAS signature definitions (synthetic but plausible per public RF lit)
# ─────────────────────────────────────────────────────────────────────────────
SIGNATURES = [
    {
        "id": "dji_mavic",
        "title": "DJI Mavic 3 (OcuSync 3+)",
        "uas_class": "DJI Mavic",
        "controller": "OcuSync",
        "band_ghz": "2.4 / 5.8",
        "centers_mhz": [2412, 2437, 2462, 5745, 5785, 5825],
        "hop_period_ms": 1.4,
        "bandwidth_mhz": 10.0,
        "snr_db": 22.0,
        "intent_hint": "recon",
        "ground_truth_range_km": 3.2,
    },
    {
        "id": "parrot_anafi",
        "title": "Parrot Anafi USA (WiFi 802.11n)",
        "uas_class": "Parrot Anafi",
        "controller": "WiFi",
        "band_ghz": "2.4 / 5.8",
        "centers_mhz": [2412, 2437, 5180, 5240, 5260],
        "hop_period_ms": 0.0,           # WiFi: continuous channels, no hopping
        "bandwidth_mhz": 20.0,
        "snr_db": 18.0,
        "intent_hint": "recon",
        "ground_truth_range_km": 1.4,
    },
    {
        "id": "cots_fixed_wing",
        "title": "Custom commercial fixed-wing (LoRa C2)",
        "uas_class": "COTS-fixed-wing",
        "controller": "LoRa",
        "band_ghz": "0.9",
        "centers_mhz": [902, 905, 910, 915, 920, 925],
        "hop_period_ms": 12.0,
        "bandwidth_mhz": 0.5,
        "snr_db": 14.0,
        "intent_hint": "strike",
        "ground_truth_range_km": 9.5,
    },
    {
        "id": "hobbyist_quad",
        "title": "Hobbyist quad (FrSky 2.4 GHz / proprietary FHSS)",
        "uas_class": "hobbyist-quad",
        "controller": "proprietary",
        "band_ghz": "2.4",
        "centers_mhz": [2402, 2418, 2434, 2450, 2466, 2480],
        "hop_period_ms": 9.0,
        "bandwidth_mhz": 1.5,
        "snr_db": 12.0,
        "intent_hint": "decoy",
        "ground_truth_range_km": 0.7,
    },
    {
        "id": "swarm_pattern",
        "title": "Multi-emitter swarm (4-8 quads, mixed FHSS)",
        "uas_class": "swarm",
        "controller": "proprietary",
        "band_ghz": "2.4 / 5.8",
        "centers_mhz": [2410, 2430, 2450, 2470, 5180, 5220, 5260, 5300],
        "hop_period_ms": 4.0,
        "bandwidth_mhz": 2.0,
        "snr_db": 16.0,
        "intent_hint": "swarm-overwatch",
        "ground_truth_range_km": 2.1,
    },
    {
        "id": "ambient_no_signal",
        "title": "Ambient RF (no UAS detected)",
        "uas_class": "ambient",
        "controller": "none",
        "band_ghz": "2.4 / 5.8",
        "centers_mhz": [],
        "hop_period_ms": 0.0,
        "bandwidth_mhz": 0.0,
        "snr_db": 0.0,
        "intent_hint": "unknown",
        "ground_truth_range_km": 0.0,
    },
]


# ─────────────────────────────────────────────────────────────────────────────
# Spectrogram synthesis
# ─────────────────────────────────────────────────────────────────────────────
def _freq_to_y(freq_mhz: float, freq_min: float, freq_max: float) -> int:
    """Map frequency to pixel row (top = high freq, bottom = low freq)."""
    if freq_max <= freq_min:
        return SPEC_H // 2
    norm = (freq_mhz - freq_min) / (freq_max - freq_min)
    norm = max(0.0, min(1.0, norm))
    return int((1.0 - norm) * (SPEC_H - 1))


def synthesize_spectrogram(sig: dict, rng: random.Random) -> np.ndarray:
    """Return an HxW float32 array of intensities in [0, 1]."""
    arr = np.zeros((SPEC_H, SPEC_W), dtype=np.float32)
    np_rng = np.random.default_rng(SEED + sum(ord(c) for c in sig["id"]))

    # baseline thermal noise floor
    arr += np_rng.normal(0.18, 0.04, size=arr.shape).astype(np.float32)

    centers = sig["centers_mhz"]
    if centers:
        freq_min = min(centers) - 30
        freq_max = max(centers) + 30
    else:
        freq_min, freq_max = 2400, 2500

    snr = sig["snr_db"] / 30.0  # rescale to a brightness boost
    bw_mhz = sig["bandwidth_mhz"]
    hop_ms = sig["hop_period_ms"]

    if sig["controller"] == "none":
        # Just thermal noise + a few faint stationary lines (WiFi APs in distance)
        for stable_mhz in [2412, 2437, 2462, 5180, 5240]:
            if freq_min <= stable_mhz <= freq_max:
                y = _freq_to_y(stable_mhz, freq_min, freq_max)
                arr[max(0, y - 1):y + 2, :] += 0.05
        return np.clip(arr, 0, 1.0)

    if sig["controller"] == "WiFi":
        # WiFi: 20 MHz wide continuous bursts on a few channels, intermittent
        for c in centers:
            y = _freq_to_y(c, freq_min, freq_max)
            half_bw_px = max(2, int((bw_mhz / (freq_max - freq_min)) * SPEC_H / 2))
            for t in range(SPEC_W):
                if rng.random() < 0.55:  # bursty traffic
                    intensity = snr * (0.7 + 0.3 * rng.random())
                    y0 = max(0, y - half_bw_px)
                    y1 = min(SPEC_H, y + half_bw_px)
                    arr[y0:y1, t] += intensity * np.exp(
                        -((np.arange(y0, y1) - y) ** 2) / (2 * (half_bw_px / 1.5) ** 2)
                    )
        return np.clip(arr, 0, 1.0)

    if sig["controller"] == "LoRa":
        # Chirp spread spectrum — visible diagonal up-chirps
        chirp_w = 30  # px wide per chirp
        n_chirps = SPEC_W // 90
        for n in range(n_chirps):
            t0 = n * 90 + rng.randint(0, 25)
            f0 = rng.choice(centers)
            f1 = f0 + rng.choice([3, 4, 5])  # up-chirp
            for k in range(chirp_w):
                t = t0 + k
                if t >= SPEC_W:
                    break
                fk = f0 + (f1 - f0) * (k / chirp_w)
                y = _freq_to_y(fk, freq_min, freq_max)
                arr[max(0, y - 1):y + 2, t] += snr * 0.85
        return np.clip(arr, 0, 1.0)

    # Hopping / FHSS controllers (OcuSync, hobbyist FHSS, swarm)
    # Each "hop" parks energy in one channel for hop_period (in pixels).
    hop_px = max(2, int(hop_ms * (SPEC_W / 200.0)))
    n_emitters = 1
    if sig["uas_class"] == "swarm":
        n_emitters = rng.randint(4, 7)
    for _emitter in range(n_emitters):
        t = rng.randint(0, hop_px)
        while t < SPEC_W:
            c = rng.choice(centers)
            y = _freq_to_y(c, freq_min, freq_max)
            half_bw_px = max(2, int((bw_mhz / (freq_max - freq_min)) * SPEC_H / 2))
            t_end = min(SPEC_W, t + hop_px)
            for tx in range(t, t_end):
                jitter = rng.gauss(0, 0.5)
                yc = y + int(jitter)
                y0 = max(0, yc - half_bw_px)
                y1 = min(SPEC_H, yc + half_bw_px)
                intensity = snr * (0.85 + 0.15 * rng.random())
                arr[y0:y1, tx] += intensity * np.exp(
                    -((np.arange(y0, y1) - yc) ** 2) / (2 * (half_bw_px / 1.4) ** 2)
                )
            t = t_end + rng.randint(1, 3)  # short blank between hops

    return np.clip(arr, 0, 1.0)


def render_png(arr: np.ndarray, sig: dict, out_path: Path) -> None:
    """Render a spectrogram array to a colored PNG with axis annotations."""
    # Map intensity -> color (kamiwaza neon-green to amber to red palette)
    def colormap(v: float) -> tuple[int, int, int]:
        v = max(0.0, min(1.0, v))
        if v < 0.25:
            # dark → deep green
            t = v / 0.25
            return (int(10 + t * 6), int(20 + t * 80), int(20 + t * 56))
        elif v < 0.55:
            t = (v - 0.25) / 0.30
            return (int(16), int(100 + t * 155), int(76 + t * 90))  # green → neon
        elif v < 0.80:
            t = (v - 0.55) / 0.25
            return (int(16 + t * 226), int(255 - t * 60), int(166 - t * 90))
        else:
            t = (v - 0.80) / 0.20
            return (int(242 + t * 13), int(195 - t * 120), int(76 - t * 60))

    h, w = arr.shape
    img = Image.new("RGB", (w, h), (10, 10, 10))
    px = img.load()
    for y in range(h):
        row = arr[y]
        for x in range(w):
            px[x, y] = colormap(float(row[x]))

    # add a small axis label band at the bottom + freq band on left
    canvas = Image.new("RGB", (w + 60, h + 40), (10, 10, 10))
    canvas.paste(img, (60, 0))
    draw = ImageDraw.Draw(canvas)
    try:
        font = ImageFont.truetype("/System/Library/Fonts/Menlo.ttc", 11)
        font_big = ImageFont.truetype("/System/Library/Fonts/Menlo.ttc", 13)
    except (OSError, IOError):
        font = ImageFont.load_default()
        font_big = ImageFont.load_default()

    # title
    draw.text((6, h + 6), f"{sig['title']}  ·  {sig['band_ghz']} GHz", fill=(0, 255, 167), font=font_big)
    draw.text((6, h + 24), f"hop_period={sig['hop_period_ms']}ms  bw={sig['bandwidth_mhz']}MHz  snr={sig['snr_db']}dB",
              fill=(160, 160, 160), font=font)
    # left freq axis
    draw.text((4, 4), "FREQ↑", fill=(0, 255, 167), font=font)
    draw.text((4, h - 14), "FREQ↓", fill=(0, 255, 167), font=font)
    # bottom time axis
    draw.text((60, h - 14), "← TIME →", fill=(160, 160, 160), font=font)

    canvas.save(out_path, format="PNG")


def write_npy(arr: np.ndarray, out_path: Path) -> None:
    """Also write the raw float32 array for downstream heuristic feature extraction."""
    np.save(out_path, arr.astype(np.float32))


# ─────────────────────────────────────────────────────────────────────────────
# RF identification database (30 known controllers)
# ─────────────────────────────────────────────────────────────────────────────
RF_DB_ROWS = [
    # (manufacturer, controller_model, band_ghz, hopping_pattern, protocol)
    ("DJI",        "RC-N1",            "2.4 / 5.8", "FHSS 1.4ms",       "OcuSync 2.0"),
    ("DJI",        "RC Pro",           "2.4 / 5.8", "FHSS 1.4ms",       "OcuSync 3+"),
    ("DJI",        "DJI RC 2",         "2.4 / 5.8", "FHSS 1.6ms",       "OcuSync 3+"),
    ("DJI",        "Lightbridge 2",    "2.4",       "FHSS 2.0ms",       "Lightbridge"),
    ("DJI",        "Cendence",         "2.4 / 5.8", "FHSS 1.5ms",       "Lightbridge 2"),
    ("Parrot",     "SkyController 4",  "2.4 / 5.8", "WiFi 802.11ac",    "WiFi"),
    ("Parrot",     "Anafi USA RC",     "2.4 / 5.8", "WiFi 802.11n",     "WiFi"),
    ("Autel",      "Smart Controller", "2.4 / 5.8", "FHSS 1.8ms",       "Autel-Sky"),
    ("Autel",      "EVO Lite RC",      "2.4 / 5.8", "FHSS 2.0ms",       "Autel-Sky"),
    ("Skydio",     "Skydio 2 Beacon",  "2.4",       "WiFi 802.11n",     "WiFi"),
    ("Skydio",     "X10D Controller",  "2.4 / 5.8", "FHSS 1.6ms",       "proprietary"),
    ("Yuneec",     "ST16S",            "2.4 / 5.8", "WiFi 802.11n",     "WiFi"),
    ("FrSky",      "Taranis X9D",      "2.4",       "FHSS 9ms",         "ACCESS"),
    ("FrSky",      "Horus X10",        "2.4",       "FHSS 9ms",         "ACCST D16"),
    ("Spektrum",   "DX9 Black",        "2.4",       "DSSS/FHSS 11ms",   "DSMX"),
    ("Spektrum",   "iX20",             "2.4",       "DSSS/FHSS 11ms",   "DSMX"),
    ("Futaba",     "T16IZ",            "2.4",       "FHSS 8ms",         "FASSTest"),
    ("Futaba",     "T18SZ",            "2.4",       "FHSS 8ms",         "FASSTest"),
    ("Walkera",    "Devo F12E",        "2.4",       "FHSS 6ms",         "DEVO"),
    ("Spreadtrum", "TBS Crossfire",    "0.9",       "LoRa 12ms chirp",  "Crossfire"),
    ("ImmersionRC","Tramp HV",         "5.8",       "analog video",     "analog VTx"),
    ("Holybro",    "Telemetry SiK",    "0.9",       "FHSS 10ms",        "MAVLink/SiK"),
    ("RFD900x",    "RFD900x telemetry","0.9",       "FHSS 25ms",        "MAVLink"),
    ("Microhard",  "pMDDL2450",        "2.4",       "TDMA",             "Microhard"),
    ("Doodle Labs","Mesh Rider",       "2.4 / 5.8", "Mesh OFDM",        "MIMO mesh"),
    ("Silvus",     "StreamCaster",     "2.4 / 5.8", "MIMO-OFDM",        "MN-MIMO"),
    ("Sirius",     "GCS-Lite",         "0.9 / 2.4", "FHSS 7ms",         "proprietary"),
    ("Iris",       "ATAK companion",   "2.4",       "WiFi 802.11n",     "WiFi"),
    ("Generic",    "Locally-admin C2", "2.4 / 5.8", "FHSS unspecified", "unknown"),
    ("Generic",    "ESP32 video drop", "2.4",       "WiFi/raw 802.11",  "WiFi"),
]


def write_rf_id_db() -> None:
    p = OUT_DIR / "rf_id_db.csv"
    with p.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["manufacturer", "controller_model", "band_ghz", "hopping_pattern", "protocol"])
        w.writerows(RF_DB_ROWS)


# ─────────────────────────────────────────────────────────────────────────────
# Engagement options w/ ROE annotations
# (Realistic categories, not specific deployed-system claims.)
# ─────────────────────────────────────────────────────────────────────────────
ENGAGEMENT_OPTIONS = [
    {
        "id": "monitor",
        "name": "Passive monitor / track only",
        "kinetic": False,
        "rf_emission": False,
        "authority_required": "Watch officer (OOD)",
        "roe_class": "Observe / report — no engagement.",
        "notes": "Default for unverified contacts inside passive collection envelope.",
    },
    {
        "id": "ews_jam_sector",
        "name": "Directional RF jam — single sector",
        "kinetic": False,
        "rf_emission": True,
        "authority_required": "Installation Commander (delegable to OIC EW)",
        "roe_class": "Non-kinetic interdiction; FCC NTIA spectrum coordination required outside emergency.",
        "notes": "Sector-narrow C2 + GNSS jam. Lowest collateral risk; spectrum deconfliction first.",
    },
    {
        "id": "ews_jam_omnidirectional",
        "name": "Omnidirectional RF jam (perimeter wide)",
        "kinetic": False,
        "rf_emission": True,
        "authority_required": "Installation Commander, MARFORCYBER notify",
        "roe_class": "Non-kinetic; will affect friendly C2/Wi-Fi/GNSS in zone.",
        "notes": "Reserve for confirmed multi-vehicle / swarm threats only.",
    },
    {
        "id": "spoof_gps",
        "name": "GPS spoof (push UAS off course)",
        "kinetic": False,
        "rf_emission": True,
        "authority_required": "Installation Commander + EW spectrum auth",
        "roe_class": "Non-kinetic; may displace UAS into civil airspace.",
        "notes": "Effective against navigation-coupled autonomy; ineffective vs. inertial-only.",
    },
    {
        "id": "request_kinetic",
        "name": "Request kinetic engagement (small-arms / SHORAD)",
        "kinetic": True,
        "rf_emission": False,
        "authority_required": "FOC / Range Control + SECDEF UAS rule-set",
        "roe_class": "Kinetic — last resort. Requires positive ID + hostile intent.",
        "notes": "Per DoDD 3000.09 + 10 USC 130i UAS authorities; backstop overflight defense.",
    },
    {
        "id": "spoof_link",
        "name": "C2 link takeover (protocol-aware)",
        "kinetic": False,
        "rf_emission": True,
        "authority_required": "MARFORCYBER + Title 10 cyber EXORD",
        "roe_class": "Cyber/EW hybrid; pre-coordinated mission required.",
        "notes": "Effective vs. unencrypted FHSS hobbyist links; not for COTS encrypted DJI.",
    },
    {
        "id": "skytracker_log",
        "name": "Track + log only (SkyTracker-style passive ID)",
        "kinetic": False,
        "rf_emission": False,
        "authority_required": "Watch officer",
        "roe_class": "Observe; build pattern of life for repeat overflights.",
        "notes": "Always-on baseline for installation perimeter sensors.",
    },
    {
        "id": "escalate_foc",
        "name": "Escalate to Force Operations Center (FOC)",
        "kinetic": False,
        "rf_emission": False,
        "authority_required": "Watch officer",
        "roe_class": "Notification + decision request.",
        "notes": "Push contact + recommendation up the chain when authority exceeds OOD.",
    },
]


def write_engagement_options() -> None:
    p = OUT_DIR / "engagement_options.json"
    p.write_text(json.dumps(ENGAGEMENT_OPTIONS, indent=2))


# ─────────────────────────────────────────────────────────────────────────────
# Heuristic feature extraction (numpy on the spectrogram array)
# ─────────────────────────────────────────────────────────────────────────────
def extract_features(arr: np.ndarray) -> dict:
    """Return a dict of heuristic spectral features used by the baseline classifier
    AND fed to the multimodal LLM as a JSON sidecar."""
    h, w = arr.shape
    # Power per frequency row (averaged across time)
    row_power = arr.mean(axis=1)
    col_power = arr.mean(axis=0)
    noise_floor = float(np.percentile(arr, 30))
    peak = float(arr.max())
    snr_est_db = float(20 * math.log10(max(1e-3, peak / max(1e-3, noise_floor))))

    # Find top-N frequency rows by power
    top_n = 8
    top_rows_idx = np.argsort(row_power)[-top_n:][::-1]
    # Convert pixel rows back into a band label
    # (relative position; UI knows the band)
    top_bins = [int(i) for i in top_rows_idx]

    # Hopping detection: count zero-crossings of column power around its median
    median = float(np.median(col_power))
    bursts = int(np.sum(np.diff((col_power > median).astype(int)) != 0))
    # Estimate hop period in pixels
    if bursts > 0:
        hop_period_px = float(w / max(1, bursts))
    else:
        hop_period_px = 0.0

    # Active frequency span (rows above threshold)
    active_rows = int((row_power > (noise_floor + 0.05)).sum())
    active_freq_span_pct = float(active_rows / h)

    # Modulation hints
    if snr_est_db < 8:
        mod_hint = "below detection threshold (likely ambient)"
    elif active_freq_span_pct > 0.55 and bursts > 30:
        mod_hint = "wideband multi-emitter (swarm or WiFi)"
    elif bursts > 60 and hop_period_px < 25:
        mod_hint = "fast FHSS (likely OcuSync / proprietary FHSS)"
    elif bursts > 20 and hop_period_px < 60:
        mod_hint = "medium FHSS (hobbyist controller)"
    elif active_freq_span_pct < 0.10 and bursts < 15:
        mod_hint = "narrowband (likely LoRa / telemetry chirp)"
    else:
        mod_hint = "WiFi-style continuous wideband"

    return {
        "noise_floor": round(noise_floor, 3),
        "peak_intensity": round(peak, 3),
        "snr_estimate_db": round(snr_est_db, 1),
        "top_freq_bins": top_bins,
        "burst_count": bursts,
        "hop_period_px": round(hop_period_px, 1),
        "active_freq_span_pct": round(active_freq_span_pct, 3),
        "modulation_hint": mod_hint,
    }


def baseline_classify(features: dict) -> dict:
    """Deterministic baseline guess from features alone (fallback / first-pass)."""
    snr = features["snr_estimate_db"]
    hop_px = features["hop_period_px"]
    bursts = features["burst_count"]
    span = features["active_freq_span_pct"]
    mod = features["modulation_hint"]

    if snr < 8:
        cls = "ambient"
        ctrl = "none"
        intent = "unknown"
        conf = 0.85
    elif "swarm" in mod or "WiFi" in mod and span > 0.5:
        cls = "swarm" if span > 0.55 and bursts > 40 else "Parrot Anafi"
        ctrl = "WiFi" if "WiFi" in mod else "proprietary"
        intent = "swarm-overwatch" if cls == "swarm" else "recon"
        conf = 0.62
    elif "narrowband" in mod or "LoRa" in mod:
        cls = "COTS-fixed-wing"
        ctrl = "LoRa"
        intent = "strike"
        conf = 0.66
    elif "fast FHSS" in mod:
        cls = "DJI Mavic"
        ctrl = "OcuSync"
        intent = "recon"
        conf = 0.72
    elif "medium FHSS" in mod:
        cls = "hobbyist-quad"
        ctrl = "proprietary"
        intent = "decoy"
        conf = 0.58
    else:
        cls = "unknown"
        ctrl = "unknown"
        intent = "unknown"
        conf = 0.40
    return {
        "uas_class_guess": cls,
        "controller_guess": ctrl,
        "intent_guess": intent,
        "baseline_confidence": conf,
        "reasoning": (
            f"baseline: snr={snr}dB, hop_px={hop_px}, bursts={bursts}, "
            f"span={span:.2f}, hint='{mod}'"
        ),
    }


# ─────────────────────────────────────────────────────────────────────────────
# Pre-compute hero CUAS engagement briefs (cache-first)
# ─────────────────────────────────────────────────────────────────────────────
SCENARIO_CONTEXT = {
    "site": "Camp Pendleton — Building 22 perimeter sensor (LOGCOM tenant area)",
    "dtg": "271730ZAPR26",
    "wind": "210/06 KT",
    "ceiling": "BKN 4500",
    "civil_airspace_distance_nm": 0.4,
    "friendly_air_active": "negative",
}


def _scenario_payload(sig: dict, features: dict, baseline: dict) -> dict:
    return {
        "scenario_id": sig["id"],
        "uas_signature_title": sig["title"],
        "ground_truth": {
            "uas_class": sig["uas_class"],
            "controller": sig["controller"],
            "band_ghz": sig["band_ghz"],
            "estimated_range_km": sig["ground_truth_range_km"],
            "intent_hint": sig["intent_hint"],
        },
        "spectral_features": features,
        "baseline_classifier": baseline,
        "site_context": SCENARIO_CONTEXT,
        "rf_id_db_hint": [r for r in RF_DB_ROWS
                          if (sig["controller"] in r[4]
                              or sig["controller"].lower() in r[3].lower())][:4],
    }


SYSTEM_BRIEF = (
    "You are CUAS-DETECT — a USMC LOGCOM Installation Force Protection "
    "watch-officer assistant, on-prem. Given an inbound UAS RF contact "
    "(spectral features + baseline classifier guess + site context), "
    "produce a 'CUAS Engagement Recommendation' brief for the OOD. "
    "Format exactly:\n\n"
    "(U) BLUF — one sentence\n"
    "(U) Contact Identification — UAS class, controller, range, confidence\n"
    "(U) Threat Assessment — inferred intent + 1-line rationale\n"
    "(U) Engagement Options (graded against ROE) — 3 bulleted options, "
    "each tagged [PASSIVE / NON-KINETIC / KINETIC] and with the authority "
    "required\n"
    "(U) Recommended COA — one specific option from the list above with "
    "1-line justification\n\n"
    "Hard rules: Use only the data provided. Do not name specific deployed "
    "USMC EW systems. Do not assert legal authority not listed in the "
    "engagement options. Total length under ~280 words."
)


def _fallback_brief(payload: dict) -> str:
    """Deterministic engagement brief for cache + watchdog fallback."""
    g = payload["ground_truth"]
    b = payload["baseline_classifier"]
    feats = payload["spectral_features"]
    site = payload["site_context"]["site"]
    dtg = payload["site_context"]["dtg"]
    cls = b["uas_class_guess"]
    ctrl = b["controller_guess"]
    intent = b["intent_guess"]
    rng_km = g["estimated_range_km"]
    if cls == "ambient":
        return (
            f"(U) BLUF — No UAS contact above detection threshold at {site} ({dtg}). "
            f"Continue passive watch.\n\n"
            f"(U) Contact Identification — class: ambient · controller: none · "
            f"range: n/a · confidence: HIGH (SNR {feats['snr_estimate_db']} dB).\n\n"
            f"(U) Threat Assessment — No inferred threat; baseline RF environment "
            f"consistent with installation Wi-Fi APs.\n\n"
            f"(U) Engagement Options (graded against ROE)\n"
            f" - [PASSIVE] Track + log (SkyTracker-style) — Watch officer.\n"
            f" - [PASSIVE] Continue baseline collection — Watch officer.\n"
            f" - [PASSIVE] Escalate only on threshold-breach.\n\n"
            f"(U) Recommended COA — Track + log; no engagement warranted."
        )
    return (
        f"(U) BLUF — Probable {cls} UAS inbound at ~{rng_km} km, intent assessed "
        f"as {intent}. Recommend non-kinetic interdiction on watch-officer authority.\n\n"
        f"(U) Contact Identification — class: {cls} · controller: {ctrl} · "
        f"range: ~{rng_km} km · confidence: MED ({feats['modulation_hint']}; "
        f"SNR {feats['snr_estimate_db']} dB).\n\n"
        f"(U) Threat Assessment — {intent.title()} intent inferred from signature "
        f"and approach corridor. Baseline classifier matches "
        f"{b['baseline_confidence']*100:.0f}% confident.\n\n"
        f"(U) Engagement Options (graded against ROE)\n"
        f" - [PASSIVE] Track + SkyTracker log — Watch officer; immediate.\n"
        f" - [NON-KINETIC] Directional sector RF jam — Installation Commander "
        f"(delegable to OIC EW); requires spectrum deconfliction.\n"
        f" - [KINETIC] Request engagement (small-arms / SHORAD) — FOC + SECDEF "
        f"UAS rule-set; reserved for confirmed hostile intent.\n\n"
        f"(U) Recommended COA — Directional sector RF jam after 60-second "
        f"identification hold; matches threat level without civil airspace risk."
    )


def _precompute_briefs() -> None:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))
    try:
        from shared.kamiwaza_client import chat  # noqa: WPS433
    except Exception as e:  # noqa: BLE001
        print(f"[precompute] LLM client unavailable, skipping cache: {e}")
        return

    rng = random.Random(SEED)
    cached: dict[str, dict] = {}
    for sig in SIGNATURES:
        arr_path = SPECTRA_DIR / f"{sig['id']}.npy"
        if arr_path.exists():
            arr = np.load(arr_path)
        else:
            arr = synthesize_spectrogram(sig, rng)
        feats = extract_features(arr)
        baseline = baseline_classify(feats)
        payload = _scenario_payload(sig, feats, baseline)

        # try hero model (text-only — vision call lives in app.py for live demo)
        text = ""
        for hero_model in ("gpt-5.4", "gpt-5.4-mini", None):
            try:
                print(f"[precompute] {sig['id']} (model={hero_model or 'chain-default'}) ...")
                user = (
                    f"Scenario:\n{json.dumps(payload, indent=2)}\n\n"
                    f"Write the CUAS Engagement Recommendation now."
                )
                text = chat(
                    [
                        {"role": "system", "content": SYSTEM_BRIEF},
                        {"role": "user", "content": user},
                    ],
                    model=hero_model,
                    temperature=0.4,
                    max_tokens=600,
                )
                if text and text.strip():
                    break
            except Exception as e:  # noqa: BLE001
                print(f"[precompute] {hero_model} failed: {e}")
                continue
        if not text:
            print(f"[precompute] all models failed for {sig['id']}; using fallback")
            text = _fallback_brief(payload)

        cached[sig["id"]] = {
            "title": sig["title"],
            "ground_truth": payload["ground_truth"],
            "spectral_features": feats,
            "baseline_classifier": baseline,
            "engagement_brief": text,
        }

    out = OUT_DIR / "cached_briefs.json"
    out.write_text(json.dumps(cached, indent=2))
    print(f"[precompute] wrote {out}")


def main() -> None:
    rng = random.Random(SEED)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    SPECTRA_DIR.mkdir(parents=True, exist_ok=True)

    write_rf_id_db()
    write_engagement_options()

    print(f"Synthesizing {len(SIGNATURES)} sample spectrograms ...")
    for sig in SIGNATURES:
        arr = synthesize_spectrogram(sig, rng)
        png_path = SPECTRA_DIR / f"{sig['id']}.png"
        npy_path = SPECTRA_DIR / f"{sig['id']}.npy"
        render_png(arr, sig, png_path)
        write_npy(arr, npy_path)
        print(f"  · {png_path.name}  ({arr.shape}, peak={arr.max():.2f})")

    # also write a manifest the app can iterate
    manifest = [
        {
            "id": s["id"],
            "title": s["title"],
            "uas_class": s["uas_class"],
            "controller": s["controller"],
            "band_ghz": s["band_ghz"],
            "png": f"sample_spectra/{s['id']}.png",
            "npy": f"sample_spectra/{s['id']}.npy",
        }
        for s in SIGNATURES
    ]
    (OUT_DIR / "spectra_manifest.json").write_text(json.dumps(manifest, indent=2))
    print(f"Wrote {OUT_DIR/'spectra_manifest.json'}")


if __name__ == "__main__":
    main()
    if os.getenv("SKIP_PRECOMPUTE") != "1":
        _precompute_briefs()
