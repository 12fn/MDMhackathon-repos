# WEATHERVANE — mission-window environmental brief
# Part of the MDM 2026 Hackathon Templates (https://github.com/12fn/MDMhackathon-repos)
# MIT licensed. Built on GAI (Government Acquisitions, Inc.) + Kamiwaza (https://www.kamiwaza.ai/).
"""WEATHERVANE — Streamlit UI.

Run: streamlit run src/app.py --server.port 3012
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parent.parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

APP_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(APP_DIR))
sys.path.insert(0, str(APP_DIR / "src"))

from src.agent import MISSION_PROFILES, fuse  # noqa: E402
from src.charts import CHARTS, make_chart  # noqa: E402

# ----- Page config -----
st.set_page_config(
    page_title="WEATHERVANE — Environmental Intelligence",
    page_icon="⚡",
    layout="wide",
)

# ----- Brand CSS -----
BRAND_CSS = """
<style>
  .stApp { background-color: #0A0A0A; color: #FFFFFF; }
  section[data-testid="stSidebar"] { background-color: #0E0E0E; border-right: 1px solid #222222; }
  h1, h2, h3, h4 { color: #FFFFFF !important; }
  .vw-header { display:flex; align-items:center; justify-content:space-between;
               border-bottom:1px solid #222; padding:8px 0 14px 0; margin-bottom:8px; }
  .vw-title  { font-size:32px; font-weight:700; letter-spacing:0.5px; color:#FFFFFF; }
  .vw-tag    { color:#00FFA7; font-size:13px; letter-spacing:1.5px; text-transform:uppercase; }
  .vw-codename { color:#00BB7A; font-weight:700; }
  .vw-card   { background:#0E0E0E; border:1px solid #222222; border-radius:8px;
               padding:14px 16px; margin-bottom:10px; }
  .vw-source-row { display:flex; align-items:center; gap:8px; padding:5px 0;
                   color:#7E7E7E; font-size:12px; font-family:Menlo,monospace; }
  .vw-pulse  { width:8px; height:8px; border-radius:50%; background:#00FFA7;
               box-shadow:0 0 8px #00FFA7; animation:pulse 1.6s infinite; }
  @keyframes pulse { 0%,100% { opacity:1; } 50% { opacity:0.35; } }
  .vw-grade-GO     { background:#00BB7A; color:#0A0A0A; }
  .vw-grade-CAUTION{ background:#FFB347; color:#0A0A0A; }
  .vw-grade-NO-GO  { background:#FF5577; color:#FFFFFF; }
  .vw-grade-pill { display:inline-block; padding:6px 14px; border-radius:14px;
                   font-weight:800; letter-spacing:1px; font-size:14px; }
  .vw-footer { text-align:center; color:#6A6969; padding:18px 0 4px 0; font-size:12px;
               border-top:1px solid #222222; margin-top:24px; }
  .vw-brief { font-family:Menlo,monospace; white-space:pre-wrap; color:#E8E8E8;
              background:#0A0A0A; border:1px solid #00BB7A33; padding:14px; border-radius:6px;
              line-height:1.55; font-size:13px; }
  .vw-risk-tag { display:inline-block; background:#1a1a1a; border:1px solid #00FFA744;
                 color:#00FFA7; padding:3px 10px; border-radius:4px; font-size:11px;
                 margin-right:6px; margin-top:4px; font-family:Menlo,monospace; }
</style>
"""
st.markdown(BRAND_CSS, unsafe_allow_html=True)


# ----- Header -----
st.markdown(
    """
    <div class='vw-header'>
      <div>
        <span class='vw-title'><span class='vw-codename'>WEATHERVANE</span></span><br/>
        <span class='vw-tag'>Weather - Earth-Observation - Atmospherics - Hydrology Intelligence Engine</span>
      </div>
      <div style='text-align:right;color:#7E7E7E;font-size:12px;'>
        Agent #12 - USMC LOGCOM CDAO @ MDM 2026<br/>
        <span style='color:#00FFA7'>NASA Earthdata fusion - Kamiwaza Stack</span>
      </div>
    </div>
    """,
    unsafe_allow_html=True,
)


# ----- Data loader -----
DATA_DIR = APP_DIR / "data"


@st.cache_data
def load_manifest() -> dict:
    p = DATA_DIR / "manifest.json"
    if not p.exists():
        st.error(
            "data/manifest.json missing. Run `python data/generate.py` first."
        )
        st.stop()
    return json.loads(p.read_text())


@st.cache_data
def load_csv(slug: str) -> pd.DataFrame:
    return pd.read_csv(DATA_DIR / f"{slug}.csv")


manifest = load_manifest()


# ----- Sidebar (mission inputs) -----
with st.sidebar:
    st.markdown("### Mission Parameters")

    loc_options = {loc["name"]: loc for loc in manifest["locations"]}
    location_name = st.selectbox(
        "Area of Operations",
        list(loc_options.keys()),
        index=0,
    )
    location = loc_options[location_name]

    mission = st.selectbox(
        "Mission Profile",
        list(MISSION_PROFILES.keys()),
        index=0,
    )

    st.markdown("---")
    st.markdown("### Date Window")
    horizon_start = pd.to_datetime(manifest["horizon_start_utc"])
    horizon_end = horizon_start + pd.Timedelta(hours=manifest["hours"] - 1)

    # Default planning window: 14-21 May 2026 (matches Subic Bay scenario)
    default_start = max(horizon_start.date(), pd.Timestamp("2026-05-14").date())
    default_end = min(horizon_end.date(), pd.Timestamp("2026-05-21").date())

    win_start = st.date_input(
        "Window start (UTC)",
        value=default_start,
        min_value=horizon_start.date(),
        max_value=horizon_end.date(),
    )
    win_end = st.date_input(
        "Window end (UTC)",
        value=default_end,
        min_value=horizon_start.date(),
        max_value=horizon_end.date(),
    )

    st.markdown("---")
    hero = st.toggle("Use hero model (Kamiwaza-deployed)", value=False,
                     help="Routes the narrative brief through the larger Kamiwaza-deployed model.")

    run = st.button("Generate Environmental Brief", type="primary", use_container_width=True)

    st.markdown("---")
    st.markdown(
        f"<div style='color:#6A6969;font-size:11px;line-height:1.5'>"
        f"AOI: <span style='color:#00FFA7'>{location['lat']:.2f}, {location['lon']:.2f}</span><br/>"
        f"Horizon: {horizon_start:%d %b} to {horizon_end:%d %b %Y}<br/>"
        f"Records loaded: <span style='color:#00BB7A'>{location['rows']}</span>"
        f"</div>",
        unsafe_allow_html=True,
    )


# ----- Main column 1: source ingest panel -----
left, right = st.columns([1, 2])

with left:
    st.markdown("#### Live Ingest")
    st.markdown("<div class='vw-card'>", unsafe_allow_html=True)
    for src in manifest["sources_simulated"]:
        st.markdown(
            f"<div class='vw-source-row'>"
            f"<span class='vw-pulse'></span>{src}</div>",
            unsafe_allow_html=True,
        )
    st.markdown("</div>", unsafe_allow_html=True)

    st.markdown("#### Mission Constraints")
    profile = MISSION_PROFILES[mission]
    st.markdown(
        "<div class='vw-card' style='font-family:Menlo,monospace;font-size:12px;color:#E8E8E8;'>"
        f"<b style='color:#00FFA7'>{mission}</b><br/><br/>"
        f"max Hs &nbsp;= <span style='color:#00BB7A'>{profile['max_hs_m']} m</span><br/>"
        f"max wind = <span style='color:#00BB7A'>{profile['max_wind_kn']} kn</span><br/>"
        f"max precip = <span style='color:#00BB7A'>{profile['max_precip_mmhr']} mm/hr</span><br/>"
        f"max cloud = <span style='color:#00BB7A'>{profile['min_visibility_proxy_cloud_pct']}%</span><br/><br/>"
        f"<i style='color:#7E7E7E'>{profile['notes']}</i>"
        "</div>",
        unsafe_allow_html=True,
    )

# ----- Main column 2: results -----
with right:
    if not run:
        st.markdown("#### Awaiting tasking")
        st.markdown(
            "<div class='vw-card' style='color:#7E7E7E;line-height:1.6'>"
            "Select an Area of Operations, mission profile, and window in the left panel.<br/><br/>"
            "WEATHERVANE will fuse the four NASA Earth-observation sources into a single mission "
            "brief in <span style='color:#00FFA7'>under 5 seconds</span>, including a typed "
            "go/no-go grade, a recommended H-hour window, and prioritized risk callouts."
            "</div>",
            unsafe_allow_html=True,
        )
    else:
        df = load_csv(location["slug"])
        start_iso = datetime.combine(win_start, datetime.min.time(), tzinfo=timezone.utc).isoformat()
        end_iso = datetime.combine(win_end, datetime.max.time().replace(microsecond=0), tzinfo=timezone.utc).isoformat()
        with st.spinner("Fusing NASA MERRA-2 / GPM / GHRSST / MODIS / WAVEWATCH III + LLM synthesis..."):
            try:
                result = fuse(df, location_name=location_name, start_iso=start_iso,
                              end_iso=end_iso, mission=mission, hero=hero)
            except Exception as e:  # noqa: BLE001
                st.error(f"Agent fusion failed: {e}")
                st.stop()

        if "error" in result:
            st.error(result["error"])
            st.stop()

        rec = result["recommendation"]
        grade = (rec.get("grade") or "CAUTION").upper().replace(" ", "-")
        grade_class = grade if grade in ("GO", "CAUTION", "NO-GO") else "CAUTION"
        confidence = rec.get("confidence_pct", 0)
        risks = rec.get("top_risks") or []

        # Grade banner
        st.markdown(
            f"<div class='vw-card' style='display:flex;justify-content:space-between;"
            f"align-items:center;'>"
            f"<div><span class='vw-grade-pill vw-grade-{grade_class}'>{grade}</span>"
            f"&nbsp;&nbsp;<span style='color:#FFFFFF;font-weight:600;font-size:14px'>"
            f"{rec.get('one_liner','')}</span></div>"
            f"<div style='color:#7E7E7E;font-size:12px'>"
            f"Confidence <span style='color:#00FFA7;font-weight:700'>{confidence}%</span>"
            f"</div></div>",
            unsafe_allow_html=True,
        )

        # Recommended window box
        rec_win = rec.get("recommended_window") or {}
        if rec_win:
            try:
                rs = pd.to_datetime(rec_win["start"])
                re_ = pd.to_datetime(rec_win["end"])
                st.markdown(
                    f"<div class='vw-card' style='border-color:#00FFA7'>"
                    f"<div style='color:#00FFA7;font-size:11px;letter-spacing:1.5px;"
                    f"text-transform:uppercase'>Recommended H-Hour Window</div>"
                    f"<div style='font-family:Menlo,monospace;font-size:18px;color:#FFFFFF;"
                    f"margin-top:4px'>{rs:%d %b %Y, %H%MZ} &rarr; {re_:%H%MZ}</div>"
                    + ("".join([f"<span class='vw-risk-tag'>{r}</span>" for r in risks]))
                    + "</div>",
                    unsafe_allow_html=True,
                )
            except Exception:
                pass

        # Charts
        for spec in CHARTS:
            fig = make_chart(result["window_df"], spec, recommended_window=rec_win)
            st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})

        # Brief
        st.markdown("#### Mission Brief")
        st.markdown(f"<div class='vw-brief'>{result['brief']}</div>",
                    unsafe_allow_html=True)


# ----- Footer -----
st.markdown(
    "<div class='vw-footer'>WEATHERVANE - Powered by Kamiwaza - "
    "100% data containment - Nothing ever leaves your accredited environment.</div>",
    unsafe_allow_html=True,
)
