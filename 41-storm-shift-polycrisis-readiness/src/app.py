"""STORM-SHIFT — Streamlit app (port 3141).

Polycrisis storm-scenario gameboard. Operator picks installation + storm
scenario; six parallel projection agents stream a cascade picture. Polycrisis
multiplier card surfaces compounding effects from co-occurring scenarios.

Run:
    cd apps/41-storm-shift
    streamlit run src/app.py --server.port 3141 --server.headless true
"""
from __future__ import annotations

import sys
from pathlib import Path

import folium
import pandas as pd
import streamlit as st
from streamlit_folium import st_folium

APP_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = APP_ROOT.parents[1]
for p in (str(REPO_ROOT), str(APP_ROOT)):
    if p not in sys.path:
        sys.path.insert(0, p)

from shared.kamiwaza_client import BRAND  # noqa: E402
from src import agent, charts, projections  # noqa: E402


# ─────────────────────────────────────────────────────────────────────────────
# Page config + theme
# ─────────────────────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="STORM-SHIFT — Polycrisis Readiness",
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
  .ss-tagline {{
    color: {BRAND['neon']};
    font-family: Helvetica, Arial, sans-serif;
    font-weight: 600;
    letter-spacing: 1.2px;
    text-transform: uppercase;
    font-size: 12px;
  }}
  .ss-headline {{
    color: #FFFFFF;
    font-family: Helvetica, Arial, sans-serif;
    font-weight: 700;
    font-size: 30px;
    line-height: 1.15;
    margin-top: 4px;
  }}
  .ss-card {{
    background: {BRAND['surface']};
    border: 1px solid {BRAND['border']};
    border-radius: 10px;
    padding: 14px 18px;
    margin-bottom: 10px;
  }}
  .ss-card-poly {{
    background: linear-gradient(135deg, #2a0a3a 0%, #0a0a0a 100%);
    border: 1px solid #C43A8B;
    border-radius: 10px;
    padding: 14px 18px;
    margin-bottom: 10px;
  }}
  .ss-pill {{
    display: inline-block;
    padding: 2px 9px;
    border-radius: 999px;
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 0.6px;
    margin-left: 6px;
  }}
  .pill-low    {{ background:#0E2F22; color:#00FFA7; border:1px solid #00BB7A; }}
  .pill-med    {{ background:#3A2C0E; color:#E0B341; border:1px solid #E0B341; }}
  .pill-high   {{ background:#3A1A0E; color:#E36F2C; border:1px solid #E36F2C; }}
  .pill-crit   {{ background:#3A0E0E; color:#FF6F66; border:1px solid #D8362F; }}
  .ss-footer {{
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
</style>
"""
st.markdown(CSS, unsafe_allow_html=True)


def status_pill(status: str) -> str:
    cls = {"GREEN": "pill-low", "AMBER": "pill-med", "RED": "pill-crit"}.get(status, "pill-low")
    return f'<span class="ss-pill {cls}">{status}</span>'


# ─────────────────────────────────────────────────────────────────────────────
# Data
# ─────────────────────────────────────────────────────────────────────────────

INSTALLATIONS = projections.load_installations()
SCENARIOS = projections.load_scenarios()


# ─────────────────────────────────────────────────────────────────────────────
# Sidebar — operator controls
# ─────────────────────────────────────────────────────────────────────────────

with st.sidebar:
    st.markdown(
        f"<div class='ss-tagline'>{BRAND['footer']}</div>"
        f"<div class='ss-headline'>STORM-SHIFT</div>"
        f"<div style='color:{BRAND['text_dim']};font-size:12px;margin-top:6px;'>"
        "Polycrisis Readiness Gameboard for<br/>USMC Installations · Climate-Driven Storm Cascades"
        "</div>",
        unsafe_allow_html=True,
    )
    st.markdown("---")
    st.markdown("**MISSION FRAME**")
    st.markdown(
        "<span style='color:#9A9A9A;font-size:12px;'>"
        "I-COP aggregator + Inventory Control Management + LogTRACE consumption — "
        "fused into a single polycrisis projection. LOGCOM problem set: "
        "<i>climate resilience, supply chain management, expeditionary readiness</i>."
        "</span>",
        unsafe_allow_html=True,
    )
    st.markdown("---")
    st.markdown("**SCENARIO**")
    inst_id = st.selectbox(
        "Landfall installation",
        options=[i["id"] for i in INSTALLATIONS],
        format_func=lambda i: next(x["name"] for x in INSTALLATIONS if x["id"] == i),
        index=1,  # Cherry Point — matches the brief's demo arc
        key="op_inst",
    )
    scenario_id = st.selectbox(
        "Storm scenario",
        options=[s["id"] for s in SCENARIOS],
        format_func=lambda s: next(x["label"] for x in SCENARIOS if x["id"] == s),
        index=4,  # cat3
        key="op_scn",
    )
    co_options = ["(none)"] + [s["id"] for s in SCENARIOS if s["id"] != scenario_id]
    # Default to atmos-river for cat3 — triggers the 1.25x polycrisis multiplier card
    default_co_idx = co_options.index("atmos-river") if "atmos-river" in co_options and scenario_id == "cat3" else 0
    co_scenario_id = st.selectbox(
        "Co-occurring scenario (polycrisis)",
        options=co_options,
        format_func=lambda s: "(none)" if s == "(none)" else next(x["label"] for x in SCENARIOS if x["id"] == s),
        index=default_co_idx,
        key="op_co_scn",
    )
    co_scenario_id = None if co_scenario_id == "(none)" else co_scenario_id

    st.markdown("---")
    hero = st.toggle(
        "Hero AI brief (Kamiwaza-deployed model)", value=True,
        help="When ON, regenerate uses the hero model. Cached briefs render instantly.",
    )

    st.markdown("---")
    st.markdown("**DATASETS (5)**")
    st.markdown(
        "<span style='color:#9A9A9A;font-size:11px;'>"
        "<b>NASA Earthdata</b> (GPM IMERG hourly grids)<br/>"
        "<b>NASA FIRMS</b> (active fire pixels)<br/>"
        "<b>FEMA NFIP Redacted Claims v2</b><br/>"
        "<b>FEMA Supply Chain Climate Resilience</b><br/>"
        "<b>Logistics-and-supply-chain-dataset (CA)</b><br/>"
        "Real-data swap recipe: <code>data/load_real.py</code>."
        "</span>",
        unsafe_allow_html=True,
    )

    st.markdown("---")
    st.markdown(
        "<span style='color:#9A9A9A;font-size:11px;'>"
        "Storm models stay in your enclave. <b>No cloud egress.</b> "
        "Set <code>KAMIWAZA_BASE_URL</code> to run on-prem."
        "</span>",
        unsafe_allow_html=True,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Header
# ─────────────────────────────────────────────────────────────────────────────

col_a, col_b = st.columns([0.65, 0.35])
with col_a:
    st.markdown(
        "<div class='ss-tagline'>Polycrisis storm-scenario gameboard · USMC installations</div>"
        "<div class='ss-headline'>The polycrisis era is here. STORM-SHIFT projects six cascading futures in parallel.</div>",
        unsafe_allow_html=True,
    )
with col_b:
    st.markdown(
        f"<div class='ss-card' style='text-align:right;'>"
        f"<div style='color:{BRAND['muted']};font-size:11px;letter-spacing:1px;'>CLASSIFICATION</div>"
        f"<div style='color:{BRAND['neon']};font-weight:700;letter-spacing:1.2px;'>UNCLASSIFIED // FOUO</div>"
        f"<div style='color:{BRAND['muted']};font-size:11px;letter-spacing:1px;margin-top:8px;'>POSTURE</div>"
        f"<div style='color:#FFFFFF;font-weight:700;'>On-prem · Kamiwaza Stack</div>"
        f"</div>",
        unsafe_allow_html=True,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Action row — projection trigger + KPI tiles
# ─────────────────────────────────────────────────────────────────────────────

if "rollup" not in st.session_state:
    # Always have something to render (so the demo never opens cold)
    st.session_state.rollup = projections.run_all_projections(inst_id, scenario_id, co_scenario_id)
    st.session_state.brief = agent.get_brief(st.session_state.rollup, hero=False)

c1, c2, c3, c4, c5 = st.columns([0.28, 0.18, 0.18, 0.18, 0.18])
with c1:
    if st.button("RUN 6 PARALLEL PROJECTIONS", use_container_width=True, type="primary",
                 key="btn_run"):
        with st.spinner("Fanning out 6 projection agents in parallel…"):
            st.session_state.rollup = projections.run_all_projections(
                inst_id, scenario_id, co_scenario_id
            )
        with st.spinner("Composing Polycrisis Readiness Brief (Kamiwaza-deployed)…"):
            st.session_state.brief = agent.get_brief(st.session_state.rollup, hero=hero)

rollup = st.session_state.rollup
bi = rollup["base_impact"]
inv = rollup["inventory"]
fi = rollup["fire"]
poly = rollup["polycrisis"]

with c2:
    st.metric("$ exposure", f"${bi['total_dollar_exposure_usd']/1e9:.2f}B")
with c3:
    st.metric("Days to MC", f"{bi['days_to_mission_capable']:.1f}d")
with c4:
    st.metric("Inv RED", f"{inv['items_red']}",
              help="Inventory classes that go red within shelter window.")
with c5:
    st.metric("Polycrisis x", f"{poly['multiplier']:.2f}",
              help="Compounding multiplier from co-occurring scenarios.")

st.markdown("---")


# ─────────────────────────────────────────────────────────────────────────────
# Top row — installation map + 6-projection panel cards
# ─────────────────────────────────────────────────────────────────────────────

g_left, g_right = st.columns([0.45, 0.55])

with g_left:
    st.markdown("#### Installation map · NFIP claim density + FIRMS pixels")
    inst = projections.installation_by_id(inst_id)
    m = folium.Map(
        location=[inst["lat"], inst["lon"]], zoom_start=8,
        tiles="CartoDB dark_matter",
    )
    folium.Marker(
        [inst["lat"], inst["lon"]],
        tooltip=inst["name"],
        icon=folium.Icon(color="green", icon="star"),
    ).add_to(m)
    # NFIP density heatmap-ish (sample ≤ 200)
    for c in projections.load_nfip()[:: max(1, len(projections.load_nfip()) // 200)]:
        d = projections.haversine_mi(c["latitude"], c["longitude"], inst["lat"], inst["lon"])
        if d > 80:
            continue
        folium.CircleMarker(
            [c["latitude"], c["longitude"]],
            radius=2.5, color="#3A4FC4", weight=0, fill=True, fill_opacity=0.6,
        ).add_to(m)
    # FIRMS pixels
    for f in projections.load_firms():
        d = projections.haversine_mi(f["latitude"], f["longitude"], inst["lat"], inst["lon"])
        if d > 80:
            continue
        folium.CircleMarker(
            [f["latitude"], f["longitude"]],
            radius=3, color="#FF6F66", weight=0, fill=True, fill_opacity=0.85,
            tooltip=f"FIRMS · FRP {f.get('frp', 0):.1f}",
        ).add_to(m)
    st_folium(m, height=420, width=None, returned_objects=[])

with g_right:
    st.markdown("#### Six parallel projection agents")
    fl = rollup["flood"]
    su = rollup["supply"]
    cons = rollup["consumption"]
    grid = st.columns(2)
    proj_cards = [
        ("1 · Flood damage",
         f"${fl['total_usd']/1e6:,.0f}M",
         f"{fl['nfip_claims_in_radius']} NFIP claims in 30-mi · severity {fl['severity']}",
         "#3A4FC4"),
        ("2 · Supply chain",
         f"{su['suppliers_affected']} suppliers",
         f"Lead-time {su['lead_time_baseline_days']:.0f}d → {su['lead_time_disrupted_days']:.0f}d · {su['lead_time_surge_factor']}x",
         "#C46B3A"),
        ("3 · Inventory cascade",
         f"{inv['items_red']} RED / {inv['items_amber']} AMBER",
         f"Headcount in shelter {inv['headcount_in_shelter']:,} · {inv['shelter_days']}d posture",
         "#FF6F66"),
        ("4 · Consumption surge",
         f"{cons['headcount']:,} pers",
         f"Top class burn: {cons['classes'][0]['total_over_shelter']:,.0f} {cons['classes'][0]['units']}",
         "#E0B341"),
        ("5 · Base impact",
         f"${bi['total_dollar_exposure_usd']/1e9:.2f}B",
         f"Days-to-MC {bi['days_to_mission_capable']:.1f}",
         "#FFFFFF"),
        ("6 · Fire-secondary",
         f"score {fi['ignition_risk_score']}",
         f"{fi['firms_pixels_within_60mi']} FIRMS pixels · lag {fi['time_lag_days']}d",
         "#C43A8B"),
    ]
    for i, (title, big, small, color) in enumerate(proj_cards):
        with grid[i % 2]:
            st.markdown(
                f"<div class='ss-card'>"
                f"<div style='color:{color};font-size:11px;font-weight:700;letter-spacing:0.8px;'>{title}</div>"
                f"<div style='color:#FFFFFF;font-weight:700;font-size:22px;margin-top:2px;'>{big}</div>"
                f"<div style='color:#9A9A9A;font-size:11px;margin-top:2px;'>{small}</div>"
                f"</div>",
                unsafe_allow_html=True,
            )


# ─────────────────────────────────────────────────────────────────────────────
# Polycrisis multiplier card (only if active)
# ─────────────────────────────────────────────────────────────────────────────

if poly["multiplier"] > 1.0:
    st.markdown(
        f"<div class='ss-card-poly'>"
        f"<div style='color:#C43A8B;font-size:11px;font-weight:700;letter-spacing:1px;'>POLYCRISIS MULTIPLIER ACTIVE</div>"
        f"<div style='color:#FFFFFF;font-weight:700;font-size:24px;'>×{poly['multiplier']:.2f} compounding effect</div>"
        f"<div style='color:#FFD0E8;font-size:13px;margin-top:6px;'>{poly['rationale']}</div>"
        f"</div>",
        unsafe_allow_html=True,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Sankey + stacked bar + timeline
# ─────────────────────────────────────────────────────────────────────────────

st.markdown("### Cascade chain · Sankey")
st.plotly_chart(charts.cascade_sankey(rollup), use_container_width=True, key="sankey")

c_left, c_right = st.columns([0.4, 0.6])
with c_left:
    st.markdown("### Impact by category")
    st.plotly_chart(charts.impact_stacked_bar(rollup), use_container_width=True, key="stacked")
with c_right:
    st.markdown("### Cascade over 72h")
    st.plotly_chart(charts.cascade_timeline(rollup), use_container_width=True, key="timeline")

st.markdown("### Inventory hours-to-RED")
st.plotly_chart(charts.inventory_hours_bar(rollup), use_container_width=True, key="inv_bar")


# ─────────────────────────────────────────────────────────────────────────────
# Polycrisis Readiness Brief
# ─────────────────────────────────────────────────────────────────────────────

st.markdown("---")
st.markdown("### Polycrisis Readiness Brief")
brief = st.session_state.brief
src_label = {"cached": "cache (instant)",
             "hero-live": "hero · Kamiwaza-deployed",
             "default-chain": "default chain · Kamiwaza-deployed",
             "deterministic-fallback": "deterministic baseline"}.get(brief["source"], brief["source"])
st.caption(f"Source: {src_label} · STORM-SHIFT polycrisis cell")
st.markdown(
    "<div class='ss-card' style='padding:22px 30px;'>",
    unsafe_allow_html=True,
)
st.markdown(brief["brief"])
st.markdown("</div>", unsafe_allow_html=True)


# ─────────────────────────────────────────────────────────────────────────────
# Inventory detail table
# ─────────────────────────────────────────────────────────────────────────────

with st.expander("Inventory cascade — full table"):
    df = pd.DataFrame(inv["rows"])
    st.dataframe(df, use_container_width=True, hide_index=True)

with st.expander("Raw projection JSON (all 6)"):
    st.json({
        "flood": rollup["flood"],
        "supply": rollup["supply"],
        "inventory": {k: v for k, v in rollup["inventory"].items() if k != "rows"},
        "consumption": rollup["consumption"],
        "base_impact": rollup["base_impact"],
        "fire": rollup["fire"],
        "polycrisis": rollup["polycrisis"],
    })


# ─────────────────────────────────────────────────────────────────────────────
# Footer
# ─────────────────────────────────────────────────────────────────────────────

st.markdown(
    f"<div class='ss-footer'>"
    f"Powered by Kamiwaza · Storm models stay in your enclave · No cloud egress"
    f"</div>",
    unsafe_allow_html=True,
)
