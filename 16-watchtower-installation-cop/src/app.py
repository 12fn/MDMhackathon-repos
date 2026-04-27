"""WATCHTOWER — Streamlit frontend on port 3016.

Installation Common Operating Picture (I-COP) Aggregator. A multi-tab
dashboard for the installation commander's watch officer:

  Overview      — KPIs + map + alert ticker
  Streams       — per-stream tables (gate, utility, EMS, mass-notify, weather)
  Correlations  — cross-stream anomaly cards (hero AI move)
  Brief         — Commander's I-COP Brief (cache-first hero)
"""
from __future__ import annotations

import json
import math
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import folium
import pandas as pd
import requests
import streamlit as st
from streamlit_folium import st_folium

ROOT = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(ROOT))

from shared.kamiwaza_client import BRAND  # noqa: E402

# In-process fallback so the demo never dies if the backend hiccups.
try:
    from src.correlator import (  # noqa: E402
        correlate_streams, commander_brief, baseline_correlation, baseline_brief,
    )
except ImportError:
    sys.path.insert(0, str(Path(__file__).parent))
    from correlator import (  # type: ignore  # noqa: E402
        correlate_streams, commander_brief, baseline_correlation, baseline_brief,
    )

BACKEND = os.getenv("WATCHTOWER_BACKEND_URL", "http://localhost:8016")
DATA = Path(__file__).resolve().parent.parent / "data"

# ---------------------------------------------------------------------------
# Page config + brand styling
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="WATCHTOWER — Installation Common Operating Picture",
    page_icon="◆",
    layout="wide",
    initial_sidebar_state="expanded",
)

CSS = f"""
<style>
.stApp {{ background-color: {BRAND['bg']}; color: #E5E5E5; }}
section[data-testid="stSidebar"] {{ background-color: {BRAND['surface']}; border-right: 1px solid {BRAND['border']}; }}
.block-container {{ padding-top: 1rem; padding-bottom: 1rem; max-width: 1500px; }}
h1, h2, h3, h4 {{ color: {BRAND['neon']}; }}
.brand-bar {{ display: flex; align-items: center; justify-content: space-between; padding: 8px 14px;
              background: linear-gradient(90deg, #0E0E0E 0%, #111111 60%, #0E0E0E 100%);
              border: 1px solid {BRAND['border']}; border-radius: 8px; margin-bottom: 10px; }}
.brand-left {{ display: flex; align-items: center; gap: 14px; }}
.brand-left img {{ height: 28px; }}
.brand-title {{ color: {BRAND['neon']}; font-weight: 700; letter-spacing: 1px; }}
.brand-tag {{ color: {BRAND['muted']}; font-size: 12px; }}
.kpi {{ display: inline-block; margin-right: 22px; }}
.kpi .v {{ color: {BRAND['neon']}; font-weight: 700; font-size: 22px; }}
.kpi .l {{ color: {BRAND['muted']}; font-size: 11px; text-transform: uppercase; letter-spacing: 1px; }}
.section-card {{ background: {BRAND['surface']}; border: 1px solid {BRAND['border']};
                 border-radius: 8px; padding: 12px 14px; margin-bottom: 10px; }}
.kamiwaza-footer {{ text-align: center; color: {BRAND['muted']}; font-size: 12px;
                    padding: 12px 0; border-top: 1px solid {BRAND['border']}; margin-top: 16px; }}
.stream-chip {{ display: inline-block; padding: 8px 12px; border-radius: 8px;
                font-weight: 700; font-size: 12px; border: 1px solid {BRAND['border']};
                margin: 4px 6px 4px 0; min-width: 168px; background: {BRAND['surface_high']};
                color: #E5E5E5; }}
.stream-chip .name {{ display: block; font-size: 11px; color: {BRAND['muted']}; letter-spacing: 1px; }}
.stream-chip .v {{ display: block; font-size: 16px; color: {BRAND['neon']}; font-weight: 800; }}
.stream-chip .a {{ display: block; font-size: 11px; color: #ff7a3b; }}
.anomaly-card {{ background: {BRAND['surface_high']}; border: 1px solid {BRAND['border']};
                 border-left: 5px solid #ff3b3b; border-radius: 6px; padding: 12px 14px;
                 margin-bottom: 10px; }}
.anomaly-card.MEDIUM {{ border-left-color: #ff9a3b; }}
.anomaly-card.LOW    {{ border-left-color: #ffe23b; }}
.anomaly-card .id {{ color: {BRAND['neon']}; font-weight: 700; letter-spacing: 1px; font-size: 13px; }}
.anomaly-card .sev {{ float: right; font-weight: 800; padding: 1px 8px; border-radius: 4px;
                      font-size: 12px; }}
.anomaly-card .sev.HIGH   {{ background: #4a0d0d; color: #ffd6d6; }}
.anomaly-card .sev.MEDIUM {{ background: #4a2c0d; color: #ffe6c8; }}
.anomaly-card .sev.LOW    {{ background: #4a4a0d; color: #fff7c8; }}
.anomaly-card .streams span {{ display: inline-block; margin-right: 6px;
                               background: {BRAND['surface']}; color: {BRAND['neon']};
                               border: 1px solid {BRAND['border']}; padding: 2px 8px;
                               border-radius: 10px; font-size: 11px; }}
.anomaly-card .hyp {{ margin-top: 6px; color: #E5E5E5; font-size: 14px; line-height: 1.45; }}
.anomaly-card .act {{ margin-top: 8px; color: {BRAND['neon']}; font-size: 13px; font-weight: 600; }}
.brief-box {{ background: {BRAND['surface_high']}; border: 1px solid {BRAND['border']};
              border-radius: 6px; padding: 14px; }}
.brief-box pre {{ background: transparent; color: #E5E5E5; white-space: pre-wrap;
                  font-family: ui-monospace, SFMono-Regular, monospace; font-size: 13px;
                  margin: 0; line-height: 1.5; }}
.ticker {{ display: flex; gap: 12px; overflow: hidden; padding: 8px 0; }}
.ticker .item {{ background: {BRAND['surface_high']}; border: 1px solid {BRAND['border']};
                 border-radius: 6px; padding: 6px 10px; font-size: 12px; color: #E5E5E5;
                 white-space: nowrap; }}
.ticker .item.anom {{ border-color: #ff3b3b; color: #ffd6d6; }}
button[kind="primary"] {{ background-color: {BRAND['primary']} !important; color: #001b10 !important; }}
</style>
"""
st.markdown(CSS, unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Brand bar
# ---------------------------------------------------------------------------
st.markdown(
    f"""
<div class="brand-bar">
  <div class="brand-left">
    <img src="{BRAND['logo_url']}" alt="Kamiwaza"/>
    <div>
      <div class="brand-title">WATCHTOWER</div>
      <div class="brand-tag">Installation Common Operating Picture (I-COP) Aggregator
        :: USMC LOGCOM CDAO published use case
      </div>
    </div>
  </div>
  <div class="brand-tag">From seven disparate installation feeds to one
    cross-stream picture in a single tab.</div>
</div>
""",
    unsafe_allow_html=True,
)


# ---------------------------------------------------------------------------
# Backend-first loaders, file fallback for resilience.
# ---------------------------------------------------------------------------
@st.cache_data(ttl=8)
def get_health() -> dict:
    try:
        return requests.get(f"{BACKEND}/health", timeout=2).json()
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": str(e)}


@st.cache_data(ttl=8)
def _file(name: str):
    return json.loads((DATA / name).read_text())


@st.cache_data(ttl=8)
def get_installation() -> dict:
    try:
        return requests.get(f"{BACKEND}/api/installation", timeout=2).json()
    except Exception:
        return _file("installations.json")[0]


@st.cache_data(ttl=8)
def get_streams_summary() -> list[dict]:
    try:
        return requests.get(f"{BACKEND}/api/streams", timeout=2).json()
    except Exception:
        fused = _file("fused_timeline.json")
        by_stream: dict[str, int] = {}
        anom_by_stream: dict[str, int] = {}
        for r in fused:
            by_stream[r["stream"]] = by_stream.get(r["stream"], 0) + 1
            if r.get("is_anomaly"):
                anom_by_stream[r["stream"]] = anom_by_stream.get(r["stream"], 0) + 1
        return [
            {"stream": s, "count": c, "anomalies": anom_by_stream.get(s, 0)}
            for s, c in sorted(by_stream.items())
        ]


@st.cache_data(ttl=8)
def get_timeline() -> list[dict]:
    try:
        return requests.get(f"{BACKEND}/api/timeline", timeout=3).json()
    except Exception:
        return _file("fused_timeline.json")


@st.cache_data(ttl=8)
def get_stream(name: str) -> list[dict]:
    try:
        return requests.get(f"{BACKEND}/api/stream/{name}", timeout=3).json()
    except Exception:
        fname = {
            "gate": "gate_events.json",
            "utility": "utility_events.json",
            "ems": "ems_events.json",
            "massnotify": "massnotify_events.json",
            "weather": "weather.json",
            "maintenance": "maintenance.json",
        }[name]
        return _file(fname)


@st.cache_data(ttl=8)
def get_cached_briefs() -> dict:
    try:
        return requests.get(f"{BACKEND}/api/cached", timeout=3).json()
    except Exception:
        try:
            return _file("cached_briefs.json")
        except Exception:
            inst = get_installation()
            fused = get_timeline()
            corr = baseline_correlation(fused)
            brief = baseline_brief(inst["name"], fused[-1]["ts_iso"] if fused else "", corr)
            return {
                "as_of_iso": fused[-1]["ts_iso"] if fused else "",
                "installation": {"id": inst["id"], "name": inst["name"], "centroid": inst["centroid"]},
                "baseline_correlation": corr,
                "baseline_brief": brief,
                "live_correlation": None,
                "live_brief": None,
            }


def post_correlate(use_cache: bool = True) -> dict:
    try:
        r = requests.post(f"{BACKEND}/api/correlate",
                          json={"use_cache": use_cache}, timeout=30)
        r.raise_for_status()
        return r.json()
    except Exception:
        inst = get_installation()
        fused = get_timeline()
        as_of = fused[-1]["ts_iso"] if fused else ""
        if use_cache:
            cb = get_cached_briefs()
            live = cb.get("live_correlation")
            if live:
                live["_source"] = live.get("_source", "cached_live")
                return live
            bc = cb.get("baseline_correlation") or baseline_correlation(fused)
            bc["_source"] = bc.get("_source", "cached_baseline")
            return bc
        return correlate_streams(inst["name"], as_of, fused)


def post_brief(correlation: dict | None = None, use_cache: bool = True) -> dict:
    try:
        r = requests.post(f"{BACKEND}/api/brief",
                          json={"use_cache": use_cache, "correlation": correlation},
                          timeout=45)
        r.raise_for_status()
        return r.json()
    except Exception:
        inst = get_installation()
        fused = get_timeline()
        as_of = fused[-1]["ts_iso"] if fused else ""
        if use_cache:
            cb = get_cached_briefs()
            live = cb.get("live_brief")
            if live and live.strip():
                return {"brief": live, "source": "cached_live"}
            return {"brief": cb.get("baseline_brief", ""), "source": "cached_baseline"}
        corr = correlation or correlate_streams(inst["name"], as_of, fused)
        return {"brief": commander_brief(inst["name"], as_of, corr), "source": "live"}


# ---------------------------------------------------------------------------
# Sidebar controls
# ---------------------------------------------------------------------------
with st.sidebar:
    st.markdown("### Operator Controls")
    use_cache = st.checkbox(
        "Cache-first hero outputs",
        True,
        help=(
            "On. Reads pre-computed correlation + brief from data/cached_briefs.json "
            "(snappy demo). Off issues a live AI call (timeout-bounded with "
            "deterministic fallback)."
        ),
    )
    show_anom_only = st.checkbox("Show flagged anomalies only", False)
    st.markdown("---")
    st.markdown("### Backend")
    h = get_health()
    if h.get("ok"):
        st.success(
            f"OK :: AI engine — Kamiwaza-deployed\n\n"
            f"Endpoint: `{h.get('kamiwaza_endpoint')}`"
        )
    else:
        st.warning(
            f"Backend unreachable; using in-process compute.\n\n{h.get('error','')}"
        )
    st.markdown("---")
    st.markdown(
        f"<div class='brand-tag'>Models route through your Kamiwaza-deployed "
        f"endpoint. Set <code>KAMIWAZA_BASE_URL</code> to keep all traffic "
        f"inside your wire.</div>",
        unsafe_allow_html=True,
    )


# ---------------------------------------------------------------------------
# Pull data
# ---------------------------------------------------------------------------
inst = get_installation()
streams_summary = get_streams_summary()
fused = get_timeline()
cached = get_cached_briefs()

# KPI strip
total_events = sum(s["count"] for s in streams_summary)
total_anoms = sum(s["anomalies"] for s in streams_summary)
n_streams = len(streams_summary)

st.markdown(
    f"""
<div class="section-card">
  <span class="kpi"><span class="v">{inst['name']}</span><span class="l">Installation</span></span>
  <span class="kpi"><span class="v">{n_streams}</span><span class="l">Live Feeds</span></span>
  <span class="kpi"><span class="v">{total_events}</span><span class="l">Fused Events / 24h</span></span>
  <span class="kpi"><span class="v" style="color:#ff3b3b">{total_anoms}</span><span class="l">Cross-Stream Flags</span></span>
  <span class="kpi"><span class="v">{cached.get('as_of_iso','')[:16].replace('T',' ')}</span><span class="l">As Of (UTC)</span></span>
</div>
""",
    unsafe_allow_html=True,
)

# Stream chips strip
chips_html = ['<div style="margin: 6px 0 14px 0;">']
icon = {"gate": "GATE", "utility": "UTIL", "ems": "EMS",
        "massnotify": "ATHOC", "weather": "WX", "maintenance": "GCSS"}
for s in streams_summary:
    a = s["anomalies"]
    chips_html.append(
        f'<div class="stream-chip">'
        f'<span class="name">{icon.get(s["stream"], s["stream"]).upper()}</span>'
        f'<span class="v">{s["count"]}</span>'
        f'<span class="a">{a} flagged</span>'
        f'</div>'
    )
chips_html.append("</div>")
st.markdown("\n".join(chips_html), unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Tabs
# ---------------------------------------------------------------------------
tab_overview, tab_streams, tab_corr, tab_brief = st.tabs(
    ["Overview", "Streams", "Correlations", "Commander's Brief"]
)


# ---------------------------------------------------------------------------
# OVERVIEW
# ---------------------------------------------------------------------------
with tab_overview:
    left, right = st.columns([2, 1], gap="medium")

    with left:
        st.markdown("#### Common Operating Picture — Installation Map")
        clat, clon = inst["centroid"]
        m = folium.Map(location=[clat, clon], zoom_start=11,
                       tiles="CartoDB dark_matter", control_scale=True)
        # Installation polygon
        poly = inst["polygon"] + [inst["polygon"][0]]
        folium.Polygon(
            locations=poly, color=BRAND["primary"], weight=2,
            fill=True, fill_color=BRAND["primary"], fill_opacity=0.06,
            tooltip=inst["name"],
        ).add_to(m)
        # Gates
        for g in inst.get("gates", []):
            folium.CircleMarker(
                location=[g["lat"], g["lon"]], radius=5,
                color=BRAND["neon"], fill=True, fill_color=BRAND["neon"], fill_opacity=0.85,
                tooltip=f"{g['name']} (gate)",
            ).add_to(m)
        # Utility nodes
        for n in inst.get("utility_nodes", []):
            folium.CircleMarker(
                location=[n["lat"], n["lon"]], radius=5,
                color="#3bb6ff", fill=True, fill_color="#3bb6ff", fill_opacity=0.85,
                tooltip=f"{n['name']} ({n['kind']} node)",
            ).add_to(m)
        # EMS units
        for u in inst.get("ems_units", []):
            folium.CircleMarker(
                location=[u["lat"], u["lon"]], radius=5,
                color="#ff9a3b", fill=True, fill_color="#ff9a3b", fill_opacity=0.85,
                tooltip=f"{u['name']} ({u['type']})",
            ).add_to(m)
        # HIFLD critical infrastructure (squares)
        for ci in inst.get("critical_infrastructure", []):
            folium.RegularPolygonMarker(
                location=[ci["lat"], ci["lon"]],
                number_of_sides=4, radius=6, color="#c39bff",
                fill=True, fill_color="#c39bff", fill_opacity=0.85,
                tooltip=f"HIFLD :: {ci['kind']} :: {ci['name']}",
            ).add_to(m)
        # Plot the active anomalies (red x)
        for f in fused:
            if not f.get("is_anomaly"):
                continue
            if f.get("lat") is None or f.get("lon") is None:
                continue
            folium.CircleMarker(
                location=[f["lat"], f["lon"]], radius=8,
                color="#ff3b3b", weight=2, fill=False,
                tooltip=f"[{f['stream'].upper()}] {f.get('label','')}",
            ).add_to(m)

        st_folium(m, height=560, width=None, returned_objects=[], key="cop")

    with right:
        st.markdown("#### Live Anomaly Ticker")
        anom = [f for f in fused if f.get("is_anomaly")]
        anom = sorted(anom, key=lambda r: r["ts_iso"], reverse=True)[:18]
        if not anom:
            st.info("No anomalies in the last 24h.")
        for a in anom:
            st.markdown(
                f"<div class='ticker'><div class='item anom'>"
                f"<b>{a['ts_iso'][11:16]}Z</b> "
                f"<span style='color:#00FFA7'>[{a['stream'].upper()}]</span> "
                f"{a.get('label','')[:120]}"
                f"</div></div>",
                unsafe_allow_html=True,
            )

        st.markdown("---")
        st.markdown("#### HIFLD-shape Critical Infrastructure")
        ci = inst.get("critical_infrastructure", [])
        if ci:
            df = pd.DataFrame(ci)[["kind", "name", "owner", "status"]]
            st.dataframe(df, use_container_width=True, height=240, hide_index=True)


# ---------------------------------------------------------------------------
# STREAMS
# ---------------------------------------------------------------------------
with tab_streams:
    st.markdown("#### Per-Stream Drill-Down")
    pick = st.selectbox(
        "Stream",
        ["gate", "utility", "ems", "massnotify", "weather", "maintenance"],
        format_func=lambda s: {
            "gate": "Gate ingress / egress (DBIDS-shape)",
            "utility": "Utility readings (DPW SCADA-shape)",
            "ems": "Fire / EMS dispatches (CAD-shape)",
            "massnotify": "Mass notification (AtHoc / Giant Voice)",
            "weather": "Weather (NASA Earthdata-shape)",
            "maintenance": "Maintenance (GCSS-MC-shape)",
        }[s],
    )
    rows = get_stream(pick)
    if show_anom_only and pick not in ("weather", "maintenance"):
        rows = [r for r in rows if r.get("is_anomaly")]
    if not rows:
        st.info("No records.")
    else:
        df = pd.DataFrame(rows)
        # Hide noisy cols
        for col in ("source_system", "is_anomaly"):
            if col in df.columns and pick != "ems":
                pass
        st.dataframe(df, use_container_width=True, height=520, hide_index=True)
        st.caption(
            f"{len(rows)} records :: "
            + ("flagged-only" if show_anom_only else "full window")
        )


# ---------------------------------------------------------------------------
# CORRELATIONS
# ---------------------------------------------------------------------------
with tab_corr:
    st.markdown("#### Cross-Stream Anomaly Correlator")
    st.caption(
        "Hero AI move: the correlator consumes the last 24h of fused events "
        "and emits anomalies that are corroborated across multiple streams "
        "in the same time window. Cache-first by default — uncheck the "
        "sidebar control to fire the live call."
    )
    col_run, col_meta = st.columns([1, 3])
    with col_run:
        rerun = st.button("Run correlator", type="primary",
                          use_container_width=True, key="run-corr")
    if rerun or "last_corr" not in st.session_state:
        with st.spinner("Cross-stream correlation in flight..."):
            corr = post_correlate(use_cache=use_cache)
        st.session_state["last_corr"] = corr
    corr = st.session_state["last_corr"]
    src = corr.get("_source", "?")
    with col_meta:
        st.markdown(
            f"<div class='brand-tag'>Source: <code>{src}</code> :: "
            f"{len(corr.get('anomalies',[]))} cross-stream anomalies</div>",
            unsafe_allow_html=True,
        )

    for a in corr.get("anomalies", []):
        sev = a.get("severity", "MEDIUM")
        streams_html = "".join(
            f"<span>{s.upper()}</span>" for s in a.get("contributing_streams", [])
        )
        st.markdown(
            f"""
<div class="anomaly-card {sev}">
  <span class="id">{a.get('anomaly_id','?')}</span>
  <span class="sev {sev}">{sev}</span>
  <div class="streams">{streams_html}</div>
  <div class="hyp">{a.get('hypothesis','')}</div>
  <div class="act">RECOMMENDED: {a.get('recommended_action','')}</div>
</div>
""",
            unsafe_allow_html=True,
        )

    with st.expander("Raw JSON (verifies structured-output JSON-mode)"):
        st.json(corr)


# ---------------------------------------------------------------------------
# COMMANDER'S BRIEF
# ---------------------------------------------------------------------------
with tab_brief:
    st.markdown("#### Commander's I-COP Brief")
    st.caption(
        "Hero call. Cache-first reads pre-computed text from data/cached_briefs.json. "
        "Live mode invokes the hero model (35s timeout, deterministic fallback)."
    )
    col_run, col_meta = st.columns([1, 3])
    with col_run:
        gen = st.button("Generate brief", type="primary",
                        use_container_width=True, key="run-brief")
    if gen or "last_brief" not in st.session_state:
        with st.spinner("Drafting Commander's I-COP Brief..."):
            corr = st.session_state.get("last_corr") or post_correlate(use_cache=use_cache)
            br = post_brief(correlation=corr, use_cache=use_cache)
        st.session_state["last_brief"] = br
    br = st.session_state["last_brief"]
    with col_meta:
        st.markdown(
            f"<div class='brand-tag'>Source: <code>{br.get('source','?')}</code> :: "
            f"{len(br.get('brief',''))} chars</div>",
            unsafe_allow_html=True,
        )
    st.markdown(
        f"<div class='brief-box'><pre>{br.get('brief','')}</pre></div>",
        unsafe_allow_html=True,
    )


# ---------------------------------------------------------------------------
# Footer
# ---------------------------------------------------------------------------
st.markdown(
    f"<div class='kamiwaza-footer'>{BRAND['footer']}  ::  "
    f"HIFLD + NASA Earthdata + GCSS-MC :: same code, "
    f"<code>KAMIWAZA_BASE_URL</code> swap = on-prem in one env-var</div>",
    unsafe_allow_html=True,
)
