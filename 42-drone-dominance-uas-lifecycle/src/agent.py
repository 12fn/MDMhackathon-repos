"""DRONE-DOMINANCE agent — triple-fusion multimodal pipeline.

Three live calls (each watch-dogged, each with a deterministic fallback):

  1. triple_fuse(scenario)        — three multimodal calls in one workflow:
                                     RF spectrogram-as-image, thermal IR,
                                     visual EO. Each emits a structured JSON;
                                     fuse them into one detection JSON.
  2. engagement_decision(payload)  — chat_json call: graded options ladder
                                     (monitor / EW jam / kinetic / spoof /
                                     escalate FOC) ROE-aware.
  3. encounter_brief(payload)      — hero `chat` ('gpt-5.4', 35s wall clock,
                                     cache-first) writing the full
                                     UAS Encounter Brief.
  4. egocentric_aar(frame, response, eval) — vision-language scoring of the
                                     trainee's decision against doctrine,
                                     using the helmet-cam still as input.

Pattern: every hero call is wrapped in ThreadPoolExecutor with a wall-clock
timeout. On timeout, fall back to the deterministic baseline so the demo
never spinner-locks (per AGENT_BRIEF_V2 §B).
"""
from __future__ import annotations

import base64
import io
import json
import os
import re
import sys
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutTimeout
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from shared.kamiwaza_client import chat, chat_json  # noqa: E402

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
sys.path.insert(0, str(DATA_DIR))
from generate import (  # noqa: E402
    extract_rf_features,
    extract_thermal_features,
    extract_visual_features,
    baseline_triple_fuse,
    baseline_engagement_decision,
    _fallback_brief,
    SCENARIOS,
    SCENARIO_CONTEXT,
    SYSTEM_HERO,
    ENGAGEMENT_OPTIONS,
)


HERO_MODEL = os.getenv("DRONE_DOMINANCE_HERO_MODEL", "gpt-5.4")
VISION_MODEL = os.getenv("DRONE_DOMINANCE_VISION_MODEL", "gpt-4o")
TIMEOUT_FUSE = int(os.getenv("DRONE_DOMINANCE_FUSE_TIMEOUT", "25"))
TIMEOUT_DECISION = int(os.getenv("DRONE_DOMINANCE_DECISION_TIMEOUT", "20"))
TIMEOUT_BRIEF = int(os.getenv("DRONE_DOMINANCE_BRIEF_TIMEOUT", "35"))
TIMEOUT_AAR = int(os.getenv("DRONE_DOMINANCE_AAR_TIMEOUT", "25"))


# ─────────────────────────────────────────────────────────────────────────────
# Image helpers
# ─────────────────────────────────────────────────────────────────────────────
def _png_to_data_url(png_path: Path, *, max_side: int = 1024) -> str:
    img = Image.open(png_path).convert("RGB")
    w, h = img.size
    if max(w, h) > max_side:
        scale = max_side / max(w, h)
        img = img.resize((int(w * scale), int(h * scale)), Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=85)
    return f"data:image/jpeg;base64,{base64.b64encode(buf.getvalue()).decode('ascii')}"


def _coerce_json(raw: str) -> dict:
    s = (raw or "").strip()
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
        m = re.search(r"\{.*\}", s, flags=re.S)
        if m:
            return json.loads(m.group(0))
        raise


# ─────────────────────────────────────────────────────────────────────────────
# 1. THREE multimodal calls — one per sensor modality. Each returns a JSON.
# ─────────────────────────────────────────────────────────────────────────────
SYSTEM_RF = (
    "You are DRONE-DOMINANCE's RF spectrogram-as-image classifier. The image "
    "is a spectrogram, frequency on Y, time on X, intensity dark→neon→amber→"
    "red. Use BOTH the image and the heuristic JSON sidecar to identify the "
    "controller signature. Output STRICT JSON only:\n"
    '{ "p_uas_present": float 0-1,\n'
    '  "controller_signature_match": one of '
    '["OcuSync","Lightbridge","WiFi","LoRa","proprietary","none"],\n'
    '  "uas_class_guess": one of '
    '["DJI Mavic","Parrot Anafi","COTS-fixed-wing","hobbyist-quad","swarm","ambient"],\n'
    '  "rationale": short string (<=24 words) }'
)


SYSTEM_THERMAL = (
    "You are DRONE-DOMINANCE's thermal IR scene classifier. The image is an "
    "inferno-LUT pseudo-colored thermal frame with bounding boxes drawn on "
    "detected hot blobs. Use BOTH the image and the JSON heuristic counts to "
    "identify whether a UAS is present and confirm or revise the "
    "person/vehicle/UAS classification. Output STRICT JSON only:\n"
    '{ "p_uas_present": float 0-1,\n'
    '  "blob_classes_confirmed": list of strings,\n'
    '  "person_or_vehicle_in_frame": bool,\n'
    '  "rationale": short string (<=24 words) }'
)


SYSTEM_VISUAL = (
    "You are DRONE-DOMINANCE's visual EO classifier. The image is a "
    "perimeter EO photo (sky / horizon / ground line) with possible drone "
    "silhouettes. Use the image to count drone silhouettes and confirm the "
    "platform shape (quad / fixed-wing / swarm). Output STRICT JSON only:\n"
    '{ "p_uas_present": float 0-1,\n'
    '  "n_silhouettes": int,\n'
    '  "platform_shape": one of '
    '["quad","fixed-wing","swarm","none","unclear"],\n'
    '  "rationale": short string (<=24 words) }'
)


def _baseline_rf_json(rf_feats: dict, sig: dict) -> dict:
    snr = rf_feats["snr_estimate_db"]
    p = max(0.05, min(0.99, (snr - 4) / 26.0))
    if rf_feats["modulation_hint"].startswith("below detection"):
        p = 0.10
    return {
        "p_uas_present": round(p, 3),
        "controller_signature_match": sig.get("controller", "unknown"),
        "uas_class_guess": sig.get("uas_class", "unknown"),
        "rationale": f"baseline: {rf_feats['modulation_hint']}; SNR {snr} dB",
    }


def _baseline_thermal_json(thm_feats: dict) -> dict:
    n_uas = thm_feats["n_uas_blobs"]
    p = max(0.10, min(0.95, 0.30 + 0.20 * n_uas))
    if n_uas == 0:
        p = 0.18
    classes = []
    if n_uas:
        classes.append("UAS")
    if thm_feats["n_person_blobs"]:
        classes.append("person")
    if thm_feats["n_vehicle_blobs"]:
        classes.append("vehicle")
    if thm_feats["n_animal_blobs"]:
        classes.append("animal/bird")
    return {
        "p_uas_present": round(p, 3),
        "blob_classes_confirmed": classes,
        "person_or_vehicle_in_frame": bool(thm_feats["n_person_blobs"]
                                             or thm_feats["n_vehicle_blobs"]),
        "rationale": f"baseline: {n_uas} UAS-class blob(s), peak "
                      f"{thm_feats['peak_intensity_8bit']}/255",
    }


def _baseline_visual_json(vis_feats: dict, sig: dict) -> dict:
    n = vis_feats["n_drone_silhouettes"]
    p = max(0.10, min(0.95, 0.30 + 0.18 * n))
    if n == 0:
        p = 0.20
    shape = ("none" if n == 0
             else "swarm" if n >= 3
             else "fixed-wing" if "fixed_wing" in vis_feats["scene_kind"]
             else "quad")
    return {
        "p_uas_present": round(p, 3),
        "n_silhouettes": n,
        "platform_shape": shape,
        "rationale": f"baseline: {n} silhouette(s) in {vis_feats['scene_kind']}",
    }


def _live_modal_call(system: str, png_path: Path, sidecar_text: str,
                      *, model: str = VISION_MODEL, temperature: float = 0.2) -> dict:
    content = [
        {"type": "text", "text": sidecar_text},
        {"type": "image_url",
         "image_url": {"url": _png_to_data_url(png_path), "detail": "high"}},
    ]
    raw = chat(
        [
            {"role": "system", "content": system},
            {"role": "user", "content": content},
        ],
        model=model,
        temperature=temperature,
        max_tokens=400,
        response_format={"type": "json_object"},
    )
    return _coerce_json(raw)


def _try_with_timeout(fn, timeout: int, fallback):
    """Run fn() under a wall clock; on any failure, return fallback (a value)."""
    with ThreadPoolExecutor(max_workers=1) as ex:
        try:
            return ex.submit(fn).result(timeout=timeout)
        except (FutTimeout, Exception):  # noqa: BLE001
            return fallback


def triple_fuse(scenario: dict, *, rf_arr: np.ndarray, rf_png: Path,
                 thm_gray: np.ndarray, thm_bboxes: list[dict], thm_png: Path,
                 vis_png: Path, timeout: int = TIMEOUT_FUSE) -> dict:
    """Three multimodal calls in one workflow (RF, thermal, visual) → fused JSON.

    Each modality call has a per-call watchdog so a slow modality can't sink
    the whole fusion. Falls back to deterministic per-modality JSON on any
    failure, then runs the same Bayesian-product fusion as the cache path.
    """
    rf_feats = extract_rf_features(rf_arr)
    thm_feats = extract_thermal_features(thm_gray, thm_bboxes)
    vis_feats = extract_visual_features(scenario)

    rf_sidecar = (
        "Heuristic RF JSON sidecar:\n"
        f"{json.dumps(rf_feats, indent=2)}\n\nReturn JSON only."
    )
    thm_sidecar = (
        "Heuristic thermal JSON sidecar:\n"
        f"{json.dumps(thm_feats, indent=2)}\n"
        "Bounding boxes drawn on the image are heuristic-detected blobs.\n\n"
        "Return JSON only."
    )
    vis_sidecar = (
        "Heuristic visual JSON sidecar:\n"
        f"{json.dumps(vis_feats, indent=2)}\n\nReturn JSON only."
    )

    per_call = max(8, timeout // 3)
    rf_json = _try_with_timeout(
        lambda: _live_modal_call(SYSTEM_RF, rf_png, rf_sidecar),
        per_call, _baseline_rf_json(rf_feats, scenario))
    thm_json = _try_with_timeout(
        lambda: _live_modal_call(SYSTEM_THERMAL, thm_png, thm_sidecar),
        per_call, _baseline_thermal_json(thm_feats))
    vis_json = _try_with_timeout(
        lambda: _live_modal_call(SYSTEM_VISUAL, vis_png, vis_sidecar),
        per_call, _baseline_visual_json(vis_feats, scenario))

    # Bayesian product fusion across the three p_uas_present
    p_rf = float(rf_json.get("p_uas_present", 0.5))
    p_thm = float(thm_json.get("p_uas_present", 0.5))
    p_vis = float(vis_json.get("p_uas_present", 0.5))
    prod = p_rf * p_thm * p_vis
    prod_n = (1 - p_rf) * (1 - p_thm) * (1 - p_vis)
    fused = prod / max(1e-9, prod + prod_n)

    contributors = []
    if p_rf > 0.4:
        contributors.append("RF")
    if p_thm > 0.4:
        contributors.append("thermal")
    if p_vis > 0.4:
        contributors.append("visual")

    detection_class = (rf_json.get("uas_class_guess")
                        or scenario.get("uas_class", "unknown"))

    return {
        "detection_class": detection_class,
        "make_model_guess": scenario.get("make_model", "unknown"),
        "controller_signature_match": rf_json.get(
            "controller_signature_match", scenario.get("controller", "unknown")),
        "inferred_intent": scenario.get("intent_hint", "unknown"),
        "estimated_range_km": scenario.get("ground_truth_range_km", 0.0),
        "estimated_alt_m": scenario.get("ground_truth_alt_m", 0),
        "confidence_per_modality": {
            "rf": round(p_rf, 3),
            "thermal": round(p_thm, 3),
            "visual": round(p_vis, 3),
        },
        "fused_confidence": round(fused, 3),
        "contributing_sensors": contributors or ["none-above-threshold"],
        "fusion_method": "naive-Bayes product over 3 multimodal classifier outputs",
        "_per_modality_json": {
            "rf": rf_json,
            "thermal": thm_json,
            "visual": vis_json,
        },
        "_features": {
            "rf": rf_feats,
            "thermal": thm_feats,
            "visual": vis_feats,
        },
    }


# ─────────────────────────────────────────────────────────────────────────────
# 2. Engagement decision — chat_json graded options ladder
# ─────────────────────────────────────────────────────────────────────────────
SYSTEM_DECISION = (
    "You are DRONE-DOMINANCE's engagement-decision agent. Given a fused UAS "
    "detection JSON, the site context, and the ROE-graded engagement option "
    "ladder (8 options), return a JSON object scoring each option from 0.0 to "
    "1.0 against the current context, then nominate the recommended option. "
    "Output STRICT JSON only:\n"
    '{\n'
    '  "recommended_option_id": "<id from the ladder>",\n'
    '  "recommended_option_name": "<name>",\n'
    '  "recommended_tag": "PASSIVE | NON-KINETIC | KINETIC",\n'
    '  "recommended_rationale": "<one sentence>",\n'
    '  "options_graded": [\n'
    '    {"id":"...","name":"...","tag":"...","authority_required":"...",'
    '"score":0.x,"rationale":"..."}, ...\n'
    '  ],\n'
    '  "ROE_floor": "Watch officer (OOD)",\n'
    '  "ROE_ceiling": "FOC + SECDEF UAS rule-set (kinetic only)"\n'
    '}\n'
    "Hard rules: only score options from the provided ladder; never invent "
    "options; for ambient contacts, max-score must be a PASSIVE option."
)


def engagement_decision(scenario: dict, fused: dict, *,
                         timeout: int = TIMEOUT_DECISION) -> dict:
    user = (
        f"Fused detection JSON:\n{json.dumps({k: v for k, v in fused.items() if not k.startswith('_')}, indent=2)}\n\n"
        f"Site context:\n{json.dumps(SCENARIO_CONTEXT, indent=2)}\n\n"
        f"ROE-graded engagement options ladder:\n"
        f"{json.dumps(ENGAGEMENT_OPTIONS, indent=2)}\n\n"
        "Score each option, then nominate the recommended one. JSON only."
    )

    def _try():
        for m in (HERO_MODEL, "gpt-5.4-mini", "gpt-4o-mini"):
            try:
                return chat_json(
                    [
                        {"role": "system", "content": SYSTEM_DECISION},
                        {"role": "user", "content": user},
                    ],
                    schema_hint=("recommended_option_id, recommended_option_name, "
                                  "recommended_tag, recommended_rationale, "
                                  "options_graded[], ROE_floor, ROE_ceiling"),
                    model=m,
                    temperature=0.3,
                    max_tokens=900,
                )
            except Exception:  # noqa: BLE001
                continue
        raise RuntimeError("decision chain exhausted")

    return _try_with_timeout(_try, timeout,
                              baseline_engagement_decision(fused, scenario))


# ─────────────────────────────────────────────────────────────────────────────
# 3. Hero "UAS Encounter Brief" — full SITREP, cache-first
# ─────────────────────────────────────────────────────────────────────────────
def encounter_brief(payload: dict, *, model: str | None = None,
                     timeout: int = TIMEOUT_BRIEF) -> str:
    msgs = [
        {"role": "system", "content": SYSTEM_HERO},
        {"role": "user", "content":
            f"Scenario:\n{json.dumps(payload, indent=2)}\n\n"
            f"Write the UAS ENCOUNTER BRIEF now."},
    ]

    def _try():
        for m in (model or HERO_MODEL, "gpt-5.4-mini", "gpt-4o-mini", None):
            try:
                out = chat(msgs, model=m, temperature=0.4, max_tokens=700)
                if out and out.strip():
                    return out
            except Exception:  # noqa: BLE001
                continue
        raise RuntimeError("hero chain exhausted")

    return _try_with_timeout(_try, timeout, _fallback_brief(payload))


def build_brief_payload(scenario: dict, fused: dict, decision: dict) -> dict:
    """Assemble the brief input payload from a (live) fusion+decision pair."""
    feats = fused.get("_features", {})
    return {
        "scenario_id": scenario.get("id", "live"),
        "scenario_title": scenario.get("title", "Unknown contact"),
        "ground_truth": {
            "uas_class": scenario.get("uas_class"),
            "make_model": scenario.get("make_model"),
            "controller": scenario.get("controller"),
            "band_ghz": scenario.get("band_ghz"),
            "estimated_range_km": scenario.get("ground_truth_range_km", 0.0),
            "estimated_alt_m": scenario.get("ground_truth_alt_m", 0),
            "intent_hint": scenario.get("intent_hint"),
        },
        "rf_features": feats.get("rf", {}),
        "thermal_features": feats.get("thermal", {}),
        "visual_features": feats.get("visual", {}),
        "triple_fusion": {k: v for k, v in fused.items() if not k.startswith("_")},
        "engagement_decision": decision,
        "site_context": SCENARIO_CONTEXT,
    }


# ─────────────────────────────────────────────────────────────────────────────
# 4. Egocentric AAR — vision-language scoring on a helmet-cam still
# ─────────────────────────────────────────────────────────────────────────────
SYSTEM_AAR = (
    "You are DRONE-DOMINANCE's egocentric AAR coach — an SNCO-tonal Marine "
    "Corps after-action review writer. You are reviewing a helmet-cam still "
    "of an operator (Stinger gunner, EW console operator, patrol with hand-"
    "held jammer, or FOC battle captain) plus the engagement decision they "
    "selected and the doctrinal context. Score the decision against doctrine "
    "and write a 4-line hot-wash. Output STRICT JSON only:\n"
    '{ "decision_classified_as": "doctrinally_correct | tactical | hesitation | risky",\n'
    '  "score_0_100": int,\n'
    '  "doctrine_reference": "<echo the passed doctrine_reference>",\n'
    '  "consequences_simulated": "<one short line>",\n'
    '  "coaching_feedback": "<2-3 SNCO-voice sentences>",\n'
    '  "next_iteration": "<one short line>" }\n'
    "Hard rules: never invent doctrine references; 'doctrinally_correct' "
    "requires the operator's choice to match the recommended COA in spirit "
    "AND not skip a ROE step (e.g. kinetic without positive ID)."
)


def _baseline_aar(frame: dict, operator_choice: str, recommended: str,
                   fused: dict) -> dict:
    cls_lower = operator_choice.lower()
    rec_lower = recommended.lower()
    matches = (rec_lower in cls_lower or cls_lower in rec_lower
                or any(w in cls_lower for w in rec_lower.split() if len(w) > 3))
    skipped_steps = ("kinetic" in cls_lower
                      and fused.get("inferred_intent") in {"recon", "decoy"})
    if skipped_steps:
        cls = "risky"
        score = 35
        consequences = ("Escalated to kinetic without positive hostile intent — "
                        "civil airspace + ROE breach risk.")
        feedback = (
            "Kinetic option is not authorized for recon-intent contacts under "
            "the floor ROE. Walk the EOF ladder: monitor, sector jam, "
            "escalate. Lead with the lowest-collateral non-kinetic option "
            "every time."
        )
    elif matches:
        cls = "doctrinally_correct"
        score = 90
        consequences = "Threat displaced or denied; no ROE breach; chain informed."
        feedback = (
            "Solid call. You matched the recommended COA without skipping the "
            "ROE floor. Re-rep the same flow under timer next iteration so "
            "decision latency drops further."
        )
    elif "monitor" in cls_lower or "log" in cls_lower:
        cls = "hesitation"
        score = 55
        consequences = "Threat persists in the area; pattern-of-life only."
        feedback = (
            "Track-only is the right baseline, but with this fused confidence "
            "you owe the OOD a recommendation, not just a log entry. Push the "
            "next rung on the ladder."
        )
    else:
        cls = "tactical"
        score = 72
        consequences = "Action taken; doctrinal step missing."
        feedback = (
            "Right idea, missing a step. Confirm authority before the action "
            "and call up the contact to higher in the same breath. The recommended "
            "COA was a notch off your call."
        )
    return {
        "decision_classified_as": cls,
        "score_0_100": score,
        "doctrine_reference": frame["doctrine_reference"],
        "consequences_simulated": consequences,
        "coaching_feedback": feedback,
        "next_iteration": "Re-rep this scenario; narrate ROE floor before action.",
        "_source": "baseline",
    }


def egocentric_aar(frame: dict, operator_choice: str, fused: dict,
                    decision: dict, *, png_path: Path | None = None,
                    timeout: int = TIMEOUT_AAR) -> dict:
    """Multimodal AAR scoring — uses the helmet-cam still + decision context."""
    user_text = (
        f"AAR FRAME TITLE: {frame['title']}\n"
        f"CONTEXT: {frame['context']}\n\n"
        f"DOCTRINE REFERENCE: {frame['doctrine_reference']}\n\n"
        f"FUSED DETECTION:\n"
        f"{json.dumps({k: v for k, v in fused.items() if not k.startswith('_')}, indent=2)}\n\n"
        f"RECOMMENDED COA: {decision.get('recommended_option_name', '?')} "
        f"({decision.get('recommended_tag', '?')})\n"
        f"OPERATOR'S TYPED CHOICE: \"{operator_choice}\"\n\n"
        "Score the decision against doctrine. JSON only."
    )

    def _try():
        content: list[dict[str, Any]] = [{"type": "text", "text": user_text}]
        if png_path is not None and Path(png_path).exists():
            content.append({
                "type": "image_url",
                "image_url": {"url": _png_to_data_url(Path(png_path)),
                                "detail": "high"},
            })
        for m in (VISION_MODEL, "gpt-4o-mini"):
            try:
                raw = chat(
                    [
                        {"role": "system", "content": SYSTEM_AAR},
                        {"role": "user", "content": content},
                    ],
                    model=m,
                    temperature=0.3,
                    max_tokens=500,
                    response_format={"type": "json_object"},
                )
                parsed = _coerce_json(raw)
                parsed["_source"] = "live"
                parsed.setdefault("doctrine_reference", frame["doctrine_reference"])
                return parsed
            except Exception:  # noqa: BLE001
                continue
        raise RuntimeError("aar chain exhausted")

    return _try_with_timeout(
        _try, timeout,
        _baseline_aar(frame, operator_choice,
                      decision.get("recommended_option_name", ""), fused),
    )
