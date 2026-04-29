"""DRONE-DOMINANCE — synthetic data generator for the full UAS encounter lifecycle.

This wave-3 app fuses *three* sensor modalities (RF + thermal IR + visual) into a
single multimodal triple-fusion pipeline, then pipes the contact through an
ROE-graded engagement option ladder, an SNCO-tonal hero brief, and an
egocentric AAR scoring step.

Real datasets referenced (would plug in via data/load_real.py):
  1. Drone Dataset (UAV)                  — Kaggle visual photos
  2. HIT-UAV (High-altitude Infrared Thermal Dataset)
  3. DroneRF-B Spectra                    — IEEE DataPort RF spectrograms
  4. DroneRC RF Identification            — IEEE DataPort controller fingerprints
  5. Xperience-10M                        — egocentric helmet-cam stills

Outputs (all under apps/42-drone-dominance/):
  sample_spectra/<scn>.png  + .npy        — 6 RF spectrograms
  sample_thermal/<scn>.png                — 6 thermal IR frames (640x512)
  sample_visual/<scn>.png                 — 6 visual EO photos (640x426)
  xperience_aar_frames/aar_<n>.png        — 4 egocentric helmet-cam stills
  data/scenarios.json                     — 6 scenarios with full ground truth
  data/rf_id_db.csv                       — 30 controller signatures
  data/engagement_options.json            — 8 ROE-graded engagement options
  data/friendly_fleet.json                — friendly drone inventory + mission load
  data/cached_briefs.json                 — pre-computed hero "UAS Encounter Brief"
                                            for all 6 scenarios (cache-first demo)

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
from PIL import Image, ImageDraw, ImageFilter, ImageFont

DATA_DIR = Path(__file__).parent
APP_DIR = DATA_DIR.parent
SPECTRA_DIR = APP_DIR / "sample_spectra"
THERMAL_DIR = APP_DIR / "sample_thermal"
VISUAL_DIR = APP_DIR / "sample_visual"
AAR_DIR = APP_DIR / "xperience_aar_frames"

SEED = 1776
SPEC_W, SPEC_H = 720, 360
THM_W, THM_H = 640, 512
VIS_W, VIS_H = 640, 426
AAR_W, AAR_H = 768, 512


# ─────────────────────────────────────────────────────────────────────────────
# Six threat scenarios — each pairs an RF spectrogram + thermal frame + visual
# photo so the triple-fusion call has all three modalities for the same threat.
# ─────────────────────────────────────────────────────────────────────────────
SCENARIOS: list[dict] = [
    {
        "id": "dji_mavic_recon",
        "title": "DJI Mavic 3 — recon overflight",
        "uas_class": "DJI Mavic",
        "make_model": "DJI Mavic 3",
        "controller": "OcuSync",
        "protocol": "OcuSync 3+",
        "band_ghz": "2.4 / 5.8",
        "centers_mhz": [2412, 2437, 2462, 5745, 5785, 5825],
        "hop_period_ms": 1.4,
        "bandwidth_mhz": 10.0,
        "snr_db": 22.0,
        "intent_hint": "recon",
        "ground_truth_range_km": 3.2,
        "ground_truth_alt_m": 120,
        "thermal_kind": "small_quad_high",
        "visual_kind": "quad_silhouette_sky",
    },
    {
        "id": "parrot_anafi_recon",
        "title": "Parrot Anafi USA — perimeter loiter",
        "uas_class": "Parrot Anafi",
        "make_model": "Parrot Anafi USA",
        "controller": "WiFi",
        "protocol": "WiFi 802.11n (proprietary skycontroller)",
        "band_ghz": "2.4 / 5.8",
        "centers_mhz": [2412, 2437, 5180, 5240, 5260],
        "hop_period_ms": 0.0,
        "bandwidth_mhz": 20.0,
        "snr_db": 18.0,
        "intent_hint": "recon",
        "ground_truth_range_km": 1.4,
        "ground_truth_alt_m": 80,
        "thermal_kind": "small_quad_mid",
        "visual_kind": "quad_silhouette_treeline",
    },
    {
        "id": "cots_fixed_wing_strike",
        "title": "Custom commercial fixed-wing — possible strike",
        "uas_class": "COTS-fixed-wing",
        "make_model": "Skywalker X-class clone (LoRa C2)",
        "controller": "LoRa",
        "protocol": "LoRa CSS",
        "band_ghz": "0.9",
        "centers_mhz": [902, 905, 910, 915, 920, 925],
        "hop_period_ms": 12.0,
        "bandwidth_mhz": 0.5,
        "snr_db": 14.0,
        "intent_hint": "strike",
        "ground_truth_range_km": 9.5,
        "ground_truth_alt_m": 250,
        "thermal_kind": "fixed_wing_low",
        "visual_kind": "fixed_wing_horizon",
    },
    {
        "id": "hobbyist_quad_decoy",
        "title": "Hobbyist quad — close-in decoy",
        "uas_class": "hobbyist-quad",
        "make_model": "FrSky-class proprietary FHSS quad",
        "controller": "proprietary",
        "protocol": "proprietary FHSS",
        "band_ghz": "2.4",
        "centers_mhz": [2402, 2418, 2434, 2450, 2466, 2480],
        "hop_period_ms": 9.0,
        "bandwidth_mhz": 1.5,
        "snr_db": 12.0,
        "intent_hint": "decoy",
        "ground_truth_range_km": 0.7,
        "ground_truth_alt_m": 30,
        "thermal_kind": "small_quad_close",
        "visual_kind": "quad_silhouette_close",
    },
    {
        "id": "swarm_overwatch",
        "title": "Multi-emitter swarm — 6 quads, mixed FHSS",
        "uas_class": "swarm",
        "make_model": "Mixed FPV/quad swarm (6+ vehicles)",
        "controller": "proprietary",
        "protocol": "mixed proprietary FHSS",
        "band_ghz": "2.4 / 5.8",
        "centers_mhz": [2410, 2430, 2450, 2470, 5180, 5220, 5260, 5300],
        "hop_period_ms": 4.0,
        "bandwidth_mhz": 2.0,
        "snr_db": 16.0,
        "intent_hint": "swarm-overwatch",
        "ground_truth_range_km": 2.1,
        "ground_truth_alt_m": 90,
        "thermal_kind": "swarm_blobs",
        "visual_kind": "swarm_specks",
    },
    {
        "id": "ambient_false_alarm",
        "title": "Ambient — sensor false alarm (no UAS)",
        "uas_class": "ambient",
        "make_model": "(no UAS — ambient WiFi + bird heat-track)",
        "controller": "none",
        "protocol": "n/a",
        "band_ghz": "2.4 / 5.8",
        "centers_mhz": [],
        "hop_period_ms": 0.0,
        "bandwidth_mhz": 0.0,
        "snr_db": 0.0,
        "intent_hint": "unknown",
        "ground_truth_range_km": 0.0,
        "ground_truth_alt_m": 0,
        "thermal_kind": "ambient_birds",
        "visual_kind": "empty_sky",
    },
]


# ═════════════════════════════════════════════════════════════════════════════
# 1. RF SPECTROGRAM SYNTHESIS (borrowed from CUAS-DETECT — same shape so the
#    DroneRF-B Spectra plug-in matches both apps)
# ═════════════════════════════════════════════════════════════════════════════
def _freq_to_y(freq_mhz: float, freq_min: float, freq_max: float) -> int:
    if freq_max <= freq_min:
        return SPEC_H // 2
    norm = max(0.0, min(1.0, (freq_mhz - freq_min) / (freq_max - freq_min)))
    return int((1.0 - norm) * (SPEC_H - 1))


def synthesize_spectrogram(sig: dict, rng: random.Random) -> np.ndarray:
    arr = np.zeros((SPEC_H, SPEC_W), dtype=np.float32)
    np_rng = np.random.default_rng(SEED + sum(ord(c) for c in sig["id"]))
    arr += np_rng.normal(0.18, 0.04, size=arr.shape).astype(np.float32)

    centers = sig["centers_mhz"]
    if centers:
        freq_min, freq_max = min(centers) - 30, max(centers) + 30
    else:
        freq_min, freq_max = 2400, 2500

    snr = sig["snr_db"] / 30.0
    bw_mhz = sig["bandwidth_mhz"]
    hop_ms = sig["hop_period_ms"]

    if sig["controller"] == "none":
        for stable_mhz in [2412, 2437, 2462, 5180, 5240]:
            if freq_min <= stable_mhz <= freq_max:
                y = _freq_to_y(stable_mhz, freq_min, freq_max)
                arr[max(0, y - 1):y + 2, :] += 0.05
        return np.clip(arr, 0, 1.0)

    if sig["controller"] == "WiFi":
        for c in centers:
            y = _freq_to_y(c, freq_min, freq_max)
            half_bw_px = max(2, int((bw_mhz / (freq_max - freq_min)) * SPEC_H / 2))
            for t in range(SPEC_W):
                if rng.random() < 0.55:
                    intensity = snr * (0.7 + 0.3 * rng.random())
                    y0 = max(0, y - half_bw_px)
                    y1 = min(SPEC_H, y + half_bw_px)
                    arr[y0:y1, t] += intensity * np.exp(
                        -((np.arange(y0, y1) - y) ** 2) / (2 * (half_bw_px / 1.5) ** 2)
                    )
        return np.clip(arr, 0, 1.0)

    if sig["controller"] == "LoRa":
        chirp_w = 30
        n_chirps = SPEC_W // 90
        for n in range(n_chirps):
            t0 = n * 90 + rng.randint(0, 25)
            f0 = rng.choice(centers)
            f1 = f0 + rng.choice([3, 4, 5])
            for k in range(chirp_w):
                t = t0 + k
                if t >= SPEC_W:
                    break
                fk = f0 + (f1 - f0) * (k / chirp_w)
                y = _freq_to_y(fk, freq_min, freq_max)
                arr[max(0, y - 1):y + 2, t] += snr * 0.85
        return np.clip(arr, 0, 1.0)

    # FHSS / OcuSync / proprietary / swarm
    hop_px = max(2, int(hop_ms * (SPEC_W / 200.0)))
    n_emitters = 1 if sig["uas_class"] != "swarm" else rng.randint(4, 7)
    for _e in range(n_emitters):
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
            t = t_end + rng.randint(1, 3)
    return np.clip(arr, 0, 1.0)


def render_spectrogram_png(arr: np.ndarray, sig: dict, out_path: Path) -> None:
    def colormap(v: float) -> tuple[int, int, int]:
        v = max(0.0, min(1.0, v))
        if v < 0.25:
            t = v / 0.25
            return (int(10 + t * 6), int(20 + t * 80), int(20 + t * 56))
        elif v < 0.55:
            t = (v - 0.25) / 0.30
            return (16, int(100 + t * 155), int(76 + t * 90))
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

    canvas = Image.new("RGB", (w + 60, h + 40), (10, 10, 10))
    canvas.paste(img, (60, 0))
    draw = ImageDraw.Draw(canvas)
    try:
        font = ImageFont.truetype("/System/Library/Fonts/Menlo.ttc", 11)
        font_big = ImageFont.truetype("/System/Library/Fonts/Menlo.ttc", 13)
    except (OSError, IOError):
        font = ImageFont.load_default()
        font_big = ImageFont.load_default()
    draw.text((6, h + 6), f"{sig['title']}  ·  {sig['band_ghz']} GHz",
              fill=(0, 255, 167), font=font_big)
    draw.text((6, h + 24),
              f"hop_period={sig['hop_period_ms']}ms  bw={sig['bandwidth_mhz']}MHz  snr={sig['snr_db']}dB",
              fill=(160, 160, 160), font=font)
    draw.text((4, 4), "FREQ↑", fill=(0, 255, 167), font=font)
    draw.text((4, h - 14), "FREQ↓", fill=(0, 255, 167), font=font)
    draw.text((60, h - 14), "← TIME →", fill=(160, 160, 160), font=font)
    canvas.save(out_path, format="PNG")


# ═════════════════════════════════════════════════════════════════════════════
# 2. THERMAL IR FRAME SYNTHESIS (HIT-UAV plug-in shape)
# ═════════════════════════════════════════════════════════════════════════════
def _thermal_blob(arr: np.ndarray, cx: int, cy: int, rx: int, ry: int,
                  intensity: float) -> None:
    h, w = arr.shape
    y0, y1 = max(0, cy - ry * 3), min(h, cy + ry * 3)
    x0, x1 = max(0, cx - rx * 3), min(w, cx + rx * 3)
    yy, xx = np.meshgrid(np.arange(y0, y1), np.arange(x0, x1), indexing="ij")
    g = intensity * np.exp(
        -(((xx - cx) / max(1.0, rx)) ** 2 + ((yy - cy) / max(1.0, ry)) ** 2)
    )
    arr[y0:y1, x0:x1] = np.maximum(arr[y0:y1, x0:x1], g.astype(np.float32))


def synthesize_thermal(sig: dict, rng: random.Random) -> tuple[np.ndarray, list[dict]]:
    """Return (gray_uint8 frame, list of bbox dicts)."""
    arr = np.zeros((THM_H, THM_W), dtype=np.float32)
    # background gradient (cool sky top, warmer ground bottom)
    grad = np.linspace(0.05, 0.18, THM_H).reshape(-1, 1).repeat(THM_W, axis=1)
    arr += grad.astype(np.float32)
    np_rng = np.random.default_rng(SEED + sum(ord(c) for c in sig["id"]))
    arr += np_rng.normal(0.0, 0.018, size=arr.shape).astype(np.float32)

    bboxes: list[dict] = []
    kind = sig["thermal_kind"]

    def _add_bbox(cls: str, cx: int, cy: int, rx: int, ry: int, conf: float):
        bboxes.append({
            "cls": cls,
            "conf": round(conf, 2),
            "bbox": [int(cx - rx), int(cy - ry), int(cx + rx), int(cy + ry)],
        })

    if kind == "small_quad_high":
        cx, cy = THM_W // 2 + rng.randint(-30, 30), int(THM_H * 0.35)
        _thermal_blob(arr, cx, cy, 7, 5, 0.85)
        _add_bbox("UAS", cx, cy, 12, 9, 0.84)
    elif kind == "small_quad_mid":
        cx, cy = int(THM_W * 0.65), int(THM_H * 0.45)
        _thermal_blob(arr, cx, cy, 9, 7, 0.78)
        _add_bbox("UAS", cx, cy, 14, 11, 0.78)
        # treeline warm pixels
        for x in range(0, THM_W, 14):
            _thermal_blob(arr, x, int(THM_H * 0.78), 16, 8, 0.32)
    elif kind == "fixed_wing_low":
        cx, cy = int(THM_W * 0.4), int(THM_H * 0.50)
        # long thin shape
        for k in range(-22, 23):
            _thermal_blob(arr, cx + k, cy + int(0.05 * k), 3, 2, 0.62)
        _thermal_blob(arr, cx, cy, 10, 4, 0.78)
        _add_bbox("UAS-fixed-wing", cx, cy, 28, 7, 0.71)
    elif kind == "small_quad_close":
        cx, cy = int(THM_W * 0.55), int(THM_H * 0.60)
        _thermal_blob(arr, cx, cy, 14, 12, 0.92)
        _add_bbox("UAS", cx, cy, 22, 18, 0.91)
        # person in the FOB perimeter
        _thermal_blob(arr, int(THM_W * 0.18), int(THM_H * 0.78), 5, 11, 0.74)
        _add_bbox("person", int(THM_W * 0.18), int(THM_H * 0.78), 7, 13, 0.81)
    elif kind == "swarm_blobs":
        for _ in range(rng.randint(5, 7)):
            cx = rng.randint(80, THM_W - 80)
            cy = rng.randint(int(THM_H * 0.25), int(THM_H * 0.55))
            _thermal_blob(arr, cx, cy, 6, 5, rng.uniform(0.66, 0.84))
            _add_bbox("UAS", cx, cy, 10, 8, round(rng.uniform(0.62, 0.80), 2))
    elif kind == "ambient_birds":
        # a couple of small low-confidence warm specks (birds)
        for _ in range(2):
            cx = rng.randint(60, THM_W - 60)
            cy = rng.randint(60, int(THM_H * 0.55))
            _thermal_blob(arr, cx, cy, 3, 2, rng.uniform(0.36, 0.48))
            _add_bbox("animal/bird", cx, cy, 5, 4, round(rng.uniform(0.31, 0.42), 2))
        # a vehicle on the ground (warm, large)
        _thermal_blob(arr, int(THM_W * 0.30), int(THM_H * 0.85), 22, 12, 0.62)
        _add_bbox("vehicle", int(THM_W * 0.30), int(THM_H * 0.85), 26, 16, 0.72)

    arr = np.clip(arr, 0, 1.0)
    gray = (arr * 255.0).astype(np.uint8)
    return gray, bboxes


def render_thermal_png(gray: np.ndarray, bboxes: list[dict],
                       sig: dict, out_path: Path) -> None:
    """Render the thermal frame as an inferno-LUT pseudo-color PNG with bboxes."""
    h, w = gray.shape

    # inferno-ish LUT (no cv2 dependency for the colormap)
    def lut(v: int) -> tuple[int, int, int]:
        u = v / 255.0
        if u < 0.25:
            t = u / 0.25
            return (int(10 + t * 28), int(8 + t * 8), int(60 + t * 95))
        elif u < 0.55:
            t = (u - 0.25) / 0.30
            return (int(38 + t * 130), int(16 + t * 30), int(155 - t * 50))
        elif u < 0.80:
            t = (u - 0.55) / 0.25
            return (int(168 + t * 70), int(46 + t * 110), int(105 - t * 60))
        else:
            t = (u - 0.80) / 0.20
            return (int(238 + t * 17), int(156 + t * 80), int(45 + t * 60))

    # build palette table
    palette = [lut(i) for i in range(256)]
    img = Image.new("RGB", (w, h))
    px = img.load()
    for y in range(h):
        row = gray[y]
        for x in range(w):
            px[x, y] = palette[int(row[x])]

    # bboxes
    draw = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype("/System/Library/Fonts/Menlo.ttc", 12)
    except (OSError, IOError):
        font = ImageFont.load_default()
    for b in bboxes:
        x0, y0, x1, y1 = b["bbox"]
        color = ((255, 80, 80) if "UAS" in b["cls"] else (0, 255, 167))
        draw.rectangle([x0, y0, x1, y1], outline=color, width=2)
        # halo + label
        label = f"{b['cls']} {b['conf']:.2f}"
        tx, ty = x0, max(0, y0 - 14)
        draw.rectangle([tx, ty, tx + 9 * len(label), ty + 12], fill=(0, 0, 0))
        draw.text((tx + 2, ty), label, fill=color, font=font)

    # title strip
    canvas = Image.new("RGB", (w, h + 28), (10, 10, 10))
    canvas.paste(img, (0, 0))
    d2 = ImageDraw.Draw(canvas)
    try:
        font_big = ImageFont.truetype("/System/Library/Fonts/Menlo.ttc", 13)
    except (OSError, IOError):
        font_big = ImageFont.load_default()
    d2.text((6, h + 6), f"THERMAL IR · {sig['title']} · alt~{sig['ground_truth_alt_m']}m",
            fill=(0, 255, 167), font=font_big)
    canvas.save(out_path, format="PNG")


# ═════════════════════════════════════════════════════════════════════════════
# 3. VISUAL EO PHOTO SYNTHESIS (Drone Dataset UAV plug-in shape)
# ═════════════════════════════════════════════════════════════════════════════
def synthesize_visual(sig: dict, rng: random.Random) -> Image.Image:
    """Procedural sky/horizon scene with a drone silhouette."""
    img = Image.new("RGB", (VIS_W, VIS_H), (170, 195, 215))
    draw = ImageDraw.Draw(img)
    kind = sig["visual_kind"]

    # sky gradient
    for y in range(VIS_H):
        u = y / VIS_H
        r = int(140 + (1 - u) * 40)
        g = int(170 + (1 - u) * 35)
        b = int(205 + (1 - u) * 25)
        draw.line([(0, y), (VIS_W, y)], fill=(r, g, b))

    # ground/horizon
    horizon_y = int(VIS_H * 0.78)
    if kind in {"quad_silhouette_treeline", "fixed_wing_horizon",
                "swarm_specks", "quad_silhouette_close"}:
        for x in range(VIS_W):
            jitter = int(8 * math.sin(x * 0.07) + 5 * math.cos(x * 0.13))
            for y in range(horizon_y + jitter, VIS_H):
                u = (y - horizon_y) / max(1, VIS_H - horizon_y)
                draw.point((x, y), fill=(int(60 + u * 25),
                                          int(70 + u * 25),
                                          int(48 + u * 22)))

    # drone shapes
    def _draw_quad(cx: int, cy: int, sz: int, color=(28, 28, 28)):
        # X-frame quad silhouette
        draw.line([(cx - sz, cy - sz), (cx + sz, cy + sz)], fill=color, width=2)
        draw.line([(cx - sz, cy + sz), (cx + sz, cy - sz)], fill=color, width=2)
        # rotors
        for dx, dy in [(-sz, -sz), (sz, -sz), (-sz, sz), (sz, sz)]:
            draw.ellipse([cx + dx - 3, cy + dy - 3, cx + dx + 3, cy + dy + 3],
                          outline=color, width=1)
        # body
        draw.rectangle([cx - 3, cy - 3, cx + 3, cy + 3], fill=color)

    def _draw_fixed_wing(cx: int, cy: int, sz: int, color=(40, 40, 40)):
        draw.polygon([(cx - sz, cy), (cx + sz, cy),
                       (cx + int(sz * 0.4), cy - int(sz * 0.18)),
                       (cx - int(sz * 0.4), cy - int(sz * 0.18))], fill=color)
        draw.line([(cx - 3, cy - 6), (cx + 3, cy - 6)], fill=color, width=2)

    if kind == "quad_silhouette_sky":
        _draw_quad(int(VIS_W * 0.55), int(VIS_H * 0.40), 14)
    elif kind == "quad_silhouette_treeline":
        _draw_quad(int(VIS_W * 0.62), int(VIS_H * 0.45), 16)
    elif kind == "quad_silhouette_close":
        _draw_quad(int(VIS_W * 0.50), int(VIS_H * 0.50), 32)
    elif kind == "fixed_wing_horizon":
        _draw_fixed_wing(int(VIS_W * 0.40), int(VIS_H * 0.55), 26)
    elif kind == "swarm_specks":
        for _ in range(rng.randint(5, 7)):
            cx = rng.randint(80, VIS_W - 80)
            cy = rng.randint(int(VIS_H * 0.20), int(VIS_H * 0.55))
            _draw_quad(cx, cy, rng.randint(7, 12))
    elif kind == "empty_sky":
        # just a couple of birds
        for _ in range(2):
            cx = rng.randint(80, VIS_W - 80)
            cy = rng.randint(60, int(VIS_H * 0.45))
            draw.line([(cx - 6, cy), (cx, cy - 4)], fill=(40, 40, 40), width=2)
            draw.line([(cx, cy - 4), (cx + 6, cy)], fill=(40, 40, 40), width=2)

    # title overlay
    try:
        font = ImageFont.truetype("/System/Library/Fonts/Menlo.ttc", 12)
    except (OSError, IOError):
        font = ImageFont.load_default()
    draw.rectangle([0, 0, VIS_W, 18], fill=(0, 0, 0))
    draw.text((6, 3), f"VISUAL EO · {sig['title']}", fill=(0, 255, 167), font=font)
    return img


def render_visual_png(sig: dict, rng: random.Random, out_path: Path) -> None:
    img = synthesize_visual(sig, rng)
    img.save(out_path, format="PNG")


# ═════════════════════════════════════════════════════════════════════════════
# 4. EGOCENTRIC AAR FRAMES (Xperience-10M plug-in shape) — 4 helmet-cam stills
# ═════════════════════════════════════════════════════════════════════════════
AAR_FRAMES: list[dict] = [
    {
        "id": "aar_01",
        "title": "Helmet-cam — behind a Stinger MANPADS launcher",
        "scene_kind": "stinger_launcher",
        "context": (
            "You are gunner on an MANPADS team. UAS classified as DJI Mavic 3 "
            "at 3.2 km, intent assessed RECON. ROE: jam-non-kinetic recommended; "
            "kinetic requires confirmed hostile intent."
        ),
        "doctrine_reference": "JP 3-01 'Countering Air and Missile Threats' Ch IV; 10 USC 130i UAS authorities",
    },
    {
        "id": "aar_02",
        "title": "Helmet-cam — behind a SkyTracker passive RF console",
        "scene_kind": "skytracker_console",
        "context": (
            "You are watch officer at the Installation EOC. Active contact: COTS "
            "fixed-wing at 9.5 km, intent STRIKE. Civil airspace 0.4 nm. Hero "
            "brief recommends sector RF jam after 60-second hold."
        ),
        "doctrine_reference": "JCO-CUAS Operational Concept; MARFORCYBER spectrum coordination",
    },
    {
        "id": "aar_03",
        "title": "Helmet-cam — perimeter foot patrol, hand-held EW jammer",
        "scene_kind": "patrol_jammer",
        "context": (
            "You are on a perimeter patrol with a hand-held DroneGun-class jammer. "
            "Hobbyist quad observed at 0.7 km, intent assessed DECOY. ROE allows "
            "watch-officer-level non-kinetic interdiction."
        ),
        "doctrine_reference": "MCWP 3-22 Air Defense; MARADMIN 131/26 (UAS authorities digest)",
    },
    {
        "id": "aar_04",
        "title": "Helmet-cam — FOC battle captain, decision station",
        "scene_kind": "foc_captain",
        "context": (
            "You are the FOC battle captain. Multi-emitter swarm at 2.1 km, intent "
            "OVERWATCH. Kinetic engagement requires SECDEF UAS rule-set + positive "
            "ID. Jam-omnidirectional will affect friendly C2 in zone."
        ),
        "doctrine_reference": "DoDD 3000.09; 10 USC 130i; JP 3-01 Ch IV",
    },
]


def synthesize_aar_frame(frame: dict, out_path: Path) -> None:
    """Procedural egocentric helmet-cam still — first-person framed scene."""
    img = Image.new("RGB", (AAR_W, AAR_H), (35, 38, 42))
    draw = ImageDraw.Draw(img)
    kind = frame["scene_kind"]

    # base ground/horizon
    for y in range(AAR_H):
        u = y / AAR_H
        r = int(40 + u * 30)
        g = int(46 + u * 32)
        b = int(50 + u * 32)
        draw.line([(0, y), (AAR_W, y)], fill=(r, g, b))

    # helmet-cam vignette top + bottom
    for y in range(0, 60):
        a = 1.0 - y / 60.0
        for x in range(AAR_W):
            draw.point((x, y), fill=(int(20 * a), int(20 * a), int(20 * a)))

    # arms / equipment in lower foreground (always present in helmet-cam)
    # gloves + sleeves
    draw.polygon([(0, AAR_H), (210, AAR_H), (170, int(AAR_H * 0.78)),
                   (0, int(AAR_H * 0.82))], fill=(50, 56, 48))
    draw.polygon([(AAR_W, AAR_H), (AAR_W - 210, AAR_H), (AAR_W - 170, int(AAR_H * 0.78)),
                   (AAR_W, int(AAR_H * 0.82))], fill=(50, 56, 48))

    if kind == "stinger_launcher":
        # MANPADS tube extending from shoulder forward into frame center
        draw.polygon([(int(AAR_W * 0.30), int(AAR_H * 0.85)),
                       (int(AAR_W * 0.65), int(AAR_H * 0.45)),
                       (int(AAR_W * 0.72), int(AAR_H * 0.48)),
                       (int(AAR_W * 0.36), int(AAR_H * 0.92))],
                      fill=(38, 40, 35))
        draw.ellipse([int(AAR_W * 0.62), int(AAR_H * 0.42),
                       int(AAR_W * 0.74), int(AAR_H * 0.52)], outline=(28, 28, 24), width=3)
        # sky + a tiny drone speck downrange
        for y in range(0, int(AAR_H * 0.50)):
            u = y / (AAR_H * 0.50)
            for x in range(AAR_W):
                draw.point((x, y), fill=(int(150 + u * 20), int(170 + u * 20), int(195 + u * 20)))
        draw.ellipse([int(AAR_W * 0.78), int(AAR_H * 0.18),
                       int(AAR_W * 0.81), int(AAR_H * 0.20)], fill=(20, 20, 20))

    elif kind == "skytracker_console":
        # console bezel with a fake spectrogram on it
        draw.rectangle([60, int(AAR_H * 0.15), AAR_W - 60, int(AAR_H * 0.70)],
                        fill=(14, 14, 14), outline=(0, 187, 122), width=3)
        # rows of fake spectrogram bars
        for y in range(int(AAR_H * 0.20), int(AAR_H * 0.65), 6):
            for x in range(80, AAR_W - 80, 5):
                v = (math.sin(x * 0.03 + y * 0.02) + 1) * 0.5
                col = (int(20 + v * 200), int(120 + v * 100), int(80 + v * 50))
                draw.rectangle([x, y, x + 4, y + 4], fill=col)
        # "INBOUND" callout text
        try:
            f = ImageFont.truetype("/System/Library/Fonts/Menlo.ttc", 14)
        except (OSError, IOError):
            f = ImageFont.load_default()
        draw.text((80, int(AAR_H * 0.16)), "INBOUND · COTS FIXED-WING · 9.5km",
                  fill=(255, 80, 80), font=f)

    elif kind == "patrol_jammer":
        # hands holding a rifle-shaped jammer at low ready
        draw.polygon([(int(AAR_W * 0.30), int(AAR_H * 0.95)),
                       (int(AAR_W * 0.62), int(AAR_H * 0.62)),
                       (int(AAR_W * 0.78), int(AAR_H * 0.65)),
                       (int(AAR_W * 0.40), int(AAR_H * 0.98))],
                      fill=(45, 45, 42))
        # antenna / muzzle pointing ahead
        draw.line([(int(AAR_W * 0.78), int(AAR_H * 0.65)),
                    (int(AAR_W * 0.94), int(AAR_H * 0.55))],
                   fill=(28, 28, 24), width=4)
        # a drone speck above tree line
        draw.ellipse([int(AAR_W * 0.55), int(AAR_H * 0.32),
                       int(AAR_W * 0.59), int(AAR_H * 0.34)], fill=(20, 20, 20))

    elif kind == "foc_captain":
        # tactical display wall
        draw.rectangle([40, 30, AAR_W - 40, int(AAR_H * 0.60)],
                        fill=(8, 8, 12), outline=(0, 187, 122), width=2)
        # fake threat blips
        for _ in range(6):
            cx = random.Random(SEED).randint(80, AAR_W - 80)
            cy = random.Random(SEED * 2).randint(60, int(AAR_H * 0.55))
        # generate stable pattern
        rng = random.Random(SEED + 17)
        for _ in range(6):
            cx = rng.randint(80, AAR_W - 80)
            cy = rng.randint(60, int(AAR_H * 0.55))
            draw.ellipse([cx - 6, cy - 6, cx + 6, cy + 6], outline=(255, 80, 80), width=2)
        try:
            f = ImageFont.truetype("/System/Library/Fonts/Menlo.ttc", 14)
        except (OSError, IOError):
            f = ImageFont.load_default()
        draw.text((50, 38), "SWARM · 6 EMITTERS · 2.1km · OVERWATCH",
                  fill=(255, 80, 80), font=f)

    # caption strip
    try:
        font = ImageFont.truetype("/System/Library/Fonts/Menlo.ttc", 12)
    except (OSError, IOError):
        font = ImageFont.load_default()
    draw.rectangle([0, 0, AAR_W, 18], fill=(0, 0, 0))
    draw.text((6, 3), f"EGOCENTRIC AAR · {frame['title']}",
              fill=(0, 255, 167), font=font)
    img.save(out_path, format="PNG")


# ═════════════════════════════════════════════════════════════════════════════
# 5. RF identification database (30 known controllers — borrowed from CUAS-DETECT)
# ═════════════════════════════════════════════════════════════════════════════
RF_DB_ROWS = [
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
    p = DATA_DIR / "rf_id_db.csv"
    with p.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["manufacturer", "controller_model", "band_ghz",
                    "hopping_pattern", "protocol"])
        w.writerows(RF_DB_ROWS)


# ═════════════════════════════════════════════════════════════════════════════
# 6. ROE-graded engagement options
# ═════════════════════════════════════════════════════════════════════════════
ENGAGEMENT_OPTIONS = [
    {
        "id": "monitor",
        "name": "Passive monitor / track only",
        "kinetic": False, "rf_emission": False,
        "authority_required": "Watch officer (OOD)",
        "roe_class": "Observe / report — no engagement.",
        "notes": "Default for unverified contacts; pattern-of-life build.",
    },
    {
        "id": "ews_jam_sector",
        "name": "Directional RF jam — single sector",
        "kinetic": False, "rf_emission": True,
        "authority_required": "Installation Commander (delegable to OIC EW)",
        "roe_class": "Non-kinetic interdiction; spectrum coordination required.",
        "notes": "Lowest collateral risk; sector-narrow C2 + GNSS.",
    },
    {
        "id": "ews_jam_omnidirectional",
        "name": "Omnidirectional RF jam (perimeter wide)",
        "kinetic": False, "rf_emission": True,
        "authority_required": "Installation Commander; MARFORCYBER notify",
        "roe_class": "Non-kinetic; will affect friendly C2/Wi-Fi/GNSS in zone.",
        "notes": "Reserve for confirmed swarm / multi-vehicle threats only.",
    },
    {
        "id": "spoof_gps",
        "name": "GPS spoof (push UAS off course)",
        "kinetic": False, "rf_emission": True,
        "authority_required": "Installation Commander + EW spectrum auth",
        "roe_class": "Non-kinetic; may displace UAS into civil airspace.",
        "notes": "Effective vs nav-coupled autonomy; ineffective vs inertial-only.",
    },
    {
        "id": "request_kinetic",
        "name": "Request kinetic engagement (small-arms / SHORAD)",
        "kinetic": True, "rf_emission": False,
        "authority_required": "FOC / Range Control + SECDEF UAS rule-set",
        "roe_class": "Kinetic — last resort. Positive ID + hostile intent required.",
        "notes": "Per DoDD 3000.09 + 10 USC 130i UAS authorities.",
    },
    {
        "id": "spoof_link",
        "name": "C2 link takeover (protocol-aware)",
        "kinetic": False, "rf_emission": True,
        "authority_required": "MARFORCYBER + Title 10 cyber EXORD",
        "roe_class": "Cyber/EW hybrid; pre-coordinated mission required.",
        "notes": "Effective vs unencrypted FHSS hobbyist; not for COTS encrypted DJI.",
    },
    {
        "id": "skytracker_log",
        "name": "Track + log only (SkyTracker-style passive ID)",
        "kinetic": False, "rf_emission": False,
        "authority_required": "Watch officer",
        "roe_class": "Observe; build pattern of life for repeat overflights.",
        "notes": "Always-on baseline for installation perimeter sensors.",
    },
    {
        "id": "escalate_foc",
        "name": "Escalate to Force Operations Center (FOC)",
        "kinetic": False, "rf_emission": False,
        "authority_required": "Watch officer",
        "roe_class": "Notification + decision request.",
        "notes": "Push contact + recommendation up the chain when authority exceeds OOD.",
    },
]


def write_engagement_options() -> None:
    (DATA_DIR / "engagement_options.json").write_text(
        json.dumps(ENGAGEMENT_OPTIONS, indent=2)
    )


# ═════════════════════════════════════════════════════════════════════════════
# 7. Friendly drone fleet inventory (the "AI Visual Quantification" use case)
# ═════════════════════════════════════════════════════════════════════════════
FRIENDLY_FLEET = {
    "site": "Camp Pendleton — LOGCOM tenant area",
    "as_of": "271730ZAPR26",
    "platforms": [
        {"make": "Skydio", "model": "X10D", "role": "ISR (squad-organic)",
         "count_total": 14, "count_mission_ready": 11, "battery_pack_pct_avg": 78,
         "primary_use": "perimeter recon, building clearing overhead"},
        {"make": "Parrot", "model": "Anafi USA",
         "role": "ISR (small unit)", "count_total": 8, "count_mission_ready": 7,
         "battery_pack_pct_avg": 82,
         "primary_use": "convoy overwatch, route recon"},
        {"make": "Teal", "model": "Black Widow",
         "role": "Group 1 NDAA-compliant ISR",
         "count_total": 4, "count_mission_ready": 4, "battery_pack_pct_avg": 91,
         "primary_use": "indoor / structure sweep"},
        {"make": "AeroVironment", "model": "Switchblade 300",
         "role": "loitering munition (Group 1)",
         "count_total": 6, "count_mission_ready": 5, "battery_pack_pct_avg": 88,
         "primary_use": "stand-off precision strike (kinetic)"},
        {"make": "AeroVironment", "model": "Puma AE",
         "role": "Group 2 long-range ISR", "count_total": 2,
         "count_mission_ready": 2, "battery_pack_pct_avg": 85,
         "primary_use": "long-range reconnaissance, EO/IR"},
    ],
    "mission_load_today": "Group 1 ISR: 4 sorties planned · loitering munition: 0 (training restriction) · Puma: 1 long sortie SP+30",
    "visual_quantification_note":
        "Image-based fleet count: 39 platforms recognized in motor-pool stills "
        "(matches manifest within ±1).",
}


def write_friendly_fleet() -> None:
    (DATA_DIR / "friendly_fleet.json").write_text(
        json.dumps(FRIENDLY_FLEET, indent=2)
    )


# ═════════════════════════════════════════════════════════════════════════════
# 8. Heuristic feature extraction (numpy on each modality)
# ═════════════════════════════════════════════════════════════════════════════
def extract_rf_features(arr: np.ndarray) -> dict:
    h, w = arr.shape
    row_power = arr.mean(axis=1)
    col_power = arr.mean(axis=0)
    noise_floor = float(np.percentile(arr, 30))
    peak = float(arr.max())
    snr_est_db = float(20 * math.log10(max(1e-3, peak / max(1e-3, noise_floor))))
    median = float(np.median(col_power))
    bursts = int(np.sum(np.diff((col_power > median).astype(int)) != 0))
    hop_period_px = float(w / max(1, bursts)) if bursts else 0.0
    active_rows = int((row_power > (noise_floor + 0.05)).sum())
    active_freq_span_pct = float(active_rows / h)
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
        "burst_count": bursts,
        "hop_period_px": round(hop_period_px, 1),
        "active_freq_span_pct": round(active_freq_span_pct, 3),
        "modulation_hint": mod_hint,
    }


def extract_thermal_features(gray: np.ndarray, bboxes: list[dict]) -> dict:
    """Numpy-only blob heuristics. Returns hot-blob counts + classes."""
    classes = [b["cls"] for b in bboxes]
    n_uas = sum(1 for c in classes if "UAS" in c)
    n_person = sum(1 for c in classes if c == "person")
    n_vehicle = sum(1 for c in classes if c == "vehicle")
    n_animal = sum(1 for c in classes if "animal" in c)
    peak = int(gray.max())
    mean = float(gray.mean())
    # max bbox area as a proxy for closest contact
    max_area = 0
    for b in bboxes:
        x0, y0, x1, y1 = b["bbox"]
        max_area = max(max_area, (x1 - x0) * (y1 - y0))
    return {
        "n_uas_blobs": n_uas,
        "n_person_blobs": n_person,
        "n_vehicle_blobs": n_vehicle,
        "n_animal_blobs": n_animal,
        "peak_intensity_8bit": peak,
        "mean_intensity_8bit": round(mean, 1),
        "max_bbox_area_px": int(max_area),
    }


def extract_visual_features(sig: dict) -> dict:
    """Lightweight: report the procedural ground-truth count of drone shapes
    (in real ingestion, this is replaced with a YOLO / vision pass)."""
    kind = sig["visual_kind"]
    if kind == "swarm_specks":
        n = 6
    elif kind == "empty_sky":
        n = 0
    else:
        n = 1
    return {
        "n_drone_silhouettes": n,
        "scene_kind": kind,
        "horizon_visible": kind != "empty_sky",
    }


# ═════════════════════════════════════════════════════════════════════════════
# 9. Bayesian-style triple-fusion (deterministic baseline used as fallback &
#    pre-cache; the live demo path can swap in a multimodal LLM).
# ═════════════════════════════════════════════════════════════════════════════
def baseline_triple_fuse(sig: dict, rf_feats: dict, thm_feats: dict,
                          vis_feats: dict) -> dict:
    """Naive-Bayes-style fusion across 3 sensors → fused detection JSON.

    Each modality emits P(uas_present) and P(class | uas_present); we combine
    via the product rule (then re-normalize). This is intentionally simple
    so the UI can show the math step by step.
    """
    # Per-modality P(uas_present)
    rf_snr = rf_feats["snr_estimate_db"]
    p_rf = max(0.05, min(0.99, (rf_snr - 4) / 26.0))  # SNR 4dB→0, 30dB→1
    if rf_feats["modulation_hint"].startswith("below detection"):
        p_rf = 0.10

    p_thm = max(0.05, min(0.99, 0.30 + 0.20 * thm_feats["n_uas_blobs"]))
    if thm_feats["n_uas_blobs"] == 0:
        p_thm = 0.18

    p_vis = max(0.05, min(0.99, 0.30 + 0.18 * vis_feats["n_drone_silhouettes"]))
    if vis_feats["n_drone_silhouettes"] == 0:
        p_vis = 0.20

    # Bayesian combine assuming equal priors
    def fuse(*ps: float) -> float:
        prod = 1.0
        prod_n = 1.0
        for p in ps:
            prod *= p
            prod_n *= (1 - p)
        return prod / max(1e-9, prod + prod_n)

    fused = fuse(p_rf, p_thm, p_vis)

    # Class voting — RF is most discriminative for class
    class_guess = sig["uas_class"]  # ground truth shortcut for cache demo
    contributors = []
    if p_rf > 0.4:
        contributors.append("RF")
    if p_thm > 0.4:
        contributors.append("thermal")
    if p_vis > 0.4:
        contributors.append("visual")

    return {
        "detection_class": class_guess,
        "make_model_guess": sig["make_model"],
        "controller_signature_match": sig["controller"],
        "inferred_intent": sig["intent_hint"],
        "estimated_range_km": sig["ground_truth_range_km"],
        "estimated_alt_m": sig["ground_truth_alt_m"],
        "confidence_per_modality": {
            "rf": round(p_rf, 3),
            "thermal": round(p_thm, 3),
            "visual": round(p_vis, 3),
        },
        "fused_confidence": round(fused, 3),
        "contributing_sensors": contributors or ["none-above-threshold"],
        "fusion_method": "naive-Bayes product over 3 sensor modalities (equal prior)",
    }


# ═════════════════════════════════════════════════════════════════════════════
# 10. Engagement-decision heuristic (used as deterministic fallback for the
#     `chat_json` graded options call).
# ═════════════════════════════════════════════════════════════════════════════
def baseline_engagement_decision(fused: dict, sig: dict) -> dict:
    """Pick a recommended option from ENGAGEMENT_OPTIONS using simple ROE rules."""
    cls = fused["detection_class"]
    intent = fused["inferred_intent"]
    rng_km = fused["estimated_range_km"]
    confidence = fused["fused_confidence"]

    options_graded: list[dict] = []
    for opt in ENGAGEMENT_OPTIONS:
        score = 0.0
        rationale_bits = []
        if cls == "ambient":
            score = 0.95 if opt["id"] in {"monitor", "skytracker_log"} else 0.05
            rationale_bits.append("ambient — passive only")
        elif cls == "swarm":
            if opt["id"] == "ews_jam_omnidirectional":
                score = 0.85
                rationale_bits.append("swarm warrants wide jam")
            elif opt["id"] == "escalate_foc":
                score = 0.80
                rationale_bits.append("authority above OOD required")
            elif opt["id"] == "request_kinetic":
                score = 0.40
                rationale_bits.append("kinetic possible but ROE strict")
            else:
                score = 0.20
        elif intent == "strike":
            if opt["id"] == "ews_jam_sector":
                score = 0.80
                rationale_bits.append("non-kinetic first vs strike intent")
            elif opt["id"] == "request_kinetic":
                score = 0.78
                rationale_bits.append("kinetic if non-kinetic fails")
            elif opt["id"] == "escalate_foc":
                score = 0.72
            else:
                score = 0.15
        elif intent == "recon":
            if opt["id"] == "ews_jam_sector":
                score = 0.78
                rationale_bits.append("sector jam pushes recon off-site")
            elif opt["id"] == "spoof_gps":
                score = 0.62
                rationale_bits.append("displace via GPS spoof")
            elif opt["id"] == "skytracker_log":
                score = 0.55
                rationale_bits.append("baseline logging continues")
            else:
                score = 0.20
        elif intent == "decoy":
            if opt["id"] == "skytracker_log":
                score = 0.72
                rationale_bits.append("track-log to find the real threat")
            elif opt["id"] == "ews_jam_sector":
                score = 0.62
            elif opt["id"] == "spoof_link":
                score = 0.55
            else:
                score = 0.18
        else:
            score = 0.20

        score *= (0.4 + 0.6 * confidence)  # damp by fused confidence
        options_graded.append({
            "id": opt["id"],
            "name": opt["name"],
            "tag": ("KINETIC" if opt["kinetic"]
                     else "NON-KINETIC" if opt["rf_emission"]
                     else "PASSIVE"),
            "authority_required": opt["authority_required"],
            "score": round(score, 3),
            "rationale": "; ".join(rationale_bits) or "standard fit for context",
        })

    options_graded.sort(key=lambda o: o["score"], reverse=True)
    recommended = options_graded[0]
    return {
        "recommended_option_id": recommended["id"],
        "recommended_option_name": recommended["name"],
        "recommended_tag": recommended["tag"],
        "recommended_rationale": recommended["rationale"],
        "options_graded": options_graded,
        "ROE_floor": "Watch officer (OOD)",
        "ROE_ceiling": "FOC + SECDEF UAS rule-set (kinetic only)",
    }


# ═════════════════════════════════════════════════════════════════════════════
# 11. Hero "UAS Encounter Brief" — full SITREP ingesting all three sensor takes
# ═════════════════════════════════════════════════════════════════════════════
SCENARIO_CONTEXT = {
    "site": "Camp Pendleton — Building 22 perimeter (LOGCOM tenant area)",
    "dtg": "271730ZAPR26",
    "wind": "210/06 KT",
    "ceiling": "BKN 4500",
    "civil_airspace_distance_nm": 0.4,
    "friendly_air_active": "negative",
    "operator": "OOD watch — DRONE-DOMINANCE console",
}


SYSTEM_HERO = (
    "You are DRONE-DOMINANCE — a USMC LOGCOM Installation Force Protection "
    "watch-officer assistant, on-prem. The OOD has just received a triple-"
    "fused UAS contact (RF spectrogram analysis + thermal IR detection + "
    "visual EO confirmation), an ROE-graded engagement option ladder, and "
    "the site context. Produce a 'UAS ENCOUNTER BRIEF' formatted exactly as:\n\n"
    "(U) BLUF — one sentence covering class, intent, fused confidence, COA.\n\n"
    "(U) MULTI-SENSOR FUSION\n"
    "  · RF — <one line: modulation, controller signature, p(uas)>\n"
    "  · Thermal IR — <one line: blob count, classes, p(uas)>\n"
    "  · Visual EO — <one line: silhouette count, scene context, p(uas)>\n"
    "  · Fused confidence — <number> · sensors contributing — <list>\n\n"
    "(U) THREAT ASSESSMENT — <2 sentences, intent + reasoning>\n\n"
    "(U) ENGAGEMENT OPTIONS (top 3 from the ROE ladder)\n"
    "  - [PASSIVE/NON-KINETIC/KINETIC] <name> — authority: <auth>\n"
    "  - [...]\n"
    "  - [...]\n\n"
    "(U) RECOMMENDED COA — <option name> · authority: <auth> · 1-line "
    "justification.\n\n"
    "(U) AUTHORITIES — Cite only from this short list when relevant: "
    "10 USC 130i (UAS authorities), DoDD 3000.09, JCO-CUAS Operational "
    "Concept, JP 3-01 Ch IV, MARADMIN 131/26.\n\n"
    "Hard rules: USE ONLY the data provided. Do NOT name specific deployed "
    "USMC EW systems. Do NOT assert legal authority not listed above. Total "
    "length under ~320 words."
)


def _fallback_brief(payload: dict) -> str:
    fused = payload["triple_fusion"]
    decision = payload["engagement_decision"]
    site = payload["site_context"]["site"]
    dtg = payload["site_context"]["dtg"]
    cls = fused["detection_class"]
    intent = fused["inferred_intent"]
    fc = fused["fused_confidence"]
    rng_km = fused["estimated_range_km"]
    p_rf = fused["confidence_per_modality"]["rf"]
    p_thm = fused["confidence_per_modality"]["thermal"]
    p_vis = fused["confidence_per_modality"]["visual"]
    contributors = ", ".join(fused["contributing_sensors"])
    top3 = decision["options_graded"][:3]
    if cls == "ambient":
        return (
            f"(U) BLUF — No UAS contact above triple-fusion threshold at "
            f"{site} ({dtg}). Continue passive watch.\n\n"
            f"(U) MULTI-SENSOR FUSION\n"
            f"  · RF — ambient WiFi APs only · p={p_rf}\n"
            f"  · Thermal IR — bird/animal heat signatures, no UAS blobs · p={p_thm}\n"
            f"  · Visual EO — empty sky, no silhouettes · p={p_vis}\n"
            f"  · Fused confidence — {fc} · sensors contributing — {contributors}\n\n"
            f"(U) THREAT ASSESSMENT — No threat. Triple-fusion below action "
            f"threshold; baseline RF environment consistent with installation.\n\n"
            f"(U) ENGAGEMENT OPTIONS (top 3 from the ROE ladder)\n"
            + "\n".join(f"  - [{o['tag']}] {o['name']} — authority: {o['authority_required']}"
                        for o in top3) + "\n\n"
            f"(U) RECOMMENDED COA — {decision['recommended_option_name']} · "
            f"authority: Watch officer · no engagement warranted.\n\n"
            f"(U) AUTHORITIES — n/a; observe-only posture under JP 3-01 Ch IV."
        )
    return (
        f"(U) BLUF — Probable {cls} at ~{rng_km} km, intent {intent}; "
        f"fused confidence {fc}. Recommend {decision['recommended_option_name']}.\n\n"
        f"(U) MULTI-SENSOR FUSION\n"
        f"  · RF — {payload['rf_features']['modulation_hint']} · "
        f"controller={fused['controller_signature_match']} · p={p_rf}\n"
        f"  · Thermal IR — {payload['thermal_features']['n_uas_blobs']} UAS blob(s), "
        f"peak {payload['thermal_features']['peak_intensity_8bit']}/255 · p={p_thm}\n"
        f"  · Visual EO — {payload['visual_features']['n_drone_silhouettes']} "
        f"silhouette(s) recognized · p={p_vis}\n"
        f"  · Fused confidence — {fc} · sensors contributing — {contributors}\n\n"
        f"(U) THREAT ASSESSMENT — {intent.title()} intent inferred from "
        f"signature, approach corridor, and bbox count. Triple-fusion clears "
        f"the action threshold (>0.55).\n\n"
        f"(U) ENGAGEMENT OPTIONS (top 3 from the ROE ladder)\n"
        + "\n".join(f"  - [{o['tag']}] {o['name']} — authority: {o['authority_required']}"
                    for o in top3) + "\n\n"
        f"(U) RECOMMENDED COA — {decision['recommended_option_name']} · "
        f"authority: {top3[0]['authority_required']} · {decision['recommended_rationale']}.\n\n"
        f"(U) AUTHORITIES — 10 USC 130i UAS authorities; JP 3-01 Ch IV; "
        f"JCO-CUAS Operational Concept."
    )


def _scenario_payload(sig: dict, rf_feats: dict, thm_feats: dict,
                      vis_feats: dict, fused: dict, decision: dict) -> dict:
    return {
        "scenario_id": sig["id"],
        "scenario_title": sig["title"],
        "ground_truth": {
            "uas_class": sig["uas_class"],
            "make_model": sig["make_model"],
            "controller": sig["controller"],
            "band_ghz": sig["band_ghz"],
            "estimated_range_km": sig["ground_truth_range_km"],
            "estimated_alt_m": sig["ground_truth_alt_m"],
            "intent_hint": sig["intent_hint"],
        },
        "rf_features": rf_feats,
        "thermal_features": thm_feats,
        "visual_features": vis_feats,
        "triple_fusion": fused,
        "engagement_decision": decision,
        "site_context": SCENARIO_CONTEXT,
    }


# ═════════════════════════════════════════════════════════════════════════════
# 12. Orchestrator — generate everything + pre-compute hero briefs
# ═════════════════════════════════════════════════════════════════════════════
def write_scenarios_manifest(rng: random.Random) -> list[dict]:
    """Build the master manifest + run all 6 scenarios through synth+fusion."""
    manifest: list[dict] = []
    payloads: dict[str, dict] = {}

    for sig in SCENARIOS:
        # RF
        rf_arr = synthesize_spectrogram(sig, rng)
        rf_png = SPECTRA_DIR / f"{sig['id']}.png"
        rf_npy = SPECTRA_DIR / f"{sig['id']}.npy"
        render_spectrogram_png(rf_arr, sig, rf_png)
        np.save(rf_npy, rf_arr.astype(np.float32))

        # Thermal
        thm_gray, thm_bboxes = synthesize_thermal(sig, rng)
        thm_png = THERMAL_DIR / f"{sig['id']}.png"
        thm_npy = THERMAL_DIR / f"{sig['id']}.npy"
        render_thermal_png(thm_gray, thm_bboxes, sig, thm_png)
        np.save(thm_npy, thm_gray)
        # also dump bboxes as JSON sidecar
        (THERMAL_DIR / f"{sig['id']}.bboxes.json").write_text(
            json.dumps(thm_bboxes, indent=2)
        )

        # Visual
        vis_png = VISUAL_DIR / f"{sig['id']}.png"
        render_visual_png(sig, rng, vis_png)

        # Features + fusion
        rf_feats = extract_rf_features(rf_arr)
        thm_feats = extract_thermal_features(thm_gray, thm_bboxes)
        vis_feats = extract_visual_features(sig)
        fused = baseline_triple_fuse(sig, rf_feats, thm_feats, vis_feats)
        decision = baseline_engagement_decision(fused, sig)
        payload = _scenario_payload(sig, rf_feats, thm_feats, vis_feats,
                                     fused, decision)
        payloads[sig["id"]] = payload

        manifest.append({
            "id": sig["id"],
            "title": sig["title"],
            "uas_class": sig["uas_class"],
            "make_model": sig["make_model"],
            "controller": sig["controller"],
            "band_ghz": sig["band_ghz"],
            "ground_truth_range_km": sig["ground_truth_range_km"],
            "ground_truth_alt_m": sig["ground_truth_alt_m"],
            "intent_hint": sig["intent_hint"],
            "rf_png": f"sample_spectra/{sig['id']}.png",
            "rf_npy": f"sample_spectra/{sig['id']}.npy",
            "thermal_png": f"sample_thermal/{sig['id']}.png",
            "thermal_npy": f"sample_thermal/{sig['id']}.npy",
            "thermal_bboxes": f"sample_thermal/{sig['id']}.bboxes.json",
            "visual_png": f"sample_visual/{sig['id']}.png",
        })

    (DATA_DIR / "scenarios.json").write_text(json.dumps(manifest, indent=2))
    (DATA_DIR / "_payloads_cache.json").write_text(json.dumps(payloads, indent=2))
    return manifest


def _precompute_briefs(rng: random.Random) -> None:
    """Pre-compute hero "UAS Encounter Brief" for all 6 scenarios.

    Cache-first per AGENT_BRIEF_V2 §A. Falls back to deterministic brief if
    the LLM client isn't available or every model in the chain fails.
    """
    payloads = json.loads((DATA_DIR / "_payloads_cache.json").read_text())
    cached: dict[str, dict] = {}

    chat_fn = None
    try:
        sys.path.insert(0, str(APP_DIR.parent.parent))
        from shared.kamiwaza_client import chat as _chat  # noqa: WPS433
        chat_fn = _chat
    except Exception as e:  # noqa: BLE001
        print(f"[precompute] LLM client unavailable, using fallback briefs: {e}")

    for sig in SCENARIOS:
        payload = payloads[sig["id"]]
        text = ""
        if chat_fn:
            for hero_model in ("gpt-5.4", "gpt-5.4-mini", "gpt-4o-mini", None):
                try:
                    print(f"[precompute] {sig['id']} (model={hero_model or 'chain-default'}) ...")
                    user = (
                        f"Scenario:\n{json.dumps(payload, indent=2)}\n\n"
                        f"Write the UAS ENCOUNTER BRIEF now."
                    )
                    text = chat_fn(
                        [
                            {"role": "system", "content": SYSTEM_HERO},
                            {"role": "user", "content": user},
                        ],
                        model=hero_model,
                        temperature=0.4,
                        max_tokens=700,
                    )
                    if text and text.strip():
                        break
                except Exception as e:  # noqa: BLE001
                    print(f"[precompute] {hero_model} failed: {e}")
                    continue
        if not text:
            text = _fallback_brief(payload)

        cached[sig["id"]] = {
            "title": sig["title"],
            "ground_truth": payload["ground_truth"],
            "rf_features": payload["rf_features"],
            "thermal_features": payload["thermal_features"],
            "visual_features": payload["visual_features"],
            "triple_fusion": payload["triple_fusion"],
            "engagement_decision": payload["engagement_decision"],
            "encounter_brief": text,
        }

    out = DATA_DIR / "cached_briefs.json"
    out.write_text(json.dumps(cached, indent=2))
    print(f"[precompute] wrote {out}")


def write_aar_frames() -> None:
    AAR_DIR.mkdir(parents=True, exist_ok=True)
    for f in AAR_FRAMES:
        synthesize_aar_frame(f, AAR_DIR / f"{f['id']}.png")
    (DATA_DIR / "aar_frames.json").write_text(json.dumps(AAR_FRAMES, indent=2))


def main() -> None:
    rng = random.Random(SEED)
    for d in (DATA_DIR, SPECTRA_DIR, THERMAL_DIR, VISUAL_DIR, AAR_DIR):
        d.mkdir(parents=True, exist_ok=True)

    write_rf_id_db()
    write_engagement_options()
    write_friendly_fleet()
    write_aar_frames()
    print(f"Synthesizing {len(SCENARIOS)} threat scenarios across 3 sensor modalities...")
    write_scenarios_manifest(rng)
    print("Manifests + features + fusion + decision written.")


if __name__ == "__main__":
    main()
    if os.getenv("SKIP_PRECOMPUTE") != "1":
        _precompute_briefs(random.Random(SEED))
