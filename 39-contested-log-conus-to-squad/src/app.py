"""CONTESTED-LOG Streamlit UI — port 3039.

Mega-app: end-to-end CONUS-to-squad in contested INDOPACOM AOR.
PyDeck dark theatre map (full Pacific) + Plotly Gantt timeline +
Folium pirate-KDE overlay + live agent reasoning sidebar.

Run with:
    cd apps/39-contested-log
    streamlit run src/app.py --server.port 3039 --server.headless true \\
      --server.runOnSave false --server.fileWatcherType none \\
      --browser.gatherUsageStats false
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

# Make `shared` and `src` importable from any cwd.
APP_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = APP_ROOT.parents[1]
for p in (str(REPO_ROOT), str(APP_ROOT)):
    if p not in sys.path:
        sys.path.insert(0, p)

import pandas as pd
import plotly.express as px
import pydeck as pdk
import streamlit as st

from shared.kamiwaza_client import BRAND  # noqa: E402

from src.agent import stream_run, _deterministic_brief  # noqa: E402
from src.tools import (  # noqa: E402
    load_bts_nodes, load_ports, load_squads, load_disruptions,
    load_depot_stocks, load_lanes, compare_options,
)
from src.kde import hotspots, basin_lookup_risk  # noqa: E402

DATA_DIR = APP_ROOT / "data"


# ──────────────────────────────────────────────────────────────────────────────
# Page config
# ──────────────────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="CONTESTED-LOG — Contested Sustainment Planning",
    page_icon="◆",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ──────────────────────────────────────────────────────────────────────────────
# Theme — Kamiwaza dark
# ──────────────────────────────────────────────────────────────────────────────
st.markdown(f"""
<style>
  html, body, [data-testid="stAppViewContainer"], [data-testid="stHeader"] {{
    background-color: {BRAND['bg']} !important;
    color: #E8E8E8 !important;
  }}
  [data-testid="stSidebar"] {{
    background-color: {BRAND['surface']} !important;
    border-right: 1px solid {BRAND['border']};
  }}
  h1, h2, h3, h4 {{ color: #FFFFFF !important; letter-spacing: .04em; }}
  .cl-tagline {{
    color: {BRAND['neon']}; font-family: Helvetica, Arial, sans-serif;
    font-weight: 600; letter-spacing: 1.2px; text-transform: uppercase;
    font-size: 11px;
  }}
  .cl-headline {{
    color: #FFFFFF; font-family: Helvetica, Arial, sans-serif;
    font-weight: 700; font-size: 26px; line-height: 1.1; margin-top: 4px;
  }}
  .cl-card {{
    background: {BRAND['surface_high']}; border: 1px solid {BRAND['border']};
    border-radius: 8px; padding: 14px 18px; margin-bottom: 10px;
  }}
  .cl-rec {{
    border-color: {BRAND['neon']} !important;
    box-shadow: 0 0 0 1px {BRAND['neon']};
  }}
  .cl-pill {{
    display:inline-block; padding:3px 10px; border-radius:999px;
    font-size:11px; font-weight:700; letter-spacing:.6px; margin-right:6px;
  }}
  .pill-go    {{ background:#0E2F22; color:#00FFA7; border:1px solid #00BB7A; }}
  .pill-cau   {{ background:#3A2C0E; color:#E0B341; border:1px solid #E0B341; }}
  .pill-no    {{ background:#3A0E0E; color:#FF6F66; border:1px solid #D8362F; }}
  .pill-mode  {{ background:#0E0E0E; color:#FFFFFF; border:1px solid #333333; }}
  .stButton > button {{
    background: {BRAND['primary']}; color:#0A0A0A; border:0;
    font-weight:700; letter-spacing:.6px;
  }}
  .stButton > button:hover {{ background: {BRAND['primary_hover']}; color:#0A0A0A; }}
  .cl-trace-call {{
    color: {BRAND['neon']}; font-family: ui-monospace, Menlo, monospace;
    font-size: 12px; padding: 2px 0;
  }}
  .cl-trace-result {{
    color: #B8B8B8; font-family: ui-monospace, Menlo, monospace;
    font-size: 11px; white-space: pre-wrap; padding-left: 14px;
  }}
  .cl-footer {{
    color:{BRAND['muted']}; text-align:center; margin-top:30px;
    padding:14px; border-top:1px solid {BRAND['border']};
    font-size:12px; letter-spacing:1.2px; text-transform:uppercase;
  }}
  div[data-testid="stMetricValue"] {{ color: {BRAND['neon']} !important; }}
</style>
""", unsafe_allow_html=True)


# ──────────────────────────────────────────────────────────────────────────────
# Cached loaders
# ──────────────────────────────────────────────────────────────────────────────
@st.cache_data(show_spinner=False)
def _bts_nodes(): return load_bts_nodes()
@st.cache_data(show_spinner=False)
def _ports(): return load_ports()
@st.cache_data(show_spinner=False)
def _squads(): return load_squads()
@st.cache_data(show_spinner=False)
def _disruptions(): return load_disruptions()
@st.cache_data(show_spinner=False)
def _stocks(): return load_depot_stocks()
@st.cache_data(show_spinner=False)
def _lanes(): return load_lanes()
@st.cache_data(show_spinner=False)
def _hotspots(): return hotspots(8)


@st.cache_data(show_spinner=False)
def _cached_briefs() -> dict:
    p = DATA_DIR / "cached_briefs.json"
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text())
    except Exception:
        return {}


# ──────────────────────────────────────────────────────────────────────────────
# Session state
# ──────────────────────────────────────────────────────────────────────────────
if "events" not in st.session_state:
    st.session_state.events = []
    st.session_state.final = ""
    st.session_state.compare_result = None
    st.session_state.brief_source = "—"


# ──────────────────────────────────────────────────────────────────────────────
# Sidebar — agent reasoning + scenario picker
# ──────────────────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown(
        f"<div class='cl-tagline'>{BRAND['footer']}</div>"
        f"<div class='cl-headline'>CONTESTED-LOG</div>"
        f"<div style='color:{BRAND['text_dim']};font-size:11px;margin-top:6px;'>"
        "End-to-end CONUS-to-squad sustainment<br/>in a contested INDOPACOM AOR"
        "</div>",
        unsafe_allow_html=True,
    )
    st.markdown("---")
    st.markdown("**MISSION FRAME**")
    st.markdown(
        "<span style='color:#9A9A9A;font-size:11px;'>"
        "Force Design 2030. INDOPACOM contested. Single sustainment plan must "
        "fuse 8 datasets — BTS NTAD, MSI WPI, AIS, ASAM piracy, AFCENT, GCSS-MC, "
        "LaDe, SC disruption — to push pallets from depot to squad inside "
        "a closing 14-day window."
        "</span>",
        unsafe_allow_html=True,
    )
    st.markdown("---")
    st.markdown("### <span style='color:#00FFA7'>Agent Reasoning</span>",
                unsafe_allow_html=True)
    st.markdown(
        f"<div style='color:{BRAND['text_dim']};font-size:11px;'>"
        "Live tool-calling trace — Kamiwaza-deployed model fires "
        "<code>route_conus()</code>, <code>check_port_capacity()</code>, "
        "<code>forecast_pirate_risk()</code>, "
        "<code>check_supply_chain_disruption()</code>, "
        "<code>compute_last_mile()</code>, <code>compare_options()</code>."
        "</div>",
        unsafe_allow_html=True,
    )
    trace_slot = st.empty()


def _render_trace(events: list[dict]):
    parts = []
    for ev in events:
        if ev["type"] == "user":
            parts.append(f"<div style='color:{BRAND['text_dim']};margin:6px 0;'>"
                         f"USER &gt; {ev['content'][:220]}</div>")
        elif ev["type"] == "model_message":
            if ev["content"].strip():
                parts.append(
                    f"<div style='color:#CFCFCF;margin:6px 0;font-style:italic;font-size:11px;'>"
                    f"thinking &gt; {ev['content'][:280]}</div>")
        elif ev["type"] == "tool_call":
            args = json.dumps(ev["arguments"], separators=(",", ":"))[:160]
            parts.append(f"<div class='cl-trace-call'>→ {ev['name']}({args})</div>")
        elif ev["type"] == "tool_result":
            r = ev["result"]
            if isinstance(r, dict):
                if "error" in r:
                    summary = f"error: {str(r['error'])[:80]}"
                elif "options" in r:
                    summary = f"options={len(r['options'])} (recommended set)"
                elif "kde_risk_0_1" in r:
                    summary = f"risk={r['kde_risk_0_1']} basin='{r.get('risk_basin','?')}' verdict={r.get('verdict','?')}"
                elif "legs" in r:
                    summary = f"legs={len(r['legs'])} dist={r.get('total_distance_km') or r.get('total_distance_nm')}"
                elif "pallets_per_day_capacity" in r:
                    summary = f"port={r['port_id']} cap={r['pallets_per_day_capacity']}/d feasible={r['feasible']}"
                elif "events" in r:
                    summary = f"matched={r['matched']} severity={r.get('severity_count')}"
                else:
                    summary = "ok"
            else:
                summary = str(r)[:80]
            parts.append(f"<div class='cl-trace-result'>← {summary} ({ev['ms']} ms)</div>")
        elif ev["type"] == "final":
            parts.append(
                f"<div style='color:{BRAND['neon']};margin-top:8px;"
                f"border-top:1px solid {BRAND['border']};padding-top:6px;font-size:11px;'>"
                f"finish_reason=stop · {len([e for e in events if e['type']=='tool_call'])} tools fired"
                f"</div>")
    trace_slot.markdown("".join(parts), unsafe_allow_html=True)


# ──────────────────────────────────────────────────────────────────────────────
# Header
# ──────────────────────────────────────────────────────────────────────────────
hdr_l, hdr_r = st.columns([0.7, 0.3])
with hdr_l:
    st.markdown(
        f"""
        <div style="display:flex;align-items:center;gap:14px;">
          <img src="{BRAND['logo_url']}" alt="Kamiwaza" style="height:34px;" />
          <div>
            <div style="font-size:28px;font-weight:700;color:{BRAND['neon']};
                        letter-spacing:.06em;">CONTESTED-LOG</div>
            <div style="color:{BRAND['text_dim']};font-size:12px;">
              CONUS to Squad. Eight datasets. One COA. Contested INDOPACOM.
            </div>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
with hdr_r:
    st.markdown(
        f"""
        <div class='cl-card' style='text-align:right;padding:8px 14px;'>
          <span class='cl-pill pill-mode'>INDOPACOM</span>
          <span class='cl-pill pill-go'>TIER A</span>
          <div style='color:{BRAND['muted']};font-size:10px;margin-top:6px;'>
            LOGCOM use cases: TMR Auto · LogTRACE · I-COP
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

# Top metrics — always populated
m1, m2, m3, m4, m5 = st.columns(5)
with m1: st.metric("BTS nodes", f"{len(_bts_nodes())}")
with m2: st.metric("Pacific ports", f"{len(_ports())}")
with m3: st.metric("ASAM attacks", "3,000")
with m4: st.metric("31st MEU squads", f"{len(_squads())}")
with m5: st.metric("Active disruptions",
                   f"{sum(1 for e in _disruptions() if e['active'])}")

st.markdown("---")


# ──────────────────────────────────────────────────────────────────────────────
# Operator input
# ──────────────────────────────────────────────────────────────────────────────
left, right = st.columns([0.55, 0.45], gap="large")
with left:
    st.markdown("#### Operator Sustainment Request")
    default_q = ("Push 200 pallets of MREs from MCLB Albany to the 31st MEU "
                 "at Itbayat by D+14, contested INDOPACOM, lowest pirate-risk.")
    user_msg = st.text_area("Type a sustainment request:",
                            value=default_q, height=110,
                            label_visibility="collapsed")
    examples = [
        "Push 200 pallets of MREs from MCLB Albany to the 31st MEU at Itbayat by D+14, contested INDOPACOM, lowest pirate-risk.",
        "Move 120 pallets of Class IX from MCLB Barstow to Norway forward staging in 21 days, EUCOM cold-weather route.",
        "Bab-el-Mandeb is closed. Reroute 80 pallets of Class I to Camp Lemonnier Djibouti within 30 days via Cape of Good Hope.",
    ]
    pick = st.selectbox("Or pick a cached scenario:", examples, index=0,
                        label_visibility="collapsed")
    c1, c2, c3 = st.columns([0.3, 0.3, 0.4])
    with c1:
        run_btn = st.button("PLAN COA", type="primary", use_container_width=True)
    with c2:
        cached_btn = st.button("Load cached", use_container_width=True)

with right:
    st.markdown("#### Theatre Footprint — Pacific")
    # Quick disruption strip
    active_evs = [e for e in _disruptions() if e["active"]][:5]
    rows = []
    for e in active_evs:
        sev_pill = ("pill-no" if e["severity"] == "HIGH" else
                    "pill-cau" if e["severity"] == "MEDIUM" else "pill-go")
        rows.append(
            f"<div style='font-size:11px;margin:4px 0;'>"
            f"<span class='cl-pill {sev_pill}'>{e['severity']}</span> "
            f"<b>{e['location']}</b> — {e['narrative'][:80]}</div>")
    st.markdown(
        f"<div class='cl-card' style='padding:10px 14px;'>"
        f"<div style='color:{BRAND['neon']};font-size:11px;font-weight:700;"
        f"text-transform:uppercase;'>SC Disruption Feed (active)</div>"
        + "".join(rows) +
        f"</div>",
        unsafe_allow_html=True,
    )

# ──────────────────────────────────────────────────────────────────────────────
# Big PyDeck theatre map
# ──────────────────────────────────────────────────────────────────────────────
st.markdown("#### Pacific Theatre — BTS CONUS · MSI Ports · AIS Lanes · ASAM Hotspots")


def _build_theatre_map(highlight_legs=None, highlight_sealift=None):
    bts = pd.DataFrame(_bts_nodes())
    bts["color"] = bts["kind"].map({
        "depot": [0, 187, 122],
        "port":  [0, 255, 167],
        "rail":  [255, 199, 64],
        "air":   [120, 200, 255],
    })
    ports = pd.DataFrame(_ports())
    ports["color"] = ports["role"].map({
        "POE": [0, 255, 167],
        "FWD": [255, 165, 0],
        "ALY": [120, 200, 255],
        "NEU": [180, 180, 180],
    })
    squads = pd.DataFrame(_squads())
    squads["color"] = squads["priority"].map({
        "URGENT":   [255, 110, 110],
        "PRIORITY": [255, 199, 64],
        "ROUTINE":  [0, 187, 122],
    })
    hs = pd.DataFrame(_hotspots())

    layers = [
        # AIS lanes (always on)
        pdk.Layer(
            "LineLayer",
            data=pd.DataFrame([{
                "from_lon": next((p["lon"] for p in _ports() if p["id"] == ln["from_port"]), 0),
                "from_lat": next((p["lat"] for p in _ports() if p["id"] == ln["from_port"]), 0),
                "to_lon":   next((p["lon"] for p in _ports() if p["id"] == ln["to_port"]),   0),
                "to_lat":   next((p["lat"] for p in _ports() if p["id"] == ln["to_port"]),   0),
            } for ln in _lanes()]),
            get_source_position="[from_lon, from_lat]",
            get_target_position="[to_lon, to_lat]",
            get_color=[80, 110, 130, 110], get_width=1.5,
        ),
        # BTS nodes
        pdk.Layer("ScatterplotLayer", data=bts,
                  get_position="[lon, lat]", get_radius=40000,
                  get_fill_color="color", opacity=0.85, pickable=True),
        # Pacific ports
        pdk.Layer("ScatterplotLayer", data=ports,
                  get_position="[lon, lat]", get_radius=55000,
                  get_fill_color="color", opacity=0.75, pickable=True),
        # 31st MEU squads
        pdk.Layer("ScatterplotLayer", data=squads,
                  get_position="[lon, lat]", get_radius=24000,
                  get_fill_color="color", opacity=0.95, pickable=True),
        # Pirate hotspots — KDE overlay (hex-ish)
        pdk.Layer("ScatterplotLayer", data=hs,
                  get_position="[lon, lat]",
                  get_radius="risk * 350000",
                  get_fill_color=[255, 60, 60, 70],
                  pickable=True),
    ]
    if highlight_legs:
        leg_df = pd.DataFrame([{
            "from_lon": l["from_lon"], "from_lat": l["from_lat"],
            "to_lon": l["to_lon"], "to_lat": l["to_lat"],
            "mode": l.get("mode", "rail"),
        } for l in highlight_legs])
        leg_df["color"] = leg_df["mode"].map({
            "rail":  [0, 255, 167],
            "road":  [255, 199, 64],
            "water": [80, 180, 255],
        }).fillna("[0,255,167]")
        layers.append(pdk.Layer(
            "LineLayer", data=leg_df,
            get_source_position="[from_lon, from_lat]",
            get_target_position="[to_lon, to_lat]",
            get_color="color", get_width=5,
        ))
    if highlight_sealift:
        sl_df = pd.DataFrame([{
            "from_lon": s["from_lon"], "from_lat": s["from_lat"],
            "to_lon":   s["to_lon"],   "to_lat":   s["to_lat"],
        } for s in highlight_sealift])
        layers.append(pdk.Layer(
            "ArcLayer", data=sl_df,
            get_source_position="[from_lon, from_lat]",
            get_target_position="[to_lon, to_lat]",
            get_source_color=[0, 187, 122, 200],
            get_target_color=[0, 255, 167, 200],
            get_width=4,
        ))
    deck = pdk.Deck(
        map_style=None,
        initial_view_state=pdk.ViewState(latitude=18.0, longitude=170.0,
                                         zoom=1.7, pitch=0),
        layers=layers,
        tooltip={"text": "{name} {callsign} {id}"},
    )
    return deck


map_slot = st.empty()
map_slot.pydeck_chart(_build_theatre_map(), use_container_width=True)


# ──────────────────────────────────────────────────────────────────────────────
# COA recommendations
# ──────────────────────────────────────────────────────────────────────────────
st.markdown("---")
st.markdown("#### Contested Sustainment COA — 3-Option Comparison")
result_slot = st.container()
gantt_slot = st.empty()
brief_slot = st.empty()


def _render_coa(comparison: dict):
    if not comparison or "options" not in comparison:
        result_slot.info("Run the agent to populate COA options.")
        return
    opts = comparison["options"]
    cols = result_slot.columns(len(opts))
    rows = []
    for i, (col, opt) in enumerate(zip(cols, opts)):
        rec = opt.get("recommended", False)
        css = "cl-card cl-rec" if rec else "cl-card"
        badge = '<span class="cl-pill pill-go">RECOMMENDED</span>' if rec else ""
        feas = ('<span class="cl-pill pill-go">FEASIBLE</span>'
                if opt["feasible"]
                else '<span class="cl-pill pill-cau">REVIEW</span>')
        risk = opt["avg_pirate_risk_0_1"]
        risk_pill = ('<span class="cl-pill pill-go">PIRATE LOW</span>'
                     if risk < 0.25
                     else '<span class="cl-pill pill-cau">PIRATE MED</span>'
                     if risk < 0.55
                     else '<span class="cl-pill pill-no">PIRATE HIGH</span>')
        col.markdown(
            f"""
            <div class='{css}'>
              <div style='display:flex;justify-content:space-between;align-items:flex-start;'>
                <div style='font-weight:700;font-size:14px;color:{BRAND['neon']};'>
                  {opt['label']}</div>
                <div>{badge}</div>
              </div>
              <div style='color:{BRAND['text_dim']};font-size:11px;margin-bottom:8px;'>
                POE: {opt['poe']} · Forward: {opt['fwd_port']} · Last-mile: {opt['last_mode'].upper()}
              </div>
              <div style='font-size:13px;line-height:1.7;'>
                <b>CONUS:</b> {opt['conus_days']} d<br/>
                <b>Sealift:</b> {opt['sealift_days']} d<br/>
                <b>Total:</b> {opt['total_days']} d / deadline {opt['deadline_days']:.0f} d<br/>
                <b>Avg pirate-risk:</b> {risk}<br/>
                <b>Score:</b> {opt['score']}
              </div>
              <div style='margin-top:8px;'>{feas} {risk_pill}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        rows.append({
            "Option": opt["label"][:40], "POE": opt["poe"],
            "Forward": opt["fwd_port"], "CONUS d": opt["conus_days"],
            "Sealift d": opt["sealift_days"], "Total d": opt["total_days"],
            "Pirate-risk": opt["avg_pirate_risk_0_1"],
            "Feasible": "✓" if opt["feasible"] else "—",
            "Score": opt["score"], "Rec": "★" if opt.get("recommended") else "",
        })
    result_slot.dataframe(pd.DataFrame(rows), use_container_width=True,
                          hide_index=True)
    # Render Gantt
    rec = next((o for o in opts if o.get("recommended")), opts[0])
    _render_gantt(rec)
    # Refresh map with recommended route highlighted
    map_slot.pydeck_chart(
        _build_theatre_map(
            highlight_legs=rec.get("conus_legs", []),
            highlight_sealift=rec.get("sealift_segments", []),
        ),
        use_container_width=True,
    )


def _render_gantt(rec: dict):
    """Plotly Gantt timeline of recommended COA."""
    today = datetime.now()
    bars = []
    cur = today
    bars.append({"task": "CONUS rail (BNSF 286k)",
                 "start": cur, "end": cur + timedelta(days=rec["conus_days"]),
                 "phase": "CONUS"})
    cur += timedelta(days=rec["conus_days"])
    bars.append({"task": f"POE staging — {rec['poe']}",
                 "start": cur, "end": cur + timedelta(days=0.75),
                 "phase": "POE"})
    cur += timedelta(days=0.75)
    bars.append({"task": "Strategic sealift (T-AKE)",
                 "start": cur, "end": cur + timedelta(days=rec["sealift_days"]),
                 "phase": "SEALIFT"})
    cur += timedelta(days=rec["sealift_days"])
    bars.append({"task": f"Forward port — {rec['fwd_port']}",
                 "start": cur, "end": cur + timedelta(days=0.5),
                 "phase": "FWD"})
    cur += timedelta(days=0.5)
    bars.append({"task": "Last-mile push (C-130J → squads)",
                 "start": cur, "end": cur + timedelta(days=0.5),
                 "phase": "LAST-MILE"})
    df = pd.DataFrame(bars)
    fig = px.timeline(df, x_start="start", x_end="end", y="task",
                      color="phase",
                      color_discrete_map={
                          "CONUS": "#00BB7A", "POE": "#0DCC8A",
                          "SEALIFT": "#00FFA7", "FWD": "#E0B341",
                          "LAST-MILE": "#FF6F66",
                      })
    fig.update_yaxes(autorange="reversed")
    fig.update_layout(
        plot_bgcolor=BRAND["bg"], paper_bgcolor=BRAND["bg"],
        font_color="#E8E8E8", title="Recommended COA — End-to-End Timeline",
        height=320, margin=dict(l=10, r=10, t=40, b=20),
        showlegend=True,
    )
    gantt_slot.plotly_chart(fig, use_container_width=True)


# ──────────────────────────────────────────────────────────────────────────────
# Run agent or load cache
# ──────────────────────────────────────────────────────────────────────────────
cache = _cached_briefs()


def _trigger_run(prompt: str):
    st.session_state.events = []
    events: list[dict] = []
    last_compare = None
    with st.spinner("CONTESTED-LOG agent planning end-to-end COA…"):
        try:
            for ev in stream_run(prompt):
                events.append(ev)
                _render_trace(events)
                if (ev["type"] == "tool_result"
                        and ev["name"] == "compare_options"
                        and "error" not in ev["result"]):
                    last_compare = ev["result"]
                if ev["type"] == "final":
                    st.session_state.final = ev["content"]
        except Exception as e:  # noqa: BLE001
            st.error(f"Agent error: {e}")
            st.session_state.final = _deterministic_brief()
    if not last_compare:
        # ensure something rendered even if model didn't call compare_options
        last_compare = compare_options()
    st.session_state.events = events
    st.session_state.compare_result = last_compare
    st.session_state.brief_source = "live"


def _load_cache():
    if cache:
        sid = next(iter(cache))
        blob = cache[sid]
        st.session_state.final = blob.get("final", "")
        st.session_state.events = blob.get("trace", [])
        st.session_state.compare_result = compare_options()
        st.session_state.brief_source = blob.get("cached_from", "cached")
        _render_trace(st.session_state.events)
    else:
        st.warning("No cached briefs on disk. Run `data/generate.py`.")


if run_btn and user_msg.strip():
    _trigger_run(user_msg)
elif cached_btn:
    _load_cache()
elif not st.session_state.compare_result:
    # First load — pre-populate from cache so the app is never empty
    if cache:
        sid = next(iter(cache))
        st.session_state.final = cache[sid].get("final", "")
        st.session_state.events = cache[sid].get("trace", [])
        st.session_state.brief_source = cache[sid].get("cached_from", "cached")
    st.session_state.compare_result = compare_options()
    if st.session_state.events:
        _render_trace(st.session_state.events)


_render_coa(st.session_state.compare_result)


# ──────────────────────────────────────────────────────────────────────────────
# Hero brief panel
# ──────────────────────────────────────────────────────────────────────────────
st.markdown("---")
st.markdown("### Contested Sustainment COA Brief")
st.caption(f"brief source: {st.session_state.brief_source} · "
           f"Originator: CONTESTED-LOG / LOGCOM contested-sustainment cell")

if st.session_state.final:
    brief_slot.markdown(
        f"<div class='cl-card cl-rec' style='padding:22px 30px;'>"
        f"{st.session_state.final}</div>",
        unsafe_allow_html=True,
    )
else:
    brief_slot.info("Click PLAN COA or Load cached to populate the brief.")


# ──────────────────────────────────────────────────────────────────────────────
# Days-of-supply check (LogTRACE cross-check)
# ──────────────────────────────────────────────────────────────────────────────
st.markdown("---")
st.markdown("#### Days-of-Supply Cross-Check — LogTRACE")
dos_l, dos_r = st.columns([0.55, 0.45])
with dos_l:
    pallets = 200
    mres_per_pallet = 72  # standard MRE pallet
    mres = pallets * mres_per_pallet
    mres_per_meu_per_day = 2200 * 3  # 31st MEU(SOC) ≈ 2,200 pers · 3 MREs/day
    days = mres / mres_per_meu_per_day
    st.markdown(
        f"""
        <div class='cl-card'>
          <div style='color:{BRAND['neon']};font-size:13px;font-weight:700;
                      text-transform:uppercase;'>200 MRE Pallets vs 31st MEU(SOC)</div>
          <div style='font-size:13px;line-height:1.7;margin-top:8px;'>
            <b>Pallets:</b> 200<br/>
            <b>MREs total:</b> {mres:,} (72 MREs / pallet)<br/>
            <b>MEU(SOC) personnel:</b> ~2,200<br/>
            <b>Daily burn:</b> {mres_per_meu_per_day:,} MREs (3/day/Marine — doctrinal)<br/>
            <b>Days of subsistence:</b> <span style='color:{BRAND['neon']};font-weight:700;'>{days:.1f}</span><br/>
            <b>Combat sustainment window:</b> 14 days<br/>
            <b>Reserve:</b> {days - 14:.1f} days
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
with dos_r:
    stocks = _stocks()
    rows = []
    for d, classes in stocks.items():
        for cls, info in classes.items():
            rows.append({"depot": d, "class": cls,
                         "on_hand_pallets": info["on_hand_pallets"],
                         "lots": info["lot_count"]})
    df = pd.DataFrame(rows)
    fig = px.bar(df[df["class"] == "Class I"], x="depot", y="on_hand_pallets",
                 color="depot", title="Class I (MRE) on-hand by depot",
                 color_discrete_sequence=["#00BB7A", "#0DCC8A", "#00FFA7",
                                           "#E0B341", "#FF6F66", "#7AC4FF"])
    fig.update_layout(plot_bgcolor=BRAND["bg"], paper_bgcolor=BRAND["bg"],
                      font_color="#E8E8E8",
                      height=300, margin=dict(l=10, r=10, t=40, b=20),
                      showlegend=False)
    st.plotly_chart(fig, use_container_width=True)


# ──────────────────────────────────────────────────────────────────────────────
# KAMIWAZA env beat
# ──────────────────────────────────────────────────────────────────────────────
st.markdown("---")
kam_l, kam_r = st.columns([0.55, 0.45])
with kam_l:
    st.markdown("#### On-Prem Posture")
    st.markdown(
        f"<div class='cl-card'>"
        f"<div style='color:{BRAND['neon']};font-size:11px;font-weight:700;"
        f"letter-spacing:1.2px;text-transform:uppercase;'>same code · two endpoints</div>"
        f"<pre style='background:#000;color:#00FFA7;padding:14px;border-radius:6px;"
        f"font-family:Menlo,monospace;font-size:12px;margin-top:10px;overflow-x:auto;'>"
        f"# Cloud (today)\n"
        f"export CLOUD_LLM_API_KEY=&lt;your-cloud-key&gt;\n\n"
        f"# On-prem (Kamiwaza Stack)\n"
        f"export KAMIWAZA_BASE_URL=https://kamiwaza.local/api/v1\n"
        f"export KAMIWAZA_API_KEY=...\n\n"
        f"# IL5/IL6 ready · 100% data containment\n"
        f"# Nothing ever leaves your accredited environment."
        f"</pre>"
        f"</div>",
        unsafe_allow_html=True,
    )
with kam_r:
    st.markdown("#### Datasets Fused (8)")
    st.markdown(
        "<div class='cl-card'>"
        "<ul style='font-size:12px;line-height:1.7;margin:0;padding-left:18px;color:#E8E8E8;'>"
        "<li><b>BTS NTAD</b> — CONUS rail/road/water typed graph</li>"
        "<li><b>MSI WPI</b> — 50 ports, throughput, berths, LCAC pads</li>"
        "<li><b>AIS</b> — Pacific shipping-lane corridors</li>"
        "<li><b>ASAM Pirate Attacks</b> — 3,000-record KDE risk overlay</li>"
        "<li><b>AFCENT Logistics</b> — depot Class I-IX on-hand</li>"
        "<li><b>GCSS-MC</b> — lot-level inventory + expiration</li>"
        "<li><b>LaDe Last-Mile</b> — 8 dispersed squad positions</li>"
        "<li><b>Global SC Disruption</b> — 60-day events feed</li>"
        "</ul>"
        "<div style='color:#7E7E7E;font-size:11px;margin-top:10px;'>"
        "Real-data swap: <code>data/load_real.py</code> per-dataset"
        "</div></div>",
        unsafe_allow_html=True,
    )


st.markdown(
    f"<div class='cl-footer'>"
    f"Powered by Kamiwaza · Contested logistics, executed without compromise."
    f"</div>",
    unsafe_allow_html=True,
)
