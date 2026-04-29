"""CAT-ROUTER — Kamiwaza Model Catalog router demo (Streamlit, port 3052).

Hero AI move: a Marine analyst submits a 5-task workflow; CAT-ROUTER picks the
optimal Kamiwaza-deployed model for each task, displays the catalog card per
pick, and shows the rationale. Toggle Fast/Cheap mode to re-route everything to
the smallest edge model and watch the quality / cost / latency trade-off live.

Run:
    streamlit run src/app.py --server.port 3052 --server.headless true \\
        --server.runOnSave false --server.fileWatcherType none \\
        --browser.gatherUsageStats false
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

ROOT = Path(__file__).resolve().parent.parent.parent.parent
APP_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(APP_ROOT))

from shared.kamiwaza_client import BRAND  # noqa: E402
from src.router import (  # noqa: E402
    audit_chain,
    kamiwaza_endpoint,
    load_cached_briefs,
    load_catalog,
    load_workflows,
    route_workflow,
)

st.set_page_config(
    page_title="CAT-ROUTER — Kamiwaza Model Catalog",
    page_icon="-",
    layout="wide",
    initial_sidebar_state="collapsed",
)

CSS = f"""
<style>
  .stApp {{
    background: {BRAND['bg']};
    color: #E8E8E8;
  }}
  [data-testid="stHeader"] {{ background: transparent; }}
  [data-testid="stToolbar"] {{ display: none; }}
  section[data-testid="stSidebar"] {{
    background: {BRAND['surface']};
    border-right: 1px solid {BRAND['border']};
  }}
  .cr-hero {{
    background: linear-gradient(135deg, {BRAND['surface']} 0%, {BRAND['bg']} 100%);
    border: 1px solid {BRAND['border']};
    border-left: 4px solid {BRAND['primary']};
    border-radius: 8px;
    padding: 18px 24px;
    margin-bottom: 12px;
  }}
  .cr-hero h1 {{
    color: {BRAND['neon']};
    font-family: 'Helvetica Neue', sans-serif;
    font-size: 28px;
    margin: 0;
    letter-spacing: -0.5px;
  }}
  .cr-hero p {{
    color: {BRAND['text_dim']};
    margin: 4px 0 0 0;
    font-size: 13px;
  }}
  .cr-pill {{
    display: inline-block;
    background: {BRAND['surface_high']};
    color: {BRAND['primary']};
    border: 1px solid {BRAND['primary']};
    border-radius: 999px;
    padding: 2px 10px;
    font-size: 11px;
    margin-right: 6px;
    letter-spacing: 0.5px;
  }}
  .cr-card {{
    background: {BRAND['surface']};
    border: 1px solid {BRAND['border']};
    border-radius: 6px;
    padding: 14px 18px;
    margin-bottom: 8px;
  }}
  .cr-card-active {{
    border: 1px solid {BRAND['primary']};
    box-shadow: 0 0 0 1px {BRAND['primary']} inset;
  }}
  .cr-card h4 {{
    margin: 0 0 4px 0;
    color: {BRAND['neon']};
    font-size: 15px;
  }}
  .cr-card .cr-sub {{
    color: {BRAND['text_dim']};
    font-size: 11px;
    text-transform: uppercase;
    letter-spacing: 1.0px;
  }}
  .cr-card .cr-meta {{
    color: #DDD;
    font-size: 12px;
    margin-top: 6px;
    line-height: 1.45;
  }}
  .cr-card .cr-meta span {{
    color: {BRAND['primary']};
  }}
  .cr-route-card {{
    background: {BRAND['surface_high']};
    border: 1px solid {BRAND['border']};
    border-left: 4px solid {BRAND['neon']};
    border-radius: 6px;
    padding: 12px 16px;
    margin-bottom: 8px;
  }}
  .cr-metric {{
    color: {BRAND['neon']};
    font-size: 22px;
    font-weight: 700;
  }}
  .cr-metric-label {{
    color: {BRAND['text_dim']};
    font-size: 11px;
    text-transform: uppercase;
    letter-spacing: 1.2px;
  }}
  .cr-rationale {{
    background: {BRAND['surface']};
    border: 1px dashed {BRAND['primary']};
    color: #DDD;
    border-radius: 4px;
    padding: 8px 12px;
    font-size: 12px;
    line-height: 1.5;
    margin-top: 6px;
  }}
  .cr-footer {{
    color: {BRAND['text_dim']};
    font-size: 12px;
    text-align: center;
    padding: 16px 0 4px 0;
    border-top: 1px solid {BRAND['border']};
    margin-top: 28px;
  }}
  .cr-footer span {{ color: {BRAND['primary']}; font-weight: 600; }}
  div.stButton > button:first-child {{
    background: {BRAND['primary']};
    color: #000;
    border: 0;
    font-weight: 600;
    border-radius: 4px;
    padding: 6px 18px;
  }}
  div.stButton > button:hover {{
    background: {BRAND['primary_hover']};
    color: #000;
  }}
  textarea, input {{
    background: {BRAND['surface_high']} !important;
    color: #E8E8E8 !important;
    border-color: {BRAND['border']} !important;
  }}
  .stDataFrame {{ border: 1px solid {BRAND['border']}; }}
  hr {{ border-color: {BRAND['border']}; }}
  code {{ color: {BRAND['neon']}; background: {BRAND['surface_high']}; }}
</style>
"""
st.markdown(CSS, unsafe_allow_html=True)

HERO_HTML = f"""
<div class="cr-hero">
  <h1>CAT-ROUTER</h1>
  <p><strong>Kamiwaza Model Catalog routing for Marine analysts</strong>
     &nbsp;-&nbsp; one workflow, five LLM tasks, five different best models &mdash; auto-picked.</p>
  <p style="margin-top:8px;">
    <span class="cr-pill">Model Catalog</span>
    <span class="cr-pill">Inference Mesh</span>
    <span class="cr-pill">8-Model Pool</span>
    <span class="cr-pill">Fast/Cheap Toggle</span>
    <span class="cr-pill">USMC LOGCOM 2026</span>
  </p>
</div>
"""
st.markdown(HERO_HTML, unsafe_allow_html=True)


@st.cache_data(show_spinner=False)
def _catalog() -> list[dict]:
    return load_catalog()


@st.cache_data(show_spinner=False)
def _workflows() -> dict:
    return load_workflows()


@st.cache_data(show_spinner=False)
def _cached() -> dict:
    return load_cached_briefs()


CATALOG = _catalog()
WORKFLOWS = _workflows()["workflows"]
CACHED = _cached()


# ─────────────────────────────────────────────────────────────────────────────
# Top KPI strip
# ─────────────────────────────────────────────────────────────────────────────
m1, m2, m3, m4, m5 = st.columns(5)
n_models = len(CATALOG)
n_vision = sum(1 for m in CATALOG if m["vision"])
n_il5 = sum(1 for m in CATALOG if m["scar_grade"] in {"IL5", "IL6"})
n_tool = sum(1 for m in CATALOG if m["tool_calls"])
n_workflows = len(WORKFLOWS)

m1.markdown(f'<div class="cr-card"><div class="cr-metric">{n_models}</div><div class="cr-metric-label">Models in Catalog</div></div>', unsafe_allow_html=True)
m2.markdown(f'<div class="cr-card"><div class="cr-metric">{n_vision}</div><div class="cr-metric-label">Vision-Capable</div></div>', unsafe_allow_html=True)
m3.markdown(f'<div class="cr-card"><div class="cr-metric">{n_il5}</div><div class="cr-metric-label">IL5+ Hardened</div></div>', unsafe_allow_html=True)
m4.markdown(f'<div class="cr-card"><div class="cr-metric">{n_tool}</div><div class="cr-metric-label">Tool-Calling</div></div>', unsafe_allow_html=True)
m5.markdown(f'<div class="cr-card"><div class="cr-metric">{n_workflows}</div><div class="cr-metric-label">Demo Workflows</div></div>', unsafe_allow_html=True)

st.markdown("&nbsp;")


# ─────────────────────────────────────────────────────────────────────────────
# Workflow + mode picker
# ─────────────────────────────────────────────────────────────────────────────
c_wf, c_mode = st.columns([3, 1])
with c_wf:
    options = {w["label"]: w["workflow_id"] for w in WORKFLOWS}
    chosen_label = st.selectbox(
        "Operator workflow",
        list(options.keys()),
        index=0,
        help="Each workflow is a chain of LLM tasks. CAT-ROUTER picks the best Kamiwaza-deployed model per task.",
    )
    workflow_id = options[chosen_label]
with c_mode:
    st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)
    fast_cheap = st.toggle(
        "Fast / Cheap mode",
        value=False,
        help="Re-route every task to the cheapest fast model. Watch quality and cost trade off live.",
    )
    mode = "fast_cheap" if fast_cheap else "best_quality"

# Routing decision (cache-first)
def _get_routing(wid: str, m: str) -> dict:
    cached = CACHED.get(wid, {}).get(m)
    if cached:
        return cached
    return route_workflow(wid, mode=m)


bq = _get_routing(workflow_id, "best_quality")
fc = _get_routing(workflow_id, "fast_cheap")
active = fc if mode == "fast_cheap" else bq

st.markdown(f"**Narrator cue:** _{active['narrator']}_")


# ─────────────────────────────────────────────────────────────────────────────
# Catalog grid — one card per model in the catalog, highlight routed picks
# ─────────────────────────────────────────────────────────────────────────────
st.markdown("##### Kamiwaza Model Catalog (8 deployed models)")
st.caption("Cards bordered green are currently selected by the router for one or more tasks in this workflow.")

routed_ids = {d["winner_id"] for d in active["decisions"]}
routed_taskcount = {}
for d in active["decisions"]:
    routed_taskcount.setdefault(d["winner_id"], []).append(d["task_id"])


def _model_card(model: dict, *, active_for: list[str] | None = None) -> str:
    cls = "cr-card cr-card-active" if active_for else "cr-card"
    badge = ""
    if active_for:
        badge = f'<span class="cr-pill" style="background:{BRAND["primary"]};color:#000;border-color:{BRAND["primary"]};">routed: {", ".join(active_for)}</span>'
    params = f"{model['parameters_b']}B"
    if model.get("active_parameters_b"):
        params = f"{model['parameters_b']}B / {model['active_parameters_b']}B active (MoE)"
    vis = "YES" if model["vision"] else "no"
    tool = "YES" if model["tool_calls"] else "no"
    return f"""
    <div class="{cls}">
      <h4>{model['display_name']} {badge}</h4>
      <div class="cr-sub">{model['publisher']} &middot; {model['family']}</div>
      <div class="cr-meta">
        <span>params:</span> {params} &middot;
        <span>ctx:</span> {model['context_window']:,} &middot;
        <span>vision:</span> {vis} &middot;
        <span>tools:</span> {tool}<br>
        <span>license:</span> {model['license']}<br>
        <span>SCAR:</span> {model['scar_grade']} &middot;
        <span>home:</span> {model['hardware_home']}<br>
        <span>throughput:</span> {model['tokens_per_second']} tok/s &middot;
        <span>first-token:</span> {model['first_token_ms']} ms<br>
        <span>cost:</span> ${model['cost_per_1k_input_tokens']:.4f}/1k in &middot;
                          ${model['cost_per_1k_output_tokens']:.4f}/1k out<br>
        <span>cutoff:</span> {model['training_cutoff']} &middot;
        <span>quality:</span> {model['quality_score']:.2f}
      </div>
    </div>
    """


cols = st.columns(4)
for i, m in enumerate(CATALOG):
    with cols[i % 4]:
        st.markdown(
            _model_card(m, active_for=routed_taskcount.get(m["model_id"])),
            unsafe_allow_html=True,
        )

st.markdown("---")


# ─────────────────────────────────────────────────────────────────────────────
# Per-task routing decisions (the hero panel)
# ─────────────────────────────────────────────────────────────────────────────
st.markdown(f"##### Per-task routing decisions &nbsp;-&nbsp; mode: `{mode}`")

for d in active["decisions"]:
    w = d["winner"]
    st.markdown(
        f"""
        <div class="cr-route-card">
          <div style="display:flex; justify-content:space-between; align-items:flex-start;">
            <div>
              <div class="cr-sub">{d['task_id']} &middot; {d['task_type']}</div>
              <div style="color:#FFF; font-weight:600; font-size:14px;">{d['task_label']}</div>
            </div>
            <div style="text-align:right;">
              <div class="cr-sub">routed to</div>
              <div style="color:{BRAND['neon']}; font-weight:700;">{w['display_name']}</div>
              <div class="cr-sub">{w['hardware_home']}</div>
            </div>
          </div>
          <div class="cr-rationale">{d['rationale']}</div>
          <div style="margin-top:6px; font-size:11px; color:{BRAND['text_dim']};">
            est. cost: <code>${d['cost_estimate_usd']:.5f}</code> &middot;
            est. latency: <code>{d['latency_estimate_s']:.2f}s</code> &middot;
            quality score: <code>{d['quality_score']:.2f}</code>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Quality / Cost / Latency comparison (Plotly)
# ─────────────────────────────────────────────────────────────────────────────
st.markdown("---")
st.markdown("##### Mode comparison: best-quality vs fast/cheap")

rows = []
for d_bq, d_fc in zip(bq["decisions"], fc["decisions"]):
    rows.append({
        "Task": d_bq["task_id"],
        "Type": d_bq["task_type"],
        "Best-Q model": d_bq["winner"]["display_name"],
        "Best-Q cost": d_bq["cost_estimate_usd"],
        "Best-Q latency": d_bq["latency_estimate_s"],
        "Best-Q quality": d_bq["quality_score"],
        "Fast-C model": d_fc["winner"]["display_name"],
        "Fast-C cost": d_fc["cost_estimate_usd"],
        "Fast-C latency": d_fc["latency_estimate_s"],
        "Fast-C quality": d_fc["quality_score"],
    })
cdf = pd.DataFrame(rows)

c_left, c_right = st.columns([1.2, 1])
with c_left:
    st.dataframe(cdf, hide_index=True, use_container_width=True, height=240)

with c_right:
    fig = go.Figure()
    fig.add_trace(go.Bar(
        name="Best-Quality",
        x=cdf["Task"],
        y=cdf["Best-Q cost"],
        marker_color=BRAND["primary"],
        hovertemplate="%{x}: $%{y:.5f}<extra>Best-Quality</extra>",
    ))
    fig.add_trace(go.Bar(
        name="Fast/Cheap",
        x=cdf["Task"],
        y=cdf["Fast-C cost"],
        marker_color=BRAND["neon"],
        hovertemplate="%{x}: $%{y:.5f}<extra>Fast/Cheap</extra>",
    ))
    fig.update_layout(
        barmode="group",
        plot_bgcolor=BRAND["bg"],
        paper_bgcolor=BRAND["bg"],
        font=dict(color="#DDD", size=11),
        height=240,
        margin=dict(l=10, r=10, t=30, b=10),
        title=dict(text="Per-task cost (USD)", font=dict(color=BRAND["primary"], size=13)),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0.0),
        xaxis=dict(gridcolor=BRAND["border"]),
        yaxis=dict(gridcolor=BRAND["border"]),
    )
    st.plotly_chart(fig, use_container_width=True)

# Totals comparison
t_bq = bq["totals"]
t_fc = fc["totals"]
cost_drop = (t_bq["cost_usd"] - t_fc["cost_usd"]) / max(t_bq["cost_usd"], 1e-9) * 100
quality_drop = (t_bq["avg_quality"] - t_fc["avg_quality"]) / max(t_bq["avg_quality"], 1e-9) * 100

t1, t2, t3, t4 = st.columns(4)
t1.markdown(f'<div class="cr-card"><div class="cr-metric">${t_bq["cost_usd"]:.4f}</div><div class="cr-metric-label">Best-Q workflow cost</div></div>', unsafe_allow_html=True)
t2.markdown(f'<div class="cr-card"><div class="cr-metric">${t_fc["cost_usd"]:.4f}</div><div class="cr-metric-label">Fast/Cheap workflow cost</div></div>', unsafe_allow_html=True)
t3.markdown(f'<div class="cr-card"><div class="cr-metric">{cost_drop:.0f}%</div><div class="cr-metric-label">Cost reduction (Fast/Cheap)</div></div>', unsafe_allow_html=True)
t4.markdown(f'<div class="cr-card"><div class="cr-metric">{quality_drop:.0f}%</div><div class="cr-metric-label">Quality drop (measured)</div></div>', unsafe_allow_html=True)


# ─────────────────────────────────────────────────────────────────────────────
# Hash-chained audit
# ─────────────────────────────────────────────────────────────────────────────
st.markdown("---")
st.markdown("##### Hash-chained routing audit")
st.caption("Every model selection is appended to a hash chain. Tampering with any link breaks every downstream hash.")

audit_df = pd.DataFrame([
    {
        "Task": row["task_id"],
        "Mode": row["mode"],
        "Model": row["winner_id"],
        "Cost": f"${row['cost_usd']:.5f}",
        "Prev hash": row["prev_hash"],
        "This hash": row["hash"],
    }
    for row in active["audit_chain"]
])
st.dataframe(audit_df, hide_index=True, use_container_width=True, height=220)


# ─────────────────────────────────────────────────────────────────────────────
# Catalog detail explorer
# ─────────────────────────────────────────────────────────────────────────────
with st.expander("Full catalog metadata (click to inspect raw catalog JSON)", expanded=False):
    st.json(CATALOG)


# ─────────────────────────────────────────────────────────────────────────────
# Footer (KAMIWAZA env-var beat)
# ─────────────────────────────────────────────────────────────────────────────
endpoint = kamiwaza_endpoint()
st.markdown(
    f'<div class="cr-footer">'
    f'<span>Powered by Kamiwaza</span> &nbsp;-&nbsp; '
    f'Catalog endpoint: <code>{endpoint}</code> &nbsp;-&nbsp; '
    f'Set <code>KAMIWAZA_BASE_URL</code> + <code>KAMIWAZA_API_KEY</code> to swap the synthetic catalog '
    f'for a live <code>/v1/catalog/models</code> on your on-prem Kamiwaza Model Gateway.'
    f'</div>',
    unsafe_allow_html=True,
)
