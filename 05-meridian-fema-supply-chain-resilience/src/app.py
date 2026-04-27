# MERIDIAN — MARFORPAC sustainment node OPORD-style climate brief
# Part of the MDM 2026 Hackathon Templates (https://github.com/12fn/MDMhackathon-repos)
# MIT licensed. Built on GAI (Government Acquisitions, Inc.) + Kamiwaza (https://www.kamiwaza.ai/).
"""MERIDIAN — Streamlit app (port 3005).

Run with:
    streamlit run src/app.py --server.port 3005 --server.headless true
"""
from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

import pandas as pd
import streamlit as st

# Make `shared` and `src` importable.
APP_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = APP_ROOT.parents[1]
for p in (str(REPO_ROOT), str(APP_ROOT)):
    if p not in sys.path:
        sys.path.insert(0, p)

from shared.kamiwaza_client import BRAND  # noqa: E402
from src import agent, graph  # noqa: E402


# ---------- Page config + theme ---------------------------------------------

st.set_page_config(
    page_title="MERIDIAN — MARFORPAC Climate Resilience",
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
  .meridian-tagline {{
    color: {BRAND['neon']};
    font-family: Helvetica, Arial, sans-serif;
    font-weight: 600;
    letter-spacing: 1.2px;
    text-transform: uppercase;
    font-size: 12px;
  }}
  .meridian-headline {{
    color: #FFFFFF;
    font-family: Helvetica, Arial, sans-serif;
    font-weight: 700;
    font-size: 30px;
    line-height: 1.15;
    margin-top: 4px;
  }}
  .meridian-card {{
    background: {BRAND['surface']};
    border: 1px solid {BRAND['border']};
    border-radius: 10px;
    padding: 14px 18px;
    margin-bottom: 10px;
  }}
  .meridian-pill {{
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
  .meridian-footer {{
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
  /* dataframe */
  .stDataFrame, .stDataFrame * {{
    color: #E8E8E8 !important;
  }}
</style>
"""
st.markdown(CSS, unsafe_allow_html=True)


def risk_pill(r: float) -> str:
    if r < 4.0:
        return f'<span class="meridian-pill pill-low">{r:.1f}</span>'
    if r < 6.5:
        return f'<span class="meridian-pill pill-med">{r:.1f}</span>'
    if r < 8.0:
        return f'<span class="meridian-pill pill-high">{r:.1f}</span>'
    return f'<span class="meridian-pill pill-crit">{r:.1f}</span>'


# ---------- Session state ---------------------------------------------------

if "result" not in st.session_state:
    st.session_state.result = None
if "injected_count" not in st.session_state:
    st.session_state.injected_count = 0


# ---------- Sidebar ---------------------------------------------------------

with st.sidebar:
    st.markdown(
        f"<div class='meridian-tagline'>{BRAND['footer']}</div>"
        f"<div class='meridian-headline'>MERIDIAN</div>"
        f"<div style='color:{BRAND['text_dim']};font-size:12px;margin-top:6px;'>"
        "Maritime / Energy Resilience for<br/>Indo-Pacific Distribution & Aerial Networks"
        "</div>",
        unsafe_allow_html=True,
    )
    st.markdown("---")
    st.markdown("**MISSION FRAME**")
    st.markdown(
        "<span style='color:#9A9A9A;font-size:12px;'>"
        "Daily climate-resilience brief over MARFORPAC's 12-node sustainment chain. "
        "LOGCOM problem set: <i>contested logistics, supply chain management, expeditionary operations</i>."
        "</span>",
        unsafe_allow_html=True,
    )
    st.markdown("---")
    hero = st.toggle("Hero call (Kamiwaza-deployed hero narrative)", value=True,
                     help="When ON, uses the Kamiwaza-deployed hero model. When OFF, uses the mini chain.")
    st.markdown("**DATASET**")
    st.markdown(
        "<span style='color:#9A9A9A;font-size:12px;'>"
        "FEMA Supply Chain Climate Resilience Data (sponsored by Qlik). "
        "Synthetic NOAA / JTWC / FEMA / J2 / G-4 reports stand in for the real corpus. "
        "Real-data swap: mount classified feeds, set <code>KAMIWAZA_BASE_URL</code>."
        "</span>",
        unsafe_allow_html=True,
    )
    st.markdown("---")
    st.markdown("**INJECT NEW INCIDENT** (demo)")
    target_choice = st.selectbox(
        "Node",
        options=["APRA", "AAFB", "NAHA", "KADENA", "SUBIC", "TINIAN",
                 "IWAKUNI", "SASEBO", "YOKO", "PNI", "PALAU", "DGAR"],
        index=0,
        key="inject_target",
    )
    incident_kind = st.selectbox(
        "Kind",
        options=["Cat-5 typhoon CPA <48h",
                 "Pier crane catastrophic failure",
                 "Undersea cable cut",
                 "Host-nation labor strike",
                 "Fuel berm contamination"],
        key="inject_kind",
    )
    if st.button("Inject incident", use_container_width=True, key="btn_inject"):
        body = (
            f"# MARFORPAC G-4 FLASH INCIDENT (INJECTED)\n"
            f"**DTG:** {datetime.utcnow().strftime('%d%H%MZ %b %Y').upper()}\n"
            f"**Node:** {target_choice}\n"
            f"**Incident:** {incident_kind}\n"
            f"**Effect on Sustainment:** Severe — sustainment throughput at this node "
            f"projected to fall by 60-90% within 24h.\n"
            f"**Confidence:** HIGH\n"
            f"**Recommended COA:** Re-route via nearest feasible alternate; CCDR notified.\n"
        )
        agent.inject_incident({"target_id": target_choice, "body": body})
        st.session_state.injected_count += 1
        st.toast(f"Incident injected at {target_choice}. Click GENERATE to refresh.")


# ---------- Header ----------------------------------------------------------

col_a, col_b = st.columns([0.65, 0.35])
with col_a:
    st.markdown(
        f"<div class='meridian-tagline'>Daily climate-resilience brief · MARFORPAC</div>"
        f"<div class='meridian-headline'>MARFORPAC sustainment hangs by a string of 12 nodes. MERIDIAN watches every one.</div>",
        unsafe_allow_html=True,
    )
with col_b:
    st.markdown(
        f"<div class='meridian-card' style='text-align:right;'>"
        f"<div style='color:{BRAND['muted']};font-size:11px;letter-spacing:1px;'>CLASSIFICATION</div>"
        f"<div style='color:{BRAND['neon']};font-weight:700;letter-spacing:1.2px;'>UNCLASSIFIED // FOUO</div>"
        f"<div style='color:{BRAND['muted']};font-size:11px;letter-spacing:1px;margin-top:8px;'>POSTURE</div>"
        f"<div style='color:#FFFFFF;font-weight:700;'>On-prem · Kamiwaza Stack</div>"
        f"</div>",
        unsafe_allow_html=True,
    )


# ---------- Action row ------------------------------------------------------

# Deterministic baseline scoring — populates the topology graph + the
# `Nodes at critical risk` metric card the moment the page loads, so neither
# is gated on the LLM hero call landing.
_baseline_nodes = agent.load_nodes()
_baseline_reports = agent.load_reports()
_baseline_scores = agent.baseline_scores(_baseline_nodes, _baseline_reports)
_critical_count = agent.nodes_at_critical_risk(_baseline_scores)

c1, c2, c3, c4 = st.columns([0.25, 0.25, 0.25, 0.25])
with c1:
    if st.button("GENERATE TODAYS BRIEF", use_container_width=True, type="primary",
                 key="btn_generate"):
        with st.spinner("Step 1/2 — scoring 12 nodes (chat_json)…"):
            nodes = agent.load_nodes()
            edges = agent.load_edges()
            reports = agent.load_reports()
            scores = agent.score_nodes(nodes, reports)
        with st.spinner("Step 2/2 — drafting OPORD-style brief (Kamiwaza-deployed)…"):
            brief = agent.write_brief(nodes, scores, reports, hero=hero)
        st.session_state.result = {
            "nodes": nodes, "edges": edges, "reports": reports,
            "scores": scores, "brief": brief,
            "generated_at": datetime.utcnow().isoformat() + "Z",
        }
with c2:
    st.metric("Nodes monitored", "12")
with c3:
    rep_count = len(list((agent.DATA_DIR / "reports").glob("*.md")))
    st.metric("Source reports", f"{rep_count}")
with c4:
    # Deterministic from synth corpus + criticality — never zero in the demo.
    st.metric("Nodes at critical risk", str(_critical_count),
              help="Heuristic baseline from synthetic corpus; refined when LLM lands.")


st.markdown("---")


# ---------- Default render (no result yet) ---------------------------------

if not st.session_state.result:
    nodes = _baseline_nodes
    edges = agent.load_edges()
    g_left, g_right = st.columns([0.62, 0.38])
    with g_left:
        st.markdown("#### Supply-line topology — baseline (heuristic risk overlay)")
        # Baseline scores feed real risk colors on the graph immediately, so
        # the topology never appears empty or all-grey before the LLM lands.
        st.plotly_chart(graph.build_figure(nodes, edges, _baseline_scores),
                        use_container_width=True, key="baseline_graph")
    with g_right:
        st.markdown("#### 12 critical nodes")
        df = pd.DataFrame([
            {"ID": n["id"], "Node": n["name"], "Type": n["kind"], "CCDR": n["ccdr"],
             "Crit.": n["criticality"], "Tons/day": n["throughput_tpd"],
             "Fuel kgal": n["fuel_storage_kgal"]}
            for n in nodes
        ])
        st.dataframe(df, use_container_width=True, hide_index=True, height=440)
    st.info("Click **GENERATE TODAY'S BRIEF** to score all 12 nodes and produce the OPORD-style daily.")

else:
    r = st.session_state.result
    g_left, g_right = st.columns([0.58, 0.42])

    with g_left:
        st.markdown("#### Supply-line topology — risk-colored")
        st.plotly_chart(graph.build_figure(r["nodes"], r["edges"], r["scores"]),
                        use_container_width=True, key="risk_graph")
        # Legend
        st.markdown(
            "<div style='font-size:11px;color:#9A9A9A;'>"
            "<span style='color:#00BB7A;'>● low</span>  "
            "<span style='color:#E0B341;'>● moderate</span>  "
            "<span style='color:#E36F2C;'>● elevated</span>  "
            "<span style='color:#D8362F;'>● critical</span>"
            "  &nbsp;&nbsp;|&nbsp;&nbsp; "
            "Edge styles: solid=sea · dash=air · dot=road · dash-dot=undersea cable"
            "</div>",
            unsafe_allow_html=True,
        )

    with g_right:
        st.markdown("#### Node risk ranking")
        ranked = sorted(r["scores"], key=lambda s: s["risk_index"], reverse=True)
        node_by_id = {n["id"]: n for n in r["nodes"]}
        for s in ranked:
            n = node_by_id.get(s["node_id"])
            if not n:
                continue
            st.markdown(
                f"<div class='meridian-card' style='padding:8px 12px;margin-bottom:6px;'>"
                f"<div style='display:flex;justify-content:space-between;align-items:center;'>"
                f"<div><b style='color:#FFFFFF'>{n['name']}</b> "
                f"<span style='color:{BRAND['muted']};font-size:11px;'>· {n['id']} · {n['ccdr']}</span></div>"
                f"<div>{risk_pill(s['risk_index'])}</div>"
                f"</div>"
                f"<div style='color:#C0C0C0;font-size:12px;margin-top:3px;'>"
                f"<b>Top threat:</b> {s['top_threat']} "
                f"<span style='color:{BRAND['muted']};'>({s['confidence']})</span></div>"
                f"</div>",
                unsafe_allow_html=True,
            )

    st.markdown("---")
    st.markdown("### Daily Resilience Brief")
    st.caption(f"Generated {r['generated_at']} · Originator: MERIDIAN G-4 climate-resilience cell")
    # Open visual card; use real st.markdown so headings (## PARA 1 ...) render
    # as proper h2 elements (the demo recorder waits on the literal "PARA 1" text).
    st.markdown(
        "<div class='meridian-card' style='padding:22px 30px;'>",
        unsafe_allow_html=True,
    )
    st.markdown(r["brief"])
    st.markdown("</div>", unsafe_allow_html=True)

    with st.expander("Show raw node scores (JSON)"):
        st.json({s["node_id"]: {k: v for k, v in s.items() if k != "node_id"}
                 for s in ranked})


# ---------- Footer ----------------------------------------------------------

st.markdown(
    f"<div class='meridian-footer'>"
    f"Powered by Kamiwaza · 100% Data Containment — Nothing ever leaves your accredited environment."
    f"</div>",
    unsafe_allow_html=True,
)
