# FORGE — predictive bearing failure
# Part of the MDM 2026 Hackathon Templates (https://github.com/12fn/MDMhackathon-repos)
# MIT licensed. Built on GAI (Government Acquisitions, Inc.) + Kamiwaza (https://www.kamiwaza.ai/).
"""FORGE — Forecasted Onset of Rotational-Gear Endpoint.

Streamlit operator console for predictive bearing-failure on USMC ground fleet.
Run:
    streamlit run src/app.py --server.port 3002
"""
from __future__ import annotations

import io
import json
import sys
import time
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import streamlit as st

ROOT = Path(__file__).resolve().parent.parent
REPO_ROOT = ROOT.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.signal_proc import (  # noqa: E402
    characteristic_freqs,
    envelope_spectrum,
    hand_crafted_features,
    spectrogram_image,
)
from src.classifier import (  # noqa: E402
    CLASSES,
    estimate_rul,
    predict_one,
    severity_from_features,
    train_classifier,
)
from src.agent import commander_recommendation, lookup_part_availability  # noqa: E402
from shared.kamiwaza_client import BRAND  # noqa: E402

DATA = ROOT / "data"
CORPUS = DATA / "vibration_corpus.npz"
LOG = DATA / "maintenance_log.json"
VEHICLES_FILE = DATA / "vehicles.json"

st.set_page_config(
    page_title="FORGE — Predictive Bearing-Failure for USMC Ground Fleet",
    page_icon="⚙",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---- Kamiwaza dark theme ----
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
      [data-testid="stSidebar"] {{ background-color: var(--surface) !important; border-right: 1px solid var(--border); }}
      .forge-hero {{
        padding: 18px 24px;
        background: linear-gradient(120deg, var(--surface), var(--bg) 55%, #0a1f15 100%);
        border: 1px solid var(--border);
        border-left: 4px solid var(--primary);
        border-radius: 8px;
        margin-bottom: 18px;
      }}
      .forge-hero h1 {{
        margin: 0 0 4px 0;
        font-size: 32px;
        letter-spacing: 0.5px;
        color: var(--neon);
      }}
      .forge-hero .tagline {{ color: var(--text_dim); font-size: 14px; }}
      .forge-card {{
        background: var(--surface);
        border: 1px solid var(--border);
        border-radius: 6px;
        padding: 14px 18px;
        margin-bottom: 10px;
      }}
      .forge-card h3 {{ margin: 0 0 8px 0; color: var(--primary); font-size: 14px; letter-spacing: 1px; text-transform: uppercase; }}
      .forge-pill {{
        display: inline-block; padding: 3px 10px; border-radius: 999px;
        font-size: 11px; font-weight: 600; letter-spacing: 0.7px; text-transform: uppercase;
        border: 1px solid var(--border);
      }}
      .pill-red    {{ background: #2a0d10; color: #ff6b6b; border-color: #ff6b6b40; }}
      .pill-amber  {{ background: #2b1d05; color: #ffb347; border-color: #ffb34740; }}
      .pill-yellow {{ background: #2a280a; color: #fff066; border-color: #fff06640; }}
      .pill-green  {{ background: #06281c; color: var(--neon); border-color: var(--primary); }}
      .forge-kv {{ display: flex; justify-content: space-between; padding: 4px 0; border-bottom: 1px dashed var(--border); font-size: 13px; }}
      .forge-kv:last-child {{ border-bottom: none; }}
      .forge-kv .k {{ color: var(--text_dim); }}
      .forge-kv .v {{ color: #E5E5E5; font-weight: 600; }}
      .forge-rec {{
        background: linear-gradient(120deg, #06281c, var(--surface) 80%);
        border: 1px solid var(--primary);
        border-left: 4px solid var(--neon);
        border-radius: 6px;
        padding: 16px 20px;
        margin-top: 8px;
      }}
      .forge-rec h2 {{ margin: 0 0 4px 0; color: var(--neon); font-size: 18px; }}
      .forge-tool {{
        background: #0b0f0d;
        border: 1px solid var(--border);
        border-left: 3px solid var(--primary);
        border-radius: 4px;
        padding: 10px 14px;
        font-family: 'SF Mono', 'Menlo', monospace;
        font-size: 12px;
        color: #cfd8dc;
        margin-top: 6px;
      }}
      .forge-tool .toolname {{ color: var(--neon); }}
      .forge-footer {{
        margin-top: 32px; padding: 12px;
        text-align: center; color: var(--text_dim);
        border-top: 1px solid var(--border); font-size: 12px;
      }}
      .stButton > button {{
        background: var(--primary) !important;
        color: #062018 !important;
        border: 0 !important;
        font-weight: 700 !important;
        padding: 8px 18px !important;
        letter-spacing: 0.5px;
      }}
      .stButton > button:hover {{ background: var(--primary_hover) !important; }}
      [data-testid="stMetricValue"] {{ color: var(--neon) !important; }}
      [data-testid="stMetricLabel"] {{ color: var(--text_dim) !important; text-transform: uppercase; letter-spacing: 1px; }}
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
    </style>
    """,
    unsafe_allow_html=True,
)


# ---- Cached resources ----

@st.cache_data
def load_vehicles() -> list[dict]:
    return json.loads(VEHICLES_FILE.read_text())


@st.cache_data
def load_log() -> dict:
    return json.loads(LOG.read_text())


@st.cache_data
def load_corpus():
    z = np.load(CORPUS, allow_pickle=False)
    return {
        "signals": z["signals"],
        "labels": z["labels"],
        "severity": z["severity"],
        "fs": int(z["fs"]),
    }


@st.cache_resource
def get_classifier():
    clf, meta = train_classifier(CORPUS)
    return clf, meta


def pick_signal_for_class(corpus: dict, target_class: str, severity_hint: float | None = None) -> tuple[np.ndarray, float]:
    cls_idx = CLASSES.index(target_class)
    mask = corpus["labels"] == cls_idx
    idxs = np.where(mask)[0]
    if severity_hint is not None and target_class != "healthy":
        sevs = corpus["severity"][idxs]
        # pick the sample whose severity is closest to the hint
        closest = idxs[int(np.argmin(np.abs(sevs - severity_hint)))]
        return corpus["signals"][closest], float(corpus["severity"][closest])
    rng = np.random.default_rng()
    pick = int(rng.choice(idxs))
    return corpus["signals"][pick], float(corpus["severity"][pick])


def render_spectrogram_png(sig: np.ndarray, fs: int, *, vehicle_id: str) -> tuple[bytes, plt.Figure]:
    f, t, Sxx = spectrogram_image(sig, fs)
    fig, ax = plt.subplots(figsize=(8, 4.2), dpi=140)
    fig.patch.set_facecolor(BRAND["bg"])
    ax.set_facecolor(BRAND["surface"])
    pcm = ax.pcolormesh(t, f, Sxx, shading="gouraud", cmap="inferno")
    ax.set_ylim(0, 5500)
    ax.set_xlabel("Time (s)", color="#cfd8dc")
    ax.set_ylabel("Frequency (Hz)", color="#cfd8dc")
    ax.set_title(f"Drive-end accelerometer spectrogram — {vehicle_id}", color=BRAND["neon"], pad=10)
    ax.tick_params(colors="#9aa6ad")
    for spine in ax.spines.values():
        spine.set_color(BRAND["border"])
    cf = characteristic_freqs()
    for label, freq, color in [
        ("BPFO", cf.bpfo, BRAND["neon"]),
        ("BPFI", cf.bpfi, "#62d4ff"),
        ("BSF", cf.bsf, "#ffb347"),
    ]:
        ax.axhline(freq, color=color, linewidth=0.7, linestyle="--", alpha=0.55)
        ax.text(0.005, freq + 40, label, color=color, fontsize=8, fontweight="bold")
    cbar = fig.colorbar(pcm, ax=ax, pad=0.01)
    cbar.set_label("Power (dB)", color="#cfd8dc")
    cbar.ax.yaxis.set_tick_params(color="#9aa6ad")
    plt.setp(plt.getp(cbar.ax.axes, "yticklabels"), color="#9aa6ad")
    fig.tight_layout()
    buf = io.BytesIO()
    fig.savefig(buf, format="png", facecolor=fig.get_facecolor())
    buf.seek(0)
    return buf.getvalue(), fig


def render_timeseries(sig: np.ndarray, fs: int) -> plt.Figure:
    t = np.arange(len(sig)) / fs
    fig, ax = plt.subplots(figsize=(8, 2.2), dpi=140)
    fig.patch.set_facecolor(BRAND["bg"])
    ax.set_facecolor(BRAND["surface"])
    ax.plot(t, sig, color=BRAND["neon"], linewidth=0.6)
    ax.set_xlabel("Time (s)", color="#cfd8dc", fontsize=9)
    ax.set_ylabel("Accel (g)", color="#cfd8dc", fontsize=9)
    ax.tick_params(colors="#9aa6ad", labelsize=8)
    for spine in ax.spines.values():
        spine.set_color(BRAND["border"])
    ax.set_title("Live drive-end vibration trace (1 s @ 12 kHz)", color=BRAND["neon"], fontsize=10, pad=8)
    fig.tight_layout()
    return fig


def render_envelope(sig: np.ndarray, fs: int) -> plt.Figure:
    f, m = envelope_spectrum(sig, fs)
    cf = characteristic_freqs()
    fig, ax = plt.subplots(figsize=(8, 2.5), dpi=140)
    fig.patch.set_facecolor(BRAND["bg"])
    ax.set_facecolor(BRAND["surface"])
    ax.semilogy(f, m + 1e-9, color=BRAND["neon"], linewidth=0.8)
    ax.set_xlim(0, 600)
    ax.set_xlabel("Frequency (Hz)", color="#cfd8dc", fontsize=9)
    ax.set_ylabel("Envelope mag", color="#cfd8dc", fontsize=9)
    ax.tick_params(colors="#9aa6ad", labelsize=8)
    for spine in ax.spines.values():
        spine.set_color(BRAND["border"])
    for label, freq, color in [
        ("BPFO", cf.bpfo, BRAND["neon"]),
        ("BPFI", cf.bpfi, "#62d4ff"),
        ("BSF", cf.bsf, "#ffb347"),
        ("FTF", cf.ftf, "#cfd8dc"),
    ]:
        ax.axvline(freq, color=color, linewidth=0.8, linestyle="--", alpha=0.7)
        ax.text(freq + 2, ax.get_ylim()[1] * 0.4, label, color=color, fontsize=8)
    ax.set_title("Envelope spectrum — fault frequencies highlighted", color=BRAND["neon"], fontsize=10, pad=8)
    fig.tight_layout()
    return fig


# ---- HEADER ----
st.markdown(
    """
    <div class="forge-hero">
      <h1>FORGE</h1>
      <div class="tagline">Forecasted Onset of Rotational-Gear Endpoint &nbsp;·&nbsp;
      Predictive bearing-failure for USMC ground-fleet wheel hubs (CBM+) &nbsp;·&nbsp;
      MARCORLOGCOM AI Forum Hackathon 2026</div>
    </div>
    """,
    unsafe_allow_html=True,
)


# ---- SIDEBAR (Asset roster) ----
vehicles = load_vehicles()
with st.sidebar:
    st.markdown("### Test Asset Roster")
    st.caption("Pick a vehicle from the LOGCOM CBM+ telemetry queue.")
    vehicle_labels = [f"{v['vehicle_id']} — {v['type'].split()[0]}" for v in vehicles]
    sel = st.radio("Asset", vehicle_labels, label_visibility="collapsed")
    sel_idx = vehicle_labels.index(sel)
    vehicle = vehicles[sel_idx]

    st.markdown("---")
    st.markdown("### Asset Card")
    st.markdown(
        f"""
        <div class="forge-card">
          <div class="forge-kv"><span class="k">Type</span><span class="v">{vehicle['type']}</span></div>
          <div class="forge-kv"><span class="k">Unit</span><span class="v">{vehicle['unit']}</span></div>
          <div class="forge-kv"><span class="k">Hub</span><span class="v">{vehicle['hub_position']}</span></div>
          <div class="forge-kv"><span class="k">Op Hours</span><span class="v">{vehicle['operating_hours']:,}</span></div>
          <div class="forge-kv"><span class="k">Since Overhaul</span><span class="v">{vehicle['since_last_overhaul_hr']} hr</span></div>
          <div class="forge-kv"><span class="k">Replacement NSN</span><span class="v">{vehicle['nsn']}</span></div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown("---")
    run_btn = st.button("RUN VIBRATION ANALYSIS", use_container_width=True)
    hero_mode = st.toggle("Hero mode (Kamiwaza-deployed hero model for commander brief)", value=False, help="One-shot use of the larger model for the demo's wow moment.")
    st.markdown("---")
    st.markdown("### Deployment Mode")
    st.markdown(
        """
        <div class="forge-tool">
        <span class="toolname">$ env | grep KAMI</span><br/>
        # Today: cloud fallback; Kamiwaza on-prem when BASE_URL set<br/>
        KAMIWAZA_BASE_URL=&lt;unset&gt;<br/><br/>
        # Tomorrow (one env-var swap):<br/>
        export KAMIWAZA_BASE_URL=<br/>
        &nbsp;&nbsp;https://kamiwaza.local/api/v1<br/>
        # 100% data containment.
        </div>
        """,
        unsafe_allow_html=True,
    )


# ---- LOAD MODEL + DATA ----
corpus = load_corpus()
fs = corpus["fs"]
clf, clf_meta = get_classifier()

# Pick signal that matches the vehicle's "current" state (severity hint)
sig, sev = pick_signal_for_class(
    corpus,
    vehicle["current_class"],
    severity_hint=vehicle["current_severity"] if vehicle["current_class"] != "healthy" else None,
)

# Top metrics row
m1, m2, m3, m4 = st.columns(4)
m1.metric("Sample rate", f"{fs/1000:.0f} kHz", help="CWRU 12k drive-end canonical")
m2.metric("Classifier acc (held-out)", f"{clf_meta['test_acc']*100:.1f}%")
m3.metric("Signal window", "1.0 s")
m4.metric("Vehicle status", vehicle["current_class"].replace("_", " ").upper())

# ---- LAYOUT ----
left_col, right_col = st.columns([3, 2])

with left_col:
    st.markdown("### Live Sensor Stream")
    ts_slot = st.empty()
    spec_slot = st.empty()
    env_slot = st.empty()

with right_col:
    st.markdown("### Classifier Output")
    cls_slot = st.empty()
    st.markdown("### RUL Estimate")
    rul_slot = st.empty()
    st.markdown("### Agent Tool Calls")
    tool_slot = st.empty()

# Persist agent output across reruns
if "agent_result" not in st.session_state:
    st.session_state["agent_result"] = None
if "agent_for_vehicle" not in st.session_state:
    st.session_state["agent_for_vehicle"] = None
if "spectrogram_png" not in st.session_state:
    st.session_state["spectrogram_png"] = None


# ---- INITIAL RENDER ----

ts_slot.pyplot(render_timeseries(sig, fs), use_container_width=True)
spec_png, spec_fig = render_spectrogram_png(sig, fs, vehicle_id=vehicle["vehicle_id"])
spec_slot.pyplot(spec_fig, use_container_width=True)
env_slot.pyplot(render_envelope(sig, fs), use_container_width=True)

# Run classifier always
pred = predict_one(clf, sig, fs)
feats = hand_crafted_features(sig, fs)
sev_est = severity_from_features(feats)
rul = estimate_rul(pred["class"], pred["confidence"], sev_est, vehicle["operating_hours"])

# Render classifier card
cls_color = {
    "healthy": "pill-green",
    "outer_race": "pill-red",
    "inner_race": "pill-red",
    "ball": "pill-amber",
}.get(pred["class"], "pill-amber")
cls_label = pred["class"].replace("_", " ").upper()
prob_rows = "".join(
    f'<div class="forge-kv"><span class="k">{k.replace("_"," ")}</span><span class="v">{v*100:.1f}%</span></div>'
    for k, v in pred["probabilities"].items()
)
cls_slot.markdown(
    f"""
    <div class="forge-card">
      <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:10px;">
        <span class="forge-pill {cls_color}">{cls_label}</span>
        <span style="color: var(--neon); font-size: 22px; font-weight: 700;">{pred['confidence']*100:.0f}%</span>
      </div>
      {prob_rows}
    </div>
    """,
    unsafe_allow_html=True,
)

# RUL card
rul_pill = {
    "induct_now": ("pill-red", "INDUCT NOW"),
    "monitor_closely": ("pill-amber", "MONITOR CLOSELY"),
    "monitor_routine": ("pill-yellow", "MONITOR — ROUTINE"),
    "safe_to_operate": ("pill-green", "SAFE TO OPERATE"),
}.get(rul["recommendation"], ("pill-amber", "MONITOR"))
rul_slot.markdown(
    f"""
    <div class="forge-card">
      <div class="forge-kv"><span class="k">Remaining useful life</span>
        <span class="v" style="color: var(--neon); font-size: 18px;">{rul['rul_hours']:,} hr</span></div>
      <div class="forge-kv"><span class="k">Severity (model)</span>
        <span class="v">{sev_est:.2f}</span></div>
      <div class="forge-kv"><span class="k">Rule-based call</span>
        <span class="forge-pill {rul_pill[0]}">{rul_pill[1]}</span></div>
    </div>
    """,
    unsafe_allow_html=True,
)

# Initial parts lookup display
parts = lookup_part_availability(vehicle["nsn"])
tool_slot.markdown(
    f"""
    <div class="forge-tool">
      <span class="toolname">→ lookup_part_availability(nsn="{vehicle['nsn']}")</span><br/>
      &nbsp;&nbsp;name: {parts.get('name','-')}<br/>
      &nbsp;&nbsp;in_stock_at_mclb_albany: <span style="color: {'#00FFA7' if parts.get('in_stock_at_mclb_albany') else '#ff6b6b'}">{parts.get('in_stock_at_mclb_albany')}</span><br/>
      &nbsp;&nbsp;qty_albany: {parts.get('qty_albany',0)}<br/>
      &nbsp;&nbsp;alt_depots: {json.dumps(parts.get('alt_depots',{}))}<br/>
      &nbsp;&nbsp;unit_cost_usd: ${parts.get('unit_cost_usd','-')}
    </div>
    """,
    unsafe_allow_html=True,
)


# ---- BOTTOM PANEL: Maintenance log + Commander brief ----
st.markdown("---")
left2, right2 = st.columns([2, 3])

log = load_log()
with left2:
    st.markdown("### 6-Month Maintenance Log")
    wo = log.get(vehicle["vehicle_id"], [])
    log_html = "<div class='forge-card' style='max-height: 380px; overflow-y: auto;'>"
    for w in wo:
        log_html += (
            f"<div style='padding: 6px 0; border-bottom: 1px dashed var(--border);'>"
            f"<div style='color: var(--neon); font-size: 12px; font-weight: 600;'>{w['date']} · {w['type']} · {w['operating_hours_at_event']:,} hr</div>"
            f"<div style='color: #cfd8dc; font-size: 13px; margin-top: 2px;'>{w['narrative']}</div>"
            f"</div>"
        )
    log_html += "</div>"
    st.markdown(log_html, unsafe_allow_html=True)


with right2:
    st.markdown("### Commander's Recommendation (FORGE Agent)")
    rec_slot = st.empty()
    json_slot = st.empty()

    # Auto-run on button OR if we have no result yet for this vehicle
    needs_run = run_btn or st.session_state.get("agent_for_vehicle") != vehicle["vehicle_id"]

    if needs_run:
        with st.spinner("FORGE agent reasoning over spectrogram + maintenance log + parts availability..."):
            st.session_state["spectrogram_png"] = spec_png
            result = commander_recommendation(
                spectrogram_png=spec_png,
                classifier_result=pred,
                rul_result=rul,
                vehicle=vehicle,
                maintenance_log=wo,
                use_hero_model=hero_mode,
            )
            st.session_state["agent_result"] = result
            st.session_state["agent_for_vehicle"] = vehicle["vehicle_id"]

    result = st.session_state["agent_result"] or {}
    urgency_pill = {
        "red": "pill-red",
        "amber": "pill-amber",
        "yellow": "pill-yellow",
        "green": "pill-green",
    }.get(result.get("urgency", "amber"), "pill-amber")

    rec_label = (result.get("recommendation", "monitor")).replace("_", " ").upper()
    bullets_html = "".join(f"<li style='margin-bottom: 4px; color: #cfd8dc;'>{b}</li>" for b in result.get("rationale_bullets", []))

    rec_slot.markdown(
        f"""
        <div class="forge-rec">
          <div style="display:flex; justify-content:space-between; align-items:center;">
            <h2>{rec_label}</h2>
            <span class="forge-pill {urgency_pill}">{result.get('urgency','amber').upper()}</span>
          </div>
          <div style="color: #E5E5E5; font-size: 14px; margin: 10px 0; line-height: 1.5;">
            {result.get('commander_brief','')}
          </div>
          <ul style="margin: 6px 0 6px 18px; padding-left: 0; font-size: 13px;">{bullets_html}</ul>
          <div style="color: var(--text_dim); font-size: 12px; margin-top: 6px;">
            <strong>Predicted failure mode:</strong> {result.get('predicted_failure_mode','-')}<br/>
            <strong>Parts action:</strong> {result.get('parts_action','-')}<br/>
            <span style="color: var(--muted);">Model: {result.get('_model','?')} · Tool calls: {len(result.get('_tool_call_log', []))}</span>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    with json_slot.expander("Structured JSON output (for downstream GCSS-MC integration)"):
        st.json({k: v for k, v in result.items() if not k.startswith("_")})


# ---- FOOTER ----
st.markdown(
    f"""
    <div class="forge-footer">
      Real dataset cited: <strong>Case Western Reserve University Bearing Data Center</strong> · 12k drive-end accelerometer.
      Synthetic signals generated from same characteristic-frequency model (BPFO/BPFI/BSF/FTF on SKF 6205-2RS JEM geometry).
      <br/>
      <strong style="color: {BRAND['primary']};">Powered by Kamiwaza.</strong>
      &nbsp;·&nbsp; Orchestration Without Migration. Execution Without Compromise.
    </div>
    """,
    unsafe_allow_html=True,
)
