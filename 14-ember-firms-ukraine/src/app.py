# EMBER — combat-fire signature analytics + ASIB brief
# Part of the MDM 2026 Hackathon Templates (https://github.com/12fn/MDMhackathon-repos)
# MIT licensed. Built on GAI (Government Acquisitions, Inc.) + Kamiwaza (https://www.kamiwaza.ai/).
"""EMBER -- Engagement & Munitions Burn-signature Extraction & Reconnaissance.

Streamlit app on port 3014. Conflict-zone combustion analytics for USMC LOGCOM.
"""
from __future__ import annotations

import json
import sys
from dataclasses import asdict
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

ROOT = Path(__file__).resolve().parent.parent
REPO = ROOT.parent.parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(ROOT / "src"))

from cluster import (  # noqa: E402
    CLASS_COLORS,
    ClusterSummary,
    cluster_pixels,
    heuristic_classify,
    llm_classify,
)
from brief import generate_brief  # noqa: E402
from shared.kamiwaza_client import BRAND  # noqa: E402

DATA_PATH = ROOT / "data" / "firms_ukraine.json"


# ---------- page config ----------
st.set_page_config(
    page_title="EMBER -- Conflict-Zone Combustion Analytics",
    page_icon="??",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---------- dark theme CSS ----------
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
      .ember-title {{
          font-family: 'Helvetica Neue', sans-serif;
          font-size: 36px; font-weight: 800; letter-spacing: 2px;
          color: var(--neon);
          text-shadow: 0 0 12px rgba(0,255,167,0.35);
      }}
      .ember-tagline {{ color: var(--muted); font-size: 14px; margin-top: -6px; }}
      .ember-card {{
          background: var(--surface_high); border: 1px solid var(--border);
          padding: 14px 16px; border-radius: 10px;
      }}
      .ember-kpi {{
          font-size: 30px; color: var(--primary); font-weight: 700;
      }}
      .ember-kpi-label {{ color: var(--muted); font-size: 12px; text-transform: uppercase; }}
      .ember-footer {{
          color: var(--muted); font-size: 11px; text-align: center;
          padding-top: 30px; border-top: 1px solid var(--border); margin-top: 30px;
      }}
      .ember-pill {{
          display: inline-block; padding: 2px 8px; border-radius: 999px;
          font-size: 11px; font-weight: 700; margin-right: 6px;
      }}
      div[data-testid="stMetric"] {{
          background: var(--surface_high); border: 1px solid var(--border);
          padding: 10px; border-radius: 8px;
      }}
      .stButton > button {{
          background: var(--primary); color: #001a10; border: 0; font-weight: 700;
      }}
      .stButton > button:hover {{ background: var(--neon); color: #001a10; }}
    </style>
    """,
    unsafe_allow_html=True,
)


# ---------- data load ----------
@st.cache_data
def load_pixels() -> pd.DataFrame:
    raw = json.loads(DATA_PATH.read_text())
    df = pd.DataFrame(raw["pixels"])
    # Parse to UTC then drop tz-info so all downstream comparisons (slider,
    # filter, cluster module) are naive-UTC. The "Z" suffix on the source ISO
    # strings would otherwise produce tz-aware timestamps that won't compare
    # to the tz-naive datetime() values used by the slider.
    df["acq_datetime"] = pd.to_datetime(df["acq_datetime"], utc=True).dt.tz_localize(None)
    return df


@st.cache_data
def run_clustering(df: pd.DataFrame, eps: float, min_samples: int):
    pixels = df.to_dict("records")
    # convert datetime back to ISO string for cluster module
    for p in pixels:
        if isinstance(p["acq_datetime"], pd.Timestamp):
            p["acq_datetime"] = p["acq_datetime"].isoformat() + "Z"
    labels, summaries = cluster_pixels(pixels, eps=eps, min_samples=min_samples)
    return labels, summaries


def classify_clusters(summaries: list[ClusterSummary], use_llm: bool) -> list[ClusterSummary]:
    out = []
    for s in summaries:
        if use_llm:
            classification = llm_classify(s)
        else:
            label, conf, why = heuristic_classify(s)
            classification = {"label": label, "confidence": conf, "rationale": why,
                              "recommend": "Cross-cue with SIGINT/UAS for confirmation.",
                              "source": "heuristic"}
        s.llm = classification  # type: ignore[attr-defined]
        out.append(s)
    return out


# ---------- header ----------
col_logo, col_title = st.columns([1, 5])
with col_logo:
    st.image(BRAND["logo_url"], width=100)
with col_title:
    st.markdown('<div class="ember-title">EMBER</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="ember-tagline">Engagement &amp; Munitions Burn-signature '
        "Extraction &amp; Reconnaissance &nbsp;|&nbsp; "
        "Every artillery shell that lands shows up in a NASA satellite. "
        "EMBER reads the burns and writes the brief.</div>",
        unsafe_allow_html=True,
    )

st.write("")

# ---------- load data ----------
df = load_pixels()
min_date = df["acq_datetime"].min().to_pydatetime()
max_date = df["acq_datetime"].max().to_pydatetime()

# ---------- sidebar controls ----------
st.sidebar.markdown("### EMBER Controls")
st.sidebar.caption("USMC LOGCOM CDAO -- demo build")

window_days = st.sidebar.slider(
    "Time window (days)", min_value=3, max_value=60, value=14, step=1
)
end_dt = st.sidebar.slider(
    "Window end (scrub time)",
    min_value=min_date + timedelta(days=window_days),
    max_value=max_date,
    value=datetime(2025, 7, 15),
    format="YYYY-MM-DD",
)
start_dt = end_dt - timedelta(days=window_days)

st.sidebar.markdown("### Cluster parameters")
eps = st.sidebar.slider("DBSCAN eps", 0.05, 0.5, 0.18, 0.01)
min_samples = st.sidebar.slider("DBSCAN min_samples", 2, 12, 4, 1)

st.sidebar.markdown("### Classifier")
use_llm = st.sidebar.checkbox(
    "Use Kamiwaza LLM (chat_json)", value=True,
    help="Off = deterministic heuristic baseline.",
)

st.sidebar.markdown("---")
st.sidebar.markdown("**Stack**")
st.sidebar.code(
    "DBSCAN (sklearn) + chat_json\n"
    "Map: Plotly + OSM tiles\n"
    "LLM: Kamiwaza Gateway",
    language="text",
)

# ---------- filter ----------
window_df = df[(df["acq_datetime"] >= start_dt) & (df["acq_datetime"] <= end_dt)].reset_index(drop=True)


# ---------- KPIs ----------
k1, k2, k3, k4, k5 = st.columns(5)
k1.metric("Pixels in window", f"{len(window_df):,}")
k2.metric("Total radiative power", f"{window_df['frp_mw'].sum():,.0f} MW")
k3.metric("Window span", f"{window_days} d")
k4.metric("Oblasts hit", f"{window_df['oblast'].nunique()}")
k5.metric("Pixel archive", f"{len(df):,} / 24 mo")

st.write("")


# ---------- run clustering ----------
labels, summaries = run_clustering(window_df, eps, min_samples)

# Classify (skip if too many clusters for LLM speed)
max_llm = 30
classified = classify_clusters(
    summaries[:max_llm] if use_llm else summaries,
    use_llm=use_llm,
)
if use_llm and len(summaries) > max_llm:
    # heuristic-fill the tail
    for s in summaries[max_llm:]:
        label, conf, why = heuristic_classify(s)
        s.llm = {"label": label, "confidence": conf, "rationale": why,
                 "recommend": "Cross-cue with SIGINT/UAS for confirmation.",
                 "source": "heuristic-tail"}
        classified.append(s)


# ---------- map + selection ----------
left, right = st.columns([3, 2])
with left:
    st.markdown("#### Cluster overlay (color = inferred class)")
    if not classified:
        st.info("No clusters in window. Widen the time window or relax DBSCAN.")
    else:
        rows = []
        for s in classified:
            rows.append({
                "cluster_id": s.cluster_id,
                "lat": s.centroid_lat,
                "lon": s.centroid_lon,
                "label": s.llm["label"],
                "confidence": s.llm["confidence"],
                "n_pixels": s.n_pixels,
                "max_frp": s.max_frp_mw,
                "oblast": s.dominant_oblast,
                "duration_h": s.duration_hours,
                "spread_km": s.spread_km,
            })
        cdf = pd.DataFrame(rows)
        cdf["color"] = cdf["label"].map(CLASS_COLORS).fillna(CLASS_COLORS["ambiguous"])
        cdf["size"] = (cdf["n_pixels"].clip(lower=4)) * 1.4

        # underlying pixels for context
        pdf = window_df.copy()
        pdf["color"] = "#444444"

        fig = go.Figure()
        fig.add_trace(go.Scattermap(
            lat=pdf["lat"], lon=pdf["lon"],
            mode="markers",
            marker=dict(size=4, color="#3a3a3a", opacity=0.55),
            name="raw FIRMS pixel",
            hoverinfo="skip",
        ))
        for label_class, sub in cdf.groupby("label"):
            fig.add_trace(go.Scattermap(
                lat=sub["lat"], lon=sub["lon"],
                mode="markers",
                marker=dict(
                    size=sub["size"].tolist(),
                    color=CLASS_COLORS.get(label_class, CLASS_COLORS["ambiguous"]),
                    opacity=0.85,
                ),
                text=[
                    f"cluster {r.cluster_id}<br>{r.label} ({r.confidence:.2f})<br>"
                    f"oblast: {r.oblast}<br>n={r.n_pixels}, FRP={r.max_frp:.0f} MW<br>"
                    f"dur {r.duration_h:.1f} h, spread {r.spread_km:.1f} km"
                    for r in sub.itertuples()
                ],
                hoverinfo="text",
                name=label_class,
            ))
        fig.update_layout(
            map=dict(
                style="carto-darkmatter",
                center=dict(lat=48.8, lon=34.0),
                zoom=5.2,
            ),
            margin=dict(l=0, r=0, t=0, b=0),
            height=520,
            paper_bgcolor=BRAND["bg"],
            font=dict(color="#E5E5E5"),
            legend=dict(bgcolor="rgba(14,14,14,0.7)", bordercolor=BRAND["border"]),
        )
        st.plotly_chart(fig, use_container_width=True, key="ember_map")

with right:
    st.markdown("#### Cluster inspector")
    if classified:
        options = [
            f"#{s.cluster_id} -- {s.llm['label']} -- {s.dominant_oblast} (n={s.n_pixels})"
            for s in classified
        ]
        sel = st.selectbox("Select cluster", options=range(len(classified)),
                           format_func=lambda i: options[i])
        s = classified[sel]
        c = s.llm
        st.markdown(
            f"<span class='ember-pill' style='background:{CLASS_COLORS.get(c['label'], '#888')};color:#000'>"
            f"{c['label']}</span>"
            f"<span class='ember-pill' style='background:{BRAND['surface_high']};"
            f"color:{BRAND['neon']};border:1px solid {BRAND['border']}'>"
            f"conf {c['confidence']:.2f}</span>"
            f"<span class='ember-pill' style='background:{BRAND['surface_high']};"
            f"color:{BRAND['muted']};border:1px solid {BRAND['border']}'>"
            f"{c.get('source', '')}</span>",
            unsafe_allow_html=True,
        )

        st.markdown("**Feature vector**")
        fv = {
            "centroid": f"{s.centroid_lat}, {s.centroid_lon}",
            "oblast": s.dominant_oblast,
            "n_pixels": s.n_pixels,
            "duration": f"{s.duration_hours:.1f} h",
            "spread / bbox": f"{s.spread_km:.1f} / {s.bbox_km:.1f} km",
            "mean / max brightness": f"{s.mean_brightness_k:.0f} / {s.max_brightness_k:.0f} K",
            "mean / max / sum FRP": f"{s.mean_frp_mw:.1f} / {s.max_frp_mw:.1f} / {s.sum_frp_mw:.0f} MW",
            "point score": f"{s.point_score:.2f}",
            "burst score": f"{s.burst_score:.2f}",
            "high-confidence frac": f"{s.high_conf_frac:.2f}",
            "night frac": f"{s.night_frac:.2f}",
            "window": f"{s.start_iso[:16]} -> {s.end_iso[:16]}",
        }
        st.dataframe(
            pd.DataFrame({"feature": list(fv.keys()), "value": list(fv.values())}),
            use_container_width=True, hide_index=True,
        )

        st.markdown("**Analyst rationale**")
        st.info(c.get("rationale", "(no rationale)"))
        st.markdown("**Collection recommendation**")
        st.success(c.get("recommend", "Cross-cue with SIGINT/UAS for confirmation."))


st.write("")

# ---------- timeline ----------
st.markdown("#### Combustion timeline (window)")
if not window_df.empty:
    tline = window_df.copy()
    tline["bucket"] = tline["acq_datetime"].dt.floor("D")
    timeline = (tline.groupby(["bucket", "truth_class"]).size()
                     .reset_index(name="count"))
    fig2 = px.bar(
        timeline, x="bucket", y="count", color="truth_class",
        color_discrete_map={
            "combat_artillery": CLASS_COLORS["combat_artillery"],
            "combat_armor":     CLASS_COLORS["combat_armor"],
            "industrial":       CLASS_COLORS["industrial"],
            "wildfire":         CLASS_COLORS["wildfire"],
            "structure":        CLASS_COLORS["structure"],
        },
        labels={"bucket": "Date (UTC)", "count": "FIRMS pixels", "truth_class": "Source"},
    )
    fig2.update_layout(
        plot_bgcolor=BRAND["bg"], paper_bgcolor=BRAND["bg"],
        font=dict(color="#E5E5E5"),
        height=260, margin=dict(l=10, r=10, t=10, b=10),
        legend=dict(bgcolor="rgba(14,14,14,0.7)"),
        xaxis=dict(gridcolor=BRAND["border"]),
        yaxis=dict(gridcolor=BRAND["border"]),
    )
    st.plotly_chart(fig2, use_container_width=True, key="ember_timeline")


# ---------- daily brief ----------
st.markdown("---")
b_col1, b_col2 = st.columns([3, 1])
with b_col1:
    st.markdown("### Daily All-Source Intelligence Brief (ASIB)")
    st.caption("Hero LLM call -- generates a SIPR-format daily brief from the classified clusters in window.")
with b_col2:
    gen = st.button("Generate today's brief", use_container_width=True)

if gen and classified:
    with st.spinner("Composing ASIB..."):
        try:
            date_z = end_dt.strftime("%d%H%MZ %b %Y").upper()
            brief = generate_brief(classified, date_z=date_z)
            st.session_state["ember_brief"] = brief
        except Exception as e:  # noqa: BLE001
            st.error(f"Brief generation failed: {e}")

if "ember_brief" in st.session_state:
    st.markdown(
        f"<div class='ember-card'>{st.session_state['ember_brief']}</div>",
        unsafe_allow_html=True,
    )
    st.download_button(
        "Download brief (markdown)",
        data=st.session_state["ember_brief"],
        file_name=f"ember_asib_{end_dt.strftime('%Y%m%d')}.md",
        mime="text/markdown",
    )


# ---------- footer ----------
st.markdown(
    f"""
    <div class='ember-footer'>
      EMBER -- Mission frame: <b>contested logistics &amp; Stand-In Forces ISR</b> (MARADMIN 131/26).
      Data: synthetic FIRMS-format (5,000 pixels, 24 mo). Plug-in to NASA FIRMS Ukraine 2-yr archive.
      Classifier: DBSCAN + Kamiwaza Gateway (Kamiwaza-deployed mini → hero).
      <br>On-prem swap: <code>KAMIWAZA_BASE_URL=https://kamiwaza.local/api/v1</code>.
      <br><b>{BRAND['footer']}</b>
    </div>
    """,
    unsafe_allow_html=True,
)
