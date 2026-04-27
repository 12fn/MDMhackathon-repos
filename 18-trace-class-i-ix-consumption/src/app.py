"""TRACE — LogTRACE Class I-IX consumption estimator (port 3018).

Run with:
    cd apps/18-trace
    streamlit run src/app.py \\
        --server.port 3018 --server.headless true \\
        --server.runOnSave false --server.fileWatcherType none \\
        --browser.gatherUsageStats false
"""
from __future__ import annotations

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
from src import agent  # noqa: E402
from data.generate import DEPOTS, DOCTRINE_RATES, SCENARIOS, baseline_estimate  # noqa: E402


# ---------------------------------------------------------------------------
# Page config + theme
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="TRACE — LogTRACE Class I-IX Estimator",
    page_icon="*",
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
  .trace-tagline {{
    color: {BRAND['neon']};
    font-family: Helvetica, Arial, sans-serif;
    font-weight: 600;
    letter-spacing: 1.2px;
    text-transform: uppercase;
    font-size: 12px;
  }}
  .trace-headline {{
    color: #FFFFFF;
    font-family: Helvetica, Arial, sans-serif;
    font-weight: 700;
    font-size: 28px;
    line-height: 1.18;
    margin-top: 4px;
  }}
  .trace-card {{
    background: {BRAND['surface']};
    border: 1px solid {BRAND['border']};
    border-radius: 10px;
    padding: 14px 18px;
    margin-bottom: 10px;
  }}
  .trace-pill {{
    display: inline-block;
    padding: 2px 9px;
    border-radius: 999px;
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 0.6px;
  }}
  .pill-low    {{ background:#0E2F22; color:#00FFA7; border:1px solid #00BB7A; }}
  .pill-med    {{ background:#3A2C0E; color:#E0B341; border:1px solid #E0B341; }}
  .pill-high   {{ background:#3A1A0E; color:#E36F2C; border:1px solid #E36F2C; }}
  .pill-crit   {{ background:#3A0E0E; color:#FF6F66; border:1px solid #D8362F; }}
  .trace-footer {{
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


CLASS_ORDER = ["I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX"]
CLASS_COLORS = {
    "I":    "#00BB7A",  # subsistence — Kamiwaza green
    "II":   "#0DCC8A",
    "III":  "#FFB347",  # POL — amber
    "IV":   "#A78BFA",
    "V":    "#F87171",  # ammo — red
    "VI":   "#60A5FA",
    "VII":  "#F472B6",
    "VIII": "#34D399",  # medical — light green
    "IX":   "#FACC15",  # repair parts — yellow
}


def variance_pill(v: int) -> str:
    if v < 10:
        return f'<span class="trace-pill pill-low">±{v}%</span>'
    if v < 16:
        return f'<span class="trace-pill pill-med">±{v}%</span>'
    if v < 22:
        return f'<span class="trace-pill pill-high">±{v}%</span>'
    return f'<span class="trace-pill pill-crit">±{v}%</span>'


def build_stacked_bar(estimate: dict) -> go.Figure:
    """Plotly stacked bar of all 9 supply classes across the operation window.

    X-axis: each day in the window (1..days)
    Y-axis: total weight (lbs) — Class III converted to lbs (1 gal JP-8 ~ 6.7 lbs)
            Class VII converted via 200 lbs/end-item rough avg.
    Stacks: Class I-IX, Kamiwaza-themed colors.
    """
    days = int(estimate["days"])
    x = list(range(1, days + 1))
    fig = go.Figure()
    for c in estimate["classes"]:
        cls = c["class"]
        daily = float(c["daily_consumption"])
        # Normalize to lbs-equivalent for stacking visualization.
        if cls == "III":
            daily_lbs = daily * 6.7  # gal -> lbs JP-8
        elif cls == "VII":
            daily_lbs = daily * 200.0  # ea -> lbs (rough major-end-item avg)
        else:
            daily_lbs = daily
        y = [daily_lbs] * days
        fig.add_trace(go.Bar(
            name=f"Class {cls}",
            x=x,
            y=y,
            marker_color=CLASS_COLORS.get(cls, "#888"),
            hovertemplate=(
                f"Class {cls} — {c['name']}<br>"
                "Day %{x}<br>"
                f"Daily: {daily:,.1f} {c['daily_unit']}<br>"
                f"Window total: {c['total_30day_or_window']:,.0f} {c['total_unit']}<br>"
                f"Variance: ±{c['variance_band_pct']}%<extra></extra>"
            ),
        ))
    fig.update_layout(
        barmode="stack",
        plot_bgcolor=BRAND["bg"],
        paper_bgcolor=BRAND["bg"],
        font=dict(color="#E8E8E8", family="Helvetica, Arial, sans-serif"),
        title=dict(
            text=f"Daily Class I-IX consumption (lbs-equivalent) over {days}-day window",
            font=dict(color="#FFFFFF", size=14),
        ),
        xaxis=dict(title="Day of operation", gridcolor=BRAND["border"], zerolinecolor=BRAND["border"]),
        yaxis=dict(title="lbs-equivalent / day (stacked)", gridcolor=BRAND["border"], zerolinecolor=BRAND["border"]),
        legend=dict(orientation="h", y=-0.18, font=dict(color="#E8E8E8")),
        margin=dict(t=50, l=60, r=20, b=80),
        height=420,
    )
    return fig


# ---------------------------------------------------------------------------
# Session state
# ---------------------------------------------------------------------------
if "result" not in st.session_state:
    st.session_state.result = None
if "active_scenario_id" not in st.session_state:
    st.session_state.active_scenario_id = SCENARIOS[0]["id"]


# ---------------------------------------------------------------------------
# Sidebar — unit composition inputs
# ---------------------------------------------------------------------------
with st.sidebar:
    st.markdown(
        f"<div class='trace-tagline'>{BRAND['footer']}</div>"
        f"<div class='trace-headline'>TRACE</div>"
        f"<div style='color:{BRAND['text_dim']};font-size:12px;margin-top:6px;'>"
        "LogTRACE — Class I-IX consumption-rate estimator<br/>"
        "for the USMC Logistics Command (LOGCOM)."
        "</div>",
        unsafe_allow_html=True,
    )
    st.markdown("---")

    st.markdown("**MISSION FRAME**")
    st.markdown(
        "<span style='color:#9A9A9A;font-size:12px;'>"
        "<i>\"A logistics estimate application informed by doctrine and technical "
        "specifications consumption rates. Class I-IX requirements for "
        "consumption/usage rates through current estimate tools and/or doctrine.\"</i>"
        "</span>",
        unsafe_allow_html=True,
    )
    st.markdown("---")
    st.markdown("**UNIT COMPOSITION**")

    scenario_labels = {s["id"]: s["label"] for s in SCENARIOS}
    chosen = st.selectbox(
        "Pre-baked scenario",
        options=list(scenario_labels.keys()),
        format_func=lambda k: scenario_labels[k],
        index=0,
        key="scenario_select",
    )
    st.session_state.active_scenario_id = chosen
    base_sc = next(s for s in SCENARIOS if s["id"] == chosen)

    unit_type = st.text_input("Unit type", value=base_sc["unit_type"], key="unit_type")
    personnel = st.number_input("Personnel", min_value=50, max_value=50000,
                                value=int(base_sc["personnel"]), step=50, key="personnel")
    days = st.number_input("Operation window (days)", min_value=1, max_value=180,
                           value=int(base_sc["days"]), step=1, key="days")
    climate = st.selectbox(
        "Climate",
        options=["temperate", "tropical", "arid", "cold_weather", "expeditionary_austere"],
        index=["temperate", "tropical", "arid", "cold_weather",
               "expeditionary_austere"].index(base_sc["supply_basis"]),
        key="climate",
    )
    opscale = st.selectbox(
        "Operational scale / tempo",
        options=["low", "medium", "high"],
        index=["low", "medium", "high"].index(base_sc["opscale"]),
        key="opscale",
    )

    st.markdown("---")
    hero = st.toggle("Use Kamiwaza-deployed hero model", value=True,
                     help="ON: agentic two-step pipeline (JSON estimate + narrator brief). "
                          "OFF: deterministic doctrine baseline only.")

    st.markdown("---")
    st.markdown("**DATASETS**")
    st.markdown(
        "<span style='color:#9A9A9A;font-size:12px;'>"
        "Synthetic stand-ins for:<br/>"
        "• Logistics-and-supply-chain-dataset (California)<br/>"
        "• GCSS-MC Supply &amp; Maintenance<br/>"
        "Doctrine basis: synthetic stand-in for MCWP 4-11 / MCRP 3-40D consumption "
        "planning rates. Real-data swap via <code>data/load_real.py</code>."
        "</span>",
        unsafe_allow_html=True,
    )


# ---------------------------------------------------------------------------
# Header
# ---------------------------------------------------------------------------
col_a, col_b = st.columns([0.65, 0.35])
with col_a:
    st.markdown(
        f"<div class='trace-tagline'>LogTRACE - Class I-IX consumption estimator</div>"
        f"<div class='trace-headline'>Sustainment estimates in seconds. Doctrine-aware. Source-aware.</div>",
        unsafe_allow_html=True,
    )
with col_b:
    st.markdown(
        f"<div class='trace-card' style='text-align:right;'>"
        f"<div style='color:{BRAND['muted']};font-size:11px;letter-spacing:1px;'>CLASSIFICATION</div>"
        f"<div style='color:{BRAND['neon']};font-weight:700;letter-spacing:1.2px;'>UNCLASSIFIED // FOUO</div>"
        f"<div style='color:{BRAND['muted']};font-size:11px;letter-spacing:1px;margin-top:8px;'>POSTURE</div>"
        f"<div style='color:#FFFFFF;font-weight:700;'>On-prem - Kamiwaza Stack</div>"
        f"</div>",
        unsafe_allow_html=True,
    )


# ---------------------------------------------------------------------------
# Build the live scenario from sidebar inputs
# ---------------------------------------------------------------------------
live_scenario = {
    "id": chosen,
    "label": (f"{unit_type}, {personnel:,} personnel, {days} days, "
              f"{climate}, {opscale} tempo"),
    "unit_type": unit_type,
    "personnel": int(personnel),
    "days": int(days),
    "climate": climate,
    "opscale": opscale,
    "supply_basis": climate,  # 1:1 mapping in synthetic doctrine
}


# Deterministic baseline estimate ALWAYS computed so the chart never blank.
_baseline_estimate = baseline_estimate(live_scenario)


# Action row + metric cards.
c1, c2, c3, c4 = st.columns([0.30, 0.23, 0.23, 0.24])
with c1:
    if st.button("BUILD SUSTAINMENT ESTIMATE", use_container_width=True,
                 type="primary", key="btn_build"):
        with st.spinner("Step 1/2 - structured Class I-IX estimate (chat_json)..."):
            est = agent.estimate_consumption(live_scenario, hero=hero)
        with st.spinner("Step 2/2 - drafting Sustainment Estimate Brief (Kamiwaza-deployed)..."):
            brief, source = agent.write_brief(live_scenario, est, hero=hero)
        st.session_state.result = {
            "scenario": live_scenario,
            "estimate": est,
            "brief": brief,
            "source": source,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }

with c2:
    st.metric("Personnel", f"{int(personnel):,}")
with c3:
    st.metric("Window (days)", f"{int(days)}")
with c4:
    total_lbs = sum(
        (c["total_30day_or_window"] * (6.7 if c["class"] == "III"
                                       else 200.0 if c["class"] == "VII"
                                       else 1.0))
        for c in _baseline_estimate["classes"]
    )
    st.metric("Total lift (lbs-equiv)", f"{total_lbs:,.0f}",
              help="Baseline doctrine estimate; refined when AI engine returns.")

st.markdown("---")


# ---------------------------------------------------------------------------
# Render: result if present, otherwise baseline preview.
# ---------------------------------------------------------------------------
result = st.session_state.result
if result is None:
    # Try cache first for default scenario.
    cached = agent.load_cached_briefs().get(chosen)
    if cached:
        result = {
            "scenario": cached["scenario"],
            "estimate": cached["estimate"],
            "brief": cached["brief"],
            "source": cached.get("source", "cache"),
            "generated_at": "(cached)",
        }
    else:
        # No cache; render the deterministic baseline so the screen is never empty.
        result = {
            "scenario": live_scenario,
            "estimate": _baseline_estimate,
            "brief": None,
            "source": "baseline",
            "generated_at": "(baseline preview)",
        }


# Top-row: Stacked bar (left, 65%) | Class table (right, 35%)
g_left, g_right = st.columns([0.62, 0.38])
with g_left:
    st.markdown("#### Class I-IX consumption stack")
    st.plotly_chart(build_stacked_bar(result["estimate"]),
                    use_container_width=True, key="stacked_bar")
    st.markdown(
        "<div style='font-size:11px;color:#9A9A9A;'>"
        "Daily lbs-equivalent stacked across Class I-IX over the operation window. "
        "Class III (POL) and Class VII (major end items) normalized to lbs for "
        "visualization (gal x 6.7 / ea x 200)."
        "</div>",
        unsafe_allow_html=True,
    )

with g_right:
    st.markdown("#### Class breakdown")
    rows = []
    for c in result["estimate"]["classes"]:
        rows.append({
            "Cls": c["class"],
            "Name": c["name"].split(" (")[0][:24],
            "Daily": f"{c['daily_consumption']:,.1f} {c['daily_unit']}",
            "Window total": f"{c['total_30day_or_window']:,.0f} {c['total_unit']}",
            "Var": f"+/-{c['variance_band_pct']}%",
        })
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True, height=370)


st.markdown("---")


# Sources panel — which depots can supply each class
st.markdown("#### Recommended pre-positioning sources (synthetic GCSS-MC)")
src_cols = st.columns(3)
for i, s in enumerate(result["estimate"]["sourcing"]):
    cls = s["class"]
    cls_meta = next(c for c in result["estimate"]["classes"] if c["class"] == cls)
    with src_cols[i % 3]:
        sources_html = "".join(
            f"<div style='font-size:12px;color:#C8C8C8;margin-top:4px;'>"
            f"<b style='color:#FFFFFF;'>{src['name']}</b> "
            f"<span style='color:{BRAND['muted']};font-size:11px;'>({src['depot_id']})</span><br/>"
            f"<span style='color:{BRAND['neon']};'>{src['on_hand']:,} {src['unit']}</span> "
            f"<span style='color:{BRAND['muted']};font-size:11px;'>"
            f"covers {src['covers_pct']}% of window</span>"
            f"</div>"
            for src in s["sources"]
        )
        st.markdown(
            f"<div class='trace-card'>"
            f"<div style='display:flex;justify-content:space-between;align-items:center;'>"
            f"<div><b style='color:#FFFFFF;'>Class {cls}</b> "
            f"<span style='color:{BRAND['muted']};font-size:11px;'>"
            f"{cls_meta['name'].split(' (')[0]}</span></div>"
            f"<div>{variance_pill(cls_meta['variance_band_pct'])}</div>"
            f"</div>"
            f"{sources_html}"
            f"</div>",
            unsafe_allow_html=True,
        )


st.markdown("---")


# Sustainment Estimate Brief
st.markdown("### Sustainment Estimate Brief")
st.caption(
    f"Generated {result['generated_at']} - Originator: TRACE / LOGCOM sustainment cell "
    f"- source: {result['source']}"
)
brief_md = result.get("brief")
if not brief_md:
    # Generate the deterministic brief inline so the page is never empty.
    from data.generate import baseline_brief as _bb
    brief_md = _bb(live_scenario, _baseline_estimate)
st.markdown(
    "<div class='trace-card' style='padding:22px 30px;'>",
    unsafe_allow_html=True,
)
st.markdown(brief_md)
st.markdown("</div>", unsafe_allow_html=True)

with st.expander("Show raw consumption JSON"):
    st.json({
        "scenario": result["scenario"],
        "classes":   result["estimate"]["classes"],
        "sourcing":  result["estimate"]["sourcing"],
    })


# ---------------------------------------------------------------------------
# Footer
# ---------------------------------------------------------------------------
st.markdown(
    f"<div class='trace-footer'>"
    f"Powered by Kamiwaza - 100% Data Containment - Nothing ever leaves your accredited environment."
    f"</div>",
    unsafe_allow_html=True,
)
