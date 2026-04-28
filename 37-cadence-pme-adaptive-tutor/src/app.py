"""CADENCE — Real-Data Adaptive PME Tutor for Marines.
Streamlit app on port 3037. Student-facing sibling of LEARN (instructor-facing).

Run with:
    cd apps/37-cadence
    streamlit run src/app.py --server.port 3037 --server.headless true
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

APP_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = APP_ROOT.parents[1]
for p in (str(REPO_ROOT), str(APP_ROOT)):
    if p not in sys.path:
        sys.path.insert(0, p)

from shared.kamiwaza_client import BRAND  # noqa: E402
from src import agent, audit  # noqa: E402

# ---------------------------------------------------------------------------
# Page config + theme
# ---------------------------------------------------------------------------

st.set_page_config(
    page_title="CADENCE — Adaptive PME Tutor",
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
  .cad-tagline {{
    color: {BRAND['neon']};
    font-family: Helvetica, Arial, sans-serif;
    font-weight: 600;
    letter-spacing: 1.2px;
    text-transform: uppercase;
    font-size: 12px;
  }}
  .cad-headline {{
    color: #FFFFFF;
    font-family: Helvetica, Arial, sans-serif;
    font-weight: 700;
    font-size: 28px;
    line-height: 1.15;
    margin-top: 4px;
  }}
  .cad-card {{
    background: {BRAND['surface']};
    border: 1px solid {BRAND['border']};
    border-radius: 10px;
    padding: 14px 18px;
    margin-bottom: 10px;
  }}
  .cad-pill {{
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
  .cad-footer {{
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
  .cad-doctrine {{
    font-family: Menlo, monospace;
    color: {BRAND['neon']};
    font-size: 12px;
  }}
  .cad-quote {{
    border-left: 3px solid {BRAND['primary']};
    padding-left: 10px;
    color: #C7C7C7;
    font-style: italic;
    font-size: 13px;
    margin: 6px 0;
  }}
</style>
"""
st.markdown(CSS, unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def alignment_pill(pct: int) -> str:
    if pct >= 80:
        return f'<span class="cad-pill pill-green">{pct}%</span>'
    if pct >= 65:
        return f'<span class="cad-pill pill-amber">{pct}%</span>'
    return f'<span class="cad-pill pill-red">{pct}%</span>'


def writing_pill(score: float) -> str:
    if score >= 4.0:
        return f'<span class="cad-pill pill-green">{score:.1f}/5</span>'
    if score >= 2.5:
        return f'<span class="cad-pill pill-amber">{score:.1f}/5</span>'
    return f'<span class="cad-pill pill-red">{score:.1f}/5</span>'


def competency_progress_chart(analysis: dict, course: dict) -> go.Figure:
    """Plotly bar chart of estimated mastery per rubric axis (heuristic from
    the analysis: alignment % + writing score map onto the published axes)."""
    pct = analysis.get("estimated_competency_alignment_pct", 70)
    writing = analysis.get("writing_competency_score", 3.0)
    axes = course["rubric_axes"]
    # Spread the alignment + writing across the axes deterministically
    base = pct / 100.0 * 5.0  # to 0-5 scale
    scores = []
    for axis in axes:
        if "writing" in axis or "clarity" in axis or "alignment" in axis:
            scores.append(round(min(5, max(0, writing)), 2))
        elif "doctrinal" in axis:
            scores.append(round(min(5, max(0, base + 0.4)), 2))
        elif "critical" in axis or "thinking" in axis or "judgment" in axis or "systems" in axis:
            scores.append(round(min(5, max(0, base - 0.2)), 2))
        else:
            scores.append(round(min(5, max(0, base)), 2))

    pretty = [a.replace("_", " ").title() for a in axes]
    colors = [
        BRAND["primary"] if s >= 3.5 else
        ("#E0B341" if s >= 2.5 else "#FF6F66")
        for s in scores
    ]
    fig = go.Figure()
    fig.add_bar(
        x=scores, y=pretty, orientation="h",
        marker_color=colors,
        text=[f"{s:.1f}/5" for s in scores],
        textposition="outside",
        textfont=dict(color="#E8E8E8", size=12),
    )
    fig.update_layout(
        plot_bgcolor=BRAND["bg"],
        paper_bgcolor=BRAND["bg"],
        font=dict(color="#E8E8E8"),
        height=260,
        margin=dict(l=10, r=40, t=20, b=20),
        xaxis=dict(range=[0, 5.5], gridcolor="#222222",
                   tickfont=dict(color=BRAND["text_dim"])),
        yaxis=dict(tickfont=dict(color="#E8E8E8")),
    )
    return fig


def _audit_summary_inline(e: dict) -> str:
    if e.get("event") == "ADAPTIVE_ANALYSIS":
        return (f"writing={e.get('writing_competency_score','?')}, "
                f"align={e.get('estimated_competency_alignment_pct','?')}%, "
                f"depth={e.get('cognitive_depth_observed','?')}, "
                f"gaps={e.get('n_gaps','?')}, src={e.get('source','?')}")
    if e.get("event") == "STUDY_PLAN_GENERATED":
        return (f"plan_sha256={(e.get('plan_sha256') or '')[:24]}…, "
                f"model={e.get('model_class','?')}")
    if e.get("event") == "TUTORING_SESSION_OPENED":
        return f"opened by Marine"
    return ""


# ---------------------------------------------------------------------------
# Session state
# ---------------------------------------------------------------------------

if "result" not in st.session_state:
    st.session_state.result = None
if "selected_marine" not in st.session_state:
    st.session_state.selected_marine = None
if "selected_course" not in st.session_state:
    st.session_state.selected_course = None


# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------

with st.sidebar:
    st.markdown(
        f"<div class='cad-tagline'>{BRAND['footer']}</div>"
        f"<div class='cad-headline'>CADENCE</div>"
        f"<div style='color:{BRAND['text_dim']};font-size:12px;margin-top:6px;'>"
        "Adaptive PME Tutor for Marines<br/>1:1 student-facing companion"
        "</div>",
        unsafe_allow_html=True,
    )
    st.markdown("---")
    st.markdown("**MISSION FRAME**")
    st.markdown(
        "<span style='color:#9A9A9A;font-size:12px;'>"
        "<i>One-size-fits-all PME isn't working. The Marine taking the course needs "
        "a tutor who has read every one of their forum posts and every assignment "
        "they've turned in. CADENCE does that for every Marine in the schoolhouse.</i>"
        "</span>",
        unsafe_allow_html=True,
    )
    st.markdown("---")
    hero_on = st.toggle(
        "Hero study plan (Kamiwaza-deployed narrative model)",
        value=True,
        help="When ON, the Adaptive Study Plan uses the Kamiwaza-deployed hero model. When OFF, the standard chain.",
    )
    live_analysis = st.toggle(
        "Live LLM analysis (audit demo)",
        value=False,
        help="When ON, fires the Stage 2 chat_json analysis live (audited). Default OFF for snappy demo load.",
    )
    st.markdown("**DATASETS**")
    st.markdown(
        "<span style='color:#9A9A9A;font-size:12px;'>"
        "Plug-in for both NEW LOGCOM-portal datasets:<br/>"
        "• <b>LMS Course data sets</b> (.mbz Moodle 4.5+ exports)<br/>"
        "• <b>Student Written Assignment Examples</b> (PDF + xlsx + docx)<br/>"
        "Real-data swap: <code>data/load_real.py</code>."
        "</span>",
        unsafe_allow_html=True,
    )
    st.markdown("---")
    st.markdown(
        "<div style='color:#9A9A9A;font-size:11px;'>"
        "Tagline: <i>From Context to Action.</i><br/>"
        "Compliance posture: IL5/IL6 ready · NIPR/SIPR/JWICS deployable.<br/>"
        "Records governance: <b>Privacy Act of 1974 (5 U.S.C. § 552a) and "
        "DoDI 1322.35 'Military Education Records'</b> — NOT FERPA "
        "(FERPA does not apply to active-duty military training).<br/>"
        "Sibling app: LEARN (instructor-facing cohort dashboard)."
        "</div>",
        unsafe_allow_html=True,
    )


# ---------------------------------------------------------------------------
# Header + course/Marine selector
# ---------------------------------------------------------------------------

courses = agent.load_courses()
students = agent.load_students()

col_a, col_b = st.columns([0.65, 0.35])
with col_a:
    st.markdown(
        f"<div class='cad-tagline'>1:1 adaptive tutoring · grounded in this Marine's actual work</div>"
        f"<div class='cad-headline'>"
        f"This Marine. This course. This week's plan."
        f"</div>",
        unsafe_allow_html=True,
    )
with col_b:
    st.markdown(
        f"<div class='cad-card' style='text-align:right;'>"
        f"<div style='color:{BRAND['muted']};font-size:11px;letter-spacing:1px;'>CLASSIFICATION</div>"
        f"<div style='color:{BRAND['neon']};font-weight:700;letter-spacing:1.2px;'>UNCLASSIFIED // FOUO</div>"
        f"<div style='color:{BRAND['muted']};font-size:11px;letter-spacing:1px;margin-top:8px;'>POSTURE</div>"
        f"<div style='color:#FFFFFF;font-weight:700;'>On-prem · Privacy Act / DoDI 1322.35</div>"
        f"</div>",
        unsafe_allow_html=True,
    )

# Selectors
sel_l, sel_c, sel_r = st.columns([0.34, 0.34, 0.32])
with sel_l:
    course_label = {c["id"]: f"{c['name']} ({c['code']})" for c in courses}
    course_id = st.selectbox(
        "Select your course",
        options=[c["id"] for c in courses],
        format_func=lambda cid: course_label[cid],
        key="course_picker",
    )
with sel_c:
    # Match a Marine to the course's primary student
    matching = [s for s in students if s["primary_course_id"] == course_id] or students
    marine_label = {s["student_id"]: f"{s['name']} ({s['rank']})" for s in matching}
    marine_id = st.selectbox(
        "Marine logging in",
        options=[s["student_id"] for s in matching],
        format_func=lambda sid: marine_label.get(sid, sid),
        key="marine_picker",
    )
with sel_r:
    st.write("")
    st.write("")
    generate_clicked = st.button("GENERATE ADAPTIVE STUDY PLAN",
                                 use_container_width=True, type="primary",
                                 key="btn_generate")

# Resolve picks (if the matching list shrank, fall back gracefully)
selected_marine = next((s for s in students if s["student_id"] == marine_id),
                       students[0])
selected_course = next((c for c in courses if c["id"] == course_id), courses[0])

# ---------------------------------------------------------------------------
# Trigger the pipeline (cache-first under the hood)
# ---------------------------------------------------------------------------

if generate_clicked:
    with st.spinner("Stage 1/3 — reading this Marine's submission and forum posts …"):
        # nothing async; loaders return immediately
        pass
    with st.spinner("Stage 2/3 — adaptive analysis (chat_json) …"):
        analysis = agent.analyze_marine(selected_marine, selected_course,
                                        live=live_analysis)
        audit.append({
            "event": "TUTORING_SESSION_OPENED",
            "student_id": selected_marine["student_id"],
            "course_id": selected_course["id"],
        })
        audit.append({
            "event": "ADAPTIVE_ANALYSIS",
            "student_id": selected_marine["student_id"],
            "course_id": selected_course["id"],
            "writing_competency_score": analysis.get("writing_competency_score"),
            "estimated_competency_alignment_pct":
                analysis.get("estimated_competency_alignment_pct"),
            "cognitive_depth_observed": analysis.get("cognitive_depth_observed"),
            "n_gaps": len(analysis.get("knowledge_gaps_identified", [])),
            "source": analysis.get("_source", "baseline"),
        })
    with st.spinner("Stage 3/3 — drafting Adaptive Study Plan (Kamiwaza-deployed) …"):
        plan = agent.write_study_plan(selected_marine, selected_course, analysis,
                                      hero=hero_on)
        audit.append({
            "event": "STUDY_PLAN_GENERATED",
            "student_id": selected_marine["student_id"],
            "course_id": selected_course["id"],
            "plan_sha256": audit.sha256_text(plan),
            "model_class": "hero" if hero_on else "default",
        })
    st.session_state.result = {
        "student": selected_marine,
        "course": selected_course,
        "analysis": analysis,
        "study_plan": plan,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


# ---------------------------------------------------------------------------
# Default render (cache-first): pull baseline analysis + cached brief instantly
# ---------------------------------------------------------------------------

result = st.session_state.result
if not result:
    analysis = agent.baseline_analysis  # function — not what we want
    # use deterministic baseline immediately so demo isn't empty
    from generate import baseline_analysis as _ba
    analysis = _ba(selected_marine, selected_course)
    cached = agent.load_cached_briefs()
    key = f"{selected_marine['student_id']}_{selected_course['id']}"
    plan = (cached.get(key) or {}).get("study_plan") or \
        agent.baseline_study_plan(selected_marine, selected_course, analysis)
    generated_at = (cached.get(key) or {}).get("generated_at", "pre-computed cache")
else:
    analysis = result["analysis"]
    plan = result["study_plan"]
    generated_at = result["generated_at"]

# ---------------------------------------------------------------------------
# Top row — Marine card + analysis card
# ---------------------------------------------------------------------------

st.markdown("---")

c1, c2, c3 = st.columns([0.30, 0.36, 0.34])
with c1:
    posts = selected_marine.get("forum_posts", [])
    n_posts = len(posts)
    n_subs = len(selected_marine.get("submission_history", []))
    st.markdown(
        f"<div class='cad-card'>"
        f"<div style='color:{BRAND['muted']};font-size:11px;letter-spacing:1px;'>SIGNED IN MARINE</div>"
        f"<div style='font-size:18px;color:#FFFFFF;font-weight:700;margin-top:4px;'>"
        f"{selected_marine['name']}</div>"
        f"<div style='color:{BRAND['muted']};font-size:12px;'>"
        f"{selected_marine['student_id']} · {selected_marine['rank']} · "
        f"EDIPI {selected_marine['edipi_synth']}</div>"
        f"<div style='color:{BRAND['muted']};font-size:11px;letter-spacing:1px;margin-top:14px;'>"
        f"COURSE</div>"
        f"<div style='color:#FFFFFF;font-weight:700;'>{selected_course['name']}</div>"
        f"<div style='color:{BRAND['muted']};font-size:11px;'>{selected_course['school']}</div>"
        f"<div style='color:{BRAND['muted']};font-size:11px;letter-spacing:1px;margin-top:10px;'>"
        f"T&amp;R / PME AUTHORITY</div>"
        f"<div style='color:{BRAND['neon']};font-family:Menlo,monospace;font-size:11px;'>"
        f"{selected_course.get('tr_manual_short', selected_course.get('tr_manual', '—'))}</div>"
        f"<div style='color:{BRAND['muted']};font-size:10px;font-family:Menlo,monospace;'>"
        f"events: {', '.join(selected_course.get('tr_event_codes', [])) or '—'}</div>"
        f"<div style='color:{BRAND['muted']};font-size:11px;letter-spacing:1px;margin-top:14px;'>"
        f"ARTIFACTS THIS COURSE</div>"
        f"<div style='font-size:14px;color:#FFFFFF;font-weight:700;'>"
        f"{n_subs} submissions · {n_posts} forum posts</div>"
        f"</div>",
        unsafe_allow_html=True,
    )
with c2:
    st.markdown("#### Adaptive Analysis")
    st.markdown(
        f"<div class='cad-card'>"
        f"<div style='color:{BRAND['muted']};font-size:11px;letter-spacing:1px;'>"
        f"COMPETENCY ALIGNMENT</div>"
        f"<div style='font-size:20px;color:#FFFFFF;font-weight:700;margin-top:4px;'>"
        f"{analysis['estimated_competency_alignment_pct']}% "
        f"{alignment_pill(analysis['estimated_competency_alignment_pct'])}</div>"
        f"<div style='color:{BRAND['muted']};font-size:11px;letter-spacing:1px;margin-top:14px;'>"
        f"WRITING COMPETENCY</div>"
        f"<div style='font-size:16px;color:#FFFFFF;font-weight:700;margin-top:2px;'>"
        f"{analysis['writing_competency_score']:.1f}/5 "
        f"{writing_pill(analysis['writing_competency_score'])}</div>"
        f"<div style='color:{BRAND['muted']};font-size:11px;letter-spacing:1px;margin-top:14px;'>"
        f"COGNITIVE DEPTH OBSERVED</div>"
        f"<div style='font-size:14px;color:{BRAND['neon']};font-weight:700;margin-top:2px;text-transform:uppercase;'>"
        f"{analysis['cognitive_depth_observed']}</div>"
        f"<div style='color:{BRAND['muted']};font-size:11px;letter-spacing:1px;margin-top:14px;'>"
        f"DOCTRINAL CITES VERIFIED</div>"
        f"<div style='font-size:14px;color:#FFFFFF;font-weight:700;margin-top:2px;'>"
        f"{analysis['doctrinal_references_cited_correctly']}</div>"
        f"</div>",
        unsafe_allow_html=True,
    )
with c3:
    st.markdown("#### Rubric mastery (estimated)")
    st.plotly_chart(competency_progress_chart(analysis, selected_course),
                    use_container_width=True, key="comp_progress")
    st.caption(
        f"Five rubric axes for {selected_course['code']}. Click GENERATE for the "
        f"live LLM scoring path (audited)."
    )


# ---------------------------------------------------------------------------
# Knowledge gaps + doctrine to review + critical thinking + study questions
# ---------------------------------------------------------------------------

g_l, g_r = st.columns([0.5, 0.5])
with g_l:
    st.markdown(
        f"<div class='cad-card'>"
        f"<div style='color:{BRAND['muted']};font-size:11px;letter-spacing:1px;margin-bottom:6px;'>"
        f"KNOWLEDGE GAPS IDENTIFIED</div>"
        + "".join(
            f"<div style='font-size:13px;color:#E8E8E8;margin-top:4px;'>• {g}</div>"
            for g in analysis["knowledge_gaps_identified"]
        ) + f"</div>",
        unsafe_allow_html=True,
    )
    st.markdown(
        f"<div class='cad-card'>"
        f"<div style='color:{BRAND['muted']};font-size:11px;letter-spacing:1px;margin-bottom:6px;'>"
        f"DOCTRINAL REFERENCES TO REVIEW</div>"
        + "".join(
            f"<div class='cad-doctrine' style='margin-top:4px;'>→ {r}</div>"
            for r in analysis["doctrinal_references_to_review"]
        ) + f"</div>",
        unsafe_allow_html=True,
    )
with g_r:
    st.markdown(
        f"<div class='cad-card'>"
        f"<div style='color:{BRAND['muted']};font-size:11px;letter-spacing:1px;margin-bottom:6px;'>"
        f"CRITICAL THINKING INDICATORS</div>"
        + "".join(
            f"<div style='font-size:13px;color:#E8E8E8;margin-top:4px;'>✓ {i}</div>"
            for i in analysis["critical_thinking_indicators"]
        ) + f"</div>",
        unsafe_allow_html=True,
    )
    st.markdown(
        f"<div class='cad-card'>"
        f"<div style='color:{BRAND['muted']};font-size:11px;letter-spacing:1px;margin-bottom:6px;'>"
        f"RECOMMENDED STUDY QUESTIONS (3 tailored to your gaps)</div>"
        + "".join(
            f"<div style='font-size:13px;color:#E8E8E8;margin-top:6px;'>{i+1}. {q}</div>"
            for i, q in enumerate(analysis["recommended_study_questions"])
        ) + f"</div>",
        unsafe_allow_html=True,
    )

# Peer learning
st.markdown(
    f"<div class='cad-card'>"
    f"<div style='color:{BRAND['muted']};font-size:11px;letter-spacing:1px;margin-bottom:6px;'>"
    f"PEER LEARNING — FORUM THREADS WORTH READING</div>"
    + "".join(
        f"<div style='font-size:13px;color:#E8E8E8;margin-top:4px;'>• {t}</div>"
        for t in analysis["peer_learning_suggestions"]
    ) + f"</div>",
    unsafe_allow_html=True,
)

# ---------------------------------------------------------------------------
# Forum posts panel + submission excerpt
# ---------------------------------------------------------------------------

st.markdown("---")
st.markdown("### What CADENCE actually read")

ar_l, ar_r = st.columns([0.5, 0.5])
with ar_l:
    st.markdown("#### Your last 10 forum posts")
    posts = selected_marine.get("forum_posts", [])
    df = pd.DataFrame([
        {"depth": p["depth"], "thread": p["thread"], "post": p["body"][:140] + ("…" if len(p["body"]) > 140 else "")}
        for p in posts
    ])
    st.dataframe(df, use_container_width=True, hide_index=True, height=320)
with ar_r:
    st.markdown("#### Your latest .docx submission (extract)")
    submission = agent.load_submission_text(selected_marine["student_id"])
    if submission:
        st.markdown(
            f"<div class='cad-quote'>{submission[:1100].replace(chr(10), '<br/>')}…</div>",
            unsafe_allow_html=True,
        )
    else:
        st.info("No submission .docx on file for this Marine + course pairing.")
    st.caption("Read in-process via python-docx. Never leaves the accredited environment.")


# ---------------------------------------------------------------------------
# Hero — Adaptive Study Plan
# ---------------------------------------------------------------------------

st.markdown("---")
st.markdown("### Adaptive Study Plan — next 7 days")
st.caption(
    f"Generated {generated_at} · Cache-first; click GENERATE for the live hero call. "
    f"This Marine's submissions and forum posts never leave the accredited environment."
)

st.markdown("<div class='cad-card' style='padding:22px 30px;'>", unsafe_allow_html=True)
st.markdown(plan)
st.markdown("</div>", unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Audit chain
# ---------------------------------------------------------------------------

st.markdown("---")
st.markdown(
    "### Cryptographic audit chain "
    "(Privacy Act of 1974 / DoDI 1322.35 \"Military Education Records\")"
)
st.caption(
    "Every analysis CADENCE makes about a Marine is appended to a SHA-256-chained "
    "audit log. Records are governed by the Privacy Act of 1974 (5 U.S.C. § 552a) "
    "and DoDI 1322.35 \"Military Education Records\" — NOT FERPA (FERPA does not "
    "apply to active-duty military training). Any cognitive-developer / IG / SJA "
    "can replay how a study-plan recommendation was made months later — without "
    "the Marine's data ever leaving the accredited environment."
)

chain = audit.read_chain(limit=12)
if not chain:
    st.info("Audit chain is empty. Click GENERATE ADAPTIVE STUDY PLAN to seed the genesis entry.")
else:
    rows = []
    for e in chain:
        rows.append({
            "event": e.get("event", "?"),
            "marine": e.get("student_id", "—"),
            "course": e.get("course_id", "—"),
            "summary": _audit_summary_inline(e),
            "ts": (e.get("timestamp_utc", "") or "")[:19].replace("T", " "),
            "prev_hash": (e.get("prev_hash", "") or "")[:12] + "…",
            "entry_hash": (e.get("entry_hash", "") or "")[:12] + "…",
        })
    df = pd.DataFrame(rows)
    st.dataframe(df, use_container_width=True, hide_index=True, height=320)


# ---------------------------------------------------------------------------
# Footer
# ---------------------------------------------------------------------------

st.markdown(
    f"<div class='cad-footer'>"
    f"Powered by Kamiwaza · From Context to Action · "
    f"100% Data Containment — nothing ever leaves your accredited environment."
    f"</div>",
    unsafe_allow_html=True,
)
