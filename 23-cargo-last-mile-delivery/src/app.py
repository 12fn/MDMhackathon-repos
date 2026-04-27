"""CARGO Streamlit UI — natural-language last-mile expeditionary delivery."""
from __future__ import annotations

import json
import sys
from pathlib import Path

# Make repo root + the app dir importable regardless of cwd. This keeps
# `from src.agent import ...` working even when Streamlit reruns the script
# from an unexpected cwd (e.g. file-watcher reruns).
_THIS = Path(__file__).resolve()
ROOT = _THIS.parents[3]
APP_ROOT = _THIS.parents[1]
for _p in (ROOT, APP_ROOT):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import folium
import pandas as pd
import streamlit as st
from folium.plugins import AntPath
from streamlit_folium import st_folium

from shared.kamiwaza_client import BRAND  # noqa: E402

from src.agent import stream_run  # noqa: E402
from src.tools import (  # noqa: E402
    load_depots, load_squads, load_vehicles, load_threat_zones,
)


DATA_DIR = Path(__file__).resolve().parents[1] / "data"
CACHE_PATH = DATA_DIR / "cached_briefs.json"


st.set_page_config(
    page_title="CARGO — Last-Mile Expeditionary Delivery Optimizer",
    layout="wide",
)

# ---------------------------------------------------------------------------
# Kamiwaza dark theme
# ---------------------------------------------------------------------------
st.markdown(
    f"""
    <style>
      .stApp {{ background-color: {BRAND['bg']}; color: #E6E6E6; }}
      [data-testid="stSidebar"] {{ background-color: {BRAND['surface']};
                                    border-right: 1px solid {BRAND['border']}; }}
      h1, h2, h3, h4 {{ color: {BRAND['neon']}; letter-spacing: .04em; }}
      .stButton > button {{ background-color: {BRAND['primary']};
                            color: #0A0A0A; border: 0; font-weight: 600; }}
      .stButton > button:hover {{ background-color: {BRAND['primary_hover']};
                                   color: #000; }}
      .stTextInput > div > div > input,
      .stTextArea textarea,
      .stSelectbox div[data-baseweb="select"] {{
            background-color: {BRAND['surface_high']}; color: #E6E6E6;
            border: 1px solid {BRAND['border']}; }}
      .cg-card {{ background-color: {BRAND['surface_high']};
                  border: 1px solid {BRAND['border']}; border-radius: 8px;
                  padding: 14px 18px; margin-bottom: 10px; }}
      .cg-recommended {{ border-color: {BRAND['neon']};
                         box-shadow: 0 0 0 1px {BRAND['neon']}; }}
      .cg-pill {{ display: inline-block; padding: 2px 8px; margin-right: 6px;
                  border-radius: 999px; background: {BRAND['primary']};
                  color: #0A0A0A; font-weight: 600; font-size: 12px; }}
      .cg-pill-neon {{ background: {BRAND['neon']}; color: #062F1F; }}
      .cg-pill-warn {{ background: #aa3333; color: #fff; }}
      .cg-trace-call {{ color: {BRAND['neon']}; font-family: ui-monospace,
                        Menlo, monospace; font-size: 12px; }}
      .cg-trace-result {{ color: #B8B8B8; font-family: ui-monospace,
                          Menlo, monospace; font-size: 11px;
                          white-space: pre-wrap; }}
      .cg-footer {{ color: {BRAND['muted']}; text-align: center; font-size: 12px;
                    margin-top: 24px; padding-top: 12px;
                    border-top: 1px solid {BRAND['border']}; }}
    </style>
    """,
    unsafe_allow_html=True,
)

# ---------------------------------------------------------------------------
# Header
# ---------------------------------------------------------------------------
hdr_l, hdr_r = st.columns([0.7, 0.3])
with hdr_l:
    st.markdown(
        f"""
        <div style="display:flex; align-items:center; gap:14px;">
          <img src="{BRAND['logo_url']}" alt="Kamiwaza" style="height:34px;" />
          <div>
            <div style="font-size:28px; font-weight:700;
                        color:{BRAND['neon']}; letter-spacing:.06em;">
              CARGO
            </div>
            <div style="color:{BRAND['text_dim']}; font-size:13px;">
              Last-Mile Expeditionary Delivery Optimizer &nbsp;|&nbsp;
              FOB Raven &rarr; alpha through hotel
            </div>
          </div>
        </div>
        """, unsafe_allow_html=True,
    )
with hdr_r:
    st.markdown(
        f"""
        <div style="text-align:right; padding-top:6px;">
          <span class="cg-pill">EXPEDITIONARY</span>
          <span class="cg-pill cg-pill-neon">LAST-MILE</span>
          <div style="color:{BRAND['text_dim']}; font-size:11px; margin-top:6px;">
            Mission: 30 km AOI &nbsp;|&nbsp; T-48h push window &nbsp;|&nbsp;
            8 dispersed squads
          </div>
        </div>
        """, unsafe_allow_html=True,
    )

st.markdown("---")

# ---------------------------------------------------------------------------
# Sidebar: live agent reasoning trace
# ---------------------------------------------------------------------------
with st.sidebar:
    st.markdown(
        f"### <span style='color:{BRAND['neon']}'>Agent Reasoning</span>",
        unsafe_allow_html=True,
    )
    st.markdown(
        f"<div style='color:{BRAND['text_dim']}; font-size:12px;'>"
        "Live Kamiwaza-deployed model tool-calling trace — every "
        "<code>list_squad_positions()</code>, <code>compute_route()</code>, "
        "<code>check_threat_overlay()</code>, and "
        "<code>compare_options()</code> the agent fires.</div>",
        unsafe_allow_html=True,
    )
    trace_slot = st.empty()

# ---------------------------------------------------------------------------
# Load data
# ---------------------------------------------------------------------------
depots = load_depots()
squads = load_squads()
vehicles_df = load_vehicles()
threat_zones = load_threat_zones()


def load_cache() -> dict:
    if CACHE_PATH.exists():
        try:
            return json.loads(CACHE_PATH.read_text())
        except Exception:  # noqa: BLE001
            return {}
    return {}


CACHE = load_cache()

# ---------------------------------------------------------------------------
# Main area
# ---------------------------------------------------------------------------
left, right = st.columns([0.55, 0.45], gap="large")

with left:
    st.markdown("#### Push Request")
    default_q = (
        "Push 8,000 lb of Class I and 2,400 rounds-equivalent Class V "
        "from FOB Raven to alpha through hotel squads by 0600 tomorrow, "
        "lowest threat exposure."
    )
    examples = [
        default_q,
        "URGENT: Delta squad needs 600 lb Class VIII (med) and 900 lb water "
        "inside 6 hours. UAS sector active 0500-0800.",
        "Resupply only the URGENT and PRIORITY squads with the fastest "
        "armored option — JLTV preferred.",
        "Detach UGVs only for the unmanned last-tactical-mile push to "
        "Delta, Echo, and Golf. Lowest signature.",
    ]
    pick = st.selectbox(
        "Or pick a canned scenario:", examples, index=0,
        label_visibility="collapsed",
    )
    user_msg = st.text_area(
        "Type a push request:", value=pick, height=100,
        label_visibility="collapsed",
    )
    c1, c2, _ = st.columns([0.35, 0.35, 0.3])
    with c1:
        run_btn = st.button("Plan Push (cache-first)", type="primary",
                            use_container_width=True)
    with c2:
        live_btn = st.button("Regenerate Live", use_container_width=True)

with right:
    st.markdown("#### AOI Footprint")
    total_demand = sum(s["demand_total_lb"] for s in squads)
    urgent_n = sum(1 for s in squads if s["priority"] == "URGENT")
    st.markdown(
        f"""
        <div class='cg-card'>
          <div style='display:flex; justify-content:space-around; text-align:center;'>
            <div><div style='font-size:24px; color:{BRAND['neon']};
                  font-weight:700;'>{len(depots)}</div>
                  <div style='color:{BRAND['text_dim']}; font-size:12px;'>
                  Depot</div></div>
            <div><div style='font-size:24px; color:{BRAND['neon']};
                  font-weight:700;'>{len(squads)}</div>
                  <div style='color:{BRAND['text_dim']}; font-size:12px;'>
                  Squads</div></div>
            <div><div style='font-size:24px; color:{BRAND['primary']};
                  font-weight:700;'>{len(vehicles_df)}</div>
                  <div style='color:{BRAND['text_dim']}; font-size:12px;'>
                  Vehicles</div></div>
            <div><div style='font-size:24px; color:{BRAND['primary']};
                  font-weight:700;'>{len(threat_zones)}</div>
                  <div style='color:{BRAND['text_dim']}; font-size:12px;'>
                  Threat zones</div></div>
            <div><div style='font-size:24px; color:#E6E6E6;
                  font-weight:700;'>{total_demand:,}</div>
                  <div style='color:{BRAND['text_dim']}; font-size:12px;'>
                  Total demand (lb)</div></div>
            <div><div style='font-size:24px; color:#FF8866;
                  font-weight:700;'>{urgent_n}</div>
                  <div style='color:{BRAND['text_dim']}; font-size:12px;'>
                  URGENT</div></div>
          </div>
        </div>
        """, unsafe_allow_html=True,
    )
    map_slot = st.empty()


# ---------------------------------------------------------------------------
# Map renderer (Folium with threat-zone rectangles + AntPath route)
# ---------------------------------------------------------------------------
def _route_color(vehicle_class: str | None) -> str:
    return {
        "MTVR": "#00FFA7",
        "JLTV": "#00BB7A",
        "ARV":  "#0DCC8A",
        "UGV":  "#FFC740",
    }.get((vehicle_class or "").upper(), "#00FFA7")


def render_map(highlight_route: dict | None = None):
    centroid_lat = sum(s["lat"] for s in squads) / len(squads)
    centroid_lon = sum(s["lon"] for s in squads) / len(squads)
    fm = folium.Map(
        location=[centroid_lat, centroid_lon], zoom_start=10,
        tiles="CartoDB dark_matter", control_scale=True,
    )
    # Threat zones
    for z in threat_zones:
        color = {"HIGH": "#ff5560", "MEDIUM": "#ffb74a",
                 "LOW": "#62c97a"}.get(z["severity"], "#888")
        folium.Rectangle(
            bounds=[[z["lat_min"], z["lon_min"]], [z["lat_max"], z["lon_max"]]],
            color=color, weight=1.5, fill=True, fill_opacity=0.18,
            tooltip=f"{z['name']} ({z['severity']}, {z['type']}) "
                    f"[{z['window_local']}]",
        ).add_to(fm)
    # Depot
    for d in depots:
        folium.Marker(
            location=[d["lat"], d["lon"]],
            icon=folium.Icon(color="green", icon="warehouse", prefix="fa"),
            tooltip=f"{d['name']} ({d['lz_grade']} LZ)",
        ).add_to(fm)
    # Squads
    pri_color = {"URGENT": "red", "PRIORITY": "orange", "ROUTINE": "blue"}
    for s in squads:
        folium.CircleMarker(
            location=[s["lat"], s["lon"]],
            radius=7, color=pri_color.get(s["priority"], "blue"),
            fill=True, fill_opacity=0.9,
            tooltip=(f"{s['callsign']} ({s['priority']}, {s['terrain']}) "
                     f"— {s['demand_total_lb']:,} lb / {s['personnel']} pax"),
        ).add_to(fm)
        folium.map.Marker(
            [s["lat"] + 0.006, s["lon"]],
            icon=folium.DivIcon(
                icon_size=(80, 12), icon_anchor=(40, 6),
                html=(f"<div style='font-size:11px;color:#E6E6E6;"
                      f"text-shadow:0 0 3px #000;text-align:center;'>"
                      f"{s['callsign']}</div>"),
            ),
        ).add_to(fm)
    # Highlighted route (AntPath = animated dashed line)
    if highlight_route and "legs" in highlight_route:
        color = _route_color(highlight_route.get("vehicle_class"))
        for leg in highlight_route["legs"]:
            AntPath(
                locations=[[leg["from_lat"], leg["from_lon"]],
                           [leg["to_lat"], leg["to_lon"]]],
                color=color, weight=4, opacity=0.85, delay=600,
                dash_array=[10, 20], tooltip=(
                    f"{leg['from']} → {leg['to']} "
                    f"({leg['distance_km']} km, {leg['time_hr']} hr)"
                ),
            ).add_to(fm)
    with map_slot:
        st_folium(fm, height=420, width=None, returned_objects=[],
                  key=f"map-{id(highlight_route)}")


render_map()

# ---------------------------------------------------------------------------
# Results section
# ---------------------------------------------------------------------------
st.markdown("---")
st.markdown("#### Recommended Course of Action")
result_slot = st.container()
final_slot = st.empty()


def render_options(comparison: dict):
    if "error" in comparison:
        result_slot.error(comparison["error"])
        return
    opts = comparison.get("options", [])
    if not opts:
        result_slot.warning("No options returned.")
        return
    cols = result_slot.columns(len(opts))
    rows = []
    for col, opt in zip(cols, opts):
        rec = opt.get("recommended", False)
        css = "cg-card cg-recommended" if rec else "cg-card"
        badge = ('<span class="cg-pill cg-pill-neon">RECOMMENDED</span>'
                 if rec else "")
        zones_pill = ""
        for z in (opt.get("zones_touched") or []):
            zones_pill += f'<span class="cg-pill">{z}</span>'
        col.markdown(
            f"""
            <div class='{css}'>
              <div style="display:flex; justify-content:space-between;
                          align-items:center;">
                <div style="font-weight:700; font-size:16px;
                            color:{BRAND['neon']};">{opt['label']}</div>
                <div>{badge}</div>
              </div>
              <div style="color:{BRAND['text_dim']}; font-size:12px;
                          margin-bottom:8px;">
                {opt['vehicle']} &nbsp;|&nbsp; {opt['stops_count']} stops
              </div>
              <div style="font-size:13px; line-height:1.7;">
                <b>Distance:</b> {opt['total_distance_km']:.1f} km<br/>
                <b>Time:</b> {opt['total_time_hr']:.2f} hr<br/>
                <b>Fuel:</b> {opt['total_fuel_gal']:.1f} gal<br/>
                <b>Risk:</b> {opt['overall_risk_0_1']:.2f} / 1.00<br/>
                <b>Score:</b> {opt['score']:.3f}
              </div>
              <div style="margin-top:8px;">{zones_pill}</div>
            </div>
            """, unsafe_allow_html=True,
        )
        rows.append({
            "Option":      opt["label"],
            "Vehicle":     opt["vehicle"],
            "Stops":       opt["stops_count"],
            "km":          round(opt["total_distance_km"], 1),
            "Hours":       round(opt["total_time_hr"], 2),
            "Fuel (gal)":  round(opt["total_fuel_gal"], 1),
            "Risk":        opt["overall_risk_0_1"],
            "Score":       opt["score"],
            "Recommended": "YES" if opt.get("recommended") else "",
        })
    result_slot.dataframe(pd.DataFrame(rows), use_container_width=True,
                          hide_index=True)
    rec = next((o for o in opts if o.get("recommended")), opts[0])
    render_map(rec.get("route"))


def render_trace(events: list[dict]):
    parts = []
    for ev in events:
        if ev["type"] == "user":
            parts.append(
                f"<div style='color:{BRAND['text_dim']}; margin:6px 0;'>"
                f"USER &gt; {ev['content']}</div>")
        elif ev["type"] == "model_message":
            if ev["content"].strip():
                parts.append(
                    f"<div style='color:#CFCFCF; margin:6px 0;"
                    f"font-style:italic;'>thinking &gt; "
                    f"{ev['content'][:280]}</div>")
        elif ev["type"] == "tool_call":
            args = json.dumps(ev["arguments"], separators=(",", ":"))[:160]
            parts.append(
                f"<div class='cg-trace-call'>→ {ev['name']}({args})</div>")
        elif ev["type"] == "tool_result":
            r = ev["result"]
            if isinstance(r, dict):
                if "matched" in r:
                    summary = (f"matched={r.get('matched')} "
                               f"demand_lb={r.get('total_demand_lb')}")
                elif "options" in r:
                    summary = f"options={len(r['options'])}"
                elif "legs" in r and "total_distance_km" in r:
                    summary = (f"legs={len(r['legs'])} "
                               f"dist={r.get('total_distance_km')}km "
                               f"fuel={r.get('total_fuel_gal')}gal")
                elif "leg_findings" in r:
                    summary = (f"risk={r['overall_risk_0_1']} "
                               f"zones={r.get('zones_touched')}")
                elif "error" in r:
                    summary = f"error: {str(r['error'])[:80]}"
                else:
                    summary = "ok"
            else:
                summary = str(r)[:80]
            parts.append(
                f"<div class='cg-trace-result'>  ← {summary} "
                f"({ev['ms']} ms)</div>")
        elif ev["type"] == "final":
            parts.append(
                f"<div style='color:{BRAND['neon']}; margin-top:8px; "
                f"border-top:1px solid {BRAND['border']}; padding-top:6px;'>"
                f"finish_reason=stop</div>")
    trace_slot.markdown("".join(parts), unsafe_allow_html=True)


def render_final(content: str):
    final_slot.markdown(
        f"<div class='cg-card' style='border-color:{BRAND['neon']};'>"
        f"<div style='color:{BRAND['neon']}; font-weight:700; "
        f"margin-bottom:6px;'>CARGO recommends:</div>"
        f"<div style='color:#E6E6E6; line-height:1.6; "
        f"white-space:pre-wrap;'>{content}</div></div>",
        unsafe_allow_html=True,
    )


# ---------------------------------------------------------------------------
# Cache-first dispatcher
# ---------------------------------------------------------------------------
def _matched_cached(prompt: str) -> dict | None:
    """Fuzzy match prompt to a cached scenario."""
    p = prompt.lower()
    for sid, brief in CACHE.items():
        cached_prompt = (brief.get("prompt") or "").lower()
        if not cached_prompt:
            continue
        # cheap match: any 4 leading words in common
        a = set(p.split())
        b = set(cached_prompt.split())
        if a == b or len(a & b) >= max(4, int(len(b) * 0.5)):
            return brief
    # default: fall back to first cached brief if available
    return next(iter(CACHE.values())) if CACHE else None


def _replay_trace(trace_events: list[dict], compare_slot: list[dict | None]):
    """Replay a cached trace (for instant demos)."""
    events: list[dict] = []
    for ev in trace_events:
        events.append(ev)
        render_trace(events)
        if ev.get("type") == "tool_result" and ev.get("name") == "compare_options":
            compare_slot[0] = ev["result"]


# ---------------------------------------------------------------------------
# Run the agent (live or cache-first)
# ---------------------------------------------------------------------------
if (run_btn or live_btn) and user_msg.strip():
    events: list[dict] = []
    last_compare_holder: list[dict | None] = [None]

    if run_btn:
        cached = _matched_cached(user_msg)
        if cached:
            events.append({"type": "user", "content": user_msg})
            events.append({"type": "model_message",
                           "content": "(cache hit — replaying pre-computed brief)"})
            for ev in cached.get("trace") or []:
                events.append(ev)
            events.append({"type": "final", "content": cached["final"]})
            for i in range(len(events)):
                render_trace(events[: i + 1])
                ev = events[i]
                if (ev.get("type") == "tool_result"
                        and ev.get("name") == "compare_options"):
                    last_compare_holder[0] = ev["result"]
            render_final(cached["final"])
            if last_compare_holder[0]:
                render_options(last_compare_holder[0])
            else:
                # no tool trace → fall back to default 3-option compare
                from src.tools import compare_options as _co
                render_options(_co(plans=None, objective="lowest_threat"))

    if live_btn or (run_btn and not _matched_cached(user_msg)):
        with st.spinner("CARGO agent planning..."):
            try:
                for ev in stream_run(user_msg):
                    events.append(ev)
                    render_trace(events)
                    if (ev["type"] == "tool_result"
                            and ev["name"] == "compare_options"):
                        last_compare_holder[0] = ev["result"]
                    if ev["type"] == "final":
                        render_final(ev["content"])
            except Exception as e:  # noqa: BLE001
                st.error(f"Agent error: {e}")
        if last_compare_holder[0]:
            render_options(last_compare_holder[0])

# ---------------------------------------------------------------------------
# Footer
# ---------------------------------------------------------------------------
st.markdown(
    f"<div class='cg-footer'>"
    f"Powered by Kamiwaza &nbsp;|&nbsp; "
    f"<code>KAMIWAZA_BASE_URL</code> swap &rarr; on-prem inference, "
    f"100% data containment. Real-data plug-in: "
    f"<code>data/load_real.py</code> (LaDe — Cainiao/Alibaba)."
    f"</div>",
    unsafe_allow_html=True,
)
