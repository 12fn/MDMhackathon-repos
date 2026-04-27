"""EMBODIED — multimodal Marine training scenario coach.

Hero AI call: a vision-capable model ingests the egocentric still frame, the
trainee's typed action, and the scenario's doctrinal context, then returns a
structured JSON evaluation:

    {
      "action_classified_as": "tactical | hesitation | risky | doctrinally_correct",
      "score": 0-100,
      "doctrine_reference": str,
      "consequences_simulated": str,
      "coaching_feedback": str,
      "next_scenario_suggestion": str
    }

A second hero call writes a 1-page after-action review across multiple
attempts ("Egocentric Decision Brief"). Both calls are wrapped in
ThreadPoolExecutor timeouts with a deterministic baseline fallback so the
demo never spinner-locks (per AGENT_BRIEF_V2 §B).
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

from PIL import Image

# Allow `streamlit run src/app.py` and direct execution
ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from shared.kamiwaza_client import chat  # noqa: E402

# Vision-capable hero model. The shared client maps this to whatever the
# active provider serves (Kamiwaza VLM / OpenAI gpt-4o / Anthropic).
HERO_MODEL = os.getenv("EMBODIED_HERO_MODEL", "gpt-4o")
TIMEOUT_S_EVAL = int(os.getenv("EMBODIED_EVAL_TIMEOUT", "25"))
TIMEOUT_S_AAR = int(os.getenv("EMBODIED_AAR_TIMEOUT", "35"))


SYSTEM_PROMPT_EVAL = """You are EMBODIED, a Marine Corps egocentric training
scenario coach. You evaluate trainee decision-making at first-person
points-of-view (helmet-cam style stills) for events like building entries,
vehicle checkpoints, casualty triage, IED indicators, and night perimeter
contacts.

You are reviewing the SAME still the trainee just saw, plus their typed
intended action, plus the scenario's doctrinal context (MCWP / MCRP / TM
references, the canonical correct actions, the canonical common failures).

Your job: classify their action against doctrine, score 0-100, and write
2-3 sentences of coaching feedback that an E-7 or SNCO instructor would
recognize as tonally correct (direct, blameless on intent but firm on doctrine).

Hard rules:
- Never invent doctrinal references — use ONLY the doctrine_reference passed
  in the scenario.
- 'doctrinally_correct' requires the trainee response to match at least one
  of the correct_actions in spirit AND not match any common_failure.
- 'risky' is reserved for responses that match a common_failure or a use of
  force that is not doctrinally justified.
- 'hesitation' is for non-actions, freezing, or vague answers.
- 'tactical' is the middle ground — the right idea but missing a doctrinal step.
- Output ONLY valid JSON matching the schema. No prose, no code fences.

Schema:
{
  "action_classified_as": "tactical|hesitation|risky|doctrinally_correct",
  "score": <int 0-100>,
  "doctrine_reference": "<echo the passed scenario doctrine_reference>",
  "consequences_simulated": "<one short line: what happens to the friendly / civilian / mission>",
  "coaching_feedback": "<2-3 sentences in SNCO instructor voice>",
  "next_scenario_suggestion": "<one short line: what to repeat or progress to>"
}
"""


SYSTEM_PROMPT_AAR = """You are EMBODIED, a Marine Corps SNCO instructor writing
a one-page after-action review of a trainee's run through several egocentric
training scenarios. The trainee's callsign and per-scenario evaluations are
provided as JSON.

Tone: concise, direct, blameless on intent but firm on doctrine. Marines call
this a 'hot wash' — diagnostic, not punitive.

Output structure (Markdown):

## EGOCENTRIC DECISION BRIEF — <callsign>

**Attempts evaluated:** <n>

### PATTERNS OBSERVED
3-4 bullets on what shows up across multiple scenarios.

### STRENGTHS
2-3 bullets on what the trainee did well.

### GROWTH AREAS
3-4 bullets on doctrine gaps. Tie each to a specific MCWP/MCRP/TM reference.

### NEXT ITERATION
1 short paragraph: what to re-run, what to progress to, and what doctrinal
reading to issue.
"""


# ---------------------------------------------------------------------------
# Image utility
# ---------------------------------------------------------------------------
def _image_to_data_url(img: Image.Image, *, max_side: int = 768) -> str:
    img = img.convert("RGB")
    w, h = img.size
    if max(w, h) > max_side:
        scale = max_side / max(w, h)
        img = img.resize((int(w * scale), int(h * scale)), Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=85)
    return f"data:image/jpeg;base64,{base64.b64encode(buf.getvalue()).decode('ascii')}"


# ---------------------------------------------------------------------------
# Deterministic baseline (timeout fallback + offline path)
# ---------------------------------------------------------------------------
def _baseline_eval(scenario: dict, trainee_response: str) -> dict:
    text = trainee_response.lower()
    correct_hits = 0
    failure_hits = 0
    for a in scenario.get("correct_actions", []):
        for kw in _kw(a):
            if kw in text:
                correct_hits += 1
                break
    for a in scenario.get("common_failures", []):
        for kw in _kw(a):
            if kw in text:
                failure_hits += 1
                break
    raw = 50 + correct_hits * 12 - failure_hits * 18
    score = max(0, min(100, raw))
    if failure_hits >= 1:
        cls = "risky"
        consequences = "Action matches a documented common failure — likely casualty or escalation."
    elif score >= 80:
        cls = "doctrinally_correct"
        consequences = "Doctrinally sound; friendly survival likelihood high."
    elif score >= 60:
        cls = "tactical"
        consequences = "Acceptable, but a doctrinal step is missing."
    else:
        cls = "hesitation"
        consequences = "Indecisive — exposure window stays open."
    return {
        "action_classified_as": cls,
        "score": score,
        "doctrine_reference": scenario.get("doctrine_reference", ""),
        "consequences_simulated": consequences,
        "coaching_feedback": (
            f"Re-anchor on {scenario.get('doctrine_reference', 'the cited doctrine')}. "
            f"Prioritized step you can lead with next time: "
            f"{scenario.get('correct_actions', ['(see doctrine)'])[0]}"
        ),
        "next_scenario_suggestion": "Repeat this scenario with the corrected sequence; then progress.",
        "_source": "baseline",
    }


def _kw(s: str) -> list[str]:
    out: list[str] = []
    for w in re.split(r"[^a-zA-Z]+", s.lower()):
        if len(w) >= 4 and w not in {"with", "into", "your", "from", "this",
                                     "that", "then", "step", "they", "them",
                                     "their", "have", "will", "shall", "stay"}:
            out.append(w)
    return out


# ---------------------------------------------------------------------------
# Hero LLM evaluation — multimodal
# ---------------------------------------------------------------------------
def _user_block_for_eval(scenario: dict, trainee_response: str) -> str:
    return (
        f"SCENARIO TITLE: {scenario['title']}\n"
        f"EGOCENTRIC POV (what the trainee sees): {scenario['pov']}\n\n"
        f"DOCTRINE REFERENCE: {scenario['doctrine_reference']}\n\n"
        f"CANONICAL CORRECT ACTIONS:\n"
        + "\n".join(f"  - {a}" for a in scenario["correct_actions"])
        + "\n\nCANONICAL COMMON FAILURES:\n"
        + "\n".join(f"  - {a}" for a in scenario["common_failures"])
        + f"\n\nTRAINEE'S TYPED ACTION: \"{trainee_response}\"\n\n"
        "Evaluate per the system rules. Return ONLY the JSON object."
    )


def _parse_eval_json(raw: str, scenario: dict) -> dict:
    """Defensive JSON parse — strip code fences / leading prose."""
    s = raw.strip()
    # try direct
    try:
        return json.loads(s)
    except Exception:
        pass
    # try code-fence stripped
    m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", s, flags=re.S)
    if m:
        try:
            return json.loads(m.group(1))
        except Exception:
            pass
    # try first-bracket span
    m = re.search(r"(\{.*\})", s, flags=re.S)
    if m:
        try:
            return json.loads(m.group(1))
        except Exception:
            pass
    # final fallback — synthesize
    return {
        "action_classified_as": "tactical",
        "score": 60,
        "doctrine_reference": scenario.get("doctrine_reference", ""),
        "consequences_simulated": "Parser failed; live model returned non-JSON.",
        "coaching_feedback": raw[:300] if raw else "(no model output)",
        "next_scenario_suggestion": "Re-run the scenario.",
    }


def _live_eval(scenario: dict, trainee_response: str, frame_path: Path | None) -> dict:
    """Multimodal hero call. Returns parsed dict; raises on failure."""
    user_text = _user_block_for_eval(scenario, trainee_response)
    content: list[dict[str, Any]] = [{"type": "text", "text": user_text}]
    if frame_path is not None and frame_path.exists():
        img = Image.open(frame_path)
        content.append({
            "type": "image_url",
            "image_url": {"url": _image_to_data_url(img), "detail": "high"},
        })
    raw = chat(
        [
            {"role": "system", "content": SYSTEM_PROMPT_EVAL},
            {"role": "user", "content": content},
        ],
        model=HERO_MODEL,
        temperature=0.25,
        max_tokens=600,
    )
    parsed = _parse_eval_json(raw, scenario)
    parsed["_source"] = "live"
    # echo doctrine reference even if model dropped it
    parsed.setdefault("doctrine_reference", scenario.get("doctrine_reference", ""))
    return parsed


def evaluate_text_only(scenario: dict, trainee_response: str) -> dict:
    """Text-only path used by data/generate.py to pre-cache briefs.

    Avoids loading Pillow images during a non-interactive cache build (the
    images may not yet exist on first run). Same prompt, no image attached.
    """
    raw = chat(
        [
            {"role": "system", "content": SYSTEM_PROMPT_EVAL},
            {"role": "user", "content": _user_block_for_eval(scenario, trainee_response)
             + "\n\n(No image attached — text-only pre-cache run.)"},
        ],
        model=os.getenv("EMBODIED_PRECACHE_MODEL", "gpt-4o-mini"),
        temperature=0.25,
        max_tokens=500,
    )
    parsed = _parse_eval_json(raw, scenario)
    parsed["_source"] = "live-text-precache"
    return parsed


def evaluate(scenario: dict, trainee_response: str, frame_path: Path | None = None) -> dict:
    """Run the hero multimodal call with timeout + deterministic fallback.

    Pattern from AGENT_BRIEF_V2 §B (apps/05-meridian).
    """
    if not trainee_response.strip():
        return _baseline_eval(scenario, "")
    with ThreadPoolExecutor(max_workers=1) as ex:
        try:
            return ex.submit(_live_eval, scenario, trainee_response, frame_path).result(
                timeout=TIMEOUT_S_EVAL
            )
        except FutTimeout:
            out = _baseline_eval(scenario, trainee_response)
            out["consequences_simulated"] = "(timeout) " + out["consequences_simulated"]
            return out
        except Exception as e:  # noqa: BLE001
            out = _baseline_eval(scenario, trainee_response)
            out["consequences_simulated"] = f"(fallback: {type(e).__name__}) " + out["consequences_simulated"]
            return out


# ---------------------------------------------------------------------------
# After-action review — hero brief across attempts
# ---------------------------------------------------------------------------
def _baseline_aar(callsign: str, attempts: list[dict]) -> str:
    n = len(attempts)
    classes = [a["evaluation"]["action_classified_as"] for a in attempts]
    risky_n = classes.count("risky")
    correct_n = classes.count("doctrinally_correct")
    return (
        f"## EGOCENTRIC DECISION BRIEF — {callsign}\n\n"
        f"**Attempts evaluated:** {n}\n\n"
        f"### PATTERNS OBSERVED\n"
        f"- {correct_n} of {n} attempts assessed as doctrinally correct.\n"
        f"- {risky_n} of {n} attempts flagged as risky (matched a known common failure).\n"
        f"- Average score: {sum(a['evaluation']['score'] for a in attempts) / max(1, n):.0f}/100.\n\n"
        f"### STRENGTHS\n- Decisive engagement; no freeze responses.\n\n"
        f"### GROWTH AREAS\n"
        + "".join(
            f"- {a['evaluation'].get('coaching_feedback', '')}\n"
            for a in attempts if a["evaluation"]["action_classified_as"] != "doctrinally_correct"
        )
        + f"\n### NEXT ITERATION\nRe-rep the risky attempts with explicit step-by-step "
          f"doctrine narration before action.\n"
    )


def _live_aar(callsign: str, attempts: list[dict]) -> str:
    user_text = (
        f"Trainee callsign: {callsign}\n"
        f"Attempts ({len(attempts)}):\n"
        + json.dumps(attempts, indent=2)
        + "\n\nWrite the after-action brief per the system rules."
    )
    return chat(
        [
            {"role": "system", "content": SYSTEM_PROMPT_AAR},
            {"role": "user", "content": user_text},
        ],
        model=os.getenv("EMBODIED_AAR_MODEL", "gpt-4o-mini"),
        temperature=0.4,
        max_tokens=900,
    )


def after_action_review(callsign: str, attempts: list[dict]) -> str:
    """Hero AAR brief with timeout fallback. Returns Markdown."""
    if not attempts:
        return f"## EGOCENTRIC DECISION BRIEF — {callsign}\n\n_No attempts logged yet._"
    with ThreadPoolExecutor(max_workers=1) as ex:
        try:
            return ex.submit(_live_aar, callsign, attempts).result(timeout=TIMEOUT_S_AAR)
        except FutTimeout:
            return _baseline_aar(callsign, attempts) + "\n\n_(timeout — baseline brief shown)_"
        except Exception as e:  # noqa: BLE001
            return _baseline_aar(callsign, attempts) + f"\n\n_(fallback: {type(e).__name__})_"
