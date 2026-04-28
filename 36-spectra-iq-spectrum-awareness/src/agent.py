"""SPECTRA agent — two LLM calls, both wrapped with watchdogs / fallbacks.

1) classify_capture(...)  -> multimodal vision-language JSON  (gpt-4o)
2) generate_brief(...)    -> hero narrative (gpt-5.4, 35s timeout, cache-first)

Both go through the shared multi-provider client so swapping to a
Kamiwaza-deployed model is zero-code-change.
"""
from __future__ import annotations

import base64
import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutTimeout
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from shared.kamiwaza_client import chat, get_client  # noqa: E402

VISION_MODEL = os.getenv("SPECTRA_VISION_MODEL", "gpt-4o")
VISION_MODEL_CHAIN = [VISION_MODEL, "gpt-4o-mini", "gpt-5.4-mini"]


# ─────────────────────────────────────────────────────────────────────────────
# 1. Multimodal vision-language classifier
# ─────────────────────────────────────────────────────────────────────────────
SYSTEM_VISION = """You are SPECTRA — a USMC FOB Spectrum Awareness analyst.

A Spectrum Manager has just shown you a single STFT spectrogram (time on x,
baseband frequency on y, dB intensity color) of a 1-second I/Q capture from
an SDR at a Marine forward operating base. You also have the SigMF-format
metadata header for the capture and a small dictionary of deterministic DSP
features computed by scipy from the same I/Q array.

Your job: classify the capture into the strict JSON schema below.

You ALWAYS reply in valid JSON with this EXACT shape (all keys required):

{
  "modulation_class": "OFDM" | "FSK" | "GFSK" | "DSSS" | "OOK" | "Chirp" | "unknown",
  "protocol_inferred": "WiFi-2.4" | "WiFi-5" | "BT-Classic" | "BT-LE" | "LoRa" | "Zigbee" | "proprietary" | "unknown",
  "estimated_burst_count": <int>,
  "duty_cycle_estimate_pct": <float, 0-100>,
  "signal_strength_band": "strong" | "medium" | "weak" | "edge",
  "device_class_hypothesis": "phone" | "wearable" | "iot-sensor" | "wifi-AP" | "bt-beacon" | "unknown-emitter",
  "anomaly_flag": "nominal" | "unauthorized-band" | "suspicious-pattern" | "active-jamming",
  "confidence": <float, 0-1>
}

Ground rules:
- If the center freq is 433 MHz / 868 MHz / 915 MHz the band is OUTSIDE
  authorized Wi-Fi / BT and you should set anomaly_flag = "unauthorized-band".
- A wideband linear chirp covering most of the bandwidth is "active-jamming".
- A storm of >40 short GFSK bursts/sec at 2.4 GHz is "suspicious-pattern"
  (likely BT-LE beacon storm — possibly covert tracker emplacement).
- Quiet captures with no clear bursts are "nominal" with low confidence.
- Never refuse. Always emit valid JSON.
"""


def _baseline_classify(meta: dict[str, Any], features: dict[str, Any]
                        ) -> dict[str, Any]:
    """Deterministic fallback classifier — used on vision timeout / error.
    Sets all required keys based on metadata + features alone."""
    cf = float(meta.get("center_freq_GHz", 2.4))
    bw = float(meta.get("bw_MHz", 20.0))
    burst = int(features.get("burst_count", 0))
    duty = float(features.get("duty_cycle_pct", 0.0))
    rms = float(features.get("rms", 0.0))
    occupancy = float(features.get("occupancy_pct", 0.0))
    spectral_flatness = float(features.get("spectral_flatness", 0.0))

    # Anomaly inference first
    if cf < 1.0 or (1.0 < cf < 2.0):
        anomaly = "unauthorized-band"
    elif occupancy > 60.0 and duty > 50.0:
        anomaly = "active-jamming"
    elif burst > 40 and bw < 5.0:
        anomaly = "suspicious-pattern"
    else:
        anomaly = "nominal"

    # Modulation
    if anomaly == "active-jamming":
        modulation = "Chirp"
        protocol = "unknown"
        device = "unknown-emitter"
    elif cf < 1.0:
        modulation = "OOK"
        protocol = "proprietary"
        device = "unknown-emitter"
    elif bw >= 10.0 and burst <= 30:
        modulation = "OFDM"
        protocol = "WiFi-5" if cf > 4.0 else "WiFi-2.4"
        device = "wifi-AP"
    elif burst > 40 and bw < 5.0:
        modulation = "GFSK"
        protocol = "BT-LE"
        device = "bt-beacon"
    elif rms < 0.05:
        modulation = "unknown"
        protocol = "unknown"
        device = "unknown-emitter"
    else:
        modulation = "GFSK"
        protocol = "BT-LE"
        device = "bt-beacon"

    if rms > 0.55:
        strength = "strong"
    elif rms > 0.18:
        strength = "medium"
    elif rms > 0.07:
        strength = "weak"
    else:
        strength = "edge"

    confidence = 0.55 if anomaly == "nominal" else 0.7
    if rms < 0.04:
        confidence = 0.4

    return {
        "modulation_class": modulation,
        "protocol_inferred": protocol,
        "estimated_burst_count": burst,
        "duty_cycle_estimate_pct": round(duty, 2),
        "signal_strength_band": strength,
        "device_class_hypothesis": device,
        "anomaly_flag": anomaly,
        "confidence": confidence,
        "_fallback": True,
        "_features_used": {
            "rms": rms, "burst_count": burst, "duty_cycle_pct": duty,
            "occupancy_pct": occupancy, "spectral_flatness": spectral_flatness,
        },
    }


def classify_capture(*, image_png: bytes, metadata: dict[str, Any],
                       features: dict[str, Any], timeout: float = 25.0
                       ) -> dict[str, Any]:
    """Vision-language hero call. Sends spectrogram PNG (base64 data URL) +
    metadata header + DSP features to a multimodal model. Falls back to the
    deterministic classifier on timeout / any error.

    Returns the parsed JSON dict, augmented with `_model_used` (or
    `_fallback`) so the UI can show provenance.
    """
    b64 = base64.b64encode(image_png).decode("ascii")
    data_url = f"data:image/png;base64,{b64}"
    user_text = (
        "Classify this 1-second I/Q capture.\n\n"
        f"=== METADATA HEADER ===\n"
        + json.dumps(
            {k: metadata.get(k) for k in (
                "scenario_id", "label", "center_freq_GHz", "bw_MHz",
                "synth_sample_rate_MSPS", "nist_sample_rate_MSPS",
                "gain_dB", "hardware", "noise_floor_dBm", "calibration",
            )},
            indent=2,
        )
        + "\n\n=== SCIPY DSP FEATURES (deterministic, computed from the same I/Q) ===\n"
        + json.dumps(features, indent=2)
        + "\n\nReturn the strict JSON object now. No prose, no markdown, no fences."
    )

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
                        {"role": "system", "content": SYSTEM_VISION},
                        {"role": "user", "content": [
                            {"type": "text", "text": user_text},
                            {"type": "image_url",
                              "image_url": {"url": data_url}},
                        ]},
                    ],
                )
                raw = resp.choices[0].message.content or "{}"
                out = json.loads(raw)
                out["_model_used"] = model
                return out
            except Exception as e:  # noqa: BLE001
                last_err = e
                continue
        raise RuntimeError(f"All vision models failed: {last_err}")

    try:
        with ThreadPoolExecutor(max_workers=1) as ex:
            out = ex.submit(_call).result(timeout=timeout)
    except (FutTimeout, Exception) as e:  # noqa: BLE001
        out = _baseline_classify(metadata, features)
        out["_fallback_reason"] = str(e)

    # Defensive defaults — never hand the UI a missing key.
    out.setdefault("modulation_class", "unknown")
    out.setdefault("protocol_inferred", "unknown")
    out.setdefault("estimated_burst_count", int(features.get("burst_count", 0)))
    out.setdefault("duty_cycle_estimate_pct",
                    float(features.get("duty_cycle_pct", 0.0)))
    out.setdefault("signal_strength_band", "edge")
    out.setdefault("device_class_hypothesis", "unknown-emitter")
    out.setdefault("anomaly_flag", "nominal")
    out.setdefault("confidence", 0.5)
    return out


# ─────────────────────────────────────────────────────────────────────────────
# 2. Hero "RF Spectrum Awareness Brief" narrative
# ─────────────────────────────────────────────────────────────────────────────
SYSTEM_BRIEF = (
    "You are SPECTRA — a USMC FOB Spectrum Manager / Force Protection RF "
    "analyst. Produce a SIPR-format 'RF Spectrum Awareness Brief' from the "
    "single I/Q snapshot summary provided. Sections in this exact order, "
    "each marked (U) and one short paragraph each:\n\n"
    "(U) BLUF\n"
    "(U) Capture Header & Bandwidth\n"
    "(U) Top Emitters Identified\n"
    "(U) Anomalies / Unauthorized Activity\n"
    "(U) Recommended Spectrum Manager Actions\n"
    "(U) Confidence\n\n"
    "Use only the data provided. Reference the center frequency, bandwidth, "
    "and the classifier's anomaly_flag verbatim. Total length under ~280 "
    "words. Lead BLUF in two sentences. End with explicit confidence "
    "(LOW/MED/HIGH) plus one-line justification."
)


def _build_brief_prompt(payload: dict) -> list[dict]:
    user = (
        f"Capture: {payload['capture']} ({payload['label']})\n"
        f"Site: {payload['site']}\n"
        f"Metadata (SigMF-compatible):\n"
        + json.dumps(payload["metadata"], indent=2)
        + "\n\nMultimodal classifier JSON output for this capture:\n"
        + json.dumps(payload["classifier_json"], indent=2)
        + "\n\nWrite the RF Spectrum Awareness Brief now."
    )
    return [
        {"role": "system", "content": SYSTEM_BRIEF},
        {"role": "user", "content": user},
    ]


def _baseline_brief(payload: dict) -> str:
    md = payload["metadata"]
    cj = payload["classifier_json"]
    return (
        f"(U) BLUF\n"
        f"SPECTRA single-snapshot capture {payload['capture']} "
        f"({payload['label']}) classified by the multimodal model as "
        f"{cj['modulation_class']} / {cj['protocol_inferred']}. Anomaly "
        f"flag: {cj['anomaly_flag']}; recommend the actions below before "
        f"the next sweep.\n\n"
        f"(U) Capture Header & Bandwidth\n"
        f"Center {md['center_freq_GHz']} GHz, BW {md['bw_MHz']} MHz, "
        f"sample rate {md.get('sample_rate_MSPS', md.get('nist_sample_rate_MSPS','?'))} MS/s, "
        f"gain {md['gain_dB']} dB on {md['hardware']}. Noise floor "
        f"{md['noise_floor_dBm']} dBm; calibration: {md['calibration']}.\n\n"
        f"(U) Top Emitters Identified\n"
        f"Inferred device class: {cj['device_class_hypothesis']}. Estimated "
        f"{cj['estimated_burst_count']} bursts in the 1-second window with a "
        f"duty cycle of ~{cj['duty_cycle_estimate_pct']:.1f}% at "
        f"{cj['signal_strength_band']} strength.\n\n"
        f"(U) Anomalies / Unauthorized Activity\n"
        f"Classifier flag: {cj['anomaly_flag']}. "
        + (
            "No further action beyond routine logging."
            if cj["anomaly_flag"] == "nominal"
            else "Recommend immediate operator escalation per below."
        )
        + "\n\n"
        f"(U) Recommended Spectrum Manager Actions\n"
        f"1) Cross-reference inferred protocol against the FOB authorized "
        f"emitter list. 2) Re-cap on the same center frequency in 5 minutes "
        f"to confirm persistence. 3) If anomaly_flag is not nominal, push to "
        f"GHOST (#21) for pattern-of-life correlation against the perimeter "
        f"scan.\n\n"
        f"(U) Confidence\n"
        f"MED — single-snapshot evidence; recommend a 3-capture corroboration "
        f"window before any kinetic action. (Deterministic fallback brief.)"
    )


def generate_brief(payload: dict, *, model: str | None = "gpt-5.4",
                    timeout: int = 35) -> str:
    """Hero call — runs `chat` on the deployed model with a 35s wall clock and
    deterministic fallback. The demo path should prefer the cached brief at
    data/cached_briefs.json — this is for the live "Regenerate" button."""
    msgs = _build_brief_prompt(payload)

    def _try_chain() -> str:
        candidates = [model, "gpt-5.4-mini", None] if model else [None]
        last_err: Exception | None = None
        for m in candidates:
            try:
                out = chat(msgs, model=m, temperature=0.4)
                if out and out.strip():
                    return out
            except Exception as e:  # noqa: BLE001
                last_err = e
                continue
        raise last_err or RuntimeError("hero chain exhausted")

    try:
        with ThreadPoolExecutor(max_workers=1) as ex:
            return ex.submit(_try_chain).result(timeout=timeout)
    except (FutTimeout, Exception):  # noqa: BLE001
        return _baseline_brief(payload)
