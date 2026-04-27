"""GHOST — RF Pattern of Life Survey. Streamlit single-page app on port 3021.

Demo path:
  - Synthetic ~5,000-event scan over Camp Pendleton main gate perimeter.
  - DBSCAN over (lat, lon, scaled_time) → clusters.
  - Folium dark heatmap + neon cluster overlay.
  - Plotly time-bucket histogram of activity.
  - Per-cluster `chat_json` classifier (cluster_type / device / TOD / confidence).
  - Hero `chat` (gpt-5.4) RF Pattern of Life Survey — cache-first.

Run:
  streamlit run src/app.py --server.port 3021 --server.headless true \\
    --server.runOnSave false --server.fileWatcherType none \\
    --browser.gatherUsageStats false
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import folium
import numpy as np
import pandas as pd
import plotly.express as px
import streamlit as st
from folium.plugins import HeatMap
from sklearn.cluster import DBSCAN
from streamlit_folium import st_folium

# repo root on sys.path so `from shared.kamiwaza_client import BRAND` works
ROOT = Path(__file__).resolve().parent.parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from shared.kamiwaza_client import BRAND  # noqa: E402

# allow `from agent import ...`
sys.path.insert(0, str(Path(__file__).resolve().parent))
from agent import classify_cluster, generate_survey  # noqa: E402


APP_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = APP_DIR / "data"
RF_CSV = DATA_DIR / "rf_events.csv"
VENDOR_CSV = DATA_DIR / "vendor_oui.csv"
CACHE_PATH = DATA_DIR / "cached_briefs.json"

# Pendleton main gate
GATE_LAT, GATE_LON = 33.2106, -117.3973


st.set_page_config(
    page_title="GHOST — RF Pattern of Life Survey",
    page_icon="📡",
    layout="wide",
    initial_sidebar_state="expanded",
)


# ─────────────────────────────────────────────────────────────────────────────
# Kamiwaza dark theme
# ─────────────────────────────────────────────────────────────────────────────
KAMIWAZA_CSS = f"""
<style>
:root {{
  --kw-bg:        {BRAND['bg']};
  --kw-surface:   {BRAND['surface']};
  --kw-surface2:  {BRAND['surface_high']};
  --kw-border:    {BRAND['border']};
  --kw-primary:   {BRAND['primary']};
  --kw-neon:      {BRAND['neon']};
  --kw-muted:     {BRAND['muted']};
}}
.stApp, body {{ background: var(--kw-bg) !important; color: #E5E5E5; }}
.block-container {{ padding-top: 1.0rem; max-width: 1500px; }}
section[data-testid="stSidebar"] {{
  background: var(--kw-surface) !important; border-right: 1px solid var(--kw-border);
}}
section[data-testid="stSidebar"] * {{ color: #E5E5E5 !important; }}
h1, h2, h3, h4 {{ color: #FFFFFF; letter-spacing: 0.4px; }}
h1 {{ font-weight: 700; }}
.stButton > button, .stDownloadButton > button {{
  background: var(--kw-primary); color: #04140C; border: none; font-weight: 600;
  border-radius: 6px;
}}
.stButton > button:hover {{ background: {BRAND['primary_hover']}; color: #04140C; }}
.metric-card {{
  background: var(--kw-surface2); border: 1px solid var(--kw-border);
  border-radius: 10px; padding: 12px 14px; margin-bottom: 6px;
}}
.metric-card .label {{ color: var(--kw-muted); font-size: 0.74rem; text-transform: uppercase;
  letter-spacing: 0.7px; }}
.metric-card .val {{ color: var(--kw-neon); font-size: 1.5rem; font-weight: 700; }}
.metric-card .sub {{ color: #BDBDBD; font-size: 0.78rem; }}
.mis-panel {{
  background: var(--kw-surface2); border: 1px solid var(--kw-border);
  border-left: 3px solid var(--kw-primary);
  border-radius: 8px; padding: 14px 18px; font-family: 'JetBrains Mono', ui-monospace,
  Menlo, monospace; font-size: 0.86rem; line-height: 1.5; white-space: pre-wrap;
  color: #E5E5E5;
}}
.brand-footer {{
  margin-top: 1.2rem; padding-top: 0.6rem; border-top: 1px solid var(--kw-border);
  color: var(--kw-muted); font-size: 0.78rem; display:flex; justify-content:space-between;
}}
.tag {{ display:inline-block; padding: 2px 8px; border-radius: 999px;
  background: rgba(0,255,167,0.10); border: 1px solid var(--kw-primary);
  color: var(--kw-neon); font-size: 0.72rem; margin-left: 6px;}}
.cluster-row {{ background: var(--kw-surface2); border:1px solid var(--kw-border);
  border-left: 2px solid var(--kw-primary);
  border-radius: 6px; padding: 8px 10px; margin-bottom:6px;}}
.conf-HIGH    {{ color:#00FFA7; font-weight:700; }}
.conf-MED     {{ color:#F2C94C; font-weight:700; }}
.conf-LOW     {{ color:#FF8C42; font-weight:700; }}
code {{ color: #00FFA7 !important; background: #0E0E0E !important; }}
</style>
"""
st.markdown(KAMIWAZA_CSS, unsafe_allow_html=True)


# ─────────────────────────────────────────────────────────────────────────────
# Header
# ─────────────────────────────────────────────────────────────────────────────
hdr_l, hdr_r = st.columns([0.66, 0.34])
with hdr_l:
    st.markdown(
        "<h1 data-testid='app-title'>GHOST "
        "<span class='tag'>Agent #21 · LOGCOM RF Data Analysis</span></h1>",
        unsafe_allow_html=True,
    )
    st.markdown(
        "<div style='color:#BDBDBD;font-size:0.95rem;'>"
        "RF Pattern of Life Survey — pattern of life, heatmaps, target / "
        "location survey from Wi-Fi + Bluetooth scans. "
        "<i>AI Inside Your Security Boundary.</i></div>",
        unsafe_allow_html=True,
    )
with hdr_r:
    st.markdown(
        f"<div style='text-align:right;padding-top:6px;'>"
        f"<img src='{BRAND['logo_url']}' style='height:34px;opacity:0.95;'/></div>",
        unsafe_allow_html=True,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Data load (cached)
# ─────────────────────────────────────────────────────────────────────────────
@st.cache_data(show_spinner=False)
def load_rf() -> pd.DataFrame:
    real_path = os.getenv("REAL_DATA_PATH")
    if real_path:
        from data.load_real import load_real  # noqa: WPS433
        df = load_real()
    elif RF_CSV.exists():
        df = pd.read_csv(RF_CSV)
    else:
        # Auto-generate if missing (no LLM precompute, just data)
        os.environ["SKIP_PRECOMPUTE"] = "1"
        sys.path.insert(0, str(DATA_DIR))
        from generate import main as gen_main  # noqa: WPS433
        gen_main()
        df = pd.read_csv(RF_CSV)
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True).dt.tz_localize(None)
    df["hour"] = df["timestamp"].dt.hour
    return df


@st.cache_data(show_spinner=False)
def load_vendors() -> pd.DataFrame:
    if VENDOR_CSV.exists():
        return pd.read_csv(VENDOR_CSV)
    return pd.DataFrame(columns=["vendor", "oui_prefix"])


@st.cache_data(show_spinner=False)
def load_cached_briefs() -> dict:
    if CACHE_PATH.exists():
        try:
            return json.loads(CACHE_PATH.read_text())
        except Exception:  # noqa: BLE001
            return {}
    return {}


df = load_rf()
vendors = load_vendors()
cached_briefs = load_cached_briefs()


# ─────────────────────────────────────────────────────────────────────────────
# Sidebar — filters
# ─────────────────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("### Scan Filters")
    hr_min, hr_max = st.slider(
        "Time window (UTC hour)", 0, 23, (0, 23), step=1, key="hr_window",
    )
    sig_choice = st.radio(
        "Signal type",
        ["Both", "WiFi", "BT"],
        index=0, horizontal=True, key="sig_choice",
    )
    all_vendors = sorted(df["vendor"].unique().tolist())
    vendor_pick = st.multiselect(
        "MAC vendor",
        options=all_vendors,
        default=all_vendors,
        key="vendor_pick",
    )
    st.divider()
    st.markdown("### DBSCAN Parameters")
    eps_m = st.slider("eps (meters)", 30, 250, 90, step=10, key="eps_m")
    min_samples = st.slider("min_samples", 5, 80, 25, step=5, key="min_samples")
    st.divider()
    st.markdown("### Kamiwaza Stack")
    st.markdown(
        "- Inference Mesh (vLLM)\n"
        "- DDE — Distributed Data Engine\n"
        "- Model Gateway (Kamiwaza-deployed: any LLM)\n"
        "- ReBAC access control\n"
        "- IL5/IL6 ready · NIPR/SIPR/JWICS"
    )
    st.markdown(
        "<div style='color:#7FE5A1; font-size:0.78rem; margin-top:0.5rem;'>"
        "Set <code>KAMIWAZA_BASE_URL</code> → 100% on-prem. Zero code change.</div>",
        unsafe_allow_html=True,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Apply filters
# ─────────────────────────────────────────────────────────────────────────────
mask = (df["hour"] >= hr_min) & (df["hour"] <= hr_max)
if sig_choice != "Both":
    mask &= (df["signal_type"] == sig_choice)
if vendor_pick:
    mask &= df["vendor"].isin(vendor_pick)
fdf = df.loc[mask].copy()


# ─────────────────────────────────────────────────────────────────────────────
# DBSCAN clustering on (lat, lon, scaled_time)
# ─────────────────────────────────────────────────────────────────────────────
@st.cache_data(show_spinner=False)
def run_dbscan(fdf_signature: tuple, lats: np.ndarray, lons: np.ndarray,
                hours: np.ndarray, eps_m: int, min_samples: int) -> np.ndarray:
    if len(lats) < min_samples:
        return np.full(len(lats), -1, dtype=int)
    # Convert lat/lon to local meters for DBSCAN
    mean_lat = float(np.mean(lats))
    lat_m = (lats - mean_lat) * 111_320.0
    lon_m = (lons - float(np.mean(lons))) * (111_320.0 * np.cos(np.radians(mean_lat)))
    # Time scaled so 1 hour ~ eps/2 meters; this lets DBSCAN treat
    # spatiotemporal proximity coherently
    time_m = (hours - 12.0) * (eps_m * 0.6)
    X = np.column_stack([lat_m, lon_m, time_m])
    db = DBSCAN(eps=eps_m, min_samples=min_samples).fit(X)
    return db.labels_


# Cache key — use a hash-friendly signature
sig = (len(fdf), int(fdf["timestamp"].min().value) if len(fdf) else 0,
       int(fdf["timestamp"].max().value) if len(fdf) else 0,
       eps_m, min_samples, tuple(sorted(vendor_pick)), sig_choice, hr_min, hr_max)
labels = run_dbscan(sig, fdf["lat"].values, fdf["lon"].values, fdf["hour"].values,
                    eps_m, min_samples)
fdf["cluster"] = labels


# ─────────────────────────────────────────────────────────────────────────────
# Build cluster summaries
# ─────────────────────────────────────────────────────────────────────────────
def summarize_cluster(group: pd.DataFrame, cid: int) -> dict:
    lat_c = float(group["lat"].mean())
    lon_c = float(group["lon"].mean())
    span_lat_m = float((group["lat"].max() - group["lat"].min()) * 111_320.0)
    span_lon_m = float((group["lon"].max() - group["lon"].min())
                        * 111_320.0 * np.cos(np.radians(lat_c)))
    span_m = float(np.sqrt(span_lat_m**2 + span_lon_m**2))
    vendor_counts = group["vendor"].value_counts()
    top_vendor = str(vendor_counts.index[0]) if len(vendor_counts) else "Unknown"
    hours = group["hour"].values
    peak_hour = int(pd.Series(hours).mode().iloc[0]) if len(hours) else 12
    hours_active = int(group["hour"].nunique())
    wifi_share = float((group["signal_type"] == "WiFi").mean())
    return {
        "id": cid,
        "n_events": int(len(group)),
        "lat": lat_c, "lon": lon_c,
        "spatial_span_m": span_m,
        "hours_active": hours_active,
        "peak_hour": peak_hour,
        "top_vendor": top_vendor,
        "vendor_top3": vendor_counts.head(3).to_dict(),
        "wifi_share": wifi_share,
        "rssi_mean": float(group["rssi"].mean()),
        "rssi_min": int(group["rssi"].min()),
    }


cluster_ids = [c for c in sorted(fdf["cluster"].unique().tolist()) if c != -1]
summaries = [summarize_cluster(fdf[fdf["cluster"] == c], c) for c in cluster_ids]
n_noise = int((fdf["cluster"] == -1).sum())


# ─────────────────────────────────────────────────────────────────────────────
# KPI strip
# ─────────────────────────────────────────────────────────────────────────────
def metric_card(col, label, value, sub):
    col.markdown(
        f"<div class='metric-card'><div class='label'>{label}</div>"
        f"<div class='val'>{value}</div><div class='sub'>{sub}</div></div>",
        unsafe_allow_html=True,
    )


k1, k2, k3, k4, k5 = st.columns(5)
metric_card(k1, "RF Events", f"{len(fdf):,}", f"of {len(df):,} total")
metric_card(k2, "Unique MACs", f"{fdf['mac'].nunique():,}",
             f"vendors {fdf['vendor'].nunique()}")
wifi_n = int((fdf["signal_type"] == "WiFi").sum())
bt_n = int((fdf["signal_type"] == "BT").sum())
metric_card(k3, "WiFi / BT", f"{wifi_n:,} / {bt_n:,}", "split by signal type")
metric_card(k4, "Clusters", f"{len(cluster_ids)}",
             f"+{n_noise:,} noise · DBSCAN ε={eps_m}m")
metric_card(k5, "Scan window", f"{hr_min:02d}:00–{hr_max:02d}:59",
             "UTC · 2026-04-26")


# ─────────────────────────────────────────────────────────────────────────────
# Map + cluster panel
# ─────────────────────────────────────────────────────────────────────────────
left, right = st.columns([0.62, 0.38])

CLUSTER_COLORS = ["#00FFA7", "#0DCC8A", "#F2C94C", "#FF8C42", "#56CCF2",
                   "#BB6BD9", "#F28C28", "#7FE5A1", "#F2994A", "#FF4D4D"]

with left:
    st.markdown("#### Heatmap · scan-area density (Wi-Fi + BT, dark CartoDB)")
    if len(fdf):
        lat_c = float(fdf["lat"].mean())
        lon_c = float(fdf["lon"].mean())
    else:
        lat_c, lon_c = GATE_LAT, GATE_LON
    fmap = folium.Map(
        location=[lat_c, lon_c],
        zoom_start=15,
        tiles="CartoDB dark_matter",
        attr="CartoDB.DarkMatter",
        control_scale=True,
    )
    if len(fdf):
        # heat points — RSSI-weighted (higher RSSI = closer = brighter)
        heat_points = []
        for _, r in fdf.iterrows():
            w = max(0.05, 1.0 + (r["rssi"] + 95) / 60.0)  # ~0..1
            heat_points.append([r["lat"], r["lon"], float(min(1.0, w))])
        HeatMap(
            heat_points, radius=14, blur=18, min_opacity=0.30, max_zoom=18,
            gradient={0.2: "#065238", 0.4: "#00BB7A", 0.6: "#00FFA7",
                       0.85: "#F2C94C", 1.0: "#FF4D4D"},
        ).add_to(fmap)
        # cluster centroid markers
        for i, s in enumerate(summaries):
            color = CLUSTER_COLORS[i % len(CLUSTER_COLORS)]
            folium.CircleMarker(
                location=[s["lat"], s["lon"]],
                radius=8 + min(14, s["n_events"] / 60),
                color=color, weight=2, fill=True,
                fill_color=color, fill_opacity=0.55,
                popup=(f"<b>Cluster #{s['id']}</b><br>"
                       f"{s['n_events']} events · {s['hours_active']}h active<br>"
                       f"Top vendor: {s['top_vendor']}<br>"
                       f"Peak hour: {s['peak_hour']:02d}:00<br>"
                       f"WiFi share: {s['wifi_share']*100:.0f}%"),
                tooltip=f"Cluster #{s['id']}  ({s['n_events']} events)",
            ).add_to(fmap)
        # Pendleton main gate marker
        folium.Marker(
            location=[GATE_LAT, GATE_LON],
            tooltip="Camp Pendleton main gate (San Onofre)",
            icon=folium.DivIcon(html=(
                "<div style='color:#00FFA7;font-weight:700;font-size:11px;"
                "text-shadow:0 0 4px #000;'>★ GATE</div>"
            )),
        ).add_to(fmap)
    st_folium(fmap, width=None, height=420, returned_objects=[],
               key="ghost_map")

with right:
    st.markdown("#### Per-Cluster AI Classification")
    st.caption("`chat_json` · structured output · cluster_type / device / "
                "TOD / confidence")

    # init state
    if "cluster_classifications" not in st.session_state:
        st.session_state["cluster_classifications"] = {}
    cls_btn = st.button("Classify all clusters", type="primary",
                         key="classify_btn")
    if cls_btn:
        st.session_state["cluster_classifications"] = {}
        with st.spinner("Routing classifier through the Inference Mesh…"):
            for s in summaries:
                tag = classify_cluster(s, timeout=10)
                st.session_state["cluster_classifications"][s["id"]] = tag
    classifications = st.session_state["cluster_classifications"]

    if not summaries:
        st.markdown(
            "<div class='mis-panel' style='color:#7E7E7E;'>"
            "No clusters at current filters. Loosen the time window, "
            "lower min_samples, or include more vendors."
            "</div>",
            unsafe_allow_html=True,
        )
    else:
        for i, s in enumerate(summaries[:8]):
            color = CLUSTER_COLORS[i % len(CLUSTER_COLORS)]
            tag = classifications.get(s["id"], {})
            ctype = tag.get("cluster_type", "—")
            dtype = tag.get("inferred_device_type", "—")
            tod = tag.get("time_of_day_pattern", "—")
            conf = tag.get("confidence", "—")
            rationale = tag.get("rationale", "")
            st.markdown(
                f"<div class='cluster-row' style='border-left-color:{color};'>"
                f"<b style='color:{color};'>Cluster #{s['id']}</b> &nbsp;"
                f"<span style='color:#BDBDBD;font-size:0.82rem;'>"
                f"n={s['n_events']} · top {s['top_vendor']} · "
                f"peak {s['peak_hour']:02d}:00 · WiFi {s['wifi_share']*100:.0f}%</span>"
                f"<br>"
                f"<span style='font-size:0.84rem;'>type: <code>{ctype}</code> · "
                f"device: <code>{dtype}</code> · tod: <code>{tod}</code> · "
                f"<span class='conf-{conf}'>{conf}</span></span>"
                + (f"<br><span style='color:#7E7E7E;font-size:0.78rem;'>"
                    f"{rationale}</span>" if rationale else "")
                + "</div>",
                unsafe_allow_html=True,
            )


# ─────────────────────────────────────────────────────────────────────────────
# Activity histogram
# ─────────────────────────────────────────────────────────────────────────────
st.markdown("#### Activity by hour · stacked by signal type")
if len(fdf):
    hist = (fdf.groupby(["hour", "signal_type"]).size()
                .reset_index(name="events"))
    fig = px.bar(
        hist, x="hour", y="events", color="signal_type",
        color_discrete_map={"WiFi": "#00FFA7", "BT": "#0DCC8A"},
        labels={"hour": "Hour (UTC)", "events": "RF events"},
    )
    fig.update_layout(
        plot_bgcolor=BRAND["bg"], paper_bgcolor=BRAND["bg"],
        font_color="#E5E5E5", height=260,
        margin=dict(l=20, r=20, t=10, b=20),
        legend=dict(orientation="h", yanchor="bottom", y=1.0, xanchor="right", x=1.0),
        xaxis=dict(gridcolor=BRAND["border"], dtick=1),
        yaxis=dict(gridcolor=BRAND["border"]),
    )
    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
else:
    st.caption("No events at current filter selection.")


# ─────────────────────────────────────────────────────────────────────────────
# Hero AI panel — RF Pattern of Life Survey
# ─────────────────────────────────────────────────────────────────────────────
st.markdown("---")
st.markdown("#### RF Pattern of Life Survey · Hero AI brief")
st.caption("Cache-first. Pre-computed for two scenarios so the demo never blocks. "
            "Live regenerate uses the hero model (35-second watchdog, deterministic fallback).")

ai_l, ai_r = st.columns([0.62, 0.38])

scenario_choice = ai_l.radio(
    "Scenario",
    ["Full 24-hour scan · WiFi + BT", "Bluetooth only · 0900-1700 work hours"],
    index=0, horizontal=False, key="scenario",
)
scenario_key = ("full_24h_all_signals"
                if scenario_choice.startswith("Full")
                else "bt_only_workhours")

if "survey_text" not in st.session_state:
    # Load cached on first render
    st.session_state["survey_text"] = cached_briefs.get(
        scenario_key,
        "Cached brief not found. Click Regenerate to draft live."
    )
    st.session_state["survey_source"] = "cached"
    st.session_state["survey_scenario"] = scenario_key

# Reload cached text when scenario flipped
if st.session_state.get("survey_scenario") != scenario_key:
    st.session_state["survey_text"] = cached_briefs.get(
        scenario_key, "Cached brief not found."
    )
    st.session_state["survey_source"] = "cached"
    st.session_state["survey_scenario"] = scenario_key

regen_col1, regen_col2 = ai_l.columns([0.5, 0.5])
regen_btn = regen_col1.button("Regenerate (live · hero model)",
                                type="primary", key="regen_btn")
reload_btn = regen_col2.button("Reload cached", key="reload_btn")

if reload_btn:
    st.session_state["survey_text"] = cached_briefs.get(scenario_key, "")
    st.session_state["survey_source"] = "cached"

if regen_btn:
    # Build payload from current scan filters + clusters
    by_class: dict[str, int] = {}
    cls_payload = []
    for s in summaries:
        # Use classification if available, else fallback labels
        tag = st.session_state.get("cluster_classifications", {}).get(s["id"], {})
        ctype = tag.get("cluster_type", "device_dwell")
        dtype = tag.get("inferred_device_type", "phone")
        tod = tag.get("time_of_day_pattern", "office_hours")
        cls_payload.append({
            "id": s["id"],
            "anchor": f"{s['lat']:.4f},{s['lon']:.4f}",
            "n": s["n_events"],
            "type": ctype,
            "device_class": dtype,
            "tod": tod,
        })
        by_class[dtype] = by_class.get(dtype, 0) + s["n_events"]
    anomalies = []
    for s in summaries:
        if s["top_vendor"] in ("Unknown", "Espressif") and s["n_events"] >= 50:
            anomalies.append(
                f"Cluster {s['id']} — {s['n_events']} events from "
                f"{s['top_vendor']} OUI at ({s['lat']:.4f},{s['lon']:.4f}) "
                f"with peak hour {s['peak_hour']:02d}:00."
            )
    if not anomalies:
        anomalies.append("No anomalies above baseline at current filter "
                          "selection.")
    payload = {
        "site": "Camp Pendleton main gate (San Onofre) perimeter",
        "window_utc": f"2026-04-26 {hr_min:02d}:00Z to 2026-04-26 {hr_max:02d}:59Z",
        "totals": {
            "events": int(len(fdf)),
            "wifi": wifi_n, "bluetooth": bt_n,
            "unique_macs": int(fdf["mac"].nunique()),
        },
        "clusters": cls_payload,
        "anomalies": anomalies,
    }
    with st.spinner("Hero model drafting RF Pattern of Life Survey via Inference Mesh…"):
        text = generate_survey(payload, model="gpt-5.4", timeout=35)
    st.session_state["survey_text"] = text
    st.session_state["survey_source"] = "live"

with ai_l:
    src = st.session_state.get("survey_source", "cached")
    st.markdown(
        f"<div style='font-size:0.78rem;color:#7E7E7E;'>"
        f"Source: <span class='tag'>{src.upper()}</span></div>",
        unsafe_allow_html=True,
    )
    st.markdown(
        f"<div class='mis-panel' data-testid='survey-output'>"
        f"{st.session_state['survey_text']}</div>",
        unsafe_allow_html=True,
    )

with ai_r:
    st.markdown("**Cluster classifications · structured JSON**")
    cls_dict = st.session_state.get("cluster_classifications", {})
    if cls_dict:
        st.code(json.dumps(cls_dict, indent=2), language="json")
    else:
        st.markdown(
            "<div class='mis-panel' style='color:#7E7E7E;'>"
            "Click <b>Classify all clusters</b> above to populate this panel.<br><br>"
            "Each cluster gets a structured-output JSON tag from the AI engine: "
            "<code>cluster_type</code>, <code>inferred_device_type</code>, "
            "<code>confidence</code>, <code>time_of_day_pattern</code>, "
            "and a one-line rationale."
            "</div>",
            unsafe_allow_html=True,
        )
    st.markdown("**Top vendor mix in current scan**")
    if len(fdf):
        vc = (fdf["vendor"].value_counts().head(8).reset_index())
        vc.columns = ["vendor", "events"]
        st.dataframe(vc, hide_index=True, use_container_width=True, height=260)


# ─────────────────────────────────────────────────────────────────────────────
# Footer
# ─────────────────────────────────────────────────────────────────────────────
st.markdown(
    f"<div class='brand-footer'>"
    f"<span>GHOST · Powered by Kamiwaza · 5,000 synthetic Wi-Fi + BT events · "
    f"DBSCAN(ε={eps_m}m, min_samples={min_samples}) over (lat, lon, scaled_time)</span>"
    f"<span>Real dataset: <i>IEEE Real-world Commercial Wi-Fi & Bluetooth "
    f"RF Fingerprinting</i> (IEEE DataPort) · plug in via "
    f"<code>data/load_real.py</code></span>"
    f"</div>",
    unsafe_allow_html=True,
)
