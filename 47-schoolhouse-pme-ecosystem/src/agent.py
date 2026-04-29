"""SCHOOLHOUSE agent — four drill types + role-aware tutor + hero brief.

Drill types
  1. Egocentric tactical decision  (multimodal — image + text)
  2. Visual ID                     (multimodal — image)
  3. Written assignment grading    (chat_json — rubric × draft)
  4. PA persona simulation         (chat_json — N personas in parallel)

Hero call
  ("gpt-5.4", 35s, cache-first) writes the Schoolhouse Intelligence Brief —
  cited against NAVMC 3500-series T&R Manual + MCO 1553.4B PME.

Role-aware reshape
  persona ∈ {student, instructor, co}. The brief is reshaped per persona.

Audit
  Every drill / brief append-only logged to audit_logs/schoolhouse_audit.jsonl
  with a SHA-256 chain (Privacy Act + DoDI 1322.35 governance — NOT FERPA).
"""
from __future__ import annotations

import base64
import concurrent.futures
import hashlib
import io
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from PIL import Image

APP_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = APP_ROOT.parents[1]
for p in (str(REPO_ROOT), str(APP_ROOT)):
    if p not in sys.path:
        sys.path.insert(0, p)

from shared.kamiwaza_client import chat, chat_json  # noqa: E402

DATA_DIR = APP_ROOT / "data"
SCENES_DIR = DATA_DIR / "scenes"
VID_DIR = DATA_DIR / "visual_id"
AUDIT_LOG = DATA_DIR / "audit_logs" / "schoolhouse_audit.jsonl"
CACHED_BRIEFS_PATH = DATA_DIR / "cached_briefs.json"

# Wall-clock caps — never let the demo block on the LLM.
PER_DRILL_TIMEOUT_S = 18.0
HERO_BRIEF_TIMEOUT_S = 35.0
PERSONA_PANEL_TIMEOUT_S = 12.0


# ─────────────────────────────────────────────────────────────────────────────
# Loaders (cached as plain module-level dict; cheap)
# ─────────────────────────────────────────────────────────────────────────────
def load_courses() -> list[dict]:
    return json.loads((DATA_DIR / "courses.json").read_text())


def load_scenes() -> list[dict]:
    return json.loads((DATA_DIR / "scenes_meta.json").read_text())


def load_visual_id() -> list[dict]:
    return json.loads((DATA_DIR / "visual_id_meta.json").read_text())


def load_personas() -> list[dict]:
    return json.loads((DATA_DIR / "personas.json").read_text())


def load_forum_posts() -> list[dict]:
    out: list[dict] = []
    with (DATA_DIR / "forum_posts.jsonl").open() as f:
        for ln in f:
            ln = ln.strip()
            if ln:
                out.append(json.loads(ln))
    return out


def load_competency_ts() -> list[dict]:
    out: list[dict] = []
    with (DATA_DIR / "competency_ts.jsonl").open() as f:
        for ln in f:
            ln = ln.strip()
            if ln:
                out.append(json.loads(ln))
    return out


def load_cached_briefs() -> dict:
    if CACHED_BRIEFS_PATH.exists():
        return json.loads(CACHED_BRIEFS_PATH.read_text())
    return {}


# ─────────────────────────────────────────────────────────────────────────────
# Audit chain (SHA-256 chained jsonl)
# ─────────────────────────────────────────────────────────────────────────────
def _sha256_text(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def _last_audit_hash() -> str:
    if not AUDIT_LOG.exists():
        return "0" * 64
    last = "0" * 64
    with AUDIT_LOG.open() as f:
        for ln in f:
            ln = ln.strip()
            if not ln:
                continue
            try:
                last = json.loads(ln).get("entry_hash", last)
            except json.JSONDecodeError:
                continue
    return last


def append_audit(entry: dict) -> dict:
    AUDIT_LOG.parent.mkdir(parents=True, exist_ok=True)
    body = {k: v for k, v in entry.items() if k != "entry_hash"}
    body["prev_hash"] = _last_audit_hash()
    body["timestamp_utc"] = datetime.now(timezone.utc).isoformat()
    body["entry_hash"] = _sha256_text(
        json.dumps(body, sort_keys=True, default=str)
    )
    with AUDIT_LOG.open("a") as f:
        f.write(json.dumps(body, default=str) + "\n")
    return body


def read_audit_chain(limit: int = 20) -> list[dict]:
    if not AUDIT_LOG.exists():
        return []
    out: list[dict] = []
    with AUDIT_LOG.open() as f:
        for ln in f:
            ln = ln.strip()
            if not ln:
                continue
            try:
                out.append(json.loads(ln))
            except json.JSONDecodeError:
                continue
    return out[-limit:][::-1]


# ─────────────────────────────────────────────────────────────────────────────
# Image utility
# ─────────────────────────────────────────────────────────────────────────────
def _image_to_data_url(img: Image.Image, *, max_side: int = 768) -> str:
    img = img.convert("RGB")
    w, h = img.size
    if max(w, h) > max_side:
        scale = max_side / max(w, h)
        img = img.resize((int(w * scale), int(h * scale)), Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=85)
    return f"data:image/jpeg;base64,{base64.b64encode(buf.getvalue()).decode('ascii')}"


def _parse_json_defensive(raw: str) -> dict | None:
    if not raw:
        return None
    s = raw.strip()
    try:
        return json.loads(s)
    except Exception:
        pass
    m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", s, flags=re.S)
    if m:
        try:
            return json.loads(m.group(1))
        except Exception:
            pass
    m = re.search(r"(\{.*\})", s, flags=re.S)
    if m:
        try:
            return json.loads(m.group(1))
        except Exception:
            pass
    return None


def _call_with_timeout(fn, timeout_s: float):
    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
            return ex.submit(fn).result(timeout=timeout_s)
    except (concurrent.futures.TimeoutError, Exception):
        return None


# ─────────────────────────────────────────────────────────────────────────────
# DRILL 1 — Egocentric tactical decision (multimodal)
# ─────────────────────────────────────────────────────────────────────────────
EGOCENTRIC_SYSTEM = """You are SCHOOLHOUSE, a USMC PME / PMOS instructor
running an egocentric (helmet-cam POV) tactical decision drill. You see the
SAME first-person frame the trainee just saw, plus their typed action, plus
the scenario's doctrinal context (MCWP / MCRP / TM / TCCC references, the
canonical correct actions, and the canonical common failures).

Score the action against doctrine. Map the result to a specific T&R event
code from NAVMC 3500.18 (Infantry T&R) or NAVMC 3500.58 (Logistics T&R) —
the user prompt will give you a recommended event code anchor. Tone:
direct, blameless on intent, firm on doctrine — what an E-7 SNCO instructor
would say.

Hard rules:
- Use ONLY the doctrine_reference passed in the scenario.
- 'doctrinally_correct' requires matching at least one correct_action in
  spirit AND not matching any common_failure.
- 'risky' = matches a common_failure or unjustified use of force.
- 'hesitation' = freezing, vague, or non-action.
- 'tactical' = right idea, missing a doctrinal step.

Output ONLY valid JSON. Schema:
{
  "action_classified_as": "tactical|hesitation|risky|doctrinally_correct",
  "score": <int 0-100>,
  "doctrine_reference": "<echo the passed scenario doctrine_reference>",
  "tr_event_scored": "<NAVMC 3500.x event code, e.g. INF-OPS-2001>",
  "consequences_simulated": "<one short line>",
  "coaching_feedback": "<2-3 sentences in SNCO instructor voice>",
  "next_iteration": "<one short line>"
}
"""


def _baseline_egocentric(scene: dict, response: str) -> dict:
    text = (response or "").lower()
    correct_hits = sum(1 for a in scene["correct_actions"]
                       if any(w in text for w in re.split(r"\W+", a.lower()) if len(w) >= 5))
    failure_hits = sum(1 for a in scene["common_failures"]
                       if any(w in text for w in re.split(r"\W+", a.lower()) if len(w) >= 5))
    raw = 50 + correct_hits * 12 - failure_hits * 18
    score = max(0, min(100, raw))
    if failure_hits >= 1:
        cls = "risky"
        cons = "Action matches a documented common failure — likely casualty or escalation."
    elif score >= 80:
        cls = "doctrinally_correct"
        cons = "Doctrinally sound; friendly survival likelihood high."
    elif score >= 60:
        cls = "tactical"
        cons = "Acceptable — but a doctrinal step is missing."
    else:
        cls = "hesitation"
        cons = "Indecisive — exposure window stays open."
    return {
        "action_classified_as": cls,
        "score": int(score),
        "doctrine_reference": scene.get("doctrine_reference", ""),
        "tr_event_scored": scene.get("tr_event", "T&R-EVENT-N/A"),
        "consequences_simulated": cons,
        "coaching_feedback": (
            f"Re-anchor on {scene.get('doctrine_reference', 'the cited doctrine')}. "
            f"Lead with: {scene['correct_actions'][0]}"
        ),
        "next_iteration": "Repeat scenario with the corrected sequence; then progress.",
        "_source": "baseline",
    }


def egocentric_evaluate(scene: dict, response: str,
                        *, frame_path: Path | None = None) -> dict:
    if not (response or "").strip():
        return _baseline_egocentric(scene, "")

    user_text = (
        f"SCENARIO TITLE: {scene['title']}\n"
        f"EGOCENTRIC POV: {scene['pov']}\n\n"
        f"DOCTRINE REFERENCE: {scene['doctrine_reference']}\n"
        f"RECOMMENDED T&R EVENT ANCHOR: {scene.get('tr_event','')}\n\n"
        f"CANONICAL CORRECT ACTIONS:\n"
        + "\n".join(f"  - {a}" for a in scene["correct_actions"])
        + "\n\nCANONICAL COMMON FAILURES:\n"
        + "\n".join(f"  - {a}" for a in scene["common_failures"])
        + f"\n\nTRAINEE'S TYPED ACTION: \"{response}\"\n\n"
        "Return ONLY the JSON object."
    )
    content: list[dict[str, Any]] = [{"type": "text", "text": user_text}]
    if frame_path is not None and frame_path.exists():
        try:
            img = Image.open(frame_path)
            content.append({
                "type": "image_url",
                "image_url": {"url": _image_to_data_url(img), "detail": "high"},
            })
        except Exception:
            pass

    def _go() -> dict | None:
        raw = chat(
            [{"role": "system", "content": EGOCENTRIC_SYSTEM},
             {"role": "user", "content": content}],
            model=os.getenv("SCHOOLHOUSE_VISION_MODEL", "gpt-4o"),
            temperature=0.25,
            max_tokens=600,
        )
        return _parse_json_defensive(raw)

    raw = _call_with_timeout(_go, PER_DRILL_TIMEOUT_S)
    if not raw:
        return _baseline_egocentric(scene, response)
    raw.setdefault("doctrine_reference", scene.get("doctrine_reference", ""))
    raw.setdefault("tr_event_scored", scene.get("tr_event", ""))
    raw["_source"] = "llm"
    return raw


# ─────────────────────────────────────────────────────────────────────────────
# DRILL 2 — Visual ID (vision only)
# ─────────────────────────────────────────────────────────────────────────────
VISUAL_ID_SYSTEM = """You are SCHOOLHOUSE, an all-source imagery analyst
training tool for USMC visual recognition (PID — Positive Identification)
of foreign and US military platforms.

Your audience is a Marine intelligence analyst trainee. Be specific. Cite
visible features by location on the platform (turret, glacis, road wheels,
tail boom, vertical stabilizer, wing planform, sensor ball). Never hedge
with empty filler. If uncertain between two close variants, name both and
say which features would disambiguate.

Output ONLY valid JSON. Schema:
{
  "asset_class": "<e.g. T-72B3>",
  "country_of_origin": "<e.g. Russian Federation>",
  "platform_type": "<MBT|IFV|Attack Helicopter|MALE UCAV|5th-gen Fighter|Loitering munition|...>",
  "confidence": <float 0.0-1.0>,
  "distinguishing_features": ["<3-5 short bullets, each citing a SPECIFIC visible feature + location>"],
  "similar_known_examples": ["<2-3 close ruled-out variants by exact name>"],
  "reasoning_steps": ["<4-6 numbered analyst-style observations leading to the ID>"],
  "releasability": "UNCLASSIFIED|UNCLASSIFIED//FOUO|CUI|CONFIDENTIAL|NOFORN",
  "releasability_rationale": "one sentence"
}
"""


def _baseline_visual_id(sample: dict) -> dict:
    return {
        "asset_class": sample["ground_truth"],
        "country_of_origin": sample["country"],
        "platform_type": sample["type"],
        "confidence": 0.55,
        "distinguishing_features": [sample["key_features"]],
        "similar_known_examples": [],
        "reasoning_steps": [
            "Baseline (no live vision call) — falling back to the SCHOOLHOUSE reference library.",
            f"Reference key features: {sample['key_features']}",
        ],
        "releasability": "UNCLASSIFIED//FOUO",
        "releasability_rationale": "Synthetic reference imagery; default conservative marking.",
        "_source": "baseline",
    }


def visual_id_evaluate(sample: dict, *, image_path: Path | None = None) -> dict:
    if image_path is None or not image_path.exists():
        return _baseline_visual_id(sample)
    try:
        img = Image.open(image_path)
    except Exception:
        return _baseline_visual_id(sample)

    user_text = (
        f"Identify the military platform in this image. Return JSON per the system schema. "
        f"For context, the SCHOOLHOUSE reference library notes this kind of platform is often "
        f"identified by features like: {sample['key_features']}\n\n"
        "Do NOT use the image filename or any caption — score on visible features only."
    )
    content = [
        {"type": "text", "text": user_text},
        {"type": "image_url",
         "image_url": {"url": _image_to_data_url(img), "detail": "high"}},
    ]

    def _go() -> dict | None:
        raw = chat(
            [{"role": "system", "content": VISUAL_ID_SYSTEM},
             {"role": "user", "content": content}],
            model=os.getenv("SCHOOLHOUSE_VISION_MODEL", "gpt-4o"),
            temperature=0.2,
            max_tokens=900,
        )
        return _parse_json_defensive(raw)

    raw = _call_with_timeout(_go, PER_DRILL_TIMEOUT_S)
    if not raw:
        return _baseline_visual_id(sample)
    raw["_source"] = "llm"
    return raw


# ─────────────────────────────────────────────────────────────────────────────
# DRILL 3 — Written assignment grading (rubric × draft, chat_json)
# ─────────────────────────────────────────────────────────────────────────────
WRITTEN_SYSTEM = """You are SCHOOLHOUSE, a USMC PME / PMOS instructor grading
a student's written paper against the published rubric. You will receive:
  - the assignment prompt
  - the rubric criteria (each with criterion_id, label, weight, and a 0-5 scale)
  - the student's draft (verbatim)
  - the governing T&R Manual or PME framework

Task: score each criterion 0-5, write 2-3 sentences of narrative feedback
per criterion citing the student's text, then a 0-5 overall writing-competency
score. Tone: SNCO instructor — direct, blameless, doctrine-anchored. Cite
specific phrases from the student's draft when justifying.

Records governance: Privacy Act of 1974 (5 U.S.C. § 552a) + DoDI 1322.35
'Military Education Records' — NOT FERPA. Do not say FERPA.

Return ONLY valid JSON, schema:
{
  "criterion_scores": [
    {"criterion_id":"C1","score":0-5,"feedback":"2-3 sentences citing the draft"}
  ],
  "weighted_score_0_5": <float>,
  "writing_competency_0_5": <float>,
  "overall_summary": "3-4 sentences — what worked, what to revise next",
  "tr_competency_notes": "<one line tying to the governing T&R / PME framework>",
  "rubric_anchored": true,
  "confidence": <float 0.0-1.0>
}
"""


def _baseline_written(course: dict, draft: str) -> dict:
    rubric = course["assignment"]["rubric_criteria"]
    wc = max(50, len(draft.split()))
    # Heuristic: longer + more cites = higher
    cites = sum(draft.count(tag) for tag in ("MCDP", "MCWP", "MCRP", "GCSS", "NAVMC", "TM "))
    base_score = min(5.0, 1.5 + (wc / 350) + (cites * 0.4))
    out = []
    for c in rubric:
        out.append({
            "criterion_id": c["id"],
            "score": round(min(5.0, base_score + (0.3 if "Doctrinal" in c["label"] else 0)), 2),
            "feedback": (
                f"Baseline scoring (no live LLM): {c['label']} — draft length {wc} words, "
                f"{cites} doctrine cites observed."
            ),
        })
    weighted = sum(s["score"] * c["weight"] for s, c in zip(out, rubric))
    return {
        "criterion_scores": out,
        "weighted_score_0_5": round(weighted, 2),
        "writing_competency_0_5": round(min(5.0, base_score), 2),
        "overall_summary": (
            "Baseline rubric pass: draft length and citation density used as proxy. "
            "Live LLM grading recommended for narrative feedback."
        ),
        "tr_competency_notes": f"Anchored to {course['tr_manual_short']}.",
        "rubric_anchored": True,
        "confidence": 0.5,
        "_source": "baseline",
    }


def written_grade(course: dict, draft: str) -> dict:
    if not (draft or "").strip():
        return _baseline_written(course, "")
    a = course["assignment"]
    rubric_text = "\n".join(
        f"  - {c['id']}  ({c['weight']:.0%}) — {c['label']}" for c in a["rubric_criteria"]
    )
    msgs = [
        {"role": "system", "content": WRITTEN_SYSTEM},
        {"role": "user", "content": (
            f"COURSE: {course['name']} ({course['code']})\n"
            f"GOVERNING T&R / PME FRAMEWORK: {course['tr_manual']}\n"
            f"INSTRUCTOR: {course['instructor']}\n\n"
            f"ASSIGNMENT: {a['title']}\n"
            f"RUBRIC ({a['rubric_xlsx']}):\n{rubric_text}\n\n"
            f"STUDENT DRAFT:\n\"\"\"\n{draft}\n\"\"\"\n\n"
            "Score each criterion. Return ONLY the JSON object."
        )},
    ]

    def _go() -> dict | None:
        try:
            return chat_json(
                msgs,
                schema_hint='{"criterion_scores":[{...}],"weighted_score_0_5":float,"writing_competency_0_5":float,"overall_summary":str,"tr_competency_notes":str,"rubric_anchored":bool,"confidence":float}',
                temperature=0.25,
            )
        except Exception:
            return None

    raw = _call_with_timeout(_go, PER_DRILL_TIMEOUT_S)
    if not isinstance(raw, dict):
        return _baseline_written(course, draft)
    raw["_source"] = "llm"
    return raw


# ─────────────────────────────────────────────────────────────────────────────
# DRILL 4 — PA persona simulation (5 personas in parallel, chat_json each)
# ─────────────────────────────────────────────────────────────────────────────
PERSONA_SYSTEM = """You are SCHOOLHOUSE — a USMC Public Affairs / Information
Operations training simulator. You will be given a single audience persona
profile and a Marine trainee's draft unit-internal PA message. Read the
message through the persona's worldview and emit strict-schema JSON.

Output ONLY valid JSON, no prose, no fences:
{
  "persona_id": "<verbatim from input>",
  "interpretation": "<one line — how this persona reads the message>",
  "trust_delta": <int -10 to +10>,
  "narrative_risk": "LOW|MEDIUM|HIGH",
  "predicted_action": "share|challenge|ignore|escalate|counter-message",
  "key_concerns_raised": ["<1-3 short bullets>"]
}
"""


def _baseline_persona(persona: dict, message: str) -> dict:
    msg = (message or "").lower()
    pos = sum(1 for p in persona.get("trigger_phrases_positive", []) if p.lower() in msg)
    neg = sum(1 for p in persona.get("trigger_phrases_negative", []) if p.lower() in msg)
    base = persona.get("trust_baseline", 0)
    delta = max(-10, min(10, base + 2 * pos - 2 * neg))
    if delta >= 4:
        risk, action = "LOW", "share"
    elif delta >= 0:
        risk, action = "MEDIUM", "ignore"
    elif delta >= -4:
        risk, action = "MEDIUM", "challenge"
    else:
        risk, action = "HIGH", "counter-message"
    concerns: list[str] = []
    for phrase in persona.get("trigger_phrases_negative", []):
        if phrase.lower() in msg:
            concerns.append(f'Triggered by phrase: "{phrase}".')
    if not concerns and delta < 0:
        concerns.append(f"Tone misaligned with values: {', '.join(persona.get('values', [])[:2])}.")
    if not concerns:
        concerns.append("Generally aligned; would still want named POC and next-update window.")
    return {
        "persona_id": persona["persona_id"],
        "interpretation": persona.get("lens", "Baseline interpretation."),
        "trust_delta": int(delta),
        "narrative_risk": risk,
        "predicted_action": action,
        "key_concerns_raised": concerns[:3],
        "_source": "baseline",
    }


def persona_simulate(personas: list[dict], message: str) -> list[dict]:
    """All N personas in parallel under per-call timeout."""
    baselines = [_baseline_persona(p, message) for p in personas]
    out: list[dict | None] = [None] * len(personas)

    def _one(i: int) -> tuple[int, dict]:
        msgs = [
            {"role": "system", "content": PERSONA_SYSTEM},
            {"role": "user", "content": (
                f"PERSONA:\n{json.dumps(personas[i], indent=2)}\n\n"
                f"TRAINEE'S DRAFT MESSAGE (verbatim):\n\"\"\"\n{message}\n\"\"\"\n\n"
                "Return ONLY the JSON object."
            )},
        ]
        try:
            raw = chat_json(
                msgs,
                schema_hint='{"persona_id":str,"interpretation":str,"trust_delta":int,"narrative_risk":str,"predicted_action":str,"key_concerns_raised":[str]}',
                temperature=0.35,
            )
        except Exception:
            return i, baselines[i]
        if not isinstance(raw, dict):
            return i, baselines[i]
        merged = dict(baselines[i])
        try:
            merged["trust_delta"] = max(-10, min(10, int(raw.get("trust_delta", merged["trust_delta"]))))
        except Exception:
            pass
        risk = str(raw.get("narrative_risk", "")).upper()
        if risk in {"LOW", "MEDIUM", "HIGH"}:
            merged["narrative_risk"] = risk
        action = str(raw.get("predicted_action", "")).lower()
        if action in {"share", "challenge", "ignore", "escalate", "counter-message"}:
            merged["predicted_action"] = action
        if isinstance(raw.get("interpretation"), str) and raw["interpretation"].strip():
            merged["interpretation"] = raw["interpretation"].strip()
        if isinstance(raw.get("key_concerns_raised"), list) and raw["key_concerns_raised"]:
            merged["key_concerns_raised"] = [str(x) for x in raw["key_concerns_raised"][:3]]
        merged["persona_id"] = personas[i]["persona_id"]
        merged["_source"] = "llm"
        return i, merged

    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as ex:
        futs = [ex.submit(_one, i) for i in range(len(personas))]
        for f in concurrent.futures.as_completed(futs):
            try:
                i, r = f.result(timeout=PERSONA_PANEL_TIMEOUT_S + 2)
                out[i] = r
            except Exception:
                continue
    for i, r in enumerate(out):
        if r is None:
            out[i] = baselines[i]
    return out  # type: ignore[return-value]


# ─────────────────────────────────────────────────────────────────────────────
# HERO BRIEF — Schoolhouse Intelligence Brief (cache-first, 35s, gpt-5.4)
# ─────────────────────────────────────────────────────────────────────────────
HERO_SYSTEM = """You are SCHOOLHOUSE — the AI cognitive-development analyst
for the USMC schoolhouse-in-a-box. You compose a one-page Schoolhouse
Intelligence Brief in markdown for the role specified in the user prompt
(student | instructor | school CO).

Records governance: Privacy Act of 1974 (5 U.S.C. § 552a) + DoDI 1322.35
'Military Education Records' — NOT FERPA. Do not use the word FERPA.

Anchor every brief to the governing T&R Manual or PME framework provided in
the user prompt:
  - NAVMC 3500.18 (Infantry T&R)
  - NAVMC 3500.58 (Logistics T&R)
  - MCO 1553.4B / DoDI 1322.35 (Enlisted PME — Sergeants Course at SNCO Academy
    Quantico is RESIDENT PME, distinct from the Squad Leader Course at SOI)

Persona-specific structure:

If persona = "instructor":
  Use these EXACT five paragraph headers in this order:
    ## PARA 1 — BLUF
    ## PARA 2 — TOP PERFORMER
    ## PARA 3 — STUDENTS AT RISK
    ## PARA 4 — CURRICULUM EFFECTIVENESS
    ## PARA 5 — RECOMMENDED INSTRUCTOR MOVES
  Then a competency map table at the end (Student × 4 competencies).

If persona = "student":
  Adaptive study plan with sections:
    ## BLUF
    ## Tonight (45 min)
    ## This Week
    ## Schoolhouse Read-back

If persona = "co":
  Schoolhouse health dashboard with sections:
    ## BLUF
    ## Curriculum Effectiveness
    ## Recommended CO Moves
    ## Schoolhouse Risk

Constraints:
  - Open with a single bold one-line headline (course name + cohort size).
  - Immediately under the headline, on its own line, state the governing T&R
    Manual / PME framework (e.g. "Anchored to NAVMC 3500.58 — Logistics T&R").
  - Be specific; cite student names + IDs from the input.
  - End with: "_UNCLASSIFIED // FOR OFFICIAL USE — Military Education Records
    governed by the Privacy Act of 1974 (5 U.S.C. § 552a) and DoDI 1322.35._"
  - Do NOT mention model names. Refer to yourself as SCHOOLHOUSE.
  - Total length under ~550 words.
"""


def _build_hero_prompt(course: dict, persona: str,
                       comp_summary: dict[str, dict[str, float]]) -> list[dict]:
    rows = []
    for s in course["students"]:
        c = comp_summary.get(s["student_id"], {})
        rows.append(
            f"  {s['student_id']} ({s['name']}, {s['rank']}, profile={s['profile']}): "
            f"CT={c.get('critical_thinking', 0):.1f} COMM={c.get('communication', 0):.1f} "
            f"DOCT={c.get('doctrinal_knowledge', 0):.1f} PS={c.get('problem_solving', 0):.1f}"
        )
    user = (
        f"PERSONA: {persona}\n\n"
        f"COURSE: {course['name']} ({course['code']})\n"
        f"SCHOOLHOUSE: {course['schoolhouse']}\n"
        f"INSTRUCTOR: {course['instructor']}\n"
        f"GOVERNING T&R / PME FRAMEWORK: {course['tr_manual']}\n"
        f"SAMPLE T&R EVENT ANCHORS: {', '.join(course['tr_event_examples'])}\n"
        f"ASSIGNMENT: {course['assignment']['title']}\n\n"
        f"COHORT COMPETENCY (current week, 0-5):\n" + "\n".join(rows) + "\n\n"
        f"DTG: {datetime.now(timezone.utc).strftime('%d%H%MZ %b %Y').upper()}\n\n"
        "Compose the Schoolhouse Intelligence Brief for the persona above."
    )
    return [
        {"role": "system", "content": HERO_SYSTEM},
        {"role": "user", "content": user},
    ]


def write_hero_brief(course: dict, persona: str = "instructor",
                     *, hero: bool = True, use_cache: bool = True) -> dict:
    """Cache-first. Returns {brief, source, generated_at}."""
    cid = course["course_id"]

    if use_cache:
        cached = load_cached_briefs()
        entry = (cached.get(cid) or {}).get(persona)
        if entry and entry.get("brief"):
            return {
                "brief": entry["brief"],
                "source": entry.get("source", "cache"),
                "generated_at": entry.get("generated_at",
                                          datetime.now(timezone.utc).isoformat()),
            }

    # Build comp summary from competency_ts (latest week per student/comp)
    ts = load_competency_ts()
    summary: dict[str, dict[str, float]] = {}
    for r in ts:
        if r["course_id"] != cid:
            continue
        sid = r["student_id"]
        summary.setdefault(sid, {})
        prev = summary[sid].get(r["competency"])
        if prev is None or r["week"] > prev:  # not perfect but cheap proxy
            summary[sid][r["competency"]] = r["score"]

    msgs = _build_hero_prompt(course, persona, summary)

    if hero:
        def _go_hero() -> str | None:
            try:
                return chat(msgs, model="gpt-5.4", temperature=0.4)
            except Exception:
                return None
        text = _call_with_timeout(_go_hero, HERO_BRIEF_TIMEOUT_S)
        if text and len(text) > 200:
            return {"brief": text, "source": "live-hero", "generated_at": datetime.now(timezone.utc).isoformat()}

    def _go_mini() -> str | None:
        try:
            return chat(msgs, temperature=0.4)
        except Exception:
            return None
    text = _call_with_timeout(_go_mini, HERO_BRIEF_TIMEOUT_S)
    if text and len(text) > 200:
        return {"brief": text, "source": "live-default", "generated_at": datetime.now(timezone.utc).isoformat()}

    # Final fallback: baseline cache
    cached = load_cached_briefs()
    entry = (cached.get(cid) or {}).get(persona) or {}
    return {
        "brief": entry.get("brief", "_(no brief available)_"),
        "source": "baseline",
        "generated_at": entry.get("generated_at", datetime.now(timezone.utc).isoformat()),
    }


# ─────────────────────────────────────────────────────────────────────────────
# Helper for the cohort heatmap (reused by app.py)
# ─────────────────────────────────────────────────────────────────────────────
def cohort_competency_summary(course: dict) -> dict[str, dict[str, float]]:
    cid = course["course_id"]
    ts = load_competency_ts()
    out: dict[str, dict[str, float]] = {s["student_id"]: {} for s in course["students"]}
    last_week: dict[tuple[str, str], int] = {}
    for r in ts:
        if r["course_id"] != cid:
            continue
        key = (r["student_id"], r["competency"])
        if r["week"] >= last_week.get(key, -1):
            last_week[key] = r["week"]
            out[r["student_id"]][r["competency"]] = r["score"]
    return out


if __name__ == "__main__":
    courses = load_courses()
    c = courses[0]
    print(f"Course: {c['name']}")
    summary = cohort_competency_summary(c)
    for sid, comp in summary.items():
        print(f"  {sid}: {comp}")
    out = write_hero_brief(c, persona="instructor", hero=False, use_cache=True)
    print(f"\nBrief source: {out['source']}\n")
    print(out["brief"][:600])
