"""EMBODIED — Streamlit egocentric Marine training simulator.

Run:
    streamlit run src/app.py --server.port 3027

Frontend port 3027. Single-process Streamlit (no separate backend).
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import streamlit as st
from PIL import Image

APP_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = APP_ROOT.parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

from src.coach import after_action_review, evaluate  # noqa: E402

DATA_DIR = APP_ROOT / "data"
FRAMES_DIR = DATA_DIR / "frames"
SCENARIOS_PATH = DATA_DIR / "scenarios.json"
CACHED_PATH = DATA_DIR / "cached_briefs.json"


# --- Brand & page config -------------------------------------------------
PRIMARY = "#00BB7A"
NEON = "#00FFA7"
BG = "#0A0A0A"
SURFACE = "#0E0E0E"
SURFACE_HIGH = "#111111"
BORDER = "#222222"
TEXT_DIM = "#7E7E7E"

st.set_page_config(
    page_title="EMBODIED — Egocentric Marine Training",
    page_icon="https://www.kamiwaza.ai/hubfs/logo-light.svg",
    layout="wide",
    initial_sidebar_state="collapsed",
)


def _inject_css() -> None:
    st.markdown(
        f"""
        <style>
            html, body, [class*="css"] {{
                background-color: {BG} !important;
                color: #E6E6E6 !important;
                font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif;
            }}
            .stApp {{ background-color: {BG}; }}
            .block-container {{ padding-top: 1.4rem; padding-bottom: 0.5rem; max-width: 1500px; }}
            .embo-hero {{
                background: linear-gradient(135deg, {SURFACE} 0%, {SURFACE_HIGH} 100%);
                border: 1px solid {BORDER};
                border-radius: 14px;
                padding: 18px 22px;
                margin-bottom: 18px;
                display: flex; align-items: center; justify-content: space-between;
            }}
            .embo-title {{
                font-size: 30px; font-weight: 800; color: #FFFFFF; letter-spacing: 0.04em;
            }}
            .embo-title span {{ color: {PRIMARY}; }}
            .embo-tagline {{ color: {TEXT_DIM}; font-size: 13px; margin-top: 2px; letter-spacing: 0.02em; }}
            .embo-pill {{
                background: {SURFACE_HIGH}; color: {NEON};
                padding: 6px 12px; border-radius: 999px; border: 1px solid {BORDER};
                font-family: 'SF Mono', Menlo, monospace; font-size: 12px;
            }}
            .embo-card {{
                background: {SURFACE};
                border: 1px solid {BORDER};
                border-radius: 12px;
                padding: 14px 16px;
                margin-bottom: 12px;
            }}
            .embo-section-title {{
                color: {PRIMARY}; text-transform: uppercase; letter-spacing: 0.12em;
                font-size: 11px; font-weight: 700; margin-bottom: 8px;
            }}
            .embo-meta {{ color: {TEXT_DIM}; font-size: 12px; line-height: 1.55; }}
            .embo-pov {{
                color: #DDDDDD; font-style: italic;
                font-size: 13.5px; line-height: 1.55;
                background: {SURFACE_HIGH}; border-left: 3px solid {PRIMARY};
                padding: 10px 14px; border-radius: 4px;
            }}
            .embo-badge {{
                display: inline-block; background: {SURFACE_HIGH}; border: 1px solid {BORDER};
                color: {NEON}; padding: 3px 10px; border-radius: 999px;
                font-size: 11px; font-family: 'SF Mono', Menlo, monospace; margin-right: 6px;
            }}
            .embo-classification {{
                display: inline-block; padding: 4px 12px; border-radius: 6px;
                font-family: 'SF Mono', Menlo, monospace; font-weight: 700;
                font-size: 12px; letter-spacing: 0.06em;
            }}
            .cls-doctrinally_correct {{ background: #073B27; color: {NEON}; border: 1px solid {PRIMARY}; }}
            .cls-tactical            {{ background: #2A2618; color: #E0C870; border: 1px solid #6A5A20; }}
            .cls-hesitation          {{ background: #1A1A24; color: #8888AA; border: 1px solid #444466; }}
            .cls-risky               {{ background: #2A0F0F; color: #E07070; border: 1px solid #7A2020; }}
            .embo-score-row {{
                display: flex; align-items: center; gap: 12px; margin-top: 6px;
            }}
            .embo-score-num {{
                font-family: 'SF Mono', Menlo, monospace;
                font-size: 38px; font-weight: 800; color: {NEON};
            }}
            .embo-score-bar {{
                flex: 1; height: 8px; background: {SURFACE_HIGH};
                border-radius: 4px; overflow: hidden; border: 1px solid {BORDER};
            }}
            .embo-score-fill {{
                height: 100%; background: linear-gradient(90deg, {PRIMARY}, {NEON});
            }}
            .embo-banner-on-prem {{
                background: {SURFACE_HIGH}; border: 1px solid {PRIMARY};
                border-radius: 10px; padding: 10px 14px; margin-top: 10px;
                font-family: 'SF Mono', Menlo, monospace; font-size: 12px; color: #DDDDDD;
            }}
            .embo-footer {{
                text-align: center; color: {TEXT_DIM}; font-size: 12px;
                padding-top: 14px; margin-top: 18px; border-top: 1px solid {BORDER};
            }}
            .stButton > button {{
                background: {PRIMARY}; color: #08110D; border: 0;
                font-weight: 700; letter-spacing: 0.04em; border-radius: 8px;
                padding: 0.55rem 1.1rem;
            }}
            .stButton > button:hover {{ background: {NEON}; color: #04140C; }}
            .stTextArea textarea {{
                background: {SURFACE_HIGH} !important;
                color: #E6E6E6 !important;
                border: 1px solid {BORDER} !important;
                font-family: 'SF Mono', Menlo, monospace !important;
                font-size: 13px !important;
            }}
            .stSelectbox > div > div {{
                background: {SURFACE_HIGH} !important;
                border: 1px solid {BORDER} !important;
            }}
            #MainMenu, footer {{ visibility: hidden; }}
        </style>
        """,
        unsafe_allow_html=True,
    )


_inject_css()


# --- Data ---------------------------------------------------------------
@st.cache_data(show_spinner=False)
def _load_scenarios() -> list[dict]:
    return json.loads(SCENARIOS_PATH.read_text())


@st.cache_data(show_spinner=False)
def _load_cached_briefs() -> dict:
    if CACHED_PATH.exists():
        return json.loads(CACHED_PATH.read_text())
    return {}


@st.cache_data(show_spinner=False)
def _load_frame(scn_id: str) -> Image.Image:
    return Image.open(FRAMES_DIR / f"{scn_id}.png")


SCENARIOS = _load_scenarios()
CACHED = _load_cached_briefs()
SCN_BY_ID = {s["id"]: s for s in SCENARIOS}


# --- Header ------------------------------------------------------------
st.markdown(
    f"""
    <div class="embo-hero">
      <div>
        <div class="embo-title">EMBODIED<span>.</span></div>
        <div class="embo-tagline">Egocentric multimodal Marine training simulator &nbsp;|&nbsp; from context to action</div>
      </div>
      <div class="embo-pill">SIMULATOR ONLINE &nbsp;|&nbsp; {len(SCENARIOS)} SCENARIOS</div>
    </div>
    """,
    unsafe_allow_html=True,
)


# --- State -------------------------------------------------------------
if "scn_idx" not in st.session_state:
    st.session_state.scn_idx = 1  # land on the checkpoint (visually rich)
if "trainee_callsign" not in st.session_state:
    st.session_state.trainee_callsign = "TRN-2-7-A"
if "attempts" not in st.session_state:
    # pre-load the cached sample run so the demo reel is non-empty
    sample_attempts: list[dict] = []
    for scn_id, runs in CACHED.items():
        if scn_id.startswith("_"):
            continue
        for r in runs:
            sample_attempts.append({
                "scenario_id": scn_id,
                "scenario_title": SCN_BY_ID.get(scn_id, {}).get("title", scn_id),
                "trainee_response": r["trainee_response"],
                "evaluation": r["evaluation"],
            })
    st.session_state.attempts = sample_attempts
if "last_eval" not in st.session_state:
    st.session_state.last_eval = None
if "aar" not in st.session_state:
    st.session_state.aar = None


# --- Layout ------------------------------------------------------------
left, right = st.columns([1.4, 1.0], gap="large")

with left:
    st.markdown('<div class="embo-section-title">SELECT SCENARIO</div>', unsafe_allow_html=True)
    scn_idx = st.selectbox(
        "Scenario",
        options=list(range(len(SCENARIOS))),
        index=st.session_state.scn_idx,
        format_func=lambda i: f"{i + 1:02d}  •  {SCENARIOS[i]['title']}",
        label_visibility="collapsed",
    )
    st.session_state.scn_idx = scn_idx
    scn = SCENARIOS[scn_idx]

    st.markdown('<div class="embo-section-title">EGOCENTRIC FRAME — HELMET-CAM POV</div>', unsafe_allow_html=True)
    st.image(_load_frame(scn["id"]), use_container_width=True,
             caption=f"{scn['id']}  |  {scn['title']}  |  procedural egocentric still")

    st.markdown('<div class="embo-section-title">SCENARIO POV</div>', unsafe_allow_html=True)
    st.markdown(f'<div class="embo-pov">{scn["pov"]}</div>', unsafe_allow_html=True)

    st.markdown('<div class="embo-section-title">WHAT WOULD YOU DO?</div>', unsafe_allow_html=True)
    trainee_response = st.text_area(
        "Type your action — what is your next move, in your own words.",
        height=110,
        placeholder="e.g. 'I begin shout-show-shove escalation and signal STOP at the warning line, off-axis from the kill funnel.'",
        key=f"resp_{scn['id']}",
        label_visibility="collapsed",
    )

    submit = st.button("EVALUATE ACTION  →", use_container_width=True, type="primary")
    if submit:
        with st.spinner("Multimodal coach analyzing frame + your action against doctrine…"):
            evaluation = evaluate(scn, trainee_response, frame_path=FRAMES_DIR / f"{scn['id']}.png")
            st.session_state.last_eval = {
                "scenario_id": scn["id"],
                "scenario_title": scn["title"],
                "trainee_response": trainee_response,
                "evaluation": evaluation,
            }
            st.session_state.attempts.append(st.session_state.last_eval)
            # invalidate the AAR — new attempt added
            st.session_state.aar = None


with right:
    st.markdown('<div class="embo-section-title">DOCTRINE REFERENCE</div>', unsafe_allow_html=True)
    st.markdown(
        f"""
        <div class="embo-card embo-meta">
        <span class="embo-badge">REF</span> {scn['doctrine_reference']}
        <br/><br/>
        <strong style="color: #BBBBBB;">Canonical correct actions:</strong>
        <ul style="margin-top: 6px;">
        {''.join(f'<li>{a}</li>' for a in scn['correct_actions'])}
        </ul>
        <strong style="color: #BBBBBB;">Common failures:</strong>
        <ul style="margin-top: 6px;">
        {''.join(f'<li>{a}</li>' for a in scn['common_failures'])}
        </ul>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown('<div class="embo-section-title">HERO AI — MULTIMODAL EVALUATION</div>', unsafe_allow_html=True)
    last = st.session_state.last_eval
    # if no live last-eval, surface the most recent cached attempt for this scenario
    if last is None:
        cached_for = [a for a in st.session_state.attempts if a.get("scenario_id") == scn["id"]]
        if cached_for:
            last = cached_for[-1]
    if last is None:
        st.markdown(
            '<div class="embo-card embo-meta">Type your action and click EVALUATE. '
            'A multimodal coach will read the frame, your response, and the doctrine.'
            '</div>', unsafe_allow_html=True,
        )
    else:
        ev = last["evaluation"]
        cls = ev.get("action_classified_as", "tactical")
        score = int(ev.get("score", 0))
        st.markdown(
            f"""
            <div class="embo-card">
              <div>
                <span class="embo-classification cls-{cls}">{cls.upper().replace('_', ' ')}</span>
                <span class="embo-badge" style="margin-left:8px;">MODEL</span> Kamiwaza-deployed multimodal
              </div>
              <div class="embo-score-row">
                <div class="embo-score-num">{score}</div>
                <div class="embo-score-bar"><div class="embo-score-fill" style="width:{score}%"></div></div>
              </div>
              <div class="embo-meta" style="margin-top: 10px;">
                <strong style="color:#BBBBBB;">Doctrine ref:</strong> {ev.get('doctrine_reference','')}<br/><br/>
                <strong style="color:#BBBBBB;">Simulated consequence:</strong> {ev.get('consequences_simulated','')}<br/><br/>
                <strong style="color:#BBBBBB;">Coaching feedback:</strong> {ev.get('coaching_feedback','')}<br/><br/>
                <strong style="color:#BBBBBB;">Next:</strong> {ev.get('next_scenario_suggestion','')}
              </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        with st.expander("Structured evaluation JSON"):
            st.json(ev)

    st.markdown('<div class="embo-section-title">AFTER-ACTION REVIEW — EGOCENTRIC DECISION BRIEF</div>',
                unsafe_allow_html=True)
    st.markdown(
        f'<div class="embo-meta">Attempts logged this session: <strong style="color:{NEON}">'
        f'{len(st.session_state.attempts)}</strong> &nbsp;|&nbsp; Callsign: '
        f'<strong style="color:{NEON}">{st.session_state.trainee_callsign}</strong></div>',
        unsafe_allow_html=True,
    )

    aar_btn = st.button("GENERATE EGOCENTRIC DECISION BRIEF", use_container_width=True)
    use_cache = "_sample_aar" in CACHED and len(st.session_state.attempts) >= 5
    if aar_btn:
        if use_cache and st.session_state.aar is None:
            cached_aar = CACHED["_sample_aar"][0]["evaluation"]
            st.session_state.aar = (
                f"## EGOCENTRIC DECISION BRIEF — {cached_aar['trainee_callsign']}\n\n"
                f"**Attempts evaluated:** {cached_aar['n_attempts']}\n\n"
                f"### PATTERNS OBSERVED\n{cached_aar['summary']}\n\n"
                f"### STRENGTHS\n" + "\n".join(f"- {s}" for s in cached_aar['strengths']) + "\n\n"
                f"### GROWTH AREAS\n" + "\n".join(f"- {s}" for s in cached_aar['growth_areas']) + "\n\n"
                f"### NEXT ITERATION\n{cached_aar['next_iteration']}"
            )
        else:
            with st.spinner("Drafting egocentric decision brief across attempts…"):
                st.session_state.aar = after_action_review(
                    st.session_state.trainee_callsign, st.session_state.attempts
                )

    if st.session_state.aar:
        st.markdown('<div class="embo-card">', unsafe_allow_html=True)
        st.markdown(st.session_state.aar)
        st.markdown('</div>', unsafe_allow_html=True)

    st.markdown('<div class="embo-section-title">ON-PREM POSTURE</div>', unsafe_allow_html=True)
    st.markdown(
        f"""
        <div class="embo-banner-on-prem">
        $ export <span style="color: {NEON}">KAMIWAZA_BASE_URL</span>=https://kamiwaza.local/api/v1<br/>
        $ export <span style="color: {NEON}">KAMIWAZA_API_KEY</span>=$(cat /run/secrets/kw)<br/>
        # same code path. trainee video stays inside the wire. SIPR / JWICS ready.
        </div>
        """,
        unsafe_allow_html=True,
    )


st.markdown(
    """
    <div class="embo-footer">
      Built on the Kamiwaza Stack &nbsp;|&nbsp; Powered by Kamiwaza &nbsp;|&nbsp;
      MDM 2026 LOGCOM Hackathon &nbsp;|&nbsp; Synthetic egocentric stills — would plug into Xperience-10M unchanged
    </div>
    """,
    unsafe_allow_html=True,
)
