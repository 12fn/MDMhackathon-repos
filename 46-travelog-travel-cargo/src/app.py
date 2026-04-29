"""TRAVELOG — Streamlit mono UI on port 3046.

Run:
    streamlit run src/app.py --server.port 3046 \\
      --server.headless true --server.runOnSave false \\
      --server.fileWatcherType none --browser.gatherUsageStats false

Three buttons. That's the workflow:
    [ View Options ]   [ Submit Both ]   [ Print Brief ]
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import folium
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from streamlit_folium import st_folium

APP_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = APP_ROOT.parents[1]
for p in (str(REPO_ROOT), str(APP_ROOT)):
    if p not in sys.path:
        sys.path.insert(0, p)

from shared.kamiwaza_client import BRAND  # noqa: E402
from src import agent  # noqa: E402
from src.tools import (  # noqa: E402
    load_nodes,
    load_scenarios,
)


# ──────────────────────────────────────────────────────────────────────────────
# Page config + brand
# ──────────────────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="TRAVELOG — PCS Travel + Cargo + LogTRACE",
    layout="wide",
    initial_sidebar_state="expanded",
)

CSS = f"""
<style>
  .stApp {{ background: {BRAND['bg']}; color: #E8E8E8; }}
  section[data-testid="stSidebar"] {{
    background: {BRAND['surface']};
    border-right: 1px solid {BRAND['border']};
  }}
  h1, h2, h3, h4 {{ color: #FFFFFF !important; letter-spacing: 0.4px; }}
  .tl-header {{ display:flex; justify-content:space-between;
                align-items:center; border-bottom:1px solid {BRAND['border']};
                padding:8px 0 14px 0; margin-bottom:10px; }}
  .tl-codename {{ color:{BRAND['primary']}; font-weight:800; letter-spacing:1px; }}
  .tl-tag {{ color:{BRAND['neon']}; font-size:12px; letter-spacing:1.5px;
             text-transform:uppercase; }}
  .tl-card {{ background:{BRAND['surface']}; border:1px solid {BRAND['border']};
              border-radius:10px; padding:14px 18px; margin-bottom:10px; }}
  .tl-pill {{ display:inline-block; padding:3px 10px; border-radius:999px;
              font-size:11px; font-weight:700; letter-spacing:0.6px;
              margin-right:6px; }}
  .pill-ok   {{ background:#0E2F22; color:#00FFA7; border:1px solid #00BB7A; }}
  .pill-warn {{ background:#3A2C0E; color:#E0B341; border:1px solid #E0B341; }}
  .pill-no   {{ background:#3A0E0E; color:#FF6F66; border:1px solid #D8362F; }}
  .tl-source-row {{ display:flex; align-items:center; gap:8px; padding:5px 0;
                    color:#7E7E7E; font-size:12px; font-family:Menlo,monospace; }}
  .tl-pulse  {{ width:8px; height:8px; border-radius:50%; background:#00FFA7;
                box-shadow:0 0 8px #00FFA7; animation:tl-pulse 1.6s infinite; }}
  @keyframes tl-pulse {{ 0%,100% {{ opacity:1; }} 50% {{ opacity:0.35; }} }}
  .tl-metric {{ background:{BRAND['surface']}; border:1px solid {BRAND['border']};
                border-radius:6px; padding:12px 16px; }}
  .tl-metric-label {{ color:#7E7E7E; font-size:11px; text-transform:uppercase;
                      letter-spacing:1.5px; }}
  .tl-metric-value {{ color:#00FFA7; font-size:26px; font-weight:700;
                      font-family:Menlo,monospace; line-height:1.2;
                      margin-top:4px; }}
  .tl-brief {{ font-family:-apple-system,BlinkMacSystemFont,'Inter',sans-serif;
               white-space:pre-wrap; color:#E8E8E8; background:#0A0A0A;
               border:1px solid #00BB7A33; padding:18px; border-radius:6px;
               line-height:1.6; font-size:14px; }}
  .stButton button {{
      background: {BRAND['primary']} !important; color:#0A0A0A !important;
      font-weight:700 !important; border:0 !important; letter-spacing:0.6px !important;
  }}
  .stButton button:hover {{ background: {BRAND['primary_hover']} !important; }}
  .tl-rec-card {{ background:#0A1410; border:1px solid #00FFA7;
                  border-radius:10px; padding:14px 18px; margin-bottom:10px; }}
  .tl-recommended-pill {{ background:#00FFA7; color:#0A0A0A; padding:2px 10px;
                          border-radius:999px; font-weight:800; font-size:11px;
                          letter-spacing:0.8px; }}
  .tl-footer {{ color:{BRAND['muted']}; text-align:center; margin-top:30px;
                padding:14px; border-top:1px solid {BRAND['border']};
                font-size:12px; letter-spacing:1.2px; text-transform:uppercase; }}
  div[data-testid="stMetricValue"] {{ color:{BRAND['neon']} !important; }}
</style>
"""
st.markdown(CSS, unsafe_allow_html=True)


# ──────────────────────────────────────────────────────────────────────────────
# Header
# ──────────────────────────────────────────────────────────────────────────────
st.markdown(
    f"""
    <div class='tl-header'>
      <div>
        <span style='font-size:30px;font-weight:800'>
          <span class='tl-codename'>TRAVELOG</span>
        </span><br/>
        <span class='tl-tag'>DTS &middot; AFCENT &middot; BTS NTAD &middot; LaDe &middot; Travel + Cargo + LogTRACE</span>
      </div>
      <div style='text-align:right;color:#7E7E7E;font-size:12px;'>
        Agent #46 &middot; USMC LOGCOM CDAO @ MDM 2026<br/>
        <span style='color:{BRAND['neon']}'>One sentence in. Travel + cargo plan out. Built on the Kamiwaza Stack.</span>
      </div>
    </div>
    """,
    unsafe_allow_html=True,
)


# ──────────────────────────────────────────────────────────────────────────────
# Cached loaders
# ──────────────────────────────────────────────────────────────────────────────
@st.cache_data(show_spinner=False)
def _scenarios() -> list[dict]:
    return load_scenarios()


@st.cache_data(show_spinner=False)
def _nodes() -> list[dict]:
    return load_nodes()


@st.cache_data(show_spinner=False)
def _manifest() -> dict:
    p = APP_ROOT / "data" / "manifest.json"
    return json.loads(p.read_text()) if p.exists() else {}


@st.cache_data(show_spinner=False)
def _cached_briefs() -> dict:
    return agent.load_cached_briefs()


scenarios = _scenarios()
nodes = _nodes()
manifest = _manifest()
cached_briefs = _cached_briefs()


# ──────────────────────────────────────────────────────────────────────────────
# Sidebar: scenario picker, live ingest, KAMIWAZA env-var beat
# ──────────────────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown(
        f"<div class='tl-tag'>{BRAND['footer']}</div>"
        f"<div style='font-weight:800;font-size:24px;color:#FFFFFF;margin-top:4px'>TRAVELOG</div>"
        f"<div style='color:{BRAND['text_dim']};font-size:12px;margin-top:6px'>"
        "Combined PCS travel + cargo planner.<br/>"
        "Pre-fills DTS authorization AND TMR<br/>from a single Marine sentence."
        "</div>",
        unsafe_allow_html=True,
    )
    st.markdown("---")

    st.markdown("### PCS Scenario")
    scenario_options = {
        f"{s['scenario_id']} — {s['traveler_grade']} "
        f"{s['traveler_name'].split(',')[0]} ({s['origin_id']}→{s['dest_id']})": s
        for s in scenarios
    }
    # Preselect a hero scenario (PCS-002 — drive escort, motor pool item)
    keys = list(scenario_options.keys())
    default_idx = next((i for i, k in enumerate(keys)
                        if k.startswith("PCS-002")), 0)
    scenario_label = st.selectbox(
        "Pick a Marine's PCS request",
        keys,
        index=default_idx,
    )
    scenario = scenario_options[scenario_label]

    st.markdown("---")
    st.markdown("### Live Ingest")
    st.markdown("<div class='tl-card'>", unsafe_allow_html=True)
    sources = manifest.get("datasets_simulated", [
        "DTS authorizations (synthetic, JTR-aligned)",
        "AFCENT Logistics Data",
        "Bureau of Transportation Statistics (BTS NTAD)",
        "Last Mile Delivery (LaDe)",
    ])
    for src in sources:
        st.markdown(
            f"<div class='tl-source-row'>"
            f"<span class='tl-pulse'></span>{src}</div>",
            unsafe_allow_html=True,
        )
    st.markdown("</div>", unsafe_allow_html=True)

    st.markdown(
        f"<div style='color:#6A6969;font-size:11px;line-height:1.7'>"
        f"PCS scenarios: <span style='color:#00BB7A'>{manifest.get('scenarios','—')}</span><br/>"
        f"DTS records: <span style='color:#00BB7A'>{manifest.get('dts_records','—')}</span><br/>"
        f"BTS nodes: <span style='color:#00BB7A'>{manifest.get('bts_nodes','—')}</span><br/>"
        f"BTS edges: <span style='color:#00BB7A'>{manifest.get('bts_edges','—')}</span><br/>"
        f"LaDe records: <span style='color:#00BB7A'>{manifest.get('lade_records','—')}</span>"
        f"</div>",
        unsafe_allow_html=True,
    )

    st.markdown("---")
    st.markdown(
        f"<div class='tl-tag'>On-prem deployment</div>"
        f"<div style='font-family:Menlo,monospace;color:#E8E8E8;font-size:12px;background:#000;padding:8px 10px;border-radius:6px;border:1px solid {BRAND['border']};margin-top:6px'>"
        "$ export KAMIWAZA_BASE_URL=\\<br/>"
        "&nbsp;&nbsp;https://kamiwaza.{installation}.usmc.mil<br/>"
        "$ streamlit run src/app.py</div>"
        f"<div style='color:#7E7E7E;font-size:11px;margin-top:8px;line-height:1.5'>"
        "Air-gapped. CUI never leaves the perimeter. IL5/IL6 ready."
        "</div>",
        unsafe_allow_html=True,
    )


# ──────────────────────────────────────────────────────────────────────────────
# The 3-button workflow
# ──────────────────────────────────────────────────────────────────────────────
st.markdown(
    f"<div class='tl-card'>"
    f"<div style='color:#7E7E7E;font-size:12px;letter-spacing:1.5px;text-transform:uppercase'>Marine PCS intent</div>"
    f"<div style='color:#FFFFFF;font-size:18px;margin-top:6px;font-style:italic'>"
    f"&ldquo;{scenario['prompt']}&rdquo;"
    f"</div></div>",
    unsafe_allow_html=True,
)

c1, c2, c3 = st.columns(3)
with c1:
    btn_view = st.button("View Options", use_container_width=True,
                         type="primary", key="btn_view")
with c2:
    btn_submit = st.button("Submit Both", use_container_width=True,
                           type="primary", key="btn_submit")
with c3:
    btn_brief = st.button("Print Brief", use_container_width=True,
                          type="primary", key="btn_brief")


# ──────────────────────────────────────────────────────────────────────────────
# Session state
# ──────────────────────────────────────────────────────────────────────────────
if "view" not in st.session_state:
    st.session_state.view = "idle"
if "plan" not in st.session_state:
    st.session_state.plan = None
if "active_sid" not in st.session_state:
    st.session_state.active_sid = None

# Reset plan when user switches scenario
if st.session_state.active_sid != scenario["scenario_id"]:
    st.session_state.active_sid = scenario["scenario_id"]
    st.session_state.plan = None
    st.session_state.view = "idle"


def _ensure_plan() -> dict:
    if st.session_state.plan is None:
        with st.spinner("Running 3-pipeline merge: travel + cargo + last-mile..."):
            st.session_state.plan = agent.deterministic_plan(scenario["scenario_id"])
    return st.session_state.plan


if btn_view:
    _ensure_plan()
    st.session_state.view = "options"

if btn_submit:
    _ensure_plan()
    st.session_state.view = "submit"

if btn_brief:
    _ensure_plan()
    st.session_state.view = "brief"


# ──────────────────────────────────────────────────────────────────────────────
# View: idle
# ──────────────────────────────────────────────────────────────────────────────
if st.session_state.view == "idle":
    st.markdown("#### Three-Button Workflow")
    st.markdown(
        f"<div class='tl-card' style='color:#7E7E7E;line-height:1.7'>"
        f"TRAVELOG ingests <b style='color:#00FFA7'>4 datasets</b> "
        "(synthetic DTS + AFCENT logistics + BTS NTAD multimodal corridor "
        "+ LaDe last-mile), runs a "
        "<b style='color:#00FFA7'>3-pipeline merge</b> in one agent, and "
        "produces a single combined action plan that pre-fills both the "
        "<b style='color:#00FFA7'>DTS travel voucher</b> AND the "
        "<b style='color:#00FFA7'>cargo TMR</b>.<br/><br/>"
        "Today: a Marine doing a PCS opens DTS for travel, GCSS-MC for cargo, "
        "and emails their S-1 for paperwork. Three different systems. "
        "TRAVELOG collapses that to one sentence in, one plan out.<br/><br/>"
        "Click <b style='color:#00BB7A'>View Options</b> to see the 4-mode "
        "comparison. Then <b style='color:#00BB7A'>Submit Both</b> to fire "
        "the DTS + TMR pre-fills via real OpenAI tool-calling. Finally "
        "<b style='color:#00BB7A'>Print Brief</b> for the cached hero brief."
        "</div>",
        unsafe_allow_html=True,
    )
    cols = st.columns(3)
    for col, (lbl, color, blurb) in zip(cols, [
        ("PIPELINE 1 · TRAVEL", "#00FFA7",
         "DTS authorization pre-fill · JTR-compliant per-diem · GTCC."),
        ("PIPELINE 2 · CARGO", "#FFB347",
         "TMR auto-submit · DTR 4500.9-R · installation policy validation."),
        ("PIPELINE 3 · LAST-MILE", "#56C5FF",
         "LaDe-shape pickup → delivery to receiving unit · GCSS-MC sync."),
    ]):
        with col:
            st.markdown(
                f"<div class='tl-card' style='border-color:{color}55'>"
                f"<div style='color:{color};font-weight:700;letter-spacing:1.5px;font-size:13px'>"
                f"&#9632; {lbl}</div>"
                f"<div style='color:#E8E8E8;font-size:13px;margin-top:6px;line-height:1.5'>{blurb}</div>"
                f"</div>",
                unsafe_allow_html=True,
            )


# ──────────────────────────────────────────────────────────────────────────────
# Helpers — Folium route map & Plotly cost bar / Gantt
# ──────────────────────────────────────────────────────────────────────────────
def _route_map(plan: dict, mode_key_filter: str | None = None) -> folium.Map:
    """Render a Folium map with the BTS NTAD nodes + recommended route legs."""
    nb = {n["id"]: n for n in nodes}
    scn = plan["scenario"]
    o, d = nb[scn["origin_id"]], nb[scn["dest_id"]]
    center_lat = (o["lat"] + d["lat"]) / 2
    center_lon = (o["lon"] + d["lon"]) / 2
    # Make sure WESTPAC trans-Pacific routes still center reasonably
    if abs(o["lon"] - d["lon"]) > 180:
        center_lon = ((o["lon"] + d["lon"] + 360) / 2) % 360 - 180
    fm = folium.Map(
        location=[center_lat, center_lon], zoom_start=3,
        tiles="CartoDB dark_matter",
    )
    # Plot all nodes lightly
    for n in nodes:
        folium.CircleMarker(
            [n["lat"], n["lon"]], radius=3, color="#444",
            fill=True, fill_opacity=0.6, weight=1,
            tooltip=n["name"],
        ).add_to(fm)
    # Highlight origin + destination
    for label, n_, color in [("Origin", o, "#00FFA7"), ("Destination", d, "#56C5FF")]:
        folium.Marker(
            [n_["lat"], n_["lon"]],
            icon=folium.Icon(color="green" if label == "Origin" else "blue"),
            tooltip=f"{label}: {n_['name']}",
        ).add_to(fm)
    # Plot recommended route
    rec = next((o for o in plan["comparison"]["options"]
                if o.get("recommended")), None)
    if rec:
        mode_color = {"road": "#00FFA7", "rail": "#FFB347",
                      "air": "#56C5FF", "sea": "#FF66BB"}
        for leg in rec["pax_legs"]:
            f_ = nb[leg["from"]]; t_ = nb[leg["to"]]
            folium.PolyLine(
                [(f_["lat"], f_["lon"]), (t_["lat"], t_["lon"])],
                color=mode_color.get(leg["mode"], "#888"),
                weight=4, opacity=0.9,
                tooltip=f"PAX · {leg['mode']} · {leg['distance_mi']:.0f} mi",
            ).add_to(fm)
        # Cargo legs (dashed)
        if rec["cargo_legs"] != rec["pax_legs"]:
            for leg in rec["cargo_legs"]:
                f_ = nb[leg["from"]]; t_ = nb[leg["to"]]
                folium.PolyLine(
                    [(f_["lat"], f_["lon"]), (t_["lat"], t_["lon"])],
                    color=mode_color.get(leg["mode"], "#888"),
                    weight=3, opacity=0.6,
                    dash_array="6,8",
                    tooltip=f"CARGO · {leg['mode']} · {leg['distance_mi']:.0f} mi",
                ).add_to(fm)
    return fm


def _cost_bar(comparison: dict) -> go.Figure:
    opts = comparison["options"]
    labels = [o["label"] for o in opts]
    pax = [o["pax_cost_usd"] for o in opts]
    cargo = [o["cargo_cost_usd"] for o in opts]
    pd_ = [o["per_diem_usd"] for o in opts]
    fig = go.Figure()
    fig.add_trace(go.Bar(name="Pax travel", x=labels, y=pax, marker_color="#00BB7A"))
    fig.add_trace(go.Bar(name="Cargo move", x=labels, y=cargo, marker_color="#FFB347"))
    fig.add_trace(go.Bar(name="Per-diem (JTR)", x=labels, y=pd_, marker_color="#56C5FF"))
    rec_idx = next((i for i, o in enumerate(opts) if o.get("recommended")), -1)
    if rec_idx >= 0:
        fig.add_annotation(
            x=labels[rec_idx],
            y=pax[rec_idx] + cargo[rec_idx] + pd_[rec_idx] + 250,
            text="<b>★ Recommended</b>", showarrow=False,
            font=dict(color="#00FFA7", size=14),
        )
    fig.update_layout(
        barmode="stack",
        paper_bgcolor=BRAND["bg"], plot_bgcolor=BRAND["bg"],
        font=dict(color="#E8E8E8"),
        title="Total cost by mode (stacked: pax + cargo + per-diem)",
        xaxis=dict(tickangle=-15),
        yaxis=dict(title="USD", gridcolor="#222"),
        height=380, margin=dict(l=20, r=20, t=50, b=80),
        legend=dict(orientation="h", y=-0.25),
    )
    return fig


def _gantt(plan: dict) -> go.Figure:
    """Lead-time Gantt for the recommended option's travel + cargo + last-mile."""
    scn = plan["scenario"]
    voucher = plan["voucher"]
    tmr = plan["tmr"]
    lm = plan["last_mile"]
    rec = next((o for o in plan["comparison"]["options"]
                if o.get("recommended")), None)
    rows = []
    # Travel bar
    rows.append({"Task": "Travel (Marine)",
                 "Start": voucher["trip_start"],
                 "Finish": voucher["trip_end"],
                 "Color": "#00BB7A"})
    # Cargo bar (RDD = end)
    cargo_start_iso = voucher["trip_start"]
    rows.append({"Task": "Cargo movement (TMR)",
                 "Start": cargo_start_iso,
                 "Finish": tmr["rdd"],
                 "Color": "#FFB347"})
    # Last-mile (LaDe)
    rows.append({"Task": "Last-mile (LaDe)",
                 "Start": lm["eta_pickup"][:10],
                 "Finish": lm["eta_delivery"][:10],
                 "Color": "#56C5FF"})
    fig = go.Figure()
    for r in rows:
        fig.add_trace(go.Bar(
            x=[(pd.to_datetime(r["Finish"]) - pd.to_datetime(r["Start"])).days
               or 1],
            y=[r["Task"]],
            base=[pd.to_datetime(r["Start"])],
            orientation="h",
            marker=dict(color=r["Color"], line=dict(color="#0A0A0A", width=1)),
            name=r["Task"],
            hovertemplate=f"{r['Task']}: {r['Start']} → {r['Finish']}",
        ))
    fig.update_layout(
        paper_bgcolor=BRAND["bg"], plot_bgcolor=BRAND["bg"],
        font=dict(color="#E8E8E8"),
        title="Lead-time Gantt — recommended mode",
        xaxis=dict(type="date", gridcolor="#222"),
        yaxis=dict(autorange="reversed"),
        height=260, margin=dict(l=20, r=20, t=50, b=20),
        showlegend=False, barmode="overlay",
    )
    return fig


# ──────────────────────────────────────────────────────────────────────────────
# View: options — 4-mode comparison with route map + cost chart
# ──────────────────────────────────────────────────────────────────────────────
if st.session_state.view == "options" and st.session_state.plan:
    plan = st.session_state.plan
    comp = plan["comparison"]
    rec = next((o for o in comp["options"] if o.get("recommended")), None)

    m1, m2, m3, m4 = st.columns(4)
    metrics = [
        ("Recommended Mode",
         (rec["label"].split("(")[0].strip() if rec else "—")),
        ("Total Cost",
         f"${rec['total_cost_usd']:,.0f}" if rec else "—"),
        ("Combined Time",
         f"{rec['combined_time_hr']:.0f} hr" if rec else "—"),
        ("Cargo Lead Time",
         f"{rec['cargo_lead_hr']:.0f} hr" if rec else "—"),
    ]
    for col, (lbl, val) in zip([m1, m2, m3, m4], metrics):
        with col:
            st.markdown(
                f"<div class='tl-metric'>"
                f"<div class='tl-metric-label'>{lbl}</div>"
                f"<div class='tl-metric-value'>{val}</div></div>",
                unsafe_allow_html=True,
            )

    st.markdown("&nbsp;", unsafe_allow_html=True)
    left, right = st.columns([3, 2])
    with left:
        st.markdown("#### BTS NTAD route map")
        st_folium(_route_map(plan), width=None, height=420,
                  returned_objects=[])
        st.caption(
            "Solid line = pax route; dashed line = cargo route. "
            "Mode color: green road · orange rail · blue air · pink sea.")
    with right:
        st.markdown("#### Mode comparison — cost stack")
        st.plotly_chart(_cost_bar(comp), use_container_width=True,
                        config={"displayModeBar": False})

    st.markdown("#### 4-Mode Comparison Table")
    rows = []
    for o in comp["options"]:
        rows.append({
            "Mode": o["label"],
            "Combined time (h)": round(o["combined_time_hr"], 1),
            "Total cost": o["total_cost_usd"],
            "Pax cost": o["pax_cost_usd"],
            "Cargo cost": o["cargo_cost_usd"],
            "Per-diem (JTR)": o["per_diem_usd"],
            "Fuel (gal)": round(o["fuel_gal"], 0),
            "Cargo lead (h)": round(o["cargo_lead_hr"], 1),
            "Score": o.get("score", 0),
            "Recommended": "★" if o.get("recommended") else "",
        })
    df = pd.DataFrame(rows)
    st.dataframe(
        df, use_container_width=True, hide_index=True,
        column_config={
            "Total cost":    st.column_config.NumberColumn(format="$%.0f"),
            "Pax cost":      st.column_config.NumberColumn(format="$%.0f"),
            "Cargo cost":    st.column_config.NumberColumn(format="$%.0f"),
            "Per-diem (JTR)": st.column_config.NumberColumn(format="$%.0f"),
            "Score":         st.column_config.ProgressColumn(
                format="%.3f", min_value=0.0, max_value=1.5),
        },
    )


# ──────────────────────────────────────────────────────────────────────────────
# View: submit — DTS voucher card + TMR card + last-mile + validation
# ──────────────────────────────────────────────────────────────────────────────
if st.session_state.view == "submit" and st.session_state.plan:
    plan = st.session_state.plan
    voucher = plan["voucher"]
    tmr = plan["tmr"]
    lm = plan["last_mile"]
    val = plan["validation"]

    # Verdict badge
    badge_class = {"OK": "pill-ok", "WARN": "pill-warn",
                   "BLOCKED": "pill-no"}.get(val["verdict"], "pill-warn")
    st.markdown(
        f"<div style='margin-bottom:10px'>"
        f"<span class='tl-pill {badge_class}'>CROSS-VALIDATION: {val['verdict']}</span>"
        f"<span style='color:#7E7E7E;font-size:13px;margin-left:8px'>"
        f"{len(val['issues'])} issue(s) · {len(val['notes'])} note(s)</span>"
        f"</div>",
        unsafe_allow_html=True,
    )

    cA, cB = st.columns(2)
    with cA:
        st.markdown("#### DTS Travel Voucher Pre-Fill")
        st.markdown(
            f"<div class='tl-rec-card'>"
            f"<span class='tl-recommended-pill'>PIPELINE 1 · TRAVEL</span>"
            f"<div style='font-family:Menlo,monospace;color:#FFFFFF;font-size:18px;margin-top:8px'>"
            f"{voucher['doc_number']}"
            f"</div>"
            f"<div style='color:#7E7E7E;font-size:12px;margin-top:2px'>"
            f"TA {voucher['ta_number']}</div>"
            f"<div style='color:#E8E8E8;font-size:13px;margin-top:10px;line-height:1.7'>"
            f"<b>{voucher['traveler_grade']} {voucher['traveler_name']}</b>  "
            f"<span style='color:#7E7E7E'>(EDIPI {voucher['traveler_edipi']})</span><br/>"
            f"AO: {voucher['ao_name']}<br/>"
            f"Trip: {voucher['trip_start']} → {voucher['trip_end']} "
            f"({voucher['nights']} nights @ {voucher['tdy_city']})<br/>"
            f"Mode of travel: <b style='color:#00FFA7'>{voucher['mode_of_travel']}</b>"
            f"</div>"
            f"<hr style='border:0;border-top:1px solid #222;margin:10px 0'/>"
            f"<div style='color:#E8E8E8;font-size:13px;line-height:1.7'>"
            f"Lodging: ${voucher['lodging_total_usd']:,.2f} "
            f"(${voucher['per_diem_lodging_ceiling_usd']}/night)<br/>"
            f"M&IE: ${voucher['mie_total_usd']:,.2f} "
            f"(${voucher['per_diem_mie_usd']}/day)<br/>"
            f"Incidentals: ${voucher['incidentals_usd']:,.2f}<br/>"
            f"<b style='color:#00FFA7'>Total authorized: ${voucher['total_authorized_usd']:,.2f}</b>"
            f"</div>"
            f"<div style='color:#7E7E7E;font-size:11px;margin-top:8px;font-style:italic'>"
            f"Authority: {voucher['per_diem_authority']}<br/>"
            f"GTCC: {voucher['gtcc_authority']}<br/>"
            f"Status: <b style='color:#00FFA7'>{voucher['status']}</b>"
            f"</div>"
            f"</div>",
            unsafe_allow_html=True,
        )
    with cB:
        st.markdown("#### Cargo TMR Pre-Fill")
        tmr_status_color = "#00FFA7" if tmr["status"] == "ROUTED-TO-AO" else "#FFB347"
        st.markdown(
            f"<div class='tl-rec-card' style='border-color:{tmr_status_color}'>"
            f"<span class='tl-recommended-pill' style='background:{tmr_status_color}'>"
            f"PIPELINE 2 · CARGO</span>"
            f"<div style='font-family:Menlo,monospace;color:#FFFFFF;font-size:18px;margin-top:8px'>"
            f"{tmr['tcn']}"
            f"</div>"
            f"<div style='color:#7E7E7E;font-size:12px;margin-top:2px'>"
            f"Authority: {tmr['routing_authority']}</div>"
            f"<div style='color:#E8E8E8;font-size:13px;margin-top:10px;line-height:1.7'>"
            f"Origin: <b>{tmr['origin_name']}</b><br/>"
            f"Dest: <b>{tmr['dest_name']}</b><br/>"
            f"Asset: <b style='color:#00FFA7'>{tmr['asset_class']}</b> "
            f"({tmr['mode']})<br/>"
            f"Cargo: {tmr['cargo_lbs']:,} lbs"
            + (f" + <b>{tmr['motor_pool_item']}</b>" if tmr.get('motor_pool_item') else "")
            + f"<br/>"
            f"RDD: <b>{tmr['rdd']}</b>"
            f"</div>"
            f"<hr style='border:0;border-top:1px solid #222;margin:10px 0'/>"
            f"<div style='color:#E8E8E8;font-size:13px;line-height:1.7'>"
            f"Last-mile (LaDe-shape):<br/>"
            f"&nbsp;&nbsp;Courier: {lm['courier']}<br/>"
            f"&nbsp;&nbsp;Pickup: {lm['eta_pickup'][:10]}<br/>"
            f"&nbsp;&nbsp;Delivery: {lm['eta_delivery'][:10]} → {lm['receiving_unit']}"
            f"</div>"
            f"<div style='color:#7E7E7E;font-size:11px;margin-top:8px;font-style:italic'>"
            f"Status: <b style='color:{tmr_status_color}'>{tmr['status']}</b><br/>"
            f"Policy cap: {tmr['policy_cap_lbs']:,} lbs"
            f"</div>"
            f"</div>",
            unsafe_allow_html=True,
        )

    st.markdown("#### Lead-time Gantt — travel + cargo + last-mile")
    st.plotly_chart(_gantt(plan), use_container_width=True,
                    config={"displayModeBar": False})

    if val["issues"] or val["notes"]:
        st.markdown("#### Cross-validation findings")
        st.markdown("<div class='tl-card'>", unsafe_allow_html=True)
        for issue in val["issues"]:
            st.markdown(
                f"<div style='color:#FFB347'>&#9888; {issue}</div>",
                unsafe_allow_html=True,
            )
        for note in val["notes"]:
            st.markdown(
                f"<div style='color:#00FFA7'>&#10003; {note}</div>",
                unsafe_allow_html=True,
            )
        st.markdown("</div>", unsafe_allow_html=True)

    # Optional: live tool-calling agent trace (real OpenAI tool-calling)
    st.markdown("---")
    with st.expander("Run live tool-calling agent (real OpenAI tool-calling)"):
        st.caption(
            "Watch the model call compare_modes → prefill_dts_voucher → "
            "submit_tmr → plan_last_mile_push → cross_validate_plan in sequence."
        )
        if st.button("Run agent", key="btn_run_agent"):
            trace_box = st.container()
            with st.spinner("Tool-calling agent running..."):
                try:
                    for ev in agent.stream_run(scenario["prompt"], hero=False):
                        if ev["type"] == "tool_call":
                            trace_box.markdown(
                                f"<div class='tl-source-row'>"
                                f"<span style='color:#00FFA7'>tool_call</span> "
                                f"<b>{ev['name']}</b> "
                                f"<span style='color:#7E7E7E'>{json.dumps(ev['arguments'])[:120]}</span>"
                                f"</div>", unsafe_allow_html=True,
                            )
                        elif ev["type"] == "tool_result":
                            r = ev["result"]
                            preview = (json.dumps(r, default=str)[:160]
                                       if isinstance(r, dict) else str(r)[:160])
                            trace_box.markdown(
                                f"<div class='tl-source-row'>"
                                f"<span style='color:#FFB347'>tool_result</span> "
                                f"<b>{ev['name']}</b> "
                                f"<span style='color:#7E7E7E'>{preview}…</span>"
                                f"</div>", unsafe_allow_html=True,
                            )
                        elif ev["type"] == "final":
                            trace_box.markdown(
                                f"<div class='tl-card' style='border-color:#00FFA7'>"
                                f"<div style='color:#00FFA7;font-size:11px;letter-spacing:1.5px;text-transform:uppercase'>Agent BLUF</div>"
                                f"<div style='color:#E8E8E8;font-size:14px;margin-top:6px;white-space:pre-wrap'>{ev['content']}</div>"
                                f"</div>", unsafe_allow_html=True,
                            )
                except Exception as e:
                    trace_box.error(f"Agent error: {e}")


# ──────────────────────────────────────────────────────────────────────────────
# View: brief — hero combined action plan (cache-first)
# ──────────────────────────────────────────────────────────────────────────────
if st.session_state.view == "brief":
    sid = scenario["scenario_id"]
    cached = cached_briefs.get(sid)

    payload = cached if cached else agent.generate_brief(sid, hero=False)
    source_labels = {
        "gpt-5.4":                "Hero model (Kamiwaza-deployed)",
        "gpt-5.4-mini":           "Standard model (Kamiwaza-deployed)",
        "default-chain":          "Standard model (Kamiwaza-deployed)",
        "deterministic-fallback": "Deterministic baseline",
    }
    source_label = source_labels.get(payload.get("source", ""),
                                      "Cached (pre-computed at ingest)")
    st.markdown(
        f"<div class='tl-card' style='border-color:#00FFA7'>"
        f"<div style='color:#00FFA7;font-size:11px;letter-spacing:1.5px;text-transform:uppercase'>"
        f"Combined Travel + Cargo Action Plan"
        f"</div>"
        f"<div style='font-family:Menlo,monospace;font-size:18px;color:#FFFFFF;margin-top:4px'>"
        f"{payload.get('traveler_grade','')} {payload.get('traveler','')} "
        f"&middot; {payload.get('origin','')} → {payload.get('dest','')}"
        f"</div>"
        f"<div style='color:#7E7E7E;font-size:11px;margin-top:6px'>"
        f"Source: <span style='color:#00FFA7'>{source_label}</span> &middot; "
        f"generated {payload.get('generated_at','')}"
        f"</div>"
        f"</div>",
        unsafe_allow_html=True,
    )
    st.markdown(payload.get("brief", "(no brief yet)"))

    rgn_col, _ = st.columns([1, 4])
    with rgn_col:
        if st.button("Regenerate (live, ~30s)", key="btn_regen_brief"):
            with st.spinner("Routing through hero Kamiwaza-deployed model..."):
                payload = agent.generate_brief(sid, use_cache=False, hero=True)
            st.markdown(payload.get("brief", ""))


# ──────────────────────────────────────────────────────────────────────────────
# Footer
# ──────────────────────────────────────────────────────────────────────────────
st.markdown(
    "<div class='tl-footer'>TRAVELOG &middot; Powered by Kamiwaza &middot; "
    "Travel + Cargo + LogTRACE &middot; Air-gapped, IL5/IL6 ready</div>",
    unsafe_allow_html=True,
)
