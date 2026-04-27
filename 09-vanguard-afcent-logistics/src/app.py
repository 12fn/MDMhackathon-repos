# VANGUARD — TMR automation with tool-calling agent loop
# Part of the MDM 2026 Hackathon Templates (https://github.com/12fn/MDMhackathon-repos)
# MIT licensed. Built on GAI (Government Acquisitions, Inc.) + Kamiwaza (https://www.kamiwaza.ai/).
"""VANGUARD Streamlit UI — natural-language TMR routing for AFCENT."""
from __future__ import annotations

import json
import sys
from pathlib import Path

# Repo root for shared imports
ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pandas as pd
import pydeck as pdk
import streamlit as st

from shared.kamiwaza_client import BRAND  # noqa: E402

from src.agent import stream_run  # noqa: E402
from src.tools import load_assets, load_bases  # noqa: E402


st.set_page_config(
    page_title="VANGUARD — AFCENT TMR Routing Agent",
    page_icon="◆",
    layout="wide",
)

# ---------------------------------------------------------------------------
# Kamiwaza dark theme (verbatim brand colors)
# ---------------------------------------------------------------------------
st.markdown(
    f"""
    <style>
      .stApp {{ background-color: {BRAND['bg']}; color: #E6E6E6; }}
      [data-testid="stSidebar"] {{ background-color: {BRAND['surface']};
                                    border-right: 1px solid {BRAND['border']}; }}
      h1, h2, h3, h4 {{ color: {BRAND['neon']}; letter-spacing: .04em; }}
      .stButton > button {{ background-color: {BRAND['primary']}; color: #0A0A0A;
                            border: 0; font-weight: 600; }}
      .stButton > button:hover {{ background-color: {BRAND['primary_hover']}; color: #000; }}
      .stTextInput > div > div > input,
      .stTextArea textarea {{ background-color: {BRAND['surface_high']};
                              color: #E6E6E6; border: 1px solid {BRAND['border']}; }}
      .vg-card {{ background-color: {BRAND['surface_high']};
                  border: 1px solid {BRAND['border']}; border-radius: 8px;
                  padding: 14px 18px; margin-bottom: 10px; }}
      .vg-recommended {{ border-color: {BRAND['neon']}; box-shadow: 0 0 0 1px {BRAND['neon']}; }}
      .vg-pill {{ display: inline-block; padding: 2px 8px; margin-right: 6px;
                  border-radius: 999px; background: {BRAND['primary']}; color: #0A0A0A;
                  font-weight: 600; font-size: 12px; }}
      .vg-pill-neon {{ background: {BRAND['neon']}; color: #062F1F; }}
      .vg-trace-call {{ color: {BRAND['neon']}; font-family: ui-monospace, Menlo, monospace;
                        font-size: 12px; }}
      .vg-trace-result {{ color: #B8B8B8; font-family: ui-monospace, Menlo, monospace;
                          font-size: 11px; white-space: pre-wrap; }}
      .vg-footer {{ color: {BRAND['muted']}; text-align: center; font-size: 12px;
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
            <div style="font-size:28px; font-weight:700; color:{BRAND['neon']};
                        letter-spacing:.06em;">VANGUARD</div>
            <div style="color:{BRAND['text_dim']}; font-size:13px;">
              Versatile AFCENT Network Guidance for Air-Land-Sea Routing &amp; Distribution
            </div>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
with hdr_r:
    st.markdown(
        f"""
        <div style="text-align:right; padding-top:6px;">
          <span class="vg-pill">CENTCOM</span>
          <span class="vg-pill vg-pill-neon">TMR Auto</span>
          <div style="color:{BRAND['text_dim']}; font-size:11px; margin-top:6px;">
            Mission frame: LOGCOM "Transportation Movement Request Automation" use case.
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

st.markdown("---")

# ---------------------------------------------------------------------------
# Sidebar: live agent reasoning trace
# ---------------------------------------------------------------------------
with st.sidebar:
    st.markdown(f"### <span style='color:{BRAND['neon']}'>Agent Reasoning</span>",
                unsafe_allow_html=True)
    st.markdown(
        f"<div style='color:{BRAND['text_dim']}; font-size:12px;'>"
        "Live Kamiwaza-deployed model tool-calling trace — every "
        "<code>list_assets()</code>, <code>compute_route()</code>, "
        "<code>check_feasibility()</code>, and <code>compare_options()</code> "
        "the agent fires.</div>",
        unsafe_allow_html=True,
    )
    trace_slot = st.empty()

# ---------------------------------------------------------------------------
# Main area
# ---------------------------------------------------------------------------
left, right = st.columns([0.55, 0.45], gap="large")

with left:
    st.markdown("#### Transportation Movement Request")
    default_q = ("Move 40 pallets of MREs from Camp Arifjan to Erbil within "
                 "72 hours, lowest fuel burn.")
    user_msg = st.text_area("Type a TMR in natural language:",
                            value=default_q, height=110, label_visibility="collapsed")
    examples = [
        "Move 40 pallets of MREs from Camp Arifjan to Erbil within 72 hours, lowest fuel burn.",
        "Push 12 pallets of class IX repair parts from Al Udeid to Diego Garcia by tomorrow night, fastest.",
        "Sealift 800 pallets of palletized water from Jebel Ali to Djibouti within 14 days, cheapest.",
        "Get 24 pallets of class V ammo from Prince Sultan AB to Al Asad within 36 hours, safest.",
    ]
    pick = st.selectbox("Or pick a canned TMR:", examples, index=0,
                        label_visibility="collapsed")
    c1, c2, _ = st.columns([0.25, 0.25, 0.5])
    with c1:
        run_btn = st.button("Plan TMR", type="primary", use_container_width=True)
    with c2:
        if st.button("Use selected", use_container_width=True):
            user_msg = pick
            run_btn = True

with right:
    st.markdown("#### Theater Footprint")
    bases = load_bases()
    assets = load_assets()
    by_mode = assets["mode"].value_counts().to_dict()
    m_air = by_mode.get("air", 0)
    m_sea = by_mode.get("sea", 0)
    m_land = by_mode.get("land", 0)
    st.markdown(
        f"""
        <div class='vg-card'>
          <div style='display:flex; justify-content:space-around; text-align:center;'>
            <div><div style='font-size:24px; color:{BRAND['neon']}; font-weight:700;'>
                  {len(bases)}</div>
                  <div style='color:{BRAND['text_dim']}; font-size:12px;'>Bases</div></div>
            <div><div style='font-size:24px; color:{BRAND['neon']}; font-weight:700;'>
                  {len(assets)}</div>
                  <div style='color:{BRAND['text_dim']}; font-size:12px;'>Assets</div></div>
            <div><div style='font-size:24px; color:{BRAND['primary']}; font-weight:700;'>
                  {m_air}</div>
                  <div style='color:{BRAND['text_dim']}; font-size:12px;'>Air</div></div>
            <div><div style='font-size:24px; color:{BRAND['primary']}; font-weight:700;'>
                  {m_sea}</div>
                  <div style='color:{BRAND['text_dim']}; font-size:12px;'>Sea</div></div>
            <div><div style='font-size:24px; color:{BRAND['primary']}; font-weight:700;'>
                  {m_land}</div>
                  <div style='color:{BRAND['text_dim']}; font-size:12px;'>Ground</div></div>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    map_slot = st.empty()


def render_base_map(highlight_legs: list[dict] | None = None):
    bases_df = bases.copy()
    bases_df["color"] = bases_df["type"].map({
        "air":  [0, 187, 122],
        "sea":  [0, 255, 167],
        "land": [255, 199, 64],
        "joint": [120, 200, 255],
    })
    layers = [
        pdk.Layer(
            "ScatterplotLayer", data=bases_df,
            get_position="[lon, lat]", get_radius=22000, get_fill_color="color",
            opacity=0.85, pickable=True,
        ),
    ]
    if highlight_legs:
        leg_df = pd.DataFrame([{
            "from_lon": l["from_lon"], "from_lat": l["from_lat"],
            "to_lon": l["to_lon"], "to_lat": l["to_lat"],
            "mode": l["mode"],
        } for l in highlight_legs])
        leg_df["color"] = leg_df["mode"].map({
            "air":  [0, 255, 167],
            "sea":  [80, 180, 255],
            "road": [255, 199, 64],
        })
        layers.append(pdk.Layer(
            "LineLayer", data=leg_df,
            get_source_position="[from_lon, from_lat]",
            get_target_position="[to_lon, to_lat]",
            get_color="color", get_width=4,
        ))
    deck = pdk.Deck(
        map_style=None,  # dark void backdrop matches Kamiwaza theme
        initial_view_state=pdk.ViewState(latitude=26.5, longitude=48.0, zoom=3.2),
        layers=layers,
        tooltip={"text": "{name}\n{country} ({type})"},
    )
    map_slot.pydeck_chart(deck, use_container_width=True)


render_base_map()

# Section: results
st.markdown("---")
st.markdown("#### Recommended Course of Action")
result_slot = st.container()
final_slot = st.empty()


def render_options(comparison: dict):
    """Pretty render of compare_options output as 3 cards + ranking table."""
    if "error" in comparison:
        result_slot.error(comparison["error"])
        return
    opts = comparison.get("options", [])
    if not opts:
        result_slot.warning("No options returned.")
        return
    cols = result_slot.columns(len(opts))
    rows = []
    for i, (col, opt) in enumerate(zip(cols, opts)):
        f = opt["feasibility"]
        rec = opt.get("recommended", False)
        css = "vg-card vg-recommended" if rec else "vg-card"
        badge = ('<span class="vg-pill vg-pill-neon">RECOMMENDED</span>'
                 if rec else "")
        feas_pill = ('<span class="vg-pill">FEASIBLE</span>'
                     if f["feasible_time"]
                     else '<span class="vg-pill" '
                          'style="background:#aa3333;color:#fff;">OVER DEADLINE</span>')
        col.markdown(
            f"""
            <div class='{css}'>
              <div style="display:flex; justify-content:space-between; align-items:center;">
                <div style="font-weight:700; font-size:16px; color:{BRAND['neon']};">
                  {opt['label']}</div>
                <div>{badge}</div>
              </div>
              <div style="color:{BRAND['text_dim']}; font-size:12px; margin-bottom:8px;">
                {opt['asset_class']}
              </div>
              <div style="font-size:13px; line-height:1.7;">
                <b>Sorties:</b> {f['sorties_required']}<br/>
                <b>Total time:</b> {f['total_hours']:.1f} h
                  / deadline {f['deadline_hours']:.0f} h<br/>
                <b>Distance:</b> {opt['route']['total_distance_nm']:.0f} nm
                  ({opt['route']['leg_count']} leg(s),
                  {'+'.join(opt['route']['modes_used'])})<br/>
                <b>Fuel burn:</b> {f['fuel_lb']:,.0f} lb
                  (~${f['fuel_cost_usd']:,.0f})<br/>
                <b>Risk:</b> {f['risk_score_0_1']:.2f} / 1.00
              </div>
              <div style="margin-top:8px;">{feas_pill}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        rows.append({
            "Option": opt["label"], "Sorties": f["sorties_required"],
            "Hours": round(f["total_hours"], 1),
            "Distance (nm)": opt["route"]["total_distance_nm"],
            "Fuel cost ($)": round(f["fuel_cost_usd"]),
            "Risk": f["risk_score_0_1"],
            "Score": opt["score"],
            "Recommended": "YES" if opt.get("recommended") else "",
        })
    result_slot.dataframe(pd.DataFrame(rows), use_container_width=True,
                          hide_index=True)
    # Highlight legs of recommended option on the map
    rec = next((o for o in opts if o.get("recommended")), opts[0])
    render_base_map(rec["route"]["legs"])


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
                    f"<div style='color:#CFCFCF; margin:6px 0; font-style:italic;'>"
                    f"thinking &gt; {ev['content'][:280]}</div>")
        elif ev["type"] == "tool_call":
            args = json.dumps(ev["arguments"], separators=(",", ":"))[:160]
            parts.append(
                f"<div class='vg-trace-call'>→ {ev['name']}({args})</div>")
        elif ev["type"] == "tool_result":
            r = ev["result"]
            if isinstance(r, dict):
                if "matched" in r:
                    summary = (f"matched={r.get('matched')} "
                               f"returned={r.get('returned')}")
                elif "options" in r:
                    summary = f"options={len(r['options'])}"
                elif "legs" in r:
                    summary = (f"legs={len(r['legs'])} "
                               f"dist={r.get('total_distance_nm')}nm")
                elif "feasible_time" in r:
                    summary = (f"feasible={r['feasible_time']} "
                               f"hrs={r['total_hours']} sorties={r['sorties_required']}")
                elif "error" in r:
                    summary = f"error: {r['error'][:80]}"
                else:
                    summary = "ok"
            else:
                summary = str(r)[:80]
            parts.append(
                f"<div class='vg-trace-result'>  ← {summary} ({ev['ms']} ms)</div>")
        elif ev["type"] == "final":
            parts.append(
                f"<div style='color:{BRAND['neon']}; margin-top:8px; "
                f"border-top:1px solid {BRAND['border']}; padding-top:6px;'>"
                f"finish_reason=stop</div>")
    trace_slot.markdown("".join(parts), unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Run the agent
# ---------------------------------------------------------------------------
if run_btn and user_msg.strip():
    events: list[dict] = []
    last_compare: dict | None = None
    with st.spinner("VANGUARD agent planning..."):
        try:
            for ev in stream_run(user_msg):
                events.append(ev)
                render_trace(events)
                if ev["type"] == "tool_result" and ev["name"] == "compare_options":
                    last_compare = ev["result"]
                if ev["type"] == "final":
                    final_slot.markdown(
                        f"<div class='vg-card' style='border-color:{BRAND['neon']};'>"
                        f"<div style='color:{BRAND['neon']}; font-weight:700; "
                        f"margin-bottom:6px;'>VANGUARD recommends:</div>"
                        f"<div style='color:#E6E6E6; line-height:1.6;'>"
                        f"{ev['content']}</div></div>",
                        unsafe_allow_html=True,
                    )
        except Exception as e:  # noqa: BLE001
            st.error(f"Agent error: {e}")
    if last_compare:
        render_options(last_compare)

st.markdown(
    f"<div class='vg-footer'>"
    f"Powered by Kamiwaza &nbsp;|&nbsp; "
    f"<code>KAMIWAZA_BASE_URL</code> swap &rarr; on-prem inference, "
    f"100% data containment.</div>",
    unsafe_allow_html=True,
)
