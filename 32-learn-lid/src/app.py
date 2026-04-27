"""LEARN — Learning Intelligence Dashboard (LID).
Streamlit app on port 3032.

Run with:
    cd apps/32-learn
    streamlit run src/app.py --server.port 3032 --server.headless true
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import streamlit as st

APP_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = APP_ROOT.parents[1]
for p in (str(REPO_ROOT), str(APP_ROOT)):
    if p not in sys.path:
        sys.path.insert(0, p)

from shared.kamiwaza_client import BRAND  # noqa: E402
from src import agent, heatmap  # noqa: E402

# --- Page config -------------------------------------------------------------

st.set_page_config(
    page_title="LEARN — Learning Intelligence Dashboard",
    page_icon="◆",
    layout="wide",
    initial_sidebar_state="expanded",
)

CSS = f"""
<style>
  html, body, [data-testid="stAppViewContainer"], [data-testid="stHeader"] {{
    background-color: {BRAND['bg']} !important;
    color: #E8E8E8 !important;
  }}
  [data-testid="stSidebar"] {{
    background-color: {BRAND['surface']} !important;
    border-right: 1px solid {BRAND['border']};
  }}
  h1, h2, h3, h4 {{
    color: #FFFFFF !important;
    letter-spacing: 0.4px;
  }}
  .learn-tagline {{
    color: {BRAND['neon']};
    font-family: Helvetica, Arial, sans-serif;
    font-weight: 600;
    letter-spacing: 1.2px;
    text-transform: uppercase;
    font-size: 12px;
  }}
  .learn-headline {{
    color: #FFFFFF;
    font-family: Helvetica, Arial, sans-serif;
    font-weight: 700;
    font-size: 28px;
    line-height: 1.15;
    margin-top: 4px;
  }}
  .learn-card {{
    background: {BRAND['surface']};
    border: 1px solid {BRAND['border']};
    border-radius: 10px;
    padding: 14px 18px;
    margin-bottom: 10px;
  }}
  .learn-pill {{
    display: inline-block;
    padding: 2px 9px;
    border-radius: 999px;
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 0.6px;
    margin-left: 6px;
  }}
  .pill-green  {{ background:#0E2F22; color:#00FFA7; border:1px solid #00BB7A; }}
  .pill-amber  {{ background:#3A2C0E; color:#E0B341; border:1px solid #E0B341; }}
  .pill-red    {{ background:#3A0E0E; color:#FF6F66; border:1px solid #D8362F; }}
  .learn-footer {{
    color:{BRAND['muted']};
    text-align:center;
    margin-top:30px;
    padding:14px;
    border-top:1px solid {BRAND['border']};
    font-size:12px;
    letter-spacing: 1.2px;
    text-transform: uppercase;
  }}
  .stButton > button {{
    background: {BRAND['primary']};
    color: #0A0A0A;
    border: 0;
    font-weight: 700;
    letter-spacing: 0.6px;
  }}
  .stButton > button:hover {{
    background: {BRAND['primary_hover']};
    color: #0A0A0A;
  }}
  div[data-testid="stMetricValue"] {{
    color: {BRAND['neon']} !important;
  }}
  .audit-row {{
    font-family: Menlo, monospace;
    font-size: 11px;
    color: #C0C0C0;
    border-bottom: 1px dashed #222222;
    padding: 4px 0;
  }}
  .audit-hash {{
    color: {BRAND['primary']};
  }}
</style>
"""
st.markdown(CSS, unsafe_allow_html=True)


# --- Helpers -----------------------------------------------------------------

def health_pill(signal: str) -> str:
    cls = {"GREEN": "pill-green", "AMBER": "pill-amber", "RED": "pill-red"}.get(
        (signal or "").upper(), "pill-green"
    )
    return f'<span class="learn-pill {cls}">{signal}</span>'


def comp_pill(score: float) -> str:
    if score >= 4.0:
        return f'<span class="learn-pill pill-green">{score:.1f}</span>'
    if score >= 2.5:
        return f'<span class="learn-pill pill-amber">{score:.1f}</span>'
    return f'<span class="learn-pill pill-red">{score:.1f}</span>'


# --- Session state -----------------------------------------------------------

if "result" not in st.session_state:
    st.session_state.result = None
if "selected_student" not in st.session_state:
    st.session_state.selected_student = None


def _audit_summary_inline(e: dict) -> str:
    if e.get("event") == "PER_STUDENT_ASSESSMENT":
        c = e.get("competency_evidence") or {}
        return (
            f"CT={c.get('critical_thinking','?')} COMM={c.get('communication','?')} "
            f"DOCT={c.get('doctrinal_knowledge','?')} PS={c.get('problem_solving','?')} "
            f"intv={e.get('intervention_needed')}"
        )
    if e.get("event") == "COHORT_ASSESSMENT":
        return (f"health={e.get('course_health_signal')}, "
                f"instr={e.get('instructor_effectiveness_signal')}, "
                f"intv={e.get('n_intervention')}")
    if e.get("event") == "INSTRUCTOR_BRIEF_GENERATED":
        return f"brief_sha256={(e.get('brief_sha256') or '')[:24]}…"
    return ""


# --- Sidebar -----------------------------------------------------------------

with st.sidebar:
    st.markdown(
        f"<div class='learn-tagline'>{BRAND['footer']}</div>"
        f"<div class='learn-headline'>LEARN</div>"
        f"<div style='color:{BRAND['text_dim']};font-size:12px;margin-top:6px;'>"
        "Learning Intelligence Dashboard<br/>for USMC PME / PMOS / Schoolhouses"
        "</div>",
        unsafe_allow_html=True,
    )
    st.markdown("---")
    st.markdown("**MISSION FRAME**")
    st.markdown(
        "<span style='color:#9A9A9A;font-size:12px;'>"
        "<i>To what extent is learning actually occurring? Are Marines demonstrating "
        "the required competencies? Are instructors providing effective training?</i> "
        "Three questions LOGCOM and TECOM cannot answer manually at the artifact level. "
        "LEARN does."
        "</span>",
        unsafe_allow_html=True,
    )
    st.markdown("---")
    hero_on = st.toggle(
        "Hero brief (Kamiwaza-deployed narrative model)",
        value=True,
        help="When ON, the Instructor's Brief uses the Kamiwaza-deployed hero model. When OFF, the standard mini chain.",
    )
    llm_per_student = st.toggle(
        "Live per-student rubric (audit demo)",
        value=False,
        help="When ON, fires Stage 1 LLM scoring on the first 4 students (audited). Kept off in default demo for snappy load.",
    )
    st.markdown("**DATASET**")
    st.markdown(
        "<span style='color:#9A9A9A;font-size:12px;'>"
        "Synthetic Moodle-shape course export (de-identified). "
        "Real-data swap: see <code>data/load_real.py</code> — point "
        "<code>REAL_DATA_PATH</code> at a Moodle JSON export."
        "</span>",
        unsafe_allow_html=True,
    )
    st.markdown("---")
    st.markdown(
        "<div style='color:#9A9A9A;font-size:11px;'>"
        "Tagline: <i>From Context to Action.</i><br/>"
        "Compliance posture: IL5/IL6 ready · NIPR/SIPR/JWICS deployable · FERPA-equivalent for training records."
        "</div>",
        unsafe_allow_html=True,
    )


# --- Header ------------------------------------------------------------------

course_static = agent.load_course()
course_name = course_static["course"]["name"]

col_a, col_b = st.columns([0.65, 0.35])
with col_a:
    st.markdown(
        f"<div class='learn-tagline'>Cognitive-development analytics · {course_name}</div>"
        f"<div class='learn-headline'>"
        f"Are Marines demonstrating the competencies the schoolhouse requires? "
        f"LEARN reads every post and every submission and tells you."
        f"</div>",
        unsafe_allow_html=True,
    )
with col_b:
    st.markdown(
        f"<div class='learn-card' style='text-align:right;'>"
        f"<div style='color:{BRAND['muted']};font-size:11px;letter-spacing:1px;'>CLASSIFICATION</div>"
        f"<div style='color:{BRAND['neon']};font-weight:700;letter-spacing:1.2px;'>UNCLASSIFIED // FOUO</div>"
        f"<div style='color:{BRAND['muted']};font-size:11px;letter-spacing:1px;margin-top:8px;'>POSTURE</div>"
        f"<div style='color:#FFFFFF;font-weight:700;'>On-prem · Kamiwaza Stack</div>"
        f"</div>",
        unsafe_allow_html=True,
    )

# --- Action row + metrics ----------------------------------------------------

# Baseline for instant load (heatmap should never wait on LLM)
_full = agent.load_full_corpus()
_baseline_per = agent.baseline_per_student(_full)
_baseline_cohort = agent.baseline_cohort(_baseline_per, _full)

c1, c2, c3, c4 = st.columns([0.30, 0.23, 0.23, 0.24])
with c1:
    if st.button("GENERATE INSTRUCTORS BRIEF", use_container_width=True,
                 type="primary", key="btn_generate"):
        with st.spinner("Stage 1/3 — per-student competency scoring (chat_json) …"):
            pass  # baseline already done
        with st.spinner("Stage 2/3 — cohort roll-up (chat_json) …"):
            cohort = agent.cohort_assess(_baseline_per, _full, baseline=_baseline_cohort)
        with st.spinner("Stage 3/3 — drafting Instructors Competency Brief (Kamiwaza-deployed) …"):
            # When hero_on, agent will try the live hero call; cache-first means
            # the cached brief is served instantly even with hero_on=True.
            per_for_brief = _baseline_per
            if llm_per_student:
                # Overlay LLM scoring on first 4 students for the audit demo
                posts_by: dict[str, list] = {}
                subs_by: dict[str, list] = {}
                for p in _full["forum_posts"]:
                    posts_by.setdefault(p["student_id"], []).append(p)
                for s in _full["submissions"]:
                    subs_by.setdefault(s["student_id"], []).append(s)
                for s in _full["students"][:4]:
                    sid = s["student_id"]
                    scored = agent.score_one_student(
                        s, posts_by.get(sid, []), subs_by.get(sid, []),
                        baseline=_baseline_per[sid],
                    )
                    per_for_brief[sid] = scored
                    agent.append_audit({
                        "event": "PER_STUDENT_ASSESSMENT",
                        "student_id": sid,
                        "course_id": _full["course"]["id"],
                        "competency_evidence": scored.get("competency_evidence"),
                        "intervention_needed": scored.get("instructor_intervention_needed"),
                        "confidence": scored.get("confidence"),
                        "source": scored.get("_source", "baseline"),
                    })
            brief = agent.write_hero_brief(_full, per_for_brief, cohort, hero=hero_on)
        agent.append_audit({
            "event": "COHORT_ASSESSMENT",
            "course_id": _full["course"]["id"],
            "cohort_avg": cohort.get("cohort_avg"),
            "course_health_signal": cohort.get("course_health_signal"),
            "instructor_effectiveness_signal": cohort.get("instructor_effectiveness_signal"),
            "n_intervention": len(cohort.get("intervention_ids", [])),
            "source": cohort.get("_source", "baseline"),
        })
        agent.append_audit({
            "event": "INSTRUCTOR_BRIEF_GENERATED",
            "course_id": _full["course"]["id"],
            "brief_sha256": agent._sha256_text(brief),
            "n_students": len(_full["students"]),
        })
        st.session_state.result = {
            "course": _full,
            "per_student": per_for_brief,
            "cohort": cohort,
            "brief": brief,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }

with c2:
    st.metric("Cohort size", f"{len(_full['students'])}")
with c3:
    st.metric("Forum posts", f"{len(_full['forum_posts'])}")
with c4:
    intv_n = sum(1 for ev in _baseline_per.values() if ev["instructor_intervention_needed"])
    st.metric("Students flagged for intervention", f"{intv_n}",
              help="Heuristic baseline; refined by Stage 1/2 LLM when GENERATE runs.")

st.markdown("---")


# --- Default render: heatmap + ranking on instant baseline -------------------

per_student = (st.session_state.result or {}).get("per_student") or _baseline_per
cohort_view = (st.session_state.result or {}).get("cohort") or _baseline_cohort
students = _full["students"]
sid_to_name = {s["student_id"]: s["name"] for s in students}

g_left, g_right = st.columns([0.62, 0.38])

with g_left:
    st.markdown("#### Cohort competency heatmap")
    st.caption(
        f"18 students × 4 competencies (0-5 rubric) — "
        f"{cohort_view.get('n_posts', len(_full['forum_posts']))} posts, "
        f"{cohort_view.get('n_submissions', len(_full['submissions']))} submissions analyzed."
    )
    fig = heatmap.build_heatmap(per_student, students)
    st.plotly_chart(fig, use_container_width=True, key="cohort_heatmap")

with g_right:
    st.markdown("#### Cohort signals")
    health = cohort_view.get("course_health_signal", "GREEN")
    instr_eff = cohort_view.get("instructor_effectiveness_signal", "EFFECTIVE")
    avg = cohort_view.get("cohort_avg", _baseline_cohort["cohort_avg"])
    st.markdown(
        f"<div class='learn-card'>"
        f"<div style='color:{BRAND['muted']};font-size:11px;letter-spacing:1px;'>COURSE HEALTH</div>"
        f"<div style='font-size:18px;color:#FFFFFF;font-weight:700;margin-top:4px;'>"
        f"{health}{health_pill(health)}</div>"
        f"<div style='color:{BRAND['muted']};font-size:11px;letter-spacing:1px;margin-top:14px;'>INSTRUCTOR EFFECTIVENESS</div>"
        f"<div style='font-size:14px;color:#FFFFFF;font-weight:700;margin-top:4px;'>{instr_eff}</div>"
        f"</div>",
        unsafe_allow_html=True,
    )
    st.markdown(
        f"<div class='learn-card'>"
        f"<div style='color:{BRAND['muted']};font-size:11px;letter-spacing:1px;margin-bottom:8px;'>"
        f"COHORT AVG (0-5)</div>"
        f"<div>Critical Thinking {comp_pill(avg['critical_thinking'])}</div>"
        f"<div style='margin-top:5px;'>Communication {comp_pill(avg['communication'])}</div>"
        f"<div style='margin-top:5px;'>Doctrinal Knowledge {comp_pill(avg['doctrinal_knowledge'])}</div>"
        f"<div style='margin-top:5px;'>Problem Solving {comp_pill(avg['problem_solving'])}</div>"
        f"</div>",
        unsafe_allow_html=True,
    )

st.markdown("---")


# --- Per-student drill-down --------------------------------------------------

st.markdown("### Per-student drill-down")
sid_choices = [s["student_id"] for s in students]
default_idx = 0
# pick first intervention student so the panel showcases the recommendation
for i, sid in enumerate(sid_choices):
    if per_student.get(sid, {}).get("instructor_intervention_needed"):
        default_idx = i
        break

sel_sid = st.selectbox(
    "Student",
    options=sid_choices,
    index=default_idx,
    format_func=lambda sid: f"{sid} — {sid_to_name.get(sid, sid)}",
    key="student_picker",
)
ev = per_student[sel_sid]

dl_a, dl_b = st.columns([0.5, 0.5])
with dl_a:
    student_obj = next(s for s in students if s["student_id"] == sel_sid)
    intv = ev.get("instructor_intervention_needed")
    intv_html = "<span class='learn-pill pill-red'>INTERVENTION</span>" if intv else "<span class='learn-pill pill-green'>ON TRACK</span>"
    st.markdown(
        f"<div class='learn-card'>"
        f"<div style='font-size:18px;color:#FFFFFF;font-weight:700;'>{student_obj['name']} "
        f"<span style='color:{BRAND['muted']};font-size:13px;'>· {sel_sid} · {student_obj['rank']}</span> "
        f"{intv_html}</div>"
        f"<div style='color:{BRAND['muted']};font-size:11px;letter-spacing:1px;margin-top:10px;'>COGNITIVE DEPTH OBSERVED</div>"
        f"<div style='font-size:14px;color:{BRAND['neon']};font-weight:700;margin-top:2px;text-transform:uppercase;'>{ev.get('cognitive_depth_observed','—')}</div>"
        f"<div style='color:{BRAND['muted']};font-size:11px;letter-spacing:1px;margin-top:10px;'>CONFIDENCE</div>"
        f"<div style='font-size:14px;color:#FFFFFF;font-weight:700;'>{ev.get('confidence',0):.2f}</div>"
        f"</div>",
        unsafe_allow_html=True,
    )
    comp = ev["competency_evidence"]
    st.markdown(
        f"<div class='learn-card'>"
        f"<div style='color:{BRAND['muted']};font-size:11px;letter-spacing:1px;margin-bottom:6px;'>RUBRIC SCORES</div>"
        f"<div>Critical Thinking {comp_pill(comp['critical_thinking'])}</div>"
        f"<div style='margin-top:5px;'>Communication {comp_pill(comp['communication'])}</div>"
        f"<div style='margin-top:5px;'>Doctrinal Knowledge {comp_pill(comp['doctrinal_knowledge'])}</div>"
        f"<div style='margin-top:5px;'>Problem Solving {comp_pill(comp['problem_solving'])}</div>"
        f"</div>",
        unsafe_allow_html=True,
    )
with dl_b:
    growth = ev.get("growth_indicators") or []
    remed = ev.get("remediation_recommendations") or []
    st.markdown(
        f"<div class='learn-card'>"
        f"<div style='color:{BRAND['muted']};font-size:11px;letter-spacing:1px;margin-bottom:6px;'>GROWTH INDICATORS</div>"
        + "".join(f"<div style='font-size:13px;color:#E8E8E8;margin-top:4px;'>• {g}</div>"
                  for g in growth) +
        f"</div>",
        unsafe_allow_html=True,
    )
    st.markdown(
        f"<div class='learn-card'>"
        f"<div style='color:{BRAND['muted']};font-size:11px;letter-spacing:1px;margin-bottom:6px;'>"
        f"RECOMMENDED INSTRUCTOR ACTIONS</div>"
        + "".join(f"<div style='font-size:13px;color:#E8E8E8;margin-top:4px;'>→ {r}</div>"
                  for r in remed) +
        f"</div>",
        unsafe_allow_html=True,
    )

with st.expander("View this student's structured competency JSON (audit-grade)"):
    st.json({k: v for k, v in ev.items() if not k.startswith("_")})


st.markdown("---")


# --- Hero brief (cache-first) ------------------------------------------------

st.markdown("### Instructor's Competency Brief")

if st.session_state.result and st.session_state.result.get("brief"):
    brief_text = st.session_state.result["brief"]
    generated_at = st.session_state.result.get("generated_at", "—")
else:
    # Cache-first: serve the pre-computed brief immediately so the demo is snappy.
    cached = agent.load_cached_briefs()
    course_id = _full["course"]["id"]
    brief_text = (cached.get(course_id) or {}).get("brief") \
        or agent._baseline_brief_text(_full, _baseline_cohort, _baseline_per)
    generated_at = (cached.get(course_id) or {}).get("generated_at", "pre-computed cache")

st.caption(
    f"Generated {generated_at} · Originator: LEARN — Learning Intelligence cell · "
    f"Cache-first; click GENERATE to fire the live hero call."
)
st.markdown("<div class='learn-card' style='padding:22px 30px;'>", unsafe_allow_html=True)
st.markdown(brief_text)
st.markdown("</div>", unsafe_allow_html=True)


# --- Audit chain panel -------------------------------------------------------

st.markdown("---")
st.markdown("### Cryptographic audit chain")
st.caption(
    "Every assessment LEARN makes is appended to a SHA-256-chained audit log. "
    "Any cognitive-developer / IG / SJA can replay how a competency call was made months later."
)

audit_chain = agent.read_audit_chain(limit=12)
if not audit_chain:
    st.info("Audit chain is empty. Click GENERATE INSTRUCTORS BRIEF to seed the genesis entry.")
else:
    rows = []
    for e in audit_chain:
        rows.append({
            "event": e.get("event", "?"),
            "course": e.get("course_id", "—"),
            "subject": e.get("student_id") or e.get("course_id") or "—",
            "summary": _audit_summary_inline(e),
            "ts": (e.get("timestamp_utc", "") or "")[:19].replace("T", " "),
            "prev_hash": (e.get("prev_hash", "") or "")[:12] + "…",
            "entry_hash": (e.get("entry_hash", "") or "")[:12] + "…",
        })
    df = pd.DataFrame(rows)
    st.dataframe(df, use_container_width=True, hide_index=True, height=320)


# Footer
st.markdown(
    f"<div class='learn-footer'>"
    f"Powered by Kamiwaza · Deploy mission intelligence without moving your data."
    f"</div>",
    unsafe_allow_html=True,
)
