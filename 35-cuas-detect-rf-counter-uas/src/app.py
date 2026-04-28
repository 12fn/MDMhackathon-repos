"""CUAS-DETECT — Counter-UAS RF Detection for Installation Force Protection.

Streamlit single-page app on port 3035.

Demo path:
  - Operator picks one of 6 sample RF spectrograms (or drops their own PNG).
  - Heuristic feature extraction (numpy on the spectrogram array) emits a
    baseline classifier guess.
  - Multimodal vision model ingests the spectrogram + heuristic JSON and
    returns a structured CUAS classification + intent JSON.
  - Hero engagement-brief LLM (cache-first) writes a CUAS Engagement
    Recommendation for the watch officer.

Run:
  streamlit run src/app.py --server.port 3035 --server.headless true \\
    --server.runOnSave false --server.fileWatcherType none \\
    --browser.gatherUsageStats false
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from PIL import Image

# repo root on sys.path so `from shared.kamiwaza_client import BRAND` works
ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from shared.kamiwaza_client import BRAND  # noqa: E402

# allow `from agent import ...`
sys.path.insert(0, str(Path(__file__).resolve().parent))
from agent import (  # noqa: E402
    heuristic_features,
    vision_classify,
    engagement_brief,
    build_scenario_payload,
)


APP_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = APP_DIR / "data"
SPECTRA_DIR = APP_DIR / "sample_spectra"
MANIFEST_PATH = DATA_DIR / "spectra_manifest.json"
CACHE_PATH = DATA_DIR / "cached_briefs.json"
ENGAGEMENT_PATH = DATA_DIR / "engagement_options.json"
RF_DB_PATH = DATA_DIR / "rf_id_db.csv"


st.set_page_config(
    page_title="CUAS-DETECT — Counter-UAS RF Detection",
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
.callout-strip {{
  background: linear-gradient(90deg, rgba(0,187,122,0.10), rgba(0,255,167,0.04));
  border: 1px solid var(--kw-primary); border-radius: 6px; padding: 8px 12px;
  font-family: 'JetBrains Mono', ui-monospace, Menlo, monospace;
  color: var(--kw-neon); font-weight: 600; margin: 6px 0;
}}
.opt-row {{ background: var(--kw-surface2); border:1px solid var(--kw-border);
  border-left: 2px solid var(--kw-primary);
  border-radius: 6px; padding: 8px 10px; margin-bottom:6px;}}
.opt-PASSIVE   {{ border-left-color: #7FE5A1; }}
.opt-NON     {{ border-left-color: #F2C94C; }}
.opt-KINETIC {{ border-left-color: #FF4D4D; }}
.threat-LOW  {{ color:#7FE5A1; font-weight:700; }}
.threat-MED  {{ color:#F2C94C; font-weight:700; }}
.threat-HIGH {{ color:#FF4D4D; font-weight:700; }}
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
        "<h1 data-testid='app-title'>CUAS-DETECT "
        "<span class='tag'>Agent #35 · LOGCOM Installation Force Protection</span></h1>",
        unsafe_allow_html=True,
    )
    st.markdown(
        "<div style='color:#BDBDBD;font-size:0.95rem;'>"
        "Counter-UAS RF detection for Marine installation force protection — "
        "spectrogram in, watch-officer engagement recommendation out, in seconds. "
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
# Data load (auto-generate if missing)
# ─────────────────────────────────────────────────────────────────────────────
@st.cache_data(show_spinner=False)
def load_manifest() -> list[dict]:
    if not MANIFEST_PATH.exists():
        import os as _os
        _os.environ["SKIP_PRECOMPUTE"] = "1"
        sys.path.insert(0, str(DATA_DIR))
        from generate import main as gen_main  # noqa: WPS433
        gen_main()
    return json.loads(MANIFEST_PATH.read_text())


@st.cache_data(show_spinner=False)
def load_cached_briefs() -> dict:
    if CACHE_PATH.exists():
        try:
            return json.loads(CACHE_PATH.read_text())
        except Exception:  # noqa: BLE001
            return {}
    return {}


@st.cache_data(show_spinner=False)
def load_engagement_options() -> list[dict]:
    if ENGAGEMENT_PATH.exists():
        return json.loads(ENGAGEMENT_PATH.read_text())
    return []


@st.cache_data(show_spinner=False)
def load_rf_db() -> pd.DataFrame:
    if RF_DB_PATH.exists():
        return pd.read_csv(RF_DB_PATH)
    return pd.DataFrame()


@st.cache_data(show_spinner=False)
def get_signature_meta() -> dict[str, dict]:
    """Reach into generate.SIGNATURES for ground-truth labels."""
    sys.path.insert(0, str(DATA_DIR))
    from generate import SIGNATURES  # noqa: WPS433
    return {s["id"]: s for s in SIGNATURES}


manifest = load_manifest()
cached_briefs = load_cached_briefs()
engagement_options = load_engagement_options()
rf_db = load_rf_db()
sig_meta = get_signature_meta()


# ─────────────────────────────────────────────────────────────────────────────
# Sidebar
# ─────────────────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("### Site Context")
    st.markdown(
        "**Camp Pendleton — Bldg 22 perimeter sensor**  \n"
        "DTG: `271730ZAPR26` · Wind: `210/06KT` · Ceiling: `BKN 4500`  \n"
        "Civil airspace: `0.4 nm` · Friendly air active: `none`"
    )
    st.divider()
    st.markdown("### Detection Pipeline")
    st.markdown(
        "1. **Heuristic features** — numpy on spectrogram array  \n"
        "2. **Vision classifier** — multimodal AI engine, structured JSON  \n"
        "3. **Engagement brief** — hero model, cache-first, 35s watchdog"
    )
    st.divider()
    st.markdown("### Kamiwaza Stack")
    st.markdown(
        "- Inference Mesh (vLLM) · multimodal\n"
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
    st.divider()
    st.markdown("### RF ID Database")
    st.caption(f"{len(rf_db)} known controller signatures loaded")


# ─────────────────────────────────────────────────────────────────────────────
# Operator: pick a sample spectrogram or upload one
# ─────────────────────────────────────────────────────────────────────────────
st.markdown("### 1) RF Capture · pick a sample or drop a spectrogram PNG")
pick_col, up_col = st.columns([0.6, 0.4])

with pick_col:
    options = {f"{m['title']}  ({m['band_ghz']} GHz)": m for m in manifest}
    chosen_label = st.radio(
        "Sample captures",
        list(options.keys()),
        index=0,
        key="spectra_pick",
        horizontal=False,
    )
    chosen = options[chosen_label]

with up_col:
    uploaded = st.file_uploader(
        "…or drop your own spectrogram (PNG)",
        type=["png", "jpg", "jpeg"],
        key="spec_upload",
    )


@st.cache_data(show_spinner=False)
def load_npy(npy_path: str) -> np.ndarray:
    return np.load(npy_path)


def _intensity_from_image(img: Image.Image) -> np.ndarray:
    g = np.asarray(img.convert("L"), dtype=np.float32) / 255.0
    return g


# Resolve the active spectrogram (image + numpy array)
if uploaded is not None:
    pil = Image.open(uploaded)
    spec_arr = _intensity_from_image(pil)
    spec_png_path = APP_DIR / ".upload_tmp.png"
    pil.convert("RGB").save(spec_png_path, format="PNG")
    active = {
        "id": "uploaded",
        "title": uploaded.name,
        "uas_class": "unknown",
        "controller": "unknown",
        "band_ghz": "unknown",
        "ground_truth_range_km": 0.0,
        "intent_hint": "unknown",
    }
else:
    spec_arr = load_npy(str(APP_DIR / chosen["npy"]))
    spec_png_path = APP_DIR / chosen["png"]
    full_meta = sig_meta.get(chosen["id"], {})
    active = {
        "id": chosen["id"],
        "title": chosen["title"],
        "uas_class": chosen["uas_class"],
        "controller": chosen["controller"],
        "band_ghz": chosen["band_ghz"],
        "ground_truth_range_km": full_meta.get("ground_truth_range_km", 0.0),
        "intent_hint": full_meta.get("intent_hint", "unknown"),
    }


# ─────────────────────────────────────────────────────────────────────────────
# Spectrogram heatmap (Plotly)
# ─────────────────────────────────────────────────────────────────────────────
st.markdown("### 2) Spectrogram heatmap · frequency × time")
hm_l, hm_r = st.columns([0.66, 0.34])
with hm_l:
    fig = go.Figure(data=go.Heatmap(
        z=spec_arr[::-1],  # invert so high freq is up
        colorscale=[
            [0.00, "#0A140C"], [0.25, "#0DCC8A"], [0.55, "#00FFA7"],
            [0.80, "#F2C94C"], [1.00, "#FF4D4D"],
        ],
        showscale=True,
        colorbar=dict(title="intensity", thickness=10, len=0.8,
                       tickfont=dict(color="#E5E5E5")),
    ))
    fig.update_layout(
        plot_bgcolor=BRAND["bg"], paper_bgcolor=BRAND["bg"],
        font_color="#E5E5E5", height=320,
        margin=dict(l=20, r=10, t=10, b=20),
        xaxis=dict(title="time →", gridcolor=BRAND["border"], showticklabels=False),
        yaxis=dict(title="frequency ↑", gridcolor=BRAND["border"], showticklabels=False),
    )
    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})

with hm_r:
    st.markdown("**Capture metadata**")
    st.markdown(
        f"- **Title:** {active['title']}\n"
        f"- **Band:** {active['band_ghz']} GHz\n"
        f"- **GT range:** {active['ground_truth_range_km']} km\n"
        f"- **GT intent:** `{active['intent_hint']}`"
    )
    st.image(str(spec_png_path),
              caption="Original spectrogram tile (annotated)",
              use_container_width=True)


# ─────────────────────────────────────────────────────────────────────────────
# Stage 2 — Heuristic feature extraction
# ─────────────────────────────────────────────────────────────────────────────
st.markdown("### 3) Heuristic feature extraction · numpy baseline classifier")

if "feats_payload" not in st.session_state or st.session_state.get("feats_for") != active["id"]:
    st.session_state["feats_payload"] = heuristic_features(spec_arr)
    st.session_state["feats_for"] = active["id"]

feats_payload = st.session_state["feats_payload"]
features = feats_payload["features"]
baseline = feats_payload["baseline"]

f_l, f_r = st.columns([0.55, 0.45])
with f_l:
    st.markdown("**Spectral features**")
    st.code(json.dumps(features, indent=2), language="json")
with f_r:
    st.markdown("**Baseline classifier (deterministic)**")
    st.code(json.dumps(baseline, indent=2), language="json")
    st.markdown(
        f"<div class='callout-strip'>BASELINE → {baseline['uas_class_guess']} "
        f"· {baseline['controller_guess']} · intent={baseline['intent_guess']} "
        f"· conf={baseline['baseline_confidence']:.2f}</div>",
        unsafe_allow_html=True,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Stage 3 — Multimodal vision classifier (live)
# ─────────────────────────────────────────────────────────────────────────────
st.markdown("### 4) Multimodal vision classifier · structured CUAS JSON")
st.caption(
    "Multimodal AI engine ingests the spectrogram + heuristic JSON sidecar → "
    "structured UAS class, intent, range, and recommended COA."
)

cls_l, cls_r = st.columns([0.55, 0.45])
with cls_l:
    run_vision = st.button("Run vision classifier (live · multimodal)",
                            type="primary", key="run_vision_btn")
    use_cache = st.button("Use cached classification", key="use_cache_btn")

# init
if ("vision_for" not in st.session_state
        or st.session_state.get("vision_for") != active["id"]):
    # Default: load from cache if available
    cached_entry = cached_briefs.get(active["id"], {})
    cached_baseline = cached_entry.get("baseline_classifier", baseline)
    # Build a default vision-style payload from cached ground truth
    default_vision = {
        "uas_class": active["uas_class"],
        "confidence": float(cached_baseline.get("baseline_confidence", 0.6)),
        "controller_signature_match":
            active["controller"] if active["controller"] in
            {"OcuSync","Lightbridge","WiFi","LoRa","proprietary","none"}
            else "none",
        "inferred_intent": active["intent_hint"],
        "estimated_range_km": active["ground_truth_range_km"],
        "recommended_action": (
            "monitor" if active["uas_class"] == "ambient"
            else "escalate-to-FOC" if active["uas_class"] == "swarm"
            else "request-engagement" if active["intent_hint"] == "strike"
            else "jam-non-kinetic"
        ),
        "rationale": "Cached classification for the demo path; click "
                     "'Run vision classifier' to invoke the live multimodal model.",
        "EOC_callout_text": (
            f"INBOUND {active['uas_class'].upper()} | {active['controller']} | "
            f"~{active['ground_truth_range_km']}km | "
            f"intent={active['intent_hint']}"
            if active["uas_class"] != "ambient"
            else "AMBIENT | no UAS contact above detection threshold"
        ),
        "_source": "cached",
    }
    st.session_state["vision_json"] = default_vision
    st.session_state["vision_for"] = active["id"]

if run_vision:
    with st.spinner("Routing through Inference Mesh (multimodal)…"):
        v = vision_classify(spec_png_path, feats_payload, timeout=25)
        v["_source"] = "live"
        st.session_state["vision_json"] = v

if use_cache:
    st.session_state.pop("vision_for", None)  # force re-init from cache
    st.rerun()

vision = st.session_state["vision_json"]

# Render vision result + EOC callout
with cls_l:
    src = vision.get("_source", "cached")
    st.markdown(
        f"<div style='font-size:0.78rem;color:#7E7E7E;margin-top:6px;'>"
        f"Source: <span class='tag'>{src.upper()}</span></div>",
        unsafe_allow_html=True,
    )
    st.code(json.dumps({k: v for k, v in vision.items() if not k.startswith("_")},
                        indent=2),
            language="json")

with cls_r:
    cls = vision.get("uas_class", "unknown")
    conf = float(vision.get("confidence", 0.0))
    intent = vision.get("inferred_intent", "unknown")
    rng_km = vision.get("estimated_range_km", 0.0)
    action = vision.get("recommended_action", "monitor")
    threat = ("LOW" if cls == "ambient"
              else "HIGH" if (cls == "swarm" or intent == "strike")
              else "MED")

    st.markdown("**Engagement summary**")
    st.markdown(
        f"<div class='metric-card'>"
        f"<div class='label'>UAS class</div>"
        f"<div class='val'>{cls}</div>"
        f"<div class='sub'>controller: <code>{vision.get('controller_signature_match','—')}</code> · "
        f"conf: {conf:.2f}</div></div>",
        unsafe_allow_html=True,
    )
    st.markdown(
        f"<div class='metric-card'>"
        f"<div class='label'>Inferred intent · range</div>"
        f"<div class='val'>{intent} · {rng_km} km</div>"
        f"<div class='sub'>threat level: <span class='threat-{threat}'>{threat}</span> · "
        f"recommended COA: <code>{action}</code></div></div>",
        unsafe_allow_html=True,
    )
    st.markdown(
        f"<div class='callout-strip' data-testid='eoc-callout'>"
        f"📡 EOC CALLOUT → {vision.get('EOC_callout_text','')}</div>",
        unsafe_allow_html=True,
    )
    st.caption(vision.get("rationale", ""))


# ─────────────────────────────────────────────────────────────────────────────
# Stage 4 — Hero engagement-brief LLM (cache-first)
# ─────────────────────────────────────────────────────────────────────────────
st.markdown("---")
st.markdown("### 5) CUAS Engagement Recommendation · Hero AI brief")
st.caption(
    "Cache-first. Pre-computed for all six sample spectrograms so the demo never "
    "blocks. Live regenerate uses the hero model (35-second watchdog, "
    "deterministic fallback)."
)

br_l, br_r = st.columns([0.62, 0.38])

with br_l:
    if "brief_for" not in st.session_state or st.session_state.get("brief_for") != active["id"]:
        cached_entry = cached_briefs.get(active["id"], {})
        st.session_state["brief_text"] = cached_entry.get(
            "engagement_brief",
            "No cached brief found for this capture. Click Regenerate to draft live."
        )
        st.session_state["brief_source"] = "cached"
        st.session_state["brief_for"] = active["id"]

    bcol1, bcol2 = st.columns([0.5, 0.5])
    regen = bcol1.button("Regenerate (live · hero model)",
                          type="primary", key="regen_brief")
    reload_c = bcol2.button("Reload cached", key="reload_brief")

    if reload_c:
        cached_entry = cached_briefs.get(active["id"], {})
        st.session_state["brief_text"] = cached_entry.get("engagement_brief", "")
        st.session_state["brief_source"] = "cached"

    if regen:
        payload = build_scenario_payload(active, features, baseline,
                                          vision={k: v for k, v in vision.items()
                                                  if not k.startswith("_")})
        with st.spinner("Hero model drafting CUAS Engagement Recommendation…"):
            text = engagement_brief(payload, model="gpt-5.4", timeout=35)
        st.session_state["brief_text"] = text
        st.session_state["brief_source"] = "live"

    src = st.session_state.get("brief_source", "cached")
    st.markdown(
        f"<div style='font-size:0.78rem;color:#7E7E7E;'>"
        f"Source: <span class='tag'>{src.upper()}</span></div>",
        unsafe_allow_html=True,
    )
    st.markdown(
        f"<div class='mis-panel' data-testid='engagement-brief'>"
        f"{st.session_state['brief_text']}</div>",
        unsafe_allow_html=True,
    )

with br_r:
    st.markdown("**Engagement options · ROE catalog**")
    for opt in engagement_options:
        # Tag class: PASSIVE / NON-KINETIC / KINETIC
        if opt["kinetic"]:
            tag_cls = "KINETIC"
            tag_label = "KINETIC"
        elif opt["rf_emission"]:
            tag_cls = "NON"
            tag_label = "NON-KINETIC"
        else:
            tag_cls = "PASSIVE"
            tag_label = "PASSIVE"
        recommended = (vision.get("recommended_action","") in opt["id"]
                        or opt["id"] in vision.get("recommended_action",""))
        star = " ★" if recommended else ""
        st.markdown(
            f"<div class='opt-row opt-{tag_cls}'>"
            f"<b style='color:#FFFFFF;'>{opt['name']}{star}</b> "
            f"<span class='tag'>{tag_label}</span><br>"
            f"<span style='color:#BDBDBD;font-size:0.82rem;'>"
            f"Authority: <code>{opt['authority_required']}</code></span><br>"
            f"<span style='color:#7E7E7E;font-size:0.78rem;'>{opt['roe_class']}</span>"
            f"</div>",
            unsafe_allow_html=True,
        )


# ─────────────────────────────────────────────────────────────────────────────
# RF identification database
# ─────────────────────────────────────────────────────────────────────────────
with st.expander("RF Identification Database — 30 known controller signatures",
                  expanded=False):
    st.dataframe(rf_db, hide_index=True, use_container_width=True, height=320)


# ─────────────────────────────────────────────────────────────────────────────
# Footer
# ─────────────────────────────────────────────────────────────────────────────
st.markdown(
    f"<div class='brand-footer'>"
    f"<span>CUAS-DETECT · Powered by Kamiwaza · 6 synthetic spectrograms · "
    f"{len(rf_db)} controller fingerprints · {len(engagement_options)} ROE-graded options</span>"
    f"<span>Real datasets: <i>DroneRF-B Spectra</i> + <i>DroneRC RF Signal</i> "
    f"(IEEE DataPort) · plug in via <code>data/load_real.py</code></span>"
    f"</div>",
    unsafe_allow_html=True,
)
