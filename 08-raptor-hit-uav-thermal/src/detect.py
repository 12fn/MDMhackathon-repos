# RAPTOR — drone IR INTREP from multi-frame thermal window
# Part of the MDM 2026 Hackathon Templates (https://github.com/12fn/MDMhackathon-repos)
# MIT licensed. Built on GAI (Government Acquisitions, Inc.) + Kamiwaza (https://www.kamiwaza.ai/).
"""Heuristic blob detection on synthetic thermal frames.

We avoid pulling YOLO weights for the demo; a thresholded contour pass on the
grayscale image gives us tight bounding boxes around hot signatures, which is
more than enough to feed the vision-language model. The same module would
swap to ultralytics YOLO-tiny in a production deploy by replacing detect_blobs().
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import List

import cv2
import numpy as np


@dataclass
class Detection:
    cls: str
    conf: float
    bbox: list[int]   # [x0, y0, x1, y1]
    cx: float
    cy: float
    area_px: int
    mean_intensity: float
    peak_intensity: float
    aspect_ratio: float

    def to_dict(self) -> dict:
        d = asdict(self)
        d["bbox"] = [int(x) for x in self.bbox]
        return d


def _classify(area: int, aspect: float, mean_i: float, peak_i: float) -> tuple[str, float]:
    """Cheap heuristic class assignment from blob shape + heat.

    Uses both mean and peak intensity (the synthetic Gaussian blobs spread heat
    over their footprint, so peak distinguishes fire from a person better than
    mean).
    Returns (class, confidence in 0..1).
    """
    very_hot = peak_i > 200
    hot = peak_i > 170
    warm = mean_i > 70 or peak_i > 130

    # fire: very hot peak, small-ish, roughly round
    if very_hot and 60 <= area <= 700 and 0.55 <= aspect <= 1.8:
        return "fire", 0.87

    # generator: warm, larger blocky thermal signature
    if warm and area > 700 and 0.9 <= aspect <= 2.2:
        return "generator", 0.76

    # vehicle (warm/hot, large rectangular blob)
    if warm and area > 700:
        return "vehicle", 0.83 if hot else 0.72

    # person: small warm vertical-ish blob (typical area 200-500)
    if warm and 150 <= area <= 700 and aspect < 1.5:
        return "person", 0.79

    # exhaust plume: small + cooler (low peak), tall thin
    if warm and aspect < 0.5 and area < 200:
        return "exhaust_plume", 0.66

    # parked / cold vehicle: rectangular elongated blob even without much heat
    if area > 250 and 1.4 <= aspect <= 3.0:
        return "vehicle_cold", 0.61

    # cold-but-visible vehicle (long-parked, residual heat)
    if area > 700:
        return "vehicle_cold", 0.57

    return "unknown_heat_source", 0.45


def detect_blobs(gray: np.ndarray, *, min_area: int = 35) -> List[Detection]:
    """Return list of Detection objects for hot blobs in a grayscale frame."""
    # Adaptive bias above background — robust against the gradient we synthesized
    blurred = cv2.GaussianBlur(gray, (11, 11), 0)
    bg = cv2.GaussianBlur(gray, (101, 101), 0).astype(np.int16)
    excess = np.clip(blurred.astype(np.int16) - bg, 0, 255).astype(np.uint8)
    _, mask = cv2.threshold(excess, 22, 255, cv2.THRESH_BINARY)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((7, 7), np.uint8))

    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    out: List[Detection] = []
    for c in contours:
        area = int(cv2.contourArea(c))
        if area < min_area:
            continue
        x, y, w, h = cv2.boundingRect(c)
        roi = gray[y:y + h, x:x + w]
        mean_i = float(roi.mean())
        peak_i = float(roi.max())
        aspect = w / max(1, h)
        cls, conf = _classify(area, aspect, mean_i, peak_i)
        out.append(Detection(
            cls=cls,
            conf=conf,
            bbox=[int(x), int(y), int(x + w), int(y + h)],
            cx=float(x + w / 2),
            cy=float(y + h / 2),
            area_px=area,
            mean_intensity=round(mean_i, 1),
            peak_intensity=round(peak_i, 1),
            aspect_ratio=round(aspect, 2),
        ))

    out.sort(key=lambda d: -d.conf)
    return out


def annotate(color_bgr: np.ndarray, dets: List[Detection]) -> np.ndarray:
    """Draw bounding boxes + labels on a pseudo-color frame."""
    img = color_bgr.copy()
    palette = {
        "person": (0, 255, 167),       # neon green
        "vehicle": (0, 187, 122),      # kamiwaza green
        "vehicle_cold": (180, 200, 90),
        "fire": (0, 80, 255),          # red-orange (BGR)
        "generator": (255, 180, 0),    # cyan-ish
        "exhaust_plume": (220, 220, 220),
        "unknown_heat_source": (160, 160, 160),
    }
    for d in dets:
        x0, y0, x1, y1 = d.bbox
        col = palette.get(d.cls, (255, 255, 255))
        cv2.rectangle(img, (x0, y0), (x1, y1), col, 2)
        label = f"{d.cls} {int(d.conf * 100)}%"
        (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.45, 1)
        cv2.rectangle(img, (x0, max(0, y0 - th - 6)), (x0 + tw + 6, y0), col, -1)
        cv2.putText(img, label, (x0 + 3, y0 - 4),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.45, (10, 10, 10), 1, cv2.LINE_AA)
    return img
