"""CUAS-DETECT agent — multi-stage classifier + LLM intent assessment.

Three callables, each wrapped with a watchdog and deterministic fallback so
the UI never freezes:

  1. heuristic_features(arr)            : numpy on the spectrogram (no LLM)
  2. vision_classify(png_path, feats)   : multimodal vision LLM ('gpt-4o') →
                                          structured JSON UAS class + intent
  3. engagement_brief(payload)          : hero text LLM ('gpt-5.4', 35s wall
                                          clock, cache-first) → 5-bullet
                                          watch-officer recommendation
"""
from __future__ import annotations

import base64
import json
import re
import sys
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutTimeout
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from shared.kamiwaza_client import chat, chat_json  # noqa: E402

# generate.py owns the heuristic feature/baseline routines — reuse them so the
# precompute and runtime paths stay in sync.
DATA_DIR = Path(__file__).resolve().parent.parent / "data"
sys.path.insert(0, str(DATA_DIR))
from generate import (  # noqa: E402
    extract_features,
    baseline_classify,
    SCENARIO_CONTEXT,
    SYSTEM_BRIEF,
    _fallback_brief,
)


VISION_MODEL = "gpt-4o"
HERO_MODEL = "gpt-5.4"


# ─────────────────────────────────────────────────────────────────────────────
# 1. Heuristic features (no LLM)
# ─────────────────────────────────────────────────────────────────────────────
def heuristic_features(arr) -> dict[str, Any]:
    feats = extract_features(arr)
    base = baseline_classify(feats)
    return {"features": feats, "baseline": base}


# ─────────────────────────────────────────────────────────────────────────────
# 2. Vision LLM — multimodal classifier + structured JSON
# ─────────────────────────────────────────────────────────────────────────────
SYSTEM_VISION = (
    "You are CUAS-DETECT's multimodal RF spectrogram classifier. The image is "
    "a spectrogram with frequency on the Y axis and time on the X axis; "
    "intensity is dark→neon→amber→red. Use BOTH the image and the heuristic "
    "JSON sidecar to identify the inbound UAS. Output STRICT JSON only — no "
    "prose, no fences. Schema:\n"
    '{\n'
    '  "uas_class": one of ["DJI Mavic","Parrot Anafi","COTS-fixed-wing",'
    '"hobbyist-quad","swarm","ambient"],\n'
    '  "confidence": float 0.0-1.0,\n'
    '  "controller_signature_match": one of ["OcuSync","Lightbridge","WiFi",'
    '"LoRa","proprietary","none"],\n'
    '  "inferred_intent": one of ["recon","strike","decoy","swarm-overwatch","unknown"],\n'
    '  "estimated_range_km": float,\n'
    '  "recommended_action": one of ["monitor","jam-non-kinetic","request-engagement",'
    '"spoof-GPS","escalate-to-FOC"],\n'
    '  "rationale": short string (1-2 sentences),\n'
    '  "EOC_callout_text": short string suitable for a watch-officer SMS alert\n'
    "}"
)


def _png_to_data_url(png_path: Path) -> str:
    b = Path(png_path).read_bytes()
    b64 = base64.b64encode(b).decode("ascii")
    return f"data:image/png;base64,{b64}"


def _baseline_vision_json(features: dict, baseline: dict) -> dict:
    """Deterministic JSON used when the vision call fails / times out."""
    cls = baseline["uas_class_guess"]
    ctrl = baseline["controller_guess"]
    intent = baseline["intent_guess"]
    conf = float(baseline["baseline_confidence"])
    # range estimate from snr (cheap heuristic)
    snr = features.get("snr_estimate_db", 10)
    if cls == "ambient":
        rng_km = 0.0
    else:
        rng_km = max(0.3, min(10.0, round(15.0 - (snr / 3.0), 1)))
    if cls == "ambient":
        action = "monitor"
    elif cls == "swarm":
        action = "escalate-to-FOC"
    elif intent == "strike":
        action = "request-engagement"
    elif intent == "recon":
        action = "jam-non-kinetic"
    else:
        action = "monitor"
    callout_pre = "AMBIENT" if cls == "ambient" else f"INBOUND {cls.upper()}"
    callout = (
        f"{callout_pre} | {ctrl} | ~{rng_km}km | intent={intent} | "
        f"COA={action} | conf={conf:.2f}"
    )
    return {
        "uas_class": cls if cls in {"DJI Mavic","Parrot Anafi","COTS-fixed-wing","hobbyist-quad","swarm","ambient"} else "ambient",
        "confidence": conf,
        "controller_signature_match": ctrl if ctrl in {"OcuSync","Lightbridge","WiFi","LoRa","proprietary","none"} else "none",
        "inferred_intent": intent,
        "estimated_range_km": rng_km,
        "recommended_action": action,
        "rationale": (f"Baseline-only fallback: {features.get('modulation_hint','n/a')}; "
                      f"SNR {snr} dB."),
        "EOC_callout_text": callout,
    }


def vision_classify(png_path: str | Path, feats_payload: dict,
                     *, timeout: int = 25) -> dict:
    """Multimodal vision call with watchdog. Returns a dict matching the schema
    in SYSTEM_VISION. Falls back to a deterministic baseline on any error."""
    features = feats_payload.get("features", {})
    baseline = feats_payload.get("baseline", {})
    user_text = (
        "Heuristic JSON sidecar (numpy on the spectrogram array):\n"
        f"{json.dumps(features, indent=2)}\n\n"
        "Baseline classifier guess (deterministic, can be overridden by vision):\n"
        f"{json.dumps(baseline, indent=2)}\n\n"
        "Now ingest the spectrogram image and return the JSON object only."
    )
    content = [
        {"type": "text", "text": user_text},
        {"type": "image_url",
         "image_url": {"url": _png_to_data_url(Path(png_path)), "detail": "high"}},
    ]

    def _try() -> dict:
        # JSON-mode + vision: response_format on OpenAI-compat
        for m in (VISION_MODEL, "gpt-4o-mini"):
            try:
                raw = chat(
                    [
                        {"role": "system", "content": SYSTEM_VISION},
                        {"role": "user", "content": content},
                    ],
                    model=m,
                    temperature=0.2,
                    max_tokens=600,
                    response_format={"type": "json_object"},
                )
                if not raw or not raw.strip():
                    continue
                return _coerce_json(raw)
            except Exception:  # noqa: BLE001
                continue
        # last-ditch: text-only chat_json with explicit hint
        return chat_json(
            [
                {"role": "system", "content": SYSTEM_VISION},
                {"role": "user", "content": user_text},
            ],
            schema_hint=("uas_class, confidence, controller_signature_match, "
                          "inferred_intent, estimated_range_km, "
                          "recommended_action, rationale, EOC_callout_text"),
            temperature=0.2,
        )

    try:
        with ThreadPoolExecutor(max_workers=1) as ex:
            return ex.submit(_try).result(timeout=timeout)
    except (FutTimeout, Exception):  # noqa: BLE001
        return _baseline_vision_json(features, baseline)


def _coerce_json(raw: str) -> dict:
    s = raw.strip()
    if s.startswith("```"):
        s = s.split("\n", 1)[1] if "\n" in s else s
        if s.endswith("```"):
            s = s[: -3]
        s = s.strip()
        if s.startswith("json"):
            s = s[4:].lstrip()
    try:
        return json.loads(s)
    except Exception:
        # try to find the largest {...}
        m = re.search(r"\{.*\}", s, flags=re.S)
        if m:
            return json.loads(m.group(0))
        raise


# ─────────────────────────────────────────────────────────────────────────────
# 3. Hero engagement-brief generator
# ─────────────────────────────────────────────────────────────────────────────
def engagement_brief(scenario_payload: dict, *, model: str | None = HERO_MODEL,
                      timeout: int = 35) -> str:
    """Hero call — runs `chat` on the deployed model with a 35s wall clock and
    deterministic fallback. Cache-first: callers should prefer
    data/cached_briefs.json for the demo path."""
    user = (
        f"Scenario:\n{json.dumps(scenario_payload, indent=2)}\n\n"
        f"Write the CUAS Engagement Recommendation now."
    )
    msgs = [
        {"role": "system", "content": SYSTEM_BRIEF},
        {"role": "user", "content": user},
    ]

    def _try_chain() -> str:
        for m in (model, "gpt-5.4-mini", None):
            try:
                out = chat(msgs, model=m, temperature=0.4, max_tokens=600)
                if out and out.strip():
                    return out
            except Exception:  # noqa: BLE001
                continue
        raise RuntimeError("hero chain exhausted")

    try:
        with ThreadPoolExecutor(max_workers=1) as ex:
            return ex.submit(_try_chain).result(timeout=timeout)
    except (FutTimeout, Exception):  # noqa: BLE001
        return _fallback_brief(scenario_payload)


def build_scenario_payload(sig_meta: dict, features: dict, baseline: dict,
                            vision: dict | None = None) -> dict:
    """Combine current-scan inputs into the payload the brief generator wants."""
    payload = {
        "scenario_id": sig_meta.get("id", "live"),
        "uas_signature_title": sig_meta.get("title", "Unknown contact"),
        "ground_truth": {
            "uas_class": sig_meta.get("uas_class", "unknown"),
            "controller": sig_meta.get("controller", "unknown"),
            "band_ghz": sig_meta.get("band_ghz", "unknown"),
            "estimated_range_km": sig_meta.get("ground_truth_range_km", 0.0),
            "intent_hint": sig_meta.get("intent_hint", "unknown"),
        },
        "spectral_features": features,
        "baseline_classifier": baseline,
        "site_context": SCENARIO_CONTEXT,
    }
    if vision:
        payload["vision_classifier"] = vision
    return payload
