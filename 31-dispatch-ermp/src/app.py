"""DISPATCH — Streamlit frontend on port 3031.

3-pane operator UI for an installation 911 / CAD watch officer:

  LEFT: Live call transcript playback (streamed segment-by-segment)
  CENTER: AI triage card (incident type, severity, callback questions, units)
  RIGHT: Folium installation map showing units en route + incident pin

Hero AI is the three-stage pipeline (transcript -> triage JSON -> CAD brief).
Cache-first: pre-computed briefs in data/cached_briefs.json so the demo
recording is snappy. Click "Re-run live" to hit the model again.
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

import folium
import requests
import streamlit as st
from streamlit_folium import st_folium

ROOT = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(ROOT))

from shared.kamiwaza_client import BRAND  # noqa: E402

try:
    from src.triage import (  # type: ignore
        baseline_triage, baseline_cad_brief, cached_brief, select_units,
    )
except ImportError:
    sys.path.insert(0, str(Path(__file__).parent))
    from triage import (  # type: ignore
        baseline_triage, baseline_cad_brief, cached_brief, select_units,
    )

BACKEND = os.getenv("DISPATCH_BACKEND_URL", "http://localhost:8031")
DATA = Path(__file__).resolve().parent.parent / "data"

# ---------------------------------------------------------------------------
# Page config + brand styling
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="DISPATCH — Emergency Response Modernization Project",
    page_icon="*",
    layout="wide",
    initial_sidebar_state="expanded",
)

CSS = f"""
<style>
.stApp {{ background-color: {BRAND['bg']}; color: #E5E5E5; }}
section[data-testid="stSidebar"] {{ background-color: {BRAND['surface']}; border-right: 1px solid {BRAND['border']}; }}
.block-container {{ padding-top: 0.6rem; padding-bottom: 0.6rem; max-width: 100% !important; }}
h1, h2, h3, h4 {{ color: {BRAND['neon']}; }}
.brand-bar {{ display: flex; align-items: center; justify-content: space-between; padding: 8px 14px;
              background: linear-gradient(90deg, #0E0E0E 0%, #111111 60%, #0E0E0E 100%);
              border: 1px solid {BRAND['border']}; border-radius: 8px; margin-bottom: 10px; }}
.brand-left {{ display: flex; align-items: center; gap: 14px; }}
.brand-left img {{ height: 28px; }}
.brand-title {{ color: {BRAND['neon']}; font-weight: 700; letter-spacing: 1px; }}
.brand-tag {{ color: {BRAND['muted']}; font-size: 12px; }}
.kamiwaza-footer {{ text-align: center; color: {BRAND['muted']}; font-size: 12px; padding: 12px 0; border-top: 1px solid {BRAND['border']}; margin-top: 16px; }}
.section-card {{ background: {BRAND['surface']}; border: 1px solid {BRAND['border']}; border-radius: 8px; padding: 12px 14px; margin-bottom: 10px; }}
.kpi {{ display: inline-block; margin-right: 22px; }}
.kpi .v {{ color: {BRAND['neon']}; font-weight: 700; font-size: 20px; }}
.kpi .l {{ color: {BRAND['muted']}; font-size: 11px; text-transform: uppercase; letter-spacing: 1px; }}

.transcript-pane {{
  background: #0a0e0c; border: 1px solid {BRAND['border']}; border-radius: 8px;
  padding: 12px 14px; height: 460px; overflow-y: auto;
  font-family: ui-monospace, SFMono-Regular, monospace; font-size: 13px;
  color: #e5e5e5;
}}
.seg {{ margin-bottom: 8px; padding: 6px 8px; border-radius: 5px; line-height: 1.45; }}
.seg.Dispatcher {{ background: rgba(0,187,122,0.10); border-left: 3px solid {BRAND['primary']}; }}
.seg.Caller     {{ background: rgba(255,154,59,0.10); border-left: 3px solid #ff9a3b; }}
.seg .who {{ color: {BRAND['muted']}; font-size: 11px; text-transform: uppercase; letter-spacing: 1px; }}
.seg .ts  {{ color: #5a5a5a; font-size: 10px; margin-left: 6px; }}
.seg .txt {{ display: block; margin-top: 3px; color: #e5e5e5; }}

.triage-card {{
  background: {BRAND['surface_high']}; border: 1px solid {BRAND['border']}; border-radius: 8px;
  padding: 14px; height: 460px; overflow-y: auto;
}}
.sev-pill {{ display: inline-block; padding: 4px 10px; border-radius: 12px; font-weight: 800;
             font-size: 12px; letter-spacing: 1px; margin-right: 6px; }}
.sev-echo    {{ background: #4a0d0d; color: #ffd6d6; border: 1px solid #ff3b3b; }}
.sev-delta   {{ background: #4a2c0d; color: #ffe6c8; border: 1px solid #ff9a3b; }}
.sev-charlie {{ background: #4a4a0d; color: #fff7c8; border: 1px solid #ffe23b; }}
.sev-bravo   {{ background: #0d3a4a; color: #c8eaff; border: 1px solid #3bb6ff; }}
.sev-alpha   {{ background: #0d3a1f; color: #c8ffe0; border: 1px solid {BRAND['primary']}; }}
.type-pill {{ display: inline-block; padding: 4px 10px; border-radius: 12px;
              background: #15291f; color: {BRAND['neon']}; border: 1px solid {BRAND['primary']};
              font-weight: 700; font-size: 12px; letter-spacing: 1px; }}
.unit-row {{ display: flex; align-items: center; padding: 6px 8px;
             border-bottom: 1px dashed {BRAND['border']}; font-size: 13px; }}
.unit-row .cs {{ color: {BRAND['neon']}; font-weight: 700; min-width: 130px; }}
.unit-row .meta {{ color: #c5c5c5; }}
.unit-row .eta {{ margin-left: auto; color: #ffe6c8; font-weight: 700; }}
.brief-pre {{ background: #0a0e0c; border: 1px solid {BRAND['border']}; border-radius: 6px;
              padding: 10px 12px; color: #e5e5e5; white-space: pre-wrap;
              font-family: ui-monospace, SFMono-Regular, monospace; font-size: 12px; }}

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
      <div class="brand-title">DISPATCH</div>
      <div class="brand-tag">Emergency Response Modernization Project — installation 911 + CAD, AI-augmented.</div>
    </div>
  </div>
  <div class="brand-tag">USMC LOGCOM CDAO :: ERMP :: From "9-1-1, what is your emergency?" to units rolling in under 30 seconds.</div>
</div>
""",
    unsafe_allow_html=True,
)


# ---------------------------------------------------------------------------
# Data loaders (backend-first, file fallback for resilience during demo)
# ---------------------------------------------------------------------------
@st.cache_data(ttl=10)
def get_health() -> dict:
    try:
        return requests.get(f"{BACKEND}/health", timeout=2).json()
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": str(e)}


@st.cache_data(ttl=30)
def get_calls() -> list[dict]:
    try:
        return requests.get(f"{BACKEND}/api/calls", timeout=2).json()
    except Exception:
        return json.loads((DATA / "calls.json").read_text())


@st.cache_data(ttl=30)
def get_units() -> list[dict]:
    try:
        return requests.get(f"{BACKEND}/api/units", timeout=2).json()
    except Exception:
        return json.loads((DATA / "units.json").read_text())


@st.cache_data(ttl=30)
def get_locations() -> dict:
    try:
        return requests.get(f"{BACKEND}/api/locations", timeout=2).json()
    except Exception:
        return json.loads((DATA / "incident_locations.geojson").read_text())


def post_dispatch(call_id: str, use_cache: bool, use_hero: bool) -> dict:
    try:
        r = requests.post(
            f"{BACKEND}/api/dispatch/{call_id}",
            json={"use_cache": use_cache, "use_hero_model": use_hero},
            timeout=45,
        )
        r.raise_for_status()
        return r.json()
    except Exception:
        # In-process fallback
        call = next(c for c in get_calls() if c["id"] == call_id)
        cb = cached_brief(call_id) if use_cache else None
        if cb:
            triage = cb["triage"]
            brief = cb["cad_brief"]
            cached = True
        else:
            triage = baseline_triage(call)
            brief = baseline_cad_brief(call, triage)
            cached = False
        return {
            "call_id": call_id,
            "call": call,
            "triage": triage,
            "cad_brief": brief,
            "assigned_units": select_units(get_units(), triage),
            "cached": cached,
        }


# ---------------------------------------------------------------------------
# Sidebar — controls
# ---------------------------------------------------------------------------
calls = get_calls()
units = get_units()
locations = get_locations()

with st.sidebar:
    st.markdown("### Operator Controls")
    call_options = {f"{c['id']} — {c['address']}": c["id"] for c in calls}
    pick = st.selectbox("Active 9-1-1 call", list(call_options.keys()), index=0)
    active_call_id = call_options[pick]

    st.caption(
        "Five synthetic calls: aviation fire, MVI on perimeter, structure fire "
        "in base housing, MASCAL on the range, suspicious package at the gate."
    )

    use_cache = st.checkbox(
        "Use cached AI briefs (recommended for demo)", True,
        help="Pre-computed during data/generate.py; ensures snappy playback. "
             "Toggle off to re-run the model live.",
    )
    use_hero = st.checkbox(
        "Use Kamiwaza-deployed hero model for CAD brief", True,
        help="Premium long-context model for the dispatcher's CAD entry.",
    )

    st.markdown("---")
    st.markdown("### Backend")
    h = get_health()
    if h.get("ok"):
        st.success(
            f"OK — primary: {h.get('primary_model')}\n\n"
            f"Endpoint: `{h.get('kamiwaza_endpoint')}`"
        )
    else:
        st.warning(
            f"Backend unreachable; using in-process compute.\n\n{h.get('error','')}"
        )

    st.markdown("---")
    st.markdown(
        f"<div class='brand-tag'>All AI calls route through your "
        f"Kamiwaza-deployed endpoint — set <code>KAMIWAZA_BASE_URL</code> "
        f"to keep traffic inside your wire.</div>",
        unsafe_allow_html=True,
    )


# ---------------------------------------------------------------------------
# Pull current dispatch payload (cache-first)
# ---------------------------------------------------------------------------
active_call = next(c for c in calls if c["id"] == active_call_id)

if "dispatch_cache" not in st.session_state:
    st.session_state["dispatch_cache"] = {}

cache_key = (active_call_id, use_cache, use_hero)
if cache_key not in st.session_state["dispatch_cache"]:
    st.session_state["dispatch_cache"][cache_key] = post_dispatch(
        active_call_id, use_cache=use_cache, use_hero=use_hero
    )
payload = st.session_state["dispatch_cache"][cache_key]
triage = payload["triage"]
brief = payload["cad_brief"]
assigned = payload["assigned_units"]


# ---------------------------------------------------------------------------
# KPI strip
# ---------------------------------------------------------------------------
n_units_assigned = len(assigned)
fastest_eta = min((u["eta_min"] for u in assigned), default=None)
total_personnel = sum(u.get("personnel", 0) for u in assigned)
st.markdown(
    f"""
<div class="section-card">
  <span class="kpi"><span class="v">{active_call['id']}</span><span class="l">Call ID</span></span>
  <span class="kpi"><span class="v" style="color:#ff9a3b">{triage['incident_type'].replace('_',' ').upper()}</span><span class="l">Incident Type</span></span>
  <span class="kpi"><span class="v" style="color:#ff3b3b">{triage['severity'].upper()}</span><span class="l">APCO Severity</span></span>
  <span class="kpi"><span class="v">{n_units_assigned}</span><span class="l">Units Assigned</span></span>
  <span class="kpi"><span class="v">{total_personnel}</span><span class="l">Personnel En Route</span></span>
  <span class="kpi"><span class="v">{(fastest_eta or '-') if fastest_eta is not None else '-'}{' min' if fastest_eta else ''}</span><span class="l">Fastest ETA</span></span>
</div>
""",
    unsafe_allow_html=True,
)


# ---------------------------------------------------------------------------
# 3-pane layout
# ---------------------------------------------------------------------------
left, center, right = st.columns([1.05, 1.05, 1.35], gap="medium")

# ----- LEFT: live transcript playback ---------------------------------------
with left:
    st.markdown("#### Stage 1 — Live Call Transcript")
    play_clicked = st.button(
        "▶  Play call",
        type="secondary", use_container_width=True,
        key=f"play_{active_call_id}",
    )
    placeholder = st.empty()

    transcript_state_key = f"played_{active_call_id}"

    def _render_transcript(segs: list[dict]) -> str:
        rows = ['<div class="transcript-pane">']
        for s in segs:
            who = s["speaker"]
            ts = f"t+{s['t']:.1f}s"
            rows.append(
                f'<div class="seg {who}">'
                f'<span class="who">{who}</span><span class="ts">{ts}</span>'
                f'<span class="txt">{s["text"]}</span>'
                f'</div>'
            )
        rows.append("</div>")
        return "\n".join(rows)

    if play_clicked or transcript_state_key not in st.session_state:
        # Stream segments with a small delay so the demo recorder catches it
        played: list[dict] = []
        for seg in active_call["transcript"]:
            played.append(seg)
            placeholder.markdown(_render_transcript(played), unsafe_allow_html=True)
            time.sleep(0.55)
        st.session_state[transcript_state_key] = True
    else:
        placeholder.markdown(
            _render_transcript(active_call["transcript"]), unsafe_allow_html=True
        )

    st.caption(
        f"Caller: {active_call['address']}  |  Received {active_call['received_at']}"
    )


# ----- CENTER: AI triage card -----------------------------------------------
with center:
    st.markdown("#### Stage 2 — AI Triage Card")
    sev = triage["severity"].lower()
    inc = triage["incident_type"].replace("_", " ").upper()
    units_html = "".join(
        f'<li><b>{u["count"]}x</b> {u["unit_type"]}</li>'
        for u in triage["recommended_units"]
    )
    callbacks_html = "".join(
        f"<li>{q}</li>" for q in triage.get("callback_questions", [])
    )
    confidence_pct = int(round(float(triage.get("confidence", 0.6)) * 100))

    st.markdown(
        f"""
<div class="triage-card">
  <div style="margin-bottom:8px">
    <span class="type-pill">{inc}</span>
    <span class="sev-pill sev-{sev}">{sev.upper()}</span>
    <span class="brand-tag" style="margin-left:8px">confidence {confidence_pct}%</span>
  </div>
  <div style="font-size:14px;color:#e5e5e5;margin:8px 0 12px 0">
    <b>Primary complaint:</b> {triage['primary_complaint']}
  </div>
  <div style="font-size:13px;color:#c5c5c5">
    <b>ANI/ALI extracted address:</b><br/>
    {triage['address_extracted']}<br/>
    <span class="brand-tag">({triage['lat_lon'][0]:.4f}, {triage['lat_lon'][1]:.4f})</span>
  </div>
  <hr style="border-color:{BRAND['border']}"/>
  <div style="font-size:13px"><b>Recommended units:</b>
    <ul style="margin-top:4px">{units_html}</ul>
  </div>
  <div style="font-size:13px;margin-top:10px"><b>Suggested callback questions:</b>
    <ol style="margin-top:4px">{callbacks_html}</ol>
  </div>
</div>
""",
        unsafe_allow_html=True,
    )

    st.caption(
        f"Source: {'cached' if payload.get('cached') else 'live model call'}  |  "
        f"chat_json structured-output triage agent"
    )


# ----- RIGHT: dispatch map --------------------------------------------------
with right:
    st.markdown("#### Stage 3 — Unit Dispatch Map")
    incident_lat, incident_lon = triage["lat_lon"]
    m = folium.Map(
        location=[incident_lat, incident_lon],
        zoom_start=15,
        tiles="CartoDB dark_matter",
        control_scale=True,
    )

    # Building / road footprints
    for feat in locations.get("features", []):
        props = feat.get("properties", {})
        geom = feat.get("geometry", {})
        if geom.get("type") == "Polygon":
            color = "#ff3b3b" if props.get("type") == "critical" else BRAND["primary"]
            ring_lonlat = geom["coordinates"][0]
            ring_latlon = [[lat, lon] for lon, lat in ring_lonlat]
            folium.Polygon(
                locations=ring_latlon,
                color=color, weight=2, fill=True, fill_color=color, fill_opacity=0.10,
                tooltip=props.get("name", ""),
            ).add_to(m)
        elif geom.get("type") == "LineString":
            ring_lonlat = geom["coordinates"]
            ring_latlon = [[lat, lon] for lon, lat in ring_lonlat]
            folium.PolyLine(
                locations=ring_latlon,
                color=BRAND["muted"], weight=1, opacity=0.6, dash_array="6, 6",
                tooltip=props.get("name", ""),
            ).add_to(m)

    # Incident pin
    folium.Marker(
        location=[incident_lat, incident_lon],
        icon=folium.Icon(color="red", icon="exclamation-sign"),
        popup=folium.Popup(
            f"<b>INCIDENT</b><br>{active_call['address']}<br>"
            f"Type: {triage['incident_type']}<br>"
            f"Severity: <b>{triage['severity'].upper()}</b>",
            max_width=260,
        ),
        tooltip=f"INCIDENT — {triage['severity'].upper()}",
    ).add_to(m)

    # Concentric stand-off rings (50m / 100m / 250m)
    for rad_m, color in [(50, "#ff3b3b"), (100, "#ff9a3b"), (250, "#ffe23b")]:
        folium.Circle(
            location=[incident_lat, incident_lon],
            radius=rad_m, color=color, weight=1, fill=False, opacity=0.45,
            tooltip=f"{rad_m}m ring",
        ).add_to(m)

    # Assigned units + route polylines
    type_color = {
        "engine": "#ff3b3b", "rescue": "#ff9a3b", "ambulance": "#3bb6ff",
        "hazmat": "#ffe23b", "police": BRAND["primary"],
    }
    type_icon = {
        "engine": "fire", "rescue": "wrench", "ambulance": "plus-sign",
        "hazmat": "tint", "police": "user",
    }
    for u in assigned:
        ulat, ulon = u["location"]
        col = type_color.get(u["type"], BRAND["primary"])
        folium.PolyLine(
            locations=[[ulat, ulon], [incident_lat, incident_lon]],
            color=col, weight=3, opacity=0.85, dash_array="2, 8",
            tooltip=f"{u['callsign']} -> incident ({u['distance_mi']} mi, ETA {u['eta_min']} min)",
        ).add_to(m)
        folium.Marker(
            location=[ulat, ulon],
            icon=folium.Icon(color="green", icon=type_icon.get(u["type"], "info-sign")),
            popup=folium.Popup(
                f"<b>{u['callsign']}</b><br>"
                f"Type: {u['type']}<br>"
                f"Personnel: {u.get('personnel', 0)}<br>"
                f"Distance: {u['distance_mi']} mi<br>"
                f"ETA: <b>{u['eta_min']} min</b>",
                max_width=240,
            ),
            tooltip=f"{u['callsign']} — ETA {u['eta_min']} min",
        ).add_to(m)

    # Show idle (un-assigned) units faintly
    assigned_ids = {u["id"] for u in assigned}
    for u in units:
        if u["id"] in assigned_ids:
            continue
        folium.CircleMarker(
            location=u["location"],
            radius=3, color=BRAND["muted"], fill=True,
            fill_color=BRAND["muted"], fill_opacity=0.6,
            tooltip=f"{u['callsign']} (idle)",
        ).add_to(m)

    st_folium(m, height=460, width=None, returned_objects=[], key=f"map_{active_call_id}")


# ---------------------------------------------------------------------------
# Hero CAD entry strip
# ---------------------------------------------------------------------------
st.markdown("---")
st.markdown("#### Hero AI — Auto-Drafted CAD Entry (Kamiwaza-routed)")
hcol1, hcol2 = st.columns([2, 1], gap="medium")

with hcol1:
    st.markdown(f"<div class='brief-pre'>{brief}</div>", unsafe_allow_html=True)
    st.caption(
        f"Source: {'cached' if payload.get('cached') else 'live model call'}  |  "
        f"15-second watchdog with deterministic baseline fallback."
    )

with hcol2:
    st.markdown("**Assigned units & ETA**")
    for u in sorted(assigned, key=lambda x: x["eta_min"]):
        st.markdown(
            f"""
<div class="unit-row">
  <span class="cs">{u['callsign']}</span>
  <span class="meta">{u['type']} :: {u['distance_mi']} mi</span>
  <span class="eta">ETA {u['eta_min']} min</span>
</div>
""",
            unsafe_allow_html=True,
        )

    st.markdown("&nbsp;")
    if st.button("Re-run live (skip cache)", use_container_width=True):
        st.session_state["dispatch_cache"].pop(cache_key, None)
        st.session_state["dispatch_cache"][(active_call_id, False, use_hero)] = (
            post_dispatch(active_call_id, use_cache=False, use_hero=use_hero)
        )
        st.rerun()


# ---------------------------------------------------------------------------
# Raw payload (judge-friendly proof)
# ---------------------------------------------------------------------------
with st.expander("Raw triage JSON (verifies structured-output JSON-mode)"):
    st.json(triage)


# ---------------------------------------------------------------------------
# Footer
# ---------------------------------------------------------------------------
st.markdown(
    f"<div class='kamiwaza-footer'>{BRAND['footer']}  ::  "
    f"NG911 ANI/ALI + NIEM-CAD shape :: KAMIWAZA_BASE_URL swap = on-prem in one env-var</div>",
    unsafe_allow_html=True,
)
