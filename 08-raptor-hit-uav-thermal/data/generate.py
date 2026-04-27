"""Synthetic 30-frame thermal scenario for RAPTOR (Bucket B template).

Produces 30 IR frames (640x512, grayscale) simulating a small UAV's thermal
camera over a Marine installation perimeter at 0300. Hot blobs represent
persons, vehicles, fires, generators, and exhaust plumes; a cooler background
gradient simulates ambient ground. Reproducible via SEED=1776.

Outputs:
  data/frames/frame_000.png ... frame_029.png   (8-bit grayscale thermal)
  data/frames_color/frame_000.png ...           (inferno-LUT pseudo-color)
  data/ground_truth.json                        (per-frame box + class labels)
  data/mission.json                             (scenario summary)

Swap in real data (Bucket B):
  Drop real thermal frames into data/frames/ as frame_000.png, frame_001.png,
  ... (8-bit grayscale PNG/TIFF). HIT-UAV (High-altitude Infrared Thermal
  Dataset for UAV-based Object Detection) ingests unchanged — same naming
  scheme, same pipeline. Re-run this script only if you also want fresh
  frames_color/, ground_truth.json, and mission.json regenerated; otherwise
  just refresh the inferno-LUT block (cv2.applyColorMap / COLORMAP_INFERNO)
  over your new frames.
"""
from __future__ import annotations

import json
import math
import random
from pathlib import Path

import cv2
import numpy as np


SEED = 1776
W, H = 640, 512
N_FRAMES = 30
DATA_DIR = Path(__file__).parent
FRAMES_DIR = DATA_DIR / "frames"
COLOR_DIR = DATA_DIR / "frames_color"


# Ground-truth scenario:
#   t=0..7   : two dismounts (persons) approach a parked vehicle from the
#              tree-line; vehicle is cold (long-parked).
#   t=8..14  : a third person joins, vehicle engine starts (hood + exhaust warm).
#   t=15..22 : vehicle drives off-frame east; new heat source appears at FOB
#              perimeter — a small fire at a barrel (potential signal fire).
#   t=23..29 : generator at LZ kicks on; persons disperse to defensive posture.

# Each "track" describes a hot object with a class, a function-of-t intensity
# (0..1) and a function-of-t (cx, cy, rx, ry) box. Returns None if not present.

def _person_track(start: int, end: int, x0: float, y0: float, x1: float, y1: float):
    def fn(t: int):
        if t < start or t > end:
            return None
        u = (t - start) / max(1, end - start)
        cx = x0 + u * (x1 - x0)
        cy = y0 + u * (y1 - y0)
        rx, ry = 5, 11
        intensity = 0.78 + 0.06 * math.sin(t * 0.9)
        return ("person", cx, cy, rx, ry, intensity)
    return fn


def _vehicle_track(start: int, end: int, path_fn, hot_after: int):
    def fn(t: int):
        if t < start or t > end:
            return None
        cx, cy = path_fn(t)
        rx, ry = 22, 14
        # cold while idle, then engine warms
        if t < hot_after:
            intensity = 0.32
        else:
            ramp = min(1.0, (t - hot_after) / 4)
            intensity = 0.32 + 0.55 * ramp
        return ("vehicle", cx, cy, rx, ry, intensity)
    return fn


def _fire_track(start: int, end: int, x: float, y: float):
    def fn(t: int):
        if t < start or t > end:
            return None
        flicker = 0.85 + 0.12 * math.sin(t * 2.3) + 0.05 * math.cos(t * 4.1)
        return ("fire", x, y, 9, 9, min(1.0, flicker))
    return fn


def _generator_track(start: int, end: int, x: float, y: float):
    def fn(t: int):
        if t < start or t > end:
            return None
        # plus a small hot exhaust plume drifting up
        pulse = 0.72 + 0.05 * math.sin(t * 1.4)
        return ("generator", x, y, 14, 10, pulse)
    return fn


def _exhaust_plume_track(start: int, end: int, x: float, y: float):
    def fn(t: int):
        if t < start or t > end:
            return None
        # rises and dissipates each frame
        u = (t - start) / max(1, end - start)
        cy = y - 14 - 6 * (t % 3)
        intensity = 0.55 - 0.1 * u
        return ("exhaust", x, cy, 7, 12, max(0.4, intensity))
    return fn


def _vehicle_path(t: int):
    # parked t<15, then drives east and slightly south
    if t < 15:
        return (310.0, 300.0)
    u = min(1.0, (t - 15) / 7)
    return (310.0 + u * 320.0, 300.0 + u * 30.0)


TRACKS = [
    # Phase 1: two dismounts approach from north tree-line
    _person_track(0, 14, 120, 90, 280, 280),
    _person_track(0, 14, 150, 90, 295, 290),
    # Phase 2: third dismount joins from west
    _person_track(8, 22, 60, 220, 270, 295),
    # Vehicle (cold then warm then drives off-frame)
    _vehicle_track(0, 22, _vehicle_path, hot_after=10),
    # Vehicle exhaust plume (briefly visible after engine start)
    _exhaust_plume_track(11, 16, 332, 296),
    # Phase 3: signal fire at barrel
    _fire_track(15, 29, 480, 180),
    # Phase 4: generator at LZ kicks on
    _generator_track(20, 29, 95, 410),
    # Phase 4: dispersing persons to defensive posture
    _person_track(23, 29, 250, 200, 200, 130),
    _person_track(23, 29, 380, 220, 460, 320),
    _person_track(23, 29, 420, 280, 510, 350),
]


PHASE_NARRATIVES = {
    (0, 7): "Two dismounts emerge from north tree-line moving south toward parked sedan; vehicle thermally cold (long-parked).",
    (8, 14): "Third dismount joins from west; vehicle hood + exhaust warming — engine just started.",
    (15, 22): "Vehicle departs east off-frame; small fire ignites at perimeter barrel (possible signal/marker).",
    (23, 29): "Generator at LZ pad spins up; remaining personnel disperse to defensive arc.",
}


def _bg_gradient(rng: random.Random) -> np.ndarray:
    """Cool background gradient — ground at ~15-25C, slight slope, plus noise."""
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    base = 28 + 0.04 * yy + 0.015 * xx  # subtle slope (warmer south + east)
    # ridge / treeline darker (cooler) along top
    treeline = np.exp(-((yy - 25) ** 2) / 240) * 8
    base -= treeline
    # speckle noise
    noise = np.array(
        [[rng.gauss(0, 2.5) for _ in range(W)] for _ in range(H)],
        dtype=np.float32,
    )
    return np.clip(base + noise, 0, 255)


def _draw_blob(img: np.ndarray, cx: float, cy: float, rx: float, ry: float, intensity: float) -> None:
    """Add a Gaussian hot blob centered at (cx,cy) with radii rx,ry. intensity 0..1."""
    # Build a small bounding box
    pad = int(max(rx, ry) * 3)
    x0 = max(0, int(cx - pad))
    x1 = min(W, int(cx + pad))
    y0 = max(0, int(cy - pad))
    y1 = min(H, int(cy + pad))
    if x1 <= x0 or y1 <= y0:
        return
    ys, xs = np.mgrid[y0:y1, x0:x1].astype(np.float32)
    g = np.exp(-(((xs - cx) / rx) ** 2 + ((ys - cy) / ry) ** 2))
    add = (intensity * 220.0) * g
    region = img[y0:y1, x0:x1].astype(np.float32) + add
    img[y0:y1, x0:x1] = np.clip(region, 0, 255).astype(img.dtype)


def _phase(t: int) -> str:
    for (a, b), narrative in PHASE_NARRATIVES.items():
        if a <= t <= b:
            return narrative
    return ""


def main() -> None:
    rng = random.Random(SEED)
    np.random.seed(SEED)
    FRAMES_DIR.mkdir(parents=True, exist_ok=True)
    COLOR_DIR.mkdir(parents=True, exist_ok=True)

    ground_truth = []
    for t in range(N_FRAMES):
        bg = _bg_gradient(rng)
        gray = bg.copy().astype(np.uint8)

        boxes = []
        for track in TRACKS:
            obj = track(t)
            if obj is None:
                continue
            cls, cx, cy, rx, ry, intensity = obj
            _draw_blob(gray, cx, cy, rx, ry, intensity)
            # bbox xyxy
            x0 = max(0, int(cx - rx * 1.4))
            y0 = max(0, int(cy - ry * 1.4))
            x1 = min(W - 1, int(cx + rx * 1.4))
            y1 = min(H - 1, int(cy + ry * 1.4))
            boxes.append({
                "class": cls,
                "cx": round(cx, 1),
                "cy": round(cy, 1),
                "bbox": [x0, y0, x1, y1],
                "intensity": round(float(intensity), 3),
            })

        # write grayscale
        cv2.imwrite(str(FRAMES_DIR / f"frame_{t:03d}.png"), gray)

        # pseudo-color (inferno LUT)
        color = cv2.applyColorMap(gray, cv2.COLORMAP_INFERNO)
        cv2.imwrite(str(COLOR_DIR / f"frame_{t:03d}.png"), color)

        ground_truth.append({
            "frame": t,
            "timestamp_utc": f"2026-04-30T03:{(t * 4) // 60:02d}:{(t * 4) % 60:02d}Z",
            "phase_narrative": _phase(t),
            "n_objects": len(boxes),
            "objects": boxes,
        })

    (DATA_DIR / "ground_truth.json").write_text(json.dumps(ground_truth, indent=2))

    mission = {
        "mission_id": "RAPTOR-DEMO-0001",
        "platform": "RQ-21A Blackjack (Group 3 UAV)",
        "sensor": "MX-10 EO/IR turret, LWIR 640x512 @ 30Hz",
        "altitude_msl_ft": 4500,
        "altitude_agl_ft": 1800,
        "site": "MCB Quantico — northern perimeter sector NPC-7 (synthetic)",
        "tasking": "Persistent ISR over reported intrusion vector; report any FOMO (forces of military observation) activity, vehicle ingress/egress, or anomalous heat sources.",
        "start_time_utc": "2026-04-30T03:00:00Z",
        "duration_s": N_FRAMES * 4,
        "frame_rate_demo_hz": 0.25,
        "ground_truth_phases": [
            {"window_s": [0, 28], "narrative": PHASE_NARRATIVES[(0, 7)]},
            {"window_s": [32, 56], "narrative": PHASE_NARRATIVES[(8, 14)]},
            {"window_s": [60, 88], "narrative": PHASE_NARRATIVES[(15, 22)]},
            {"window_s": [92, 116], "narrative": PHASE_NARRATIVES[(23, 29)]},
        ],
        "real_dataset_provenance": {
            "name": "HIT-UAV: A High-altitude Infrared Thermal Dataset for UAV-based Object Detection",
            "size_mb": 775,
            "team": "Truffle",
            "note": "Synthetic frames generated here for hackathon demo; identical pipeline (grayscale 8-bit + bbox JSON) ingests HIT-UAV unchanged.",
        },
    }
    (DATA_DIR / "mission.json").write_text(json.dumps(mission, indent=2))

    print(f"Wrote {N_FRAMES} frames to {FRAMES_DIR} and {COLOR_DIR}")
    print(f"Wrote ground truth: {DATA_DIR / 'ground_truth.json'}")
    print(f"Wrote mission scenario: {DATA_DIR / 'mission.json'}")


if __name__ == "__main__":
    main()
