# OPTIK — vision RAG over a TM library — maintainer photo to TM citation
# Part of the MDM 2026 Hackathon Templates (https://github.com/12fn/MDMhackathon-repos)
# MIT licensed. Built on GAI (Government Acquisitions, Inc.) + Kamiwaza (https://www.kamiwaza.ai/).
"""Vision-language hero call.

Uses a Kamiwaza-deployed multimodal model via the shared OpenAI-compatible client
(Qwen2-VL / LLaVA / equivalent served on the Kamiwaza vLLM Inference Mesh).
Image is sent as a base64 data URL so this works fully offline against an
on-prem Kamiwaza endpoint — no data leaves the wire.
"""
from __future__ import annotations

import base64
import io
import json
import sys
from pathlib import Path
from typing import Any

from PIL import Image

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from shared.kamiwaza_client import get_client  # noqa: E402


VISION_MODEL = "gpt-4o"  # gpt-5.4 has vision; gpt-4o is the proven floor today.

VISION_SYSTEM = """You are OPTIK — a USMC LOGCOM tactical visual-recognition agent.
Your job: look at a photo a Marine just took in the field and identify what is in it
with a maintainer's eye. Focus on items relevant to ground-fleet maintenance:
vehicles (MTVR, JLTV, HMMWV, AAV, ACV, LVSR), components (valves, seals, belts,
connectors, lines, brakes, suspension), and tools.

You always reply in strict JSON with this schema:
{
  "scene": "<one-sentence scene description>",
  "primary_subject": "<the single most important component / object>",
  "detections": [
    {"label": "<label>", "bbox": [x1, y1, x2, y2], "confidence": 0.0-1.0, "rationale": "<why>"}
  ],
  "search_query": "<a 6-12 word query to retrieve the relevant TM section>"
}

Coordinates are normalized 0-1 (top-left origin). If you can't see fine detail,
make your best estimate — the Marine will iterate. Return at most 5 detections.
"""


def _image_to_data_url(img: Image.Image, *, max_side: int = 768) -> str:
    """Resize defensively, encode as JPEG data URL."""
    img = img.convert("RGB")
    w, h = img.size
    if max(w, h) > max_side:
        scale = max_side / max(w, h)
        img = img.resize((int(w * scale), int(h * scale)), Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=85)
    b64 = base64.b64encode(buf.getvalue()).decode("ascii")
    return f"data:image/jpeg;base64,{b64}"


def detect(img: Image.Image, hint: str = "") -> dict[str, Any]:
    """Single hero vision call. Returns parsed JSON dict."""
    client = get_client()
    data_url = _image_to_data_url(img)
    user_text = (
        "Identify what is in this image with a maintainer's eye. "
        "Return JSON per the schema."
    )
    if hint:
        user_text += f" Marine's note: {hint}"

    resp = client.chat.completions.create(
        model=VISION_MODEL,
        temperature=0.2,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": VISION_SYSTEM},
            {"role": "user", "content": [
                {"type": "text", "text": user_text},
                {"type": "image_url", "image_url": {"url": data_url}},
            ]},
        ],
    )
    raw = resp.choices[0].message.content or "{}"
    try:
        out = json.loads(raw)
    except json.JSONDecodeError:
        out = {"scene": "Parse failure — see raw.", "detections": [],
               "primary_subject": "unknown", "search_query": hint or "field component",
               "_raw": raw}
    # Defensive defaults
    out.setdefault("scene", "")
    out.setdefault("detections", [])
    out.setdefault("primary_subject", "unknown")
    out.setdefault("search_query", out.get("primary_subject", "field component"))
    return out
