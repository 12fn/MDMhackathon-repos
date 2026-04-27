"""CHAIN — Streamlit app (port 3024).

Run with:
    cd apps/24-chain
    streamlit run src/app.py --server.port 3024 --server.headless true \\
      --server.runOnSave false --server.fileWatcherType none \\
      --browser.gatherUsageStats false
"""
from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import streamlit as st

APP_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = APP_ROOT.parents[1]
for p in (str(REPO_ROOT), str(APP_ROOT)):
    if p not in sys.path:
        sys.path.insert(0, p)

from shared.kamiwaza_client import BRAND  # noqa: E402
from src import agent, graph  # noqa: E402


# ─────────────────────────────────────────────────────────────────────────────
# Page config + theme
# ─────────────────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="CHAIN — USMC Critical-Component Risk",
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
  .chain-tagline {{
    color: {BRAND['neon']};
    font-family: Helvetica, Arial, sans-serif;
    font-weight: 600;
    letter-spacing: 1.2px;
    text-transform: uppercase;
    font-size: 12px;
  }}
  .chain-headline {{
    color: #FFFFFF;
    font-family: Helvetica, Arial, sans-serif;
    font-weight: 700;
    font-size: 28px;
    line-height: 1.15;
    margin-top: 4px;
  }}
  .chain-card {{
    background: {BRAND['surface']};
    border: 1px solid {BRAND['border']};
    border-radius: 10px;
    padding: 14px 18px;
    margin-bottom: 10px;
  }}
  .chain-pill {{
    display: inline-block;
    padding: 2px 9px;
    border-radius: 999px;
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 0.6px;
    margin-left: 6px;
  }}
  .pill-low    {{ background:#0E2F22; color:#00FFA7; border:1px solid #00BB7A; }}
  .pill-watch  {{ background:#3A2C0E; color:#E0B341; border:1px solid #E0B341; }}
  .pill-degrad {{ background:#3A1A0E; color:#E36F2C; border:1px solid #E36F2C; }}
  .pill-crit   {{ background:#3A0E0E; color:#FF6F66; border:1px solid #D8362F; }}
  .chain-footer {{
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


def status_pill(s: str) -> str:
    cls = {"WATCH": "pill-watch", "ELEVATED": "pill-watch",
           "DEGRADED": "pill-degrad", "CRITICAL": "pill-crit"}.get(s, "pill-low")
    return f'<span class="chain-pill {cls}">{s}</span>'


# ─────────────────────────────────────────────────────────────────────────────
# Session state
# ─────────────────────────────────────────────────────────────────────────────
if "result" not in st.session_state:
    st.session_state.result = None


# Load data once (cheap, deterministic)
SUPPLIERS = agent.load_suppliers()
EDGES = agent.load_edges()
CHOKEPOINTS = agent.load_chokepoints()
EVENTS = agent.load_events()
RISK = agent.baseline_node_risk(SUPPLIERS, EVENTS, CHOKEPOINTS)
CACHED = agent.load_cached_briefs()

SCENARIOS = [
    {"id": "taiwan_strait",
     "title": "Taiwan Strait closure (PLAN exercise → quarantine)",
     "primary_chokepoint": "TWNSTRAIT",
     "headline": "PLAN live-fire box closes Taiwan Strait for 14 days; TSMC export tonnage drops 92%."},
    {"id": "suez_bab_compound",
     "title": "Suez + Bab-el-Mandeb compound disruption",
     "primary_chokepoint": "SUEZ",
     "headline": "Houthi escalation reroutes 67% of Asia-Europe-CONUS tonnage around Cape of Good Hope."},
    {"id": "rareearth_export",
     "title": "PRC rare-earth export freeze",
     "primary_chokepoint": "BAOTOU",
     "headline": "Beijing suspends NdFeB magnet export licenses; Marine seekers and motors at single-source risk."},
]


# ─────────────────────────────────────────────────────────────────────────────
# Sidebar
# ─────────────────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown(
        f"<div class='chain-tagline'>{BRAND['footer']}</div>"
        f"<div class='chain-headline'>CHAIN</div>"
        f"<div style='color:{BRAND['text_dim']};font-size:12px;margin-top:6px;'>"
        "Critical-Component Risk for USMC<br/>PEO Land Systems & PEO Aviation"
        "</div>",
        unsafe_allow_html=True,
    )
    st.markdown("---")
    st.markdown("**MISSION FRAME**")
    st.markdown(
        "<span style='color:#9A9A9A;font-size:12px;'>"
        "When a Taiwan Strait, Suez, or Malacca disruption hits, which Marine "
        "procurement programs are exposed and what are the mitigation options? "
        "LOGCOM problem set: <i>contested logistics, supply-chain management.</i>"
        "</span>",
        unsafe_allow_html=True,
    )
    st.markdown("---")
    hero = st.toggle("Hero brief (Kamiwaza-deployed hero narrative)", value=True,
                     help="When ON, uses the Kamiwaza-deployed hero model. Cache-first.")

    st.markdown("**SCENARIO**")
    scenario_label = st.radio(
        "Pick a disruption scenario",
        options=[s["title"] for s in SCENARIOS],
        index=0,
        label_visibility="collapsed",
    )
    selected = next(s for s in SCENARIOS if s["title"] == scenario_label)

    st.markdown("---")
    st.markdown("**DATASETS (synthetic stand-in)**")
    st.markdown(
        "<span style='color:#9A9A9A;font-size:12px;'>"
        "Fused from three Kaggle sources: <b>Global Supply Chain Disruption "
        "& Resilience</b>, <b>Global supply-chain risk & logistics</b>, "
        "<b>Global trade 2024-2026</b>. "
        "Real-data swap: <code>data/load_real.py</code> + "
        "<code>REAL_DATA_DIR=…</code>."
        "</span>",
        unsafe_allow_html=True,
    )
    st.markdown("---")
    st.markdown("**LAYOUT**")
    layout_choice = st.selectbox("Topology layout", options=["geo", "spring"],
                                 index=0, label_visibility="collapsed")


# ─────────────────────────────────────────────────────────────────────────────
# Header
# ─────────────────────────────────────────────────────────────────────────────
col_a, col_b = st.columns([0.65, 0.35])
with col_a:
    st.markdown(
        "<div class='chain-tagline'>Global supply-chain disruption forecaster · USMC sustainment</div>"
        "<div class='chain-headline'>USMC critical-component sourcing in a polycrisis world. "
        "CHAIN watches every chokepoint.</div>",
        unsafe_allow_html=True,
    )
with col_b:
    st.markdown(
        "<div class='chain-card' style='text-align:right;'>"
        f"<div style='color:{BRAND['muted']};font-size:11px;letter-spacing:1px;'>CLASSIFICATION</div>"
        f"<div style='color:{BRAND['neon']};font-weight:700;letter-spacing:1.2px;'>UNCLASSIFIED // FOUO</div>"
        f"<div style='color:{BRAND['muted']};font-size:11px;letter-spacing:1px;margin-top:8px;'>POSTURE</div>"
        f"<div style='color:#FFFFFF;font-weight:700;'>On-prem · Kamiwaza Stack</div>"
        "</div>",
        unsafe_allow_html=True,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Action row
# ─────────────────────────────────────────────────────────────────────────────
critical_count = agent.nodes_at_critical_risk(RISK)

c1, c2, c3, c4 = st.columns([0.27, 0.24, 0.24, 0.25])
with c1:
    if st.button("GENERATE RISK BRIEF", use_container_width=True, type="primary",
                 key="btn_generate"):
        with st.spinner("Step 1/2 — analyzing disrupted network (chat_json)…"):
            struct = agent.analyze_network(selected, SUPPLIERS, EDGES, CHOKEPOINTS)
        with st.spinner("Step 2/2 — drafting Critical-Component Risk Brief (Kamiwaza-deployed)…"):
            brief = agent.write_brief(selected, struct, hero=hero)
        st.session_state.result = {
            "scenario": selected, "structured": struct, "brief": brief,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }
with c2:
    st.metric("Network nodes", f"{len(SUPPLIERS)}")
with c3:
    st.metric("Disruption events (60d)", f"{len(EVENTS)}")
with c4:
    st.metric("Nodes at critical risk", str(critical_count),
              help="Heuristic baseline from synthetic events feed; refined when LLM lands.")


st.markdown("---")


# ─────────────────────────────────────────────────────────────────────────────
# Topology + chokepoint map
# ─────────────────────────────────────────────────────────────────────────────
g_left, g_right = st.columns([0.62, 0.38])
with g_left:
    st.markdown("#### Supply-network topology — risk-colored")
    st.plotly_chart(graph.build_figure(SUPPLIERS, EDGES, RISK, layout=layout_choice),
                    use_container_width=True, key="topology_graph")
    st.markdown(
        "<div style='font-size:11px;color:#9A9A9A;'>"
        "<span style='color:#00BB7A;'>● low</span>  "
        "<span style='color:#E0B341;'>● moderate</span>  "
        "<span style='color:#E36F2C;'>● elevated</span>  "
        "<span style='color:#D8362F;'>● critical</span>"
        "  &nbsp;|&nbsp; "
        "Square=Supplier · Diamond=Chokepoint · Circle=USMC end-item · "
        "Edge thickness = annual flow $M"
        "</div>",
        unsafe_allow_html=True,
    )

with g_right:
    st.markdown("#### Maritime chokepoints — current status")
    st.plotly_chart(graph.build_chokepoint_map(CHOKEPOINTS),
                    use_container_width=True, key="chokepoint_map")
    for c in CHOKEPOINTS:
        st.markdown(
            f"<div class='chain-card' style='padding:8px 12px;margin-bottom:6px;'>"
            f"<div style='display:flex;justify-content:space-between;align-items:center;'>"
            f"<div><b style='color:#FFFFFF'>{c['name']}</b> "
            f"<span style='color:{BRAND['muted']};font-size:11px;'>· "
            f"${c['daily_transit_musd']:,}M/day</span></div>"
            f"<div>{status_pill(c['status'])}</div>"
            f"</div>"
            f"<div style='color:#C0C0C0;font-size:12px;margin-top:3px;'>"
            f"{c['current_event']}"
            f"</div></div>",
            unsafe_allow_html=True,
        )


st.markdown("---")


# ─────────────────────────────────────────────────────────────────────────────
# Recent disruption events
# ─────────────────────────────────────────────────────────────────────────────
with st.expander("Recent disruption events feed (60 days)", expanded=False):
    df = pd.DataFrame(EVENTS[:40])
    if not df.empty:
        df = df.rename(columns={
            "date": "Date", "event_type": "Type", "target_name": "Target",
            "headline": "Headline", "severity": "Severity",
            "estimated_impact_days": "Impact (d)", "value_at_risk_musd": "Value @ risk ($M)",
        })
        st.dataframe(df[["Date", "Type", "Severity", "Target", "Headline",
                         "Impact (d)", "Value @ risk ($M)"]],
                     use_container_width=True, hide_index=True, height=320)


# ─────────────────────────────────────────────────────────────────────────────
# Brief output
# ─────────────────────────────────────────────────────────────────────────────
result = st.session_state.result
if not result:
    # Auto-load cached brief for selected scenario so the page is never empty.
    cached_entry = CACHED.get(selected["id"])
    if cached_entry and cached_entry.get("brief"):
        result = {
            "scenario": selected,
            "structured": cached_entry.get("structured", {}),
            "brief": cached_entry["brief"],
            "generated_at": cached_entry.get("generated_at", "cached"),
        }

if result:
    st.markdown("### Critical-Component Risk Brief")
    st.caption(
        f"Scenario: {result['scenario']['title']}  ·  Generated {result['generated_at']}  ·  "
        "Originator: CHAIN · USMC LOGCOM critical-component cell"
    )
    struct = result.get("structured", {}) or {}
    if struct:
        sc1, sc2, sc3 = st.columns([0.42, 0.30, 0.28])
        with sc1:
            progs = struct.get("affected_marine_program") or []
            st.markdown(
                "<div class='chain-card'>"
                f"<div style='color:{BRAND['muted']};font-size:11px;letter-spacing:1px;'>"
                "EXPOSED PROGRAMS</div>"
                + "".join(
                    f"<div style='color:#FFFFFF;font-size:13px;margin-top:3px;'>● {p}</div>"
                    for p in progs[:6]
                ) +
                "</div>",
                unsafe_allow_html=True,
            )
        with sc2:
            subs = struct.get("substitute_supplier") or []
            st.markdown(
                "<div class='chain-card'>"
                f"<div style='color:{BRAND['muted']};font-size:11px;letter-spacing:1px;'>"
                "SUBSTITUTE SUPPLIERS</div>"
                + "".join(
                    f"<div style='color:#FFFFFF;font-size:13px;margin-top:3px;'>○ {s}</div>"
                    for s in subs[:5]
                ) +
                "</div>",
                unsafe_allow_html=True,
            )
        with sc3:
            st.markdown(
                "<div class='chain-card' style='text-align:center;'>"
                f"<div style='color:{BRAND['muted']};font-size:11px;letter-spacing:1px;'>"
                "LEAD-TIME IMPACT</div>"
                f"<div style='color:{BRAND['neon']};font-size:38px;font-weight:700;'>"
                f"{struct.get('lead_time_impact_days', '—')}<span style='font-size:14px;'> days</span></div>"
                "</div>",
                unsafe_allow_html=True,
            )

    st.markdown("<div class='chain-card' style='padding:22px 30px;'>", unsafe_allow_html=True)
    st.markdown(result["brief"])
    st.markdown("</div>", unsafe_allow_html=True)

    with st.expander("Show raw structured analysis (JSON from chat_json)"):
        st.json(result.get("structured", {}))
else:
    st.info("Click **GENERATE RISK BRIEF** to analyze the disrupted network and produce the "
            "Critical-Component Risk Brief.")


# ─────────────────────────────────────────────────────────────────────────────
# Footer
# ─────────────────────────────────────────────────────────────────────────────
st.markdown(
    f"<div class='chain-footer'>"
    f"Powered by Kamiwaza · 100% Data Containment — Nothing ever leaves your accredited environment."
    f"</div>",
    unsafe_allow_html=True,
)
