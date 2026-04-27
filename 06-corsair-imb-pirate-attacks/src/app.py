# CORSAIR — pirate-attack KDE forecast + maritime intel summary
# Part of the MDM 2026 Hackathon Templates (https://github.com/12fn/MDMhackathon-repos)
# MIT licensed. Built on GAI (Government Acquisitions, Inc.) + Kamiwaza (https://www.kamiwaza.ai/).
"""CORSAIR — Coastal & Open-water Risk Synthesizer for Asymmetric Maritime
Incidents and Routes. Streamlit single-file app.

Run:
    streamlit run src/app.py --server.port 3006
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

import folium
import numpy as np
import pandas as pd
import streamlit as st
from folium.plugins import HeatMap
from streamlit_folium import st_folium

# repo-root on path so `from shared.kamiwaza_client import BRAND` works
ROOT = Path(__file__).resolve().parent.parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from shared.kamiwaza_client import BRAND  # noqa: E402

# allow `from forecaster import ...` and `from agent import ...`
sys.path.insert(0, str(Path(__file__).resolve().parent))
from forecaster import (  # noqa: E402
    BASIN_BBOX, forecast, load_attacks, nearest_historical, trend_delta,
)
from agent import generate_mis, generate_indicator_board  # noqa: E402


st.set_page_config(
    page_title="CORSAIR — Maritime Risk Synthesizer",
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---------------- Kamiwaza dark theme ----------------
KAMIWAZA_CSS = f"""
<style>
:root {{
  --kw-bg:        {BRAND['bg']};
  --kw-surface:   {BRAND['surface']};
  --kw-surface2:  {BRAND['surface_high']};
  --kw-border:    {BRAND['border']};
  --kw-primary:   {BRAND['primary']};
  --kw-neon:      {BRAND['neon']};
  --kw-muted:     {BRAND['muted']};
}}
.stApp, body {{ background: var(--kw-bg) !important; color: #E5E5E5; }}
.block-container {{ padding-top: 1.2rem; max-width: 1500px; }}
section[data-testid="stSidebar"] {{
  background: var(--kw-surface) !important; border-right: 1px solid var(--kw-border);
}}
section[data-testid="stSidebar"] * {{ color: #E5E5E5 !important; }}
h1, h2, h3, h4 {{ color: #FFFFFF; letter-spacing: 0.4px; }}
h1 {{ font-weight: 700; }}
.stButton > button, .stDownloadButton > button {{
  background: var(--kw-primary); color: #04140C; border: none; font-weight: 600;
  border-radius: 6px;
}}
.stButton > button:hover {{ background: {BRAND['primary_hover']}; color: #04140C; }}
.metric-card {{
  background: var(--kw-surface2); border: 1px solid var(--kw-border);
  border-radius: 10px; padding: 14px 16px; margin-bottom: 8px;
}}
.metric-card .label {{ color: var(--kw-muted); font-size: 0.8rem; text-transform: uppercase;
  letter-spacing: 0.7px; }}
.metric-card .val {{ color: var(--kw-neon); font-size: 1.6rem; font-weight: 700; }}
.metric-card .sub {{ color: #BDBDBD; font-size: 0.82rem; }}
.mis-panel {{
  background: var(--kw-surface2); border: 1px solid var(--kw-border);
  border-left: 3px solid var(--kw-primary);
  border-radius: 8px; padding: 14px 18px; font-family: 'JetBrains Mono', ui-monospace,
  Menlo, monospace; font-size: 0.86rem; line-height: 1.45; white-space: pre-wrap;
}}
.brand-footer {{
  margin-top: 1.2rem; padding-top: 0.6rem; border-top: 1px solid var(--kw-border);
  color: var(--kw-muted); font-size: 0.78rem; display:flex; justify-content:space-between;
}}
.tag {{ display:inline-block; padding: 2px 8px; border-radius: 999px;
  background: rgba(0,255,167,0.10); border: 1px solid var(--kw-primary);
  color: var(--kw-neon); font-size: 0.72rem; margin-left: 6px;}}
.hotspot-row {{ background: var(--kw-surface2); border:1px solid var(--kw-border);
  border-radius: 6px; padding: 8px 10px; margin-bottom:6px;}}
.threat-LOW    {{ color:#7FE5A1; }}
.threat-GUARDED{{ color:#A3E07F; }}
.threat-ELEVATED{{ color:#F2C94C; }}
.threat-HIGH   {{ color:#F28C28; }}
.threat-SEVERE {{ color:#FF4D4D; }}
</style>
"""
st.markdown(KAMIWAZA_CSS, unsafe_allow_html=True)


# ---------------- Header ----------------
hdr_l, hdr_r = st.columns([0.66, 0.34])
with hdr_l:
    st.markdown(
        "<h1 data-testid='app-title'>CORSAIR "
        "<span class='tag'>Agent #06 · LOGCOM Contested Logistics</span></h1>",
        unsafe_allow_html=True,
    )
    st.markdown(
        "<div style='color:#BDBDBD;font-size:0.95rem;'>Coastal & Open-water Risk "
        "Synthesizer for Asymmetric Maritime Incidents and Routes — "
        "<i>Deploy mission intelligence without moving your data.</i></div>",
        unsafe_allow_html=True,
    )
with hdr_r:
    st.markdown(
        f"<div style='text-align:right;padding-top:6px;'>"
        f"<img src='{BRAND['logo_url']}' style='height:34px;opacity:0.95;'/></div>",
        unsafe_allow_html=True,
    )


# ---------------- Data load (cached) ----------------
@st.cache_data(show_spinner=False)
def _load() -> pd.DataFrame:
    return load_attacks()


df = _load()


# ---------------- Sidebar: routing controls ----------------
with st.sidebar:
    st.markdown("### Mission Routing Inputs")
    basin = st.selectbox(
        "Theater of focus (ocean basin)",
        list(BASIN_BBOX.keys()),
        index=0,
        key="basin_select",
    )
    horizon_days = st.slider("Forecast horizon (days)", 7, 60, 30, step=1)
    asof_default = pd.Timestamp("2025-12-15")
    asof = st.date_input("Effective as-of date", value=asof_default.date())
    hero_model = st.checkbox("Use hero model (Kamiwaza-deployed) for MIS narrative", value=False,
                             help="Marquee call — slower, higher quality. Use once per demo.")
    st.divider()
    st.markdown("### Kamiwaza Stack")
    st.markdown(
        "- Inference Mesh (vLLM)\n"
        "- DDE — Distributed Data Engine\n"
        "- Model Gateway (Kamiwaza-deployed: any LLM)\n"
        "- ReBAC access control\n"
        "- IL5/IL6 ready · NIPR/SIPR/JWICS"
    )
    st.markdown(
        "<div style='color:#7FE5A1; font-size:0.78rem; margin-top:0.5rem;'>"
        "Set <code>KAMIWAZA_BASE_URL</code> → 100% on-prem. Zero code change.</div>",
        unsafe_allow_html=True,
    )


# ---------------- Run forecast ----------------
asof_dt = datetime.combine(asof, datetime.min.time())
fc = forecast(basin, asof_dt, df=df)
trend = trend_delta(df, basin)

# Scale expected attacks to selected horizon
expected_for_horizon = fc.expected_attacks_30d * (horizon_days / 30.0)


# ---------------- KPI strip ----------------
k1, k2, k3, k4 = st.columns(4)
def metric(col, label, value, sub):
    col.markdown(
        f"<div class='metric-card'><div class='label'>{label}</div>"
        f"<div class='val'>{value}</div><div class='sub'>{sub}</div></div>",
        unsafe_allow_html=True,
    )

metric(k1, "Theater", fc.basin, f"{fc.n_train} training incidents")
metric(k2, f"Expected attacks · next {horizon_days}d", f"{expected_for_horizon:.1f}",
       f"recency-weighted KDE rate")
delta_color = "#FF4D4D" if trend["delta_pct"] > 0 else "#7FE5A1"
metric(k3, "5y trend Δ vs prior 5y", f"{trend['delta_pct']:+.1f}%",
       f"recent={trend['n_recent_5y']}  prior={trend['n_prior_5y']}")
shift_lbl = "MOA shift" if trend["shift"] else "MOA stable"
metric(k4, "Dominant MOA (recent)", trend["moa_recent"],
       f"{shift_lbl} · prior={trend['moa_prior']}")


# ---------------- Map + side panel ----------------
left, right = st.columns([0.62, 0.38])

with left:
    st.markdown("#### 30-Day Risk Grid · Heatmap of forecasted hostile-activity density")
    lat_c = float(np.mean([fc.grid_lat.min(), fc.grid_lat.max()]))
    lon_c = float(np.mean([fc.grid_lon.min(), fc.grid_lon.max()]))
    fmap = folium.Map(
        location=[lat_c, lon_c],
        zoom_start=5 if basin != "All Basins" else 2,
        tiles="CartoDB dark_matter",
        attr="CartoDB.DarkMatter",
        control_scale=True,
    )
    # Build heat point list from the forecast grid
    heat = []
    for i, la in enumerate(fc.grid_lat):
        for j, lo in enumerate(fc.grid_lon):
            r = float(fc.risk[i, j])
            if r > 0.05:
                heat.append([la, lo, r])
    HeatMap(
        heat, radius=18, blur=22, min_opacity=0.25, max_zoom=8,
        gradient={0.2: "#065238", 0.4: "#00BB7A", 0.6: "#00FFA7", 0.85: "#F2C94C", 1.0: "#FF4D4D"},
    ).add_to(fmap)
    # Hotspot pins
    for i, h in enumerate(fc.hotspots, 1):
        folium.CircleMarker(
            location=[h["lat"], h["lon"]],
            radius=10 + 6 * h["risk"],
            color="#00FFA7", fill=True, fill_color="#00FFA7", fill_opacity=0.85,
            popup=f"<b>Hotspot #{i}</b><br>{h['lat']:.2f}, {h['lon']:.2f}<br>"
                  f"Risk {h['risk']:.2f}",
            tooltip=f"#{i}  risk {h['risk']:.2f}",
        ).add_to(fmap)
    # Sample of recent attacks
    sub = df[df["basin"] == basin] if basin != "All Basins" else df
    sample = sub.sort_values("datetime", ascending=False).head(120)
    for _, row in sample.iterrows():
        folium.CircleMarker(
            location=[row["lat"], row["lon"]],
            radius=2, color="#7E7E7E", fill=True, fill_opacity=0.6,
        ).add_to(fmap)
    map_state = st_folium(fmap, width=None, height=520, returned_objects=["last_object_clicked"])

with right:
    st.markdown("#### Top-5 Risk Hotspots")
    for i, h in enumerate(fc.hotspots, 1):
        st.markdown(
            f"<div class='hotspot-row'><b>#{i}</b> &nbsp; "
            f"<code>{h['lat']:.2f}N / {h['lon']:.2f}E</code>"
            f"<span class='tag' style='float:right;'>risk {h['risk']:.2f}</span>"
            f"</div>",
            unsafe_allow_html=True,
        )

    if fc.hotspots:
        sel = st.selectbox(
            "Drilldown · pick a hotspot for the 3 most relevant historical incidents",
            [f"#{i+1}  ({h['lat']:.2f}, {h['lon']:.2f})" for i, h in enumerate(fc.hotspots)],
            index=0,
            key="hotspot_select",
        )
        idx = int(sel.split()[0].lstrip("#")) - 1
        h = fc.hotspots[idx]
        nearest = nearest_historical(df, h["lat"], h["lon"], k=3)
        st.markdown("**Historical incidents that informed this forecast:**")
        for _, row in nearest.iterrows():
            st.markdown(
                f"<div class='hotspot-row'>"
                f"<div style='color:#BDBDBD;font-size:0.82rem;'>"
                f"{row['datetime'].date()} · {row['vessel_type']} · {row['attack_type']}</div>"
                f"<div style='font-size:0.84rem;margin-top:4px;'>{row['narrative']}</div>"
                f"</div>",
                unsafe_allow_html=True,
            )


# ---------------- AI panel ----------------
st.markdown("---")
st.markdown("#### Maritime Intel Summary (MIS) · Generated by CORSAIR Agent")
ai_l, ai_r = st.columns([0.6, 0.4])

run_btn = ai_l.button("Generate MIS + indicator board", type="primary", key="gen_mis_btn")

if "mis_result" not in st.session_state:
    st.session_state["mis_result"] = None
    st.session_state["indicator_board"] = None

if run_btn:
    sub = df[df["basin"] == basin] if basin != "All Basins" else df
    recent_incidents = (
        sub.sort_values("datetime", ascending=False).head(6).to_dict(orient="records")
    )
    # serialize datetimes for JSON
    for r in recent_incidents:
        if isinstance(r.get("datetime"), pd.Timestamp):
            r["datetime"] = r["datetime"].isoformat()
    with st.spinner("Routing inference through Kamiwaza Model Gateway…"):
        try:
            mis_text = generate_mis(
                basin=basin,
                asof=asof.isoformat(),
                hotspots=fc.hotspots,
                trend=trend,
                recent_incidents=recent_incidents,
                expected_30d=expected_for_horizon,
                model="gpt-5.4" if hero_model else None,
            )
            st.session_state["mis_result"] = mis_text
        except Exception as e:  # noqa: BLE001
            st.session_state["mis_result"] = f"[error generating MIS] {e}"
        try:
            board = generate_indicator_board(
                basin=basin,
                hotspots=fc.hotspots,
                trend=trend,
                expected_30d=expected_for_horizon,
                recent_incidents=recent_incidents,
            )
            st.session_state["indicator_board"] = board
        except Exception as e:  # noqa: BLE001
            st.session_state["indicator_board"] = {"error": str(e)}

with ai_l:
    st.markdown("**SIPR-style narrative**")
    if st.session_state["mis_result"]:
        st.markdown(
            f"<div class='mis-panel' data-testid='mis-output'>{st.session_state['mis_result']}</div>",
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            "<div class='mis-panel' style='color:#7E7E7E;'>"
            "Click <b>Generate MIS + indicator board</b> to draft a SIPR-format Maritime "
            "Intel Summary covering BLUF, threat picture, assessed actor, MOA pattern shifts, "
            "recommended route deviations, and confidence."
            "</div>",
            unsafe_allow_html=True,
        )

with ai_r:
    st.markdown("**Structured indicator board (JSON)**")
    board = st.session_state["indicator_board"]
    if board:
        threat = (board.get("threat_level") or "").upper() if isinstance(board, dict) else ""
        if threat:
            st.markdown(
                f"<div class='metric-card'><div class='label'>Assessed Threat Level</div>"
                f"<div class='val threat-{threat}'>{threat}</div>"
                f"<div class='sub'>derived from KDE risk + trend Δ + MOA shift</div></div>",
                unsafe_allow_html=True,
            )
        st.code(json.dumps(board, indent=2), language="json")
    else:
        st.markdown(
            "<div class='mis-panel' style='color:#7E7E7E;'>"
            "JSON-mode output will populate here: threat level, hotspots with labels, "
            "MOA shift, recommended route deviations, indicators to watch."
            "</div>",
            unsafe_allow_html=True,
        )


# ---------------- Footer ----------------
st.markdown(
    f"<div class='brand-footer'>"
    f"<span>CORSAIR · Powered by Kamiwaza · "
    f"3,000 synthetic ASAM-style incidents 1993–2025 · KDE forecast bandwidth "
    f"{fc.bandwidth:.2f}°</span>"
    f"<span>Real dataset: <i>Global Maritime Pirate Attacks 1993–2020</i> "
    f"(IMB / ASAM / NGA WW Threats to Shipping mirror)</span>"
    f"</div>",
    unsafe_allow_html=True,
)
