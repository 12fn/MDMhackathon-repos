"""OPENGATE — Federal-Data Discovery RAG for Marine Analysts.

Streamlit single-page app. RAG over a synthetic data.gov-shape catalog of
~200 federal datasets across NOAA / NASA / FEMA / DOT / DOD / USDA / USGS /
EIA / DHS / State / USAID / Census / EPA / VA / BLS.

Run:
    streamlit run src/app.py --server.port 3026 --server.headless true \\
        --server.runOnSave false --server.fileWatcherType none \\
        --browser.gatherUsageStats false
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(ROOT))
APP_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(APP_ROOT))

from shared.kamiwaza_client import BRAND  # noqa: E402
from src.rag import (  # noqa: E402
    apply_filters,
    baseline_brief,
    build_embeddings,
    comparison_json,
    hero_brief,
    load_cached_briefs,
    load_datasets,
    parse_query,
    retrieve,
)

st.set_page_config(
    page_title="OPENGATE — Federal-Data Discovery",
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
  .og-hero {{
    background: linear-gradient(135deg, {BRAND['surface']} 0%, {BRAND['bg']} 100%);
    border: 1px solid {BRAND['border']};
    border-left: 4px solid {BRAND['primary']};
    border-radius: 8px;
    padding: 18px 24px;
    margin-bottom: 12px;
  }}
  .og-hero h1 {{
    color: {BRAND['neon']};
    font-family: 'Helvetica Neue', sans-serif;
    font-size: 28px;
    margin: 0;
    letter-spacing: -0.5px;
  }}
  .og-hero p {{
    color: {BRAND['text_dim']};
    margin: 4px 0 0 0;
    font-size: 13px;
  }}
  .og-pill {{
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
  .og-card {{
    background: {BRAND['surface']};
    border: 1px solid {BRAND['border']};
    border-radius: 6px;
    padding: 14px 18px;
    margin-bottom: 8px;
  }}
  .og-metric {{
    color: {BRAND['neon']};
    font-size: 22px;
    font-weight: 700;
  }}
  .og-metric-label {{
    color: {BRAND['text_dim']};
    font-size: 11px;
    text-transform: uppercase;
    letter-spacing: 1.2px;
  }}
  .og-brief {{
    background: {BRAND['surface_high']};
    border: 1px solid {BRAND['border']};
    border-left: 4px solid {BRAND['neon']};
    border-radius: 6px;
    padding: 18px 22px;
    color: #E8E8E8;
    font-size: 14px;
    line-height: 1.55;
  }}
  .og-brief strong {{ color: {BRAND['primary']}; }}
  .og-footer {{
    color: {BRAND['text_dim']};
    font-size: 12px;
    text-align: center;
    padding: 16px 0 4px 0;
    border-top: 1px solid {BRAND['border']};
    margin-top: 28px;
  }}
  .og-footer span {{ color: {BRAND['primary']}; font-weight: 600; }}
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

HERO_HTML = f"""
<div class="og-hero">
  <h1>OPENGATE</h1>
  <p><strong>Federal-Data Discovery RAG for Marine Analysts</strong> &nbsp;-&nbsp;
     data.gov catalog search for MARCORLOGCOM action officers</p>
  <p style="margin-top:8px;">
    <span class="og-pill">Production-Shape RAG</span>
    <span class="og-pill">data.gov Catalog</span>
    <span class="og-pill">On-Prem Ready</span>
    <span class="og-pill">USMC LOGCOM 2026</span>
  </p>
</div>
"""
st.markdown(HERO_HTML, unsafe_allow_html=True)


@st.cache_data(show_spinner=False)
def _load() -> list[dict]:
    return load_datasets()


@st.cache_resource(show_spinner=False)
def _index():
    return build_embeddings()


@st.cache_data(show_spinner=False)
def _briefs() -> dict:
    return load_cached_briefs()


DATASETS = _load()
CACHED = _briefs()

# Top metrics ---------------------------------------------------------------
m1, m2, m3, m4, m5 = st.columns(5)
n_total = len(DATASETS)
n_agencies = len({d["agency"] for d in DATASETS})
n_geo = sum(1 for d in DATASETS if d["format"].upper() in {"GEOTIFF", "SHP", "GEOJSON", "NETCDF", "HDF5"})
n_api = sum(1 for d in DATASETS if d["format"].upper() == "API")
n_recent = sum(1 for d in DATASETS if d["last_updated"] >= "2025-01-01")

m1.markdown(f'<div class="og-card"><div class="og-metric">{n_total}</div><div class="og-metric-label">Datasets Indexed</div></div>', unsafe_allow_html=True)
m2.markdown(f'<div class="og-card"><div class="og-metric">{n_agencies}</div><div class="og-metric-label">Agencies</div></div>', unsafe_allow_html=True)
m3.markdown(f'<div class="og-card"><div class="og-metric">{n_geo}</div><div class="og-metric-label">Geospatial</div></div>', unsafe_allow_html=True)
m4.markdown(f'<div class="og-card"><div class="og-metric">{n_api}</div><div class="og-metric-label">Live APIs</div></div>', unsafe_allow_html=True)
m5.markdown(f'<div class="og-card"><div class="og-metric">{n_recent}</div><div class="og-metric-label">Refreshed in 2025+</div></div>', unsafe_allow_html=True)

st.markdown("&nbsp;")

# Query bar -----------------------------------------------------------------
EXAMPLES = [
    ("indo_pacific_ports",
     "I need datasets relevant to Pacific port congestion and contested logistics in the Indo-Pacific. Specifically: container throughput, vessel call timing, host-nation infrastructure, and weather climatology that would slow MPF offload windows."),
    ("haadr_typhoon",
     "Pull datasets supporting a humanitarian-assistance and disaster-response cell standing up in the Western Pacific typhoon corridor. We need population, shelter capacity, prior disaster claims, real-time storm tracks, and search-and-rescue history."),
    ("pnt_alt",
     "Find federal datasets that could anchor an alternative-PNT or GPS-denied navigation feasibility study. Magnetic-field, high-resolution elevation, hydrography, and any signals-of-opportunity catalogs would all be candidates."),
]

if "query" not in st.session_state:
    st.session_state.query = EXAMPLES[0][1]
    st.session_state.scenario_id = EXAMPLES[0][0]

c_q, c_btn = st.columns([5, 1])
with c_q:
    q = st.text_area(
        "Analyst question",
        value=st.session_state.query,
        height=110,
        label_visibility="collapsed",
    )
with c_btn:
    st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)
    run_clicked = st.button("Search Catalog", use_container_width=True, type="primary")
    hero_mode = st.toggle("Hero brief", value=False,
                          help="Use the Kamiwaza-deployed hero model for the Analyst Discovery Brief")

with st.expander("Sample analyst queries", expanded=False):
    for sid, ex in EXAMPLES:
        if st.button(f"-> {ex[:90]}...", key=f"ex_{sid}"):
            st.session_state.query = ex
            st.session_state.scenario_id = sid
            st.rerun()

# Cached brief shortcut ------------------------------------------------------
def _detect_cached_id(query_text: str) -> str | None:
    for sid, ex in EXAMPLES:
        if query_text.strip() == ex.strip():
            return sid
    return None


def _run_pipeline(query_text: str, force_live: bool = False) -> dict:
    cached_id = _detect_cached_id(query_text)
    if cached_id and not force_live and cached_id in CACHED and "error" not in CACHED[cached_id]:
        c = CACHED[cached_id]
        # Reconstruct ranked records by id (fast path)
        by_id = {d["dataset_id"]: d for d in DATASETS}
        ranked = [by_id[i] for i in c.get("ranked_ids", []) if i in by_id]
        return {
            "filters": c.get("filters", {}),
            "candidate_count": len(ranked),
            "ranked": ranked,
            "comparison": c.get("comparison", {}),
            "brief": c.get("brief", ""),
            "from_cache": True,
        }
    # Live path
    result = retrieve(query_text, k=8)
    comp = comparison_json(query_text, result["ranked"]) if result["ranked"] else {"comparison": []}
    brief = hero_brief(query_text, result["ranked"], comp, use_hero_model=hero_mode)
    result["comparison"] = comp
    result["brief"] = brief
    result["from_cache"] = False
    return result


# Run -----------------------------------------------------------------------
if run_clicked or "result" not in st.session_state:
    if not q.strip():
        st.warning("Enter an analyst question.")
        st.stop()
    with st.status("Production-shape RAG over the federal catalog...", expanded=True) as status:
        st.write("- Parsing analyst intent -> structured filter (agencies, topics, recency)")
        st.write("- Loading embedding index (200 dataset abstracts, cosine-normalized)")
        _ = _index()
        st.write("- Applying agency / format / date / keyword filters")
        st.write("- Vector cosine rerank over the candidate set")
        result = _run_pipeline(q)
        st.session_state.result = result
        st.session_state.query = q
        st.write(f"- Retrieved {len(result['ranked'])} top candidates "
                 f"({result.get('candidate_count', 0)} hard-filter passes)"
                 + (" [cached brief]" if result.get("from_cache") else ""))
        status.update(label="Discovery complete.", state="complete", expanded=False)


result = st.session_state.result
ranked = result.get("ranked", [])
filters = result.get("filters", {})
comparison = result.get("comparison", {})
brief_text = result.get("brief", "")

with st.expander("Parsed filters (LLM-structured)", expanded=False):
    st.json(filters)

if not ranked:
    st.error("No datasets matched even after relaxing filters. Try a broader query.")
    st.stop()

# Layout: ranked candidates left, comparison right
left, right = st.columns([1.0, 1.1])

with left:
    st.markdown("##### Top candidates (vector-reranked)")
    df = pd.DataFrame([
        {
            "Rank": i + 1,
            "Dataset": r["title"],
            "Agency": r["agency"],
            "Format": r["format"],
            "Updated": r["last_updated"],
            "Records (est.)": f'{r["record_count_estimate"]:,}',
            "Cadence": r["refresh_cadence"],
            "Sim": r.get("similarity", 0.0),
        }
        for i, r in enumerate(ranked)
    ])
    st.dataframe(df, hide_index=True, use_container_width=True, height=520)

with right:
    st.markdown("##### Analyst comparison (LLM-structured JSON)")
    rows = comparison.get("comparison", []) if isinstance(comparison, dict) else []
    if rows:
        cdf = pd.DataFrame([
            {
                "Dataset": r.get("title"),
                "Agency": r.get("agency"),
                "Score": r.get("relevance_score"),
                "Why relevant": r.get("why_relevant"),
                "Suggested use": r.get("suggested_use"),
                "Freshness": r.get("freshness_concern"),
            }
            for r in rows
        ])
        st.dataframe(cdf, hide_index=True, use_container_width=True, height=520)
    else:
        st.info("No comparison rows returned.")

# Analyst Discovery Brief ----------------------------------------------------
st.markdown("---")
st.markdown("##### Analyst Discovery Brief (hero call, cache-first)")

c_b1, c_b2 = st.columns([1, 5])
with c_b1:
    regen = st.button("Regenerate", help="Re-run the hero brief live (35s watchdog)")

if regen:
    with st.spinner("Running hero LLM call (35 s watchdog)..."):
        new = _run_pipeline(st.session_state.query, force_live=True)
        st.session_state.result = new
        result = new
        brief_text = new.get("brief", "")

if not brief_text:
    brief_text = baseline_brief(st.session_state.query, ranked, comparison)

# Render
def _md_to_safe_html(text: str) -> str:
    # very light: only **bold** + newlines
    out = []
    for line in text.split("\n"):
        line = line.strip()
        # bold
        while "**" in line:
            line = line.replace("**", "<strong>", 1)
            line = line.replace("**", "</strong>", 1)
        out.append(line)
    return "<br>".join(out)


st.markdown(
    f'<div class="og-brief">{_md_to_safe_html(brief_text)}</div>',
    unsafe_allow_html=True,
)

if result.get("from_cache"):
    st.caption("Brief served from data/cached_briefs.json (cache-first hero pattern). Click Regenerate for a live call.")

# Footer --------------------------------------------------------------------
endpoint = os.getenv("KAMIWAZA_BASE_URL") or "Kamiwaza-deployed model (env-var swap to KAMIWAZA_BASE_URL)"
st.markdown(
    f'<div class="og-footer">'
    f'<span>Powered by Kamiwaza</span> &nbsp;-&nbsp; '
    f'Inference endpoint: <code>{endpoint}</code> &nbsp;-&nbsp; '
    f'Synthetic stand-in for the data.gov federal-dataset catalog (CKAN, 300k+ packages)'
    f'</div>',
    unsafe_allow_html=True,
)
