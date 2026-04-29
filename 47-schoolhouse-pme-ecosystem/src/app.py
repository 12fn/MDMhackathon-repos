"""SCHOOLHOUSE — Marine schoolhouse-in-a-box.

Streamlit app on port 3047. Single mono-page Streamlit (no separate backend).

Run:
    cd apps/47-schoolhouse
    streamlit run src/app.py --server.port 3047 --server.headless true \
        --server.runOnSave false --server.fileWatcherType none \
        --browser.gatherUsageStats false

Four drill types in one app:
    1. Egocentric tactical decision (multimodal — image + text)
    2. Visual ID                    (multimodal — image)
    3. Written assignment grading   (chat_json — rubric × draft)
    4. PA audience persona sim      (chat_json × N personas in parallel)

Three role personas (UI reshape):
    student | instructor | school CO

Hero call: cache-first Schoolhouse Intelligence Brief, persona-aware.
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

SCENES_DIR = APP_ROOT / "data" / "scenes"
VID_DIR = APP_ROOT / "data" / "visual_id"


# ─────────────────────────────────────────────────────────────────────────────
# Page config + CSS
# ─────────────────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="SCHOOLHOUSE — Marine Schoolhouse-in-a-Box",
    page_icon="https://www.kamiwaza.ai/hubfs/logo-light.svg",
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
  .block-container {{ padding-top: 1.4rem; padding-bottom: 0.5rem; max-width: 1600px; }}
  h1, h2, h3, h4 {{ color: #FFFFFF !important; letter-spacing: 0.4px; }}
  .sh-tagline {{
    color: {BRAND['neon']};
    font-family: Helvetica, Arial, sans-serif;
    font-weight: 600;
    letter-spacing: 1.2px;
    text-transform: uppercase;
    font-size: 12px;
  }}
  .sh-headline {{
    color: #FFFFFF;
    font-family: Helvetica, Arial, sans-serif;
    font-weight: 700;
    font-size: 28px;
    line-height: 1.15;
    margin-top: 4px;
  }}
  .sh-card {{
    background: {BRAND['surface']};
    border: 1px solid {BRAND['border']};
    border-radius: 10px;
    padding: 14px 18px;
    margin-bottom: 10px;
  }}
  .sh-pill {{
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
  .pill-blue   {{ background:#0E1F2F; color:#7AB8FF; border:1px solid #4A88BB; }}
  .sh-section-title {{
    color: {BRAND['primary']};
    text-transform: uppercase;
    letter-spacing: 0.12em;
    font-size: 11px;
    font-weight: 700;
    margin-bottom: 8px;
    margin-top: 14px;
  }}
  .sh-pov {{
    color: #DDDDDD; font-style: italic;
    font-size: 13.5px; line-height: 1.55;
    background: {BRAND['surface_high']}; border-left: 3px solid {BRAND['primary']};
    padding: 10px 14px; border-radius: 4px;
  }}
  .sh-classification {{
    display: inline-block; padding: 4px 12px; border-radius: 6px;
    font-family: 'SF Mono', Menlo, monospace; font-weight: 700;
    font-size: 12px; letter-spacing: 0.06em;
  }}
  .cls-doctrinally_correct {{ background: #073B27; color: #00FFA7; border: 1px solid #00BB7A; }}
  .cls-tactical            {{ background: #2A2618; color: #E0C870; border: 1px solid #6A5A20; }}
  .cls-hesitation          {{ background: #1A1A24; color: #8888AA; border: 1px solid #444466; }}
  .cls-risky               {{ background: #2A0F0F; color: #E07070; border: 1px solid #7A2020; }}
  .sh-banner-on-prem {{
    background: {BRAND['surface_high']}; border: 1px solid {BRAND['primary']};
    border-radius: 10px; padding: 12px 16px; margin-top: 10px;
    font-family: 'SF Mono', Menlo, monospace; font-size: 12px; color: #DDDDDD;
  }}
  .sh-footer {{
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
    border-radius: 8px;
    padding: 0.55rem 1.1rem;
  }}
  .stButton > button:hover {{
    background: {BRAND['primary_hover']};
    color: #0A0A0A;
  }}
  div[data-testid="stMetricValue"] {{ color: {BRAND['neon']} !important; }}
  .stTextArea textarea {{
    background: {BRAND['surface_high']} !important;
    color: #E6E6E6 !important;
    border: 1px solid {BRAND['border']} !important;
    font-family: 'SF Mono', Menlo, monospace !important;
    font-size: 13px !important;
  }}
  #MainMenu, footer {{ visibility: hidden; }}
</style>
"""
st.markdown(CSS, unsafe_allow_html=True)


# ─────────────────────────────────────────────────────────────────────────────
# Data load (cached)
# ─────────────────────────────────────────────────────────────────────────────
@st.cache_data(show_spinner=False)
def _load_courses() -> list[dict]:
    return agent.load_courses()


@st.cache_data(show_spinner=False)
def _load_scenes() -> list[dict]:
    return agent.load_scenes()


@st.cache_data(show_spinner=False)
def _load_visual_id() -> list[dict]:
    return agent.load_visual_id()


@st.cache_data(show_spinner=False)
def _load_personas() -> list[dict]:
    return agent.load_personas()


@st.cache_data(show_spinner=False)
def _load_forum_posts() -> list[dict]:
    return agent.load_forum_posts()


COURSES = _load_courses()
SCENES = _load_scenes()
VISUAL_ID = _load_visual_id()
PERSONAS = _load_personas()
FORUM_POSTS = _load_forum_posts()

# Default sample student draft (medium quality so the rubric has signal in BOTH directions)
SAMPLE_DRAFT = """The MAGTF's sustainment doctrine, articulated in MCDP-4, treats logistics as a
maneuver factor — co-equal with fires, command, force protection, and intelligence. In a
72-hour distributed sustainment scenario the planner who treats Class V and Class IX as
schedule items rather than maneuver factors will, by the second period of darkness, watch
his scheme of maneuver collapse for want of demand-signal latency reduction in GCSS-MC.

I assume the supported MEU is in a contested coastal regime, two days into a humanitarian
assistance / disaster response (HA/DR) follow-on after a peer denial action. I further
assume the MAGTF has degraded SATCOM and that GCSS-MC is sync-only every six hours.

My sustainment plan therefore pushes a forward LSA at the company echelon (not the
battalion) for the first 36 hours. Class III bulk is pre-positioned ashore at H-12. The
risk to mission is that the company-level LSA forces the battalion S-4 into a
distribution-by-exception posture; I accept this in trade for shorter sustainment
intervals at the rifle-company decision point. MCDP-4 page 2-7 supports this — sustainment
that arrives 'late but complete' has lost the engagement.

I would close this gap with a daily SUSTAINMENT SYNC drill — a 15-minute commander's
update at the company level — and would request the battalion XO own the GCSS-MC
demand-signal queue rather than delegating it to the warehousing chief.
"""

SAMPLE_PA_MESSAGE = """Marines and families of 2/8,

We are aware of the reports circulating on social media regarding an incident at the
North Range yesterday evening. Out of an abundance of caution, all live-fire training is
suspended pending review. We regret any inconvenience and we appreciate your patience as
we leverage all available resources to determine the facts. Operational details cannot
be shared at this time. The command remains committed to the safety of every Marine and
will continue to provide updates as appropriate.

Very respectfully,
The Command"""

SAMPLE_EGOCENTRIC = (
    "I begin shout-show-shove escalation of force, signal STOP at the warning line "
    "off-axis from the kill funnel, and call up the contact to higher in the same beat."
)


# ─────────────────────────────────────────────────────────────────────────────
# Session state
# ─────────────────────────────────────────────────────────────────────────────
if "persona" not in st.session_state:
    st.session_state.persona = "instructor"
if "course_idx" not in st.session_state:
    st.session_state.course_idx = 0
if "drill" not in st.session_state:
    st.session_state.drill = "Egocentric"
if "ego_eval" not in st.session_state:
    st.session_state.ego_eval = None
if "vid_eval" not in st.session_state:
    st.session_state.vid_eval = None
if "written_eval" not in st.session_state:
    st.session_state.written_eval = None
if "persona_eval" not in st.session_state:
    st.session_state.persona_eval = None
if "hero_brief" not in st.session_state:
    st.session_state.hero_brief = None


# ─────────────────────────────────────────────────────────────────────────────
# Sidebar — mission frame + persona switcher + course picker
# ─────────────────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown(
        f"<div class='sh-tagline'>{BRAND['footer']}</div>"
        f"<div class='sh-headline'>SCHOOLHOUSE</div>"
        f"<div style='color:{BRAND['text_dim']};font-size:12px;margin-top:6px;'>"
        f"Marine schoolhouse-in-a-box.<br/>Four drill types. One on-prem stack."
        f"</div>",
        unsafe_allow_html=True,
    )
    st.markdown("---")
    st.markdown("**MISSION FRAME**")
    st.markdown(
        f"<span style='color:#9A9A9A;font-size:12px;'>"
        f"<i>PME today is three disconnected systems and a tired NCO.</i> "
        f"SCHOOLHOUSE folds the LMS, the egocentric simulator, the vision-ID lab, "
        f"the written-assignment grader, and the PA training sim into one role-aware UI — "
        f"the same data, reshaped per role, on-prem behind the wire."
        f"</span>",
        unsafe_allow_html=True,
    )
    st.markdown("---")
    st.markdown("**ROLE (UI reshape)**")
    persona_choice = st.radio(
        "Role",
        options=["student", "instructor", "co"],
        format_func=lambda p: {"student": "Student (Marine)",
                               "instructor": "Instructor",
                               "co": "School CO"}[p],
        index=["student", "instructor", "co"].index(st.session_state.persona),
        key="persona_radio",
        label_visibility="collapsed",
    )
    if persona_choice != st.session_state.persona:
        st.session_state.persona = persona_choice
        st.session_state.hero_brief = None  # invalidate brief on persona switch

    st.markdown("**COURSE**")
    course_idx = st.selectbox(
        "Course",
        options=list(range(len(COURSES))),
        index=st.session_state.course_idx,
        format_func=lambda i: f"{COURSES[i]['code']} — {COURSES[i]['name'][:40]}",
        key="course_select",
        label_visibility="collapsed",
    )
    if course_idx != st.session_state.course_idx:
        st.session_state.course_idx = course_idx
        st.session_state.hero_brief = None

    st.markdown("---")
    st.markdown(
        f"<span style='color:#9A9A9A;font-size:12px;'>"
        f"<b>Datasets (4):</b><br/>"
        f"• Moodle .mbz course exports<br/>"
        f"• Student Written Assignment Examples<br/>"
        f"• Xperience-10M egocentric<br/>"
        f"• Military Object Detection<br/><br/>"
        f"<b>Records governance:</b> Privacy Act of 1974 (5 U.S.C. § 552a) and "
        f"DoDI 1322.35 'Military Education Records' — <i>NOT FERPA</i> "
        f"(FERPA is K-12 / higher-ed; Marines under active military training are "
        f"governed by the Privacy Act + DoDI 1322.35).<br/><br/>"
        f"<b>Posture:</b> IL5/IL6 ready · NIPR/SIPR/JWICS deployable · DDIL-tolerant."
        f"</span>",
        unsafe_allow_html=True,
    )

course = COURSES[st.session_state.course_idx]
persona = st.session_state.persona


# ─────────────────────────────────────────────────────────────────────────────
# Header
# ─────────────────────────────────────────────────────────────────────────────
header_left, header_right = st.columns([0.65, 0.35])
with header_left:
    persona_label = {"student": "Student view",
                     "instructor": "Instructor view",
                     "co": "School CO view"}[persona]
    st.markdown(
        f"<div class='sh-tagline'>{persona_label} · {course['name']}</div>"
        f"<div class='sh-headline'>"
        f"PME today is three disconnected systems and a tired NCO. "
        f"SCHOOLHOUSE folds them into one role-aware UI — on-prem."
        f"</div>",
        unsafe_allow_html=True,
    )
with header_right:
    st.markdown(
        f"<div class='sh-card' style='text-align:right;'>"
        f"<div style='color:{BRAND['muted']};font-size:11px;letter-spacing:1px;'>CLASSIFICATION</div>"
        f"<div style='color:{BRAND['neon']};font-weight:700;letter-spacing:1.2px;'>UNCLASSIFIED // FOUO</div>"
        f"<div style='color:{BRAND['muted']};font-size:11px;letter-spacing:1px;margin-top:8px;'>POSTURE</div>"
        f"<div style='color:#FFFFFF;font-weight:700;'>On-prem · Kamiwaza Stack</div>"
        f"<div style='color:{BRAND['muted']};font-size:11px;letter-spacing:1px;margin-top:8px;'>ANCHOR</div>"
        f"<div style='color:#FFFFFF;font-weight:700;font-size:12px;'>{course['tr_manual_short']}</div>"
        f"</div>",
        unsafe_allow_html=True,
    )

# Top metrics row
m1, m2, m3, m4 = st.columns(4)
with m1:
    st.metric("Cohort size", len(course["students"]))
with m2:
    course_posts = [p for p in FORUM_POSTS if p["course_id"] == course["course_id"]]
    st.metric("Forum posts", len(course_posts))
with m3:
    intv_n = sum(1 for s in course["students"] if s["profile"] == "needs_remediation")
    st.metric("Flagged for intervention", intv_n)
with m4:
    st.metric("T&R event anchors", len(course["tr_event_examples"]))

st.markdown("---")


# ─────────────────────────────────────────────────────────────────────────────
# DRILL SELECTOR (4 tabs)
# ─────────────────────────────────────────────────────────────────────────────
st.markdown("### Drill bay")
st.caption(
    "Four drill types in one app — egocentric tactical / visual ID / written assignment / "
    "PA persona simulation. The same on-prem multimodal stack scores all four."
)

tab_ego, tab_vid, tab_written, tab_pa = st.tabs([
    "1. Egocentric tactical decision",
    "2. Visual ID",
    "3. Written assignment grading",
    "4. PA audience persona sim",
])


# ─────────── DRILL 1 — EGOCENTRIC ───────────
with tab_ego:
    e_left, e_right = st.columns([1.1, 1.0])
    with e_left:
        st.markdown('<div class="sh-section-title">SELECT EGOCENTRIC SCENE</div>',
                    unsafe_allow_html=True)
        scn_idx = st.selectbox(
            "Scene",
            options=list(range(len(SCENES))),
            index=1,  # default to vehicle checkpoint (visually rich)
            format_func=lambda i: f"{i+1:02d}  •  {SCENES[i]['title']}",
            key="ego_scn",
            label_visibility="collapsed",
        )
        scn = SCENES[scn_idx]
        frame_path = SCENES_DIR / f"{scn['id']}.png"
        if frame_path.exists():
            st.image(str(frame_path), use_container_width=True,
                     caption=f"{scn['id']} · {scn['title']} · helmet-cam POV")
        st.markdown('<div class="sh-section-title">SCENARIO POV</div>',
                    unsafe_allow_html=True)
        st.markdown(f'<div class="sh-pov">{scn["pov"]}</div>',
                    unsafe_allow_html=True)
        st.markdown('<div class="sh-section-title">DOCTRINE REFERENCE</div>',
                    unsafe_allow_html=True)
        st.caption(f"{scn['doctrine_reference']}  ·  T&R event anchor: {scn['tr_event']}")

    with e_right:
        st.markdown('<div class="sh-section-title">WHAT WOULD YOU DO?</div>',
                    unsafe_allow_html=True)
        ego_response = st.text_area(
            "Type your action",
            value=SAMPLE_EGOCENTRIC,
            height=120,
            key=f"ego_resp_{scn['id']}",
            label_visibility="collapsed",
        )
        if st.button("EVALUATE ACTION  →", use_container_width=True, key="ego_btn"):
            with st.spinner("Multimodal coach reading the frame + your action against doctrine…"):
                ev = agent.egocentric_evaluate(scn, ego_response, frame_path=frame_path)
            st.session_state.ego_eval = {"scn_id": scn["id"], "title": scn["title"],
                                          "response": ego_response, "evaluation": ev}
            agent.append_audit({
                "event": "EGOCENTRIC_DRILL",
                "course_id": course["course_id"],
                "scene_id": scn["id"],
                "tr_event_scored": ev.get("tr_event_scored"),
                "score": ev.get("score"),
                "classification": ev.get("action_classified_as"),
                "source": ev.get("_source", "unknown"),
            })

        ev_show = st.session_state.ego_eval
        if ev_show is None or ev_show["scn_id"] != scn["id"]:
            st.markdown(
                '<div class="sh-card" style="color:#9A9A9A;">'
                'Type your action and click <b>EVALUATE</b>. A multimodal coach reads the '
                'frame, the response, and the doctrine — then writes coaching feedback in '
                'an SNCO instructor voice.'
                '</div>',
                unsafe_allow_html=True,
            )
        else:
            ev = ev_show["evaluation"]
            cls = ev.get("action_classified_as", "tactical")
            score = int(ev.get("score", 0))
            st.markdown(
                f'<div class="sh-card">'
                f'<span class="sh-classification cls-{cls}">{cls.upper().replace("_"," ")}</span>'
                f' &nbsp; <b style="color:#00FFA7;font-size:28px;">{score}</b> / 100<br/><br/>'
                f'<span style="color:#BBBBBB;">T&R event scored:</span> '
                f'<code style="color:#00FFA7;">{ev.get("tr_event_scored","")}</code><br/>'
                f'<span style="color:#BBBBBB;">Doctrine ref:</span> {ev.get("doctrine_reference","")}<br/><br/>'
                f'<span style="color:#BBBBBB;">Simulated consequence:</span> {ev.get("consequences_simulated","")}<br/><br/>'
                f'<span style="color:#BBBBBB;">Coaching feedback:</span> {ev.get("coaching_feedback","")}<br/><br/>'
                f'<span style="color:#BBBBBB;">Next iteration:</span> {ev.get("next_iteration","")}'
                f'</div>',
                unsafe_allow_html=True,
            )
            with st.expander("Structured evaluation JSON (audit-grade)"):
                st.json({k: v for k, v in ev.items() if not k.startswith("_")})


# ─────────── DRILL 2 — VISUAL ID ───────────
with tab_vid:
    v_left, v_right = st.columns([1.1, 1.0])
    samples_with_imgs = [v for v in VISUAL_ID if v["image"]]
    with v_left:
        st.markdown('<div class="sh-section-title">SELECT VISUAL-ID SAMPLE</div>',
                    unsafe_allow_html=True)
        v_idx = st.selectbox(
            "Sample",
            options=list(range(len(samples_with_imgs))),
            index=0,  # T-72B3 is recognizable
            format_func=lambda i: f"{samples_with_imgs[i]['id']}  •  (uncaptioned image — analyst scores from features only)",
            key="vid_sel",
            label_visibility="collapsed",
        )
        sample = samples_with_imgs[v_idx]
        img_path = VID_DIR / sample["image"]
        if img_path.exists():
            st.image(str(img_path), use_container_width=True,
                     caption=f"{sample['id']} · uncaptioned · drop into the analyst pipeline")
        st.caption(
            "12 visual-ID samples in the corpus (8 with imagery, 4 metadata-only). "
            "Real-data plug-in: Military Object Detection Dataset — see data/load_real.py."
        )

    with v_right:
        st.markdown('<div class="sh-section-title">VISION-LANGUAGE PID</div>',
                    unsafe_allow_html=True)
        if st.button("RUN PID  →", use_container_width=True, key="vid_btn"):
            with st.spinner("Vision-language model identifying the platform from visible features only…"):
                ev = agent.visual_id_evaluate(sample, image_path=img_path)
            st.session_state.vid_eval = {"id": sample["id"], "evaluation": ev}
            agent.append_audit({
                "event": "VISUAL_ID_DRILL",
                "course_id": course["course_id"],
                "sample_id": sample["id"],
                "asset_class": ev.get("asset_class"),
                "confidence": ev.get("confidence"),
                "releasability": ev.get("releasability"),
                "source": ev.get("_source", "unknown"),
            })

        ev_show = st.session_state.vid_eval
        if ev_show is None or ev_show["id"] != sample["id"]:
            st.markdown(
                '<div class="sh-card" style="color:#9A9A9A;">'
                'Click <b>RUN PID</b>. A vision-language model identifies the platform '
                'and writes the analyst-style numbered reasoning (the SENTINEL pattern).'
                '</div>',
                unsafe_allow_html=True,
            )
        else:
            ev = ev_show["evaluation"]
            asset = ev.get("asset_class", "?")
            country = ev.get("country_of_origin", "?")
            ptype = ev.get("platform_type", "?")
            conf = float(ev.get("confidence", 0.0))
            rel = ev.get("releasability", "UNCLASSIFIED//FOUO")
            steps = ev.get("reasoning_steps") or []
            features = ev.get("distinguishing_features") or []
            similar = ev.get("similar_known_examples") or []
            ground_truth_match = (asset.lower() in sample["ground_truth"].lower()
                                  or sample["ground_truth"].lower() in asset.lower())
            gt_pill = ('<span class="sh-pill pill-green">GROUND TRUTH MATCH</span>'
                       if ground_truth_match
                       else '<span class="sh-pill pill-amber">CHECK GROUND TRUTH</span>')
            st.markdown(
                f'<div class="sh-card">'
                f'<div style="font-size:18px;color:#FFFFFF;font-weight:700;">'
                f'PID: {asset} {gt_pill}</div>'
                f'<div style="color:#BBBBBB;font-size:13px;margin-top:4px;">'
                f'{country} · {ptype} · confidence <b style="color:#00FFA7;">{conf:.2f}</b> · '
                f'releasability <code>{rel}</code></div>'
                f'<div style="margin-top:12px;color:#BBBBBB;font-size:11px;letter-spacing:1px;">REASONING TRACE</div>'
                + "".join(f'<div style="font-size:13px;color:#E8E8E8;margin-top:4px;">{i+1}. {s}</div>'
                          for i, s in enumerate(steps))
                + ('<div style="margin-top:12px;color:#BBBBBB;font-size:11px;letter-spacing:1px;">DISTINGUISHING FEATURES</div>'
                   + "".join(f'<div style="font-size:13px;color:#E8E8E8;margin-top:4px;">• {f}</div>' for f in features)
                   if features else "")
                + ('<div style="margin-top:12px;color:#BBBBBB;font-size:11px;letter-spacing:1px;">ALSO RULED OUT</div>'
                   + "".join(f'<div style="font-size:13px;color:#E8E8E8;margin-top:4px;">- {s}</div>' for s in similar)
                   if similar else "")
                + f'<div style="margin-top:12px;color:#888;font-size:11px;">Ground truth: '
                  f'<code>{sample["ground_truth"]}</code> ({sample["country"]} · {sample["type"]})</div>'
                + '</div>',
                unsafe_allow_html=True,
            )
            with st.expander("Structured PID JSON (audit-grade)"):
                st.json({k: v for k, v in ev.items() if not k.startswith("_")})


# ─────────── DRILL 3 — WRITTEN ASSIGNMENT ───────────
with tab_written:
    w_left, w_right = st.columns([1.0, 1.1])
    a = course["assignment"]
    with w_left:
        st.markdown('<div class="sh-section-title">RUBRIC (xlsx)</div>',
                    unsafe_allow_html=True)
        rubric_df = pd.DataFrame(a["rubric_criteria"])
        rubric_df["weight"] = rubric_df["weight"].apply(lambda w: f"{w:.0%}")
        st.dataframe(rubric_df, use_container_width=True, hide_index=True)
        st.caption(
            f"Rubric .xlsx: `{a['rubric_xlsx']}` (real-data plug-in via "
            f"REAL_ASSIGNMENTS_PATH — see data/load_real.py)."
        )
        st.markdown('<div class="sh-section-title">ASSIGNMENT</div>',
                    unsafe_allow_html=True)
        st.markdown(f"**{a['title']}**")
        st.caption(f"Anchored to {course['tr_manual_short']}")

        st.markdown('<div class="sh-section-title">STUDENT DRAFT (verbatim)</div>',
                    unsafe_allow_html=True)
        draft = st.text_area(
            "Draft",
            value=SAMPLE_DRAFT,
            height=320,
            key="written_draft",
            label_visibility="collapsed",
        )
        if st.button("GRADE AGAINST RUBRIC  →", use_container_width=True, key="written_btn"):
            with st.spinner("chat_json grading each rubric criterion against the draft…"):
                ev = agent.written_grade(course, draft)
            st.session_state.written_eval = ev
            agent.append_audit({
                "event": "WRITTEN_ASSIGNMENT_GRADED",
                "course_id": course["course_id"],
                "assignment_id": a["id"],
                "weighted_score": ev.get("weighted_score_0_5"),
                "writing_competency": ev.get("writing_competency_0_5"),
                "rubric_anchored": ev.get("rubric_anchored", False),
                "source": ev.get("_source", "unknown"),
            })

    with w_right:
        st.markdown('<div class="sh-section-title">PER-CRITERION FEEDBACK</div>',
                    unsafe_allow_html=True)
        ev = st.session_state.written_eval
        if ev is None:
            st.markdown(
                '<div class="sh-card" style="color:#9A9A9A;">'
                'Click <b>GRADE</b>. The rubric × draft is sent through chat_json — every '
                'criterion gets a 0-5 score plus narrative feedback citing the draft. '
                'Plus a 0-5 writing-competency score.'
                '</div>',
                unsafe_allow_html=True,
            )
        else:
            scores = ev.get("criterion_scores") or []
            label_lookup = {c["id"]: c["label"] for c in a["rubric_criteria"]}
            for s in scores:
                c_id = s.get("criterion_id", "?")
                c_label = label_lookup.get(c_id, c_id)
                score = float(s.get("score", 0))
                pill_cls = ("pill-green" if score >= 4 else
                            "pill-amber" if score >= 2.5 else "pill-red")
                st.markdown(
                    f'<div class="sh-card">'
                    f'<div style="font-size:13px;color:#FFFFFF;font-weight:700;">'
                    f'{c_id} · {c_label} '
                    f'<span class="sh-pill {pill_cls}">{score:.1f}</span></div>'
                    f'<div style="color:#BBBBBB;font-size:13px;margin-top:6px;line-height:1.45;">'
                    f'{s.get("feedback","")}'
                    f'</div></div>',
                    unsafe_allow_html=True,
                )
            weighted = float(ev.get("weighted_score_0_5", 0))
            wc_score = float(ev.get("writing_competency_0_5", 0))
            st.markdown(
                f'<div class="sh-card" style="background:#0E2F22;border:1px solid #00BB7A;">'
                f'<div style="color:#00FFA7;font-size:11px;letter-spacing:1px;font-weight:700;">'
                f'WEIGHTED RUBRIC SCORE</div>'
                f'<div style="color:#FFFFFF;font-size:32px;font-weight:800;">{weighted:.2f} <span style="font-size:18px;color:#9A9A9A;">/ 5</span></div>'
                f'<div style="color:#9A9A9A;font-size:11px;letter-spacing:1px;margin-top:8px;">'
                f'WRITING COMPETENCY (0-5)</div>'
                f'<div style="color:#00FFA7;font-size:18px;font-weight:700;">{wc_score:.2f}</div>'
                f'<div style="color:#BBBBBB;font-size:13px;margin-top:10px;">'
                f'{ev.get("overall_summary","")}</div>'
                f'<div style="color:#7E7E7E;font-size:11px;margin-top:8px;font-style:italic;">'
                f'{ev.get("tr_competency_notes","")}'
                f'</div></div>',
                unsafe_allow_html=True,
            )
            with st.expander("Structured grading JSON (audit-grade)"):
                st.json({k: v for k, v in ev.items() if not k.startswith("_")})


# ─────────── DRILL 4 — PA PERSONA SIM ───────────
with tab_pa:
    p_left, p_right = st.columns([1.0, 1.1])
    with p_left:
        st.markdown('<div class="sh-section-title">SCENARIO</div>',
                    unsafe_allow_html=True)
        st.markdown(
            '<div class="sh-card">'
            '<b>Range incident — unit-internal PA message.</b><br/>'
            '<span style="color:#9A9A9A;font-size:13px;">'
            'A live-fire training mishap on the North Range yesterday evening has gone '
            'public on social media. The trainee is the assigned PA NCO drafting a '
            'unit-internal release for Marines and families of 2/8.'
            '</span>'
            '</div>',
            unsafe_allow_html=True,
        )
        st.markdown('<div class="sh-section-title">DRAFT MESSAGE</div>',
                    unsafe_allow_html=True)
        pa_message = st.text_area(
            "Message",
            value=SAMPLE_PA_MESSAGE,
            height=320,
            key="pa_msg",
            label_visibility="collapsed",
        )
        if st.button("RUN PERSONA PANEL (5 in parallel)  →",
                     use_container_width=True, key="pa_btn"):
            with st.spinner("5 audience personas reacting in parallel (chat_json)…"):
                reactions = agent.persona_simulate(PERSONAS, pa_message)
            st.session_state.persona_eval = {"message": pa_message, "reactions": reactions}
            agent.append_audit({
                "event": "PA_PERSONA_SIM",
                "course_id": course["course_id"],
                "n_personas": len(reactions),
                "avg_trust_delta": (sum(r["trust_delta"] for r in reactions)
                                    / max(1, len(reactions))),
                "high_risk_n": sum(1 for r in reactions if r["narrative_risk"] == "HIGH"),
                "source": reactions[0].get("_source", "unknown") if reactions else "unknown",
            })

    with p_right:
        st.markdown('<div class="sh-section-title">PANEL REACTIONS</div>',
                    unsafe_allow_html=True)
        ev = st.session_state.persona_eval
        if ev is None:
            st.markdown(
                '<div class="sh-card" style="color:#9A9A9A;">'
                'Click <b>RUN PERSONA PANEL</b>. 5 synthetic audience personas '
                '(junior Marine, NCO, officer, civilian spouse, retired vet) react in '
                'parallel with trust delta + interpretation + predicted action.'
                '</div>',
                unsafe_allow_html=True,
            )
        else:
            reactions = ev["reactions"]
            persona_lookup = {p["persona_id"]: p for p in PERSONAS}
            fig = heatmap.build_persona_panel_chart(reactions)
            st.plotly_chart(fig, use_container_width=True, key="persona_chart")
            for r in sorted(reactions, key=lambda x: x["trust_delta"]):
                p = persona_lookup.get(r["persona_id"], {})
                risk = r["narrative_risk"]
                pill_cls = ("pill-green" if risk == "LOW" else
                            "pill-amber" if risk == "MEDIUM" else "pill-red")
                td = int(r["trust_delta"])
                td_color = ("#00FFA7" if td >= 0 else "#FF6F66")
                st.markdown(
                    f'<div class="sh-card">'
                    f'<div style="font-size:13px;color:#FFFFFF;font-weight:700;">'
                    f'{p.get("label", r["persona_id"])} '
                    f'<span class="sh-pill {pill_cls}">{risk} · {r["predicted_action"]}</span> '
                    f'<span style="color:{td_color};font-weight:700;margin-left:8px;">trust {td:+d}</span>'
                    f'</div>'
                    f'<div style="color:#BBBBBB;font-size:13px;margin-top:6px;font-style:italic;">'
                    f'"{r["interpretation"]}"'
                    f'</div>'
                    + "".join(f'<div style="font-size:12px;color:#9A9A9A;margin-top:4px;">→ {c}</div>'
                              for c in r["key_concerns_raised"][:3])
                    + '</div>',
                    unsafe_allow_html=True,
                )


st.markdown("---")


# ─────────────────────────────────────────────────────────────────────────────
# Cohort heatmap (always-on, persona-agnostic visual)
# ─────────────────────────────────────────────────────────────────────────────
st.markdown("### Cohort competency map")
st.caption(
    f"Per-student × per-competency rubric scores (0-5) for "
    f"**{course['name']}** — 6-week trailing window. "
    f"Anchored to {course['tr_manual_short']}."
)

cm_left, cm_right = st.columns([0.62, 0.38])
comp_summary = agent.cohort_competency_summary(course)
with cm_left:
    fig = heatmap.build_heatmap(comp_summary, course["students"])
    st.plotly_chart(fig, use_container_width=True, key="cohort_heatmap")
with cm_right:
    # cohort signals
    avgs = {k: (sum(comp_summary[s["student_id"]].get(k, 0)
                    for s in course["students"]) / len(course["students"]))
            for k in ("critical_thinking", "communication",
                      "doctrinal_knowledge", "problem_solving")}
    intv_n = sum(1 for s in course["students"] if s["profile"] == "needs_remediation")
    health = ("RED" if intv_n / len(course["students"]) > 0.4 else
              "AMBER" if intv_n / len(course["students"]) >= 0.25 else "GREEN")
    health_cls = ("pill-red" if health == "RED" else
                  "pill-amber" if health == "AMBER" else "pill-green")
    st.markdown(
        f'<div class="sh-card">'
        f'<div style="color:{BRAND["muted"]};font-size:11px;letter-spacing:1px;">COURSE HEALTH</div>'
        f'<div style="font-size:18px;color:#FFFFFF;font-weight:700;margin-top:4px;">'
        f'{health} <span class="sh-pill {health_cls}">{intv_n} INTV</span></div>'
        f'<div style="color:{BRAND["muted"]};font-size:11px;letter-spacing:1px;margin-top:14px;">'
        f'INSTRUCTOR EFFECTIVENESS</div>'
        f'<div style="font-size:14px;color:#FFFFFF;font-weight:700;margin-top:4px;">EFFECTIVE</div>'
        f'<div style="color:{BRAND["muted"]};font-size:11px;letter-spacing:1px;margin-top:14px;">INSTRUCTOR</div>'
        f'<div style="font-size:14px;color:#FFFFFF;font-weight:700;">{course["instructor"]}</div>'
        f'</div>',
        unsafe_allow_html=True,
    )
    st.markdown(
        f'<div class="sh-card">'
        f'<div style="color:{BRAND["muted"]};font-size:11px;letter-spacing:1px;margin-bottom:8px;">'
        f'COHORT AVG (0-5)</div>'
        + "".join(
            f'<div style="margin-top:5px;">{LABEL}'
            f' <span class="sh-pill {("pill-green" if avgs[k] >= 3.5 else "pill-amber" if avgs[k] >= 2.5 else "pill-red")}">'
            f'{avgs[k]:.1f}</span></div>'
            for k, LABEL in [("critical_thinking", "Critical Thinking"),
                             ("communication", "Communication"),
                             ("doctrinal_knowledge", "Doctrinal Knowledge"),
                             ("problem_solving", "Problem Solving")]
        )
        + '</div>',
        unsafe_allow_html=True,
    )


st.markdown("---")


# ─────────────────────────────────────────────────────────────────────────────
# HERO BRIEF — Schoolhouse Intelligence Brief (cache-first, persona-aware)
# ─────────────────────────────────────────────────────────────────────────────
brief_title = {
    "instructor": "Schoolhouse Intelligence Brief — Instructor view",
    "student": "Adaptive Study Plan — Student view",
    "co": "Schoolhouse Health Brief — School CO view",
}[persona]
st.markdown(f"### {brief_title}")
st.caption(
    f"Cache-first one-page brief, persona-aware. Same data — reshaped per role. "
    f"Click <b>REGENERATE</b> to fire the live hero call (35s wall-clock cap)."
    , unsafe_allow_html=True,
)

bb_left, bb_right = st.columns([0.30, 0.70])
with bb_left:
    if st.button("REGENERATE BRIEF", use_container_width=True,
                 type="primary", key="hero_btn"):
        with st.spinner("Drafting Schoolhouse Intelligence Brief on the Kamiwaza-deployed hero model …"):
            out = agent.write_hero_brief(course, persona=persona,
                                         hero=True, use_cache=False)
        st.session_state.hero_brief = out
        agent.append_audit({
            "event": "SCHOOLHOUSE_BRIEF_GENERATED",
            "course_id": course["course_id"],
            "persona": persona,
            "brief_sha256": agent._sha256_text(out["brief"]),
            "source": out.get("source", "unknown"),
        })

if st.session_state.hero_brief is None:
    out = agent.write_hero_brief(course, persona=persona,
                                 hero=False, use_cache=True)
else:
    out = st.session_state.hero_brief

with bb_right:
    st.markdown(
        f"<div style='color:{BRAND['muted']};font-size:11px;letter-spacing:1px;'>"
        f"GENERATED {out.get('generated_at', '—')[:19].replace('T',' ')} · "
        f"SOURCE <code style='color:{BRAND['neon']};'>{out.get('source','—')}</code></div>",
        unsafe_allow_html=True,
    )

st.markdown('<div class="sh-card" style="padding:22px 30px;">', unsafe_allow_html=True)
st.markdown(out["brief"])
st.markdown('</div>', unsafe_allow_html=True)


# ─────────────────────────────────────────────────────────────────────────────
# Hash-chained audit log
# ─────────────────────────────────────────────────────────────────────────────
st.markdown("---")
st.markdown("### Hash-chained audit log")
st.caption(
    "Every drill, every brief, every persona panel — append-only SHA-256 chain. "
    "Privacy Act of 1974 (5 U.S.C. § 552a) + DoDI 1322.35 'Military Education Records' "
    "governance — NOT FERPA. Any IG / SJA / cognitive-developer can replay the call months later."
)
chain = agent.read_audit_chain(limit=15)
if not chain:
    st.info("Audit chain is empty — fire any drill above to seed an entry.")
else:
    rows = []
    for e in chain:
        rows.append({
            "event": e.get("event", "?"),
            "course": e.get("course_id", "—"),
            "subject": (e.get("scene_id") or e.get("sample_id")
                        or e.get("assignment_id") or e.get("persona") or "—"),
            "score": (e.get("score") or e.get("weighted_score")
                      or e.get("confidence") or e.get("avg_trust_delta") or "—"),
            "source": e.get("source", "—"),
            "ts": (e.get("timestamp_utc", "") or "")[:19].replace("T", " "),
            "prev_hash": (e.get("prev_hash", "") or "")[:12] + "…",
            "entry_hash": (e.get("entry_hash", "") or "")[:12] + "…",
        })
    st.dataframe(pd.DataFrame(rows), use_container_width=True,
                 hide_index=True, height=360)


# ─────────────────────────────────────────────────────────────────────────────
# On-prem KAMIWAZA env-var beat
# ─────────────────────────────────────────────────────────────────────────────
st.markdown("---")
st.markdown("### On-prem posture")
st.markdown(
    f'<div class="sh-banner-on-prem">'
    f'$ export <span style="color:{BRAND["neon"]};">KAMIWAZA_BASE_URL</span>=https://kamiwaza.local/api/v1<br/>'
    f'$ export <span style="color:{BRAND["neon"]};">KAMIWAZA_API_KEY</span>=$(cat /run/secrets/kw)<br/>'
    f'# same code path. PME data stays inside the SCIF. SIPR / JWICS deployable.'
    f'</div>',
    unsafe_allow_html=True,
)


# Footer
st.markdown(
    f"<div class='sh-footer'>"
    f"Powered by Kamiwaza · One on-prem stack · Four drill types · Three roles · "
    f"PME data stays inside the wire."
    f"</div>",
    unsafe_allow_html=True,
)
