"""QUEUE — Streamlit app (port 3020).

Depot Maintenance Throughput Optimizer for MCLB Albany / Barstow / Blount Island.
LOGCOM published use case: AI-driven scheduling tool that optimizes induction
sequencing, workforce allocation, and parts availability to increase monthly
throughput on priority end items.

Run with:
    cd apps/20-queue
    streamlit run src/app.py --server.port 3020 --server.headless true
"""
from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

# Make `shared` and `src` importable.
APP_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = APP_ROOT.parents[1]
for p in (str(REPO_ROOT), str(APP_ROOT)):
    if p not in sys.path:
        sys.path.insert(0, p)

from shared.kamiwaza_client import BRAND  # noqa: E402
from src import agent, optimizer  # noqa: E402


# ---------- Page config + theme ---------------------------------------------

st.set_page_config(
    page_title="QUEUE — Depot Throughput Optimizer",
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
  .queue-tagline {{
    color: {BRAND['neon']};
    font-family: Helvetica, Arial, sans-serif;
    font-weight: 600;
    letter-spacing: 1.2px;
    text-transform: uppercase;
    font-size: 12px;
  }}
  .queue-headline {{
    color: #FFFFFF;
    font-family: Helvetica, Arial, sans-serif;
    font-weight: 700;
    font-size: 30px;
    line-height: 1.15;
    margin-top: 4px;
  }}
  .queue-card {{
    background: {BRAND['surface']};
    border: 1px solid {BRAND['border']};
    border-radius: 10px;
    padding: 14px 18px;
    margin-bottom: 10px;
  }}
  .queue-pill {{
    display: inline-block;
    padding: 2px 9px;
    border-radius: 999px;
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 0.6px;
    margin-left: 6px;
  }}
  .pill-fd1  {{ background:#3A0E0E; color:#FF6F66; border:1px solid #D8362F; }}
  .pill-fd2  {{ background:#3A1A0E; color:#E36F2C; border:1px solid #E36F2C; }}
  .pill-fd3  {{ background:#3A2C0E; color:#E0B341; border:1px solid #E0B341; }}
  .pill-fd4  {{ background:#0E2F22; color:#00FFA7; border:1px solid #00BB7A; }}
  .queue-footer {{
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
  .stDataFrame, .stDataFrame * {{
    color: #E8E8E8 !important;
  }}
</style>
"""
st.markdown(CSS, unsafe_allow_html=True)


def priority_pill(p: int) -> str:
    cls = {1: "pill-fd1", 2: "pill-fd2", 3: "pill-fd3", 4: "pill-fd4"}.get(p, "pill-fd4")
    return f'<span class="queue-pill {cls}">FD-{p}</span>'


# ---------- Data load (cached) ----------------------------------------------

@st.cache_data(show_spinner=False)
def _load_all() -> dict:
    return {
        "backlog": agent.load_backlog(),
        "parts": agent.load_parts(),
        "depots": agent.load_depots(),
        "scenarios": agent.load_scenarios(),
        "cache": agent.load_cached_briefs(),
    }


bundle = _load_all()
backlog_df: pd.DataFrame = bundle["backlog"]
parts_df: pd.DataFrame = bundle["parts"]
depots: list = bundle["depots"]
scenarios: list = bundle["scenarios"]


# ---------- Session state ---------------------------------------------------

if "result" not in st.session_state:
    st.session_state.result = None
if "active_scenario" not in st.session_state:
    st.session_state.active_scenario = "baseline"


# ---------- Sidebar ---------------------------------------------------------

with st.sidebar:
    st.markdown(
        f"<div class='queue-tagline'>{BRAND['footer']}</div>"
        f"<div class='queue-headline'>QUEUE</div>"
        f"<div style='color:{BRAND['text_dim']};font-size:12px;margin-top:6px;'>"
        "Depot Maintenance Throughput Optimizer<br/>"
        "MCLB Albany &middot; Barstow &middot; Blount Island"
        "</div>",
        unsafe_allow_html=True,
    )
    st.markdown("---")
    st.markdown("**MISSION FRAME**")
    st.markdown(
        "<span style='color:#9A9A9A;font-size:12px;'>"
        "Published LOGCOM use case: <i>AI-driven scheduling tool that optimizes "
        "induction sequencing, workforce allocation, and parts availability to "
        "increase monthly throughput on priority end items.</i>"
        "</span>",
        unsafe_allow_html=True,
    )
    st.markdown("---")
    st.markdown("**SCENARIO**")
    scenario_id = st.radio(
        "Pick a scenario",
        options=[s["id"] for s in scenarios],
        format_func=lambda sid: next(s["label"] for s in scenarios if s["id"] == sid),
        index=0,
        key="scenario_radio",
        label_visibility="collapsed",
    )
    st.session_state.active_scenario = scenario_id
    scenario = next(s for s in scenarios if s["id"] == scenario_id)
    st.caption(scenario["description"])

    st.markdown("---")
    st.markdown("**OPERATOR LEVERS**")
    workforce_mult = st.slider(
        "Workforce multiplier",
        min_value=0.7, max_value=1.6, value=float(scenario["workforce_mult"]),
        step=0.1,
        help="Overtime + reservist augmentation. 1.0 = current posture; 1.4 = surge.",
    )
    release_held_parts = st.toggle(
        "Release held-parts pool",
        value=bool(scenario["release_held_parts"]),
        help="Releases held long-pole NSN stock (cuts ETA in half).",
    )
    parts_slip = st.toggle(
        "Apply 30d long-pole NSN slip",
        value=bool(scenario.get("parts_slip", False)),
        help="Simulates a DLA Land slip on hydraulic seal kits, MV-22 prop blades, transfer cases.",
    )
    priority_bias = st.selectbox(
        "Priority weighting",
        options=["balanced", "fd1_first", "bay_max"],
        format_func=lambda b: {
            "balanced":  "Balanced (priority + age)",
            "fd1_first": "FD-1/FD-2 hard first",
            "bay_max":   "Maximize bay utilization",
        }[b],
        index=0 if scenario["priority_bias"] == "balanced" else (
            1 if scenario["priority_bias"] == "fd1_first" else 2),
    )

    st.markdown("---")
    st.markdown("**DATASET**")
    st.markdown(
        "<span style='color:#9A9A9A;font-size:12px;'>"
        "GCSS-MC Supply &amp; Maintenance Data + Predictive Maintenance Data. "
        "Synthetic 80-item depot backlog stands in for the real corpus. "
        "Real-data swap: set <code>QUEUE_REAL_DATA_DIR</code> and "
        "<code>KAMIWAZA_BASE_URL</code>."
        "</span>",
        unsafe_allow_html=True,
    )


# ---------- Header ----------------------------------------------------------

col_a, col_b = st.columns([0.65, 0.35])
with col_a:
    st.markdown(
        f"<div class='queue-tagline'>Depot Maintenance Throughput Optimizer &middot; MARCORLOGCOM</div>"
        f"<div class='queue-headline'>Eighty end-items in the backlog. Three depots. "
        f"Thirty days. QUEUE re-sequences for max throughput.</div>",
        unsafe_allow_html=True,
    )
with col_b:
    st.markdown(
        f"<div class='queue-card' style='text-align:right;'>"
        f"<div style='color:{BRAND['muted']};font-size:11px;letter-spacing:1px;'>CLASSIFICATION</div>"
        f"<div style='color:{BRAND['neon']};font-weight:700;letter-spacing:1.2px;'>UNCLASSIFIED // FOUO</div>"
        f"<div style='color:{BRAND['muted']};font-size:11px;letter-spacing:1px;margin-top:8px;'>POSTURE</div>"
        f"<div style='color:#FFFFFF;font-weight:700;'>On-prem &middot; Kamiwaza Stack</div>"
        f"</div>",
        unsafe_allow_html=True,
    )


# ---------- Run optimizer (always — fast, deterministic) -------------------

levers = optimizer.OptimizerLevers(
    workforce_mult=workforce_mult,
    release_held_parts=release_held_parts,
    priority_bias=priority_bias,
    parts_slip=parts_slip,
)
schedule = optimizer.build_schedule(backlog_df, depots, parts_df, levers)
metrics = schedule.metrics


# ---------- KPI row ---------------------------------------------------------

c1, c2, c3, c4 = st.columns([0.25, 0.25, 0.25, 0.25])
with c1:
    st.metric("End-items inducted (30d)", str(metrics["throughput_units"]),
              delta=f"+{metrics['throughput_uplift_pct_est']}% vs baseline")
with c2:
    st.metric("FD-1/FD-2 priority units",
              str(metrics["throughput_units_fd12"]))
with c3:
    st.metric("Blocked by parts ETA",
              str(metrics["blocked_parts"]),
              help="End-items whose required NSN ETA falls outside the 30-day horizon.")
with c4:
    st.metric("Blocked by capacity",
              str(metrics["blocked_capacity"]),
              help="End-items the depot can't fit in 30 days.")

st.markdown("---")


# ---------- Gantt schedule (Plotly timeline) -------------------------------

st.markdown("#### 30-day depot induction schedule (Plotly Gantt)")

tasks_df = optimizer.tasks_to_dataframe(schedule.tasks)
if not tasks_df.empty:
    # Color by FD priority for instant readability
    fd_colors = {1: "#D8362F", 2: "#E36F2C", 3: "#E0B341", 4: "#00BB7A"}
    tasks_df = tasks_df.copy()
    tasks_df["FD"] = tasks_df["priority"].map(lambda p: f"FD-{p}")
    depot_label = {d["id"]: d["name"] for d in depots}
    tasks_df["depot_name"] = tasks_df["depot"].map(depot_label)
    tasks_df["row"] = tasks_df["depot_name"] + "  /  " + tasks_df["bumper_no"]

    fig = px.timeline(
        tasks_df.sort_values(["depot", "start"]),
        x_start="start", x_end="end", y="depot_name",
        color="FD",
        color_discrete_map={f"FD-{k}": v for k, v in fd_colors.items()},
        hover_data={"bumper_no": True, "family": True,
                    "labor_hours": True, "bay_slot": True,
                    "FD": True, "depot_name": False},
    )
    fig.update_layout(
        height=380,
        paper_bgcolor=BRAND["bg"],
        plot_bgcolor=BRAND["surface"],
        font=dict(color="#E8E8E8"),
        legend=dict(bgcolor=BRAND["surface"], bordercolor=BRAND["border"],
                    borderwidth=1),
        margin=dict(l=10, r=10, t=10, b=10),
        xaxis=dict(gridcolor=BRAND["border"], showgrid=True,
                   title="30-day induction window"),
        yaxis=dict(gridcolor=BRAND["border"], showgrid=False, autorange="reversed"),
    )
    st.plotly_chart(fig, use_container_width=True, key="gantt")
else:
    st.warning("No inductions could be scheduled. Loosen levers and try again.")


# ---------- Bottleneck callout ---------------------------------------------

st.markdown(
    f"<div class='queue-card'>"
    f"<div style='color:{BRAND['neon']};font-size:11px;letter-spacing:1.2px;'>"
    f"DETERMINISTIC OPTIMIZER — DOMINANT BOTTLENECK</div>"
    f"<div style='color:#FFFFFF;font-weight:700;font-size:18px;margin-top:4px;'>"
    f"{metrics['bottleneck']}</div>"
    f"<div style='color:{BRAND['muted']};font-size:12px;margin-top:6px;'>"
    f"Bottleneck class: <b style='color:#E8E8E8'>{metrics['bottleneck_kind']}</b> "
    f"&middot; Horizon: {metrics['horizon_days']} days "
    f"&middot; Workforce: {metrics['workforce_mult']:.2f}x"
    f"</div></div>",
    unsafe_allow_html=True,
)


# ---------- Action row -----------------------------------------------------

c1, c2, c3 = st.columns([0.40, 0.30, 0.30])
with c1:
    if st.button("GENERATE THROUGHPUT BRIEF", use_container_width=True,
                 type="primary", key="btn_generate"):
        with st.spinner("Step 1/2 — analyzing schedule (chat_json)..."):
            analysis = agent.analyze_schedule(metrics, backlog_df, parts_df, depots)
        with st.spinner("Step 2/2 — drafting Depot Throughput Optimization Brief (Kamiwaza-deployed)..."):
            brief, source = agent.write_brief(
                scenario["label"], scenario["id"], analysis, metrics,
                backlog_df, parts_df, depots, hero=True, use_cache=True,
            )
        st.session_state.result = {
            "analysis": analysis,
            "brief": brief,
            "source": source,
            "scenario_id": scenario["id"],
            "scenario_label": scenario["label"],
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }
with c2:
    st.metric("Depots monitored", "3",
              help="MCLB Albany, MCLB Barstow, Blount Island Command")
with c3:
    st.metric("Backlog rows", str(len(backlog_df)),
              help="Synthetic GCSS-MC stand-in. 80 inducted-or-pending end items.")


# ---------- Backlog + parts panes ------------------------------------------

st.markdown("---")
left, right = st.columns([0.55, 0.45])

with left:
    st.markdown("#### Sortable backlog (top 20 by FD priority)")
    show = backlog_df[[
        "bumper_no", "family", "depot", "priority", "labor_hours_est",
        "induct_date", "status",
    ]].head(20).copy()
    show.columns = ["Bumper", "Family", "Depot", "FD", "Labor hrs", "Inducted", "Status"]
    st.dataframe(show, use_container_width=True, hide_index=True, height=400)

with right:
    st.markdown("#### Long-pole NSN watchlist")
    long_pole = parts_df[parts_df["long_pole"] == "Y"][[
        "nsn", "nomenclature", "on_hand", "eta_days", "source"
    ]].copy()
    long_pole.columns = ["NSN", "Nomenclature", "On hand", "ETA d", "Source"]
    st.dataframe(long_pole, use_container_width=True, hide_index=True, height=400)


# ---------- Per-depot utilization ------------------------------------------

st.markdown("---")
st.markdown("#### Per-depot utilization (this scenario)")
util_cols = st.columns(3)
for col, (depot_id, u) in zip(util_cols, metrics["util_by_depot"].items()):
    with col:
        st.markdown(
            f"<div class='queue-card'>"
            f"<div style='color:{BRAND['muted']};font-size:11px;letter-spacing:1.2px;'>"
            f"{depot_id}</div>"
            f"<div style='color:#FFFFFF;font-weight:700;font-size:16px;'>"
            f"{u['name']}</div>"
            f"<div style='display:flex;justify-content:space-between;margin-top:8px;'>"
            f"<div><div style='color:{BRAND['muted']};font-size:11px;'>BAY UTIL</div>"
            f"<div style='color:{BRAND['neon']};font-weight:700;'>{u['bay_util_pct']}%</div></div>"
            f"<div><div style='color:{BRAND['muted']};font-size:11px;'>LABOR UTIL</div>"
            f"<div style='color:{BRAND['neon']};font-weight:700;'>{u['labor_util_pct']}%</div></div>"
            f"<div><div style='color:{BRAND['muted']};font-size:11px;'>TASKS</div>"
            f"<div style='color:#FFFFFF;font-weight:700;'>{u['tasks']}</div></div>"
            f"</div></div>",
            unsafe_allow_html=True,
        )


# ---------- Hero brief render ----------------------------------------------

st.markdown("---")
st.markdown("### Depot Throughput Optimization Brief")

# Cache-first: serve the cached scenario brief immediately on landing so the
# demo never sits on a spinner. Operator can click GENERATE for a live re-run.
result = st.session_state.result
if (not result) or (result.get("scenario_id") != scenario["id"]):
    cached = bundle["cache"].get(scenario["id"])
    if cached and cached.get("brief"):
        result = {
            "analysis": agent.deterministic_analysis(metrics, parts_df),
            "brief": cached["brief"],
            "source": cached.get("source", "cache"),
            "scenario_id": scenario["id"],
            "scenario_label": scenario["label"],
            "generated_at": cached.get("generated_at", "cached"),
        }

if result:
    st.caption(
        f"Generated {result['generated_at']} &middot; Source: "
        f"AI engine (cached) &middot; Scenario: {result['scenario_label']}"
    )
    st.markdown(
        "<div class='queue-card' style='padding:22px 30px;'>",
        unsafe_allow_html=True,
    )
    st.markdown(result["brief"])
    st.markdown("</div>", unsafe_allow_html=True)

    with st.expander("Show raw structured analysis (chat_json)"):
        st.json(result["analysis"])
else:
    st.info("Click **GENERATE THROUGHPUT BRIEF** to score the schedule and "
            "produce the depot-throughput optimization brief.")


# ---------- Footer ----------------------------------------------------------

st.markdown(
    f"<div class='queue-footer'>"
    f"Powered by Kamiwaza &middot; 100% Data Containment — Nothing ever leaves your accredited environment."
    f"</div>",
    unsafe_allow_html=True,
)
