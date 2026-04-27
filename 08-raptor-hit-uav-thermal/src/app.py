# RAPTOR — drone IR INTREP from multi-frame thermal window
# Part of the MDM 2026 Hackathon Templates (https://github.com/12fn/MDMhackathon-repos)
# MIT licensed. Built on GAI (Government Acquisitions, Inc.) + Kamiwaza (https://www.kamiwaza.ai/).
"""RAPTOR — Streamlit thermal-ISR analyzer for USMC LOGCOM hackathon.

Run:
    streamlit run src/app.py --server.port 3008

Frontend port 3008. Backend port 8008 (unused — single-process Streamlit).
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import cv2
import numpy as np
import streamlit as st
from PIL import Image

APP_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = APP_ROOT.parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

from src.detect import annotate, detect_blobs  # noqa: E402
from src.intrep import generate_intrep  # noqa: E402

DATA_DIR = APP_ROOT / "data"
FRAMES_DIR = DATA_DIR / "frames"
COLOR_DIR = DATA_DIR / "frames_color"


# --- Brand & page config -------------------------------------------------
PRIMARY = "#00BB7A"
NEON = "#00FFA7"
BG = "#0A0A0A"
SURFACE = "#0E0E0E"
SURFACE_HIGH = "#111111"
BORDER = "#222222"
TEXT_DIM = "#7E7E7E"

st.set_page_config(
    page_title="RAPTOR — Thermal ISR Analyzer",
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
            .stApp {{
                background-color: {BG};
            }}
            .block-container {{ padding-top: 1.4rem; padding-bottom: 0.5rem; max-width: 1500px; }}
            .raptor-hero {{
                background: linear-gradient(135deg, {SURFACE} 0%, {SURFACE_HIGH} 100%);
                border: 1px solid {BORDER};
                border-radius: 14px;
                padding: 18px 22px;
                margin-bottom: 18px;
                display: flex; align-items: center; justify-content: space-between;
            }}
            .raptor-title {{
                font-size: 30px; font-weight: 800; color: #FFFFFF; letter-spacing: 0.04em;
            }}
            .raptor-title span {{ color: {PRIMARY}; }}
            .raptor-tagline {{ color: {TEXT_DIM}; font-size: 13px; margin-top: 2px; letter-spacing: 0.02em; }}
            .raptor-status-pill {{
                background: {SURFACE_HIGH}; color: {NEON};
                padding: 6px 12px; border-radius: 999px; border: 1px solid {BORDER};
                font-family: 'SF Mono', Menlo, monospace; font-size: 12px;
            }}
            .raptor-card {{
                background: {SURFACE};
                border: 1px solid {BORDER};
                border-radius: 12px;
                padding: 14px 16px;
                margin-bottom: 12px;
            }}
            .raptor-section-title {{
                color: {PRIMARY}; text-transform: uppercase; letter-spacing: 0.12em;
                font-size: 11px; font-weight: 700; margin-bottom: 8px;
            }}
            .raptor-meta {{ color: {TEXT_DIM}; font-size: 12px; line-height: 1.55; }}
            .raptor-kbd {{
                background: {SURFACE_HIGH}; padding: 2px 6px; border-radius: 4px;
                font-family: 'SF Mono', Menlo, monospace; font-size: 11px; color: {NEON};
            }}
            .raptor-footer {{
                text-align: center; color: {TEXT_DIM}; font-size: 12px;
                padding-top: 14px; margin-top: 18px; border-top: 1px solid {BORDER};
            }}
            .stButton > button {{
                background: {PRIMARY}; color: #08110D; border: 0;
                font-weight: 700; letter-spacing: 0.04em; border-radius: 8px;
                padding: 0.55rem 1.1rem;
            }}
            .stButton > button:hover {{ background: {NEON}; color: #04140C; }}
            .stSlider > div > div > div > div {{ background: {PRIMARY}; }}
            .raptor-badge {{
                display: inline-block; background: {SURFACE_HIGH}; border: 1px solid {BORDER};
                color: {NEON}; padding: 3px 10px; border-radius: 999px;
                font-size: 11px; font-family: 'SF Mono', Menlo, monospace; margin-right: 6px;
            }}
            .raptor-detection-row {{
                display: flex; justify-content: space-between; padding: 6px 8px;
                border-bottom: 1px solid {BORDER}; font-size: 13px;
            }}
            .raptor-cls {{ color: {NEON}; font-weight: 600; font-family: 'SF Mono', Menlo, monospace; }}
            .raptor-conf {{ color: {TEXT_DIM}; }}
            .raptor-banner-on-prem {{
                background: {SURFACE_HIGH}; border: 1px solid {PRIMARY};
                border-radius: 10px; padding: 10px 14px; margin-top: 10px;
                font-family: 'SF Mono', Menlo, monospace; font-size: 12px; color: #DDDDDD;
            }}
            #MainMenu, footer {{ visibility: hidden; }}
        </style>
        """,
        unsafe_allow_html=True,
    )


_inject_css()


# tiny shim so annotate() (which expects Detection dataclass) works on dicts
class _DetShim:
    def __init__(self, **kw):
        self.cls = kw["cls"]
        self.conf = kw["conf"]
        self.bbox = kw["bbox"]


@st.cache_data(show_spinner=False)
def _load_mission() -> dict:
    return json.loads((DATA_DIR / "mission.json").read_text())


@st.cache_data(show_spinner=False)
def _load_ground_truth() -> list[dict]:
    return json.loads((DATA_DIR / "ground_truth.json").read_text())


@st.cache_data(show_spinner=False)
def _load_gray(idx: int) -> np.ndarray:
    return cv2.imread(str(FRAMES_DIR / f"frame_{idx:03d}.png"), cv2.IMREAD_GRAYSCALE)


@st.cache_data(show_spinner=False)
def _load_color(idx: int) -> np.ndarray:
    return cv2.imread(str(COLOR_DIR / f"frame_{idx:03d}.png"))


@st.cache_data(show_spinner=False)
def _detect_cached(idx: int) -> list[dict]:
    gray = _load_gray(idx)
    return [d.to_dict() for d in detect_blobs(gray)]


# --- Header ---------------------------------------------------------------
mission = _load_mission()
gt = _load_ground_truth()

st.markdown(
    f"""
    <div class="raptor-hero">
      <div>
        <div class="raptor-title">RAPTOR<span>.</span></div>
        <div class="raptor-tagline">Real-time Aerial Persistent Thermal Object Reasoning &nbsp;|&nbsp; UAV thermal ISR analyzer</div>
      </div>
      <div class="raptor-status-pill">MISSION {mission['mission_id']} &nbsp;|&nbsp; LIVE FEED</div>
    </div>
    """,
    unsafe_allow_html=True,
)


# --- Layout ---------------------------------------------------------------
left, right = st.columns([2.2, 1.0], gap="large")

if "frame_idx" not in st.session_state:
    st.session_state.frame_idx = 18  # land on a busy frame for the demo
if "intrep" not in st.session_state:
    st.session_state.intrep = None
if "intrep_for" not in st.session_state:
    st.session_state.intrep_for = -1


with left:
    st.markdown('<div class="raptor-section-title">LIVE THERMAL FRAME — LWIR 640×512</div>', unsafe_allow_html=True)

    frame_idx = st.slider(
        "Mission elapsed time (frame index)",
        min_value=0,
        max_value=len(gt) - 1,
        value=st.session_state.frame_idx,
        key="frame_slider",
        help="Scrub through 30 frames of the synthetic mission feed.",
    )
    st.session_state.frame_idx = frame_idx

    color = _load_color(frame_idx)
    dets = _detect_cached(frame_idx)
    annotated = annotate(color, [_DetShim(**d) for d in dets]) if dets else color
    rgb = cv2.cvtColor(annotated, cv2.COLOR_BGR2RGB)
    st.image(
        Image.fromarray(rgb),
        caption=f"Frame {frame_idx:03d} / {len(gt) - 1:03d}  |  {gt[frame_idx]['timestamp_utc']}  |  inferno LUT  |  {len(dets)} detections",
        use_container_width=True,
    )

    # Detection table
    st.markdown('<div class="raptor-section-title">DETECTIONS — HEURISTIC BLOB + CLASSIFY</div>', unsafe_allow_html=True)
    if not dets:
        st.markdown('<div class="raptor-meta">No hot signatures above threshold.</div>', unsafe_allow_html=True)
    else:
        rows = []
        for d in dets:
            rows.append(
                f'<div class="raptor-detection-row">'
                f'<span class="raptor-cls">{d["cls"].upper()}</span>'
                f'<span>area {d["area_px"]} px&nbsp;&nbsp;peak {int(d["peak_intensity"])}&nbsp;&nbsp;'
                f'<span class="raptor-conf">conf {int(d["conf"]*100)}%</span></span>'
                f'</div>'
            )
        st.markdown('<div class="raptor-card">' + "".join(rows) + '</div>', unsafe_allow_html=True)


with right:
    st.markdown('<div class="raptor-section-title">MISSION DOSSIER</div>', unsafe_allow_html=True)
    st.markdown(
        f"""
        <div class="raptor-card raptor-meta">
        <span class="raptor-badge">PLATFORM</span> {mission['platform']}<br/>
        <span class="raptor-badge">SENSOR</span> {mission['sensor']}<br/>
        <span class="raptor-badge">SITE</span> {mission['site']}<br/>
        <span class="raptor-badge">ALT</span> {mission['altitude_agl_ft']} ft AGL<br/>
        <br/>
        <strong>Tasking:</strong> {mission['tasking']}
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown('<div class="raptor-section-title">HERO AI — VISION-LANGUAGE INTREP</div>', unsafe_allow_html=True)
    if st.button("Generate INTREP from current + 5 prior frames", use_container_width=True):
        with st.spinner("RAPTOR analyzing frame stream — multi-step vision-language reasoning…"):
            cur_color = _load_color(frame_idx)
            cur_dets = _detect_cached(frame_idx)
            prior_window = list(range(max(0, frame_idx - 5), frame_idx))
            prior_colors = [_load_color(i) for i in prior_window]
            prior_dets_list = [_detect_cached(i) for i in prior_window]
            try:
                result = generate_intrep(
                    cur_color, prior_colors, cur_dets, prior_dets_list, mission,
                )
                st.session_state.intrep = result
                st.session_state.intrep_for = frame_idx
            except Exception as e:  # noqa: BLE001
                st.error(f"INTREP generation failed: {e}")

    if st.session_state.intrep:
        r = st.session_state.intrep
        used_v = "vision" if r.get("used_vision") else "text-only"
        st.markdown(
            f'<div class="raptor-card raptor-meta">'
            f'<span class="raptor-badge">MODEL</span> Kamiwaza-deployed VLM'
            f'<span class="raptor-badge">MODE</span> {used_v}'
            f'<span class="raptor-badge">FRAME</span> T={st.session_state.intrep_for}'
            f'</div>',
            unsafe_allow_html=True,
        )
        st.markdown(r["markdown"])
        if r.get("json"):
            with st.expander("Structured INTREP JSON"):
                st.json(r["json"])

    st.markdown('<div class="raptor-section-title">ON-PREM POSTURE</div>', unsafe_allow_html=True)
    st.markdown(
        f"""
        <div class="raptor-banner-on-prem">
        $ export <span style="color: {NEON}">KAMIWAZA_BASE_URL</span>=https://kamiwaza.local/api/v1<br/>
        $ export <span style="color: {NEON}">KAMIWAZA_API_KEY</span>=$(cat /run/secrets/kw)<br/>
        # same code path. zero data egress. SIPR / JWICS ready.
        </div>
        """,
        unsafe_allow_html=True,
    )


st.markdown(
    """
    <div class="raptor-footer">
      Built on the Kamiwaza Stack &nbsp;|&nbsp; Powered by Kamiwaza &nbsp;|&nbsp;
      MDM 2026 LOGCOM Hackathon &nbsp;|&nbsp; Synthetic data — would plug into HIT-UAV (Truffle, 775 MB) unchanged
    </div>
    """,
    unsafe_allow_html=True,
)
