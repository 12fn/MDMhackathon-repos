"""LEARN agent — three-stage cache-first competency analysis pipeline.

Stage 1 (chat_json):  Per-student rubric scoring from forum posts + submissions.
Stage 2 (chat_json):  Cohort-level roll-up + assignment effectiveness ranking.
Stage 3 (chat / hero): Instructor's Competency Brief — narrative, polished,
                       cache-first, wall-clock-capped at 35s.

Every assessment append-only logged to audit_logs/learn_audit.jsonl with a
SHA-256 chain so any cognitive-developer / IG / SJA can replay how a
competency call was made months later.

Pattern lifted directly from apps/05-meridian/src/agent.py and
apps/10-sentinel/src/app.py (audit chain).
"""
from __future__ import annotations

import concurrent.futures
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Make `shared` importable regardless of where this is run from.
APP_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = APP_ROOT.parents[1]
for p in (str(REPO_ROOT), str(APP_ROOT)):
    if p not in sys.path:
        sys.path.insert(0, p)

from shared.kamiwaza_client import chat, chat_json  # noqa: E402

DATA_DIR = APP_ROOT / "data"
AUDIT_DIR = APP_ROOT / "audit_logs"
AUDIT_DIR.mkdir(parents=True, exist_ok=True)
AUDIT_LOG = AUDIT_DIR / "learn_audit.jsonl"
CACHED_BRIEFS_PATH = DATA_DIR / "cached_briefs.json"
LIVE_BRIEF_PATH = DATA_DIR / "cached_brief_live.json"  # written when user clicks Regenerate

PER_STUDENT_TIMEOUT_S = 18.0
COHORT_TIMEOUT_S = 18.0
HERO_TIMEOUT_S = 35.0


# --- Loaders -----------------------------------------------------------------

def load_course() -> dict:
    return json.loads((DATA_DIR / "course.json").read_text())


def load_posts() -> list[dict]:
    out = []
    with (DATA_DIR / "forum_posts.jsonl").open() as f:
        for ln in f:
            ln = ln.strip()
            if ln:
                out.append(json.loads(ln))
    return out


def load_submissions() -> list[dict]:
    out = []
    with (DATA_DIR / "assignments.jsonl").open() as f:
        for ln in f:
            ln = ln.strip()
            if ln:
                out.append(json.loads(ln))
    return out


def load_full_corpus() -> dict:
    """Composite shape that mirrors data/generate.generate(0)."""
    course = load_course()
    return {
        **course,
        "forum_posts": load_posts(),
        "submissions": load_submissions(),
    }


def load_cached_briefs() -> dict:
    if CACHED_BRIEFS_PATH.exists():
        return json.loads(CACHED_BRIEFS_PATH.read_text())
    return {}


# --- Audit chain (SHA-256) ---------------------------------------------------

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
    """Append a chained entry. entry_hash = sha256(json(prev_hash + body))."""
    body = {k: v for k, v in entry.items() if k != "entry_hash"}
    body["prev_hash"] = _last_audit_hash()
    body["timestamp_utc"] = datetime.now(timezone.utc).isoformat()
    body["entry_hash"] = _sha256_text(json.dumps(body, sort_keys=True, default=str))
    with AUDIT_LOG.open("a") as f:
        f.write(json.dumps(body, default=str) + "\n")
    return body


def read_audit_chain(limit: int = 25) -> list[dict]:
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
    return out[-limit:][::-1]  # newest first


# --- Baseline (deterministic, no LLM) ---------------------------------------

# Re-export from data/generate.py so the app + agent share a single baseline.
sys.path.insert(0, str(DATA_DIR))
from generate import (  # noqa: E402
    baseline_per_student, baseline_cohort, _baseline_brief_text, COURSE_VARIANTS,
)


# --- Stage 1: per-student structured-output competency scoring ---------------

PER_STUDENT_SYSTEM = """You are LEARN, an AI cognitive-development analyst supporting USMC PME and PMOS instructors.

You will receive ONE Marine student's forum posts and assignment submissions from a USMC training course. The course will be one of:
  - Infantry Officer Course (IOC) — governed by NAVMC 3500.18 Infantry Training & Readiness Manual
  - A PMOS pipeline (e.g. 04xx Logistics) — governed by the relevant NAVMC 3500-series T&R Manual (e.g. NAVMC 3500.58 Logistics, NAVMC 3500.44 Signals Intelligence)
  - Sergeants Course — RESIDENT PME at the SNCO Academy MCB Quantico for E-5 Sergeants, governed by MCO 1553.4B (PME Framework) and DoDI 1322.35 'Military Education'. NOTE: the Sergeants Course is DISTINCT from the Squad Leader Course (which is taught at SOI under the Infantry T&R / NAVMC 3500.18). Do not conflate the two.

The course's specific governing T&R Manual / PME framework will be supplied in the user prompt. Score the student's artifacts against the published USMC training-standard rubric anchored to that document.

Records governance for every assessment: Privacy Act of 1974 (5 U.S.C. § 552a) and DoDI 1322.35 'Military Education Records' — NOT FERPA.

Return STRICT JSON with this exact schema:

{
  "student_id": "string - exact ID provided",
  "competency_evidence": {
    "critical_thinking":   0-5,
    "communication":       0-5,
    "doctrinal_knowledge": 0-5,
    "problem_solving":     0-5
  },
  "cognitive_depth_observed": "recall | application | analysis | synthesis | evaluation",
  "growth_indicators": ["1-3 short observations of growth or stagnation, citing specific artifacts"],
  "remediation_recommendations": ["1-3 concrete instructor actions, e.g. '1:1 OPORD writing drill'"],
  "instructor_intervention_needed": true | false,
  "confidence": 0.0-1.0
}

Calibration:
  - 5/5 means demonstrated synthesis or evaluation across multiple artifacts.
  - 3/5 means consistent application-level work.
  - 1/5 means recall only, with gaps.
  - intervention=true if 2+ competencies are below 2.5, or if posts/submissions are sparse.

Be specific. Cite the artifact (post depth, assignment name, grade) when justifying. Never invent artifacts.
"""


def _build_per_student_prompt(student: dict, posts: list[dict],
                              subs: list[dict],
                              course_meta: dict | None = None) -> list[dict]:
    posts_text = "\n".join(
        f"  - [{p['depth']}, {p['word_count']}w] thread=\"{p['thread']}\": {p['body']}"
        for p in posts[:12]
    ) or "  (no forum posts on record)"
    subs_text = "\n".join(
        f"  - {s['assignment_name']} (rubric={s['rubric_axis']}, grade={s['grade']}, late={s['late']}): {s['excerpt'][:300]}"
        for s in subs
    ) or "  (no submissions on record)"
    cm = course_meta or {}
    course_header = (
        f"COURSE: {cm.get('name','(unspecified)')} ({cm.get('code','')})\n"
        f"GOVERNING T&R / PME FRAMEWORK: {cm.get('tr_manual','(unspecified)')}\n"
        f"SAMPLE T&R EVENT ANCHORS: {', '.join(cm.get('tr_event_examples', []) or []) or '(n/a)'}\n"
        f"RECORDS GOVERNANCE: Privacy Act of 1974 (5 U.S.C. § 552a) and DoDI 1322.35 "
        f"'Military Education Records'\n\n"
    ) if cm else ""
    user = (
        f"{course_header}"
        f"STUDENT:\n  {student['name']} ({student['student_id']}, {student['rank']})\n\n"
        f"FORUM POSTS:\n{posts_text}\n\n"
        f"ASSIGNMENT SUBMISSIONS:\n{subs_text}\n\n"
        "Score this student against the governing T&R / PME framework cited above. Return JSON only."
    )
    return [
        {"role": "system", "content": PER_STUDENT_SYSTEM},
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


def score_one_student(student: dict, posts: list[dict], subs: list[dict],
                      *, baseline: dict | None = None,
                      course_meta: dict | None = None) -> dict:
    """Stage 1 scoring with deterministic baseline overlay."""
    base = dict(baseline) if baseline else {}
    msgs = _build_per_student_prompt(student, posts, subs, course_meta=course_meta)
    raw = _call_chat_json_with_timeout(
        msgs, PER_STUDENT_TIMEOUT_S,
        schema_hint='{"student_id":str,"competency_evidence":{"critical_thinking":int,"communication":int,"doctrinal_knowledge":int,"problem_solving":int},"cognitive_depth_observed":str,"growth_indicators":list,"remediation_recommendations":list,"instructor_intervention_needed":bool,"confidence":float}',
    )
    if not raw:
        return base or {}
    # Overlay LLM keys onto baseline (baseline is the source of truth for shape)
    if base:
        out = dict(base)
        comp = raw.get("competency_evidence") or {}
        for k in ("critical_thinking", "communication",
                  "doctrinal_knowledge", "problem_solving"):
            try:
                out["competency_evidence"][k] = round(
                    max(0.0, min(5.0, float(comp.get(k, base["competency_evidence"][k])))),
                    2,
                )
            except (TypeError, ValueError):
                pass
        for key in ("cognitive_depth_observed", "growth_indicators",
                    "remediation_recommendations", "instructor_intervention_needed",
                    "confidence"):
            if raw.get(key) not in (None, [], ""):
                out[key] = raw[key]
        out["_source"] = "llm"
        return out
    return raw


# --- Stage 2: cohort-level structured roll-up --------------------------------

COHORT_SYSTEM = """You are LEARN, the cohort-level cognitive-development analyst.

You will receive the per-student competency scores from Stage 1, plus assignment grade summaries. Produce a cohort-level structured assessment.

Return STRICT JSON:

{
  "cohort_avg": {"critical_thinking":0-5,"communication":0-5,"doctrinal_knowledge":0-5,"problem_solving":0-5},
  "course_health_signal": "GREEN | AMBER | RED",
  "instructor_effectiveness_signal": "EFFECTIVE | MIXED | UNDER-PERFORMING",
  "assignment_effectiveness_ranking": [
      {"assignment_id": "Ax", "rank": 1, "note": "<= 1 sentence"}
  ],
  "top_performer_ids": ["S01", ...],
  "intervention_ids": ["S02", ...],
  "confidence": 0.0-1.0
}

Be calibrated. AMBER if 25-40% of students need intervention. RED if >40%.
Instructor effectiveness UNDER-PERFORMING only if cohort_avg has 2+ axes < 2.5 with adequate artifacts.
"""


def _build_cohort_prompt(per_student: dict[str, dict], assn_eff: list[dict]) -> list[dict]:
    rows = []
    for sid, ev in per_student.items():
        comp = ev["competency_evidence"]
        rows.append(
            f"  {sid}: CT={comp['critical_thinking']:.1f} COMM={comp['communication']:.1f} "
            f"DOCT={comp['doctrinal_knowledge']:.1f} PS={comp['problem_solving']:.1f} "
            f"depth={ev['cognitive_depth_observed']} intv={ev['instructor_intervention_needed']}"
        )
    assn_lines = [
        f"  {a['assignment_id']} ({a['rubric_axis']}): mean={a['mean_grade']:.1f}, n={a['n_submissions']}, spread={a['spread']}"
        for a in assn_eff
    ]
    user = (
        "PER-STUDENT SCORES:\n" + "\n".join(rows) + "\n\n"
        "ASSIGNMENT GRADE SUMMARY:\n" + "\n".join(assn_lines) + "\n\n"
        "Roll up to cohort level. Return JSON only."
    )
    return [
        {"role": "system", "content": COHORT_SYSTEM},
        {"role": "user", "content": user},
    ]


def cohort_assess(per_student: dict[str, dict], course: dict, *, baseline: dict | None = None) -> dict:
    base = dict(baseline) if baseline else {}
    msgs = _build_cohort_prompt(per_student, base.get("assignment_effectiveness", []))
    raw = _call_chat_json_with_timeout(
        msgs, COHORT_TIMEOUT_S,
        schema_hint='{"cohort_avg":{...},"course_health_signal":str,"instructor_effectiveness_signal":str,"assignment_effectiveness_ranking":list,"top_performer_ids":list,"intervention_ids":list,"confidence":float}',
    )
    if not raw:
        # synth derived signals on baseline
        lo_count = sum(1 for ev in per_student.values() if ev["instructor_intervention_needed"])
        share = lo_count / max(1, len(per_student))
        health = "RED" if share > 0.4 else ("AMBER" if share >= 0.25 else "GREEN")
        avg = base.get("cohort_avg", {})
        instr_eff = "UNDER-PERFORMING" if sum(1 for v in avg.values() if v < 2.5) >= 2 else (
            "MIXED" if sum(1 for v in avg.values() if v < 3.0) >= 2 else "EFFECTIVE"
        )
        return {
            **base,
            "course_health_signal": health,
            "instructor_effectiveness_signal": instr_eff,
            "confidence": 0.55,
            "_source": "baseline",
        }
    # Merge LLM result over baseline
    merged = {**base, **raw, "_source": "llm"}
    return merged


# --- Stage 3: hero "Instructor's Competency Brief" ---------------------------

HERO_SYSTEM = """You are LEARN — the AI Learning Intelligence analyst supporting a USMC PME / PMOS instructor.

Compose a polished, one-page **Instructor's Competency Brief** in markdown using THESE EXACT five paragraph headers, in this order:

  ## PARA 1 - COHORT COMPETENCY MAP
  ## PARA 2 - TOP PERFORMERS
  ## PARA 3 - STUDENTS NEEDING INSTRUCTOR INTERVENTION
  ## PARA 4 - ASSIGNMENT EFFECTIVENESS
  ## PARA 5 - RECOMMENDED CURRICULUM ADJUSTMENTS

Constraints:
  - Open with a single bold one-line headline ABOVE the paragraphs (course name + cohort size).
  - Immediately under the headline, on its own line, state the governing T&R Manual or PME framework provided in the user prompt (e.g. "Anchored to NAVMC 3500.18 — Infantry T&R Manual" or "Anchored to MCO 1553.4B / DoDI 1322.35 PME Framework"). Records governance is the Privacy Act of 1974 (5 U.S.C. § 552a) and DoDI 1322.35 'Military Education Records' — NOT FERPA. Do not use the word FERPA anywhere.
  - PARA 1: state cohort averages on all four competencies (0-5), explicitly tied to the T&R / PME framework cited. Identify the cohort's strongest and weakest competency. When a T&R event anchor is provided, cite at least one (e.g. "INF-MAN-1001").
  - PARA 2: name the top 3 performers by name and ID. Cite cognitive depth observed.
  - PARA 3: name every student needing intervention, with one specific recommended action per student.
  - PARA 4: identify the highest- and lowest-effectiveness assignments. For the lowest, propose a re-scoping fix.
  - PARA 5: 3-4 concrete curriculum adjustments. Be specific, tactical, and instructor-actionable.
  - Keep total length under ~500 words.
  - End with a single italic line: "_UNCLASSIFIED // FOR OFFICIAL USE — Military Education Records governed by the Privacy Act of 1974 (5 U.S.C. § 552a) and DoDI 1322.35._"
  - Do NOT mention model names. Do NOT use the word "AI" outside the title; refer to yourself as LEARN.
  - For Sergeants Course cohorts: it is RESIDENT PME at the SNCO Academy MCB Quantico for E-5 Sergeants. Do NOT call it "Sergeants School" or conflate it with the distinct Squad Leader Course (which is at SOI under NAVMC 3500.18).
"""


def _build_hero_prompt(course: dict, per_student: dict[str, dict],
                       cohort: dict) -> list[dict]:
    sid_to_name = {s["student_id"]: s["name"] for s in course["students"]}
    rows = []
    for sid, ev in per_student.items():
        comp = ev["competency_evidence"]
        rows.append(
            f"  {sid} ({sid_to_name.get(sid, sid)}): "
            f"CT={comp['critical_thinking']:.1f} COMM={comp['communication']:.1f} "
            f"DOCT={comp['doctrinal_knowledge']:.1f} PS={comp['problem_solving']:.1f}, "
            f"depth={ev['cognitive_depth_observed']}, intv={ev['instructor_intervention_needed']}"
        )
    cm = course["course"]
    user = (
        f"COURSE: {cm['name']} ({cm['code']})\n"
        f"SCHOOLHOUSE: {cm.get('schoolhouse','(unspecified)')}\n"
        f"GOVERNING T&R / PME FRAMEWORK: {cm.get('tr_manual','(unspecified)')}\n"
        f"SAMPLE T&R EVENT ANCHORS: {', '.join(cm.get('tr_event_examples', []) or []) or '(n/a)'}\n"
        f"RECORDS GOVERNANCE: Privacy Act of 1974 (5 U.S.C. § 552a) and DoDI 1322.35 "
        f"'Military Education Records' (NOT FERPA)\n"
        f"COHORT SIZE: {len(course['students'])}\n"
        f"COHORT SUMMARY: {json.dumps(cohort, default=str)}\n\n"
        f"PER-STUDENT SCORES:\n" + "\n".join(rows) + "\n\n"
        f"DTG: {datetime.now(timezone.utc).strftime('%d%H%MZ %b %Y').upper()}\n\n"
        "Compose the Instructor's Competency Brief now. Cite the governing T&R / PME "
        "framework explicitly under the headline."
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


def write_hero_brief(course: dict, per_student: dict[str, dict],
                     cohort: dict, *, hero: bool = True,
                     use_cache: bool = True) -> str:
    """Stage 3: narrative Instructor's Competency Brief.

    Strategy (so the demo never hangs):
      1. If a per-course cached brief exists in cached_briefs.json or live, serve it.
      2. Else fire the hero gpt-5.4 call under HERO_TIMEOUT_S wall-clock cap.
      3. On hero failure, fall back to the deterministic baseline brief.
    """
    course_id = course["course"]["id"]

    # 1. Cache hit
    if use_cache:
        if LIVE_BRIEF_PATH.exists():
            try:
                live = json.loads(LIVE_BRIEF_PATH.read_text())
                if live.get("course_id") == course_id and live.get("brief"):
                    return live["brief"]
            except Exception:
                pass
        cached = load_cached_briefs()
        if course_id in cached and cached[course_id].get("brief"):
            return cached[course_id]["brief"]

    # 2. Hero call
    msgs = _build_hero_prompt(course, per_student, cohort)
    if hero:
        text = _call_chat_with_timeout(
            msgs, HERO_TIMEOUT_S, model="gpt-5.4", temperature=0.4
        )
        if text and "PARA 1" in text:
            _save_live_brief(course_id, text, source="gpt-5.4")
            return text

    # 3. Standard mini chain
    text = _call_chat_with_timeout(msgs, HERO_TIMEOUT_S, temperature=0.4)
    if text and "PARA 1" in text:
        _save_live_brief(course_id, text, source="default-chain")
        return text

    # 4. Deterministic fallback
    return _baseline_brief_text(course, cohort, per_student)


def _save_live_brief(course_id: str, brief: str, *, source: str) -> None:
    try:
        LIVE_BRIEF_PATH.write_text(json.dumps({
            "course_id": course_id,
            "brief": brief,
            "source": source,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }, indent=2))
    except Exception:
        pass


# --- Orchestration -----------------------------------------------------------

def run_pipeline(*, hero: bool = True, llm_per_student: bool = False,
                 max_llm_students: int = 4) -> dict[str, Any]:
    """End-to-end pipeline.

    To keep demo latency under control, per-student LLM calls are OFF by default
    (the deterministic baseline is excellent + the hero brief is the showpiece).
    Setting llm_per_student=True overlays LLM scores on the first
    `max_llm_students` students for an audit-trail showcase.
    """
    course = load_full_corpus()
    posts = course["forum_posts"]
    subs = course["submissions"]

    # Build per-student baseline
    base_per = baseline_per_student(course)

    # Optionally overlay LLM per-student scoring on a few students for the demo
    if llm_per_student:
        posts_by_sid: dict[str, list[dict]] = {}
        subs_by_sid: dict[str, list[dict]] = {}
        for p in posts:
            posts_by_sid.setdefault(p["student_id"], []).append(p)
        for s in subs:
            subs_by_sid.setdefault(s["student_id"], []).append(s)
        for s in course["students"][:max_llm_students]:
            sid = s["student_id"]
            scored = score_one_student(
                s, posts_by_sid.get(sid, []), subs_by_sid.get(sid, []),
                baseline=base_per[sid],
            )
            base_per[sid] = scored
            append_audit({
                "event": "PER_STUDENT_ASSESSMENT",
                "student_id": sid,
                "course_id": course["course"]["id"],
                "competency_evidence": scored.get("competency_evidence"),
                "intervention_needed": scored.get("instructor_intervention_needed"),
                "confidence": scored.get("confidence"),
                "source": scored.get("_source", "baseline"),
            })

    # Cohort baseline + LLM overlay
    base_cohort = baseline_cohort(base_per, course)
    cohort = cohort_assess(base_per, course, baseline=base_cohort)
    append_audit({
        "event": "COHORT_ASSESSMENT",
        "course_id": course["course"]["id"],
        "cohort_avg": cohort.get("cohort_avg"),
        "course_health_signal": cohort.get("course_health_signal"),
        "instructor_effectiveness_signal": cohort.get("instructor_effectiveness_signal"),
        "n_intervention": len(cohort.get("intervention_ids", [])),
        "source": cohort.get("_source", "baseline"),
    })

    # Hero brief
    brief = write_hero_brief(course, base_per, cohort, hero=hero, use_cache=True)
    append_audit({
        "event": "INSTRUCTOR_BRIEF_GENERATED",
        "course_id": course["course"]["id"],
        "brief_sha256": _sha256_text(brief),
        "n_students": len(course["students"]),
    })

    return {
        "course": course,
        "per_student": base_per,
        "cohort": cohort,
        "brief": brief,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


if __name__ == "__main__":
    out = run_pipeline(hero=False, llm_per_student=False)
    print(f"Course: {out['course']['course']['name']}")
    print(f"Cohort avg: {out['cohort'].get('cohort_avg')}")
    print(f"Health: {out['cohort'].get('course_health_signal')}")
    print(f"Intervention list: {out['cohort'].get('intervention_ids')}")
    print("\n--- BRIEF ---\n")
    print(out["brief"][:1200])
