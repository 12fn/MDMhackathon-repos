"""Multimodal vision-language hero call for PALLET-VISION.

Sends an image + a strict-JSON schema prompt to a multimodal model via the
shared OpenAI-compatible client. Falls back through a chain so the demo
survives a single-model outage.

Image is sent as a base64 data URL so this works fully offline against an
on-prem Kamiwaza endpoint — no data leaves the wire.
"""
from __future__ import annotations

import base64
import io
import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutTimeout
from pathlib import Path
from typing import Any

from PIL import Image

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from shared.kamiwaza_client import get_client, chat  # noqa: E402

VISION_MODEL = os.getenv("PALLET_VISION_MODEL", "gpt-4o")
VISION_MODEL_CHAIN = [VISION_MODEL, "gpt-4o-mini", "gpt-5.4-mini"]


VISION_SYSTEM = """You are PALLET-VISION — a USMC LOGCOM Visual Quantification Engine.

A logistics planner has shown you a single still image of staged cargo: warehouse
pallets, a loading dock, a drone-overhead pass of a loaded vehicle, a flight
line, a construction yard, or a ship-deck staging area. Your job is to estimate
palletization and transportation requirements with a loadmaster's eye, citing
real DoD airlift / sealift / surface-lift platform constraints.

You always reply in strict JSON with this exact schema:
{
  "pallets_visible": <int>,
  "pallet_type_estimate": "464L | 463L | wood-stringer | mixed",
  "stacking_efficiency_pct": <float, 0-100>,
  "estimated_volume_m3": <float>,
  "estimated_weight_kg": <float>,
  "vehicles_required": [
    {"platform": "<one of: C-17 Globemaster III | C-130J Super Hercules | KC-46A Pegasus | KC-130J | MTVR (MK23) | M1083 FMTV (5-ton) | M1078 LMTV (2.5-ton) | LVSR (MK36) | LCAC>",
     "count": <int>,
     "load_pct": <float, 0-100>}
  ],
  "constraints_named": [
    "<short string citing a real platform constraint, e.g., 'C-130J pallet position constraint: 6 463L max'>"
  ],
  "confidence": <float, 0-1>,
  "recommended_load_plan_brief": "<1-2 sentence plan>"
}

Ground rules:
- A single 463L pallet is 88x108 in, max 10000 lb (4536 kg) gross.
- A C-17 holds 18 463L, C-130J / KC-130J holds 6, KC-46A holds 18.
- An MTVR holds 4 standard pallets; M1083 FMTV holds 4; M1078 LMTV holds 2;
  LVSR holds 8.
- An LCAC holds ~12 pallets ship-to-shore.
- If the cargo is light enough for surface lift, prefer the smallest organic
  vehicle that fits in one trip; only call airlift when weight or distance
  warrants it.
- If you can't see fine detail, make your best estimate and lower confidence
  accordingly. Never refuse — produce a usable JSON every time.
"""


def _image_to_data_url(img: Image.Image, *, max_side: int = 1024) -> str:
    img = img.convert("RGB")
    w, h = img.size
    if max(w, h) > max_side:
        scale = max_side / max(w, h)
        img = img.resize((int(w * scale), int(h * scale)), Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=88)
    b64 = base64.b64encode(buf.getvalue()).decode("ascii")
    return f"data:image/jpeg;base64,{b64}"


def _baseline_quantify(scene_hint: str = "") -> dict[str, Any]:
    """Deterministic fallback if every model in the chain times out / errors."""
    return {
        "pallets_visible": 6,
        "pallet_type_estimate": "mixed",
        "stacking_efficiency_pct": 70.0,
        "estimated_volume_m3": 12.0,
        "estimated_weight_kg": 3600.0,
        "vehicles_required": [
            {"platform": "MTVR (MK23)", "count": 2, "load_pct": 75.0},
        ],
        "constraints_named": [
            "Fallback estimate (model timeout). MTVR (MK23) holds 4 standard pallets per cargo bed.",
            "Refresh once the multimodal model is reachable for a higher-confidence call.",
        ],
        "confidence": 0.35,
        "recommended_load_plan_brief": (
            f"Deterministic fallback for scene='{scene_hint or 'unknown'}'. "
            "Ship via two MTVR runs; refresh the vision call when service is restored."
        ),
        "_fallback": True,
    }


def quantify(img: Image.Image, *, scene_hint: str = "", timeout: float = 35.0) -> dict[str, Any]:
    """Hero vision call with watchdog + chain fallback. Returns parsed JSON dict."""
    data_url = _image_to_data_url(img)
    user_text = (
        "Quantify the palletization and transportation requirement for this image. "
        "Return JSON per the schema."
    )
    if scene_hint:
        user_text += f" Scene hint from operator: {scene_hint}"

    def _call() -> dict[str, Any]:
        client = get_client()
        last_err: Exception | None = None
        for model in VISION_MODEL_CHAIN:
            try:
                resp = client.chat.completions.create(
                    model=model,
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
                out = json.loads(raw)
                out.setdefault("_model_used", model)
                return out
            except Exception as e:  # noqa: BLE001
                last_err = e
                continue
        raise RuntimeError(f"All vision models failed: {last_err}")

    with ThreadPoolExecutor(max_workers=1) as ex:
        try:
            out = ex.submit(_call).result(timeout=timeout)
        except (FutTimeout, Exception) as e:  # noqa: BLE001
            out = _baseline_quantify(scene_hint)
            out["_fallback_reason"] = str(e)

    # Defensive defaults — never hand the UI a missing key.
    out.setdefault("pallets_visible", 0)
    out.setdefault("pallet_type_estimate", "mixed")
    out.setdefault("stacking_efficiency_pct", 70.0)
    out.setdefault("estimated_volume_m3", 0.0)
    out.setdefault("estimated_weight_kg", 0.0)
    out.setdefault("vehicles_required", [])
    out.setdefault("constraints_named", [])
    out.setdefault("confidence", 0.5)
    out.setdefault("recommended_load_plan_brief", "")
    return out


# ---------------------------------------------------------------------------
# Loadmaster narrator — second LLM call, grounds JSON in platform_specs.csv
# ---------------------------------------------------------------------------

LOADMASTER_SYSTEM = """You are a senior USMC loadmaster speaking to a logistics
planner. You have just received a Visual Quantification JSON from PALLET-VISION
and a table of organic airlift / sealift / surface-lift platforms with their
true pallet capacity and weight limits.

Write a 4-bullet 'Loadmaster Brief'. Each bullet is one sentence.
- Bullet 1: how the cargo is configured (count + type + weight estimate).
- Bullet 2: which platform you would use first and why, citing the exact
  pallet-position number from the platform table.
- Bullet 3: a backup plan or chained-platform option if the first is not
  available.
- Bullet 4: one risk or constraint the planner must brief up the chain.

Stay grounded in the provided table. Cite platform names exactly as written.
Output as plain markdown with `- ` bullets, no preamble, no closing remarks."""


def loadmaster_brief(quant: dict[str, Any], platform_specs_text: str,
                     *, timeout: float = 30.0) -> str:
    """Second LLM call — narrator grounds JSON in real platform constraints."""

    quant_for_prompt = {k: v for k, v in quant.items() if not k.startswith("_")}
    user = (
        "VISUAL QUANTIFICATION JSON:\n"
        f"{json.dumps(quant_for_prompt, indent=2)}\n\n"
        "AVAILABLE PLATFORMS (USMC + USAF organic):\n"
        f"{platform_specs_text}\n\n"
        "Write the 4-bullet Loadmaster Brief now."
    )

    def _call() -> str:
        return chat(
            [{"role": "system", "content": LOADMASTER_SYSTEM},
             {"role": "user", "content": user}],
            temperature=0.35,
            max_tokens=420,
        )

    with ThreadPoolExecutor(max_workers=1) as ex:
        try:
            return ex.submit(_call).result(timeout=timeout)
        except (FutTimeout, Exception) as e:  # noqa: BLE001
            return (
                "- Loadmaster narrator timed out; falling back to JSON-only brief.\n"
                f"- Visual estimate: {quant.get('pallets_visible', 0)} pallets, "
                f"~{int(quant.get('estimated_weight_kg') or 0)} kg.\n"
                "- Default routing: schedule the smallest organic vehicle that fits in one trip.\n"
                f"- Refresh once the narrator service is reachable. (reason: {e})"
            )
