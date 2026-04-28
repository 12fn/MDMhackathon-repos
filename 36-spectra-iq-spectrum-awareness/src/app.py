"""SPECTRA — Marine FOB / Installation Spectrum Awareness.

Streamlit single-page app on port 3036.

Demo path:
  - 6 synthetic 1-sec complex64 I/Q captures @ 8 MS/s (NIST schema-compatible)
  - Pick a capture → STFT → 128x128 spectrogram (Plotly heatmap)
  - Vision-language `gpt-4o` ingests spectrogram + SigMF metadata header
    → strict JSON classification card
  - Hero `chat` (`gpt-5.4`, 35s, cache-first) writes the SIPR-format
    "RF Spectrum Awareness Brief"

Run:
  streamlit run src/app.py --server.port 3036 --server.headless true \\
    --server.runOnSave false --server.fileWatcherType none \\
    --browser.gatherUsageStats false
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

# repo root on sys.path so `from shared.kamiwaza_client import BRAND` works
ROOT = Path(__file__).resolve().parent.parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from shared.kamiwaza_client import BRAND  # noqa: E402

# allow `from agent import ...`
sys.path.insert(0, str(Path(__file__).resolve().parent))
from agent import classify_capture, generate_brief  # noqa: E402
from signal_proc import (  # noqa: E402
    load_iq, stft_db, psd_dbm, spectrogram_image_png,
    sigmf_header, quick_features,
)


APP_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = APP_DIR / "data"
CAP_DIR = DATA_DIR / "captures"
META_CSV = DATA_DIR / "captures_metadata.csv"
VENDOR_MAP = DATA_DIR / "vendor_protocol_map.json"
CACHE_PATH = DATA_DIR / "cached_briefs.json"


st.set_page_config(
    page_title="SPECTRA — Marine FOB Spectrum Awareness",
    page_icon="📶",
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
.flag-nominal           {{ color:#00FFA7; font-weight:700; }}
.flag-suspicious-pattern{{ color:#F2C94C; font-weight:700; }}
.flag-unauthorized-band {{ color:#FF8C42; font-weight:700; }}
.flag-active-jamming    {{ color:#FF4D4D; font-weight:700; }}
.cls-row {{ background: var(--kw-surface2); border:1px solid var(--kw-border);
  border-left: 2px solid var(--kw-primary);
  border-radius: 6px; padding: 10px 12px; margin-bottom:6px;}}
code {{ color: #00FFA7 !important; background: #0E0E0E !important; }}
.sigmf-block {{
  background: #07120C; border: 1px solid var(--kw-border);
  border-left: 3px solid var(--kw-neon);
  border-radius: 6px; padding: 10px 14px;
  font-family: 'JetBrains Mono', ui-monospace, Menlo, monospace;
  font-size: 0.78rem; color:#BDBDBD; white-space: pre;
}}
</style>
"""
st.markdown(KAMIWAZA_CSS, unsafe_allow_html=True)


# ─────────────────────────────────────────────────────────────────────────────
# Header
# ─────────────────────────────────────────────────────────────────────────────
hdr_l, hdr_r = st.columns([0.72, 0.28])
with hdr_l:
    st.markdown(
        "<h1 data-testid='app-title'>SPECTRA "
        "<span class='tag'>Agent #36 · FOB Spectrum Awareness</span></h1>",
        unsafe_allow_html=True,
    )
    st.markdown(
        "<div style='color:#BDBDBD;font-size:0.95rem;'>"
        "Raw I/Q in, threat picture out. STFT spectrogram → multimodal "
        "classifier → SIPR-format Spectrum Awareness Brief. The single-snapshot "
        "raw-I/Q sister to GHOST (#21). "
        "<i>AI Inside Your Security Boundary.</i>"
        "</div>",
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
def load_metadata() -> pd.DataFrame:
    real_path = os.getenv("REAL_DATA_PATH")
    if real_path:
        try:
            sys.path.insert(0, str(DATA_DIR))
            from load_real import load_real  # noqa: WPS433
            return load_real()
        except Exception as e:  # noqa: BLE001
            st.warning(
                f"REAL_DATA_PATH set but load_real() failed ({e}); "
                "falling back to synthetic captures."
            )
    if not META_CSV.exists():
        # auto-generate (data only, skip LLM cache)
        os.environ["SKIP_PRECOMPUTE"] = "1"
        sys.path.insert(0, str(DATA_DIR))
        from generate import main as gen_main  # noqa: WPS433
        gen_main()
    return pd.read_csv(META_CSV)


@st.cache_data(show_spinner=False)
def load_vendor_map() -> dict:
    if VENDOR_MAP.exists():
        return json.loads(VENDOR_MAP.read_text())
    return {}


@st.cache_data(show_spinner=False)
def load_cached_briefs() -> dict:
    if CACHE_PATH.exists():
        try:
            return json.loads(CACHE_PATH.read_text())
        except Exception:  # noqa: BLE001
            return {}
    return {}


@st.cache_data(show_spinner=False)
def load_capture_iq(filename: str) -> tuple[np.ndarray, float]:
    """Load a complex64 .npy capture from data/captures/. Returns (iq, fs)."""
    path = DATA_DIR / filename
    if not path.exists():
        # auto-generate if missing
        os.environ["SKIP_PRECOMPUTE"] = "1"
        sys.path.insert(0, str(DATA_DIR))
        from generate import main as gen_main  # noqa: WPS433
        gen_main()
    iq = load_iq(path)
    # Find the metadata row to get the synth sample rate
    md = load_metadata()
    row = md[md["filename"] == filename].iloc[0]
    fs = float(row["synth_sample_rate_MSPS"]) * 1_000_000.0
    return iq, fs


metadata_df = load_metadata()
vendor_map = load_vendor_map()
cached_briefs = load_cached_briefs()


# ─────────────────────────────────────────────────────────────────────────────
# Sidebar — capture picker & scenario flag legend
# ─────────────────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("### Captures")
    st.caption("6 synthetic 1-sec I/Q captures, NIST SigMF schema. "
                "Drop real NIST .npy files in `data/captures/` to swap.")
    cap_options = metadata_df["scenario_id"].tolist()
    cap_labels = {row.scenario_id: f"{row.scenario_id} · {row.label}"
                    for row in metadata_df.itertuples()}
    cap_pick = st.radio(
        "Pick a capture",
        cap_options,
        index=0,
        format_func=lambda s: cap_labels.get(s, s),
        key="cap_pick",
    )
    st.divider()
    st.markdown("### Anomaly flag legend")
    st.markdown(
        "<div style='font-size:0.84rem;line-height:1.6;'>"
        "<span class='flag-nominal'>● nominal</span><br>"
        "<span class='flag-suspicious-pattern'>● suspicious-pattern</span><br>"
        "<span class='flag-unauthorized-band'>● unauthorized-band</span><br>"
        "<span class='flag-active-jamming'>● active-jamming</span>"
        "</div>",
        unsafe_allow_html=True,
    )
    st.divider()
    st.markdown("### Kamiwaza Stack")
    st.markdown(
        "- Inference Mesh (vLLM)\n"
        "- Model Gateway (multimodal — any vision model)\n"
        "- DDE — Distributed Data Engine\n"
        "- ReBAC access control\n"
        "- IL5/IL6 ready · NIPR/SIPR/JWICS"
    )
    st.markdown(
        "<div style='color:#7FE5A1; font-size:0.78rem; margin-top:0.5rem;'>"
        "Set <code>KAMIWAZA_BASE_URL</code> → 100% on-prem. Zero code change.</div>",
        unsafe_allow_html=True,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Selected capture → load + DSP
# ─────────────────────────────────────────────────────────────────────────────
sel_row = metadata_df[metadata_df["scenario_id"] == cap_pick].iloc[0]
sel_meta = sel_row.to_dict()
iq, fs = load_capture_iq(sel_meta["filename"])
features = quick_features(iq, fs)


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
metric_card(k1, "Center freq",
             f"{sel_meta['center_freq_GHz']} GHz",
             f"BW {sel_meta['bw_MHz']:.1f} MHz · gain {sel_meta['gain_dB']} dB")
metric_card(k2, "Sample rate",
             f"{sel_meta['synth_sample_rate_MSPS']:.1f} MS/s",
             f"NIST canonical {sel_meta['nist_sample_rate_MSPS']:.0f} MS/s")
metric_card(k3, "Bursts (DSP)", f"{features['burst_count']}",
             f"duty {features['duty_cycle_pct']:.1f}%")
metric_card(k4, "RMS / SNR",
             f"{features['rms']:.3f}",
             f"SNR ~ {features['snr_estimate_dB']:.0f} dB · "
             f"occ {features['occupancy_pct']:.0f}%")
metric_card(k5, "Hardware", f"{sel_meta['hardware'].split('/')[0]}",
             f"floor {sel_meta['noise_floor_dBm']} dBm · "
             f"cal {sel_meta['calibration']}")


# ─────────────────────────────────────────────────────────────────────────────
# Spectrogram + PSD + SigMF header
# ─────────────────────────────────────────────────────────────────────────────
left, right = st.columns([0.65, 0.35])

with left:
    st.markdown("#### STFT spectrogram · 1-second window · dB")
    st.caption("scipy.signal.stft — DC centered, fftshifted. This is the "
                "exact image (downsampled to 384 px) the multimodal "
                "model receives.")
    f_stft, t_stft, db_stft = stft_db(iq, fs)
    fig = go.Figure(data=go.Heatmap(
        z=db_stft,
        x=t_stft,
        y=f_stft / 1e6,
        colorscale=[
            [0.0, "#0A0A0A"], [0.18, "#0E2A1B"], [0.35, "#065238"],
            [0.55, "#00BB7A"], [0.78, "#00FFA7"],
            [0.92, "#F2C94C"], [1.0, "#FF4D4D"],
        ],
        colorbar=dict(title="dB", tickfont=dict(color="#BDBDBD"), len=0.85),
        zmin=float(np.percentile(db_stft, 4.0)),
        zmax=float(np.percentile(db_stft, 99.5)),
        hovertemplate="t=%{x:.4f}s · f=%{y:+.2f} MHz · %{z:.1f} dB<extra></extra>",
    ))
    fig.update_layout(
        plot_bgcolor=BRAND["bg"], paper_bgcolor=BRAND["bg"],
        font_color="#E5E5E5", height=380,
        margin=dict(l=10, r=10, t=10, b=30),
        xaxis=dict(title="time (s)", color="#BDBDBD", gridcolor=BRAND["border"]),
        yaxis=dict(
            title=f"baseband offset (MHz) · center {sel_meta['center_freq_GHz']:.4f} GHz",
            color="#BDBDBD", gridcolor=BRAND["border"],
        ),
    )
    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})

with right:
    st.markdown("#### SigMF-format header")
    st.markdown(
        f"<div class='sigmf-block'>{sigmf_header(sel_meta)}</div>",
        unsafe_allow_html=True,
    )
    st.markdown("#### Welch PSD")
    f_psd, p_psd = psd_dbm(iq, fs,
                            noise_floor_dbm=float(sel_meta["noise_floor_dBm"]))
    psd_fig = go.Figure(data=go.Scatter(
        x=f_psd / 1e6, y=p_psd, mode="lines",
        line=dict(color=BRAND["neon"], width=1.6),
        hovertemplate="%{x:+.2f} MHz · %{y:.1f} dBm/Hz<extra></extra>",
    ))
    psd_fig.add_hline(
        y=float(sel_meta["noise_floor_dBm"]),
        line_color="#7E7E7E", line_dash="dot",
        annotation_text=f"noise floor {sel_meta['noise_floor_dBm']} dBm",
        annotation_position="bottom right",
        annotation_font_color="#7E7E7E",
    )
    psd_fig.update_layout(
        plot_bgcolor=BRAND["bg"], paper_bgcolor=BRAND["bg"],
        font_color="#E5E5E5", height=180,
        margin=dict(l=10, r=10, t=10, b=24),
        xaxis=dict(title="MHz offset", color="#BDBDBD",
                    gridcolor=BRAND["border"]),
        yaxis=dict(title="dBm/Hz", color="#BDBDBD",
                    gridcolor=BRAND["border"]),
    )
    st.plotly_chart(psd_fig, use_container_width=True,
                     config={"displayModeBar": False})


# ─────────────────────────────────────────────────────────────────────────────
# Multimodal classifier — vision-language strict-JSON call
# ─────────────────────────────────────────────────────────────────────────────
st.markdown("---")
st.markdown("#### Multimodal Classification · STFT image + SigMF header → strict JSON")
st.caption("Vision-language model ingests the spectrogram PNG plus the SigMF "
            "metadata header plus the deterministic DSP feature vector. "
            "25-second watchdog. Deterministic fallback never blocks the demo.")

cls_col1, cls_col2 = st.columns([0.5, 0.5])

if "classification" not in st.session_state:
    st.session_state["classification"] = {}
if "classified_for" not in st.session_state:
    st.session_state["classified_for"] = None

# Reset classification when capture changes
if st.session_state["classified_for"] != cap_pick:
    st.session_state["classification"] = {}

with cls_col1:
    classify_btn = st.button(
        "Classify capture (multimodal)",
        type="primary",
        key="classify_btn",
    )
    if classify_btn:
        with st.spinner("Routing the spectrogram through the Inference Mesh "
                         "(multimodal model)…"):
            png_bytes = spectrogram_image_png(iq, fs, max_side=384)
            tag = classify_capture(
                image_png=png_bytes,
                metadata=sel_meta,
                features=features,
                timeout=25.0,
            )
        st.session_state["classification"] = tag
        st.session_state["classified_for"] = cap_pick

    cls = st.session_state.get("classification", {})
    if cls:
        flag = cls.get("anomaly_flag", "nominal")
        flag_class = f"flag-{flag}"
        st.markdown(
            f"<div class='cls-row'>"
            f"<div style='font-size:1.05rem;'>"
            f"<b>{cls.get('modulation_class','?')}</b> · "
            f"<b style='color:#00FFA7;'>{cls.get('protocol_inferred','?')}</b> "
            f"&nbsp; <span class='{flag_class}'>● {flag}</span> &nbsp; "
            f"confidence <b>{cls.get('confidence',0):.2f}</b></div>"
            f"<div style='color:#BDBDBD;font-size:0.85rem;margin-top:6px;'>"
            f"device: <code>{cls.get('device_class_hypothesis','?')}</code> · "
            f"bursts: <code>{cls.get('estimated_burst_count','?')}</code> · "
            f"duty: <code>{cls.get('duty_cycle_estimate_pct',0):.1f}%</code> · "
            f"strength: <code>{cls.get('signal_strength_band','?')}</code>"
            f"</div></div>",
            unsafe_allow_html=True,
        )
        # Vendor-protocol cross-reference
        mod = cls.get("modulation_class", "unknown")
        proto = cls.get("protocol_inferred", "unknown")
        suggestions = vendor_map.get(mod, {}).get(proto, [])
        if suggestions:
            st.caption(
                "Vendor / protocol map suggests device classes: "
                + " · ".join(f"`{s}`" for s in suggestions)
            )
    else:
        st.markdown(
            "<div class='mis-panel' style='color:#7E7E7E;'>"
            "Click <b>Classify capture (multimodal)</b> above. The model "
            "ingests the STFT spectrogram + SigMF header + DSP features and "
            "returns a strict-JSON classification card with an explicit "
            "<code>anomaly_flag</code>."
            "</div>",
            unsafe_allow_html=True,
        )

with cls_col2:
    st.markdown("**Strict JSON output**")
    cls = st.session_state.get("classification", {})
    if cls:
        public = {k: v for k, v in cls.items() if not k.startswith("_")}
        st.code(json.dumps(public, indent=2), language="json")
    else:
        st.markdown(
            "<div class='mis-panel' style='color:#7E7E7E;'>"
            "Awaiting multimodal call. Schema:<br>"
            "<code>modulation_class · protocol_inferred · "
            "estimated_burst_count · duty_cycle_estimate_pct · "
            "signal_strength_band · device_class_hypothesis · "
            "anomaly_flag · confidence</code>"
            "</div>",
            unsafe_allow_html=True,
        )


# ─────────────────────────────────────────────────────────────────────────────
# Hero brief panel — RF Spectrum Awareness Brief
# ─────────────────────────────────────────────────────────────────────────────
st.markdown("---")
st.markdown("#### RF Spectrum Awareness Brief · Hero AI narrative")
st.caption("Cache-first. Pre-computed for all six scenarios so the demo never "
            "blocks. Live regenerate uses the hero model on a 35-second wall "
            "clock with deterministic fallback.")

ai_l, ai_r = st.columns([0.62, 0.38])

if "brief_text" not in st.session_state:
    st.session_state["brief_text"] = cached_briefs.get(
        cap_pick,
        "Cached brief not found. Click Regenerate to draft live."
    )
    st.session_state["brief_source"] = "cached"
    st.session_state["brief_for"] = cap_pick

# Reload cached when scenario flipped
if st.session_state.get("brief_for") != cap_pick:
    st.session_state["brief_text"] = cached_briefs.get(
        cap_pick, "Cached brief not found for this capture."
    )
    st.session_state["brief_source"] = "cached"
    st.session_state["brief_for"] = cap_pick

regen_col1, regen_col2 = ai_l.columns([0.5, 0.5])
regen_btn = regen_col1.button("Regenerate (live · hero model)",
                                type="primary", key="regen_btn")
reload_btn = regen_col2.button("Reload cached", key="reload_btn")

if reload_btn:
    st.session_state["brief_text"] = cached_briefs.get(cap_pick, "")
    st.session_state["brief_source"] = "cached"

if regen_btn:
    cls = st.session_state.get("classification") or {}
    if not cls:
        # If user hasn't classified yet, run the deterministic baseline so the
        # brief still has structured input
        from agent import _baseline_classify  # noqa: WPS433
        cls = _baseline_classify(sel_meta, features)
        st.session_state["classification"] = cls
        st.session_state["classified_for"] = cap_pick

    payload = {
        "site": "FOB Spectrum Manager · Marine Installation perimeter",
        "capture": cap_pick,
        "label": sel_meta["label"],
        "metadata": {
            "center_freq_GHz": sel_meta["center_freq_GHz"],
            "bw_MHz": sel_meta["bw_MHz"],
            "sample_rate_MSPS": sel_meta["nist_sample_rate_MSPS"],
            "gain_dB": sel_meta["gain_dB"],
            "hardware": sel_meta["hardware"],
            "noise_floor_dBm": sel_meta["noise_floor_dBm"],
            "calibration": sel_meta["calibration"],
        },
        "classifier_json": {k: v for k, v in cls.items()
                              if not k.startswith("_")},
    }
    with st.spinner("Hero model drafting RF Spectrum Awareness Brief via the "
                     "Inference Mesh…"):
        text = generate_brief(payload, model="gpt-5.4", timeout=35)
    st.session_state["brief_text"] = text
    st.session_state["brief_source"] = "live"

with ai_l:
    src = st.session_state.get("brief_source", "cached")
    st.markdown(
        f"<div style='font-size:0.78rem;color:#7E7E7E;'>"
        f"Source: <span class='tag'>{src.upper()}</span> · "
        f"capture: <code>{cap_pick}</code></div>",
        unsafe_allow_html=True,
    )
    st.markdown(
        f"<div class='mis-panel' data-testid='brief-output'>"
        f"{st.session_state['brief_text']}</div>",
        unsafe_allow_html=True,
    )

with ai_r:
    st.markdown("**Vendor / protocol device-class map**")
    if vendor_map:
        # Render top mappings in a compact dataframe
        rows = []
        for mod, protos in vendor_map.items():
            for proto, devs in protos.items():
                rows.append({
                    "modulation": mod,
                    "protocol": proto,
                    "device_classes": ", ".join(devs),
                })
        vmap_df = pd.DataFrame(rows)
        st.dataframe(vmap_df, hide_index=True, use_container_width=True,
                      height=320)
    st.markdown("**Sister app: GHOST (#21)**")
    st.caption("If `anomaly_flag != nominal`, push this capture to GHOST "
                "for pattern-of-life correlation against the perimeter "
                "Wi-Fi + BT scan. SPECTRA = single I/Q snapshot. "
                "GHOST = aggregate scan-table forensics.")


# ─────────────────────────────────────────────────────────────────────────────
# Footer
# ─────────────────────────────────────────────────────────────────────────────
st.markdown(
    f"<div class='brand-footer'>"
    f"<span>SPECTRA · Powered by Kamiwaza · 6 synthetic 1-sec I/Q captures · "
    f"scipy.signal.stft → multimodal vision-language → SIPR brief</span>"
    f"<span>Real dataset: <i>NIST Wi-Fi & Bluetooth I/Q RF Recordings "
    f"(2.4 / 5 GHz)</i> · 900 captures @ 30 MS/s · plug in via "
    f"<code>data/load_real.py</code></span>"
    f"</div>",
    unsafe_allow_html=True,
)
