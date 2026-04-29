"""PREDICT-MAINT — Closed-Loop Predictive Maintenance for the USMC LOGCOM
PdM-flavored use cases (Predictive Mx + Parts Demand Forecasting + Depot
Throughput Optimization + Inventory Control Management).

5-stage sensor-to-shelf chain in one Streamlit app on port 3040:
  Sensor (CWRU) -> Forecast (Holt-Winters) -> Auto-reorder (chat_json) ->
  Depot induction Gantt -> SHA-256 chained inventory ledger.

Run:
    streamlit run src/app.py --server.port 3040 --server.headless true \
        --server.runOnSave false --server.fileWatcherType none \
        --browser.gatherUsageStats false
"""
from __future__ import annotations

import io
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

APP_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = Path(__file__).resolve().parents[3]
for p in (str(REPO_ROOT), str(APP_ROOT)):
    if p not in sys.path:
        sys.path.insert(0, p)

from shared.kamiwaza_client import BRAND  # noqa: E402

from src.signal_proc import (  # noqa: E402
    characteristic_freqs, envelope_spectrum, hand_crafted_features,
    spectrogram_image,
)
from src.classifier import (  # noqa: E402
    CLASSES, estimate_rul, predict_one, severity_from_features, train_classifier,
)
from src.chain import run_chain, read_ledger, verify_ledger  # noqa: E402
from src.agent import generate_brief, get_cached_brief  # noqa: E402

DATA = APP_ROOT / "data"
CORPUS = DATA / "vibration_corpus.npz"
ASSETS_FILE = DATA / "assets.json"
NSN_CATALOG_FILE = DATA / "nsn_catalog.json"
DEPOT_FILE = DATA / "depot_capacity.json"
HISTORY_FILE = DATA / "maintenance_history.csv"
INVENTORY_FILE = DATA / "inventory.csv"

st.set_page_config(
    page_title="PREDICT-MAINT — Closed-Loop Predictive Maintenance",
    page_icon="◆",
    layout="wide",
    initial_sidebar_state="expanded",
)


# ---------------------------------------------------------------------------
# Theme
# ---------------------------------------------------------------------------
st.markdown(
    f"""
    <style>
      :root {{
        --bg: {BRAND['bg']};
        --surface: {BRAND['surface']};
        --surface_high: {BRAND['surface_high']};
        --border: {BRAND['border']};
        --primary: {BRAND['primary']};
        --primary_hover: {BRAND['primary_hover']};
        --neon: {BRAND['neon']};
        --muted: {BRAND['muted']};
        --text_dim: {BRAND['text_dim']};
      }}
      html, body, [data-testid="stAppViewContainer"], .stApp {{
        background-color: var(--bg) !important;
        color: #E5E5E5 !important;
      }}
      [data-testid="stHeader"] {{ background: transparent !important; }}
      [data-testid="stSidebar"] {{
        background-color: var(--surface) !important;
        border-right: 1px solid var(--border);
      }}
      .pm-hero {{
        padding: 16px 22px;
        background: linear-gradient(120deg, var(--surface), var(--bg) 55%, #0a1f15 100%);
        border: 1px solid var(--border);
        border-left: 4px solid var(--primary);
        border-radius: 8px;
        margin-bottom: 14px;
      }}
      .pm-hero h1 {{
        margin: 0; font-size: 28px;
        letter-spacing: 0.5px; color: var(--neon);
      }}
      .pm-hero .tag {{ color: var(--text_dim); font-size: 13px; margin-top: 4px; }}
      .pm-card {{
        background: var(--surface);
        border: 1px solid var(--border);
        border-radius: 6px;
        padding: 12px 16px;
        margin-bottom: 10px;
      }}
      .pm-card h3 {{
        margin: 0 0 8px 0; color: var(--primary);
        font-size: 12px; letter-spacing: 1px; text-transform: uppercase;
      }}
      .pm-pill {{
        display: inline-block; padding: 3px 10px; border-radius: 999px;
        font-size: 11px; font-weight: 600; letter-spacing: 0.7px;
        text-transform: uppercase; border: 1px solid var(--border);
      }}
      .pill-red    {{ background: #2a0d10; color: #ff6b6b; border-color: #ff6b6b40; }}
      .pill-amber  {{ background: #2b1d05; color: #ffb347; border-color: #ffb34740; }}
      .pill-yellow {{ background: #2a280a; color: #fff066; border-color: #fff06640; }}
      .pill-green  {{ background: #06281c; color: var(--neon); border-color: var(--primary); }}
      .pm-kv {{
        display: flex; justify-content: space-between;
        padding: 4px 0; border-bottom: 1px dashed var(--border); font-size: 13px;
      }}
      .pm-kv:last-child {{ border-bottom: none; }}
      .pm-kv .k {{ color: var(--text_dim); }}
      .pm-kv .v {{ color: #E5E5E5; font-weight: 600; }}
      .pm-trace {{
        background: #0b0f0d;
        border: 1px solid var(--border);
        border-left: 3px solid var(--primary);
        border-radius: 4px;
        padding: 8px 12px;
        font-family: 'SF Mono', 'Menlo', monospace;
        font-size: 11px;
        color: #cfd8dc;
        margin-bottom: 6px;
      }}
      .pm-trace .stage {{ color: var(--neon); font-weight: 700; }}
      .pm-trace .ok    {{ color: #00FFA7; }}
      .pm-rec {{
        background: linear-gradient(120deg, #06281c, var(--surface) 80%);
        border: 1px solid var(--primary);
        border-left: 4px solid var(--neon);
        border-radius: 6px;
        padding: 14px 18px;
      }}
      .pm-rec h2 {{ margin: 0; color: var(--neon); font-size: 16px; }}
      .stButton > button {{
        background: var(--primary) !important;
        color: #062018 !important;
        border: 0 !important;
        font-weight: 700 !important;
        padding: 8px 16px !important;
        letter-spacing: 0.5px;
      }}
      .stButton > button:hover {{ background: var(--primary_hover) !important; }}
      [data-testid="stMetricValue"] {{ color: var(--neon) !important; }}
      [data-testid="stMetricLabel"] {{
        color: var(--text_dim) !important; text-transform: uppercase;
        letter-spacing: 1px; font-size: 11px !important;
      }}
      .stTabs [data-baseweb="tab-list"] {{ gap: 4px; }}
      .stTabs [data-baseweb="tab"] {{
        background: var(--surface) !important;
        border: 1px solid var(--border) !important;
        border-radius: 4px !important;
        color: var(--text_dim) !important;
      }}
      .stTabs [aria-selected="true"] {{
        background: #06281c !important;
        color: var(--neon) !important;
        border-color: var(--primary) !important;
      }}
      .pm-footer {{
        margin-top: 24px; padding: 12px;
        text-align: center; color: var(--text_dim);
        border-top: 1px solid var(--border); font-size: 12px;
      }}
      .pm-watch-toggle {{
        background: #0b0f0d; padding: 8px 12px;
        border: 1px solid var(--border); border-radius: 4px;
        font-size: 12px; color: var(--text_dim);
      }}
    </style>
    """,
    unsafe_allow_html=True,
)


# ---------------------------------------------------------------------------
# Cached resources
# ---------------------------------------------------------------------------
@st.cache_data(show_spinner=False)
def load_assets() -> list[dict]:
    return json.loads(ASSETS_FILE.read_text())


@st.cache_data(show_spinner=False)
def load_catalog() -> list[dict]:
    return json.loads(NSN_CATALOG_FILE.read_text())


@st.cache_data(show_spinner=False)
def load_depots() -> list[dict]:
    return json.loads(DEPOT_FILE.read_text())


@st.cache_data(show_spinner=False)
def load_history() -> pd.DataFrame:
    return pd.read_csv(HISTORY_FILE)


@st.cache_data(show_spinner=False)
def load_inventory() -> pd.DataFrame:
    return pd.read_csv(INVENTORY_FILE)


@st.cache_data(show_spinner=False)
def load_corpus() -> dict:
    z = np.load(CORPUS, allow_pickle=False)
    return {
        "signals": z["signals"],
        "labels": z["labels"],
        "severity": z["severity"],
        "fs": int(z["fs"]),
    }


@st.cache_resource(show_spinner=False)
def get_classifier():
    return train_classifier(CORPUS)


def pick_signal_for_class(corpus: dict, target_class: str,
                          severity_hint: float | None = None):
    cls_idx = CLASSES.index(target_class)
    mask = corpus["labels"] == cls_idx
    idxs = np.where(mask)[0]
    if severity_hint is not None and target_class != "healthy":
        sevs = corpus["severity"][idxs]
        closest = idxs[int(np.argmin(np.abs(sevs - severity_hint)))]
        return corpus["signals"][closest], float(corpus["severity"][closest])
    rng = np.random.default_rng(1776)
    pick = int(rng.choice(idxs))
    return corpus["signals"][pick], float(corpus["severity"][pick])


# ---------------------------------------------------------------------------
# Plot helpers
# ---------------------------------------------------------------------------
def render_spectrogram(sig: np.ndarray, fs: int, asset_id: str):
    f, t, Sxx = spectrogram_image(sig, fs)
    fig, ax = plt.subplots(figsize=(7, 3.4), dpi=140)
    fig.patch.set_facecolor(BRAND["bg"])
    ax.set_facecolor(BRAND["surface"])
    pcm = ax.pcolormesh(t, f, Sxx, shading="gouraud", cmap="inferno")
    ax.set_ylim(0, 5500)
    ax.set_xlabel("Time (s)", color="#cfd8dc")
    ax.set_ylabel("Frequency (Hz)", color="#cfd8dc")
    ax.set_title(f"Drive-end accelerometer spectrogram — {asset_id}",
                 color=BRAND["neon"], pad=10)
    ax.tick_params(colors="#9aa6ad")
    for spine in ax.spines.values():
        spine.set_color(BRAND["border"])
    cf = characteristic_freqs()
    for label, freq, color in [
        ("BPFO", cf.bpfo, BRAND["neon"]),
        ("BPFI", cf.bpfi, "#62d4ff"),
        ("BSF", cf.bsf, "#ffb347"),
        ("FTF", cf.ftf, "#cfd8dc"),
    ]:
        ax.axhline(freq, color=color, linewidth=0.7, linestyle="--", alpha=0.6)
        ax.text(0.005, freq + 40, label, color=color, fontsize=8, fontweight="bold")
    fig.colorbar(pcm, ax=ax, pad=0.01).set_label("Power (dB)", color="#cfd8dc")
    fig.tight_layout()
    return fig


def render_timeseries(sig: np.ndarray, fs: int):
    t = np.arange(len(sig)) / fs
    fig, ax = plt.subplots(figsize=(7, 1.7), dpi=140)
    fig.patch.set_facecolor(BRAND["bg"])
    ax.set_facecolor(BRAND["surface"])
    ax.plot(t, sig, color=BRAND["neon"], linewidth=0.6)
    ax.set_xlabel("Time (s)", color="#cfd8dc", fontsize=9)
    ax.set_ylabel("Accel (g)", color="#cfd8dc", fontsize=9)
    ax.tick_params(colors="#9aa6ad", labelsize=8)
    for spine in ax.spines.values():
        spine.set_color(BRAND["border"])
    ax.set_title("Live drive-end vibration trace (1 s @ 12 kHz)",
                 color=BRAND["neon"], fontsize=10, pad=6)
    fig.tight_layout()
    return fig


def render_forecast_chart(forecast: dict, nsn: str):
    actual = forecast["actual"]
    fcast = forecast["forecast"]
    lo = forecast["lo"]
    hi = forecast["hi"]
    days_actual = list(range(-len(actual), 0))
    days_fcast = list(range(0, len(fcast)))

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=days_actual, y=actual, mode="lines", name="actual (90 d)",
        line=dict(color=BRAND["text_dim"], width=1.5),
    ))
    fig.add_trace(go.Scatter(
        x=days_fcast + days_fcast[::-1],
        y=hi + lo[::-1],
        fill="toself", fillcolor="rgba(0,255,167,0.10)",
        line=dict(color="rgba(0,0,0,0)"), hoverinfo="skip",
        showlegend=False, name="80% band",
    ))
    fig.add_trace(go.Scatter(
        x=days_fcast, y=fcast, mode="lines", name=f"forecast ({forecast['method']})",
        line=dict(color=BRAND["neon"], width=2.2),
    ))
    fig.update_layout(
        title=f"NSN {nsn} — RUL-shocked Holt-Winters forecast (30/60 d)",
        height=320,
        paper_bgcolor=BRAND["bg"], plot_bgcolor=BRAND["surface"],
        font=dict(color="#cfd8dc"),
        xaxis=dict(title="days from today", gridcolor=BRAND["border"]),
        yaxis=dict(title="qty consumed/day", gridcolor=BRAND["border"]),
        margin=dict(l=40, r=20, t=40, b=40),
        legend=dict(bgcolor=BRAND["surface_high"], bordercolor=BRAND["border"]),
    )
    return fig


def render_gantt(gantt: list[dict], depots: list[dict],
                 highlight_asset: str | None = None):
    if not gantt:
        return None
    df = pd.DataFrame(gantt)
    df["start_dt"] = pd.to_datetime(df["start"])
    df["end_dt"] = pd.to_datetime(df["end"])
    depot_lookup = {d["id"]: d["name"] for d in depots}
    df["depot_label"] = df["depot"].map(depot_lookup).fillna(df["depot"])
    df["color_kind"] = df.apply(
        lambda r: "NEW INDUCTION" if r.get("asset_id") == highlight_asset
        else ("REBUILD" if r.get("rebuild_not_buy") else "BUY-NEW"),
        axis=1,
    )

    fig = px.timeline(
        df, x_start="start_dt", x_end="end_dt", y="depot_label",
        color="color_kind", hover_name="asset_id",
        color_discrete_map={
            "NEW INDUCTION": BRAND["neon"],
            "REBUILD": BRAND["primary"],
            "BUY-NEW": "#ffb347",
        },
    )
    fig.update_yaxes(autorange="reversed")
    fig.update_layout(
        title="Depot Induction Gantt — MCLB Albany / Barstow / Blount Island",
        height=300,
        paper_bgcolor=BRAND["bg"], plot_bgcolor=BRAND["surface"],
        font=dict(color="#cfd8dc"),
        xaxis=dict(gridcolor=BRAND["border"]),
        yaxis=dict(gridcolor=BRAND["border"]),
        margin=dict(l=40, r=20, t=40, b=40),
        legend=dict(bgcolor=BRAND["surface_high"], bordercolor=BRAND["border"]),
    )
    return fig


# ---------------------------------------------------------------------------
# Header
# ---------------------------------------------------------------------------
st.markdown(
    """
    <div class="pm-hero">
      <h1>PREDICT-MAINT</h1>
      <div class="tag">
        Closed-Loop Predictive Maintenance &nbsp;·&nbsp;
        Sensor → Forecast → Auto-Reorder → Depot Induction → SHA-256 Ledger
        &nbsp;·&nbsp; LOGCOM AI Forum Hackathon 2026
      </div>
    </div>
    """,
    unsafe_allow_html=True,
)


# ---------------------------------------------------------------------------
# Sidebar — asset roster + watchstander toggle + KAMIWAZA env beat
# ---------------------------------------------------------------------------
assets = load_assets()
catalog = load_catalog()
depots = load_depots()
history = load_history()
inventory = load_inventory()

with st.sidebar:
    st.markdown("### Test Asset Roster")
    st.caption("Pick the asset whose telemetry crossed amber.")
    labels = [
        f"{a['asset_id']} — {a['type'].split()[0]}" for a in assets
    ]
    sel = st.radio("Asset", labels, label_visibility="collapsed", index=0)
    sel_idx = labels.index(sel)
    asset = assets[sel_idx]

    st.markdown("---")
    st.markdown("### Asset Card")
    st.markdown(
        f"""
        <div class="pm-card">
          <div class="pm-kv"><span class="k">Type</span><span class="v">{asset['type']}</span></div>
          <div class="pm-kv"><span class="k">Unit</span><span class="v">{asset['unit']}</span></div>
          <div class="pm-kv"><span class="k">Hub</span><span class="v">{asset['hub_position']}</span></div>
          <div class="pm-kv"><span class="k">Op Hours</span><span class="v">{asset['operating_hours']:,}</span></div>
          <div class="pm-kv"><span class="k">Since Overhaul</span><span class="v">{asset['since_last_overhaul_hr']} hr</span></div>
          <div class="pm-kv"><span class="k">Replacement NSN</span><span class="v">{asset['nsn']}</span></div>
          <div class="pm-kv"><span class="k">Primary Depot</span><span class="v">{asset['depot']}</span></div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown("---")
    run_btn = st.button("RUN 5-STAGE CHAIN", use_container_width=True)
    hero_btn = st.button("Regenerate brief (hero, live)",
                         use_container_width=True,
                         help="One-shot live call to the hero model. 35s timeout, deterministic fallback.")

    st.markdown("---")
    st.markdown("### Watchstander view")
    watch_view = st.radio(
        "Watchstander view",
        ["E-5 Maintenance Chief", "O-3 Commander"],
        label_visibility="collapsed",
        horizontal=False,
        index=0,
    )

    st.markdown("---")
    st.markdown("### Deployment Mode")
    st.markdown(
        """
        <div class="pm-trace">
        <span class="stage">$ env | grep KAMI</span><br/>
        # Today: cloud fallback; Kamiwaza on-prem when BASE_URL set<br/>
        KAMIWAZA_BASE_URL=&lt;unset&gt;<br/><br/>
        # Tomorrow (one env-var swap):<br/>
        export KAMIWAZA_BASE_URL=<br/>
        &nbsp;&nbsp;https://kamiwaza.local/api/v1<br/>
        # 100% data containment. IL5/IL6 ready.
        </div>
        """,
        unsafe_allow_html=True,
    )


# ---------------------------------------------------------------------------
# Top metrics — coverage of the 4 use cases + 5 datasets
# ---------------------------------------------------------------------------
fs = 12_000
clf, clf_meta = get_classifier()
corpus = load_corpus()

m1, m2, m3, m4, m5 = st.columns(5)
m1.metric("Classifier acc",  f"{clf_meta['test_acc']*100:.1f}%",
          help="Held-out accuracy on CWRU 4-class fault corpus.")
m2.metric("NSN catalog",  f"{len(catalog)}", help="FSC-coherent Class IX NSNs.")
m3.metric("Work orders",  f"{len(history):,}",
          help="90 days, GCSS-MC stand-in.")
m4.metric("Inventory items",  f"{len(inventory):,}",
          help="ICM workbook stand-in.")
m5.metric("Depots wired",  f"{len(depots)}",
          help="MCLB Albany / Barstow / Blount Island Command")


# ---------------------------------------------------------------------------
# Pre-stage cards keyed to watchstander view
# ---------------------------------------------------------------------------
st.markdown("---")
st.markdown("### Pre-stage situational picture")

ps_l, ps_r = st.columns([0.5, 0.5])
if watch_view.startswith("E-5"):
    with ps_l:
        st.markdown(
            f"""
            <div class="pm-card" style="border-left:3px solid {BRAND['neon']};">
              <h3>E-5 Maintenance Chief View</h3>
              <div style="font-size: 13px; color: #cfd8dc;">
                <b>Fault on the line:</b> {asset['hub_position']} hub, asset
                {asset['asset_id']}. Vibration trace crossed amber threshold during yard test.
                Suspected <b>{asset['current_class'].replace('_', ' ').upper()}</b>.
                <br/><br/>
                <b>What I need next:</b> bearing NSN {asset['nsn']} pulled from MCLB Albany;
                yard space booked at {asset['depot']}; PMCS-Q closeout cleared.
              </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
else:
    with ps_l:
        st.markdown(
            f"""
            <div class="pm-card" style="border-left:3px solid {BRAND['neon']};">
              <h3>O-3 Commander View</h3>
              <div style="font-size: 13px; color: #cfd8dc;">
                <b>Mission frame:</b> the Marine reading the failure 30 days late is the
                Marine who loses the truck mid-mission. PREDICT-MAINT closes the loop
                before that gap opens.
                <br/><br/>
                <b>What I need:</b> a single brief, signed by hash, that says <i>induct now / monitor / reorder</i>
                — with the dollar shortfall and the named bottleneck.
              </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

with ps_r:
    cov_inventory = inventory[inventory["nsn"] == asset["nsn"]]
    on_hand_total = int(cov_inventory["qty_on_hand"].sum())
    on_hand_alb = int(cov_inventory[cov_inventory["location_id"].str.contains("ALB", na=False)]["qty_on_hand"].sum())
    on_hand_bar = int(cov_inventory[cov_inventory["location_id"].str.contains("BAR", na=False)]["qty_on_hand"].sum())
    on_hand_bic = int(cov_inventory[cov_inventory["location_id"].str.contains("BIC", na=False)]["qty_on_hand"].sum())
    st.markdown(
        f"""
        <div class="pm-card" style="border-left:3px solid {BRAND['primary']};">
          <h3>NSN {asset['nsn']} — Pre-Stage Stock</h3>
          <div class="pm-kv"><span class="k">Part</span><span class="v">{asset['part_name']}</span></div>
          <div class="pm-kv"><span class="k">MCLB Albany (ALB)</span><span class="v">{on_hand_alb}</span></div>
          <div class="pm-kv"><span class="k">MCLB Barstow (BAR)</span><span class="v">{on_hand_bar}</span></div>
          <div class="pm-kv"><span class="k">Blount Island (BIC)</span><span class="v">{on_hand_bic}</span></div>
          <div class="pm-kv"><span class="k">Total on hand</span><span class="v" style="color: {BRAND['neon']};">{on_hand_total}</span></div>
        </div>
        """,
        unsafe_allow_html=True,
    )


# ---------------------------------------------------------------------------
# Sensor stage — render the trace + spectrogram
# ---------------------------------------------------------------------------
sig, sev = pick_signal_for_class(
    corpus, asset["current_class"],
    severity_hint=asset["current_severity"] if asset["current_class"] != "healthy" else None,
)
pred = predict_one(clf, sig, fs)
feats = hand_crafted_features(sig, fs)
sev_est = severity_from_features(feats)
rul = estimate_rul(pred["class"], pred["confidence"], sev_est, asset["operating_hours"])


# ---------------------------------------------------------------------------
# Run the 5-stage chain (auto on first load, also on button)
# ---------------------------------------------------------------------------
if "chain_for" not in st.session_state:
    st.session_state["chain_for"] = None
if "chain_trace" not in st.session_state:
    st.session_state["chain_trace"] = None
if "brief" not in st.session_state:
    st.session_state["brief"] = None

needs_run = run_btn or st.session_state["chain_for"] != asset["asset_id"]
if needs_run:
    with st.spinner("Firing 5-stage closed-loop chain…"):
        trace = run_chain(
            asset=asset, classifier_result=pred, rul_result=rul,
            history_df=history, inventory_df=inventory,
            catalog=catalog, depots=depots,
        )
    st.session_state["chain_trace"] = trace
    st.session_state["chain_for"] = asset["asset_id"]
    # match scenario for cached brief
    scenario_map = {
        "MTVR-2491": "nominal",
        "AAV-7A1-3318": "surge",
        "MV-22B-167902": "parts_constrained",
    }
    sid = scenario_map.get(asset["asset_id"])
    chain_payload = {**trace.ledger_row}
    brief = generate_brief(
        asset=asset, chain_payload=chain_payload,
        scenario_id=sid, use_cache=True, hero_mode=False,
    )
    st.session_state["brief"] = brief

if hero_btn and st.session_state["chain_trace"]:
    with st.spinner("Hero model composing brief… (35s wall-clock timeout, deterministic fallback)"):
        chain_payload = {**st.session_state["chain_trace"].ledger_row}
        brief = generate_brief(
            asset=asset, chain_payload=chain_payload,
            use_cache=False, hero_mode=True,
        )
        st.session_state["brief"] = brief

trace = st.session_state["chain_trace"]
brief_obj = st.session_state["brief"]


# ---------------------------------------------------------------------------
# Live trace sidebar (shown as a row across the top of the chain)
# ---------------------------------------------------------------------------
st.markdown("---")
trace_l, trace_r = st.columns([0.78, 0.22])
with trace_l:
    st.markdown("### Sensor → Shelf — live chain trace")
with trace_r:
    chain_ok = verify_ledger()
    st.markdown(
        f"""
        <div style="text-align:right;">
          <span class="pm-pill {'pill-green' if chain_ok else 'pill-red'}">
            ledger {'INTACT' if chain_ok else 'TAMPERED'}
          </span>
        </div>
        """,
        unsafe_allow_html=True,
    )

if trace:
    timings = trace.stage_timings_ms
    stages = [
        ("(1) Sensor",       f"{trace.sensor['class']} @ RUL {trace.sensor['rul_hours']} hr",
         timings.get("stage1_sensor_ms", 0.0)),
        ("(2) Forecast",     f"30-d proj {trace.forecast['demand_30d']:.0f} ea (spike {trace.forecast['spike_ratio']:.1f}x)",
         timings.get("stage2_forecast_ms", 0.0)),
        ("(3) Auto-reorder", f"shortfall {trace.reorder.shortfall} ea, recommend {trace.reorder.recommended_reorder_qty} ea",
         timings.get("stage3_reorder_ms", 0.0)),
        ("(4) Induction",    f"{trace.induction.depot_name} bay {trace.induction.bay} ({trace.induction.start})",
         timings.get("stage4_induction_ms", 0.0)),
        ("(5) Ledger",       f"hash {trace.ledger_row['hash'][:16]}…",
         timings.get("stage5_ledger_ms", 0.0)),
    ]
    cols = st.columns(5)
    for col, (name, summary, ms) in zip(cols, stages):
        col.markdown(
            f"""
            <div class="pm-trace">
              <span class="stage">{name}</span>
              <span class="ok"> ✓</span> &nbsp;<span style="color: var(--text_dim);">{ms:.1f} ms</span><br/>
              {summary}
            </div>
            """,
            unsafe_allow_html=True,
        )


# ---------------------------------------------------------------------------
# Stage 1: sensor visualisations
# ---------------------------------------------------------------------------
st.markdown("---")
st.markdown("### Stage 1 — Sensor (CWRU drive-end accelerometer)")

s_l, s_r = st.columns([0.62, 0.38])
with s_l:
    st.pyplot(render_timeseries(sig, fs), use_container_width=True)
    st.pyplot(render_spectrogram(sig, fs, asset["asset_id"]),
              use_container_width=True)

with s_r:
    cls_color = {
        "healthy": "pill-green",
        "outer_race": "pill-red",
        "inner_race": "pill-red",
        "ball": "pill-amber",
    }.get(pred["class"], "pill-amber")
    cls_label = pred["class"].replace("_", " ").upper()
    prob_rows = "".join(
        f'<div class="pm-kv"><span class="k">{k.replace("_"," ")}</span>'
        f'<span class="v">{v*100:.1f}%</span></div>'
        for k, v in pred["probabilities"].items()
    )
    st.markdown(
        f"""
        <div class="pm-card">
          <h3>RandomForest classifier</h3>
          <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:10px;">
            <span class="pm-pill {cls_color}">{cls_label}</span>
            <span style="color: var(--neon); font-size: 22px; font-weight: 700;">{pred['confidence']*100:.0f}%</span>
          </div>
          {prob_rows}
        </div>
        """,
        unsafe_allow_html=True,
    )

    rul_pill = {
        "induct_now": ("pill-red", "INDUCT NOW"),
        "monitor_closely": ("pill-amber", "MONITOR CLOSELY"),
        "monitor_routine": ("pill-yellow", "MONITOR — ROUTINE"),
        "safe_to_operate": ("pill-green", "SAFE TO OPERATE"),
    }.get(rul["recommendation"], ("pill-amber", "MONITOR"))
    st.markdown(
        f"""
        <div class="pm-card">
          <h3>NASA Pred Mx — RUL</h3>
          <div class="pm-kv"><span class="k">Remaining useful life</span>
            <span class="v" style="color: var(--neon); font-size: 18px;">{rul['rul_hours']:,} hr</span></div>
          <div class="pm-kv"><span class="k">Severity (model)</span>
            <span class="v">{sev_est:.2f}</span></div>
          <div class="pm-kv"><span class="k">Rule call</span>
            <span class="pm-pill {rul_pill[0]}">{rul_pill[1]}</span></div>
        </div>
        """,
        unsafe_allow_html=True,
    )


# ---------------------------------------------------------------------------
# Stage 2: forecast spike
# ---------------------------------------------------------------------------
st.markdown("---")
st.markdown("### Stage 2 — Demand-spike forecast (NASA Pred Mx + Azure PdM patterns)")
if trace:
    f_l, f_r = st.columns([0.7, 0.3])
    with f_l:
        st.plotly_chart(render_forecast_chart(trace.forecast, asset["nsn"]),
                        use_container_width=True)
    with f_r:
        st.markdown(
            f"""
            <div class="pm-card">
              <h3>30/60 d projection</h3>
              <div class="pm-kv"><span class="k">Trailing 30 d (actual)</span>
                <span class="v">{trace.forecast['actual_30d']:.0f} ea</span></div>
              <div class="pm-kv"><span class="k">Next 30 d (projected)</span>
                <span class="v" style="color: var(--neon);">{trace.forecast['demand_30d']:.0f} ea</span></div>
              <div class="pm-kv"><span class="k">Next 60 d (projected)</span>
                <span class="v">{trace.forecast['demand_60d']:.0f} ea</span></div>
              <div class="pm-kv"><span class="k">Spike ratio</span>
                <span class="v" style="color: #ffb347;">{trace.forecast['spike_ratio']:.2f}×</span></div>
              <div class="pm-kv"><span class="k">Method</span>
                <span class="v">{trace.forecast['method']}</span></div>
            </div>
            """,
            unsafe_allow_html=True,
        )


# ---------------------------------------------------------------------------
# Stage 3: auto-reorder card (chat_json shape)
# ---------------------------------------------------------------------------
st.markdown("---")
st.markdown("### Stage 3 — Auto-reorder card (validated against GCSS-MC + ICM)")
if trace:
    r = trace.reorder
    rec_pill = "pill-red" if r.shortfall > 0 else "pill-green"
    st.markdown(
        f"""
        <div class="pm-card" style="border-left:3px solid {BRAND['neon']};">
          <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:8px;">
            <span class="pm-pill {rec_pill}">REORDER {'REQUIRED' if r.shortfall > 0 else 'NOT NEEDED'}</span>
            <span style="color: var(--text_dim); font-size: 11px;">structured JSON · chat_json shape</span>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    rcol1, rcol2 = st.columns([0.55, 0.45])
    with rcol1:
        reorder_json = {
            "nsn": r.nsn,
            "on_hand": r.on_hand,
            "projected_demand_30d": r.projected_demand_30d,
            "shortfall": r.shortfall,
            "recommended_reorder_qty": r.recommended_reorder_qty,
            "source_depot": r.source_depot,
            "lead_time_days": r.lead_time_days,
            "action_due_by": r.action_due_by,
            "rebuild_not_buy": r.rebuild_not_buy,
        }
        st.code(json.dumps(reorder_json, indent=2), language="json")
    with rcol2:
        st.markdown(
            f"""
            <div class="pm-card">
              <div class="pm-kv"><span class="k">NSN</span><span class="v">{r.nsn}</span></div>
              <div class="pm-kv"><span class="k">On hand (ALB)</span><span class="v">{r.on_hand}</span></div>
              <div class="pm-kv"><span class="k">Projected demand 30 d</span><span class="v">{r.projected_demand_30d}</span></div>
              <div class="pm-kv"><span class="k">Shortfall</span><span class="v" style="color: #ff6b6b;">{r.shortfall}</span></div>
              <div class="pm-kv"><span class="k">Recommended qty</span><span class="v" style="color: var(--neon);">{r.recommended_reorder_qty}</span></div>
              <div class="pm-kv"><span class="k">Lead time</span><span class="v">{r.lead_time_days} d</span></div>
              <div class="pm-kv"><span class="k">Action due by</span><span class="v">{r.action_due_by}</span></div>
              <div class="pm-kv"><span class="k">Rebuild-not-buy</span><span class="v">{'YES' if r.rebuild_not_buy else 'NO'}</span></div>
            </div>
            """,
            unsafe_allow_html=True,
        )


# ---------------------------------------------------------------------------
# Stage 4: depot induction Gantt
# ---------------------------------------------------------------------------
st.markdown("---")
st.markdown("### Stage 4 — Depot induction reslot (greedy scheduler)")
if trace:
    fig_g = render_gantt(trace.gantt, depots, highlight_asset=asset["asset_id"])
    if fig_g is not None:
        st.plotly_chart(fig_g, use_container_width=True)
    st.caption(
        f"`{asset['asset_id']}` reslotted at **{trace.induction.depot_name}** "
        f"bay {trace.induction.bay}, {trace.induction.start} → "
        f"{trace.induction.end}  ·  rebuild_not_buy = "
        f"{trace.induction.rebuild_not_buy}"
    )


# ---------------------------------------------------------------------------
# Stage 5: SHA-256 chained ledger
# ---------------------------------------------------------------------------
st.markdown("---")
st.markdown("### Stage 5 — SHA-256 chained inventory ledger (append-only)")
ledger_rows = read_ledger(tail=10)
if ledger_rows:
    show_cols = ["ts", "kind", "actor", "asset_id", "nsn",
                 "shortfall", "recommended_reorder_qty",
                 "induction_depot", "hash"]
    df_l = pd.DataFrame(ledger_rows)
    for c in show_cols:
        if c not in df_l.columns:
            df_l[c] = ""
    df_l["hash"] = df_l["hash"].astype(str).str.slice(0, 16) + "…"
    st.dataframe(df_l[show_cols], use_container_width=True, hide_index=True,
                 height=240)
else:
    st.info("Ledger is empty; trigger the chain.")


# ---------------------------------------------------------------------------
# Closed-Loop Maintenance Action Brief (the hero moment)
# ---------------------------------------------------------------------------
st.markdown("---")
st.markdown("### Closed-Loop Maintenance Action Brief")
src_label_map = {
    "cache":    '<span class="pm-pill pill-green">CACHED</span>',
    "hero":     '<span class="pm-pill pill-green">HERO LIVE</span>',
    "live":     '<span class="pm-pill pill-green">LIVE</span>',
    "fallback": '<span class="pm-pill pill-amber">DETERMINISTIC FALLBACK</span>',
}
if brief_obj:
    src_pill = src_label_map.get(brief_obj["source"], "")
    st.markdown(
        f"""
        <div class="pm-rec">
          <div style="display:flex; justify-content:space-between; align-items:center;">
            <h2>Asset {asset['asset_id']} — {asset['type'].split()[0]}</h2>
            <div>{src_pill}
              <span class="pm-pill" style="margin-left:6px;">{brief_obj['model_label']}</span>
            </div>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.markdown(brief_obj["brief"])


# ---------------------------------------------------------------------------
# Footer
# ---------------------------------------------------------------------------
st.markdown(
    f"""
    <div class="pm-footer">
      Real datasets cited: <strong>CWRU Bearing Fault</strong> ·
      <strong>NASA Pred Mx (CMAPSS)</strong> ·
      <strong>Predictive Mx (Azure)</strong> ·
      <strong>GCSS-MC Supply &amp; Maintenance</strong> ·
      <strong>Inventory Control Management workbook</strong>.
      Synthetic stand-ins seeded with random.Random(1776) — see
      <code>data/load_real.py</code> for the 5 swap recipes.
      <br/>
      <strong style="color: {BRAND['primary']};">Powered by Kamiwaza.</strong>
      &nbsp;·&nbsp; Orchestration Without Migration. Execution Without Compromise.
    </div>
    """,
    unsafe_allow_html=True,
)
