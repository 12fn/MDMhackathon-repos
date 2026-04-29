"""OMNI-INTEL -- All-Source Intelligence Fusion (USMC LOGCOM CDAO).

Streamlit mono on port 3043. 7 ISR streams normalized into one envelope, fused
by a cross-source correlator, classified per cluster, and composed into a
SIPR-style Daily All-Source Intelligence Brief (ASIB).
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import folium
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from streamlit_folium import st_folium

ROOT = Path(__file__).resolve().parent.parent
REPO = ROOT.parent.parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(ROOT / "src"))

from fusion import (  # noqa: E402
    CLASS_COLORS, INT_DISCIPLINE, SOURCE_COLORS, SOURCE_WEIGHTS,
    correlate_clusters, heuristic_classify, llm_classify,
)
from brief import compose_brief, get_cached  # noqa: E402
import audit  # noqa: E402

from shared.kamiwaza_client import BRAND  # noqa: E402

DATA = ROOT / "data"

# -----------------------------------------------------------------------------
# Page / theme
# -----------------------------------------------------------------------------
st.set_page_config(
    page_title="OMNI-INTEL  --  All-Source Fusion",
    page_icon="*",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    f"""
    <style>
      :root {{
        --bg: {BRAND['bg']};
        --surface: {BRAND['surface']};
        --surface_high: {BRAND['surface_high']};
        --border: {BRAND['border']};
        --primary: {BRAND['primary']};
        --neon: {BRAND['neon']};
        --muted: {BRAND['muted']};
      }}
      .stApp {{ background: var(--bg); color: #E5E5E5; }}
      section[data-testid="stSidebar"] {{ background: var(--surface) !important; }}
      .omni-title {{
          font-family: 'Helvetica Neue', sans-serif;
          font-size: 38px; font-weight: 800; letter-spacing: 3px;
          color: var(--neon);
          text-shadow: 0 0 14px rgba(0,255,167,0.40);
      }}
      .omni-tagline {{ color: var(--muted); font-size: 14px; margin-top: -6px; }}
      .omni-card {{
          background: var(--surface_high); border: 1px solid var(--border);
          padding: 14px 16px; border-radius: 10px;
      }}
      .omni-pill {{
          display: inline-block; padding: 2px 10px; border-radius: 999px;
          font-size: 11px; font-weight: 700; margin-right: 6px;
      }}
      .omni-trace {{
          font-family: 'JetBrains Mono', monospace; font-size: 11px;
          color: #B5FFE0; background: #06120D;
          padding: 8px 10px; border-left: 3px solid var(--neon);
          margin-bottom: 4px; border-radius: 4px;
      }}
      div[data-testid="stMetric"] {{
          background: var(--surface_high); border: 1px solid var(--border);
          padding: 10px; border-radius: 8px;
      }}
      .stButton > button {{
          background: var(--primary); color: #001a10; border: 0; font-weight: 700;
      }}
      .stButton > button:hover {{ background: var(--neon); color: #001a10; }}
      .omni-footer {{
          color: var(--muted); font-size: 11px; text-align: center;
          padding-top: 30px; border-top: 1px solid var(--border); margin-top: 30px;
      }}
    </style>
    """,
    unsafe_allow_html=True,
)


# -----------------------------------------------------------------------------
# Header
# -----------------------------------------------------------------------------
hcol1, hcol2 = st.columns([1, 6])
with hcol1:
    st.image(BRAND["logo_url"], width=110)
with hcol2:
    st.markdown('<div class="omni-title">OMNI-INTEL</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="omni-tagline">All-Source Intelligence Fusion &nbsp;|&nbsp; '
        '7 INT streams. One target picture. Daily ASIB at scale.</div>',
        unsafe_allow_html=True,
    )

st.write("")


# -----------------------------------------------------------------------------
# Load + normalize all 7 sources
# -----------------------------------------------------------------------------
@st.cache_data
def load_all() -> dict:
    bundle = json.loads((DATA / "all_observations.json").read_text())
    anchors = json.loads((DATA / "planted_fusions.json").read_text())["anchors"]
    obs = bundle["observations"]
    # parse dtg
    for o in obs:
        o["_ts"] = pd.to_datetime(o["dtg"])
    return {"obs": obs, "n": bundle["n_observations"], "by_src": bundle["sources"],
            "anchors": anchors}


def _load_warning() -> bool:
    if not (DATA / "all_observations.json").exists():
        st.error("Synthetic data not yet generated. Run `python data/generate.py` first.")
        return False
    return True


if not _load_warning():
    st.stop()

bundle = load_all()
all_obs = bundle["obs"]
src_counts = bundle["by_src"]
anchors = bundle["anchors"]


# -----------------------------------------------------------------------------
# Sidebar -- controls + KAMIWAZA env beat
# -----------------------------------------------------------------------------
st.sidebar.markdown("### OMNI-INTEL CONTROLS")
st.sidebar.caption("USMC LOGCOM CDAO  --  multi-INT fusion, demo build")

st.sidebar.markdown("**Active source streams**")
src_filter = {}
for s, n in src_counts.items():
    color = SOURCE_COLORS[s]
    label_html = f"<span style='color:{color};font-weight:700'>{INT_DISCIPLINE[s]}</span> -- {s.upper()} ({n:,})"
    st.sidebar.markdown(label_html, unsafe_allow_html=True)
    src_filter[s] = st.sidebar.checkbox(f"include {s}", value=True, key=f"f_{s}",
                                        label_visibility="collapsed")

st.sidebar.markdown("---")
st.sidebar.markdown("### Cross-source correlator")
time_window = st.sidebar.slider("Time window (min)", 30, 240, 120, 15)
space_radius = st.sidebar.slider("Space radius (km)", 1.0, 20.0, 8.0, 0.5)
min_sources = st.sidebar.slider("Min concurring INT sources", 2, 5, 2, 1)

st.sidebar.markdown("### Per-source confidence weighting")
st.sidebar.caption("Higher weight = harder to spoof. Drives weighted_score.")
for s, w in SOURCE_WEIGHTS.items():
    st.sidebar.progress(w, text=f"{s.upper()}  {w:.2f}  ({INT_DISCIPLINE[s]})")

st.sidebar.markdown("---")
st.sidebar.markdown("### Classifier")
use_llm = st.sidebar.checkbox("Use Kamiwaza-deployed model (chat_json)", value=True,
                              help="Off = deterministic heuristic baseline.")

st.sidebar.markdown("---")
st.sidebar.markdown("**On-prem deployment**")
st.sidebar.code("KAMIWAZA_BASE_URL=https://kamiwaza.local/api/v1\n"
                "# multi-INT fusion stays in the JWICS-equivalent enclave",
                language="bash")
st.sidebar.markdown(f"**{BRAND['footer']}**")


# -----------------------------------------------------------------------------
# Filter observations to active sources
# -----------------------------------------------------------------------------
active_obs = [o for o in all_obs if src_filter.get(o["source_type"], True)]


# -----------------------------------------------------------------------------
# KPIs
# -----------------------------------------------------------------------------
@st.cache_data(show_spinner=False)
def _correlate_cached(obs_ids: tuple, time_window: int, space_radius: float, min_sources: int):
    sub = [o for o in all_obs if o["observation_id"] in set(obs_ids)]
    return correlate_clusters(sub, time_window_min=time_window,
                              space_radius_km=space_radius, min_sources=min_sources)


clusters = _correlate_cached(tuple(o["observation_id"] for o in active_obs),
                             time_window, space_radius, min_sources)

# classify -- bounded for LLM speed
MAX_LLM = 12
classified: list = []
for c in clusters:
    if use_llm and len(classified) < MAX_LLM:
        c.classification = llm_classify(c)
    else:
        c.classification = heuristic_classify(c)
    classified.append(c)

# audit log a sample of the cluster decisions (only on first render per session)
if "audited" not in st.session_state:
    st.session_state.audited = True
    for c in classified[:8]:
        audit.append("correlate", c.cluster_id, {
            "centroid": [c.centroid_lat, c.centroid_lon],
            "sources_present": c.sources_present,
            "weighted_score": c.weighted_score,
            "n_obs": len(c.member_obs_ids),
        })
        audit.append("classify", c.cluster_id, {
            "label": c.classification.get("label"),
            "confidence": c.classification.get("confidence"),
            "rationale": c.classification.get("rationale", ""),
            "source": c.classification.get("source"),
        })


k1, k2, k3, k4, k5 = st.columns(5)
k1.metric("Total observations", f"{len(active_obs):,}")
k2.metric("INT streams active", f"{sum(1 for v in src_filter.values() if v)}/7")
k3.metric("Fusion clusters", f"{len(classified)}")
k4.metric("Highest weighted_score",
          f"{classified[0].weighted_score:.2f}" if classified else "0.00")
k5.metric("Distinct INT disciplines",
          f"{len(set(d for c in classified for d in c.int_disciplines))}/5"
          if classified else "0/5")

st.write("")


# -----------------------------------------------------------------------------
# Tabs
# -----------------------------------------------------------------------------
tab_map, tab_clusters, tab_per_src, tab_brief, tab_audit = st.tabs([
    "Fusion Map", "Cluster Inspector", "Per-Source Tabs", "Daily ASIB (Hero)",
    "Audit Chain"
])


# ---------- Fusion Map -------------------------------------------------------
with tab_map:
    left, right = st.columns([3, 2])
    with left:
        st.markdown("#### Multi-INT operational picture (color = source-type)")
        m = folium.Map(
            location=[10.5, 122.0], zoom_start=5,
            tiles="CartoDB dark_matter",
            attr="CARTO",
        )

        # downsample non-fusion observations for legibility
        sample = active_obs[::25]
        for o in sample:
            color = SOURCE_COLORS.get(o["source_type"], "#888888")
            folium.CircleMarker(
                location=[o["lat"], o["lon"]],
                radius=2.5, color=color, fill=True, fill_color=color,
                fill_opacity=0.65, opacity=0.65, weight=0,
                tooltip=f"{o['source_type'].upper()} -- {INT_DISCIPLINE[o['source_type']]}",
            ).add_to(m)

        # fusion clusters overlay
        for c in classified[:80]:
            label = c.classification.get("label", "ambiguous") if c.classification else "ambiguous"
            color = CLASS_COLORS.get(label, "#888888")
            popup_html = (
                f"<b>{c.cluster_id}</b><br>"
                f"label: <b>{label}</b> (conf {c.classification.get('confidence', 0):.2f})<br>"
                f"sources: {', '.join(c.sources_present)}<br>"
                f"INTs: {', '.join(c.int_disciplines)}<br>"
                f"weighted_score: {c.weighted_score:.2f}<br>"
                f"members: {len(c.member_obs_ids)}"
            )
            folium.CircleMarker(
                location=[c.centroid_lat, c.centroid_lon],
                radius=8 + min(20, c.weighted_score * 2),
                color=color, fill=True, fill_color=color, fill_opacity=0.55,
                weight=2, popup=folium.Popup(popup_html, max_width=320),
                tooltip=f"FUSION {c.cluster_id}: {label}",
            ).add_to(m)

        st_folium(m, height=540, use_container_width=True, key="omni_map",
                  returned_objects=[])

        # Legend
        legend = " ".join(
            f"<span class='omni-pill' style='background:{SOURCE_COLORS[s]};color:#000'>{s.upper()}</span>"
            for s in SOURCE_COLORS
        )
        st.markdown(f"**Source legend:** {legend}", unsafe_allow_html=True)
        legend2 = " ".join(
            f"<span class='omni-pill' style='background:{CLASS_COLORS[k]};color:#000'>{k}</span>"
            for k in CLASS_COLORS
        )
        st.markdown(f"**Cluster classification:** {legend2}", unsafe_allow_html=True)

    with right:
        st.markdown("#### Live fusion trace (top cluster)")
        if classified:
            top = classified[0]
            st.markdown(
                f"<div class='omni-card'><b>{top.cluster_id}</b> &nbsp; "
                f"<span class='omni-pill' style='background:"
                f"{CLASS_COLORS.get(top.classification.get('label','ambiguous'),'#888')};"
                f"color:#000'>{top.classification.get('label','ambiguous')}</span> "
                f"<span class='omni-pill' style='background:{BRAND['surface']};"
                f"color:{BRAND['neon']};border:1px solid {BRAND['border']}'>"
                f"score {top.weighted_score:.2f}</span></div>",
                unsafe_allow_html=True,
            )
            st.markdown("**Why the AI flagged this as a single target:**")
            for line in top.explanation_lines:
                st.markdown(f"<div class='omni-trace'>{line}</div>",
                            unsafe_allow_html=True)
            st.markdown("**Analyst rationale (chat_json):**")
            st.info(top.classification.get("rationale", "(no rationale)"))
            st.markdown("**Recommended ISR follow-up:**")
            st.success(top.classification.get("recommend", "(none)"))
            if top.fusion_anchor_truth:
                st.caption(
                    f"GROUND-TRUTH MATCH: this fusion corresponds to planted anchor "
                    f"{top.fusion_anchor_truth} (correlator rediscovered it without seeing the label)."
                )

    # Per-source activity timeline
    st.markdown("---")
    st.markdown("#### Per-source activity (24h window)")
    df = pd.DataFrame([{
        "src": o["source_type"].upper(),
        "INT": INT_DISCIPLINE[o["source_type"]],
        "ts": pd.to_datetime(o["dtg"]),
    } for o in active_obs])
    if not df.empty:
        df["bucket"] = df["ts"].dt.floor("30min")
        agg = df.groupby(["bucket", "src"]).size().reset_index(name="count")
        fig = px.area(
            agg, x="bucket", y="count", color="src",
            color_discrete_map={s.upper(): SOURCE_COLORS[s] for s in SOURCE_COLORS},
            labels={"bucket": "Time (UTC)", "count": "Observations / 30min", "src": "Source"},
        )
        fig.update_layout(
            plot_bgcolor=BRAND["bg"], paper_bgcolor=BRAND["bg"],
            font=dict(color="#E5E5E5"), height=240,
            margin=dict(l=10, r=10, t=10, b=10),
            xaxis=dict(gridcolor=BRAND["border"]),
            yaxis=dict(gridcolor=BRAND["border"]),
            legend=dict(bgcolor="rgba(14,14,14,0.7)"),
        )
        st.plotly_chart(fig, use_container_width=True, key="omni_timeline")


# ---------- Cluster Inspector ------------------------------------------------
with tab_clusters:
    st.markdown("#### Fusion-cluster inspector")
    if not classified:
        st.info("No fusion clusters in current filter. Loosen the correlator settings.")
    else:
        opts = [
            f"{c.cluster_id}  --  {c.classification.get('label','ambig')}  "
            f"({len(c.sources_present)} sources, score {c.weighted_score:.2f})"
            for c in classified
        ]
        sel = st.selectbox("Select fusion cluster",
                           options=range(len(classified)),
                           format_func=lambda i: opts[i])
        c = classified[sel]
        cls = c.classification or {}
        ll, rr = st.columns([2, 1])
        with ll:
            st.markdown(
                f"<span class='omni-pill' style='background:"
                f"{CLASS_COLORS.get(cls.get('label','ambiguous'),'#888')};color:#000'>"
                f"{cls.get('label','ambiguous')}</span>"
                f"<span class='omni-pill' style='background:{BRAND['surface_high']};"
                f"color:{BRAND['neon']};border:1px solid {BRAND['border']}'>"
                f"conf {cls.get('confidence',0):.2f}</span>"
                f"<span class='omni-pill' style='background:{BRAND['surface_high']};"
                f"color:{BRAND['muted']};border:1px solid {BRAND['border']}'>"
                f"{cls.get('source','heuristic')}</span>",
                unsafe_allow_html=True,
            )
            st.markdown("**Cross-source edges (explainability trace):**")
            for line in c.explanation_lines:
                st.markdown(f"<div class='omni-trace'>{line}</div>",
                            unsafe_allow_html=True)
            st.markdown("**Analyst rationale:**")
            st.info(cls.get("rationale", "(none)"))
            st.markdown("**Collection recommendation:**")
            st.success(cls.get("recommend", "(none)"))

        with rr:
            st.markdown("**Cluster fingerprint**")
            fingerprint = {
                "cluster_id":      c.cluster_id,
                "centroid":        f"{c.centroid_lat}, {c.centroid_lon}",
                "window":          f"{c.start_dtg} -> {c.end_dtg}",
                "sources_present": ", ".join(c.sources_present),
                "INTs":            ", ".join(c.int_disciplines),
                "n_observations":  len(c.member_obs_ids),
                "weighted_score":  c.weighted_score,
            }
            st.dataframe(
                pd.DataFrame({"feature": list(fingerprint.keys()),
                              "value": [str(v) for v in fingerprint.values()]}),
                use_container_width=True, hide_index=True,
            )
            if c.fusion_anchor_truth:
                st.caption(f"Ground-truth: planted anchor {c.fusion_anchor_truth}.")

        st.markdown("**Member observations**")
        members_df = pd.DataFrame([{
            "obs_id": m["observation_id"],
            "src":    m["source_type"].upper(),
            "INT":    INT_DISCIPLINE[m["source_type"]],
            "dtg":    m["dtg"],
            "lat":    m["lat"], "lon": m["lon"],
            "conf":   m["confidence"],
        } for m in c.members_full])
        st.dataframe(members_df, use_container_width=True, hide_index=True)


# ---------- Per-Source Tabs --------------------------------------------------
with tab_per_src:
    st.markdown("#### Per-source raw streams")
    src_tabs = st.tabs([s.upper() for s in src_counts.keys()])
    for stab, sname in zip(src_tabs, src_counts.keys()):
        with stab:
            st.caption(f"INT discipline: **{INT_DISCIPLINE[sname]}**  -- "
                       f"weight: **{SOURCE_WEIGHTS[sname]:.2f}**  -- "
                       f"native records: **{src_counts[sname]:,}**")
            sub = [o for o in active_obs if o["source_type"] == sname][:200]
            df = pd.DataFrame([{
                "obs_id":     o["observation_id"],
                "dtg":        o["dtg"],
                "lat":        o["lat"], "lon": o["lon"],
                "confidence": o["confidence"],
                **{f"raw.{k}": v for k, v in (o.get("raw_signature") or {}).items()},
            } for o in sub])
            st.dataframe(df, use_container_width=True, hide_index=True, height=380)


# ---------- Daily ASIB (Hero) ------------------------------------------------
with tab_brief:
    st.markdown("### Daily All-Source Intelligence Brief (ASIB) -- HERO")
    st.caption(
        "Pre-computed from the cached_briefs.json scenario library (cache-first). "
        "Live regen wraps the chat() call in a 35s watchdog with deterministic fallback."
    )

    cached = json.loads((DATA / "cached_briefs.json").read_text())
    scenario = st.selectbox("Scenario", options=list(cached.keys()))

    fusion_summary = {
        "n_clusters": len(classified),
        "by_int": {
            "GEOINT (AIS+FIRMS)": sum(1 for o in active_obs if o["source_type"] in ("ais","firms")),
            "SIGINT (DroneRF+WiFi/BT)": sum(1 for o in active_obs if o["source_type"] in ("dronerf","wifibt")),
            "MASINT (HIT-UAV)": sum(1 for o in active_obs if o["source_type"] == "hituav"),
            "IMINT (mil-object)": sum(1 for o in active_obs if o["source_type"] == "milobj"),
            "OSINT (ASAM)":  sum(1 for o in active_obs if o["source_type"] == "asam"),
        },
        "best_n_ints": max((len(c.int_disciplines) for c in classified), default=0),
        "top": [{
            "cluster_id": c.cluster_id,
            "classification": c.classification.get("label", "ambig"),
            "confidence": c.classification.get("confidence", 0),
            "n_sources": len(c.sources_present),
            "centroid": f"{c.centroid_lat},{c.centroid_lon}",
        } for c in classified[:5]],
    }

    bcol1, bcol2 = st.columns([3, 1])
    with bcol1:
        st.markdown(f"**Scenario:** {scenario}")
    with bcol2:
        regen = st.button("Regenerate ASIB (live, 35s watchdog)",
                          use_container_width=True)

    if regen:
        with st.spinner("Composing ASIB on Kamiwaza-deployed hero model..."):
            text = compose_brief(scenario, fusion_summary, timeout_s=35)
        # also audit-log the brief generation
        audit.append("brief", "ASIB", {"scenario": scenario, "n_chars": len(text)})
        st.session_state["omni_brief"] = text
    else:
        st.session_state.setdefault("omni_brief", cached.get(scenario, ""))

    st.markdown(
        f"<div class='omni-card'>{st.session_state['omni_brief'].replace(chr(10), '<br>')}</div>",
        unsafe_allow_html=True,
    )
    st.download_button(
        "Download brief (markdown)",
        data=st.session_state["omni_brief"],
        file_name=f"omni_asib_{datetime.now(timezone.utc).strftime('%Y%m%d')}.md",
        mime="text/markdown",
    )


# ---------- Audit Chain ------------------------------------------------------
with tab_audit:
    st.markdown("### Hash-chained audit log")
    st.caption(
        "Every fusion-cluster correlation, classification, and brief generation "
        "appends a SHA-256-chained entry. Tamper-evident per ICD 501. Required for "
        "SIGINT/HUMINT auditability when the pipeline is operating in JWICS-equivalent enclaves."
    )
    ok, n, msg = audit.verify_chain()
    if ok:
        st.success(f"Chain intact: {n} entries verified ({msg}).")
    else:
        st.error(f"CHAIN BROKEN: {msg}")

    rows = audit.tail(40)
    if rows:
        adf = pd.DataFrame([{
            "seq": r["seq"], "ts": r["ts"], "action": r["action"],
            "cluster_id": r["cluster_id"],
            "this_hash": r["this_hash"], "prev_hash": r["prev_hash"],
            "payload_keys": ", ".join(r["payload"].keys()),
        } for r in rows])
        st.dataframe(adf, use_container_width=True, hide_index=True, height=420)
    else:
        st.info("Chain is empty. Trigger a correlation to seed.")


# -----------------------------------------------------------------------------
# Footer
# -----------------------------------------------------------------------------
st.markdown(
    f"""
    <div class='omni-footer'>
      OMNI-INTEL  --  Mission frame: <b>contested logistics &amp; Stand-In Forces ISR</b> (MARADMIN 131/26).
      Data: synthetic across 7 ISR streams (AIS, ASAM, MIL-OBJ, HIT-UAV, DroneRF, WiFi/BT, FIRMS).
      Fusion: cross-source spatial-temporal correlator + chat_json classifier + hero ASIB composer.
      <br>On-prem swap: <code>KAMIWAZA_BASE_URL=https://kamiwaza.local/api/v1</code>  --
      multi-INT fusion stays in the JWICS-equivalent enclave.
      <br><b>{BRAND['footer']}</b>
    </div>
    """,
    unsafe_allow_html=True,
)
