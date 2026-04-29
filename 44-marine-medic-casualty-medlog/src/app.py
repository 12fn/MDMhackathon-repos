"""MARINE-MEDIC — full medical pipeline: blood -> casualty triage -> resupply.

Streamlit FE on port 3044. FastAPI BE on port 8044 (`backend/app.py`).

Run:
    streamlit run src/app.py --server.port 3044 --server.headless true \
        --server.runOnSave false --server.fileWatcherType none \
        --browser.gatherUsageStats false
"""
from __future__ import annotations

import sys
from datetime import datetime, timezone
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


st.set_page_config(
    page_title="MARINE-MEDIC — Class VIII / Casualty Flow",
    page_icon="+",
    layout="wide",
    initial_sidebar_state="expanded",
)


# ---- CSS -------------------------------------------------------------------
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
  .mm-tagline {{
    color: {BRAND['neon']};
    font-family: Helvetica, Arial, sans-serif;
    font-weight: 600;
    letter-spacing: 1.2px;
    text-transform: uppercase;
    font-size: 12px;
  }}
  .mm-headline {{
    color: #FFFFFF;
    font-family: Helvetica, Arial, sans-serif;
    font-weight: 700;
    font-size: 28px;
    line-height: 1.18;
    margin-top: 4px;
  }}
  .mm-card {{
    background: {BRAND['surface']};
    border: 1px solid {BRAND['border']};
    border-radius: 10px;
    padding: 14px 18px;
    margin-bottom: 10px;
  }}
  .mm-pill {{
    display: inline-block;
    padding: 2px 9px;
    border-radius: 999px;
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 0.6px;
    margin-left: 6px;
  }}
  .pill-routine        {{ background:#0E2236; color:#9AD3FF; border:1px solid #6BA8DA; }}
  .pill-priority       {{ background:#3A2C0E; color:#E0B341; border:1px solid #E0B341; }}
  .pill-urgent         {{ background:#3A1A0E; color:#E36F2C; border:1px solid #E36F2C; }}
  .pill-urgent-surg    {{ background:#3A0E0E; color:#FF6F66; border:1px solid #D8362F; }}
  .pill-expectant      {{ background:#222; color:#888; border:1px solid #555; }}
  .mm-footer {{
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
  code, .stCode, .mm-mono {{
    color: {BRAND['neon']} !important;
    background: #111 !important;
    border: 1px solid {BRAND['border']};
    padding: 1px 6px;
    border-radius: 4px;
    font-family: Menlo, monospace;
  }}
</style>
"""
st.markdown(CSS, unsafe_allow_html=True)


PILL_FOR = {
    "ROUTINE":         '<span class="mm-pill pill-routine">ROUTINE</span>',
    "PRIORITY":        '<span class="mm-pill pill-priority">PRIORITY</span>',
    "URGENT":          '<span class="mm-pill pill-urgent">URGENT</span>',
    "URGENT_SURGICAL": '<span class="mm-pill pill-urgent-surg">URGENT SURG</span>',
    "EXPECTANT":       '<span class="mm-pill pill-expectant">EXPECTANT</span>',
}


# ---- Session state ---------------------------------------------------------
if "scenario_id" not in st.session_state:
    st.session_state.scenario_id = "he_blast_mascal"
if "result" not in st.session_state:
    st.session_state.result = None
if "wia_override" not in st.session_state:
    st.session_state.wia_override = None


# ---- Sidebar ---------------------------------------------------------------
scenarios = agent.load_scenarios()
spokes    = agent.load_spokes()

with st.sidebar:
    st.markdown(
        f"<div class='mm-tagline'>{BRAND['footer']}</div>"
        f"<div class='mm-headline'>MARINE-MEDIC</div>"
        f"<div style='color:{BRAND['text_dim']};font-size:12px;margin-top:6px;'>"
        "Joint Class VIII / Casualty-Flow Decision Cell<br/>"
        "USINDOPACOM DMO — TCCC / JTS / FRSS / NMRTC"
        "</div>",
        unsafe_allow_html=True,
    )
    st.markdown("---")
    st.markdown("**MISSION FRAME**")
    st.markdown(
        "<span style='color:#9A9A9A;font-size:12px;'>"
        "Inject a casualty event. The pipeline triages every WIA, projects "
        "Class VIII demand time-phased over 24h, checks the regional hub-spoke "
        "posture, auto-builds a GCSS-MC requisition, and writes the "
        "Commander's Medical Sustainment Action Brief."
        "</span>",
        unsafe_allow_html=True,
    )
    st.markdown("---")
    st.markdown("**CASUALTY EVENT**")
    scn_labels = [s["label"] for s in scenarios]
    scn_ids    = [s["id"] for s in scenarios]
    idx = scn_ids.index(st.session_state.scenario_id) if st.session_state.scenario_id in scn_ids else 0
    chosen = st.selectbox("Scenario (mass-cas template)", scn_labels, index=idx)
    st.session_state.scenario_id = scn_ids[scn_labels.index(chosen)]
    base_scn = next(s for s in scenarios if s["id"] == st.session_state.scenario_id)
    st.session_state.wia_override = st.number_input(
        "WIA count override", min_value=0, max_value=400,
        value=int(base_scn["wia_count"]), step=1,
        help="Override scenario default; injury mix scales proportionally.",
    )
    st.markdown(
        f"<span style='color:#9A9A9A;font-size:12px;'>"
        f"<b>Frame:</b> {base_scn['frame']}<br/>"
        f"<b>Receiving spoke:</b> <span class='mm-mono'>{base_scn['location_id']}</span><br/>"
        f"<b>Hours-to-evac est.:</b> {base_scn['hours_to_evac_estimate']}h"
        f"</span>",
        unsafe_allow_html=True,
    )
    st.markdown("---")
    hero = st.toggle(
        "Hero call (Kamiwaza-deployed hero narrative)", value=True,
        help="On = uses the hero model on cache miss. Off = mini chain only.",
    )
    st.markdown("**DATASETS**")
    st.markdown(
        "<span style='color:#9A9A9A;font-size:12px;'>"
        "Plug-ins (LOGCOM portal):<br/>"
        "&bull; Medical Supply Inventory v1<br/>"
        "&bull; Medical Supply Inventory v2<br/>"
        "&bull; Medical Supply Network Data Model<br/>"
        "&bull; GCSS-MC Supply &amp; Maintenance<br/><br/>"
        "Real-data swap: see <span class='mm-mono'>data/load_real.py</span>; "
        "set <span class='mm-mono'>REAL_INVENTORY_V1</span>, "
        "<span class='mm-mono'>REAL_INVENTORY_V2</span>, "
        "<span class='mm-mono'>REAL_NETWORK_PATH</span>, "
        "<span class='mm-mono'>REAL_GCSS_PATH</span>."
        "</span>",
        unsafe_allow_html=True,
    )


# ---- Header ----------------------------------------------------------------
ca, cb = st.columns([0.65, 0.35])
with ca:
    st.markdown(
        "<div class='mm-tagline'>DHA RESCUE &middot; INVENTORY CONTROL &middot; LogTRACE</div>"
        "<div class='mm-headline'>"
        "Casualty in 30 minutes. Supply chain in 30 hours. "
        "MARINE-MEDIC closes the loop across both."
        "</div>",
        unsafe_allow_html=True,
    )
with cb:
    st.markdown(
        f"<div class='mm-card' style='text-align:right;'>"
        f"<div style='color:{BRAND['muted']};font-size:11px;letter-spacing:1px;'>CLASSIFICATION</div>"
        f"<div style='color:{BRAND['neon']};font-weight:700;letter-spacing:1.2px;'>UNCLASSIFIED // FOUO</div>"
        f"<div style='color:{BRAND['muted']};font-size:11px;letter-spacing:1px;margin-top:8px;'>POSTURE</div>"
        f"<div style='color:#FFFFFF;font-weight:700;'>On-prem &middot; Kamiwaza Stack &middot; IL5/IL6</div>"
        f"<div style='color:{BRAND['muted']};font-size:11px;letter-spacing:1px;margin-top:8px;'>PIPELINE</div>"
        f"<div style='color:#FFFFFF;font-weight:700;'>6-stage agentic chain</div>"
        f"</div>",
        unsafe_allow_html=True,
    )


# ---- Quick stats from cached pipeline (instant first paint) ----------------
hub = agent.load_hub()
inv_v1 = agent.load_inventory_v1()
inv_v2 = agent.load_inventory_v2()


# Pre-load the cached brief + cached pipeline summary for instant paint
cached_briefs = agent.load_cached_briefs()
cached_for_scn = cached_briefs.get(st.session_state.scenario_id, {})
cached_demand = cached_for_scn.get("demand", {})
cached_gap    = cached_for_scn.get("gap", {})


c1, c2, c3, c4 = st.columns([0.30, 0.23, 0.23, 0.24])
with c1:
    inject = st.button("INJECT CASUALTY EVENT  &  RUN PIPELINE",
                        use_container_width=True, type="primary",
                        key="btn_inject")
with c2:
    st.metric("WIA inbound",
              str(st.session_state.wia_override or base_scn["wia_count"]))
with c3:
    st.metric("Receiving spoke", base_scn["location_id"])
with c4:
    st.metric("Hub units / day",
              f"{hub['max_daily_throughput_units']:,}")


# ---- Pipeline run ----------------------------------------------------------
if inject:
    with st.spinner("Stage 2/6 — triage cascade (TCCC / JTS, JSON-mode)…"):
        scenario = next(s for s in scenarios if s["id"] == st.session_state.scenario_id)
        event = agent.build_casualty_event(
            scenario, wia_count=st.session_state.wia_override,
        )
        cards = agent.triage_cascade(event)
    with st.spinner("Stage 3/6 — Class VIII demand projection (24h time-phased)…"):
        demand = agent.class_viii_demand(cards)
    with st.spinner("Stage 4/6 — hub-spoke supply check (cross-VITALS)…"):
        gap = agent.hub_spoke_supply_check(event, demand, inv_v1, inv_v2)
    with st.spinner("Stage 5/6 — auto-building GCSS-MC requisition…"):
        requisition = agent.build_requisition(event, gap)
    with st.spinner("Stage 6/6 — drafting Medical Sustainment Action Brief (Kamiwaza-deployed hero)…"):
        brief = agent.write_action_brief(
            event, demand, gap, requisition,
            agent.load_vendors(), hero=hero,
        )
    with st.spinner("Bonus — buy-on-market evaluation…"):
        market = agent.evaluate_buy_on_market(gap, agent.load_vendors())
    audit = agent.hash_chain([
        {"stage": "1_casualty_injection", "ts": event["injection_time"]},
        {"stage": "2_triage_cascade",     "ts": datetime.now(timezone.utc).isoformat(),
         "cards": len(cards)},
        {"stage": "3_demand_projection",  "ts": datetime.now(timezone.utc).isoformat()},
        {"stage": "4_supply_check",       "ts": datetime.now(timezone.utc).isoformat(),
         "shortfalls": gap["total_shortfalls"]},
        {"stage": "5_requisition",        "ts": requisition["submitted_iso"]},
        {"stage": "6_brief",              "ts": datetime.now(timezone.utc).isoformat()},
    ])
    st.session_state.result = {
        "event": event, "cards": cards, "demand": demand,
        "gap": gap, "requisition": requisition, "brief": brief,
        "market": market, "audit": audit,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


# Use either the live pipeline result or the cached pre-computation
res = st.session_state.result
display_demand = (res or {}).get("demand") or cached_demand
display_gap    = (res or {}).get("gap")    or cached_gap


st.markdown("---")


# ---- Hub-spoke map (Folium) -----------------------------------------------

def render_map() -> folium.Map:
    site_id = base_scn["location_id"]
    receiving_spoke = next((s for s in spokes if s["id"] == site_id), spokes[0])

    m = folium.Map(
        location=[20.0, 138.0], zoom_start=4,
        tiles="cartodbdark_matter",
        attr="© OpenStreetMap contributors © CARTO",
    )
    # Hub
    folium.CircleMarker(
        location=[hub["lat"], hub["lon"]],
        radius=14, color="#00FFA7", fill=True, fill_color="#00FFA7",
        fill_opacity=0.9, weight=3,
        tooltip=f"HUB · {hub['name']}",
        popup=folium.Popup(
            f"<b>{hub['name']}</b><br/>"
            f"Throughput: {hub['max_daily_throughput_units']} units/day<br/>"
            f"Cold-chain units: {hub['cold_chain_units']}<br/>"
            f"Lab reagents: {hub['lab_reagent_days']} days<br/>"
            f"Dry ice: {hub['dry_ice_kg']} kg<br/>"
            f"Role: {hub['role']}",
            max_width=300,
        ),
    ).add_to(m)
    # Spokes
    routes = agent.load_routes()
    rt_by = {r["spoke_id"]: r for r in routes}
    for s in spokes:
        is_receiving = (s["id"] == site_id)
        color = "#FF6F66" if is_receiving else "#0DCC8A"
        radius = 14 if is_receiving else 8
        rt = rt_by.get(s["id"], {})
        # leg from hub
        line_color = {"GREEN": "#00BB7A", "AMBER": "#E0B341", "RED": "#D8362F"}.get(
            rt.get("lift_status", "GREEN"), "#00BB7A")
        dash = {"GREEN": None, "AMBER": "8,5", "RED": "2,4"}.get(
            rt.get("lift_status", "GREEN"), None)
        folium.PolyLine(
            locations=[[hub["lat"], hub["lon"]], [s["lat"], s["lon"]]],
            color=line_color, weight=2.4, opacity=0.75, dash_array=dash,
            tooltip=f"{s['id']} · lift {rt.get('lift_status', '—')}",
        ).add_to(m)
        folium.CircleMarker(
            location=[s["lat"], s["lon"]],
            radius=radius, color=color, fill=True, fill_color=color,
            fill_opacity=0.85, weight=2,
            tooltip=f"{s['id']} · {s['role']}{' · CASUALTY CLUSTER' if is_receiving else ''}",
            popup=folium.Popup(
                f"<b>{s['name']}</b><br/>"
                f"Role: {s['role']}<br/>"
                f"Personnel: {s['personnel']:,}"
                + ("<br/><b>CASUALTY CLUSTER (this scenario)</b>" if is_receiving else ""),
                max_width=320,
            ),
        ).add_to(m)
        if is_receiving:
            # Casualty cluster ring
            folium.CircleMarker(
                location=[s["lat"], s["lon"]],
                radius=24, color="#FF6F66", fill=False, weight=2, opacity=0.65,
            ).add_to(m)
    return m


g_left, g_right = st.columns([0.62, 0.38])
with g_left:
    st.markdown("#### Hub-and-spoke posture &middot; casualty cluster overlay")
    fmap = render_map()
    st_folium(fmap, height=460, use_container_width=True, returned_objects=[],
              key="mm_map")
    st.markdown(
        "<div style='font-size:11px;color:#9A9A9A;'>"
        "<span style='color:#00FFA7;'>● APRA-MED hub</span>  "
        "<span style='color:#0DCC8A;'>● spoke</span>  "
        "<span style='color:#FF6F66;'>● receiving spoke (casualty cluster)</span>"
        "  &nbsp;|&nbsp; "
        "Lines: solid=GREEN lift &middot; dashed=AMBER &middot; dotted=RED"
        "</div>",
        unsafe_allow_html=True,
    )

with g_right:
    st.markdown("#### Casualty-flow Sankey (Role 1 -> 2 -> 2E -> 3)")
    cards = (res or {}).get("cards") or []
    if not cards:
        # Build a synthetic cards-from-scenario for the visualization stub
        scenario = next(s for s in scenarios if s["id"] == st.session_state.scenario_id)
        event0 = agent.build_casualty_event(
            scenario, wia_count=st.session_state.wia_override,
        )
        cards_for_sankey = agent._triage_baseline(event0, agent.load_doctrine())
    else:
        cards_for_sankey = cards
    # Sankey
    role_order = ["Role 1 BAS", "Role 2 FRSS", "Role 2E", "Role 3 NMRTC"]
    triage_to_role_count: dict[tuple[str, str], int] = {}
    for c in cards_for_sankey:
        cat = c.get("triage_category", "ROUTINE")
        role = c.get("role_of_care", "Role 1 BAS")
        triage_to_role_count[(cat, role)] = triage_to_role_count.get((cat, role), 0) + 1
    triage_order = ["ROUTINE", "PRIORITY", "URGENT", "URGENT_SURGICAL", "EXPECTANT"]
    triage_in_use = [t for t in triage_order if any(k[0] == t for k in triage_to_role_count.keys())]
    role_in_use   = [r for r in role_order if any(k[1] == r for k in triage_to_role_count.keys())]
    labels = ["INJURY"] + triage_in_use + role_in_use
    label_idx = {l: i for i, l in enumerate(labels)}
    sources, targets, values, colors = [], [], [], []
    color_map = {
        "ROUTINE": "#6BA8DA", "PRIORITY": "#E0B341",
        "URGENT": "#E36F2C", "URGENT_SURGICAL": "#D8362F",
        "EXPECTANT": "#888888",
    }
    for t in triage_in_use:
        n = sum(v for (cat, _), v in triage_to_role_count.items() if cat == t)
        if n:
            sources.append(label_idx["INJURY"])
            targets.append(label_idx[t])
            values.append(n)
            colors.append(color_map.get(t, "#9AD3FF"))
    for (cat, role), n in triage_to_role_count.items():
        sources.append(label_idx[cat])
        targets.append(label_idx[role])
        values.append(n)
        colors.append(color_map.get(cat, "#9AD3FF"))
    if values:
        fig = go.Figure(data=[go.Sankey(
            node=dict(pad=12, thickness=14,
                      line=dict(color="#222", width=0.5),
                      label=labels,
                      color=["#0DCC8A"] +
                            [color_map.get(t, "#888") for t in triage_in_use] +
                            ["#00FFA7" for _ in role_in_use]),
            link=dict(source=sources, target=targets, value=values, color=colors),
        )])
        fig.update_layout(height=440, font=dict(color="#E8E8E8", size=11),
                          paper_bgcolor=BRAND["bg"], plot_bgcolor=BRAND["bg"],
                          margin=dict(l=4, r=4, t=10, b=10))
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("Run the pipeline to populate the casualty-flow Sankey.")


# ---- Triage cards ----------------------------------------------------------
st.markdown("---")
st.markdown("#### Triage cascade — per-WIA cards (TCCC / JTS)")
cards_to_show = (res or {}).get("cards") or []
if not cards_to_show:
    st.caption("Inject the casualty event to stream triage cards (chat_json).")
else:
    # Tile cards in 4-col grid
    cols = st.columns(4)
    for i, c in enumerate(cards_to_show[:24]):
        with cols[i % 4]:
            cat = c.get("triage_category", "ROUTINE")
            pill = PILL_FOR.get(cat, PILL_FOR["ROUTINE"])
            bundle = c.get("class_viii_bundle", {})
            st.markdown(
                f"<div class='mm-card' style='padding:10px 12px;margin-bottom:8px;'>"
                f"<div style='display:flex;justify-content:space-between;align-items:center;'>"
                f"<div><b style='color:#FFFFFF;'>{c.get('wia_id', '—')}</b></div>"
                f"<div>{pill}</div>"
                f"</div>"
                f"<div style='color:#C0C0C0;font-size:11px;margin-top:4px;'>"
                f"{c.get('injury_kind', '')}"
                f"</div>"
                f"<div style='color:{BRAND['neon']};font-size:11px;margin-top:4px;'>"
                f"-> {c.get('role_of_care', '—')} ({c.get('evac_window_h', '—')}h)"
                f"</div>"
                f"<div style='color:{BRAND['muted']};font-size:11px;margin-top:4px;'>"
                f"PRBC {bundle.get('PRBC_units', 0):.0f} &middot; FFP {bundle.get('FFP_units', 0):.0f}"
                f" &middot; TXA {bundle.get('TXA_g', 0):.0f}g"
                f" &middot; fluids {bundle.get('fluids_L', 0):.0f}L"
                f"</div>"
                f"</div>",
                unsafe_allow_html=True,
            )
    if len(cards_to_show) > 24:
        st.caption(f"…and {len(cards_to_show) - 24} more.")


# ---- Time-phased Class VIII demand chart -----------------------------------
st.markdown("---")
st.markdown("#### Class VIII demand — time-phased over 24h")
phased = display_demand.get("time_phased_h") if display_demand else None
if not phased:
    st.caption("Inject the casualty event (or use cached preview) to populate.")
else:
    hours = sorted(phased.keys(), key=lambda x: int(x))
    keys_to_chart = ["PRBC_units", "FFP_units", "LTOWB_units",
                     "fluids_L", "TXA_g", "antibiotic_doses",
                     "tourniquets", "surgical_sets"]
    color_keys = {
        "PRBC_units": "#D8362F", "FFP_units": "#E36F2C",
        "LTOWB_units": "#FF6F66", "fluids_L": "#9AD3FF",
        "TXA_g": "#E0B341", "antibiotic_doses": "#0DCC8A",
        "tourniquets": "#00FFA7", "surgical_sets": "#9A77FF",
    }
    fig = go.Figure()
    for k in keys_to_chart:
        ys = [phased[h].get(k, 0) for h in hours]
        if max(ys) <= 0:
            continue
        fig.add_trace(go.Bar(
            name=k, x=[f"{h}h" for h in hours], y=ys,
            marker_color=color_keys.get(k, "#9AD3FF"),
        ))
    fig.update_layout(
        barmode="group", height=380,
        font=dict(color="#E8E8E8"),
        paper_bgcolor=BRAND["bg"], plot_bgcolor=BRAND["surface"],
        margin=dict(l=8, r=8, t=10, b=8),
        legend=dict(orientation="h", yanchor="bottom", y=-0.32),
        xaxis=dict(gridcolor=BRAND["border"]),
        yaxis=dict(gridcolor=BRAND["border"], title="Quantity"),
    )
    st.plotly_chart(fig, use_container_width=True)


# ---- Supply gap + auto-requisition -----------------------------------------
st.markdown("---")
gleft, gright = st.columns([0.55, 0.45])
with gleft:
    st.markdown("#### Hub-spoke supply check &middot; gaps")
    gap = display_gap or {}
    sf = gap.get("top_shortfalls") or []
    if not sf:
        st.success("No critical Class VIII shortfalls detected at receiving spoke + APRA hub.")
    else:
        st.dataframe(
            pd.DataFrame([
                {"Item": r["item"], "Need (24h)": r["need"],
                 "On-hand": r["on_hand"], "Shortfall": r["shortfall"],
                 "Unit": r["unit"]}
                for r in sf
            ]),
            hide_index=True, use_container_width=True, height=240,
        )
    if gap.get("expiring_soon"):
        st.markdown(
            f"<div style='color:#E0B341;font-size:12px;margin-top:6px;'>"
            f"<b>Expiring &lt; 5d:</b> "
            + ", ".join(f"{e['site_id']}/{e['product']} {e['units']}u "
                        f"({e['days_to_expire']}d)"
                        for e in gap['expiring_soon'][:6])
            + "</div>",
            unsafe_allow_html=True,
        )
    if gap.get("cold_chain_red_sites"):
        st.markdown(
            f"<div style='color:#FF6F66;font-size:12px;margin-top:6px;'>"
            f"<b>Cold-chain RED:</b> {', '.join(gap['cold_chain_red_sites'][:8])}"
            f"</div>",
            unsafe_allow_html=True,
        )

with gright:
    st.markdown("#### GCSS-MC auto-requisition (Class VIII)")
    if res and res.get("requisition"):
        req = res["requisition"]
        st.markdown(
            f"<div class='mm-card'>"
            f"<div style='color:{BRAND['muted']};font-size:11px;'>SHIP-TO UIC</div>"
            f"<div style='color:#FFF;font-weight:700;'>{req['lines'][0]['ship_to_uic'] if req['lines'] else '—'}</div>"
            f"<div style='color:{BRAND['muted']};font-size:11px;margin-top:6px;'>SUBMITTED</div>"
            f"<div style='color:#FFF;'>{req['submitted_iso'][:19]}Z</div>"
            f"</div>",
            unsafe_allow_html=True,
        )
        if req["lines"]:
            st.dataframe(
                pd.DataFrame(req["lines"])[["doc_id", "nomenclature", "qty", "uoi",
                                             "priority", "source_depot",
                                             "lead_time_h_estimate"]]
                .rename(columns={"doc_id": "DOC", "nomenclature": "Item",
                                 "qty": "Qty", "uoi": "U/I",
                                 "priority": "Pri", "source_depot": "Depot",
                                 "lead_time_h_estimate": "Lead (h)"}),
                hide_index=True, use_container_width=True, height=220,
            )
    else:
        st.caption("Pipeline not run yet — auto-requisition will populate after injection.")


# ---- Buy-on-market evaluation ---------------------------------------------
st.markdown("---")
st.markdown("#### Buy-on-market evaluation (DHA RESCUE prompt)")
market = (res or {}).get("market") or []
if market:
    by_id = {v["id"]: v for v in agent.load_vendors()}
    rows = []
    for m in market:
        vid = m.get("vendor_id", "")
        v = by_id.get(vid, {})
        rows.append({
            "Item": m.get("item", ""), "Vendor": v.get("name", vid),
            "Lead (h)": m.get("lead_time_h", "—"),
            "Vehicle": v.get("contract_vehicle", "—"),
            "Trust":   v.get("trust", "—"),
            "Rationale": m.get("rationale", "")[:120],
        })
    st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True,
                 height=240)
else:
    st.caption("Pipeline not run yet — buy-on-market recommendations will populate after injection.")


# ---- Multi-modal photo upload (vision-language triage hint) ---------------
with st.expander("Multi-modal: photo of injury -> vision-language triage hint (training-only)"):
    st.markdown(
        "<span style='color:#9A9A9A;font-size:12px;'>"
        "Upload a synthetic / training photo. The multimodal model returns an "
        "advisory triage hint — not a diagnosis."
        "</span>",
        unsafe_allow_html=True,
    )
    img = st.file_uploader("Image (jpg/png)", type=["jpg", "jpeg", "png"],
                            accept_multiple_files=False)
    if img and st.button("ANALYZE IMAGE", key="btn_vision"):
        with st.spinner("Multimodal triage hint…"):
            hint = agent.vision_triage_hint(img.getvalue(), mime=img.type or "image/jpeg")
        st.markdown(
            f"<div class='mm-card'>"
            f"<b>Injury kind hint:</b> {hint.get('injury_kind_hint', '—')}<br/>"
            f"<b>Triage hint:</b> {PILL_FOR.get(hint.get('triage_category_hint', 'PRIORITY'), '')}<br/>"
            f"<span style='color:#C0C0C0;font-size:12px;'>{hint.get('rationale', '')}</span>"
            f"</div>",
            unsafe_allow_html=True,
        )


# ---- Hero brief ------------------------------------------------------------
st.markdown("---")
st.markdown("### Medical Sustainment Action Brief")
brief_text = (res or {}).get("brief") or cached_for_scn.get("brief", "")
brief_source = "live" if (res and res.get("brief")) else "cached"
if brief_text:
    st.caption(f"Source: {brief_source} &middot; Scenario: {base_scn['label']}")
    st.markdown("<div class='mm-card' style='padding:22px 30px;'>", unsafe_allow_html=True)
    st.markdown(brief_text)
    st.markdown("</div>", unsafe_allow_html=True)
else:
    st.info("Click **INJECT CASUALTY EVENT & RUN PIPELINE** to draft the brief.")


# ---- Hash-chained audit ----------------------------------------------------
audit = (res or {}).get("audit") or []
if audit:
    with st.expander("Hash-chained audit (HIPAA / NDAA Section 1739 flavored)"):
        st.dataframe(
            pd.DataFrame([
                {"Stage": a["stage"], "TS": a.get("ts", "")[:19] + "Z",
                 "Hash": a["hash"][:16] + "…",
                 "Prev": a["prev_hash"][:16] + "…"}
                for a in audit
            ]),
            hide_index=True, use_container_width=True,
        )


# ---- Footer ----------------------------------------------------------------
st.markdown(
    f"<div class='mm-footer'>"
    f"Powered by Kamiwaza &middot; Casualty data stays in IL5/IL6 enclave &middot; "
    f"Nothing ever leaves your accredited environment."
    f"</div>",
    unsafe_allow_html=True,
)
