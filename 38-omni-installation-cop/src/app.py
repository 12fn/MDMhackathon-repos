"""OMNI — Streamlit frontend on port 3038.

Mega-app I-COP / ERMP / Browser-AI-Gov dashboard for MCB Camp Pendleton.

Tabs:
  Overview      — KPIs, role-aware stream chips, Folium installation map,
                  live anomaly ticker (filtered through ABAC).
  Streams       — per-stream drill-down (denied streams shown as
                  "REDACTED — INSUFFICIENT CLEARANCE").
  Correlations  — cross-domain anomaly cards w/ explainability traces
                  (hero AI move; ABAC-filtered).
  Brief         — Commander's I-COP Brief (cache-first hero, ABAC-gated).
  Audit         — SHA-256 hash-chained who-saw-what audit log + verifier.

Sidebar persona switcher (CO / G-1 / G-2 / G-3 / G-4 / S-6) reshapes the
whole dashboard via ABAC. Every persona switch and brief view writes a
chained audit row.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import folium
import pandas as pd
import plotly.express as px
import requests
import streamlit as st
from streamlit_folium import st_folium

ROOT = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(ROOT))

from shared.kamiwaza_client import BRAND  # noqa: E402

# In-process fallbacks so the demo never dies if backend hiccups.
try:
    from src.correlator import (  # noqa: E402
        correlate_streams, commander_brief, baseline_correlation, baseline_brief,
    )
    from src.abac import (  # noqa: E402
        filter_streams_summary, filter_timeline, filter_anomalies,
        can_view_brief, can_view_audit,
    )
    from src.audit import (  # noqa: E402
        append_audit, read_audit_chain, verify_chain, reset_audit_log,
    )
except ImportError:
    sys.path.insert(0, str(Path(__file__).parent))
    from correlator import (  # type: ignore  # noqa: E402
        correlate_streams, commander_brief, baseline_correlation, baseline_brief,
    )
    from abac import (  # type: ignore  # noqa: E402
        filter_streams_summary, filter_timeline, filter_anomalies,
        can_view_brief, can_view_audit,
    )
    from audit import (  # type: ignore  # noqa: E402
        append_audit, read_audit_chain, verify_chain, reset_audit_log,
    )

BACKEND = os.getenv("OMNI_BACKEND_URL", "http://localhost:8038")
DATA = Path(__file__).resolve().parent.parent / "data"


# ---------------------------------------------------------------------------
# Page config + brand styling
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="OMNI — Cross-Domain Installation COP",
    page_icon="*",
    layout="wide",
    initial_sidebar_state="expanded",
)

CSS = f"""
<style>
.stApp {{ background-color: {BRAND['bg']}; color: #E5E5E5; }}
section[data-testid="stSidebar"] {{ background-color: {BRAND['surface']}; border-right: 1px solid {BRAND['border']}; }}
.block-container {{ padding-top: 1rem; padding-bottom: 1rem; max-width: 1620px; }}
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
.persona-card {{ background: {BRAND['surface_high']}; border: 1px solid {BRAND['border']};
                 border-left: 4px solid {BRAND['primary']}; border-radius: 6px;
                 padding: 8px 10px; margin: 8px 0; }}
.persona-card .id {{ color: {BRAND['neon']}; font-weight: 700; letter-spacing: 1px; font-size: 13px; }}
.persona-card .role {{ color: #E5E5E5; font-size: 13px; }}
.persona-card .clr {{ color: #ff9a3b; font-size: 11px; font-weight: 700; }}
.persona-card .abac {{ color: {BRAND['muted']}; font-size: 11px; margin-top: 4px; }}
.stream-chip {{ display: inline-block; padding: 8px 12px; border-radius: 8px;
                font-weight: 700; font-size: 12px; border: 1px solid {BRAND['border']};
                margin: 4px 6px 4px 0; min-width: 168px; background: {BRAND['surface_high']};
                color: #E5E5E5; }}
.stream-chip .name {{ display: block; font-size: 11px; color: {BRAND['muted']}; letter-spacing: 1px; }}
.stream-chip .v {{ display: block; font-size: 16px; color: {BRAND['neon']}; font-weight: 800; }}
.stream-chip .a {{ display: block; font-size: 11px; color: #ff7a3b; }}
.stream-chip.redacted {{ background: #1a0e0e; border: 1px dashed #6a1818; color: #6a1818; }}
.stream-chip.redacted .name {{ color: #6a1818; }}
.stream-chip.redacted .v {{ color: #6a1818; }}
.stream-chip.redacted .a {{ color: #6a1818; }}
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
.anomaly-card .domains {{ color: {BRAND['neon']}; font-weight: 700; font-size: 12px;
                          margin: 6px 0 2px 0; }}
.anomaly-card .streams span {{ display: inline-block; margin-right: 6px;
                               background: {BRAND['surface']}; color: {BRAND['neon']};
                               border: 1px solid {BRAND['border']}; padding: 2px 8px;
                               border-radius: 10px; font-size: 11px; }}
.anomaly-card .streams span.red {{ color: #6a1818; border-color: #6a1818;
                                   background: #1a0e0e; }}
.anomaly-card .hyp {{ margin-top: 6px; color: #E5E5E5; font-size: 14px; line-height: 1.45; }}
.anomaly-card .why {{ margin-top: 6px; color: {BRAND['muted']}; font-size: 12px; font-style: italic; }}
.anomaly-card .act {{ margin-top: 8px; color: {BRAND['neon']}; font-size: 13px; font-weight: 600; }}
.anomaly-card .conf {{ float: right; color: {BRAND['muted']}; font-size: 11px; margin-left: 8px; }}
.brief-box {{ background: {BRAND['surface_high']}; border: 1px solid {BRAND['border']};
              border-radius: 6px; padding: 14px; }}
.brief-box pre {{ background: transparent; color: #E5E5E5; white-space: pre-wrap;
                  font-family: ui-monospace, SFMono-Regular, monospace; font-size: 13px;
                  margin: 0; line-height: 1.5; }}
.ticker .item {{ background: {BRAND['surface_high']}; border: 1px solid {BRAND['border']};
                 border-radius: 6px; padding: 6px 10px; font-size: 12px; color: #E5E5E5;
                 white-space: nowrap; margin-bottom: 4px; }}
.ticker .item.anom {{ border-color: #ff3b3b; color: #ffd6d6; }}
.redacted-banner {{ background: #1a0e0e; border: 1px dashed #6a1818; color: #ff7a7a;
                    padding: 14px; border-radius: 6px; text-align: center;
                    font-weight: 700; letter-spacing: 1px; }}
button[kind="primary"] {{ background-color: {BRAND['primary']} !important; color: #001b10 !important; }}
.audit-row {{ background: {BRAND['surface_high']}; border: 1px solid {BRAND['border']};
              border-radius: 6px; padding: 8px 10px; margin-bottom: 6px;
              font-family: ui-monospace, SFMono-Regular, monospace; font-size: 11px; }}
.audit-row .h {{ color: {BRAND['muted']}; }}
.audit-row .ok {{ color: {BRAND['neon']}; font-weight: 700; }}
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
      <div class="brand-title">OMNI</div>
      <div class="brand-tag">Cross-domain Installation COP &middot; ERMP &middot; Browser-AI Governance &mdash; one operator screen, three LOGCOM use cases.</div>
    </div>
  </div>
  <div class="brand-tag">Six fused feeds &middot; cross-domain correlator &middot; role-aware ABAC &middot; hash-chained audit</div>
</div>
""",
    unsafe_allow_html=True,
)


# ---------------------------------------------------------------------------
# Backend-first loaders, in-process fallbacks for resilience.
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
def get_personas() -> list[dict]:
    try:
        return requests.get(f"{BACKEND}/api/personas", timeout=2).json()
    except Exception:
        return _file("personas.json")


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
            "rf": "rf_events.json",
            "drone_rf": "drone_rf_events.json",
            "firms": "firms.json",
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


def post_brief(correlation: dict | None = None, use_cache: bool = True,
               persona_id: str | None = None) -> dict:
    try:
        r = requests.post(f"{BACKEND}/api/brief",
                          json={"use_cache": use_cache,
                                "correlation": correlation,
                                "persona_id": persona_id},
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


def post_audit(persona_id: str, action: str, target: str | None = None,
               meta: dict | None = None) -> None:
    try:
        requests.post(f"{BACKEND}/api/audit",
                      json={"persona_id": persona_id, "action": action,
                            "target": target, "meta": meta or {}},
                      timeout=2)
    except Exception:
        # In-process fallback
        try:
            append_audit({"persona_id": persona_id, "action": action,
                          "target": target, "meta": meta or {}})
        except Exception:
            pass


def get_audit() -> list[dict]:
    try:
        return requests.get(f"{BACKEND}/api/audit", timeout=2).json()
    except Exception:
        return read_audit_chain(limit=50)


def get_audit_verify() -> dict:
    try:
        return requests.get(f"{BACKEND}/api/audit/verify", timeout=2).json()
    except Exception:
        ok, n, msg = verify_chain()
        return {"ok": ok, "rows_checked": n, "message": msg}


# ---------------------------------------------------------------------------
# Sidebar — persona switcher (the centerpiece of role-aware ABAC)
# ---------------------------------------------------------------------------
personas = get_personas()
persona_ids = [p["id"] for p in personas]

with st.sidebar:
    st.markdown("### Persona")
    pid = st.selectbox(
        "Operator persona (ABAC)",
        persona_ids,
        index=0,
        help=(
            "The dashboard reshapes itself for the selected persona. "
            "Streams the persona is not authorized for are returned as "
            "REDACTED. Anomalies are filtered by both the persona's allowed "
            "streams AND the inferred anomaly class."
        ),
        key="persona_selector",
    )
    persona = next(p for p in personas if p["id"] == pid)
    if st.session_state.get("_last_persona") != pid:
        post_audit(pid, "PERSONA_SWITCH", target=persona["role"],
                   meta={"allowed_streams": persona["allowed_streams"],
                         "clearance": persona["clearance"]})
        st.session_state["_last_persona"] = pid
    st.markdown(
        f"""
<div class="persona-card">
  <div class="id">{persona['id']} &nbsp;&middot;&nbsp; {persona['callsign']}</div>
  <div class="role">{persona['role']}</div>
  <div class="clr">CLEARANCE: {persona['clearance']}</div>
  <div class="abac">{persona['abac_summary']}</div>
</div>
""",
        unsafe_allow_html=True,
    )
    st.markdown("### Operator Controls")
    use_cache = st.checkbox(
        "Cache-first hero outputs",
        True,
        help=(
            "On = read pre-computed correlation + brief from data/cached_briefs.json. "
            "Off = fire a live AI call (timeout-bounded with deterministic fallback)."
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
            f"Backend unreachable; using in-process compute.\n\n{h.get('error', '')}"
        )
    st.markdown("---")
    st.markdown(
        f"<div class='brand-tag'>Models route through your Kamiwaza-deployed "
        f"endpoint. Set <code>KAMIWAZA_BASE_URL</code> to keep all traffic "
        f"inside your wire — air-gapped, IL5/IL6 ready.</div>",
        unsafe_allow_html=True,
    )


# ---------------------------------------------------------------------------
# Pull data + apply ABAC
# ---------------------------------------------------------------------------
inst = get_installation()
streams_summary_full = get_streams_summary()
streams_summary = filter_streams_summary(streams_summary_full, persona)
fused_full = get_timeline()
fused = filter_timeline(fused_full, persona)
cached = get_cached_briefs()

# KPI strip — totals reflect ABAC view (visible only)
total_events_visible = sum(s["count"] for s in streams_summary if not s.get("redacted"))
total_anoms_visible = sum(s["anomalies"] for s in streams_summary if not s.get("redacted"))
n_streams_total = len(streams_summary)
n_streams_visible = sum(1 for s in streams_summary if not s.get("redacted"))
n_streams_redacted = n_streams_total - n_streams_visible

st.markdown(
    f"""
<div class="section-card">
  <span class="kpi"><span class="v">{inst['name']}</span><span class="l">Installation</span></span>
  <span class="kpi"><span class="v">{n_streams_visible}/{n_streams_total}</span><span class="l">Streams Authorized</span></span>
  <span class="kpi"><span class="v">{total_events_visible}</span><span class="l">Visible Events / 24h</span></span>
  <span class="kpi"><span class="v" style="color:#ff3b3b">{total_anoms_visible}</span><span class="l">Visible Cross-Stream Flags</span></span>
  <span class="kpi"><span class="v" style="color:#6a1818">{n_streams_redacted}</span><span class="l">Streams Redacted</span></span>
  <span class="kpi"><span class="v">{cached.get('as_of_iso','')[:16].replace('T',' ')}</span><span class="l">As Of (UTC)</span></span>
</div>
""",
    unsafe_allow_html=True,
)

# Stream chips strip (ABAC-aware)
chips_html = ['<div style="margin: 6px 0 14px 0;">']
icon = {
    "gate": "GATE", "utility": "UTIL", "ems": "EMS",
    "massnotify": "ATHOC", "weather": "WX", "maintenance": "GCSS",
    "rf": "RF", "drone_rf": "DRONE-RF", "firms": "FIRMS",
}
for s in streams_summary:
    cls = "stream-chip redacted" if s.get("redacted") else "stream-chip"
    if s.get("redacted"):
        chips_html.append(
            f'<div class="{cls}">'
            f'<span class="name">{icon.get(s["stream"], s["stream"]).upper()}</span>'
            f'<span class="v">REDACTED</span>'
            f'<span class="a">INSUFFICIENT CLEARANCE</span>'
            f'</div>'
        )
    else:
        chips_html.append(
            f'<div class="{cls}">'
            f'<span class="name">{icon.get(s["stream"], s["stream"]).upper()}</span>'
            f'<span class="v">{s["count"]}</span>'
            f'<span class="a">{s["anomalies"]} flagged</span>'
            f'</div>'
        )
chips_html.append("</div>")
st.markdown("\n".join(chips_html), unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Tabs
# ---------------------------------------------------------------------------
tab_overview, tab_streams, tab_corr, tab_brief, tab_audit = st.tabs(
    ["Overview", "Streams", "Correlations", "Commander's Brief", "Audit"]
)


# ---------------------------------------------------------------------------
# OVERVIEW
# ---------------------------------------------------------------------------
with tab_overview:
    post_audit(persona["id"], "VIEW_DASHBOARD", target="overview",
               meta={"visible_streams": [s["stream"] for s in streams_summary if not s.get("redacted")]})

    left, right = st.columns([2, 1], gap="medium")

    with left:
        st.markdown("#### Common Operating Picture &mdash; Installation Map")
        clat, clon = inst["centroid"]
        m = folium.Map(location=[clat, clon], zoom_start=11,
                       tiles="CartoDB dark_matter", control_scale=True)
        poly = inst["polygon"] + [inst["polygon"][0]]
        folium.Polygon(
            locations=poly, color=BRAND["primary"], weight=2,
            fill=True, fill_color=BRAND["primary"], fill_opacity=0.06,
            tooltip=inst["name"],
        ).add_to(m)
        # Gates
        if "gate" in persona["allowed_streams"]:
            for g in inst.get("gates", []):
                folium.CircleMarker(
                    location=[g["lat"], g["lon"]], radius=5,
                    color=BRAND["neon"], fill=True, fill_color=BRAND["neon"], fill_opacity=0.85,
                    tooltip=f"{g['name']} (gate)",
                ).add_to(m)
        # Utility nodes
        if "utility" in persona["allowed_streams"]:
            for n in inst.get("utility_nodes", []):
                folium.CircleMarker(
                    location=[n["lat"], n["lon"]], radius=5,
                    color="#3bb6ff", fill=True, fill_color="#3bb6ff", fill_opacity=0.85,
                    tooltip=f"{n['name']} ({n['kind']} node)",
                ).add_to(m)
        # EMS units
        if "ems" in persona["allowed_streams"]:
            for u in inst.get("ems_units", []):
                folium.CircleMarker(
                    location=[u["lat"], u["lon"]], radius=5,
                    color="#ff9a3b", fill=True, fill_color="#ff9a3b", fill_opacity=0.85,
                    tooltip=f"{u['name']} ({u['type']})",
                ).add_to(m)
        # Comm nodes
        if "rf" in persona["allowed_streams"]:
            for c in inst.get("comm_nodes", []):
                folium.CircleMarker(
                    location=[c["lat"], c["lon"]], radius=5,
                    color="#c39bff", fill=True, fill_color="#c39bff", fill_opacity=0.85,
                    tooltip=f"{c['name']} ({c['kind']})",
                ).add_to(m)
        # HIFLD critical infrastructure
        for ci in inst.get("critical_infrastructure", []):
            folium.RegularPolygonMarker(
                location=[ci["lat"], ci["lon"]],
                number_of_sides=4, radius=6, color="#c39bff",
                fill=True, fill_color="#c39bff", fill_opacity=0.85,
                tooltip=f"HIFLD :: {ci['kind']} :: {ci['name']}",
            ).add_to(m)
        # Active visible anomalies
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
        st_folium(m, height=520, width=None, returned_objects=[], key=f"cop-{persona['id']}")

        # Plotly: stream-status panel (ABAC-aware bar chart)
        st.markdown("#### Stream Status &mdash; Volume + Anomalies")
        df_chart = pd.DataFrame([
            {
                "stream": s["stream"].upper(),
                "events": s["count"] if not s.get("redacted") else 0,
                "anomalies": s["anomalies"] if not s.get("redacted") else 0,
                "status": "REDACTED" if s.get("redacted") else "AUTHORIZED",
            }
            for s in streams_summary
        ])
        fig = px.bar(
            df_chart, x="stream", y="events", color="status",
            color_discrete_map={"AUTHORIZED": BRAND["primary"], "REDACTED": "#6a1818"},
            template="plotly_dark",
            labels={"events": "Events / 24h", "stream": "Stream"},
            height=240,
        )
        fig.update_layout(
            paper_bgcolor=BRAND["bg"], plot_bgcolor=BRAND["bg"],
            margin=dict(l=10, r=10, t=10, b=10),
            font=dict(color="#E5E5E5"),
            legend=dict(orientation="h", y=-0.18),
        )
        st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})

    with right:
        st.markdown("#### Live Anomaly Ticker")
        anom = [f for f in fused if f.get("is_anomaly")]
        anom = sorted(anom, key=lambda r: r["ts_iso"], reverse=True)[:18]
        if not anom:
            st.info("No anomalies visible to this persona in the last 24h.")
        ticker_html = ['<div class="ticker">']
        for a in anom:
            ticker_html.append(
                f"<div class='item anom'>"
                f"<b>{a['ts_iso'][11:16]}Z</b> "
                f"<span style='color:#00FFA7'>[{a['stream'].upper()}]</span> "
                f"{a.get('label','')[:120]}</div>"
            )
        ticker_html.append("</div>")
        st.markdown("\n".join(ticker_html), unsafe_allow_html=True)

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
    stream_options = [
        ("gate", "Gate ingress / egress (DBIDS-shape)"),
        ("utility", "Utility readings (DPW SCADA-shape)"),
        ("ems", "Fire / EMS dispatches (CAD-shape)"),
        ("massnotify", "Mass notification (AtHoc / Giant Voice)"),
        ("weather", "Weather (NASA Earthdata-shape)"),
        ("maintenance", "Maintenance (GCSS-MC-shape)"),
        ("rf", "RF fingerprinting (IEEE WiFi/BT)"),
        ("drone_rf", "Drone RF detections (DJI / non-cooperative)"),
        ("firms", "NASA FIRMS thermal pings"),
    ]
    pick = st.selectbox(
        "Stream",
        [s[0] for s in stream_options],
        format_func=lambda s: dict(stream_options)[s],
    )
    post_audit(persona["id"], "VIEW_STREAM", target=pick)
    if pick not in persona["allowed_streams"]:
        st.markdown(
            f"<div class='redacted-banner'>REDACTED &mdash; "
            f"INSUFFICIENT CLEARANCE FOR STREAM `{pick.upper()}`<br/>"
            f"Persona <b>{persona['id']}</b> ({persona['role']}) is not authorized for this stream.<br/>"
            f"Authorized streams: {', '.join(persona['allowed_streams'])}</div>",
            unsafe_allow_html=True,
        )
    else:
        rows = get_stream(pick)
        if show_anom_only and pick not in ("weather", "maintenance"):
            rows = [r for r in rows if r.get("is_anomaly")]
        if not rows:
            st.info("No records.")
        else:
            df = pd.DataFrame(rows)
            st.dataframe(df, use_container_width=True, height=520, hide_index=True)
            st.caption(
                f"{len(rows)} records :: "
                + ("flagged-only" if show_anom_only else "full window")
            )


# ---------------------------------------------------------------------------
# CORRELATIONS — hero AI move
# ---------------------------------------------------------------------------
with tab_corr:
    st.markdown("#### Cross-Domain Anomaly Correlator")
    st.caption(
        "Hero AI move: the correlator consumes the last 24h of fused events "
        "across six domains and emits anomalies that are corroborated across "
        "MULTIPLE DOMAINS in the same time window. Each card includes the "
        "domains-crossed count, the contributing streams (with redactions per "
        "persona), an explainability trace, and a confidence. Cache-first by "
        "default."
    )
    col_run, col_meta = st.columns([1, 3])
    with col_run:
        rerun = st.button("Run correlator", type="primary",
                          use_container_width=True, key="run-corr")
    if rerun or "last_corr_full" not in st.session_state:
        with st.spinner("Cross-domain correlation in flight..."):
            corr_full = post_correlate(use_cache=use_cache)
        st.session_state["last_corr_full"] = corr_full
    corr_full = st.session_state["last_corr_full"]
    corr = filter_anomalies(corr_full, persona)
    src = corr_full.get("_source", "?")
    with col_meta:
        st.markdown(
            f"<div class='brand-tag'>Source: <code>{src}</code> :: "
            f"{len(corr.get('anomalies', []))} cross-domain anomalies visible to "
            f"<b>{persona['id']}</b> "
            f"({len(corr_full.get('anomalies', [])) - len(corr.get('anomalies', []))} filtered "
            f"by ABAC)</div>",
            unsafe_allow_html=True,
        )

    for a in corr.get("anomalies", []):
        sev = a.get("severity", "MEDIUM")
        visible_streams = a.get("contributing_streams", [])
        red_streams = a.get("_redacted_streams", [])
        streams_html = "".join(f"<span>{s.upper()}</span>" for s in visible_streams)
        if red_streams:
            streams_html += "".join(
                f"<span class='red'>{s.upper()} REDACTED</span>" for s in red_streams
            )
        post_audit(persona["id"], "VIEW_ANOMALY",
                   target=a.get("anomaly_id", "?"),
                   meta={"severity": sev,
                         "domains_crossed": a.get("domains_crossed"),
                         "visible_streams": visible_streams,
                         "redacted_streams": red_streams})
        st.markdown(
            f"""
<div class="anomaly-card {sev}">
  <span class="id">{a.get('anomaly_id','?')}</span>
  <span class="sev {sev}">{sev}</span>
  <span class="conf">conf {a.get('confidence', 0):.2f}</span>
  <div class="domains">DOMAINS CROSSED: {a.get('domains_crossed','?')}</div>
  <div class="streams">{streams_html}</div>
  <div class="hyp">{a.get('hypothesis','')}</div>
  <div class="why">WHY FLAGGED: {a.get('explainability','')}</div>
  <div class="act">RECOMMENDED: {a.get('recommended_action','')}</div>
</div>
""",
            unsafe_allow_html=True,
        )

    if not corr.get("anomalies"):
        st.info(
            f"No cross-domain anomalies visible to persona {persona['id']}. "
            f"Higher-clearance personas (CO, G-2) may see more."
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
        "Live mode invokes the hero model (35s timeout, deterministic fallback). "
        "ABAC: only personas with `view_brief=true` may view."
    )
    if not can_view_brief(persona):
        post_audit(persona["id"], "BRIEF_DENIED", target="commander_brief")
        st.markdown(
            f"<div class='redacted-banner'>REDACTED &mdash; "
            f"PERSONA <b>{persona['id']}</b> NOT AUTHORIZED FOR COMMANDER'S BRIEF<br/>"
            f"This brief is restricted to roles with view_brief=true. "
            f"Switch persona to CO / G-2 / G-3 / G-4 / G-1 to view.</div>",
            unsafe_allow_html=True,
        )
    else:
        col_run, col_meta = st.columns([1, 3])
        with col_run:
            gen = st.button("Generate brief", type="primary",
                            use_container_width=True, key="run-brief")
        if gen or "last_brief" not in st.session_state:
            with st.spinner("Drafting Commander's I-COP Brief..."):
                corr_full = st.session_state.get("last_corr_full") or post_correlate(use_cache=use_cache)
                br = post_brief(correlation=corr_full, use_cache=use_cache,
                                persona_id=persona["id"])
            st.session_state["last_brief"] = br
        br = st.session_state["last_brief"]
        post_audit(persona["id"], "VIEW_BRIEF", target="commander_brief",
                   meta={"source": br.get("source"), "chars": len(br.get("brief", ""))})
        with col_meta:
            st.markdown(
                f"<div class='brand-tag'>Source: <code>{br.get('source','?')}</code> :: "
                f"{len(br.get('brief',''))} chars :: persona <b>{persona['id']}</b></div>",
                unsafe_allow_html=True,
            )
        st.markdown(
            f"<div class='brief-box'><pre>{br.get('brief','')}</pre></div>",
            unsafe_allow_html=True,
        )


# ---------------------------------------------------------------------------
# AUDIT (Browser-AI Governance tie-in)
# ---------------------------------------------------------------------------
with tab_audit:
    st.markdown("#### SHA-256 Hash-Chained Who-Saw-What Audit Log")
    st.caption(
        "Browser-AI Governance tie-in: every persona switch and every brief "
        "view is appended to a tamper-evident chain. Same pattern that "
        "GUARDIAN uses for browser-AI policy decisions. SJA / IG-replayable."
    )
    if not can_view_audit(persona):
        st.markdown(
            f"<div class='redacted-banner'>REDACTED &mdash; "
            f"PERSONA <b>{persona['id']}</b> NOT AUTHORIZED FOR AUDIT VIEW<br/>"
            f"Audit chain visibility restricted to CO / G-2.</div>",
            unsafe_allow_html=True,
        )
    else:
        col_v, col_m = st.columns([1, 3])
        with col_v:
            do_verify = st.button("Verify chain integrity", type="primary",
                                  use_container_width=True, key="verify")
        ver = get_audit_verify() if do_verify else get_audit_verify()
        with col_m:
            color = "ok" if ver.get("ok") else "h"
            st.markdown(
                f"<div class='audit-row'>"
                f"<span class='{color}'>"
                f"chain status: {'PASS' if ver.get('ok') else 'FAIL'}"
                f"</span> &nbsp;&middot;&nbsp; "
                f"<span class='h'>rows checked: {ver.get('rows_checked','?')}</span> &nbsp;&middot;&nbsp; "
                f"<span class='h'>{ver.get('message','')}</span>"
                f"</div>",
                unsafe_allow_html=True,
            )
        rows = get_audit()[:30]
        if not rows:
            st.info("Audit chain empty (no events yet).")
        for r in rows:
            st.markdown(
                f"<div class='audit-row'>"
                f"<span class='h'>{r.get('timestamp_utc','')[11:19]}Z</span> &nbsp;&middot;&nbsp; "
                f"<b>{r.get('persona_id','?')}</b> "
                f"&nbsp;<span style='color:#00FFA7'>{r.get('action','?')}</span>&nbsp; "
                f"<span class='h'>target=</span>{r.get('target','-')} &nbsp;"
                f"<span class='h'>hash=</span>{(r.get('entry_hash','')[:14])}…"
                f"</div>",
                unsafe_allow_html=True,
            )


# ---------------------------------------------------------------------------
# Footer — Kamiwaza on-prem env-var beat
# ---------------------------------------------------------------------------
st.markdown(
    f"<div class='kamiwaza-footer'>{BRAND['footer']}  ::  "
    f"HIFLD + NASA Earthdata + NASA FIRMS + GCSS-MC + IEEE WiFi/BT + Drone RF "
    f"(synthetic stand-ins; load_real.py documents the swap) :: "
    f"<code>KAMIWAZA_BASE_URL</code> swap = on-prem in one env-var</div>",
    unsafe_allow_html=True,
)
