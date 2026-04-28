# VOUCHER — DTS + Citi Manager travel program validation
# Part of the MDM 2026 Hackathon Templates (https://github.com/12fn/MDMhackathon-repos)
# MIT licensed. Built on GAI (Government Acquisitions, Inc.) + Kamiwaza (https://www.kamiwaza.ai/).
"""VOUCHER — Streamlit UI.

Run:
    streamlit run src/app.py --server.port 3034 \\
      --server.headless true --server.runOnSave false \\
      --server.fileWatcherType none --browser.gatherUsageStats false

Three buttons. That's the workflow:
    [ Run Validation ]   [ View Issues ]   [ Generate Brief ]
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

APP_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP_DIR))
sys.path.insert(0, str(APP_DIR / "src"))

from src.agent import (  # noqa: E402
    DOLLAR_EXPOSURE_BY_ISSUE,
    generate_brief,
    load_cached_briefs,
    load_cached_validations,
    load_manifest,
    save_cached_validations,
    validate_all,
)


# ──────────────────────────────────────────────────────────────────────────────
# Page config
# ──────────────────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="VOUCHER — Travel Program Validation",
    layout="wide",
)


# ──────────────────────────────────────────────────────────────────────────────
# Brand CSS — Kamiwaza dark theme
# ──────────────────────────────────────────────────────────────────────────────
BRAND_CSS = """
<style>
  .stApp { background-color: #0A0A0A; color: #FFFFFF; }
  section[data-testid="stSidebar"] { background-color: #0E0E0E; border-right: 1px solid #222222; }
  h1, h2, h3, h4, h5 { color: #FFFFFF !important; }
  .vc-header { display:flex; align-items:center; justify-content:space-between;
               border-bottom:1px solid #222; padding:8px 0 14px 0; margin-bottom:8px; }
  .vc-title  { font-size:32px; font-weight:700; letter-spacing:0.5px; color:#FFFFFF; }
  .vc-tag    { color:#00FFA7; font-size:13px; letter-spacing:1.5px; text-transform:uppercase; }
  .vc-codename { color:#00BB7A; font-weight:700; }
  .vc-card   { background:#0E0E0E; border:1px solid #222222; border-radius:8px;
               padding:14px 16px; margin-bottom:10px; }
  .vc-source-row { display:flex; align-items:center; gap:8px; padding:5px 0;
                   color:#7E7E7E; font-size:12px; font-family:Menlo,monospace; }
  .vc-pulse  { width:8px; height:8px; border-radius:50%; background:#00FFA7;
               box-shadow:0 0 8px #00FFA7; animation:pulse 1.6s infinite; }
  @keyframes pulse { 0%,100% { opacity:1; } 50% { opacity:0.35; } }
  .vc-sev-info     { background:#0E2E1F; color:#00FFA7; }
  .vc-sev-warn     { background:#3a2a07; color:#FFB347; }
  .vc-sev-escalate { background:#3a0d18; color:#FF5577; }
  .vc-sev-pill { display:inline-block; padding:3px 10px; border-radius:10px;
                 font-weight:700; letter-spacing:1px; font-size:11px;
                 font-family:Menlo,monospace; }
  .vc-footer { text-align:center; color:#6A6969; padding:18px 0 4px 0; font-size:12px;
               border-top:1px solid #222222; margin-top:24px; }
  .vc-brief { font-family:-apple-system,BlinkMacSystemFont,'Inter',sans-serif;
              white-space:pre-wrap; color:#E8E8E8; background:#0A0A0A;
              border:1px solid #00BB7A33; padding:18px; border-radius:6px;
              line-height:1.6; font-size:14px; }
  .vc-metric { background:#0E0E0E; border:1px solid #222; border-radius:6px;
               padding:12px 16px; }
  .vc-metric-label { color:#7E7E7E; font-size:11px; text-transform:uppercase;
                     letter-spacing:1.5px; }
  .vc-metric-value { color:#00FFA7; font-size:28px; font-weight:700;
                     font-family:Menlo,monospace; line-height:1.2; margin-top:4px; }
  .vc-cat-tag { display:inline-block; background:#1a1a1a; border:1px solid #00FFA744;
                color:#00FFA7; padding:3px 10px; border-radius:4px; font-size:11px;
                margin-right:6px; margin-top:4px; font-family:Menlo,monospace; }
  .vc-drilldown { background:#0E0E0E; border:1px solid #00BB7A66;
                  border-radius:8px; padding:14px 18px; margin-top:8px; }
  .vc-rationale { background:#0a1410; border-left:3px solid #00FFA7;
                  padding:10px 14px; margin:10px 0; color:#E8E8E8;
                  font-size:13px; line-height:1.55; }
  .stButton button {
      background: #00BB7A !important; color: #0A0A0A !important;
      font-weight: 700 !important; border: 0 !important;
      letter-spacing: 0.6px !important;
  }
  .stButton button:hover { background: #0DCC8A !important; }
  div[data-testid="stDataFrame"] { background:#0E0E0E; border:1px solid #222; border-radius:6px; }
</style>
"""
st.markdown(BRAND_CSS, unsafe_allow_html=True)


# ──────────────────────────────────────────────────────────────────────────────
# Header
# ──────────────────────────────────────────────────────────────────────────────
st.markdown(
    """
    <div class='vc-header'>
      <div>
        <span class='vc-title'><span class='vc-codename'>VOUCHER</span></span><br/>
        <span class='vc-tag'>DTS &middot; Citi Manager &middot; Travel Program Validation Agent</span>
      </div>
      <div style='text-align:right;color:#7E7E7E;font-size:12px;'>
        Agent #34 &middot; USMC LOGCOM CDAO @ MDM 2026<br/>
        <span style='color:#00FFA7'>Three-button S-1 desktop &middot; Kamiwaza Stack</span>
      </div>
    </div>
    """,
    unsafe_allow_html=True,
)


# ──────────────────────────────────────────────────────────────────────────────
# Data loaders
# ──────────────────────────────────────────────────────────────────────────────
DATA_DIR = APP_DIR / "data"


@st.cache_data
def _load_manifest():
    m = load_manifest()
    if not m.get("scenarios"):
        st.error("data/manifest.json missing — run `python data/generate.py` first.")
        st.stop()
    return m


@st.cache_data
def _load_cached_briefs():
    return load_cached_briefs()


manifest = _load_manifest()
cached_briefs = _load_cached_briefs()


# ──────────────────────────────────────────────────────────────────────────────
# Sidebar — scenario picker + ingest panel
# ──────────────────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("### Unit / Quarter")
    scenario_options = {
        f"{s['unit']} — {s['quarter']}": s for s in manifest["scenarios"]
    }
    scenario_label = st.selectbox(
        "Select unit-quarter",
        list(scenario_options.keys()),
        index=0,
    )
    scenario = scenario_options[scenario_label]

    st.markdown("---")
    st.markdown("### Live Ingest")
    st.markdown("<div class='vc-card'>", unsafe_allow_html=True)
    for src in manifest.get("sources_simulated", []):
        st.markdown(
            f"<div class='vc-source-row'>"
            f"<span class='vc-pulse'></span>{src}</div>",
            unsafe_allow_html=True,
        )
    st.markdown("</div>", unsafe_allow_html=True)

    st.markdown(
        f"<div style='color:#6A6969;font-size:11px;line-height:1.6'>"
        f"DTS records loaded: <span style='color:#00BB7A'>{manifest['dts_records']}</span><br/>"
        f"Citi transactions: <span style='color:#00BB7A'>{manifest['citi_transactions']}</span><br/>"
        f"Scenarios cached: <span style='color:#00BB7A'>{len(manifest['scenarios'])}</span>"
        f"</div>",
        unsafe_allow_html=True,
    )

    st.markdown("---")
    use_llm = st.toggle(
        "Validate with Kamiwaza-deployed model",
        value=False,
        help=("OFF: deterministic rule-based validator only (instant). "
              "ON: AI engine adds nuance to each verdict (slower)."),
    )


# ──────────────────────────────────────────────────────────────────────────────
# Three-button workflow
# ──────────────────────────────────────────────────────────────────────────────
btn_col1, btn_col2, btn_col3 = st.columns(3)

with btn_col1:
    run_validation = st.button(
        "Run Validation", type="primary", use_container_width=True,
        key="btn_run_validation",
    )
with btn_col2:
    view_issues = st.button(
        "View Issues", type="primary", use_container_width=True,
        key="btn_view_issues",
    )
with btn_col3:
    gen_brief = st.button(
        "Generate Brief", type="primary", use_container_width=True,
        key="btn_gen_brief",
    )


# ──────────────────────────────────────────────────────────────────────────────
# Session state
# ──────────────────────────────────────────────────────────────────────────────
if "validations" not in st.session_state:
    cached = load_cached_validations()
    st.session_state.validations = (cached or {}).get("validations") if cached else None
if "active_scenario_code" not in st.session_state:
    st.session_state.active_scenario_code = None
if "view" not in st.session_state:
    st.session_state.view = "idle"  # idle | issues | brief

# Track if user changed scenario — invalidate validations
if st.session_state.active_scenario_code != scenario["code"]:
    st.session_state.active_scenario_code = scenario["code"]
    # Don't clear cached validations — they cover the whole corpus.

# Button handlers
if run_validation:
    with st.spinner("Reconciling DTS vouchers against Citi statements + GSA per-diem..."):
        results = validate_all(scenario_code=scenario["code"], use_llm=use_llm)
        st.session_state.validations = results
        try:
            save_cached_validations(results)
        except Exception:
            pass
    st.session_state.view = "issues"
    st.toast(f"Validated {len(results)} records.")

if view_issues:
    if not st.session_state.validations:
        with st.spinner("First run — performing baseline validation..."):
            st.session_state.validations = validate_all(
                scenario_code=scenario["code"], use_llm=False)
    st.session_state.view = "issues"

if gen_brief:
    if not st.session_state.validations:
        # Bootstrap with baseline so we have something to summarize
        st.session_state.validations = validate_all(
            scenario_code=scenario["code"], use_llm=False)
    st.session_state.view = "brief"


# ──────────────────────────────────────────────────────────────────────────────
# View: idle (no buttons clicked yet)
# ──────────────────────────────────────────────────────────────────────────────
if st.session_state.view == "idle":
    st.markdown("#### Three-Button S-1 Workflow")
    st.markdown(
        "<div class='vc-card' style='color:#7E7E7E;line-height:1.7'>"
        "VOUCHER ingests a quarter of <b style='color:#00FFA7'>DTS authorization+voucher pairs</b> and "
        "<b style='color:#00FFA7'>Citi Manager card statements</b> for the selected unit, then runs a "
        "two-tier validation agent over every record. The Kamiwaza-deployed model returns a typed JSON verdict "
        "per record; a hero call writes the unit S-1's quarterly brief.<br/><br/>"
        "Click <b style='color:#00BB7A'>Run Validation</b> to begin. "
        "Then <b style='color:#00BB7A'>View Issues</b> to drill in. "
        "Finally <b style='color:#00BB7A'>Generate Brief</b> for the S-1 / CO read-out.<br/><br/>"
        "<i>Idiot-proof — that's the LOGCOM ask, and that's the design.</i>"
        "</div>",
        unsafe_allow_html=True,
    )
    # Hint cards for the three issue tiers
    cols = st.columns(3)
    for col, (label, color, blurb) in zip(cols, [
        ("INFO", "#00FFA7", "Clean records — no further action."),
        ("WARN", "#FFB347", "S-1 fix in DTS or request receipt from traveler."),
        ("ESCALATE", "#FF5577", "Refer to APC; possible card mis-use or fraud."),
    ]):
        with col:
            st.markdown(
                f"<div class='vc-card' style='border-color:{color}55'>"
                f"<div style='color:{color};font-weight:700;letter-spacing:1.5px;font-size:13px'>"
                f"&#9632; {label}</div>"
                f"<div style='color:#E8E8E8;font-size:13px;margin-top:6px;line-height:1.5'>{blurb}</div>"
                f"</div>",
                unsafe_allow_html=True,
            )


# ──────────────────────────────────────────────────────────────────────────────
# View: issues — sortable table + per-record drill-down
# ──────────────────────────────────────────────────────────────────────────────
def _filter_validations_for_scenario(vals: list[dict], code: str) -> list[dict]:
    return [v for v in vals if (v.get("_record") or {}).get("unit_code") == code]


if st.session_state.view == "issues" and st.session_state.validations:
    vals = _filter_validations_for_scenario(
        st.session_state.validations, scenario["code"]
    )
    # Headline metrics
    n_records = len(vals)
    n_with_issues = sum(1 for v in vals if v["issues_found"])
    n_escalate = sum(1 for v in vals if v["severity"] == "escalate")
    dollar_exposure = sum(float(v.get("dollar_exposure", 0)) for v in vals)

    m1, m2, m3, m4 = st.columns(4)
    for c, label, value in zip(
        [m1, m2, m3, m4],
        ["Records Validated", "With Issues", "Escalations", "Dollar Exposure"],
        [f"{n_records}", f"{n_with_issues}", f"{n_escalate}", f"${dollar_exposure:,.0f}"],
    ):
        with c:
            st.markdown(
                f"<div class='vc-metric'>"
                f"<div class='vc-metric-label'>{label}</div>"
                f"<div class='vc-metric-value'>{value}</div></div>",
                unsafe_allow_html=True,
            )

    st.markdown("&nbsp;", unsafe_allow_html=True)
    st.markdown("#### Issues Table")

    # Build a DataFrame for display
    rows = []
    for v in vals:
        r = v.get("_record", {})
        rows.append({
            "Record": v["record_id"],
            "Severity": v["severity"].upper(),
            "Issues": ", ".join(v["issues_found"]) or "—",
            "Traveler": r.get("traveler", ""),
            "City": r.get("tdy_city", ""),
            "Dates": f"{r.get('depart_date','')} → {r.get('return_date','')}",
            "Voucher $": float(r.get("voucher_total") or 0.0),
            "Action": v.get("recommended_action", ""),
            "Confidence": round(float(v.get("confidence") or 0.0), 2),
            "Auto-fix": "yes" if v.get("auto_correctable") else "no",
            "Source": v.get("_source", ""),
        })
    df = pd.DataFrame(rows)
    # Sort: escalate first
    sev_rank = {"ESCALATE": 0, "WARN": 1, "INFO": 2}
    df["_sev_rank"] = df["Severity"].map(sev_rank).fillna(99)
    df = df.sort_values(["_sev_rank", "Voucher $"], ascending=[True, False]).drop(
        columns=["_sev_rank"]
    )

    st.dataframe(
        df,
        use_container_width=True,
        hide_index=True,
        height=360,
        column_config={
            "Voucher $": st.column_config.NumberColumn(format="$%.2f"),
            "Confidence": st.column_config.ProgressColumn(
                format="%.2f", min_value=0.0, max_value=1.0,
            ),
        },
    )

    st.markdown("#### Drill-down")
    flagged_ids = [v["record_id"] for v in vals if v["issues_found"]]
    default_idx = 0
    if flagged_ids:
        # Default to the first ESCALATE record
        for i, v in enumerate(vals):
            if v["record_id"] in flagged_ids and v["severity"] == "escalate":
                default_idx = flagged_ids.index(v["record_id"])
                break

    selected = st.selectbox(
        "Select flagged record to inspect",
        options=flagged_ids if flagged_ids else ["(no flagged records)"],
        index=default_idx if flagged_ids else 0,
        key="drilldown_select",
    )
    if flagged_ids:
        v = next(x for x in vals if x["record_id"] == selected)
        r = v.get("_record", {})
        sev_class = f"vc-sev-{v['severity']}"
        st.markdown(
            f"<div class='vc-drilldown'>"
            f"<div style='display:flex;justify-content:space-between;align-items:center'>"
            f"<div><b style='font-size:18px'>{r.get('traveler','')}</b> &nbsp; "
            f"<span style='color:#7E7E7E;font-size:13px'>"
            f"({r.get('tdy_city','')} &middot; {r.get('depart_date','')} → {r.get('return_date','')})"
            f"</span></div>"
            f"<div><span class='vc-sev-pill {sev_class}'>{v['severity'].upper()}</span></div>"
            f"</div>"
            f"<div style='color:#7E7E7E;font-size:12px;margin-top:4px'>"
            f"{v['record_id']} &middot; {r.get('trip_reason','')}"
            f"</div>"
            f"<div style='margin-top:10px'>"
            + "".join(f"<span class='vc-cat-tag'>{t}</span>" for t in v["issues_found"])
            + "</div>"
            f"<div class='vc-rationale'>"
            f"<b style='color:#00FFA7'>Recommended action &middot; confidence {v.get('confidence',0):.2f}:</b><br/>"
            f"{v.get('recommended_action','')}"
            f"</div>"
            "</div>",
            unsafe_allow_html=True,
        )

        c1, c2 = st.columns(2)
        with c1:
            st.markdown("##### DTS voucher lines")
            v_lines = pd.DataFrame(r.get("voucher_lines", []))
            if not v_lines.empty:
                st.dataframe(v_lines, use_container_width=True, hide_index=True)
            v_total = float(r.get("voucher_total") or 0.0)
            st.caption(f"Voucher total: ${v_total:,.2f}")
        with c2:
            st.markdown("##### Citi Manager charges")
            citi_df = pd.DataFrame(r.get("citi_transactions", []))
            if not citi_df.empty:
                citi_disp = citi_df[["post_date", "merchant",
                                     "merchant_category", "amount"]].copy()
                citi_disp["amount"] = citi_disp["amount"].map(lambda x: f"${x:.2f}")
                st.dataframe(citi_disp, use_container_width=True, hide_index=True)
                st.caption(f"Citi sum: ${citi_df['amount'].sum():,.2f}")
            else:
                st.caption("(no linked Citi transactions)")


# ──────────────────────────────────────────────────────────────────────────────
# View: brief — hero quarterly narrative
# ──────────────────────────────────────────────────────────────────────────────
if st.session_state.view == "brief":
    vals = _filter_validations_for_scenario(
        st.session_state.validations or [], scenario["code"]
    )
    sid = f"{scenario['code']}_{scenario['quarter']}"
    scenario_obj = {
        "scenario_id": sid,
        "unit": scenario["unit"],
        "unit_code": scenario["code"],
        "quarter": scenario["quarter"],
    }

    # Use cached brief if available — instant render
    payload = generate_brief(scenario_obj, vals, use_cache=True, hero=False)

    # Map internal source ids to neutral, model-name-free labels
    source_labels = {
        "gpt-5.4":                 "Hero model (Kamiwaza-deployed)",
        "gpt-5.4-mini":            "Standard model (Kamiwaza-deployed)",
        "default-chain":           "Standard model (Kamiwaza-deployed)",
        "warm-cache":              "Cached (pre-computed at ingest)",
        "baseline-deterministic":  "Deterministic baseline",
        "deterministic-fallback":  "Deterministic baseline",
    }
    source_label = source_labels.get(payload.get("source", ""),
                                     "Cached (pre-computed at ingest)")
    st.markdown(
        f"<div class='vc-card' style='border-color:#00FFA7'>"
        f"<div style='color:#00FFA7;font-size:11px;letter-spacing:1.5px;text-transform:uppercase'>"
        f"Travel Program Quarterly Brief"
        f"</div>"
        f"<div style='font-family:Menlo,monospace;font-size:18px;color:#FFFFFF;margin-top:4px'>"
        f"{scenario['unit']} &middot; {scenario['quarter']}"
        f"</div>"
        f"<div style='color:#7E7E7E;font-size:11px;margin-top:6px'>"
        f"Source: <span style='color:#00FFA7'>{source_label}</span> &middot; "
        f"records: {payload.get('record_count', len(vals))} &middot; "
        f"generated {payload.get('generated_at','')}"
        f"</div>"
        f"</div>",
        unsafe_allow_html=True,
    )

    st.markdown(f"<div class='vc-brief'>{payload['brief']}</div>",
                unsafe_allow_html=True)

    rgn_col, _ = st.columns([1, 4])
    with rgn_col:
        regen = st.button("Regenerate (live, ~30s)", key="btn_regen_brief")
    if regen:
        with st.spinner("Routing through hero Kamiwaza-deployed model..."):
            payload = generate_brief(scenario_obj, vals,
                                      use_cache=False, hero=True)
        st.markdown(f"<div class='vc-brief'>{payload['brief']}</div>",
                    unsafe_allow_html=True)


# ──────────────────────────────────────────────────────────────────────────────
# Footer
# ──────────────────────────────────────────────────────────────────────────────
st.markdown(
    "<div class='vc-footer'>VOUCHER &middot; Powered by Kamiwaza &middot; "
    "100% data containment &middot; Nothing ever leaves your accredited environment.</div>",
    unsafe_allow_html=True,
)
