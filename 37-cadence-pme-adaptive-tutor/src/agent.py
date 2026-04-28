"""CADENCE agent — three-stage adaptive PME tutoring pipeline.

Stage 1 (data load): Read the Marine's submission .docx + last 10 forum
                     posts + course rubric .xlsx + course doctrine list.

Stage 2 (chat_json): Per-Marine adaptive analysis. Returns:
    {
      "knowledge_gaps_identified": [...],
      "doctrinal_references_cited_correctly": int,
      "doctrinal_references_to_review": [...],
      "writing_competency_score": 0-5,
      "critical_thinking_indicators": [...],
      "recommended_study_questions": [3 tailored Qs],
      "peer_learning_suggestions": [...],
      "estimated_competency_alignment_pct": 0-100
    }

Stage 3 (chat / hero): Cache-first 1-page Adaptive Study Plan with daily
    learning targets for the next 7 days, doctrine-cite homework,
    rubric-aligned writing tips, and a Privacy-Act-and-DoDI-1322.35
    audit footer. Wall-clock-capped at 35s with deterministic baseline
    fallback.

All hero LLM calls follow AGENT_BRIEF_V2 §B (ThreadPoolExecutor + timeout
+ deterministic fallback) so the demo never spinner-locks.
"""
from __future__ import annotations

import concurrent.futures
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

APP_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = APP_ROOT.parents[1]
for p in (str(REPO_ROOT), str(APP_ROOT)):
    if p not in sys.path:
        sys.path.insert(0, p)

DATA_DIR = APP_ROOT / "data"
sys.path.insert(0, str(DATA_DIR))

from shared.kamiwaza_client import chat, chat_json  # noqa: E402
from src import audit, extract  # noqa: E402
from generate import (  # noqa: E402
    DOCTRINE_INDEX, baseline_analysis, baseline_study_plan,
)

CACHED_BRIEFS_PATH = DATA_DIR / "cached_briefs.json"
LIVE_BRIEF_PATH = DATA_DIR / "cached_brief_live.json"

ANALYSIS_TIMEOUT_S = 18.0
HERO_TIMEOUT_S = 35.0
HERO_MODEL = os.getenv("CADENCE_HERO_MODEL", "gpt-5.4")


# ---------------------------------------------------------------------------
# Loaders
# ---------------------------------------------------------------------------

def load_courses() -> list[dict]:
    return json.loads((DATA_DIR / "courses.json").read_text())["courses"]


def load_students() -> list[dict]:
    return json.loads((DATA_DIR / "students.json").read_text())["students"]


def load_doctrine_index() -> dict:
    return json.loads((DATA_DIR / "doctrine_index.json").read_text())


def load_cached_briefs() -> dict:
    if CACHED_BRIEFS_PATH.exists():
        return json.loads(CACHED_BRIEFS_PATH.read_text())
    return {}


def get_student(student_id: str) -> dict:
    for s in load_students():
        if s["student_id"] == student_id:
            return s
    raise KeyError(student_id)


def get_course(course_id: str) -> dict:
    for c in load_courses():
        if c["id"] == course_id:
            return c
    raise KeyError(course_id)


def load_submission_text(student_id: str) -> str:
    """Read this student's submission .docx via python-docx."""
    p = DATA_DIR / "submissions" / f"{student_id}_submission.docx"
    return extract.read_docx(p)


def load_assignment_text(course_id: str) -> str:
    p = DATA_DIR / "assignments" / f"{course_id}_instructions.docx"
    return extract.read_docx(p)


def load_rubric_rows(course_id: str) -> list[dict]:
    p = DATA_DIR / "rubrics" / f"{course_id}_rubric.xlsx"
    return extract.read_xlsx_rubric(p)


# ---------------------------------------------------------------------------
# Stage 2: per-Marine adaptive analysis (chat_json)
# ---------------------------------------------------------------------------

ANALYSIS_SYSTEM = """You are CADENCE, an AI Adaptive PME Tutor for a single United States Marine taking a Professional Military Education or PMOS course.

You will receive ONE Marine's:
  - rank, name, course
  - last 10 forum posts (each tagged with cognitive depth)
  - their .docx assignment submission (text)
  - the course's published rubric (axes + descriptors)
  - the course's primary doctrinal references

You will return STRICT JSON with this exact schema:

{
  "student_id": "string - exact ID provided",
  "course_id":  "string - exact ID provided",
  "knowledge_gaps_identified": ["e.g. 'Class V planning factors'", "..."],
  "doctrinal_references_cited_correctly": <int>,
  "doctrinal_references_to_review": ["MCWP 4-11 Ch 3", "MCRP 3-40D para 5"],
  "writing_competency_score": <float 0-5>,
  "critical_thinking_indicators": ["e.g. 'evaluates trade-offs'", "..."],
  "recommended_study_questions": [
    "<3 tailored questions that address THIS Marine's gaps>"
  ],
  "peer_learning_suggestions": ["<forum threads worth this Marine reading>"],
  "estimated_competency_alignment_pct": <int 0-100>,
  "cognitive_depth_observed": "recall | application | analysis | synthesis | evaluation"
}

Calibration:
  - "doctrinal_references_to_review" should ONLY contain references from the
    list of allowed doctrine provided in the user prompt. Never invent.
  - writing_competency_score: 5 means publishable; 3 means coherent;
    1 means incoherent.
  - estimated_competency_alignment_pct: percentage of rubric mastery this
    Marine has demonstrated against the course's published standards.
  - recommended_study_questions: 3 questions that directly target the gaps
    you identified. Each question must be answerable in 30-60 minutes of
    focused study.

Tone: SNCO instructor — direct, blameless on intent but firm on doctrine.
NEVER mention model names. Refer to yourself as CADENCE.
"""


def _build_analysis_prompt(student: dict, course: dict, submission_text: str,
                           assignment_text: str, rubric_rows: list[dict]) -> list[dict]:
    posts_text = "\n".join(
        f"  - [{p['depth']}] thread=\"{p['thread']}\": {p['body']}"
        for p in student.get("forum_posts", [])
    ) or "  (no forum posts on record)"
    rubric_text = "\n".join(
        f"  - {r['axis']} (weight {r['weight']}): "
        + " | ".join((r.get("descriptors") or [])[-3:])
        for r in rubric_rows
    ) or "  (rubric not loaded — use course primary axes)"
    allowed_doctrine = ", ".join(course["primary_doctrine"])
    user = (
        f"MARINE:\n  {student['name']} ({student['student_id']}, {student['rank']})\n\n"
        f"COURSE:\n  {course['name']} ({course['code']}) — {course.get('school','')}\n\n"
        f"ALLOWED DOCTRINE FOR REVIEW LIST (do not invent): {allowed_doctrine}\n\n"
        f"ASSIGNMENT INSTRUCTIONS (excerpt):\n{assignment_text[:1500]}\n\n"
        f"RUBRIC AXES:\n{rubric_text}\n\n"
        f"THIS MARINE'S SUBMISSION (.docx text):\n{submission_text[:3500]}\n\n"
        f"THIS MARINE'S LAST 10 FORUM POSTS:\n{posts_text}\n\n"
        "Analyze this Marine. Return JSON only."
    )
    return [
        {"role": "system", "content": ANALYSIS_SYSTEM},
        {"role": "user", "content": user},
    ]


def _call_chat_json_with_timeout(msgs: list[dict], timeout_s: float,
                                 schema_hint: str = "") -> dict | None:
    def _go() -> dict:
        return chat_json(msgs, schema_hint=schema_hint, temperature=0.2)
    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
            return ex.submit(_go).result(timeout=timeout_s)
    except (concurrent.futures.TimeoutError, Exception):
        return None


def analyze_marine(student: dict, course: dict, *,
                   live: bool = True) -> dict:
    """Stage 2 — adaptive analysis with deterministic baseline overlay."""
    base = baseline_analysis(student, course)

    if not live:
        return base

    submission = load_submission_text(student["student_id"])
    assignment = load_assignment_text(course["id"])
    rubric_rows = load_rubric_rows(course["id"])

    msgs = _build_analysis_prompt(student, course, submission, assignment, rubric_rows)
    raw = _call_chat_json_with_timeout(
        msgs, ANALYSIS_TIMEOUT_S,
        schema_hint=(
            '{"student_id":str,"course_id":str,"knowledge_gaps_identified":list,'
            '"doctrinal_references_cited_correctly":int,'
            '"doctrinal_references_to_review":list,'
            '"writing_competency_score":float,'
            '"critical_thinking_indicators":list,'
            '"recommended_study_questions":list,'
            '"peer_learning_suggestions":list,'
            '"estimated_competency_alignment_pct":int,'
            '"cognitive_depth_observed":str}'
        ),
    )
    if not raw:
        return base

    # Overlay LLM result on baseline (baseline is the source of truth for shape)
    out = dict(base)
    for key in (
        "knowledge_gaps_identified", "doctrinal_references_cited_correctly",
        "doctrinal_references_to_review", "writing_competency_score",
        "critical_thinking_indicators", "recommended_study_questions",
        "peer_learning_suggestions", "estimated_competency_alignment_pct",
        "cognitive_depth_observed",
    ):
        if raw.get(key) not in (None, [], ""):
            out[key] = raw[key]
    out["_source"] = "llm"
    return out


# ---------------------------------------------------------------------------
# Stage 3: hero "Adaptive Study Plan" (cache-first)
# ---------------------------------------------------------------------------

HERO_SYSTEM = """You are CADENCE — the AI Adaptive PME Tutor for a single United States Marine.

Compose a polished, ONE-PAGE Adaptive Study Plan in markdown for THIS Marine over the next 7 days. Use the structured analysis you are given. Use THIS exact section order:

  # Adaptive Study Plan — <Marine name>
  **Course:** <name>  · **Estimated competency alignment:** <pct>%  · **Cognitive depth observed:** <depth>

  ## Knowledge Gaps Identified
  ## Doctrinal References to Review
  ## 7-Day Learning Targets
    ### Day 1 — <theme>
      - <items>
      *Action:* <one-line action>
    ### Day 2 — ...
    ### ...
    ### Day 7 — Capstone
  ## Rubric-Aligned Writing Tips

End with a horizontal rule, then an audit footer that:
  - Names CADENCE as the originator
  - Carries the line: UNCLASSIFIED // FOR OFFICIAL USE — Military Education Records
  - States the records governance: Privacy Act of 1974 (5 U.S.C. § 552a)
    and DoDI 1322.35 "Military Education Records" (NOT FERPA — FERPA does
    not apply to active-duty military training)
  - States that the Marine's submissions, forum posts, and the analysis above
    never leave the accredited environment
  - States that the recommendation is SHA-256 chained in the audit log

Constraints:
  - Total length under ~600 words.
  - Each Day must have an *Action:* line.
  - Every doctrine reference you cite must be in the Allowed Doctrine list.
  - Tone: SNCO instructor — direct, blameless on intent, firm on doctrine.
  - Do NOT mention model names or providers. Refer to yourself as CADENCE.
"""


def _build_hero_prompt(student: dict, course: dict, analysis: dict) -> list[dict]:
    tr_manual = course.get("tr_manual", "")
    tr_codes = ", ".join(course.get("tr_event_codes", []))
    governing = course.get(
        "governing_authority",
        "Privacy Act of 1974 (5 U.S.C. § 552a) and DoDI 1322.35 \"Military Education Records\"",
    )
    user = (
        f"MARINE: {student['name']} ({student['student_id']}, {student['rank']})\n"
        f"COURSE: {course['name']} ({course['code']})\n"
        f"T&R / PME AUTHORITY: {tr_manual}\n"
        f"T&R EVENT CODES: {tr_codes}\n"
        f"RECORDS GOVERNANCE: {governing}\n"
        f"ALLOWED DOCTRINE: {', '.join(course['primary_doctrine'])}\n"
        f"RUBRIC AXES: {', '.join(course['rubric_axes'])}\n\n"
        f"ANALYSIS (Stage 2 chat_json output):\n{json.dumps(analysis, indent=2, default=str)}\n\n"
        f"DTG: {datetime.now(timezone.utc).strftime('%d%H%MZ %b %Y').upper()}\n\n"
        "Compose this Marine's 1-page Adaptive Study Plan now. Reference the "
        "T&R manual and at least one T&R event code where appropriate. Use "
        "the records-governance line verbatim in the footer."
    )
    return [
        {"role": "system", "content": HERO_SYSTEM},
        {"role": "user", "content": user},
    ]


def _call_chat_with_timeout(msgs: list[dict], timeout_s: float, **kw) -> str | None:
    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
            return ex.submit(lambda: chat(msgs, **kw)).result(timeout=timeout_s)
    except (concurrent.futures.TimeoutError, Exception):
        return None


def write_study_plan(student: dict, course: dict, analysis: dict, *,
                     hero: bool = True, use_cache: bool = True) -> str:
    """Stage 3: 1-page Adaptive Study Plan. Cache-first."""
    key = f"{student['student_id']}_{course['id']}"

    # 1. Live cache (most-recent regenerate)
    if use_cache and LIVE_BRIEF_PATH.exists():
        try:
            live = json.loads(LIVE_BRIEF_PATH.read_text())
            if live.get("key") == key and live.get("study_plan"):
                return live["study_plan"]
        except Exception:
            pass

    # 2. Pre-computed cache
    if use_cache:
        cached = load_cached_briefs()
        if key in cached and cached[key].get("study_plan"):
            return cached[key]["study_plan"]

    # 3. Hero LLM call
    msgs = _build_hero_prompt(student, course, analysis)
    if hero:
        text = _call_chat_with_timeout(
            msgs, HERO_TIMEOUT_S, model=HERO_MODEL, temperature=0.4
        )
        if text and "Adaptive Study Plan" in text:
            _save_live(key, text, source=HERO_MODEL)
            return text

    # 4. Fallback chain
    text = _call_chat_with_timeout(msgs, HERO_TIMEOUT_S, temperature=0.4)
    if text and "Adaptive Study Plan" in text:
        _save_live(key, text, source="default-chain")
        return text

    # 5. Deterministic baseline
    return baseline_study_plan(student, course, analysis)


def _save_live(key: str, study_plan: str, *, source: str) -> None:
    try:
        LIVE_BRIEF_PATH.write_text(json.dumps({
            "key": key,
            "study_plan": study_plan,
            "source": source,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }, indent=2))
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------

def run_pipeline(student_id: str, course_id: str, *,
                 hero: bool = True, live_analysis: bool = True) -> dict:
    """End-to-end Stage 1+2+3 with audit-log entries at every stage."""
    student = get_student(student_id)
    course = get_course(course_id)

    audit.append({
        "event": "TUTORING_SESSION_OPENED",
        "student_id": student_id,
        "course_id": course_id,
    })

    analysis = analyze_marine(student, course, live=live_analysis)
    audit.append({
        "event": "ADAPTIVE_ANALYSIS",
        "student_id": student_id,
        "course_id": course_id,
        "writing_competency_score": analysis.get("writing_competency_score"),
        "estimated_competency_alignment_pct":
            analysis.get("estimated_competency_alignment_pct"),
        "cognitive_depth_observed": analysis.get("cognitive_depth_observed"),
        "n_gaps": len(analysis.get("knowledge_gaps_identified", [])),
        "source": analysis.get("_source", "baseline"),
    })

    plan = write_study_plan(student, course, analysis, hero=hero)
    audit.append({
        "event": "STUDY_PLAN_GENERATED",
        "student_id": student_id,
        "course_id": course_id,
        "plan_sha256": audit.sha256_text(plan),
        "model_class": "hero" if hero else "default",
    })

    return {
        "student": student,
        "course": course,
        "analysis": analysis,
        "study_plan": plan,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


if __name__ == "__main__":
    out = run_pipeline("M001", "log_principles_paper",
                       hero=False, live_analysis=False)
    print("Marine:", out["student"]["name"])
    print("Course:", out["course"]["name"])
    print("Alignment:", out["analysis"]["estimated_competency_alignment_pct"])
    print("\n--- STUDY PLAN ---\n")
    print(out["study_plan"][:1500])
