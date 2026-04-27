"""REORDER — Streamlit app (port 3019).

Parts Demand Forecasting for Contested Logistics. Forecasts Class IX
consumption for a deployed MAGTF; produces structured per-NSN
pre-positioning recommendations and a Class IX Sustainment Risk Brief.

Run:
    cd apps/19-reorder
    streamlit run src/app.py --server.port 3019 --server.headless true
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
from src import agent, forecast  # noqa: E402
from data.generate import synth_maintenance_history  # noqa: E402

DATA_DIR = APP_ROOT / "data"

# ---------------- Page + theme ---------------------------------------------

st.set_page_config(
    page_title="REORDER — Class IX Demand Forecasting",
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
  .reorder-tagline {{
    color: {BRAND['neon']};
    font-family: Helvetica, Arial, sans-serif;
    font-weight: 600;
    letter-spacing: 1.2px;
    text-transform: uppercase;
    font-size: 12px;
  }}
  .reorder-headline {{
    color: #FFFFFF;
    font-family: Helvetica, Arial, sans-serif;
    font-weight: 700;
    font-size: 30px;
    line-height: 1.15;
    margin-top: 4px;
  }}
  .reorder-card {{
    background: {BRAND['surface']};
    border: 1px solid {BRAND['border']};
    border-radius: 10px;
    padding: 14px 18px;
    margin-bottom: 10px;
  }}
  .pill {{
    display: inline-block;
    padding: 2px 10px;
    border-radius: 999px;
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 0.6px;
  }}
  .pill-green {{ background:#0E2F22; color:#00FFA7; border:1px solid #00BB7A; }}
  .pill-amber {{ background:#3A2C0E; color:#E0B341; border:1px solid #E0B341; }}
  .pill-red   {{ background:#3A0E0E; color:#FF6F66; border:1px solid #D8362F; }}
  .reorder-footer {{
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
  .stDataFrame, .stDataFrame * {{ color: #E8E8E8 !important; }}
</style>
"""
st.markdown(CSS, unsafe_allow_html=True)


# ---------------- Data load (cached) ---------------------------------------

@st.cache_data(show_spinner=False)
def load_catalog() -> dict:
    catalog = json.loads((DATA_DIR / "nsn_catalog.json").read_text())
    return {c["nsn"]: c for c in catalog}


@st.cache_data(show_spinner=False)
def load_forward_nodes() -> list[dict]:
    return json.loads((DATA_DIR / "forward_nodes.json").read_text())


@st.cache_data(show_spinner=False)
def load_scenarios() -> list[dict]:
    return json.loads((DATA_DIR / "scenarios.json").read_text())


@st.cache_data(show_spinner=False)
def load_default_history() -> pd.DataFrame:
    return pd.read_csv(DATA_DIR / "maintenance_history.csv")


@st.cache_data(show_spinner=False)
def synth_history_for(magtf: str, optempo: str, env: str) -> pd.DataFrame:
    catalog_list = list(load_catalog().values())
    import random as _r
    rng = _r.Random(1776 + hash((magtf, optempo, env)) % 9999)
    records = synth_maintenance_history(
        catalog_list, days=90,
        magtf_size=magtf, optempo=optempo, environment=env, rng=rng,
    )
    return pd.DataFrame(records)


def pill_for(risk: str) -> str:
    cls = {"GREEN": "pill-green", "AMBER": "pill-amber", "RED": "pill-red"}.get(risk, "pill-green")
    return f'<span class="pill {cls}">{risk}</span>'


# ---------------- Sidebar (operator scenario controls) ---------------------

scenarios = load_scenarios()
forward_nodes = load_forward_nodes()
catalog_by_nsn = load_catalog()

with st.sidebar:
    st.markdown(
        f"<div class='reorder-tagline'>{BRAND['footer']}</div>"
        f"<div class='reorder-headline'>REORDER</div>"
        f"<div style='color:{BRAND['text_dim']};font-size:12px;margin-top:6px;'>"
        "Class IX Parts Demand Forecasting for Contested Logistics"
        "</div>",
        unsafe_allow_html=True,
    )
    st.markdown("---")
    st.markdown("**MISSION FRAME**")
    st.markdown(
        "<span style='color:#9A9A9A;font-size:12px;'>"
        "LOGCOM use case — predict Class IX (repair parts) consumption for a "
        "deployed MAGTF based on OPTEMPO, environmental conditions, and "
        "historical maintenance. Output: pre-positioning recommendations for "
        "narrow / denied resupply windows."
        "</span>",
        unsafe_allow_html=True,
    )
    st.markdown("---")
    st.markdown("**OPERATOR PROFILE**")
    scenario_labels = [s["label"] for s in scenarios]
    scenario_idx = st.selectbox(
        "Scenario", range(len(scenarios)),
        format_func=lambda i: scenario_labels[i],
        key="scenario_idx",
    )
    scenario = scenarios[scenario_idx]
    magtf = st.selectbox("MAGTF size", ["MEU", "MEB", "MEF"],
                         index=["MEU", "MEB", "MEF"].index(scenario["magtf_size"]),
                         key="magtf")
    optempo = st.selectbox("OPTEMPO", ["low", "medium", "high"],
                           index=["low", "medium", "high"].index(scenario["optempo"]),
                           key="optempo")
    env = st.selectbox("Environment", ["desert", "jungle", "maritime", "cold"],
                       index=["desert", "jungle", "maritime", "cold"].index(scenario["environment"]),
                       key="env")
    fnode_idx = st.selectbox(
        "Forward node",
        range(len(forward_nodes)),
        format_func=lambda i: f"{forward_nodes[i]['name']} ({forward_nodes[i]['kind']})",
        index=3,  # default to OKI-FWD
        key="fnode_idx",
    )
    forward_node = forward_nodes[fnode_idx]
    top_n = st.slider("Top-N NSNs to forecast", 5, 20, 12, 1, key="top_n")
    st.markdown("---")
    st.markdown(
        "<span style='color:#9A9A9A;font-size:12px;'>"
        "<b>Datasets:</b> NASA Predictive Maintenance + Microsoft Azure "
        "Predictive Maintenance + GCSS-MC Supply &amp; Maintenance "
        "(synthetic stand-in). Real-data swap: set <code>REAL_DATA_PATH</code>."
        "</span>",
        unsafe_allow_html=True,
    )
    st.markdown(
        "<span style='color:#9A9A9A;font-size:12px;'>"
        "<b>Engine:</b> Holt-Winters time-series forecaster + Kamiwaza-deployed "
        "model for per-NSN judgment and the sustainment brief."
        "</span>",
        unsafe_allow_html=True,
    )


# ---------------- Header ---------------------------------------------------

col_a, col_b = st.columns([0.65, 0.35])
with col_a:
    st.markdown(
        f"<div class='reorder-tagline'>Class IX Demand Forecasting · MAGTF G-4 sustainment</div>"
        f"<div class='reorder-headline'>The first contested-logistics fight is for the parts pipeline. "
        f"REORDER puts the parts where the fight is.</div>",
        unsafe_allow_html=True,
    )
with col_b:
    st.markdown(
        f"<div class='reorder-card' style='text-align:right;'>"
        f"<div style='color:{BRAND['muted']};font-size:11px;letter-spacing:1px;'>CLASSIFICATION</div>"
        f"<div style='color:{BRAND['neon']};font-weight:700;letter-spacing:1.2px;'>UNCLASSIFIED // FOUO</div>"
        f"<div style='color:{BRAND['muted']};font-size:11px;letter-spacing:1px;margin-top:8px;'>POSTURE</div>"
        f"<div style='color:#FFFFFF;font-weight:700;'>On-prem · Kamiwaza Stack</div>"
        f"</div>",
        unsafe_allow_html=True,
    )


# ---------------- Live ingest + KPI row ------------------------------------

# Use synthesized history matching the operator selections so the demo reacts
# to dropdown changes without a re-generate step.
history_df = synth_history_for(magtf, optempo, env)

c1, c2, c3, c4 = st.columns([0.30, 0.23, 0.23, 0.24])
with c1:
    if st.button("GENERATE 90-DAY FORECAST", use_container_width=True, type="primary",
                 key="btn_generate"):
        with st.spinner("Step 1/2 — Holt-Winters forecaster + per-NSN judgment (chat_json)…"):
            forecasts = forecast.build_forecasts(history_df, top_n=top_n, horizon=90)
            judged = agent.judge_top_nsns(forecasts, catalog_by_nsn, forward_node,
                                          scenario={"magtf_size": magtf, "optempo": optempo,
                                                    "environment": env})
        with st.spinner("Step 2/2 — Class IX Sustainment Risk Brief (Kamiwaza-deployed)…"):
            brief = agent.write_brief(judged,
                                      {**scenario, "magtf_size": magtf, "optempo": optempo,
                                       "environment": env},
                                      forward_node, hero=True)
        st.session_state.result = {
            "forecasts": forecasts,
            "judged": judged,
            "brief": brief,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }
with c2:
    st.metric("Work orders ingested", f"{len(history_df):,}")
with c3:
    st.metric("NSNs in catalog", f"{len(catalog_by_nsn):,}")
with c4:
    st.metric("Forward nodes", f"{len(forward_nodes)}")

st.markdown("---")


# ---------------- Default render (pre-generate) ----------------------------

if "result" not in st.session_state:
    st.session_state.result = None

if not st.session_state.result:
    st.markdown("#### Trailing 30-day Class IX consumption — top 12 NSNs (baseline)")
    daily = history_df.copy()
    daily["date"] = pd.to_datetime(daily["date"])
    end = daily["date"].max()
    last30 = daily[daily["date"] >= end - pd.Timedelta(days=29)]
    top12 = (
        last30.groupby(["nsn"])["qty_consumed"].sum()
              .sort_values(ascending=False).head(12).reset_index()
    )
    top12 = top12.merge(
        pd.DataFrame([{"nsn": k, "part_name": v["part_name"],
                       "platform": v["primary_platform"], "subsystem": v["subsystem"]}
                      for k, v in catalog_by_nsn.items()]),
        on="nsn", how="left",
    )
    st.dataframe(
        top12.rename(columns={"qty_consumed": "30d qty"}),
        use_container_width=True, hide_index=True, height=360,
    )
    st.info("Click **GENERATE 90-DAY FORECAST** to project Class IX demand 30/60/90 "
            "days forward and produce the Sustainment Risk Brief.")

else:
    r = st.session_state.result
    judged = r["judged"]
    forecasts = r["forecasts"]

    # ----- Risk table ------------------------------------------------------
    st.markdown("#### Top-N NSN forecast — pre-positioning recommendations")
    risk_rank = {"RED": 0, "AMBER": 1, "GREEN": 2}
    judged_sorted = sorted(judged, key=lambda j: (risk_rank.get(j["shortfall_risk"], 3),
                                                  -j["projected_30d_demand"]))
    table_rows = []
    for j in judged_sorted:
        table_rows.append({
            "Risk": j["shortfall_risk"],
            "NSN": j["nsn"],
            "Part": j["part_name"],
            "Platform": j["platform_consuming"],
            "30d projected": j["projected_30d_demand"],
            "Stock @ fwd node": j["current_stock_at_forward_node"],
            "Pre-position action": j["preposition_recommendation"],
        })
    df_table = pd.DataFrame(table_rows)

    def _color_risk(val):
        if val == "RED":
            return "background-color:#3A0E0E;color:#FF6F66;font-weight:700"
        if val == "AMBER":
            return "background-color:#3A2C0E;color:#E0B341;font-weight:700"
        if val == "GREEN":
            return "background-color:#0E2F22;color:#00FFA7;font-weight:700"
        return ""

    st.dataframe(
        df_table.style.map(_color_risk, subset=["Risk"]),
        use_container_width=True, hide_index=True, height=420,
    )

    # ----- Forecast chart for the highest-risk NSN -------------------------
    top_nsn = judged_sorted[0]["nsn"]
    top_meta = catalog_by_nsn.get(top_nsn, {"part_name": top_nsn})
    fc = forecasts[top_nsn]

    actual = fc["actual"]
    forecast_y = fc["forecast"]
    lo = fc["lo"]
    hi = fc["hi"]
    n_actual = len(actual)
    n_forecast = len(forecast_y)
    x_actual = list(range(-n_actual + 1, 1))
    x_forecast = list(range(1, n_forecast + 1))

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=x_actual, y=actual, name="Actual (90d)",
        line=dict(color=BRAND["neon"], width=2),
    ))
    fig.add_trace(go.Scatter(
        x=x_forecast + x_forecast[::-1],
        y=hi + lo[::-1],
        fill="toself",
        fillcolor="rgba(0,187,122,0.18)",
        line=dict(color="rgba(0,0,0,0)"),
        hoverinfo="skip",
        name="80% confidence",
        showlegend=True,
    ))
    fig.add_trace(go.Scatter(
        x=x_forecast, y=forecast_y, name="Projected (90d)",
        line=dict(color=BRAND["primary"], width=2.5, dash="dot"),
    ))
    fig.update_layout(
        title=f"Forecast — {top_nsn} ({top_meta['part_name']}) · {fc['method']}",
        plot_bgcolor=BRAND["surface"],
        paper_bgcolor=BRAND["bg"],
        font=dict(color="#E8E8E8"),
        height=360,
        xaxis=dict(title="days from today (negative = history)",
                   gridcolor=BRAND["border"], zerolinecolor=BRAND["border"]),
        yaxis=dict(title="qty consumed / day",
                   gridcolor=BRAND["border"], zerolinecolor=BRAND["border"]),
        margin=dict(l=40, r=20, t=40, b=40),
        legend=dict(bgcolor=BRAND["surface"], bordercolor=BRAND["border"]),
    )
    st.plotly_chart(fig, use_container_width=True, key="forecast_chart")

    # ----- Forward-nodes map ----------------------------------------------
    st.markdown("#### Forward nodes + recommended pre-positioning flows")
    map_df = pd.DataFrame([
        {"name": n["name"], "lat": n["lat"], "lon": n["lon"], "tier": n["tier"],
         "size": 28 if n["tier"] == "primary" else 18}
        for n in forward_nodes
    ])
    fig_map = go.Figure()
    fig_map.add_trace(go.Scattergeo(
        lon=map_df["lon"], lat=map_df["lat"],
        text=map_df["name"], mode="markers+text",
        marker=dict(
            size=map_df["size"],
            color=[BRAND["neon"] if t == "forward" else BRAND["primary"]
                   for t in map_df["tier"]],
            line=dict(color="#FFFFFF", width=1.2),
        ),
        textposition="top center",
        textfont=dict(color="#FFFFFF", size=11),
        name="Nodes",
    ))
    # Recommended flows: from each primary CONUS depot to the active forward node.
    for src in [n for n in forward_nodes if n["tier"] == "primary"]:
        fig_map.add_trace(go.Scattergeo(
            lon=[src["lon"], forward_node["lon"]],
            lat=[src["lat"], forward_node["lat"]],
            mode="lines",
            line=dict(color=BRAND["primary"], width=1.4, dash="dot"),
            hoverinfo="skip",
            showlegend=False,
        ))
    fig_map.update_geos(
        showcountries=True, countrycolor="#222222",
        showland=True, landcolor="#0E0E0E",
        showocean=True, oceancolor="#0A0A0A",
        showcoastlines=True, coastlinecolor="#222222",
        projection_type="natural earth",
        bgcolor=BRAND["bg"],
    )
    fig_map.update_layout(
        height=380, margin=dict(l=0, r=0, t=10, b=10),
        paper_bgcolor=BRAND["bg"], plot_bgcolor=BRAND["bg"],
        font=dict(color="#E8E8E8"),
        showlegend=False,
    )
    st.plotly_chart(fig_map, use_container_width=True, key="map_chart")

    # ----- Brief ----------------------------------------------------------
    st.markdown("---")
    st.markdown("### Class IX Sustainment Risk Brief")
    st.caption(f"Generated {r['generated_at']} · Originator: REORDER / G-4 Class IX cell")
    st.markdown("<div class='reorder-card' style='padding:22px 30px;'>",
                unsafe_allow_html=True)
    st.markdown(r["brief"])
    st.markdown("</div>", unsafe_allow_html=True)

    with st.expander("Show raw per-NSN JSON judgments"):
        st.json(judged)


# ---------------- Footer ---------------------------------------------------

st.markdown(
    f"<div class='reorder-footer'>"
    f"Powered by Kamiwaza · Orchestration Without Migration. Execution Without Compromise."
    f"</div>",
    unsafe_allow_html=True,
)
