# WILDFIRE — installation wildfire predictor + auto-MASCAL comms
# Part of the MDM 2026 Hackathon Templates (https://github.com/12fn/MDMhackathon-repos)
# MIT licensed. Built on GAI (Government Acquisitions, Inc.) + Kamiwaza (https://www.kamiwaza.ai/).
"""WILDFIRE — Streamlit frontend on port 3013.

Single-pane operator UI for an installation EOC watch officer:

  - Map: fire pixels (red dots, sized by FRP), installation polygons,
    wind vectors at the heaviest threat installation.
  - Alert ladder strip: one chip per installation, color-coded WATCH/ALERT/WARNING.
  - Hero button: Generate MASCAL Comms Package -> 4 tabs (email / banner / SMS / brief).
  - Timeline slider: replay the 6-hour burn growth.
"""
from __future__ import annotations

import json
import math
import os
import sys
from pathlib import Path

import folium
import pandas as pd
import requests
import streamlit as st
from streamlit_folium import st_folium

ROOT = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(ROOT))

from shared.kamiwaza_client import BRAND  # noqa: E402

# Optional direct import — used as in-process fallback if backend is down.
try:
    from src.risk import installation_threats  # noqa: F401
    from src.comms import generate_comms_package, quick_wind_summary, HERO_MODEL  # noqa: F401
except ImportError:
    sys.path.insert(0, str(Path(__file__).parent))
    from risk import installation_threats  # type: ignore  # noqa: F401
    from comms import generate_comms_package, quick_wind_summary, HERO_MODEL  # type: ignore  # noqa: F401

BACKEND = os.getenv("WILDFIRE_BACKEND_URL", "http://localhost:8013")
DATA = Path(__file__).resolve().parent.parent / "data"

# ---------------------------------------------------------------------------
# Page config + brand styling
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="WILDFIRE — USMC LOGCOM Installation Wildfire Predictor",
    page_icon="🔥",
    layout="wide",
    initial_sidebar_state="expanded",
)

CSS = f"""
<style>
.stApp {{ background-color: {BRAND['bg']}; color: #E5E5E5; }}
section[data-testid="stSidebar"] {{ background-color: {BRAND['surface']}; border-right: 1px solid {BRAND['border']}; }}
.block-container {{ padding-top: 1rem; padding-bottom: 1rem; }}
h1, h2, h3, h4 {{ color: {BRAND['neon']}; }}
.brand-bar {{ display: flex; align-items: center; justify-content: space-between; padding: 8px 14px;
              background: linear-gradient(90deg, #0E0E0E 0%, #111111 60%, #0E0E0E 100%);
              border: 1px solid {BRAND['border']}; border-radius: 8px; margin-bottom: 10px; }}
.brand-left {{ display: flex; align-items: center; gap: 14px; }}
.brand-left img {{ height: 28px; }}
.brand-title {{ color: {BRAND['neon']}; font-weight: 700; letter-spacing: 1px; }}
.brand-tag {{ color: {BRAND['muted']}; font-size: 12px; }}
.ladder-strip {{ display: flex; gap: 10px; flex-wrap: wrap; padding: 6px 0 12px 0; }}
.chip {{ padding: 8px 12px; border-radius: 8px; font-weight: 700; font-size: 13px;
         border: 1px solid {BRAND['border']}; min-width: 220px; }}
.chip .name {{ display: block; font-size: 12px; font-weight: 600; opacity: 0.85; }}
.chip .band {{ display: block; font-size: 16px; font-weight: 800; letter-spacing: 1px; }}
.chip .meta {{ display: block; font-size: 11px; opacity: 0.8; margin-top: 4px; }}
.chip.WARNING {{ background: #4a0d0d; border-color: #ff3b3b; color: #ffd6d6; }}
.chip.ALERT   {{ background: #4a2c0d; border-color: #ff9a3b; color: #ffe6c8; }}
.chip.WATCH   {{ background: #4a4a0d; border-color: #ffe23b; color: #fff7c8; }}
.chip.CLEAR   {{ background: #0d3a1f; border-color: {BRAND['primary']}; color: #c8ffe0; }}
.kamiwaza-footer {{ text-align: center; color: {BRAND['muted']}; font-size: 12px; padding: 12px 0; border-top: 1px solid {BRAND['border']}; margin-top: 16px; }}
.section-card {{ background: {BRAND['surface']}; border: 1px solid {BRAND['border']}; border-radius: 8px; padding: 12px 14px; margin-bottom: 10px; }}
.kpi {{ display: inline-block; margin-right: 22px; }}
.kpi .v {{ color: {BRAND['neon']}; font-weight: 700; font-size: 20px; }}
.kpi .l {{ color: {BRAND['muted']}; font-size: 11px; text-transform: uppercase; letter-spacing: 1px; }}
.banner-RED {{ background: #4a0d0d; border-left: 5px solid #ff3b3b; padding: 10px 14px; color: #ffd6d6; border-radius: 6px; font-weight: 700; }}
.banner-AMBER {{ background: #4a2c0d; border-left: 5px solid #ff9a3b; padding: 10px 14px; color: #ffe6c8; border-radius: 6px; font-weight: 700; }}
.banner-YELLOW {{ background: #4a4a0d; border-left: 5px solid #ffe23b; padding: 10px 14px; color: #fff7c8; border-radius: 6px; font-weight: 700; }}
.sms-bubble {{ background: #1f1f1f; border: 1px solid {BRAND['border']}; border-radius: 14px; padding: 10px 14px; max-width: 360px; color: #E5E5E5; font-family: ui-monospace, SFMono-Regular, monospace; }}
.email-card {{ background: {BRAND['surface_high']}; border: 1px solid {BRAND['border']}; border-radius: 6px; padding: 14px; }}
.email-card pre {{ background: transparent; color: #E5E5E5; white-space: pre-wrap; font-family: ui-monospace, SFMono-Regular, monospace; font-size: 13px; }}
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
      <div class="brand-title">WILDFIRE</div>
      <div class="brand-tag">Wildland Incident Locator & Detection For Installation Resilience and Evacuation</div>
    </div>
  </div>
  <div class="brand-tag">USMC LOGCOM CDAO :: MARADMIN 131/26 Installation Incident Response :: From a NASA satellite ping to a base-wide evacuation order in 90 seconds.</div>
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


@st.cache_data(ttl=5)
def get_installations() -> list[dict]:
    try:
        return requests.get(f"{BACKEND}/api/installations", timeout=2).json()
    except Exception:
        return json.loads((DATA / "installations.json").read_text())


@st.cache_data(ttl=5)
def get_fires(step: int | None) -> list[dict]:
    try:
        params = {"step": step} if step is not None else {}
        return requests.get(f"{BACKEND}/api/fires", params=params, timeout=2).json()
    except Exception:
        all_fires = json.loads((DATA / "fire_pixels.json").read_text())
        if step is None:
            return all_fires
        timeline = json.loads((DATA / "timeline.json").read_text())
        vis = set(timeline[step]["fire_ids"])
        return [f for f in all_fires if f["id"] in vis]


@st.cache_data(ttl=5)
def get_wind() -> list[dict]:
    try:
        return requests.get(f"{BACKEND}/api/wind", timeout=2).json()
    except Exception:
        df = pd.read_csv(DATA / "wind_grid.csv")
        return df.to_dict("records")


@st.cache_data(ttl=5)
def get_timeline() -> list[dict]:
    try:
        return requests.get(f"{BACKEND}/api/timeline", timeout=2).json()
    except Exception:
        return json.loads((DATA / "timeline.json").read_text())


@st.cache_data(ttl=5)
def get_threats(step: int | None) -> list[dict]:
    try:
        params = {"step": step} if step is not None else {}
        return requests.get(f"{BACKEND}/api/threats", params=params, timeout=4).json()
    except Exception:
        # In-process compute as fallback
        return installation_threats(
            get_installations(), get_fires(None), get_wind(),
            visible_ids=(set(get_timeline()[step]["fire_ids"]) if step is not None else None),
        )


def post_comms(installation_id: str, step: int | None, use_hero: bool = True) -> dict:
    try:
        r = requests.post(
            f"{BACKEND}/api/comms/{installation_id}",
            json={"step": step, "use_hero_model": use_hero},
            timeout=60,
        )
        r.raise_for_status()
        return r.json()
    except Exception:
        # In-process fallback so demo never dies
        from shared.kamiwaza_client import chat_json  # noqa: WPS433
        insts = get_installations()
        inst = next(i for i in insts if i["id"] == installation_id)
        threats = get_threats(step)
        block = next(t for t in threats if t["installation_id"] == installation_id)
        wind_summary = quick_wind_summary(block)
        pkg = generate_comms_package(
            chat_json, inst, block, wind_summary,
            model=(HERO_MODEL if use_hero else None),
        )
        return {
            "installation": {"id": inst["id"], "name": inst["name"], "centroid": inst["centroid"]},
            "step": step,
            "threat": block,
            "wind_summary": wind_summary,
            "comms_package": pkg,
        }


# ---------------------------------------------------------------------------
# Sidebar — controls
# ---------------------------------------------------------------------------
timeline = get_timeline()
n_steps = len(timeline)
with st.sidebar:
    st.markdown("### Operator Controls")
    step = st.slider(
        "Timeline (T-6h to T0)",
        0, n_steps - 1, n_steps - 1,
        help="Replay the 6-hour burn growth window. T0 is current.",
    )
    t_label = timeline[step]["t"]
    elapsed = timeline[step]["elapsed_hr"]
    st.caption(f"Step {step}/{n_steps-1}  |  T+{elapsed:.1f}h  |  {t_label}")

    show_wind = st.checkbox("Wind vectors overlay", True)
    show_polys = st.checkbox("Installation polygons", True)
    auto_zoom = st.checkbox("Auto-zoom to top threat", True)
    use_hero = st.checkbox("Use Kamiwaza-deployed hero model for comms", True,
                           help="One-time premium call for the demo wow shot.")

    st.markdown("---")
    st.markdown("### Backend")
    h = get_health()
    if h.get("ok"):
        st.success(
            f"OK — {h.get('primary_model')}\n\n"
            f"Endpoint: `{h.get('kamiwaza_endpoint')}`"
        )
    else:
        st.warning(
            f"Backend unreachable; using in-process compute.\n\n{h.get('error','')}"
        )

    st.markdown("---")
    st.markdown(
        f"<div class='brand-tag'>Models route through your Kamiwaza-deployed "
        f"endpoint — set <code>KAMIWAZA_BASE_URL</code> to keep all traffic "
        f"inside your wire.</div>",
        unsafe_allow_html=True,
    )


# ---------------------------------------------------------------------------
# Pull data for current step
# ---------------------------------------------------------------------------
installations = get_installations()
fires = get_fires(step)
wind = get_wind()
threats = get_threats(step)

# KPI header
total_pixels = len(fires)
warning_n = sum(1 for t in threats if t["alert_band"] == "WARNING")
alert_n = sum(1 for t in threats if t["alert_band"] == "ALERT")
watch_n = sum(1 for t in threats if t["alert_band"] == "WATCH")
clear_n = sum(1 for t in threats if t["alert_band"] == "CLEAR")
top = sorted(
    [t for t in threats if t["alert_band"] != "CLEAR"],
    key=lambda t: (
        {"WARNING": 0, "ALERT": 1, "WATCH": 2, "CLEAR": 3}[t["alert_band"]],
        t["nearest_distance_mi"] if t["nearest_distance_mi"] is not None else 999,
    ),
)
hero_target = top[0] if top else (threats[0] if threats else None)

st.markdown(
    f"""
<div class="section-card">
  <span class="kpi"><span class="v">{total_pixels}</span><span class="l">FIRMS Pixels Visible</span></span>
  <span class="kpi"><span class="v" style="color:#ff3b3b">{warning_n}</span><span class="l">Bases @ WARNING</span></span>
  <span class="kpi"><span class="v" style="color:#ff9a3b">{alert_n}</span><span class="l">Bases @ ALERT</span></span>
  <span class="kpi"><span class="v" style="color:#ffe23b">{watch_n}</span><span class="l">Bases @ WATCH</span></span>
  <span class="kpi"><span class="v" style="color:{BRAND['primary']}">{clear_n}</span><span class="l">Bases CLEAR</span></span>
  <span class="kpi"><span class="v">T+{elapsed:.1f}h</span><span class="l">Window Position</span></span>
</div>
""",
    unsafe_allow_html=True,
)


# ---------------------------------------------------------------------------
# Alert ladder strip
# ---------------------------------------------------------------------------
chips_html = ['<div class="ladder-strip">']
band_order = {"WARNING": 0, "ALERT": 1, "WATCH": 2, "CLEAR": 3}
for t in sorted(threats, key=lambda x: (band_order[x["alert_band"]], x["nearest_distance_mi"] or 999)):
    nd = t["nearest_distance_mi"]
    nd_str = f"{nd:.1f} mi" if nd is not None else "—"
    chips_html.append(
        f'<div class="chip {t["alert_band"]}">'
        f'<span class="name">{t["installation_name"]}</span>'
        f'<span class="band">{t["alert_band"]}</span>'
        f'<span class="meta">Nearest fire {nd_str} | {t["n_fires_within_50mi"]} pixels &lt;50mi</span>'
        f'</div>'
    )
chips_html.append("</div>")
st.markdown("\n".join(chips_html), unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Map + side panel
# ---------------------------------------------------------------------------
left, right = st.columns([2, 1], gap="medium")

with left:
    st.markdown("#### Common Operating Picture")
    # Center map
    if hero_target and auto_zoom:
        clat, clon = hero_target["centroid"]
        zoom = 9
    else:
        clat, clon = 36.5, -110.0
        zoom = 4

    m = folium.Map(
        location=[clat, clon], zoom_start=zoom,
        tiles="CartoDB dark_matter", control_scale=True,
    )

    # Installation polygons + centroids
    if show_polys:
        for inst in installations:
            band = next(
                (t["alert_band"] for t in threats if t["installation_id"] == inst["id"]),
                "CLEAR",
            )
            color = {"WARNING": "#ff3b3b", "ALERT": "#ff9a3b",
                     "WATCH": "#ffe23b", "CLEAR": BRAND["primary"]}[band]
            poly = inst["polygon"] + [inst["polygon"][0]]
            folium.Polygon(
                locations=poly,
                color=color,
                weight=3,
                fill=True,
                fill_color=color,
                fill_opacity=0.12,
                popup=folium.Popup(
                    f"<b>{inst['name']}</b><br>"
                    f"Personnel: {inst['personnel']:,}<br>"
                    f"Alert: <b>{band}</b>",
                    max_width=260,
                ),
                tooltip=f"{inst['name']} :: {band}",
            ).add_to(m)
            folium.CircleMarker(
                location=inst["centroid"],
                radius=4, color=color, fill=True, fill_color=color, fill_opacity=1.0,
                tooltip=inst["name"],
            ).add_to(m)

    # Fire pixels — size by FRP
    for f in fires:
        frp = f.get("frp") or 5
        radius = max(2.5, min(11.0, math.log1p(frp) * 1.7))
        opacity = 0.85 if f.get("hot") else 0.55
        folium.CircleMarker(
            location=[f["latitude"], f["longitude"]],
            radius=radius,
            color="#ff5a3c",
            weight=0,
            fill=True,
            fill_color="#ff5a3c",
            fill_opacity=opacity,
            tooltip=(f"{f['satellite']} | FRP {frp} MW | "
                     f"BR {f['brightness']} K | {f['acq_datetime']}"),
        ).add_to(m)

    # Wind vector overlay (only near hero target for clarity)
    if show_wind and hero_target:
        clat, clon = hero_target["centroid"]
        for w in wind:
            d = math.hypot(w["latitude"] - clat, w["longitude"] - clon)
            if d > 0.6:
                continue
            # Project u/v as a 0.05-0.15 deg arrow
            speed = max(0.5, w["speed_mps"])
            scale = 0.012 + min(0.06, speed * 0.0035)
            tip_lat = w["latitude"] + (w["v_mps"] / max(speed, 0.5)) * scale
            tip_lon = w["longitude"] + (w["u_mps"] / max(speed, 0.5)) * scale
            folium.PolyLine(
                locations=[[w["latitude"], w["longitude"]], [tip_lat, tip_lon]],
                color=BRAND["neon"], weight=2, opacity=0.85,
                tooltip=f"Wind {speed:.1f} m/s from {w['from_dir_deg']:.0f} deg",
            ).add_to(m)
            folium.CircleMarker(
                location=[tip_lat, tip_lon],
                radius=2, color=BRAND["neon"], fill=True, fill_opacity=1.0,
            ).add_to(m)

    st_folium(m, height=560, width=None, returned_objects=[], key="cop")

with right:
    st.markdown("#### Top-Threat Installation")
    if hero_target is None:
        st.info("No threat data.")
    else:
        ht = hero_target
        st.markdown(
            f"""
<div class="section-card">
  <div style="font-size:18px;font-weight:700;color:{BRAND['neon']}">{ht['installation_name']}</div>
  <div class="brand-tag">Centroid {ht['centroid'][0]:.3f}, {ht['centroid'][1]:.3f}</div>
  <div style="margin-top:6px"><span class="kpi"><span class="v" style="color:#ff3b3b">{ht['alert_band']}</span><span class="l">Alert Band</span></span>
  <span class="kpi"><span class="v">{(ht['nearest_distance_mi'] or 0):.1f} mi</span><span class="l">Nearest Fire</span></span>
  <span class="kpi"><span class="v">{ht['n_fires_within_50mi']}</span><span class="l">Pixels &lt;50 mi</span></span></div>
</div>
""",
            unsafe_allow_html=True,
        )
        # Top threats table
        if ht["top_threats"]:
            df = pd.DataFrame(ht["top_threats"])[
                ["fire_id", "distance_mi", "frp", "alignment",
                 "wind_speed_mps", "fire_to_base_bearing", "wind_to_dir_bearing", "priority_score"]
            ]
            st.markdown("**Top Threats (wind-projected priority)**")
            st.dataframe(df, use_container_width=True, height=220, hide_index=True)

        # Hero button
        st.markdown("&nbsp;")
        gen = st.button(
            f"Generate MASCAL Comms Package — {ht['installation_name']}",
            type="primary", use_container_width=True,
            disabled=(ht["alert_band"] == "CLEAR"),
        )
        if ht["alert_band"] == "CLEAR":
            st.caption("Available once an installation is at WATCH or higher.")

        if gen:
            with st.spinner("Drafting 4-channel MASCAL package via Kamiwaza-routed model..."):
                resp = post_comms(ht["installation_id"], step, use_hero=use_hero)
            st.session_state["last_comms"] = resp


# ---------------------------------------------------------------------------
# Comms package render
# ---------------------------------------------------------------------------
if "last_comms" in st.session_state:
    resp = st.session_state["last_comms"]
    pkg = resp["comms_package"]
    st.markdown("---")
    st.markdown(
        f"### Auto-Drafted MASCAL Communications Package — "
        f"`{pkg.get('incident_id','')}` :: **{pkg.get('alert_band','?')}**"
    )
    st.caption(
        f"Generated for {resp['installation']['name']} at step {resp['step']}. "
        f"Wind context: {resp['wind_summary']}"
    )

    tabs = st.tabs([
        "MARFORRES Email",
        "Intranet Banner",
        "Commander SMS",
        "Evacuation Brief",
    ])

    with tabs[0]:
        em = pkg.get("marforres_email", {})
        st.markdown(
            f"""
<div class="email-card">
<div class="brand-tag">FROM: {em.get('from','')}</div>
<div class="brand-tag">TO: {em.get('to','')}</div>
<div style="font-size:15px;font-weight:700;color:{BRAND['neon']};margin-top:6px">SUBJECT: {em.get('subject','')}</div>
<pre>{em.get('body','')}</pre>
</div>
""",
            unsafe_allow_html=True,
        )

    with tabs[1]:
        bn = pkg.get("base_intranet_banner", {})
        color = bn.get("color", "AMBER")
        st.markdown(
            f"<div class='banner-{color}'>{bn.get('text','')}</div>",
            unsafe_allow_html=True,
        )
        st.caption(f"Render color: {color}")

    with tabs[2]:
        sm = pkg.get("commander_sms", {})
        st.markdown(
            f"<div class='sms-bubble'>{sm.get('text','')}</div>",
            unsafe_allow_html=True,
        )
        recips = sm.get("recipients", [])
        st.caption(f"Recipients: {', '.join(recips) if recips else '—'}  |  "
                   f"Length: {len(sm.get('text',''))} chars")

    with tabs[3]:
        ev = pkg.get("evacuation_brief", {})
        st.markdown(f"**{ev.get('title','Evacuation Brief')}**")
        for b in ev.get("bullets", []):
            st.markdown(f"- {b}")
        st.caption(f"EOC reachback: {ev.get('eoc_phone','')}")

    with st.expander("Raw JSON (verifies structured-output JSON-mode)"):
        st.json(pkg)


# ---------------------------------------------------------------------------
# Footer
# ---------------------------------------------------------------------------
st.markdown(
    f"<div class='kamiwaza-footer'>{BRAND['footer']}  ::  "
    f"NASA FIRMS data shape :: KAMIWAZA_BASE_URL swap = on-prem in one env-var</div>",
    unsafe_allow_html=True,
)
