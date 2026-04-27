# RIPTIDE — installation flood-risk + impact assessment
# Part of the MDM 2026 Hackathon Templates (https://github.com/12fn/MDMhackathon-repos)
# MIT licensed. Built on GAI (Government Acquisitions, Inc.) + Kamiwaza (https://www.kamiwaza.ai/).
"""RIPTIDE — Streamlit UI for flood-risk + claims-cost forecasting.

Run with:
    BACKEND_URL=http://localhost:8004 streamlit run frontend/app.py --server.port 3004
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path

import folium
import requests
import streamlit as st
from folium.plugins import HeatMap
from streamlit_folium import st_folium

BACKEND = os.getenv("BACKEND_URL", "http://localhost:8004")
BRAND_PRIMARY = "#00BB7A"
BRAND_NEON = "#00FFA7"
BRAND_BG = "#0A0A0A"
BRAND_SURFACE = "#0E0E0E"
BRAND_BORDER = "#222222"
BRAND_MUTED = "#7E7E7E"
LOGO_URL = "https://www.kamiwaza.ai/hubfs/logo-light.svg"

st.set_page_config(
    page_title="RIPTIDE — USMC Flood-Risk Forecaster",
    page_icon="🌊",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ---------- Kamiwaza dark theme ----------
st.markdown(
    f"""
    <style>
      html, body, [class*="stAppViewContainer"], [data-testid="stAppViewContainer"] {{
          background-color: {BRAND_BG} !important;
          color: #E8E8E8 !important;
      }}
      [data-testid="stHeader"] {{ background: {BRAND_BG} !important; }}
      .block-container {{ padding-top: 1.4rem; padding-bottom: 1rem; max-width: 1400px; }}
      h1, h2, h3, h4 {{ color: #F2F2F2 !important; letter-spacing: -0.02em; }}
      .riptide-hero {{
          display:flex; align-items:center; gap:14px;
          border:1px solid {BRAND_BORDER}; background:{BRAND_SURFACE};
          padding:14px 18px; border-radius:10px; margin-bottom:14px;
      }}
      .riptide-hero img {{ height:30px; }}
      .riptide-hero .title {{ font-size:1.6rem; font-weight:700; color:{BRAND_NEON}; }}
      .riptide-hero .tag {{ color:{BRAND_MUTED}; font-size:0.95rem; }}
      .riptide-card {{
          border:1px solid {BRAND_BORDER}; background:{BRAND_SURFACE};
          padding:14px 16px; border-radius:10px; margin-bottom:10px;
      }}
      .riptide-kpi-num {{ font-size:1.7rem; font-weight:700; color:{BRAND_NEON}; }}
      .riptide-kpi-label {{ font-size:0.8rem; color:{BRAND_MUTED}; text-transform:uppercase; letter-spacing:0.08em; }}
      .riptide-mission {{
          border-left:3px solid {BRAND_PRIMARY}; padding:6px 12px;
          background:#0c1612; color:#cfe9dd; font-size:0.9rem; margin-bottom:14px;
          border-radius:4px;
      }}
      .riptide-footer {{ color:{BRAND_MUTED}; font-size:0.85rem; text-align:center;
          margin-top:30px; padding-top:14px; border-top:1px solid {BRAND_BORDER}; }}
      .stSelectbox label, .stRadio label, .stSlider label {{ color:#cfcfcf !important; }}
      .stButton button {{
          background:{BRAND_PRIMARY} !important; color:#001a10 !important;
          border:none !important; font-weight:700 !important;
          padding:0.55rem 1.3rem !important; border-radius:8px !important;
      }}
      .stButton button:hover {{ background:{BRAND_NEON} !important; }}
      .action-row {{
          display:grid; grid-template-columns: 50px 1fr 130px 90px 110px;
          gap:10px; padding:10px 12px; border-bottom:1px solid {BRAND_BORDER};
          align-items:center; font-size:0.93rem;
      }}
      .action-row.head {{ color:{BRAND_MUTED}; font-size:0.78rem; text-transform:uppercase; }}
      .pri-pill {{ display:inline-block; min-width:28px; text-align:center;
          background:{BRAND_PRIMARY}; color:#001a10; border-radius:14px;
          padding:2px 8px; font-weight:800; }}
      .pri-pill.p1 {{ background:#ff6b4a; color:#1a0500; }}
      .pri-pill.p2 {{ background:#ffae3a; color:#1a0a00; }}
      .pri-pill.p3 {{ background:{BRAND_NEON}; color:#001a10; }}
      .pri-pill.p4 {{ background:{BRAND_PRIMARY}; color:#001a10; }}
      .pri-pill.p5 {{ background:#3f7a64; color:#001a10; }}
      .narr-box {{
          border:1px solid {BRAND_BORDER}; background:#0c1410;
          padding:14px 18px; border-radius:8px; line-height:1.55;
          color:#dde9e2; white-space:pre-wrap;
      }}
    </style>
    """,
    unsafe_allow_html=True,
)

# ---------- Hero header ----------
st.markdown(
    f"""
    <div class="riptide-hero">
      <img src="{LOGO_URL}" alt="Kamiwaza"/>
      <div>
        <div class="title">RIPTIDE</div>
        <div class="tag">Resilience &amp; Inundation Predictive Tide-zone Intelligence Decision Engine
        &nbsp;·&nbsp; Forecast the flood before it floods readiness.</div>
      </div>
    </div>
    <div class="riptide-mission">
      <b>Mission frame —</b> LOGCOM Installation Incident Response:
      <i>"digital tools to enhance situational awareness and response coordination during installation-level incidents."</i>
    </div>
    """,
    unsafe_allow_html=True,
)


# ---------- Data load (cached) ----------
@st.cache_data(ttl=300)
def fetch(url: str, default=None):
    try:
        r = requests.get(url, timeout=15)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        st.error(f"Backend unreachable: {url} — {e}")
        return default


@st.cache_data(ttl=300)
def fetch_aggregate(installation_id: str, scenario_id: str, radius_nm: float):
    return fetch(
        f"{BACKEND}/api/claims/aggregate?installation={installation_id}"
        f"&scenario={scenario_id}&radius_nm={radius_nm}"
    )


installations = fetch(f"{BACKEND}/api/installations", default=[])
scenarios = fetch(f"{BACKEND}/api/scenarios", default={})

if not installations or not scenarios:
    st.warning("Cannot reach backend. Start it with: `uvicorn backend.app:app --port 8004`")
    st.stop()

# ---------- Controls + KPIs ----------
left, right = st.columns([1, 2])

with left:
    st.markdown("#### Operator Controls")
    inst_options = {f"{i['name']} ({i['state']})": i["id"] for i in installations}
    inst_label = st.selectbox("Installation", list(inst_options.keys()), index=1)
    installation_id = inst_options[inst_label]

    scen_options = {v["label"]: k for k, v in scenarios.items()}
    scen_label = st.selectbox(
        "Scenario", list(scen_options.keys()),
        index=list(scen_options.keys()).index("Category 3 Hurricane")
        if "Category 3 Hurricane" in scen_options else 0,
    )
    scenario_id = scen_options[scen_label]

    radius_nm = st.slider("Search radius (nm)", 25, 150, 50, 5)
    run_btn = st.button("⚡ Run Operational Impact Assessment", use_container_width=True)

agg = fetch_aggregate(installation_id, scenario_id, radius_nm)

with right:
    if agg:
        c1, c2, c3, c4 = st.columns(4)
        for col, label, val in [
            (c1, "Historic claims (radius)", f"{agg['claims_in_radius']:,}"),
            (c2, "Historic $ paid", f"${agg['historic_paid_usd']/1e6:.1f}M"),
            (c3, "Projected claims $", f"${agg['projected_claims_usd']/1e6:.1f}M"),
            (c4, "Days to MC restore", f"{agg['days_to_mission_capable']}d"),
        ]:
            with col:
                st.markdown(
                    f'<div class="riptide-card">'
                    f'<div class="riptide-kpi-label">{label}</div>'
                    f'<div class="riptide-kpi-num">{val}</div></div>',
                    unsafe_allow_html=True,
                )

# ---------- Map ----------
st.markdown("### Historic NFIP Claim Density (5,000-record synthetic, FEMA-schema)")
inst = next(i for i in installations if i["id"] == installation_id)

m = folium.Map(
    location=[inst["lat"], inst["lon"]],
    zoom_start=7,
    tiles="cartodbdark_matter",
    control_scale=True,
)
# Installation marker
folium.CircleMarker(
    location=[inst["lat"], inst["lon"]],
    radius=14, color=BRAND_NEON, fill=True, fill_color=BRAND_NEON, fill_opacity=0.85,
    popup=folium.Popup(
        f"<b>{inst['name']}</b><br>{inst['personnel']:,} personnel<br>{inst['notable_history']}",
        max_width=320),
    tooltip=inst["name"],
).add_to(m)
# Radius ring
folium.Circle(
    location=[inst["lat"], inst["lon"]],
    radius=radius_nm * 1852,  # nm -> meters
    color=BRAND_PRIMARY, weight=2, fill=False, dash_array="6,8",
    tooltip=f"{radius_nm} nm risk radius",
).add_to(m)

if agg and agg["heat"]:
    heat_pts = [
        [h["latitude"], h["longitude"], min(1.0, h["paid"] / 50_000)]
        for h in agg["heat"]
    ]
    HeatMap(heat_pts, radius=14, blur=22, max_zoom=10,
            gradient={0.2: "#0a3a25", 0.4: BRAND_PRIMARY, 0.7: BRAND_NEON, 1.0: "#ffd166"}).add_to(m)

st_folium(m, width=None, height=460, returned_objects=[])

# ---------- AI assessment ----------
st.markdown("### Operational Impact Assessment")
narr_slot = st.empty()
actions_slot = st.empty()

if "last_run" not in st.session_state:
    st.session_state.last_run = {"installation_id": None, "scenario_id": None}

should_run = run_btn or (
    st.session_state.last_run["installation_id"] == installation_id
    and st.session_state.last_run["scenario_id"] == scenario_id
    and st.session_state.last_run.get("narrative")
)

if run_btn:
    with st.spinner(f"Kamiwaza-deployed model streaming OIA for {inst['name']} · {scenarios[scenario_id]['label']}…"):
        try:
            r = requests.post(
                f"{BACKEND}/api/assess",
                json={"installation_id": installation_id, "scenario_id": scenario_id, "radius_nm": radius_nm},
                timeout=90,
            )
            r.raise_for_status()
            narrative = r.json().get("narrative", "")
        except Exception as e:
            narrative = f"[LLM error] {e}\n\nFalling back to template:\n\n" + (
                f"Projected exposure for {inst['name']} under {scenarios[scenario_id]['label']} is "
                f"${agg['projected_claims_usd']/1e6:.1f}M over {agg['days_to_mission_capable']} days "
                "to mission-capable restoration."
            )
        try:
            r2 = requests.post(
                f"{BACKEND}/api/actions",
                json={"installation_id": installation_id, "scenario_id": scenario_id, "radius_nm": radius_nm},
                timeout=90,
            )
            r2.raise_for_status()
            actions = r2.json().get("actions", [])
        except Exception as e:
            actions = [{"priority": 1, "action": f"LLM error: {e}", "asset": "n/a",
                        "lead_time_hrs": 0, "cost_estimate_usd": 0, "rationale": ""}]

    st.session_state.last_run = {
        "installation_id": installation_id, "scenario_id": scenario_id,
        "narrative": narrative, "actions": actions,
    }

if st.session_state.last_run.get("narrative"):
    # Streaming feel: render character chunks.
    narrative = st.session_state.last_run["narrative"]
    actions = st.session_state.last_run["actions"]
    if run_btn:
        # Animate
        buf = ""
        for chunk in [narrative[i:i+60] for i in range(0, len(narrative), 60)]:
            buf += chunk
            narr_slot.markdown(f'<div class="narr-box">{buf}</div>', unsafe_allow_html=True)
            time.sleep(0.025)
    else:
        narr_slot.markdown(f'<div class="narr-box">{narrative}</div>', unsafe_allow_html=True)

    # Actions table
    rows_html = ['<div class="action-row head"><div>PRI</div><div>ACTION</div><div>ASSET</div><div>LEAD (h)</div><div>COST</div></div>']
    for a in sorted(actions, key=lambda x: x.get("priority", 99)):
        p = int(a.get("priority", 5))
        rows_html.append(
            f'<div class="action-row">'
            f'<div><span class="pri-pill p{p}">P{p}</span></div>'
            f'<div><b>{a.get("action","")}</b><br>'
            f'<span style="color:{BRAND_MUTED}; font-size:0.82rem;">{a.get("rationale","")}</span></div>'
            f'<div>{a.get("asset","")}</div>'
            f'<div>{a.get("lead_time_hrs","")}</div>'
            f'<div>${int(a.get("cost_estimate_usd",0)):,}</div>'
            f'</div>'
        )
    actions_slot.markdown(
        '<div class="riptide-card" style="padding:0;">' + "".join(rows_html) + "</div>",
        unsafe_allow_html=True,
    )
else:
    st.info("Choose installation + scenario, then click **Run Operational Impact Assessment** to invoke the LLM.")

# ---------- On-prem story panel ----------
with st.expander("On-prem deployment — Kamiwaza env-var swap"):
    st.code(
        """# Production: Kamiwaza on-prem (default deployment target):
export KAMIWAZA_BASE_URL=https://kamiwaza.local/api/v1
export KAMIWAZA_API_KEY=<your-token>

# Optional fallback (cloud-hosted, dev only):
# unset KAMIWAZA_BASE_URL  # falls back to cloud endpoint

# 100% data containment. Nothing ever leaves your accredited environment.""",
        language="bash",
    )

# ---------- Footer ----------
st.markdown(
    f'<div class="riptide-footer">RIPTIDE · Agent #04 of 14 · Built on the Kamiwaza Stack &nbsp;·&nbsp; '
    f'<b style="color:{BRAND_NEON}">Powered by Kamiwaza</b></div>',
    unsafe_allow_html=True,
)
