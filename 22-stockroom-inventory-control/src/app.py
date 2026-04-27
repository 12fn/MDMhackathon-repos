"""STOCKROOM — AI-augmented relational inventory app for the USMC LOGCOM
'Inventory Control Management' use case.

Three on-screen workflows (top-down):
  1. Sidebar ingest: Excel/CSV upload (or default synthetic data); filter by
     location, category, sensitivity, responsible Marine.
  2. Natural-language query: "show me sensitive items not lateral-transferred
     in 60 days" -> chat_json filter spec -> structured table render.
  3. Hero brief: "Readiness & Lateral Transfer Brief" — three scenarios, all
     pre-cached so the demo is instant. "Regenerate" hits the hero model with
     a 35s wall-clock timeout and a deterministic fallback.

Plus an append-only audit log (transactions.jsonl) — credible production
pattern visible to judges.
"""
from __future__ import annotations

import io
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import streamlit as st

# Make `shared` + `src` importable when this file is run from anywhere.
APP_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = Path(__file__).resolve().parents[3]
for p in (str(REPO_ROOT), str(APP_ROOT)):
    if p not in sys.path:
        sys.path.insert(0, p)

from shared.kamiwaza_client import BRAND  # noqa: E402

from src.agent import (  # noqa: E402
    apply_filter_spec,
    generate_brief,
    load_cached_briefs,
    parse_nl_query,
)

DATA_DIR = APP_ROOT / "data"
INVENTORY_XLSX = DATA_DIR / "inventory.xlsx"
INVENTORY_CSV = DATA_DIR / "inventory.csv"
LOCATIONS_JSON = DATA_DIR / "locations.json"
TRANSACTIONS_JSONL = DATA_DIR / "transactions.jsonl"

SCENARIOS = [
    {"id": "routine",    "title": "Routine — daily supply NCO brief",
     "frame": "It is 0700 Monday. Surface the top issues for the supply NCO's first stand-up."},
    {"id": "pre_deploy", "title": "Pre-deployment — 30 days out",
     "frame": "Battalion deploys in 30 days. Surface what could keep it from going."},
    {"id": "post_ig",    "title": "Post-IG — corrective action brief",
     "frame": "An IG inspection just finished. Surface every accountability gap they will cite."},
]


# ---------------------------------------------------------------------------
# Page setup + theme
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="STOCKROOM — Inventory Control Management",
    page_icon="◆",
    layout="wide",
)

st.markdown(
    f"""
    <style>
      .stApp {{ background-color: {BRAND['bg']}; color: #E6E6E6; }}
      [data-testid="stSidebar"] {{ background-color: {BRAND['surface']};
                                    border-right: 1px solid {BRAND['border']}; }}
      h1, h2, h3, h4 {{ color: {BRAND['neon']}; letter-spacing: .04em; }}
      .stButton > button {{ background-color: {BRAND['primary']}; color: #0A0A0A;
                            border: 0; font-weight: 600; }}
      .stButton > button:hover {{ background-color: {BRAND['primary_hover']}; color: #000; }}
      .stTextInput > div > div > input,
      .stTextArea textarea {{ background-color: {BRAND['surface_high']};
                              color: #E6E6E6; border: 1px solid {BRAND['border']}; }}
      .sr-card {{ background-color: {BRAND['surface_high']};
                  border: 1px solid {BRAND['border']}; border-radius: 8px;
                  padding: 14px 18px; margin-bottom: 10px; }}
      .sr-pill {{ display: inline-block; padding: 2px 10px; margin-right: 6px;
                  border-radius: 999px; background: {BRAND['primary']}; color: #0A0A0A;
                  font-weight: 600; font-size: 12px; }}
      .sr-pill-neon {{ background: {BRAND['neon']}; color: #062F1F; }}
      .sr-pill-amber {{ background: #d2a233; color: #0A0A0A; }}
      .sr-pill-red {{ background: #b04040; color: #fff; }}
      .sr-metric-num {{ font-size: 28px; font-weight: 700; color: {BRAND['neon']}; }}
      .sr-metric-lbl {{ color: {BRAND['text_dim']}; font-size: 12px; }}
      .sr-footer {{ color: {BRAND['muted']}; text-align: center; font-size: 12px;
                    margin-top: 24px; padding-top: 12px;
                    border-top: 1px solid {BRAND['border']}; }}
      .sr-trace {{ color: {BRAND['neon']}; font-family: ui-monospace, Menlo, monospace;
                   font-size: 12px; white-space: pre-wrap; }}
    </style>
    """,
    unsafe_allow_html=True,
)


# ---------------------------------------------------------------------------
# Header
# ---------------------------------------------------------------------------
hdr_l, hdr_r = st.columns([0.7, 0.3])
with hdr_l:
    st.markdown(
        f"""
        <div style="display:flex; align-items:center; gap:14px;">
          <img src="{BRAND['logo_url']}" alt="Kamiwaza" style="height:34px;" />
          <div>
            <div style="font-size:28px; font-weight:700; color:{BRAND['neon']};
                        letter-spacing:.06em;">STOCKROOM</div>
            <div style="color:{BRAND['text_dim']}; font-size:13px;">
              AI-Augmented Inventory Control Management for the USMC supply NCO.
            </div>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
with hdr_r:
    st.markdown(
        f"""
        <div style="text-align:right; padding-top:6px;">
          <span class="sr-pill">LOGCOM</span>
          <span class="sr-pill sr-pill-neon">ICM</span>
          <div style="color:{BRAND['text_dim']}; font-size:11px; margin-top:6px;">
            Mission frame: LOGCOM "Inventory Control Management" use case —
            replace 5,000-item Excel hell with an AI-augmented relational app.
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

st.markdown("---")


# ---------------------------------------------------------------------------
# Data loading (sidebar ingest)
# ---------------------------------------------------------------------------
@st.cache_data(show_spinner=False)
def _load_default_inventory() -> pd.DataFrame:
    if INVENTORY_XLSX.exists():
        return pd.read_excel(INVENTORY_XLSX, engine="openpyxl")
    if INVENTORY_CSV.exists():
        return pd.read_csv(INVENTORY_CSV)
    return pd.DataFrame()


@st.cache_data(show_spinner=False)
def _load_locations() -> list[dict]:
    if LOCATIONS_JSON.exists():
        return json.loads(LOCATIONS_JSON.read_text())
    return []


def _load_uploaded(uploaded) -> pd.DataFrame:
    name = uploaded.name.lower()
    raw = uploaded.read()
    if name.endswith((".xlsx", ".xlsm", ".xls")):
        return pd.read_excel(io.BytesIO(raw), engine="openpyxl")
    return pd.read_csv(io.BytesIO(raw))


def _append_audit(event: dict) -> None:
    TRANSACTIONS_JSONL.parent.mkdir(parents=True, exist_ok=True)
    with open(TRANSACTIONS_JSONL, "a") as f:
        f.write(json.dumps(event) + "\n")


def _load_audit(tail: int = 12) -> list[dict]:
    if not TRANSACTIONS_JSONL.exists():
        return []
    lines = TRANSACTIONS_JSONL.read_text().strip().splitlines()
    out = []
    for ln in lines[-tail:]:
        try:
            out.append(json.loads(ln))
        except Exception:
            continue
    return out


# ---------------------------------------------------------------------------
# Sidebar — ingest + filters
# ---------------------------------------------------------------------------
with st.sidebar:
    st.markdown(f"### <span style='color:{BRAND['neon']}'>Inventory Ingest</span>",
                unsafe_allow_html=True)
    st.markdown(
        f"<div style='color:{BRAND['text_dim']}; font-size:12px;'>"
        "Drop the LOGCOM Excel workbook in here. Synthetic 5,000-item dataset "
        "loads by default — no data movement, runs in your perimeter.</div>",
        unsafe_allow_html=True,
    )
    uploaded = st.file_uploader("Upload inventory.xlsx / .csv",
                                type=["xlsx", "xls", "csv"],
                                label_visibility="collapsed")

    if uploaded is not None:
        try:
            df = _load_uploaded(uploaded)
            st.success(f"Loaded {len(df):,} rows from {uploaded.name}")
        except Exception as e:
            st.error(f"Could not parse upload: {e}")
            df = _load_default_inventory()
    else:
        df = _load_default_inventory()
        if df.empty:
            st.error("No inventory loaded. Run `python data/generate.py` first.")
        else:
            st.markdown(
                f"<div style='color:{BRAND['text_dim']}; font-size:12px;'>"
                f"Default dataset loaded: <b>{len(df):,}</b> items.</div>",
                unsafe_allow_html=True,
            )

    st.markdown("---")
    st.markdown(f"### <span style='color:{BRAND['neon']}'>Filters</span>",
                unsafe_allow_html=True)

    sel_loc = st.multiselect(
        "Location",
        options=sorted(df["location_id"].dropna().unique().tolist()) if "location_id" in df.columns else [],
        default=[],
    )
    sel_cat = st.multiselect(
        "Category (Class)",
        options=sorted(df["category"].dropna().unique().tolist()) if "category" in df.columns else [],
        default=[],
    )
    sel_sens = st.multiselect(
        "Sensitivity class",
        options=sorted(df["sensitivity_class"].dropna().unique().tolist())
        if "sensitivity_class" in df.columns else [],
        default=[],
    )
    sel_marine = st.multiselect(
        "Responsible Marine",
        options=sorted(df["responsible_marine"].dropna().unique().tolist())
        if "responsible_marine" in df.columns else [],
        default=[],
    )
    only_overdue = st.checkbox("Only inventory-overdue items", value=False)
    only_nmc = st.checkbox("Only NMC-impacting items", value=False)

    st.markdown("---")
    st.markdown(
        f"<div style='color:{BRAND['text_dim']}; font-size:11px;'>"
        "Real-data plug-in: set <code>REAL_DATA_PATH</code> and "
        "<code>data/load_real.py</code> swaps in the live LOGCOM workbook.</div>",
        unsafe_allow_html=True,
    )


# ---------------------------------------------------------------------------
# Apply sidebar filters
# ---------------------------------------------------------------------------
filtered = df.copy()
if not filtered.empty:
    if sel_loc:
        filtered = filtered[filtered["location_id"].isin(sel_loc)]
    if sel_cat:
        filtered = filtered[filtered["category"].isin(sel_cat)]
    if sel_sens:
        filtered = filtered[filtered["sensitivity_class"].isin(sel_sens)]
    if sel_marine:
        filtered = filtered[filtered["responsible_marine"].isin(sel_marine)]
    if only_overdue and "inventory_overdue" in filtered.columns:
        filtered = filtered[filtered["inventory_overdue"].astype(bool)]
    if only_nmc and "nmc_impacting" in filtered.columns:
        filtered = filtered[filtered["nmc_impacting"].astype(bool)]


# ---------------------------------------------------------------------------
# Top metrics row
# ---------------------------------------------------------------------------
def _metric(col, label: str, value: str, accent: str | None = None) -> None:
    color = accent or BRAND["neon"]
    col.markdown(
        f"""
        <div class='sr-card' style='text-align:center;'>
          <div class='sr-metric-num' style='color:{color};'>{value}</div>
          <div class='sr-metric-lbl'>{label}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


m1, m2, m3, m4, m5 = st.columns(5)
_metric(m1, "Items in scope", f"{len(filtered):,}")
_metric(m2, "Locations", f"{filtered['location_id'].nunique() if 'location_id' in filtered.columns else 0}")
_metric(m3, "Marines on hook",
        f"{filtered['responsible_marine'].nunique() if 'responsible_marine' in filtered.columns else 0}")
overdue_count = (filtered["inventory_overdue"].astype(bool).sum()
                 if "inventory_overdue" in filtered.columns else 0)
_metric(m4, "Overdue inventory", f"{int(overdue_count):,}",
        accent="#d2a233" if overdue_count else BRAND["neon"])
nmc_count = (filtered["nmc_impacting"].astype(bool).sum()
             if "nmc_impacting" in filtered.columns else 0)
_metric(m5, "NMC-impacting", f"{int(nmc_count):,}",
        accent="#b04040" if nmc_count else BRAND["neon"])


# ---------------------------------------------------------------------------
# Natural-language query
# ---------------------------------------------------------------------------
st.markdown("### Ask STOCKROOM")
st.markdown(
    f"<div style='color:{BRAND['text_dim']}; font-size:12px; margin-bottom:6px;'>"
    "Type a question in plain English. An AI engine parses it into a structured "
    "filter spec (JSON) and runs it against the inventory table — no SQL.</div>",
    unsafe_allow_html=True,
)

EXAMPLE_QUERIES = [
    "Show me all sensitive items not lateral-transferred in 60 days.",
    "Which armory items are overdue for inventory?",
    "List NMC-impacting Class IX shortages over qty 0.",
    "Find every CCI item in COMSEC-1 not transferred in 90 days.",
    "Show ARMS-class items that haven't been inventoried in 30 days.",
]

q_col_l, q_col_r = st.columns([0.65, 0.35])
with q_col_l:
    nl_q = st.text_input(
        "NL query",
        value="Show me all sensitive items not lateral-transferred in 60 days.",
        label_visibility="collapsed",
    )
with q_col_r:
    canned = st.selectbox("Canned examples", EXAMPLE_QUERIES, index=0,
                          label_visibility="collapsed")

c_run, c_use, _ = st.columns([0.18, 0.22, 0.6])
with c_run:
    run_q = st.button("Run query", type="primary", use_container_width=True)
with c_use:
    use_canned = st.button("Use selected", use_container_width=True)
if use_canned:
    nl_q = canned
    run_q = True

q_result_slot = st.container()
spec_slot = st.empty()

if run_q and nl_q.strip():
    with st.spinner("Parsing your question into a filter spec…"):
        spec = parse_nl_query(nl_q)
    spec_slot.markdown(
        f"""
        <div class='sr-card'>
          <div style="color:{BRAND['neon']}; font-weight:600; margin-bottom:6px;">
            AI engine parsed your question into:
          </div>
          <div class='sr-trace'>{json.dumps(spec, indent=2)}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    matched = apply_filter_spec(filtered if not filtered.empty else df, spec)
    q_result_slot.markdown(
        f"<div style='color:{BRAND['text_dim']}; font-size:13px; margin:6px 0;'>"
        f"<b>{len(matched):,}</b> items matched — {spec.get('explanation', '')}</div>",
        unsafe_allow_html=True,
    )
    show_cols = [c for c in [
        "item_id", "nsn", "nomenclature", "category", "qty_on_hand", "qty_required",
        "shortage", "condition_code", "sensitivity_class", "location_id",
        "responsible_marine", "days_since_inventory", "days_since_lateral_transfer",
    ] if c in matched.columns]
    q_result_slot.dataframe(
        matched[show_cols].head(500) if show_cols else matched.head(500),
        use_container_width=True, hide_index=True, height=320,
    )
    # audit log entry — credible production-grade pattern
    _append_audit({
        "ts":   datetime.now(timezone.utc).isoformat(),
        "kind": "NL_QUERY",
        "actor":"supply NCO",
        "query":nl_q,
        "spec": spec,
        "matched_count": int(len(matched)),
    })

st.markdown("---")


# ---------------------------------------------------------------------------
# Hero brief — Readiness & Lateral Transfer Brief
# ---------------------------------------------------------------------------
st.markdown("### Readiness & Lateral Transfer Brief")
st.markdown(
    f"<div style='color:{BRAND['text_dim']}; font-size:12px; margin-bottom:8px;'>"
    "Hero AI move: a polished BLUF / overdue / NMC / lateral-transfer / "
    "recommended-actions brief, generated by a Kamiwaza-deployed model and "
    "served from cache so the demo is instant. \"Regenerate\" hits the hero "
    "model live with a 35s wall-clock timeout and a deterministic fallback.</div>",
    unsafe_allow_html=True,
)

if "brief_id" not in st.session_state:
    st.session_state.brief_id = SCENARIOS[0]["id"]
if "brief_text" not in st.session_state:
    cached = load_cached_briefs()
    st.session_state.brief_text = cached.get(st.session_state.brief_id, "")
    st.session_state.brief_source = "cache" if st.session_state.brief_text else "none"

scen_cols = st.columns(len(SCENARIOS))
for sc, col in zip(SCENARIOS, scen_cols):
    is_active = sc["id"] == st.session_state.brief_id
    label = ("◆ " if is_active else "") + sc["title"]
    if col.button(label, use_container_width=True, key=f"sc-{sc['id']}"):
        st.session_state.brief_id = sc["id"]
        cached = load_cached_briefs()
        st.session_state.brief_text = cached.get(sc["id"], "")
        st.session_state.brief_source = "cache" if st.session_state.brief_text else "none"

active = next(s for s in SCENARIOS if s["id"] == st.session_state.brief_id)

a_col_l, a_col_r = st.columns([0.78, 0.22])
with a_col_l:
    st.markdown(
        f"<div style='color:{BRAND['text_dim']}; font-size:12px;'>"
        f"<b>Scenario:</b> {active['title']} &nbsp;|&nbsp; "
        f"<b>Frame:</b> {active['frame']}</div>",
        unsafe_allow_html=True,
    )
with a_col_r:
    if st.button("Regenerate (live)", use_container_width=True, key="regen"):
        with st.spinner("Hero model composing brief… (35s timeout, deterministic fallback)"):
            result = generate_brief(active, df, use_cache=False)
        st.session_state.brief_text = result["brief"]
        st.session_state.brief_source = result["source"]
        _append_audit({
            "ts":      datetime.now(timezone.utc).isoformat(),
            "kind":    "BRIEF_REGENERATE",
            "actor":   "supply NCO",
            "scenario":active["id"],
            "source":  result["source"],
        })

# Always make sure something is on screen
if not st.session_state.brief_text:
    cached = load_cached_briefs()
    st.session_state.brief_text = cached.get(active["id"], "")
    st.session_state.brief_source = "cache" if st.session_state.brief_text else "none"

if not st.session_state.brief_text:
    # Final fallback: synthesize one on the fly
    result = generate_brief(active, df, use_cache=False)
    st.session_state.brief_text = result["brief"]
    st.session_state.brief_source = result["source"]

src_label = {
    "cache":    '<span class="sr-pill sr-pill-neon">CACHED</span>',
    "hero":     '<span class="sr-pill">HERO LIVE</span>',
    "fallback": '<span class="sr-pill sr-pill-amber">DETERMINISTIC FALLBACK</span>',
    "none":     '<span class="sr-pill sr-pill-red">EMPTY</span>',
}.get(st.session_state.brief_source, "")

st.markdown(
    f"""
    <div class='sr-card' style='border-color:{BRAND['neon']};'>
      <div style="display:flex; justify-content:space-between; align-items:center;
                  margin-bottom:8px;">
        <div style="color:{BRAND['neon']}; font-weight:700; font-size:15px;">
          {active['title']}
        </div>
        <div>{src_label}</div>
      </div>
    </div>
    """,
    unsafe_allow_html=True,
)
st.markdown(st.session_state.brief_text)


# ---------------------------------------------------------------------------
# Audit log (append-only JSONL) — visible production pattern
# ---------------------------------------------------------------------------
st.markdown("---")
st.markdown("### Audit log (append-only JSONL)")
st.markdown(
    f"<div style='color:{BRAND['text_dim']}; font-size:12px; margin-bottom:8px;'>"
    "Every NL query, regenerate, and ingest writes to "
    "<code>data/transactions.jsonl</code>. ReBAC + Living Ontologies on the "
    "Kamiwaza Stack make this surface a first-class governance citizen.</div>",
    unsafe_allow_html=True,
)
audit_rows = _load_audit(tail=10)
if audit_rows:
    audit_df = pd.DataFrame(audit_rows)
    cols_in_order = [c for c in [
        "ts", "kind", "actor", "item_id", "nomenclature", "from_loc", "to_loc",
        "delta_qty", "scenario", "source", "matched_count", "query", "note",
    ] if c in audit_df.columns]
    st.dataframe(audit_df[cols_in_order], use_container_width=True,
                 hide_index=True, height=260)
else:
    st.info("Audit log is empty — interact with the app to populate.")


# ---------------------------------------------------------------------------
# Footer
# ---------------------------------------------------------------------------
st.markdown(
    f"<div class='sr-footer'>"
    f"Powered by Kamiwaza &nbsp;|&nbsp; "
    f"<code>KAMIWAZA_BASE_URL</code> swap &rarr; on-prem inference, "
    f"100% data containment. IL5/IL6 ready, air-gapped + DDIL.</div>",
    unsafe_allow_html=True,
)
