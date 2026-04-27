# ANCHOR — agentic RAG port-capability assessor
# Part of the MDM 2026 Hackathon Templates (https://github.com/12fn/MDMhackathon-repos)
# MIT licensed. Built on GAI (Government Acquisitions, Inc.) + Kamiwaza (https://www.kamiwaza.ai/).
"""ANCHOR — Allied Naval Capability Hub for Operational Readiness.

Streamlit app for Marine Corps Blount Island Command (BIC) and the
Maritime Prepositioning Force (MPF) planning cell.

Run:
    streamlit run src/app.py --server.port 3011
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import streamlit as st

# Make repo importable
ROOT = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(ROOT))
APP_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(APP_ROOT))

from shared.kamiwaza_client import BRAND  # noqa: E402
from src.rag import (  # noqa: E402
    load_ports,
    retrieve,
    comparison_json,
    narrative_stream,
    build_embeddings,
    KNOWN_REFERENCE_POINTS,
)

# --- Page config -----------------------------------------------------------
st.set_page_config(
    page_title="ANCHOR — Allied Naval Capability Hub",
    page_icon="⚓",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# --- Kamiwaza dark theme ---------------------------------------------------
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
  .anchor-hero {{
    background: linear-gradient(135deg, {BRAND['surface']} 0%, {BRAND['bg']} 100%);
    border: 1px solid {BRAND['border']};
    border-left: 4px solid {BRAND['primary']};
    border-radius: 8px;
    padding: 18px 24px;
    margin-bottom: 12px;
  }}
  .anchor-hero h1 {{
    color: {BRAND['neon']};
    font-family: 'Helvetica Neue', sans-serif;
    font-size: 28px;
    margin: 0;
    letter-spacing: -0.5px;
  }}
  .anchor-hero p {{
    color: {BRAND['text_dim']};
    margin: 4px 0 0 0;
    font-size: 13px;
  }}
  .anchor-pill {{
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
  .anchor-card {{
    background: {BRAND['surface']};
    border: 1px solid {BRAND['border']};
    border-radius: 6px;
    padding: 14px 18px;
    margin-bottom: 8px;
  }}
  .anchor-metric {{
    color: {BRAND['neon']};
    font-size: 22px;
    font-weight: 700;
  }}
  .anchor-metric-label {{
    color: {BRAND['text_dim']};
    font-size: 11px;
    text-transform: uppercase;
    letter-spacing: 1.2px;
  }}
  .anchor-footer {{
    color: {BRAND['text_dim']};
    font-size: 12px;
    text-align: center;
    padding: 16px 0 4px 0;
    border-top: 1px solid {BRAND['border']};
    margin-top: 28px;
  }}
  .anchor-footer span {{ color: {BRAND['primary']}; font-weight: 600; }}
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
</style>
"""
st.markdown(CSS, unsafe_allow_html=True)

# --- Header ---------------------------------------------------------------
HERO_HTML = f"""
<div class="anchor-hero">
  <h1>⚓ ANCHOR</h1>
  <p><strong>Allied Naval Capability Hub for Operational Readiness</strong> &nbsp;·&nbsp;
     MPF / Blount Island Command port-capability assessor</p>
  <p style="margin-top:8px;">
    <span class="anchor-pill">Agentic RAG</span>
    <span class="anchor-pill">WPI Corpus</span>
    <span class="anchor-pill">On-Prem Ready</span>
    <span class="anchor-pill">USMC LOGCOM 2026</span>
  </p>
</div>
"""
st.markdown(HERO_HTML, unsafe_allow_html=True)

# --- Load + index ports (cached) ------------------------------------------
@st.cache_data(show_spinner=False)
def _load() -> list[dict]:
    return load_ports()


@st.cache_resource(show_spinner=False)
def _index() -> tuple[Any, list[str]]:
    return build_embeddings()


PORTS = _load()

# --- Top metrics ----------------------------------------------------------
m1, m2, m3, m4, m5 = st.columns(5)
roro = sum(1 for p in PORTS if p["roro_capable"])
deep = sum(1 for p in PORTS if p["max_draft_m"] >= 12)
allies = sum(1 for p in PORTS if p["hostnation_status"] in ("ALLY", "US_TERRITORY"))
denied = sum(1 for p in PORTS if p["hostnation_status"] == "DENIED")
m1.markdown(f'<div class="anchor-card"><div class="anchor-metric">{len(PORTS)}</div><div class="anchor-metric-label">Ports Indexed</div></div>', unsafe_allow_html=True)
m2.markdown(f'<div class="anchor-card"><div class="anchor-metric">{roro}</div><div class="anchor-metric-label">RoRo Capable</div></div>', unsafe_allow_html=True)
m3.markdown(f'<div class="anchor-card"><div class="anchor-metric">{deep}</div><div class="anchor-metric-label">≥12m Draft</div></div>', unsafe_allow_html=True)
m4.markdown(f'<div class="anchor-card"><div class="anchor-metric">{allies}</div><div class="anchor-metric-label">Ally / US Soil</div></div>', unsafe_allow_html=True)
m5.markdown(f'<div class="anchor-card"><div class="anchor-metric">{denied}</div><div class="anchor-metric-label">Denied Risk</div></div>', unsafe_allow_html=True)

st.markdown("&nbsp;")

# --- Query bar ------------------------------------------------------------
EXAMPLES = [
    "Which ports within 500 nm of Subic Bay can offload 2 BIC-class roll-on/roll-off vessels with 12-meter channel depth?",
    "Find ally-aligned ports in the Mediterranean with at least 14m draft, RoRo, and bunker.",
    "I need a backup MPF offload site within 600 nm of Diego Garcia, partner-or-better host nation, 11m draft minimum.",
    "Show me Western Pacific deep-water ports inside 800 nm of Guam, low political risk, 15m channel.",
]

if "query" not in st.session_state:
    st.session_state.query = EXAMPLES[0]

c_q, c_btn = st.columns([5, 1])
with c_q:
    q = st.text_area(
        "Planner question",
        value=st.session_state.query,
        height=78,
        label_visibility="collapsed",
    )
with c_btn:
    st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)
    run_clicked = st.button("⚓ Assess", use_container_width=True, type="primary")
    hero_mode = st.toggle("Hero model", value=False, help="Use the Kamiwaza-deployed hero model (no -mini) for the narrative")

with st.expander("Sample planner queries", expanded=False):
    for i, ex in enumerate(EXAMPLES):
        if st.button(f"→ {ex}", key=f"ex_{i}"):
            st.session_state.query = ex
            st.rerun()

# --- Run pipeline ---------------------------------------------------------
if run_clicked or "result" not in st.session_state:
    if not q.strip():
        st.warning("Enter a planner question.")
        st.stop()

    with st.status("Agentic RAG over WPI corpus...", expanded=True) as status:
        st.write("• Parsing planner intent → structured filters")
        st.write("• Building / loading embedding index (250 port profiles)")
        _ = _index()
        st.write("• Applying capability + geography filters")
        st.write("• Vector cosine rerank over candidate set")
        result = retrieve(q, k=8)
        st.session_state.result = result
        st.session_state.query = q
        st.write(f"• Retrieved {len(result['ranked'])} top candidates from "
                 f"{result.get('candidate_count', 0)} hard-filter passes")
        status.update(label="Retrieval complete.", state="complete", expanded=False)

result = st.session_state.result
ranked = result.get("ranked", [])
filters = result.get("filters", {})

# --- Filter summary -------------------------------------------------------
with st.expander("Parsed filters (LLM-structured)", expanded=False):
    st.json(filters)

if not ranked:
    st.error("No ports matched even after relaxing filters. Try a broader question.")
    st.stop()

# --- Layout: map + table --------------------------------------------------
left, right = st.columns([1.1, 1.0])

with left:
    st.markdown("##### Port pins (filtered)")
    # Render with Folium for proper Leaflet w/ pins
    try:
        import folium
        from streamlit_folium import st_folium

        center_lat = float(np.mean([r["lat"] for r in ranked]))
        center_lon = float(np.mean([r["lon"] for r in ranked]))
        fmap = folium.Map(
            location=[center_lat, center_lon],
            zoom_start=4,
            tiles="CartoDB dark_matter",
        )

        # Plot every WPI port faintly first
        for p in PORTS:
            folium.CircleMarker(
                [p["lat"], p["lon"]],
                radius=2,
                color="#444",
                weight=0,
                fill=True,
                fill_color="#666",
                fill_opacity=0.35,
            ).add_to(fmap)

        # Overlay filter "near" reference if present
        near = filters.get("near") or {}
        if near.get("lat") is not None and near.get("lon") is not None:
            folium.Marker(
                [near["lat"], near["lon"]],
                icon=folium.Icon(color="red", icon="crosshairs", prefix="fa"),
                tooltip=f"Reference: {near.get('name', 'planner anchor')}",
            ).add_to(fmap)
            if near.get("radius_nm"):
                # 1 nm ≈ 1852 m
                folium.Circle(
                    [near["lat"], near["lon"]],
                    radius=float(near["radius_nm"]) * 1852,
                    color=BRAND["primary"],
                    weight=2,
                    fill=False,
                    dash_array="6,6",
                ).add_to(fmap)

        # Plot ranked (top-K) prominently
        for i, p in enumerate(ranked):
            color = BRAND["neon"] if i == 0 else BRAND["primary"]
            popup = (
                f"<b>{p['name']}</b><br>"
                f"{p['country']} · {p['region']}<br>"
                f"Draft {p['max_draft_m']}m · Channel {p['channel_depth_m']}m<br>"
                f"Berths {p['berths']} · Cranes {p['cranes']}<br>"
                f"RoRo {'✓' if p['roro_capable'] else '✗'} · "
                f"Bunker {'✓' if p['bunker_available'] else '✗'}<br>"
                f"HN: {p['hostnation_status']} · Pol risk {p['political_risk']}/10"
            )
            folium.CircleMarker(
                [p["lat"], p["lon"]],
                radius=10 if i == 0 else 7,
                color=color,
                weight=2,
                fill=True,
                fill_color=color,
                fill_opacity=0.85,
                popup=folium.Popup(popup, max_width=280),
                tooltip=f"#{i+1} {p['name']}",
            ).add_to(fmap)

        st_folium(fmap, height=520, use_container_width=True, returned_objects=[])
    except ImportError:
        # Fallback to st.map (no styling, but works)
        df = pd.DataFrame([{"lat": r["lat"], "lon": r["lon"]} for r in ranked])
        st.map(df, zoom=3)

with right:
    st.markdown("##### Top candidates (vector-reranked)")
    df = pd.DataFrame([
        {
            "Rank": i + 1,
            "Port": r["name"],
            "Country": r["country"],
            "Draft (m)": r["max_draft_m"],
            "Channel (m)": r["channel_depth_m"],
            "LOA (m)": r["max_loa_m"],
            "Berths": r["berths"],
            "RoRo": "✓" if r["roro_capable"] else "—",
            "Bunker": "✓" if r["bunker_available"] else "—",
            "HN": r["hostnation_status"],
            "Pol Risk": r["political_risk"],
            "Wx Risk": r["weather_risk"],
            "Sim": r.get("similarity", 0.0),
            **({"Dist (nm)": r["_distance_nm"]} if "_distance_nm" in r else {}),
        }
        for i, r in enumerate(ranked)
    ])
    st.dataframe(df, hide_index=True, use_container_width=True, height=520)

# --- Comparison table (LLM structured) ------------------------------------
st.markdown("---")
st.markdown("##### MPF planner comparison (LLM-structured JSON)")

if "comparison" not in st.session_state or st.session_state.get("compare_for") != st.session_state.query:
    with st.spinner("Generating comparison table..."):
        try:
            comp = comparison_json(st.session_state.query, ranked)
            st.session_state.comparison = comp
            st.session_state.compare_for = st.session_state.query
        except Exception as e:  # noqa: BLE001
            st.warning(f"Comparison call failed: {e}")
            st.session_state.comparison = {"comparison": []}

comp = st.session_state.comparison
rows = comp.get("comparison", []) if isinstance(comp, dict) else []
if rows:
    cdf = pd.DataFrame([
        {
            "Port": r.get("name"),
            "Country": r.get("country"),
            "Fit": r.get("fit_score"),
            "Strengths": " · ".join(r.get("key_strengths") or []),
            "Risks": " · ".join(r.get("key_risks") or []),
            "Recommended Role": r.get("recommended_role"),
        }
        for r in rows
    ])
    st.dataframe(cdf, hide_index=True, use_container_width=True)
else:
    st.info("No comparison rows returned.")

# --- Narrative recommendation (streaming) ---------------------------------
st.markdown("##### MPF narrative recommendation")
narrative_box = st.empty()

# Auto-stream the narrative whenever the comparison just changed (or no narrative cached yet).
needs_narrative = (
    "narrative" not in st.session_state
    or st.session_state.get("narrative_for") != st.session_state.query
)

c_n1, c_n2 = st.columns([1, 5])
with c_n1:
    regen = st.button("Regenerate", help="Re-stream the narrative")

if needs_narrative or regen:
    chunks = []
    out_md = narrative_box.empty()
    for piece in narrative_stream(
        st.session_state.query, ranked, comp, hero=hero_mode,
    ):
        chunks.append(piece)
        out_md.markdown("".join(chunks))
    st.session_state.narrative = "".join(chunks)
    st.session_state.narrative_for = st.session_state.query
else:
    narrative_box.markdown(st.session_state.narrative)

# --- Footer ---------------------------------------------------------------
import os
endpoint = os.getenv("KAMIWAZA_BASE_URL") or "Kamiwaza-deployed model (OpenAI fallback available via env-var swap)"
st.markdown(
    f'<div class="anchor-footer">'
    f'<span>Powered by Kamiwaza</span> &nbsp;·&nbsp; '
    f'Inference endpoint: <code>{endpoint}</code> &nbsp;·&nbsp; '
    f'Synthetic stand-in for NGA MSI World Port Index (WPI), Pub 150'
    f'</div>',
    unsafe_allow_html=True,
)
