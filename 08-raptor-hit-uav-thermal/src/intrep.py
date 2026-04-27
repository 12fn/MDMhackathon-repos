# RAPTOR — drone IR INTREP from multi-frame thermal window
# Part of the MDM 2026 Hackathon Templates (https://github.com/12fn/MDMhackathon-repos)
# MIT licensed. Built on GAI (Government Acquisitions, Inc.) + Kamiwaza (https://www.kamiwaza.ai/).
"""Generate a 4-paragraph mission INTREP from the current + prior thermal frames.

Hero AI call: a vision-language model reads the current pseudo-color thermal
frame plus up to 5 prior frames (provided as base64 image_url entries) and the
detection JSON, then writes an INTREP (intelligence report) plus structured
JSON with confidence indicators and ISR collection refinements.
"""
from __future__ import annotations

import base64
import json
import os
import sys
from pathlib import Path
from typing import List

import cv2
import numpy as np

# allow `python -m src.intrep` and direct execution from streamlit
# /apps/08-raptor/src/intrep.py → repo root is parents[3]
ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from shared.kamiwaza_client import chat  # noqa: E402


HERO_MODEL = "gpt-4o"  # vision-capable; passed as API model param to shared client
SYSTEM_PROMPT = """You are RAPTOR, an on-prem multi-step vision-language ISR
analyst supporting USMC LOGCOM Installation Incident Response. You read
LWIR thermal frames captured by a Group 3 UAV over a Marine Corps installation
perimeter at night. You produce concise, professionally-toned mission
intelligence reports (INTREPs) that an E-5 watchstander or COC OOD can act on
in under 30 seconds.

Hard rules:
- Reference specific bounding-box detections by class + count.
- Never fabricate sensor specs, locations, or units; use only what is provided.
- Distinguish observed signatures (high confidence) from inferred activity
  (medium / low confidence).
- Always end the prose INTREP with a 'PIR collection refinements' bullet list:
  what should the UAV do next.
- Output the INTREP as Markdown with these section headers exactly:
    ## SITREP / OBSERVED SIGNATURES
    ## PATTERN OF LIFE / TREND
    ## ASSESSED ACTIVITY (MEDIUM CONFIDENCE)
    ## RECOMMENDED ACTIONS & PIR REFINEMENT
"""


def _img_to_data_url(bgr: np.ndarray) -> str:
    ok, buf = cv2.imencode(".png", bgr)
    if not ok:
        raise RuntimeError("Failed to encode frame as PNG")
    b64 = base64.b64encode(buf.tobytes()).decode("ascii")
    return f"data:image/png;base64,{b64}"


def _summarize_dets(dets_per_frame: list[list[dict]]) -> str:
    """Compact text summary of detections across the recent frame window."""
    lines = []
    for i, dets in enumerate(dets_per_frame):
        counts: dict[str, int] = {}
        for d in dets:
            counts[d["cls"]] = counts.get(d["cls"], 0) + 1
        if counts:
            counts_str = ", ".join(f"{n} {c}" for c, n in counts.items())
        else:
            counts_str = "no detections"
        lines.append(f"  frame T-{len(dets_per_frame) - 1 - i}: {counts_str}")
    return "\n".join(lines)


def generate_intrep(
    current_color_bgr: np.ndarray,
    prior_color_bgrs: List[np.ndarray],
    current_dets: list[dict],
    prior_dets: list[list[dict]],
    mission_meta: dict,
    *,
    use_vision: bool = True,
) -> dict:
    """Generate INTREP. Returns {'markdown': str, 'json': dict, 'model': str, 'used_vision': bool}.

    Falls back to text-only mode if the vision call fails (lets the demo still run
    on a model that doesn't accept image_url).
    """
    # Cap to last 5 prior frames per spec
    prior_color_bgrs = prior_color_bgrs[-5:]
    prior_dets = prior_dets[-5:]

    det_summary = _summarize_dets(prior_dets + [current_dets])
    user_text = (
        f"Mission: {mission_meta.get('mission_id')}\n"
        f"Platform: {mission_meta.get('platform')}\n"
        f"Sensor: {mission_meta.get('sensor')}\n"
        f"Site: {mission_meta.get('site')}\n"
        f"Tasking: {mission_meta.get('tasking')}\n\n"
        f"Detection summary across the recent frame window (T-N indicates frames "
        f"prior to current):\n{det_summary}\n\n"
        f"Current-frame detection JSON: {json.dumps(current_dets)}\n\n"
        "Write the INTREP per the system rules. Then on a separate line emit a "
        "fenced ```json``` block matching this schema:\n"
        '{ "intrep_id": str, "dtg": str, "threat_level": "LOW|MEDIUM|HIGH", '
        '"observed_signatures": [{"class": str, "count": int, "confidence": '
        '"LOW|MEDIUM|HIGH"}], "assessed_activity": str, "recommended_actions": '
        '[str], "pir_refinements": [str] }'
    )

    used_vision = False
    markdown = ""
    if use_vision:
        # Build vision-mode message: text + image_url(s)
        content: list[dict] = [{"type": "text", "text": user_text}]
        for bgr in prior_color_bgrs:
            content.append({
                "type": "image_url",
                "image_url": {"url": _img_to_data_url(bgr), "detail": "low"},
            })
        content.append({
            "type": "image_url",
            "image_url": {"url": _img_to_data_url(current_color_bgr), "detail": "high"},
        })
        try:
            markdown = chat(
                [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": content},
                ],
                model=HERO_MODEL,
                temperature=0.3,
                max_tokens=900,
            )
            used_vision = True
        except Exception as e:  # noqa: BLE001
            print(f"[RAPTOR] vision call failed, falling back to text-only: {e}")
            used_vision = False

    if not used_vision:
        markdown = chat(
            [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_text},
            ],
            temperature=0.3,
            max_tokens=900,
        )

    # try to extract trailing JSON block
    payload = _extract_trailing_json(markdown)
    return {
        "markdown": markdown,
        "json": payload,
        "model": HERO_MODEL if used_vision else "text-fallback",
        "used_vision": used_vision,
    }


def _extract_trailing_json(md: str) -> dict:
    import re
    blocks = re.findall(r"```(?:json)?\s*(\{.*?\})\s*```", md, flags=re.S)
    if not blocks:
        # try last { ... }
        m = re.search(r"(\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\})\s*$", md, flags=re.S)
        if m:
            blocks = [m.group(1)]
    for b in reversed(blocks):
        try:
            return json.loads(b)
        except Exception:  # noqa: BLE001
            continue
    return {}
