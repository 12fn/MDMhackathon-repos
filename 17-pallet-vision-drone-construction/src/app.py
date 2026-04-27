"""PALLET-VISION — AI Visual Quantification Engine for USMC LOGCOM.

Streamlit operator console. Pick (or upload) a single still of staged cargo;
one click fires a multimodal vision-language call that returns a strict-JSON
quantification (pallets visible, type, weight, lift requirement). A second
narrator call writes a 4-bullet Loadmaster Brief grounded in the real
platform-spec table.

Run:
    streamlit run src/app.py --server.port 3017
"""
from __future__ import annotations

import csv
import json
import sys
import time
from io import BytesIO
from pathlib import Path

import pandas as pd
import streamlit as st
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
REPO_ROOT = ROOT.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from shared.kamiwaza_client import BRAND  # noqa: E402

from src.vision import quantify, loadmaster_brief  # noqa: E402
from data.load_real import list_real_samples  # noqa: E402

DATA_DIR = ROOT / "data"
SAMPLES_DIR = ROOT / "sample_images"
MANIFEST = DATA_DIR / "sample_manifest.json"
CACHED_BRIEFS = DATA_DIR / "cached_briefs.json"
PLATFORM_SPECS_CSV = DATA_DIR / "platform_specs.csv"


st.set_page_config(
    page_title="PALLET-VISION — AI Visual Quantification Engine",
    page_icon="◆",
    layout="wide",
    initial_sidebar_state="expanded",
)


# ----------------------------- Theme (Kamiwaza dark) ----------------------------
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
      .pv-hero {{
        padding: 18px 24px;
        background: linear-gradient(120deg, var(--surface), var(--bg) 55%, #0a1f15 100%);
        border: 1px solid var(--border);
        border-left: 4px solid var(--primary);
        border-radius: 8px;
        margin-bottom: 18px;
      }}
      .pv-hero h1 {{
        margin: 0 0 4px 0;
        font-size: 30px;
        letter-spacing: 0.5px;
        color: var(--neon);
      }}
      .pv-hero .tag {{ color: var(--text_dim); font-size: 13px; }}
      .pv-card {{
        background: var(--surface);
        border: 1px solid var(--border);
        border-radius: 6px;
        padding: 14px 18px;
        margin-bottom: 10px;
      }}
      .pv-card h3 {{
        margin: 0 0 8px 0;
        color: var(--primary);
        font-size: 13px;
        letter-spacing: 1px;
        text-transform: uppercase;
      }}
      .pv-pill {{
        display: inline-block; padding: 3px 10px; border-radius: 999px;
        font-size: 11px; font-weight: 600; letter-spacing: 0.7px; text-transform: uppercase;
        border: 1px solid var(--border);
      }}
      .pill-green  {{ background: #06281c; color: var(--neon); border-color: var(--primary); }}
      .pill-amber  {{ background: #2b1d05; color: #ffb347; border-color: #ffb34740; }}
      .pill-red    {{ background: #2a0d10; color: #ff6b6b; border-color: #ff6b6b40; }}
      .pv-brief {{
        background: linear-gradient(120deg, #06281c, var(--surface) 80%);
        border: 1px solid var(--primary);
        border-left: 4px solid var(--neon);
        border-radius: 6px;
        padding: 16px 20px;
      }}
      .pv-brief h2 {{ margin: 0 0 8px 0; color: var(--neon); font-size: 18px; }}
      .pv-tool {{
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
      .pv-tool .toolname {{ color: var(--neon); }}
      .pv-footer {{
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
    </style>
    """,
    unsafe_allow_html=True,
)


# ------------------------------- Cached resources -------------------------------
@st.cache_data
def load_manifest() -> list[dict]:
    if not MANIFEST.exists():
        return []
    return json.loads(MANIFEST.read_text())


@st.cache_data
def load_cached_briefs() -> dict:
    if not CACHED_BRIEFS.exists():
        return {}
    try:
        return json.loads(CACHED_BRIEFS.read_text())
    except Exception:
        return {}


@st.cache_data
def load_platform_specs() -> pd.DataFrame:
    if not PLATFORM_SPECS_CSV.exists():
        return pd.DataFrame()
    return pd.read_csv(PLATFORM_SPECS_CSV)


def platform_specs_text(df: pd.DataFrame) -> str:
    lines = []
    for _, r in df.iterrows():
        lines.append(
            f"- {r['platform']} ({r['category']}): {int(r['pallets_463l'])} 463L pallets, "
            f"max {int(r['max_payload_kg'])} kg, cube {float(r['internal_cube_m3']):.1f} m^3. "
            f"{r['notes']}"
        )
    return "\n".join(lines)


# ------------------------------------ Header ------------------------------------
st.markdown(
    """
    <div class="pv-hero">
      <h1>PALLET-VISION</h1>
      <div class="tag">AI Visual Quantification Engine &nbsp;·&nbsp;
      Convert images of physical goods into accurate estimates of palletization
      and transportation requirements &nbsp;·&nbsp;
      USMC LOGCOM &nbsp;·&nbsp; AI Forum Hackathon 2026</div>
    </div>
    """,
    unsafe_allow_html=True,
)


manifest = load_manifest()
cached = load_cached_briefs()
specs_df = load_platform_specs()
specs_text = platform_specs_text(specs_df) if not specs_df.empty else ""

# Real-data plug-in: prepend if REAL_DATA_PATH is set
real_paths = []
try:
    real_paths = list_real_samples()
except NotImplementedError as e:
    st.sidebar.warning(str(e))


# ------------------------------------ Sidebar -----------------------------------
with st.sidebar:
    st.markdown("### Sample Bank")
    st.caption("Pick a still, or upload your own warehouse / dock / drone frame.")

    sample_options: list[tuple[str, Path, dict | None]] = []
    for entry in manifest:
        sample_options.append((
            f"{entry['id']} · {entry['title']}",
            ROOT / entry["local_path"],
            entry,
        ))
    for p in real_paths:
        sample_options.append((f"REAL · {p.name}", p, None))

    if sample_options:
        labels = [s[0] for s in sample_options]
        sel_label = st.radio("Sample", labels, label_visibility="collapsed", index=0)
        sel_idx = labels.index(sel_label)
        sel_label, sel_path, sel_entry = sample_options[sel_idx]
    else:
        st.error("No sample images found. Run `python data/generate.py` first.")
        sel_label, sel_path, sel_entry = None, None, None

    uploaded = st.file_uploader("Or upload (JPG/PNG)", type=["jpg", "jpeg", "png"])

    st.markdown("---")
    run_btn = st.button("RUN QUANTIFICATION", use_container_width=True)
    regen_btn = st.button("REGENERATE (live multimodal call)", use_container_width=True)

    st.markdown("---")
    st.markdown("### AI Engine")
    st.caption("Kamiwaza-deployed multimodal model · vision + narrator chain")

    st.markdown("### Deployment Mode")
    st.markdown(
        """
        <div class="pv-tool">
        <span class="toolname">$ env | grep KAMI</span><br/>
        # Today: cloud fallback; on-prem when BASE_URL set<br/>
        KAMIWAZA_BASE_URL=&lt;unset&gt;<br/><br/>
        # Tomorrow (one env-var swap):<br/>
        export KAMIWAZA_BASE_URL=<br/>
        &nbsp;&nbsp;https://kamiwaza.local/api/v1<br/>
        # 100% data containment.
        </div>
        """,
        unsafe_allow_html=True,
    )


# ----------------------------- Pick the source image ----------------------------
def _resolve_image() -> tuple[Image.Image | None, str, dict | None, str]:
    """Return (PIL image, source label, manifest entry or None, sample_id_for_cache)."""
    if uploaded is not None:
        try:
            img = Image.open(uploaded).convert("RGB")
            return img, f"upload · {uploaded.name}", None, ""
        except Exception as e:  # noqa: BLE001
            st.error(f"Could not open upload: {e}")
            return None, "", None, ""
    if sel_path is not None and sel_path.exists():
        img = Image.open(sel_path).convert("RGB")
        sample_id = sel_entry["id"] if sel_entry else ""
        return img, sel_label, sel_entry, sample_id
    return None, "", None, ""


img, src_label, entry, sample_id = _resolve_image()

# ------------------------------------ Layout ------------------------------------
left_col, right_col = st.columns([5, 6])

with left_col:
    st.markdown("### 1. Source frame")
    if img is not None:
        st.image(img, caption=src_label, use_container_width=True)
        st.markdown(f"<div class='pv-card'><b>Resolution:</b> {img.size[0]}x{img.size[1]} px  &nbsp;·&nbsp;  <b>Source:</b> {src_label}</div>", unsafe_allow_html=True)
        if entry:
            st.markdown(
                f"<div class='pv-card'><b>Scene type:</b> {entry['scene_type']}  &nbsp;·&nbsp;  "
                f"<b>Ground truth (synth):</b> {entry['true_pallets']} pallets, type "
                f"<code>{entry['pallet_type']}</code>, ~{entry['estimated_avg_kg_per_pallet']} kg avg.<br/>"
                f"<i>{entry['narration']}</i></div>",
                unsafe_allow_html=True,
            )
    else:
        st.info("Pick a sample or upload a frame.")

    st.markdown("### 4. Platform reference table")
    if not specs_df.empty:
        st.dataframe(specs_df, use_container_width=True, hide_index=True)


with right_col:
    st.markdown("### 2. Visual Quantification (multimodal hero call)")
    quant_slot = st.empty()
    json_slot = st.empty()

    st.markdown("### 3. Loadmaster Brief")
    brief_slot = st.empty()


# ---------------------------- Decide what to render -----------------------------
if "last_quant" not in st.session_state:
    st.session_state["last_quant"] = None
if "last_brief" not in st.session_state:
    st.session_state["last_brief"] = None
if "last_source" not in st.session_state:
    st.session_state["last_source"] = None
if "last_latency_ms" not in st.session_state:
    st.session_state["last_latency_ms"] = None

# Auto-load the cached brief whenever the user changes selection (cache-first).
needs_cache_load = (
    sample_id
    and sample_id in cached
    and st.session_state["last_source"] != f"cached:{sample_id}"
    and not regen_btn
)
if needs_cache_load:
    st.session_state["last_quant"] = cached[sample_id]["quant"]
    st.session_state["last_brief"] = cached[sample_id]["brief_md"]
    st.session_state["last_source"] = f"cached:{sample_id}"
    st.session_state["last_latency_ms"] = 0  # cached

# A live run is requested either by RUN (no cache for selection / upload) or REGENERATE.
needs_live_run = False
if regen_btn:
    needs_live_run = True
elif run_btn:
    if uploaded is not None or not sample_id or sample_id not in cached:
        needs_live_run = True
    # If sample is cached and user hits RUN, just show cache (handled above).

if needs_live_run and img is not None:
    with st.spinner("Multimodal model is quantifying the scene…"):
        t0 = time.time()
        quant = quantify(img, scene_hint=(entry["scene_type"] if entry else "operator-upload"))
        brief_md = loadmaster_brief(quant, specs_text)
        latency_ms = int((time.time() - t0) * 1000)
    st.session_state["last_quant"] = quant
    st.session_state["last_brief"] = brief_md
    st.session_state["last_source"] = f"live:{sample_id or 'upload'}"
    st.session_state["last_latency_ms"] = latency_ms


# ------------------------------------- Render ------------------------------------
quant = st.session_state.get("last_quant")
brief = st.session_state.get("last_brief")

if quant:
    pallets = int(quant.get("pallets_visible", 0) or 0)
    pallet_type = quant.get("pallet_type_estimate", "?")
    eff = float(quant.get("stacking_efficiency_pct", 0.0) or 0.0)
    vol = float(quant.get("estimated_volume_m3", 0.0) or 0.0)
    wt = float(quant.get("estimated_weight_kg", 0.0) or 0.0)
    conf = float(quant.get("confidence", 0.0) or 0.0)
    plan = quant.get("recommended_load_plan_brief", "")
    vehicles = quant.get("vehicles_required", []) or []
    constraints = quant.get("constraints_named", []) or []
    src = st.session_state.get("last_source", "")
    latency_ms = st.session_state.get("last_latency_ms", 0)

    # Headline metrics row
    with quant_slot.container():
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Pallets visible", f"{pallets}")
        m2.metric("Pallet type", pallet_type)
        m3.metric("Est. weight", f"{wt:,.0f} kg")
        m4.metric("Confidence", f"{conf*100:.0f}%")

        # Vehicles required card
        veh_rows = ""
        for v in vehicles:
            veh_rows += (
                f"<div style='padding:6px 0; border-bottom:1px dashed var(--border);'>"
                f"<span class='pv-pill pill-green'>{v.get('platform','?')}</span>"
                f"&nbsp;&nbsp;<b>x {v.get('count', 1)}</b>"
                f"&nbsp;&nbsp;<span style='color:var(--text_dim)'>load {float(v.get('load_pct', 0)):.0f}%</span>"
                f"</div>"
            )
        if not veh_rows:
            veh_rows = "<i>No platforms recommended — model returned an empty list.</i>"

        st.markdown(
            f"""
            <div class="pv-card">
              <h3>LIFT REQUIREMENT</h3>
              {veh_rows}
              <div style='color:var(--text_dim); font-size:12px; margin-top:10px;'>
                Stacking efficiency: <b>{eff:.0f}%</b>  ·  Cube est: <b>{vol:.1f} m³</b>  ·
                Source: <code>{src}</code>  ·  Latency: {latency_ms} ms
              </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        constraint_html = "".join(
            f"<li style='margin-bottom:4px; color:#cfd8dc;'>{c}</li>"
            for c in constraints
        )
        st.markdown(
            f"""
            <div class="pv-card">
              <h3>CONSTRAINTS NAMED BY MODEL</h3>
              <ul style='margin:0 0 0 18px; padding:0; font-size:13px;'>{constraint_html or '<li><i>none</i></li>'}</ul>
              <div style='color:var(--muted); font-size:12px; margin-top:8px;'>
                Recommended plan: <i>{plan or '—'}</i>
              </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    with json_slot.expander("Structured JSON (for downstream GCSS-MC / TC-AIMS integration)", expanded=False):
        st.json({k: v for k, v in quant.items() if not k.startswith("_")})
else:
    quant_slot.info("Run quantification to populate.")

if brief:
    brief_slot.markdown(
        f"<div class='pv-brief'>{brief}</div>",
        unsafe_allow_html=True,
    )
else:
    brief_slot.info("Loadmaster brief will appear once the quantification runs.")


# ----------------------------------- Footer -------------------------------------
st.markdown(
    f"""
    <div class="pv-footer">
      Real datasets cited: <strong>HIT-UAV</strong> (drone-overhead infrared, 2898 frames) &nbsp;·&nbsp;
      <strong>Moving objects in construction sites</strong> (10,013 images).
      Synthetic stand-in renders bundled so the demo runs offline.
      <br/>
      <strong style="color: {BRAND['primary']};">Powered by Kamiwaza.</strong>
      &nbsp;·&nbsp; Orchestration Without Migration. Execution Without Compromise.
    </div>
    """,
    unsafe_allow_html=True,
)
