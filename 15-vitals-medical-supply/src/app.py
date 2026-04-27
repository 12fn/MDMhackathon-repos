"""VITALS — DHA RESCUE blood-logistics decision support (Streamlit, port 3015).

Run:
    streamlit run src/app.py --server.port 3015 --server.headless true
"""
from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

import folium
import pandas as pd
import streamlit as st
from streamlit_folium import st_folium

# Make `shared` and `src` importable.
APP_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = APP_ROOT.parents[1]
for p in (str(REPO_ROOT), str(APP_ROOT)):
    if p not in sys.path:
        sys.path.insert(0, p)

from shared.kamiwaza_client import BRAND  # noqa: E402
from src import agent  # noqa: E402


st.set_page_config(
    page_title="VITALS — DHA RESCUE Blood Logistics",
    page_icon="+",
    layout="wide",
    initial_sidebar_state="expanded",
)


# ---- CSS / theme -----------------------------------------------------------
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
  .vitals-tagline {{
    color: {BRAND['neon']};
    font-family: Helvetica, Arial, sans-serif;
    font-weight: 600;
    letter-spacing: 1.2px;
    text-transform: uppercase;
    font-size: 12px;
  }}
  .vitals-headline {{
    color: #FFFFFF;
    font-family: Helvetica, Arial, sans-serif;
    font-weight: 700;
    font-size: 28px;
    line-height: 1.18;
    margin-top: 4px;
  }}
  .vitals-card {{
    background: {BRAND['surface']};
    border: 1px solid {BRAND['border']};
    border-radius: 10px;
    padding: 14px 18px;
    margin-bottom: 10px;
  }}
  .vitals-pill {{
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
  .vitals-footer {{
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
</style>
"""
st.markdown(CSS, unsafe_allow_html=True)


def viability_pill(v: float) -> str:
    if v >= 7.0:
        return f'<span class="vitals-pill pill-low">{v:.1f}</span>'
    if v >= 4.5:
        return f'<span class="vitals-pill pill-med">{v:.1f}</span>'
    if v >= 2.5:
        return f'<span class="vitals-pill pill-high">{v:.1f}</span>'
    return f'<span class="vitals-pill pill-crit">{v:.1f}</span>'


def viability_color(v: float) -> str:
    """Folium marker color from viability index."""
    if v >= 7.0:
        return "#00BB7A"
    if v >= 4.5:
        return "#E0B341"
    if v >= 2.5:
        return "#E36F2C"
    return "#D8362F"


# ---- Session state ---------------------------------------------------------
if "scenario_id" not in st.session_state:
    st.session_state.scenario_id = "baseline"
if "result" not in st.session_state:
    st.session_state.result = None


# ---- Sidebar ---------------------------------------------------------------
with st.sidebar:
    st.markdown(
        f"<div class='vitals-tagline'>{BRAND['footer']}</div>"
        f"<div class='vitals-headline'>VITALS</div>"
        f"<div style='color:{BRAND['text_dim']};font-size:12px;margin-top:6px;'>"
        "DHA RESCUE — Joint Blood Logistics Decision Support<br/>"
        "USINDOPACOM Distributed Maritime Operations"
        "</div>",
        unsafe_allow_html=True,
    )
    st.markdown("---")
    st.markdown("**MISSION FRAME**")
    st.markdown(
        "<span style='color:#9A9A9A;font-size:12px;'>"
        "Predict when a constrained regional medical hub will cause spoke-level "
        "<i>mission failure</i> across 12 distributed Marine units. Cold-chain, "
        "transport, and lab-reagent cascades simulated end-to-end."
        "</span>",
        unsafe_allow_html=True,
    )
    st.markdown("---")
    st.markdown("**SCENARIO**")
    scenarios = list(agent.SCENARIOS.items())
    scn_labels = [v["label"] for _, v in scenarios]
    scn_ids = [k for k, _ in scenarios]
    idx = scn_ids.index(st.session_state.scenario_id) if st.session_state.scenario_id in scn_ids else 0
    chosen = st.selectbox("Select scenario", scn_labels, index=idx, key="scn_select")
    st.session_state.scenario_id = scn_ids[scn_labels.index(chosen)]
    st.markdown(
        f"<span style='color:#9A9A9A;font-size:12px;'>"
        f"<b>Constraint:</b> {agent.SCENARIOS[st.session_state.scenario_id]['constraint']}"
        f"</span>",
        unsafe_allow_html=True,
    )
    st.markdown("---")
    hero = st.toggle(
        "Hero call (Kamiwaza-deployed hero narrative)", value=True,
        help="When ON, uses the Kamiwaza-deployed hero model. When OFF, uses the mini chain.",
    )
    st.markdown("**DATASET**")
    st.markdown(
        "<span style='color:#9A9A9A;font-size:12px;'>"
        "LOGCOM portal: <i>Medical Supply Inventory</i> + "
        "<i>Medical Supply Network Data Model</i>. Shipped here as seeded "
        "synthetic stand-in. Real-data swap: set "
        "<code>REAL_INVENTORY_PATH</code> + <code>REAL_NETWORK_PATH</code>, "
        "then point at <code>KAMIWAZA_BASE_URL</code> for on-prem inference."
        "</span>",
        unsafe_allow_html=True,
    )


# ---- Header ----------------------------------------------------------------
col_a, col_b = st.columns([0.65, 0.35])
with col_a:
    st.markdown(
        f"<div class='vitals-tagline'>DHA RESCUE · DMO blood logistics</div>"
        f"<div class='vitals-headline'>One depot, twelve spokes, sixty hours of sustainment. "
        f"VITALS predicts which spoke fails first.</div>",
        unsafe_allow_html=True,
    )
with col_b:
    st.markdown(
        f"<div class='vitals-card' style='text-align:right;'>"
        f"<div style='color:{BRAND['muted']};font-size:11px;letter-spacing:1px;'>CLASSIFICATION</div>"
        f"<div style='color:{BRAND['neon']};font-weight:700;letter-spacing:1.2px;'>UNCLASSIFIED // FOUO</div>"
        f"<div style='color:{BRAND['muted']};font-size:11px;letter-spacing:1px;margin-top:8px;'>POSTURE</div>"
        f"<div style='color:#FFFFFF;font-weight:700;'>On-prem · Kamiwaza Stack</div>"
        f"</div>",
        unsafe_allow_html=True,
    )


# ---- Load + score (instant baseline) ---------------------------------------
hub = agent.load_hub()
spokes = agent.load_spokes()
vendors = agent.load_vendors()
inventory_raw = agent.load_inventory()
routes_raw = agent.load_routes()
casualties = agent.load_casualties()

inv_s, rts_s = agent.apply_scenario(
    st.session_state.scenario_id, spokes, inventory_raw, routes_raw,
)
baseline = agent.baseline_scores(spokes, inv_s, rts_s)
crit_count = agent.nodes_at_critical_risk(baseline)


# ---- Action row ------------------------------------------------------------
c1, c2, c3, c4 = st.columns([0.28, 0.24, 0.24, 0.24])
with c1:
    if st.button("CONSTRAIN HUB & GENERATE BRIEF", use_container_width=True,
                 type="primary", key="btn_generate"):
        with st.spinner("Step 1/2 — scoring 12 spokes (chat_json)…"):
            scores = agent.score_spokes(hub, spokes, inv_s, rts_s, casualties)
        with st.spinner("Step 2/2 — drafting Commander's Decision Brief (Kamiwaza-deployed hero)…"):
            brief = agent.write_brief(
                hub, spokes, scores, vendors,
                st.session_state.scenario_id, hero=hero,
            )
        st.session_state.result = {
            "scores": scores, "brief": brief,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }
with c2:
    st.metric("Hub units / day", f"{hub['max_daily_throughput_units']:,}")
with c3:
    st.metric("Spokes monitored", str(len(spokes)))
with c4:
    st.metric("Spokes at critical viability", str(crit_count),
              help="Heuristic baseline; refined when LLM lands.")

st.markdown("---")


# ---- Map (Folium hub-spoke) ------------------------------------------------
def render_map(scores: list[dict]) -> folium.Map:
    score_by_id = {s["node_id"]: s for s in scores}
    rt_by_id = {r["spoke_id"]: r for r in rts_s}

    m = folium.Map(
        location=[20.0, 138.0], zoom_start=4,
        tiles="cartodbdark_matter",
        attr="© OpenStreetMap contributors © CARTO",
    )

    # Hub marker
    folium.CircleMarker(
        location=[hub["lat"], hub["lon"]],
        radius=14,
        color="#00FFA7",
        fill=True,
        fill_color="#00FFA7",
        fill_opacity=0.9,
        weight=3,
        popup=folium.Popup(
            f"<b>{hub['name']}</b><br/>"
            f"Cold-chain units: {hub['cold_chain_units']}<br/>"
            f"Lab reagents: {hub['lab_reagent_days']} days<br/>"
            f"Dry ice: {hub['dry_ice_kg']} kg<br/>"
            f"Throughput: {hub['max_daily_throughput_units']} units/day",
            max_width=280,
        ),
        tooltip=f"HUB · {hub['name']}",
    ).add_to(m)

    # Spoke markers + lines hub<->spoke colored by viability
    for s in spokes:
        sc = score_by_id.get(s["id"], {"viability_index": 7.0, "days_of_supply": 5,
                                       "top_constraint": "—", "confidence": "—",
                                       "projected_stockout_date": "—"})
        col = viability_color(sc["viability_index"])
        rt = rt_by_id.get(s["id"], {})
        # leg
        folium.PolyLine(
            locations=[[hub["lat"], hub["lon"]], [s["lat"], s["lon"]]],
            color=col,
            weight=2.4,
            opacity=0.75,
            dash_array={"GREEN": None, "AMBER": "8,5", "RED": "2,4"}.get(
                rt.get("lift_status", "GREEN"), None,
            ),
            tooltip=f"{s['id']} · lift {rt.get('lift_status', '—')} · {rt.get('mode', '—')}",
        ).add_to(m)
        # spoke marker
        folium.CircleMarker(
            location=[s["lat"], s["lon"]],
            radius=9,
            color=col,
            fill=True,
            fill_color=col,
            fill_opacity=0.85,
            weight=2,
            popup=folium.Popup(
                f"<b>{s['name']}</b> ({s['id']})<br/>"
                f"Type: {s['kind']}<br/>"
                f"Personnel: {s['personnel']:,}<br/>"
                f"Viability: <b>{sc['viability_index']:.1f}/10</b><br/>"
                f"Days of supply: {sc['days_of_supply']:.1f}<br/>"
                f"Projected stockout: {sc['projected_stockout_date']}<br/>"
                f"Top constraint: {sc['top_constraint']}<br/>"
                f"Confidence: {sc['confidence']}",
                max_width=320,
            ),
            tooltip=f"{s['id']} · viability {sc['viability_index']:.1f}",
        ).add_to(m)
    return m


scores_for_map = (st.session_state.result or {}).get("scores") or baseline

g_left, g_right = st.columns([0.62, 0.38])
with g_left:
    st.markdown("#### Hub-and-spoke posture map")
    fmap = render_map(scores_for_map)
    st_folium(fmap, height=520, use_container_width=True, returned_objects=[],
              key="vitals_map")
    st.markdown(
        "<div style='font-size:11px;color:#9A9A9A;'>"
        "<span style='color:#00BB7A;'>● robust</span>  "
        "<span style='color:#E0B341;'>● degraded</span>  "
        "<span style='color:#E36F2C;'>● elevated risk</span>  "
        "<span style='color:#D8362F;'>● mission-failure window</span>"
        "  &nbsp;|&nbsp; "
        "Lines: solid=GREEN lift · dashed=AMBER · dotted=RED"
        "</div>",
        unsafe_allow_html=True,
    )

with g_right:
    st.markdown("#### Spoke viability ranking")
    ranked = sorted(scores_for_map, key=lambda s: s["viability_index"])
    spoke_by_id = {s["id"]: s for s in spokes}
    for s in ranked:
        n = spoke_by_id.get(s["node_id"])
        if not n:
            continue
        st.markdown(
            f"<div class='vitals-card' style='padding:8px 12px;margin-bottom:6px;'>"
            f"<div style='display:flex;justify-content:space-between;align-items:center;'>"
            f"<div><b style='color:#FFFFFF'>{n['name']}</b> "
            f"<span style='color:{BRAND['muted']};font-size:11px;'>· {n['id']}</span></div>"
            f"<div>{viability_pill(s['viability_index'])}</div>"
            f"</div>"
            f"<div style='color:#C0C0C0;font-size:12px;margin-top:3px;'>"
            f"DOS <b>{s['days_of_supply']:.1f}d</b> · "
            f"<b>Top constraint:</b> {s['top_constraint']} "
            f"<span style='color:{BRAND['muted']};'>({s['confidence']})</span></div>"
            f"</div>",
            unsafe_allow_html=True,
        )


# ---- Inventory table -------------------------------------------------------
st.markdown("---")
st.markdown("#### Live inventory — blood components (scenario-adjusted)")
inv_df = pd.DataFrame([
    {"Site": r["site_id"], "Product": r["product"], "Units": r["units"],
     "Cold-chain": r["cold_chain_status"],
     "DOS (d)": r.get("days_of_supply", "—"),
     "Daily use": r.get("daily_consumption", "—"),
     "Expires": r.get("expires_iso", "—")[:10]}
    for r in inv_s
])
st.dataframe(inv_df, use_container_width=True, hide_index=True, height=240)


# ---- Brief -----------------------------------------------------------------
st.markdown("---")
st.markdown("### Commander's Decision Brief")

# Always render *something* — cache-first so first paint is instant.
cached_briefs = agent.load_cached_briefs()
default_brief = (cached_briefs.get(st.session_state.scenario_id) or {}).get("brief")

result_brief = (st.session_state.result or {}).get("brief")
brief_to_show = result_brief or default_brief
brief_source = "live" if result_brief else "cached"

if brief_to_show:
    st.caption(
        f"Source: {brief_source} · Scenario: "
        f"{agent.SCENARIOS[st.session_state.scenario_id]['label']}"
    )
    st.markdown("<div class='vitals-card' style='padding:22px 30px;'>", unsafe_allow_html=True)
    st.markdown(brief_to_show)
    st.markdown("</div>", unsafe_allow_html=True)
else:
    st.info("Click **CONSTRAIN HUB & GENERATE BRIEF** to score 12 spokes and draft the brief.")


# ---- Vendors ---------------------------------------------------------------
with st.expander("Approved buy-on-market vendors (commercial / host-nation)"):
    st.dataframe(
        pd.DataFrame([
            {"ID": v["id"], "Vendor": v["name"], "Country": v["country"],
             "Supplies": ", ".join(v["supplies"]), "Lead (h)": v["lead_time_h"],
             "Trust": v["trust"], "Vehicle": v["contract_vehicle"]}
            for v in vendors
        ]),
        use_container_width=True, hide_index=True,
    )


# ---- Footer ----------------------------------------------------------------
st.markdown(
    f"<div class='vitals-footer'>"
    f"Powered by Kamiwaza · 100% Data Containment — Nothing ever leaves your accredited environment."
    f"</div>",
    unsafe_allow_html=True,
)
