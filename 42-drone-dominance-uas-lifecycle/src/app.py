"""DRONE-DOMINANCE — Full UAS encounter lifecycle.

Streamlit single-page app on port 3042.

Demo path (cold-open → closer):
  1. Friendly drone planning — quantify your fleet, mission load
  2. Hostile UAS detection: three sensor modalities fuse (RF + thermal + visual)
  3. Engagement decision — ROE-graded options ladder
  4. Hero "UAS Encounter Brief" — full SITREP, cache-first
  5. Egocentric AAR — operator decision reviewed against doctrine

Run:
  streamlit run src/app.py --server.port 3042 --server.headless true \\
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
    triple_fuse,
    engagement_decision,
    encounter_brief,
    egocentric_aar,
    build_brief_payload,
)


APP_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = APP_DIR / "data"
SPECTRA_DIR = APP_DIR / "sample_spectra"
THERMAL_DIR = APP_DIR / "sample_thermal"
VISUAL_DIR = APP_DIR / "sample_visual"
AAR_DIR = APP_DIR / "xperience_aar_frames"
MANIFEST_PATH = DATA_DIR / "scenarios.json"
CACHE_PATH = DATA_DIR / "cached_briefs.json"
ENGAGEMENT_PATH = DATA_DIR / "engagement_options.json"
RF_DB_PATH = DATA_DIR / "rf_id_db.csv"
FLEET_PATH = DATA_DIR / "friendly_fleet.json"
AAR_FRAMES_PATH = DATA_DIR / "aar_frames.json"


st.set_page_config(
    page_title="DRONE-DOMINANCE — Full UAS Encounter Lifecycle",
    page_icon="🦅",
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
.fuse-strip {{
  display: grid; grid-template-columns: 1fr 1fr 1fr 1.2fr;
  gap: 10px; margin: 8px 0;
}}
.fuse-cell {{ background: var(--kw-surface2); border: 1px solid var(--kw-border);
  border-radius: 8px; padding: 10px 12px; }}
.fuse-cell.fused {{ border-left: 3px solid var(--kw-neon);
  background: linear-gradient(90deg, rgba(0,255,167,0.10), var(--kw-surface2));}}
.fuse-cell .lbl {{ color: var(--kw-muted); font-size: 0.74rem; text-transform: uppercase; letter-spacing:0.6px; }}
.fuse-cell .pval {{ color: var(--kw-neon); font-size: 1.5rem; font-weight: 700; font-family: ui-monospace, Menlo; }}
.fuse-cell .sub {{ color: #BDBDBD; font-size: 0.78rem; }}
.aar-card {{
  background: var(--kw-surface2); border: 1px solid var(--kw-border);
  border-left: 3px solid var(--kw-neon);
  border-radius: 8px; padding: 14px 16px; margin-top: 6px;
}}
</style>
"""
st.markdown(KAMIWAZA_CSS, unsafe_allow_html=True)


# ─────────────────────────────────────────────────────────────────────────────
# Header
# ─────────────────────────────────────────────────────────────────────────────
hdr_l, hdr_r = st.columns([0.66, 0.34])
with hdr_l:
    st.markdown(
        "<h1 data-testid='app-title'>DRONE-DOMINANCE "
        "<span class='tag'>Agent #42 · Tier A · Full UAS Encounter Lifecycle</span></h1>",
        unsafe_allow_html=True,
    )
    st.markdown(
        "<div style='color:#BDBDBD;font-size:0.95rem;'>"
        "Friendly fleet quantification · hostile RF + thermal + visual triple-"
        "fusion · ROE-graded engagement ladder · hero encounter brief · "
        "egocentric AAR. <i>The whole UAS-vs-FOB problem on one screen.</i></div>",
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
def load_fleet() -> dict:
    if FLEET_PATH.exists():
        return json.loads(FLEET_PATH.read_text())
    return {}


@st.cache_data(show_spinner=False)
def load_aar_frames() -> list[dict]:
    if AAR_FRAMES_PATH.exists():
        return json.loads(AAR_FRAMES_PATH.read_text())
    return []


@st.cache_data(show_spinner=False)
def load_scenarios_meta() -> dict[str, dict]:
    sys.path.insert(0, str(DATA_DIR))
    from generate import SCENARIOS  # noqa: WPS433
    return {s["id"]: s for s in SCENARIOS}


@st.cache_data(show_spinner=False)
def load_npy(npy_path: str) -> np.ndarray:
    return np.load(npy_path)


@st.cache_data(show_spinner=False)
def load_thermal_bboxes(path: str) -> list[dict]:
    return json.loads(Path(path).read_text())


manifest = load_manifest()
cached_briefs = load_cached_briefs()
engagement_options = load_engagement_options()
rf_db = load_rf_db()
fleet = load_fleet()
aar_frames = load_aar_frames()
scenarios_meta = load_scenarios_meta()


# ─────────────────────────────────────────────────────────────────────────────
# Sidebar — site context + Kamiwaza pitch
# ─────────────────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("### Site Context")
    st.markdown(
        "**Camp Pendleton — Bldg 22 perimeter sensor**  \n"
        "DTG: `271730ZAPR26` · Wind: `210/06KT` · Ceiling: `BKN 4500`  \n"
        "Civil airspace: `0.4 nm` · Friendly air active: `none`"
    )
    st.divider()
    st.markdown("### Encounter Pipeline")
    st.markdown(
        "1. **Friendly fleet** — visual quantification of own platforms  \n"
        "2. **RF · Thermal · Visual** — three multimodal calls in one workflow  \n"
        "3. **Bayesian fusion** — naïve-Bayes product across sensors  \n"
        "4. **Engagement decision** — ROE-graded options (`chat_json`)  \n"
        "5. **Hero brief** — `gpt-5.4`-class, 35 s, cache-first  \n"
        "6. **Egocentric AAR** — vision-language scoring of operator choice"
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
        "Set <code>KAMIWAZA_BASE_URL</code> → CUAS decisions stay in the SCIF. "
        "Zero code change.</div>",
        unsafe_allow_html=True,
    )
    st.divider()
    st.markdown("### RF ID Database")
    st.caption(f"{len(rf_db)} known controller signatures loaded")


# ─────────────────────────────────────────────────────────────────────────────
# 0) Friendly drone fleet — visual quantification
# ─────────────────────────────────────────────────────────────────────────────
st.markdown("### 0) Friendly fleet · AI Visual Quantification")
fleet_l, fleet_r = st.columns([0.62, 0.38])
with fleet_l:
    fleet_df = pd.DataFrame(fleet.get("platforms", []))
    if not fleet_df.empty:
        fleet_df = fleet_df[
            ["make", "model", "role", "count_total",
             "count_mission_ready", "battery_pack_pct_avg"]
        ]
        st.dataframe(fleet_df, hide_index=True, use_container_width=True, height=210)
    st.caption(fleet.get("visual_quantification_note", ""))
with fleet_r:
    total = sum(p["count_total"] for p in fleet.get("platforms", []))
    ready = sum(p["count_mission_ready"] for p in fleet.get("platforms", []))
    st.markdown(
        f"<div class='metric-card'><div class='label'>Friendly platforms</div>"
        f"<div class='val'>{ready} / {total}</div>"
        f"<div class='sub'>mission-ready / total</div></div>",
        unsafe_allow_html=True,
    )
    st.markdown(
        f"<div class='metric-card'><div class='label'>Today's mission load</div>"
        f"<div class='val' style='font-size:0.95rem;'>"
        f"{fleet.get('mission_load_today','')}</div></div>",
        unsafe_allow_html=True,
    )


st.markdown("---")


# ─────────────────────────────────────────────────────────────────────────────
# 1) Pick a hostile UAS scenario
# ─────────────────────────────────────────────────────────────────────────────
st.markdown("### 1) Hostile UAS scenario · pick one (six pre-loaded)")
options = {f"{m['title']}": m for m in manifest}
chosen_label = st.radio(
    "Sample threat scenarios",
    list(options.keys()),
    index=0,
    key="scenario_pick",
    horizontal=True,
)
chosen = options[chosen_label]
chosen_meta = scenarios_meta.get(chosen["id"], chosen)

# load all three sensor frames
rf_arr = load_npy(str(APP_DIR / chosen["rf_npy"]))
thm_gray = load_npy(str(APP_DIR / chosen["thermal_npy"]))
thm_bboxes = load_thermal_bboxes(str(APP_DIR / chosen["thermal_bboxes"]))
rf_png_path = APP_DIR / chosen["rf_png"]
thm_png_path = APP_DIR / chosen["thermal_png"]
vis_png_path = APP_DIR / chosen["visual_png"]


# ─────────────────────────────────────────────────────────────────────────────
# 2) Three sensor modalities — side by side
# ─────────────────────────────────────────────────────────────────────────────
st.markdown("### 2) Three sensor modalities · side by side")
m1, m2, m3 = st.columns(3)
with m1:
    st.markdown("**RF · Spectrogram**")
    fig = go.Figure(data=go.Heatmap(
        z=rf_arr[::-1],
        colorscale=[
            [0.00, "#0A140C"], [0.25, "#0DCC8A"], [0.55, "#00FFA7"],
            [0.80, "#F2C94C"], [1.00, "#FF4D4D"],
        ],
        showscale=False,
    ))
    fig.update_layout(
        plot_bgcolor=BRAND["bg"], paper_bgcolor=BRAND["bg"],
        font_color="#E5E5E5", height=190,
        margin=dict(l=10, r=10, t=10, b=10),
        xaxis=dict(showticklabels=False, gridcolor=BRAND["border"]),
        yaxis=dict(showticklabels=False, gridcolor=BRAND["border"]),
    )
    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
    st.caption(f"{chosen_meta.get('band_ghz','?')} GHz · "
               f"hop={chosen_meta.get('hop_period_ms','?')}ms · "
               f"snr={chosen_meta.get('snr_db','?')}dB")

with m2:
    st.markdown("**Thermal IR · HIT-UAV-shape**")
    st.image(str(thm_png_path), use_container_width=True)
    st.caption(f"{len(thm_bboxes)} hot-blob detection(s) · alt~"
               f"{chosen_meta.get('ground_truth_alt_m','?')}m")

with m3:
    st.markdown("**Visual EO · Drone-Dataset-shape**")
    st.image(str(vis_png_path), use_container_width=True)
    st.caption(f"scene: {chosen_meta.get('visual_kind','?')} · "
               f"GT range ~{chosen_meta.get('ground_truth_range_km','?')}km")


# ─────────────────────────────────────────────────────────────────────────────
# 3) Triple fusion — three multimodal calls + Bayesian product
# ─────────────────────────────────────────────────────────────────────────────
st.markdown("### 3) Triple-fusion · three multimodal calls in one workflow")
st.caption(
    "Three multimodal AI calls in parallel-watchdog style: RF spectrogram-as-"
    "image, thermal IR + bbox sidecar, visual EO. Each emits p(uas_present); "
    "fused via naïve-Bayes product. Cache-first; live regenerates run with "
    "per-call timeouts so no single sensor stalls the workflow."
)

# Initialize fused state from cache
if ("fuse_for" not in st.session_state
        or st.session_state.get("fuse_for") != chosen["id"]):
    cached_entry = cached_briefs.get(chosen["id"], {})
    cached_fused = cached_entry.get("triple_fusion", {})
    if cached_fused:
        # Inject features into the fused dict so downstream pieces have them
        cached_fused = {
            **cached_fused,
            "_features": {
                "rf": cached_entry.get("rf_features", {}),
                "thermal": cached_entry.get("thermal_features", {}),
                "visual": cached_entry.get("visual_features", {}),
            },
            "_per_modality_json": cached_entry.get("triple_fusion", {}).get("_per_modality_json", {}),
            "_source": "cached",
        }
    st.session_state["fused"] = cached_fused
    st.session_state["fuse_for"] = chosen["id"]
    st.session_state["decision"] = cached_briefs.get(chosen["id"], {}).get("engagement_decision", {})
    st.session_state["decision_source"] = "cached"
    st.session_state["brief_text"] = cached_briefs.get(chosen["id"], {}).get(
        "encounter_brief",
        "(no cached brief; click Regenerate below)"
    )
    st.session_state["brief_source"] = "cached"

fb1, fb2 = st.columns([0.5, 0.5])
run_fuse = fb1.button("Run triple-fusion (live · 3 multimodal calls)",
                       type="primary", key="run_fuse_btn")
use_cache = fb2.button("Use cached fusion", key="use_cache_btn")

if run_fuse:
    with st.spinner("Routing through Inference Mesh — RF + thermal + visual…"):
        fused = triple_fuse(
            chosen_meta,
            rf_arr=rf_arr, rf_png=rf_png_path,
            thm_gray=thm_gray, thm_bboxes=thm_bboxes, thm_png=thm_png_path,
            vis_png=vis_png_path,
            timeout=30,
        )
        fused["_source"] = "live"
        st.session_state["fused"] = fused
        # decision auto-runs after fuse
        st.session_state["decision"] = engagement_decision(chosen_meta, fused, timeout=20)
        st.session_state["decision_source"] = "live"

if use_cache:
    st.session_state.pop("fuse_for", None)
    st.rerun()

fused = st.session_state.get("fused", {}) or {}
decision = st.session_state.get("decision", {}) or {}

p_per = fused.get("confidence_per_modality", {"rf": 0, "thermal": 0, "visual": 0})
fc = fused.get("fused_confidence", 0.0)
contributors = ", ".join(fused.get("contributing_sensors", []))
src_fuse = fused.get("_source", "cached")

st.markdown(
    f"<div class='fuse-strip'>"
    f"<div class='fuse-cell'><div class='lbl'>RF · spectrogram</div>"
    f"<div class='pval'>{p_per.get('rf', 0):.2f}</div>"
    f"<div class='sub'>p(uas_present)</div></div>"
    f"<div class='fuse-cell'><div class='lbl'>Thermal · IR</div>"
    f"<div class='pval'>{p_per.get('thermal', 0):.2f}</div>"
    f"<div class='sub'>p(uas_present)</div></div>"
    f"<div class='fuse-cell'><div class='lbl'>Visual · EO</div>"
    f"<div class='pval'>{p_per.get('visual', 0):.2f}</div>"
    f"<div class='sub'>p(uas_present)</div></div>"
    f"<div class='fuse-cell fused'><div class='lbl'>Fused (Bayes-product)</div>"
    f"<div class='pval'>{fc:.2f}</div>"
    f"<div class='sub'>contributing sensors: {contributors or '—'}</div></div>"
    f"</div>",
    unsafe_allow_html=True,
)

st.markdown(
    f"<div style='font-size:0.78rem;color:#7E7E7E;'>"
    f"Source: <span class='tag'>{src_fuse.upper()}</span> · method: "
    f"<code>{fused.get('fusion_method','—')}</code></div>",
    unsafe_allow_html=True,
)

callout_class = ("LOW" if fused.get("detection_class") == "ambient"
                 else "HIGH" if (fused.get("detection_class") == "swarm"
                                  or fused.get("inferred_intent") == "strike")
                 else "MED")
st.markdown(
    f"<div class='callout-strip' data-testid='fuse-callout'>"
    f"📡 FUSED → {fused.get('detection_class','?').upper()} | "
    f"{fused.get('controller_signature_match','?')} | "
    f"~{fused.get('estimated_range_km','?')}km @ "
    f"~{fused.get('estimated_alt_m','?')}m | "
    f"intent={fused.get('inferred_intent','?')} | "
    f"<span class='threat-{callout_class}'>{callout_class}</span>"
    f"</div>",
    unsafe_allow_html=True,
)

# Per-modality JSON expander
with st.expander("Per-modality classifier JSON (3 multimodal calls)", expanded=False):
    per = fused.get("_per_modality_json", {})
    j1, j2, j3 = st.columns(3)
    with j1:
        st.markdown("**RF**")
        st.code(json.dumps(per.get("rf", {}), indent=2), language="json")
    with j2:
        st.markdown("**Thermal**")
        st.code(json.dumps(per.get("thermal", {}), indent=2), language="json")
    with j3:
        st.markdown("**Visual**")
        st.code(json.dumps(per.get("visual", {}), indent=2), language="json")


# ─────────────────────────────────────────────────────────────────────────────
# 4) Engagement decision · ROE-graded options
# ─────────────────────────────────────────────────────────────────────────────
st.markdown("---")
st.markdown("### 4) Engagement decision · ROE-graded option ladder")
st.caption(
    "`chat_json` graded options: monitor / EW jam (sector or omni) / spoof-GPS / "
    "kinetic / link takeover / SkyTracker log / escalate-FOC. Authority required "
    "is shown per option — the OOD never picks a kinetic option without seeing "
    "the rule-set."
)
e_l, e_r = st.columns([0.55, 0.45])
with e_l:
    rec_name = decision.get("recommended_option_name", "—")
    rec_tag = decision.get("recommended_tag", "—")
    rec_rationale = decision.get("recommended_rationale", "")
    threat = ("LOW" if fused.get("detection_class") == "ambient"
              else "HIGH" if (fused.get("detection_class") == "swarm"
                                or fused.get("inferred_intent") == "strike")
              else "MED")
    st.markdown(
        f"<div class='metric-card'><div class='label'>Recommended COA</div>"
        f"<div class='val' style='font-size:1.15rem;'>{rec_name}</div>"
        f"<div class='sub'>tag: <span class='tag'>{rec_tag}</span> · "
        f"threat level: <span class='threat-{threat}'>{threat}</span></div></div>",
        unsafe_allow_html=True,
    )
    st.markdown(
        f"<div class='callout-strip' data-testid='engagement-callout'>"
        f"⚡ {rec_rationale}</div>",
        unsafe_allow_html=True,
    )
    st.caption(
        f"ROE floor: {decision.get('ROE_floor','?')} · "
        f"ROE ceiling: {decision.get('ROE_ceiling','?')} · "
        f"source: {st.session_state.get('decision_source','cached').upper()}"
    )

with e_r:
    st.markdown("**Top 5 graded options**")
    for opt in (decision.get("options_graded") or [])[:5]:
        tag_cls = ("KINETIC" if opt.get("tag") == "KINETIC"
                    else "NON" if opt.get("tag") == "NON-KINETIC"
                    else "PASSIVE")
        score = float(opt.get("score", 0.0))
        st.markdown(
            f"<div class='opt-row opt-{tag_cls}'>"
            f"<b style='color:#FFFFFF;'>{opt.get('name','?')}</b> "
            f"<span class='tag'>{opt.get('tag','?')}</span>"
            f"<span style='color:#00FFA7;float:right;font-family:ui-monospace;'>"
            f"score {score:.2f}</span><br>"
            f"<span style='color:#BDBDBD;font-size:0.82rem;'>Authority: "
            f"<code>{opt.get('authority_required','?')}</code></span><br>"
            f"<span style='color:#7E7E7E;font-size:0.78rem;'>"
            f"{opt.get('rationale','')}</span>"
            f"</div>",
            unsafe_allow_html=True,
        )


# ─────────────────────────────────────────────────────────────────────────────
# 5) Hero "UAS Encounter Brief" — full SITREP, cache-first
# ─────────────────────────────────────────────────────────────────────────────
st.markdown("---")
st.markdown("### 5) UAS Encounter Brief · Hero AI · cache-first")
st.caption(
    "Pre-computed for all six scenarios so the demo never blocks. Live "
    "regenerate uses the hero model (35-second wall-clock watchdog, "
    "deterministic fallback). Cites only authorized references "
    "(10 USC 130i · DoDD 3000.09 · JCO-CUAS · JP 3-01 · MARADMIN 131/26)."
)

br_l, br_r = st.columns([0.62, 0.38])
with br_l:
    bb1, bb2 = st.columns([0.5, 0.5])
    regen = bb1.button("Regenerate (live · hero model)",
                        type="primary", key="regen_brief_btn")
    reload_c = bb2.button("Reload cached", key="reload_brief_btn")

    if reload_c:
        cached_entry = cached_briefs.get(chosen["id"], {})
        st.session_state["brief_text"] = cached_entry.get("encounter_brief", "")
        st.session_state["brief_source"] = "cached"

    if regen:
        payload = build_brief_payload(chosen_meta, fused, decision)
        with st.spinner("Hero model drafting UAS Encounter Brief…"):
            text = encounter_brief(payload, timeout=35)
        st.session_state["brief_text"] = text
        st.session_state["brief_source"] = "live"

    src_b = st.session_state.get("brief_source", "cached")
    st.markdown(
        f"<div style='font-size:0.78rem;color:#7E7E7E;'>"
        f"Source: <span class='tag'>{src_b.upper()}</span></div>",
        unsafe_allow_html=True,
    )
    st.markdown(
        f"<div class='mis-panel' data-testid='encounter-brief'>"
        f"{st.session_state.get('brief_text','')}</div>",
        unsafe_allow_html=True,
    )

with br_r:
    st.markdown("**Ground truth (oracle)**")
    gt = chosen_meta
    st.markdown(
        f"<div class='metric-card'>"
        f"<div class='label'>Class · make/model</div>"
        f"<div class='val' style='font-size:1.05rem;'>{gt.get('uas_class','?')}</div>"
        f"<div class='sub'>{gt.get('make_model','?')} · "
        f"protocol: <code>{gt.get('protocol','?')}</code></div></div>",
        unsafe_allow_html=True,
    )
    st.markdown(
        f"<div class='metric-card'>"
        f"<div class='label'>Range · altitude · intent</div>"
        f"<div class='val' style='font-size:1.05rem;'>"
        f"{gt.get('ground_truth_range_km','?')} km · "
        f"{gt.get('ground_truth_alt_m','?')} m</div>"
        f"<div class='sub'>intent: <code>{gt.get('intent_hint','?')}</code></div>"
        f"</div>",
        unsafe_allow_html=True,
    )


# ─────────────────────────────────────────────────────────────────────────────
# 6) Egocentric AAR · Xperience-10M-shape
# ─────────────────────────────────────────────────────────────────────────────
st.markdown("---")
st.markdown("### 6) Egocentric AAR · Xperience-10M-shape · vision-language scoring")
st.caption(
    "After the engagement, the operator's helmet-cam still + their typed "
    "decision are scored by the multimodal model against the doctrine "
    "reference. SNCO-tonal hot-wash: classify (correct / tactical / hesitation "
    "/ risky), score 0-100, write feedback."
)

aar_pick_l, aar_pick_r = st.columns([0.4, 0.6])
with aar_pick_l:
    frame_options = {f["title"]: f for f in aar_frames}
    aar_label = st.selectbox(
        "Egocentric POV",
        list(frame_options.keys()),
        index=0,
        key="aar_pick",
    )
    aar_frame = frame_options[aar_label]
    aar_png_path = AAR_DIR / f"{aar_frame['id']}.png"
    if aar_png_path.exists():
        st.image(str(aar_png_path), use_container_width=True)
    st.caption(f"Doctrine: {aar_frame['doctrine_reference']}")

with aar_pick_r:
    st.markdown("**Operator's typed decision**")
    default_choice = decision.get("recommended_option_name", "Track + log only")
    operator_choice = st.text_input(
        "What did you do? (free-text)",
        value=default_choice,
        key="aar_op_choice",
    )
    score_btn = st.button("Score against doctrine (live · multimodal)",
                          type="primary", key="aar_score_btn")
    if "aar_eval" not in st.session_state or st.session_state.get("aar_for") != aar_frame["id"]:
        # baseline pre-fill so the panel never shows blank
        from agent import _baseline_aar  # noqa: WPS433
        st.session_state["aar_eval"] = _baseline_aar(
            aar_frame, default_choice,
            decision.get("recommended_option_name", ""), fused,
        )
        st.session_state["aar_for"] = aar_frame["id"]

    if score_btn:
        with st.spinner("Multimodal AAR coach scoring helmet-cam still…"):
            ev = egocentric_aar(aar_frame, operator_choice, fused, decision,
                                 png_path=aar_png_path, timeout=25)
        st.session_state["aar_eval"] = ev

    ev = st.session_state.get("aar_eval", {})
    cls = ev.get("decision_classified_as", "—")
    score = ev.get("score_0_100", 0)
    badge_color = ("#7FE5A1" if cls == "doctrinally_correct"
                    else "#F2C94C" if cls == "tactical"
                    else "#FF4D4D" if cls == "risky"
                    else "#BDBDBD")
    st.markdown(
        f"<div class='aar-card'>"
        f"<div style='display:flex;justify-content:space-between;align-items:center;'>"
        f"<span style='color:{badge_color};font-weight:700;text-transform:uppercase;'>"
        f"{cls.replace('_',' ')}</span>"
        f"<span style='color:#00FFA7;font-family:ui-monospace;font-size:1.4rem;font-weight:700;'>"
        f"{score}/100</span></div>"
        f"<div style='color:#BDBDBD;font-size:0.84rem;margin-top:6px;'>"
        f"<b>Doctrine:</b> {ev.get('doctrine_reference','?')}</div>"
        f"<div style='color:#E5E5E5;font-size:0.92rem;margin-top:8px;'>"
        f"<b>Consequence:</b> {ev.get('consequences_simulated','?')}</div>"
        f"<div style='color:#E5E5E5;font-size:0.92rem;margin-top:6px;'>"
        f"<b>Coaching:</b> {ev.get('coaching_feedback','?')}</div>"
        f"<div style='color:#7E7E7E;font-size:0.82rem;margin-top:6px;'>"
        f"<b>Next:</b> {ev.get('next_iteration','?')}</div>"
        f"<div style='color:#7E7E7E;font-size:0.74rem;margin-top:8px;'>"
        f"source: <span class='tag'>{ev.get('_source','baseline').upper()}</span></div>"
        f"</div>",
        unsafe_allow_html=True,
    )


# ─────────────────────────────────────────────────────────────────────────────
# RF identification database + ROE catalog
# ─────────────────────────────────────────────────────────────────────────────
with st.expander("RF Identification Database — 30 known controller signatures",
                  expanded=False):
    st.dataframe(rf_db, hide_index=True, use_container_width=True, height=320)

with st.expander("ROE Engagement Catalog — 8 options, full notes", expanded=False):
    for opt in engagement_options:
        tag = ("KINETIC" if opt["kinetic"]
                else "NON-KINETIC" if opt["rf_emission"]
                else "PASSIVE")
        st.markdown(
            f"**{opt['name']}** — `{tag}` · authority: `{opt['authority_required']}`  \n"
            f"_{opt['roe_class']}_  \n"
            f"<span style='color:#7E7E7E;font-size:0.85rem;'>{opt['notes']}</span>",
            unsafe_allow_html=True,
        )


# ─────────────────────────────────────────────────────────────────────────────
# Footer
# ─────────────────────────────────────────────────────────────────────────────
st.markdown(
    f"<div class='brand-footer'>"
    f"<span>DRONE-DOMINANCE · Powered by Kamiwaza · 6 scenarios × 3 sensor "
    f"modalities · {len(rf_db)} RF fingerprints · "
    f"{len(engagement_options)} ROE-graded options · "
    f"{len(aar_frames)} egocentric AAR frames</span>"
    f"<span>Real-data plug-in: Drone Dataset (UAV) · HIT-UAV · DroneRF-B · "
    f"DroneRC · Xperience-10M (see <code>data/load_real.py</code>)</span>"
    f"</div>",
    unsafe_allow_html=True,
)
