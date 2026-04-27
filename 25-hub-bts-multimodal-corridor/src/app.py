"""HUB — Streamlit app (port 3025).

Multimodal transport-stat explorer for Marine logistics planners.

Run with:
    cd apps/25-hub
    streamlit run src/app.py --server.port 3025 --server.headless true \\
      --server.runOnSave false --server.fileWatcherType none \\
      --browser.gatherUsageStats false
"""
from __future__ import annotations

import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import streamlit as st
from streamlit_folium import st_folium

# Make `shared` and `src` importable from any cwd.
APP_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = APP_ROOT.parents[1]
for p in (str(REPO_ROOT), str(APP_ROOT)):
    if p not in sys.path:
        sys.path.insert(0, p)

from shared.kamiwaza_client import BRAND  # noqa: E402
from src import agent, charts  # noqa: E402


# ──────────────────────────────────────────────────────────────────────────────
# Page config + theme
# ──────────────────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="HUB — Multimodal Movement Planner",
    page_icon="◆",
    layout="wide",
    initial_sidebar_state="expanded",
)

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
  h1, h2, h3, h4 {{ color: #FFFFFF !important; letter-spacing: 0.4px; }}
  .hub-tagline {{
    color: {BRAND['neon']};
    font-family: Helvetica, Arial, sans-serif;
    font-weight: 600;
    letter-spacing: 1.2px;
    text-transform: uppercase;
    font-size: 12px;
  }}
  .hub-headline {{
    color: #FFFFFF;
    font-family: Helvetica, Arial, sans-serif;
    font-weight: 700;
    font-size: 30px;
    line-height: 1.15;
    margin-top: 4px;
  }}
  .hub-card {{
    background: {BRAND['surface']};
    border: 1px solid {BRAND['border']};
    border-radius: 10px;
    padding: 14px 18px;
    margin-bottom: 10px;
  }}
  .hub-pill {{
    display:inline-block; padding:3px 10px; border-radius:999px;
    font-size:11px; font-weight:700; letter-spacing:0.6px; margin-right:6px;
  }}
  .pill-go    {{ background:#0E2F22; color:#00FFA7; border:1px solid #00BB7A; }}
  .pill-cau   {{ background:#3A2C0E; color:#E0B341; border:1px solid #E0B341; }}
  .pill-no    {{ background:#3A0E0E; color:#FF6F66; border:1px solid #D8362F; }}
  .pill-mode  {{ background:#0E0E0E; color:#FFFFFF; border:1px solid #333333; }}
  .hub-footer {{
    color:{BRAND['muted']}; text-align:center; margin-top:30px;
    padding:14px; border-top:1px solid {BRAND['border']};
    font-size:12px; letter-spacing:1.2px; text-transform:uppercase;
  }}
  .stButton > button {{
    background: {BRAND['primary']}; color:#0A0A0A; border:0;
    font-weight:700; letter-spacing:0.6px;
  }}
  .stButton > button:hover {{
    background: {BRAND['primary_hover']}; color:#0A0A0A;
  }}
  div[data-testid="stMetricValue"] {{ color: {BRAND['neon']} !important; }}
  .stDataFrame, .stDataFrame * {{ color:#E8E8E8 !important; }}
</style>
"""
st.markdown(CSS, unsafe_allow_html=True)


def _verdict_pill(feasible: bool) -> str:
    if feasible:
        return '<span class="hub-pill pill-go">FEASIBLE</span>'
    return '<span class="hub-pill pill-no">BLOCKED</span>'


_POE_HEADING_RE = re.compile(
    r"^\s*#{1,6}\s*POE\s+Movement\s+Plan\s*$",
    flags=re.IGNORECASE | re.MULTILINE,
)


def _strip_poe_headings(narrative: str) -> str:
    """Remove any embedded '# POE Movement Plan' headings from the narrative.

    The hero LLM (and some cached briefs) may emit one or more
    '# POE Movement Plan' / '## POE Movement Plan' lines at the top of the
    body. The app already renders a single '### POE Movement Plan' heading
    above this block, so duplicates would stack visibly on screen.
    """
    if not narrative:
        return narrative
    cleaned = _POE_HEADING_RE.sub("", narrative)
    # Collapse the leading whitespace/blank lines left behind.
    return cleaned.lstrip("\n").lstrip()


# ──────────────────────────────────────────────────────────────────────────────
# Cached data
# ──────────────────────────────────────────────────────────────────────────────
@st.cache_data(show_spinner=False)
def _all_nodes() -> list[dict]:
    return agent.load_nodes()


@st.cache_data(show_spinner=False)
def _all_edges() -> list[dict]:
    return agent.load_edges()


@st.cache_data(show_spinner=False)
def _all_items() -> list[dict]:
    return agent.load_end_items()


@st.cache_data(show_spinner=False)
def _cached_briefs() -> dict:
    return agent.load_cached_briefs()


nodes = _all_nodes()
edges = _all_edges()
items = _all_items()
cache = _cached_briefs()


# ──────────────────────────────────────────────────────────────────────────────
# Session state
# ──────────────────────────────────────────────────────────────────────────────
if "result" not in st.session_state:
    # Pre-load the first cached scenario so the page is never empty.
    if cache:
        first_id = next(iter(cache))
        st.session_state.result = cache[first_id]
        st.session_state.result_source = "cache"
        st.session_state.scenario_id = first_id
    else:
        st.session_state.result = None
        st.session_state.result_source = None
        st.session_state.scenario_id = None


# ──────────────────────────────────────────────────────────────────────────────
# Sidebar — operator workflow
# ──────────────────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown(
        f"<div class='hub-tagline'>{BRAND['footer']}</div>"
        f"<div class='hub-headline'>HUB</div>"
        f"<div style='color:{BRAND['text_dim']};font-size:12px;margin-top:6px;'>"
        "Multimodal CONUS movement planner for<br/>USMC LOGCOM POE flow"
        "</div>",
        unsafe_allow_html=True,
    )
    st.markdown("---")
    st.markdown("**MISSION FRAME**")
    st.markdown(
        "<span style='color:#9A9A9A;font-size:12px;'>"
        "Marine planners need a single pane to compare road / rail / waterway / air "
        "capacity and throughput when planning CONUS-to-port-of-embarkation movement "
        "of equipment. LOGCOM problem set: <i>contested logistics, supply chain, "
        "expeditionary operations</i>."
        "</span>",
        unsafe_allow_html=True,
    )
    st.markdown("---")

    st.markdown("**OPERATOR INPUT**")
    # Scenario quick-pick (cached briefs)
    scenario_label_to_id: dict[str, str] = {}
    for sid, blob in cache.items():
        sc = blob.get("scenario", {})
        scenario_label_to_id[sc.get("label", sid)] = sid
    scenario_label_to_id["— custom selection —"] = "__custom__"
    scenario_choice = st.selectbox(
        "Cached scenario",
        options=list(scenario_label_to_id.keys()),
        index=0,
        help="Cached briefs render instantly. Pick 'custom' to compose a new movement.",
        key="scenario_choice",
    )
    sid_chosen = scenario_label_to_id[scenario_choice]

    # Defaults from chosen cache entry (or sensible CONUS defaults).
    default_origin = "MCLB-ALB"
    default_dest = "POE-BMT"
    default_item = "M1A1"
    if sid_chosen in cache:
        sc = cache[sid_chosen].get("scenario", {})
        default_origin = sc.get("origin_id", default_origin)
        default_dest = sc.get("destination_id", default_dest)
        default_item = sc.get("end_item_id", default_item)

    node_ids = [n["id"] for n in nodes]
    node_label = {n["id"]: f"{n['id']} — {n['name']}" for n in nodes}

    origin_id = st.selectbox(
        "Origin",
        options=node_ids,
        index=node_ids.index(default_origin) if default_origin in node_ids else 0,
        format_func=lambda i: node_label[i],
        key="origin_pick",
    )
    dest_options = [n["id"] for n in nodes if n["kind"] == "poe"]
    dest_id = st.selectbox(
        "Destination (POE)",
        options=dest_options,
        index=dest_options.index(default_dest) if default_dest in dest_options else 0,
        format_func=lambda i: node_label[i],
        key="dest_pick",
    )
    item_ids = [i["id"] for i in items]
    item_label = {i["id"]: f"{i['id']} — {i['name']}" for i in items}
    end_item_id = st.selectbox(
        "End item",
        options=item_ids,
        index=item_ids.index(default_item) if default_item in item_ids else 0,
        format_func=lambda i: item_label[i],
        key="item_pick",
    )

    st.markdown("---")
    use_cache_toggle = st.toggle(
        "Use cached brief if available",
        value=True,
        help="Cached briefs render instantly (cache-first hero pattern). Toggle off to "
             "force a live AI engine call.",
    )

    if st.button("ANALYZE CORRIDOR", use_container_width=True, type="primary",
                 key="btn_analyze"):
        # Pick scenario id only if input still matches a cached scenario.
        scenario_id_for_cache = None
        if use_cache_toggle and sid_chosen in cache:
            sc = cache[sid_chosen].get("scenario", {})
            if (sc.get("origin_id") == origin_id and
                    sc.get("destination_id") == dest_id and
                    sc.get("end_item_id") == end_item_id):
                scenario_id_for_cache = sid_chosen

        if scenario_id_for_cache:
            st.session_state.result = cache[scenario_id_for_cache]
            st.session_state.result_source = "cache"
            st.session_state.scenario_id = scenario_id_for_cache
            st.toast(f"Loaded cached brief: {scenario_choice}")
        else:
            with st.spinner("Step 1/2 — scoring all four modes…"):
                plan = agent.compute_corridor(origin_id, dest_id, end_item_id)
                jb = agent.hero_chat_json(plan)
            with st.spinner("Step 2/2 — drafting POE Movement Plan…"):
                narrative = agent.hero_chat_narrative(plan, jb)
            st.session_state.result = {
                "scenario": {"origin_id": origin_id, "destination_id": dest_id,
                             "end_item_id": end_item_id,
                             "label": f"{node_label[origin_id]} → {node_label[dest_id]} · {item_label[end_item_id]}"},
                "plan": plan,
                "json_brief": jb,
                "narrative": narrative,
                "generated_at": datetime.now(timezone.utc).isoformat(),
            }
            st.session_state.result_source = jb.get("_source", "live")
            st.session_state.scenario_id = None
            st.toast("Live POE Movement Plan generated.")

    st.markdown("---")
    st.markdown("**DATASET**")
    st.markdown(
        "<span style='color:#9A9A9A;font-size:12px;'>"
        "Bureau of Transportation Statistics — National Transportation Atlas Database "
        "(NTAD): roads, rail lines, navigable waterways, T-100 air carrier flows. "
        "Synthetic stand-in here; real-data swap via "
        "<code>data/load_real.py</code> + BTS shapefiles."
        "</span>",
        unsafe_allow_html=True,
    )


# ──────────────────────────────────────────────────────────────────────────────
# Header
# ──────────────────────────────────────────────────────────────────────────────
col_a, col_b = st.columns([0.65, 0.35])
with col_a:
    st.markdown(
        f"<div class='hub-tagline'>Multimodal POE movement planner · BTS NTAD</div>"
        f"<div class='hub-headline'>Pick origin, POE, and end-item — HUB compares road, rail, waterway, and air in one pane.</div>",
        unsafe_allow_html=True,
    )
with col_b:
    st.markdown(
        f"<div class='hub-card' style='text-align:right;'>"
        f"<div style='color:{BRAND['muted']};font-size:11px;letter-spacing:1px;'>CLASSIFICATION</div>"
        f"<div style='color:{BRAND['neon']};font-weight:700;letter-spacing:1.2px;'>UNCLASSIFIED // FOR PLANNING USE</div>"
        f"<div style='color:{BRAND['muted']};font-size:11px;letter-spacing:1px;margin-top:8px;'>POSTURE</div>"
        f"<div style='color:#FFFFFF;font-weight:700;'>On-prem · Kamiwaza Stack</div>"
        f"</div>",
        unsafe_allow_html=True,
    )

# Top metric strip — always populated from synthetic corpus
m1, m2, m3, m4 = st.columns(4)
with m1:
    st.metric("Hubs in network", f"{len(nodes)}")
with m2:
    st.metric("Typed edges (multimodal)", f"{len(edges)}")
with m3:
    st.metric("End-items in catalog", f"{len(items)}")
with m4:
    st.metric("Cached scenarios", f"{len(cache)}")

st.markdown("---")


# ──────────────────────────────────────────────────────────────────────────────
# Result panel
# ──────────────────────────────────────────────────────────────────────────────
result = st.session_state.result
if not result:
    st.info(
        "Pick a scenario in the sidebar and click **ANALYZE CORRIDOR**. "
        "Cached briefs render instantly; custom inputs trigger a live AI engine call."
    )
else:
    plan = result["plan"]
    jb = result["json_brief"]
    narrative = _strip_poe_headings(result["narrative"])
    plan["_all_nodes"] = nodes  # let charts.py draw the full base layer

    # ── BLUF strip ──
    rec = jb.get("recommended_mode", "n/a").upper()
    transit = jb.get("transit_days_estimate", "—")
    bn = jb.get("bottleneck_named", "—")
    cost_rel = jb.get("cost_relative", "—")
    src = result.get("_source") or st.session_state.get("result_source") or jb.get("_source", "cache")
    o = plan["origin"]; d = plan["destination"]; item = plan["end_item"]

    st.markdown(
        f"<div class='hub-card'>"
        f"<div style='display:flex;justify-content:space-between;align-items:center;'>"
        f"<div>"
        f"<span class='hub-pill pill-mode'>RECOMMENDED · {rec}</span> "
        f"<span class='hub-pill pill-go'>{transit} d transit</span> "
        f"<span class='hub-pill pill-cau'>cost {cost_rel}× road</span>"
        f"</div>"
        f"<div style='color:{BRAND['muted']};font-size:11px;'>brief source: {src}</div>"
        f"</div>"
        f"<div style='margin-top:10px;color:#FFFFFF;font-size:14px;'>"
        f"<b>{o['name']}</b> ({o['id']}) → <b>{d['name']}</b> ({d['id']}) · "
        f"<b>{item['id']}</b> {item['name']} · "
        f"named choke point: <span style='color:#FFB347;'>{bn}</span>"
        f"</div>"
        f"</div>",
        unsafe_allow_html=True,
    )

    # ── Map + per-mode panel ──
    g_left, g_right = st.columns([0.62, 0.38])
    with g_left:
        st.markdown("#### Corridor map — recommended mode highlighted")
        focus = jb.get("recommended_mode")
        fmap = charts.build_routing_map(plan, focus_mode=focus)
        st_folium(fmap, height=460, width=None, returned_objects=[], key="hub_map")

    with g_right:
        st.markdown("#### Per-mode feasibility")
        per_mode = plan["per_mode"]
        for mode in ("road", "rail", "waterway", "air"):
            mp = per_mode.get(mode, {})
            if not mp.get("available"):
                st.markdown(
                    f"<div class='hub-card' style='padding:8px 12px;margin-bottom:6px;'>"
                    f"<b style='color:#FFFFFF;text-transform:uppercase;'>{mode}</b> "
                    f"<span class='hub-pill pill-no'>NO PATH</span>"
                    f"</div>",
                    unsafe_allow_html=True,
                )
                continue
            s = mp["summary"]
            verdict = _verdict_pill(s["feasible"])
            bn_chip = (
                f"<span class='hub-pill pill-cau' style='font-size:10px;'>"
                f"⚠ {', '.join(s['named_bottlenecks'])}</span>"
                if s["named_bottlenecks"] else ""
            )
            tag = "RECOMMENDED" if mode == focus else ""
            tag_html = (
                f"<span class='hub-pill pill-go' style='font-size:10px;'>{tag}</span>"
                if tag else ""
            )
            st.markdown(
                f"<div class='hub-card' style='padding:10px 12px;margin-bottom:6px;'>"
                f"<div style='display:flex;justify-content:space-between;align-items:center;'>"
                f"<div><b style='color:#FFFFFF;text-transform:uppercase;'>{mode}</b> "
                f"{verdict} {tag_html}</div>"
                f"<div style='color:{BRAND['muted']};font-size:11px;font-family:Menlo,monospace;'>"
                f"{mp['transit_days']}d · {s['miles']:,} mi"
                f"</div></div>"
                f"<div style='color:#C0C0C0;font-size:12px;margin-top:4px;'>"
                f"min cap <b>{s['min_capacity_tpd']:,}</b> tpd · "
                f"clearance <b>{s['min_clearance_in']}</b>\" · "
                f"weight <b>{s['min_weight_limit_lbs']:,}</b> lb · "
                f"cost idx <b>{mp['cost_index']}</b></div>"
                f"<div style='margin-top:4px;'>{bn_chip}</div>"
                f"</div>",
                unsafe_allow_html=True,
            )

    # ── Plotly throughput bars ──
    c1, c2 = st.columns(2)
    with c1:
        st.plotly_chart(charts.build_throughput_bars(plan),
                        use_container_width=True, key="cap_bars")
    with c2:
        st.plotly_chart(charts.build_transit_cost_chart(plan),
                        use_container_width=True, key="time_cost_bars")

    # ── Hero narrative brief ──
    st.markdown("---")
    st.markdown("### POE Movement Plan")
    st.caption(
        f"Generated {result.get('generated_at','—')} · "
        f"Originator: HUB / LOGCOM movement-planning cell · brief source: {src}"
    )
    st.markdown(
        "<div class='hub-card' style='padding:22px 30px;'>",
        unsafe_allow_html=True,
    )
    st.markdown(narrative)
    st.markdown("</div>", unsafe_allow_html=True)

    # ── Structured JSON expander + raw evidence ──
    with st.expander("Show structured chat_json output"):
        st.json({k: v for k, v in jb.items() if not k.startswith("_")})

    with st.expander("Show per-mode evidence (deterministic engine)"):
        for mode, mp in plan["per_mode"].items():
            st.markdown(f"**{mode.upper()}**")
            if not mp.get("available"):
                st.markdown("- no path available")
                continue
            s = mp["summary"]
            st.markdown(
                f"- path: `{' → '.join(mp['node_path'])}`\n"
                f"- miles: {s['miles']:,} · transit_days: {mp['transit_days']} · "
                f"cost_index: {mp['cost_index']}\n"
                f"- min_capacity_tpd: {s['min_capacity_tpd']:,} · "
                f"min_clearance_in: {s['min_clearance_in']} · "
                f"min_weight_limit_lbs: {s['min_weight_limit_lbs']:,}\n"
                f"- named_bottlenecks: {', '.join(s['named_bottlenecks']) or 'none'}\n"
                f"- feasibility: {s['feasible']} · reasons: {'; '.join(s['reasons']) or 'ok'}"
            )

    with st.expander("Show end-item profile"):
        st.json(item)


# ──────────────────────────────────────────────────────────────────────────────
# Footer
# ──────────────────────────────────────────────────────────────────────────────
st.markdown(
    f"<div class='hub-footer'>"
    f"Powered by Kamiwaza · 100% Data Containment — Nothing ever leaves your accredited environment."
    f"</div>",
    unsafe_allow_html=True,
)
