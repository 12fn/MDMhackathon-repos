"""REDLINE — CUI Auto-Tagging and Classification Assistant.

Streamlit mono-page on port 3028.

Flow:
  1. Operator picks a draft (or pastes text / uploads .docx / .txt).
  2. App reads cached per-paragraph + document brief from cached_briefs.json
     for known docs (cache-first, snappy demo). For ad-hoc text, fires the
     live structured-JSON markings call with watchdog.
  3. Side-by-side: original on the left, marked-up version with colored
     highlights on the right. Document Marking Brief above. Audit chain below.
  4. Analyst can concur / non-concur per paragraph; every action chains into
     the SHA-256 audit log.
"""
from __future__ import annotations

import io
import json
import os
import sys
import time
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = APP_DIR / "data"
SAMPLES_DIR = APP_DIR / "sample_docs"
AUDIT_DIR = APP_DIR / "audit_logs"
REPO_ROOT = APP_DIR.parent.parent
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(APP_DIR))

import streamlit as st  # noqa: E402

from shared.kamiwaza_client import BRAND  # noqa: E402

from src.audit import AuditChain, sha256_text  # noqa: E402
from src.marker import (  # noqa: E402
    document_brief,
    load_cached_briefs,
    load_taxonomy,
    mark_paragraph,
    split_paragraphs,
)

AUDIT_DIR.mkdir(parents=True, exist_ok=True)
AUDIT = AuditChain(AUDIT_DIR / "redline_audit.jsonl")
TAXONOMY = load_taxonomy()
CACHED = load_cached_briefs()

# ---------------- Marking color palette --------------------------------------

MARKING_COLOR = {
    "UNCLASSIFIED": ("#0E5132", "#A8FFC9"),       # bg, fg
    "CUI//FOUO": ("#5C4E14", "#FFE680"),
    "CUI//SP-PROCURE": ("#3F2A6B", "#D7C2FF"),
    "CUI//SP-PROPIN": ("#4B2A6B", "#E0BFFF"),
    "CUI//SP-PRVCY": ("#2C4F87", "#B5D8FF"),
    "CUI//SP-CTI": ("#2D5C5A", "#9CFFF6"),
    "CUI//SP-OPSEC": ("#6B2A2A", "#FFB5B5"),
    "CUI//SP-EXPT": ("#7A1F1F", "#FF9C9C"),
    "CUI//SP-LEI": ("#5C2A6B", "#E0B0FF"),
    "CUI//SP-NF": ("#9A0E0E", "#FFC2C2"),
}

DEFAULT_COLOR = ("#222222", "#E8E8E8")


def color_for(marking: str) -> tuple[str, str]:
    return MARKING_COLOR.get(marking, DEFAULT_COLOR)


# ---------------- Page setup -------------------------------------------------

st.set_page_config(
    page_title="REDLINE — CUI Auto-Tagging Assistant",
    page_icon=None,
    layout="wide",
    initial_sidebar_state="collapsed",
)

st.markdown(f"""
<style>
    .stApp {{ background-color: {BRAND['bg']}; color: #E8E8E8; }}
    .block-container {{ padding-top: 0.6rem; padding-bottom: 0.6rem; max-width: 1500px; }}
    h1, h2, h3, h4 {{ color: {BRAND['neon']} !important; font-family: Helvetica, Arial, sans-serif; }}
    .redline-header {{
        padding: 12px 18px; border-bottom: 1px solid {BRAND['border']};
        background: linear-gradient(90deg, #000 0%, {BRAND['surface']} 100%);
        margin-bottom: 12px;
    }}
    .redline-title {{ color: {BRAND['neon']}; font-size: 24px; letter-spacing: 3px; margin: 0; }}
    .redline-sub  {{ color: {BRAND['text_dim']}; font-size: 13px; margin-top: 4px; }}
    .doc-pane {{
        background: {BRAND['surface']}; border: 1px solid {BRAND['border']};
        padding: 12px; border-radius: 4px; height: 540px; overflow-y: auto;
        font-family: 'Menlo', monospace; font-size: 12.5px; line-height: 1.55;
        color: #D0D0D0;
    }}
    .marked-pane {{
        background: {BRAND['surface']}; border: 1px solid {BRAND['border']};
        padding: 12px; border-radius: 4px; height: 540px; overflow-y: auto;
    }}
    .para-block {{
        border-left: 3px solid #444; padding: 8px 10px; margin-bottom: 10px;
        background: {BRAND['surface_high']};
        font-family: 'Menlo', monospace; font-size: 12.5px; line-height: 1.5;
    }}
    .para-marking {{
        display: inline-block; padding: 2px 8px; border-radius: 3px;
        font-weight: 700; font-size: 11px; letter-spacing: 1px;
        font-family: 'Menlo', monospace; margin-bottom: 6px;
    }}
    .para-conf {{
        color: {BRAND['muted']}; font-size: 10px; margin-left: 8px;
        font-family: 'Menlo', monospace;
    }}
    .para-rationale {{
        color: {BRAND['neon']}; font-size: 11px; font-style: italic;
        margin-top: 4px;
    }}
    .triggers {{ color: #FFB347; font-size: 11px; margin-top: 4px; }}
    .triggers code {{ background: #000; color: #FFB347; padding: 1px 5px; border-radius: 2px; }}
    .banner-line {{
        background: #9A0E0E; color: #FFE; font-weight: 800;
        padding: 6px 12px; letter-spacing: 4px; text-align: center;
        font-family: 'Menlo', monospace; font-size: 13px; margin-bottom: 12px;
        border-radius: 3px;
    }}
    .brief-pane {{
        background: {BRAND['surface_high']}; border: 1px solid {BRAND['border']};
        border-left: 3px solid {BRAND['primary']};
        padding: 14px 18px; border-radius: 4px; margin-bottom: 12px;
    }}
    .brief-pane h4 {{ margin-top: 8px; }}
    .audit-row {{ font-family: 'Menlo', monospace; font-size: 11px; }}
    .footer {{
        text-align: center; color: {BRAND['muted']}; padding: 16px 8px;
        border-top: 1px solid {BRAND['border']}; margin-top: 18px;
        font-size: 12px; letter-spacing: 1px;
    }}
    .footer .kw {{ color: {BRAND['primary']}; font-weight: 700; }}
    .footer .neon {{ color: {BRAND['neon']}; }}
    div[data-testid="stExpander"] {{
        background: {BRAND['surface']}; border: 1px solid {BRAND['border']};
    }}
    div[data-testid="stMetricValue"] {{ color: {BRAND['neon']}; }}
    button[kind="primary"] {{
        background-color: {BRAND['primary']} !important;
        color: #000 !important; font-weight: 700;
    }}
</style>
""", unsafe_allow_html=True)

st.markdown(f"""
<div class="redline-header">
  <h1 class="redline-title">REDLINE</h1>
  <div class="redline-sub">
    CUI Auto-Tagging and Classification Assistant &middot;
    <span style="color:{BRAND['primary']}">USMC LOGCOM</span> &middot;
    DoDM 5200.01 Vol 2 marking recommendations + cryptographic audit chain
  </div>
</div>
""", unsafe_allow_html=True)


# ---------------- Document selection ----------------------------------------

st.markdown("### 1. Select a draft document")
col_pick, col_ana = st.columns([3, 2])

doc_choices = []
for d in sorted(SAMPLES_DIR.glob("*.txt")):
    doc_choices.append(d.stem)

with col_pick:
    pick = st.selectbox(
        "Cached sample drafts (synthetic — no real CUI/PII)",
        options=doc_choices,
        index=0 if doc_choices else None,
        help="4 synthetic drafts authored for the demo. Cached briefs load instantly.",
    )

with col_ana:
    analyst_id = st.text_input(
        "Analyst ID (signed into the audit chain)",
        value="MAJ HALL / III MEF G-2 IPO",
    )

with st.expander("Or paste / upload your own draft", expanded=False):
    uploaded = st.file_uploader(
        "Upload .txt or .docx (no real CUI please — synthetic only)",
        type=["txt"],
        accept_multiple_files=False,
        help="Pastes / uploads bypass the cache and run a live AI marking pass.",
    )
    pasted = st.text_area("…or paste draft text here:", height=140,
                          placeholder="Paste a synthetic draft document here…")
    use_live = st.button("Run live marking pass", type="primary",
                         help="Live structured-JSON per-paragraph + hero document brief")

# Resolve which doc / text to render
doc_id: str | None = None
doc_text: str = ""
paragraphs: list[dict] = []
brief: dict = {}
source_label = ""

if use_live and (uploaded or pasted.strip()):
    if uploaded is not None:
        raw = uploaded.read().decode("utf-8", errors="replace")
        doc_id = f"upload_{uploaded.name}"
        source_label = f"live: uploaded {uploaded.name}"
    else:
        raw = pasted
        doc_id = "paste_adhoc"
        source_label = "live: pasted text"

    doc_text = raw
    para_texts = split_paragraphs(raw)
    progress = st.progress(0.0, text="Marking paragraphs (structured-JSON)…")
    para_results: list[dict] = []
    t_para0 = time.time()
    for i, p in enumerate(para_texts):
        res = mark_paragraph(p, TAXONOMY, i)
        res["paragraph_index"] = i
        res["paragraph_text"] = p
        para_results.append(res)
        progress.progress((i + 1) / max(1, len(para_texts)),
                          text=f"Paragraph {i+1}/{len(para_texts)} done")
    para_latency = int((time.time() - t_para0) * 1000)
    progress.empty()
    with st.spinner("Drafting Document Marking Brief (hero model, ~35 s)…"):
        t0 = time.time()
        brief = document_brief(raw, para_results, TAXONOMY)
        brief_latency = int((time.time() - t0) * 1000)
    paragraphs = para_results
    brief["_latency_ms"] = brief_latency
    brief["_paragraph_latency_ms"] = para_latency
elif pick:
    cached = CACHED.get(pick)
    if cached:
        doc_id = cached["doc_id"]
        doc_text = (SAMPLES_DIR / f"{pick}.txt").read_text()
        paragraphs = cached["paragraphs"]
        brief = cached["doc_brief"]
        source_label = "cache: pre-analyzed"
    else:
        # No cache — fall back to deterministic on-the-fly
        doc_id = pick
        doc_text = (SAMPLES_DIR / f"{pick}.txt").read_text()
        para_texts = split_paragraphs(doc_text)
        paragraphs = []
        for i, p in enumerate(para_texts):
            res = mark_paragraph(p, TAXONOMY, i, timeout=8)
            res["paragraph_index"] = i
            res["paragraph_text"] = p
            paragraphs.append(res)
        brief = document_brief(doc_text, paragraphs, TAXONOMY, timeout=20)
        source_label = "live (no cache hit)"

# ---------------- Document Marking Brief (hero) -----------------------------

if brief:
    overall = brief.get("overall_marking", "—")
    rel = brief.get("releasability", "—")
    bg, fg = color_for(overall)
    st.markdown(f"""
    <div class="banner-line" style="background:{bg}; color:{fg};">
      {overall} &nbsp;&nbsp; // &nbsp;&nbsp; {rel}
    </div>
    """, unsafe_allow_html=True)

    st.markdown("### 2. Document Marking Brief — hero output")
    st.caption(f"Source: {source_label}")
    if "_fallback" in brief:
        st.warning(f"Hero brief fell back to deterministic baseline ({brief['_fallback']}). "
                   f"Live AI brief will return on next run.")
    st.markdown(f"""
    <div class="brief-pane">
      <h4 style="margin-top:0">Executive brief</h4>
      <div>{brief.get('executive_brief', '—')}</div>
      <h4>IPO recommendation</h4>
      <div style="color:{BRAND['neon']}">{brief.get('ipo_recommendation', '—')}</div>
      <h4>Risk of over-marking</h4>
      <div style="color:#FFB347">{brief.get('over_marking_risk', '—')}</div>
      <h4>Risk of under-marking</h4>
      <div style="color:#FF6B6B">{brief.get('under_marking_risk', '—')}</div>
    </div>
    """, unsafe_allow_html=True)

# ---------------- Side-by-side: original | marked --------------------------

st.markdown("### 3. Original draft &nbsp;|&nbsp; AI-marked version")

left, right = st.columns(2)
with left:
    st.markdown("**Original draft (analyst input)**")
    safe = (doc_text or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    safe_html = safe.replace("\n\n", "<br/><br/>").replace("\n", "<br/>")
    st.markdown(f'<div class="doc-pane">{safe_html}</div>', unsafe_allow_html=True)

with right:
    st.markdown("**AI-recommended marking (per paragraph)**")
    blocks: list[str] = []
    for p in paragraphs:
        marking = p.get("recommended_marking", "—")
        bg, fg = color_for(marking)
        conf = p.get("confidence", 0.0) or 0.0
        rationale = p.get("rationale", "")
        triggers = p.get("trigger_phrases", []) or []
        caveats = p.get("caveats_recommended", []) or []
        ptext = (p.get("paragraph_text", "")
                 .replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
                 .replace("\n", "<br/>"))
        trig_html = ""
        if triggers:
            trig_html = "<div class='triggers'>triggers: " + " ".join(
                f"<code>{t}</code>" for t in triggers
            ) + "</div>"
        cav_html = ""
        if caveats:
            cav_html = (f"<div class='triggers' style='color:#62D4FF'>caveats: "
                        + " ".join(f"<code>{c}</code>" for c in caveats)
                        + "</div>")
        fb_html = ""
        if "_fallback" in p:
            fb_html = (f"<div class='triggers' style='color:#888'>"
                       f"({p['_fallback']})</div>")
        blocks.append(f"""
        <div class="para-block" style="border-left-color:{fg};">
          <span class="para-marking" style="background:{bg}; color:{fg};">{marking}</span>
          <span class="para-conf">conf {conf:.2f} &middot; ¶ {p.get('paragraph_index', '?')}</span>
          <div style="margin-top:6px">{ptext}</div>
          <div class="para-rationale">{rationale}</div>
          {trig_html}{cav_html}{fb_html}
        </div>
        """)
    st.markdown(f'<div class="marked-pane">{"".join(blocks)}</div>',
                unsafe_allow_html=True)


# ---------------- Per-paragraph attestation --------------------------------

st.markdown("### 4. Analyst attestation (signed into the audit chain)")
att_col1, att_col2, att_col3 = st.columns([1, 4, 2])
para_indices = [str(p.get("paragraph_index", i)) for i, p in enumerate(paragraphs)]
with att_col1:
    if para_indices:
        para_pick = st.selectbox("Paragraph #", options=para_indices, index=0,
                                 key="attest_para")
    else:
        para_pick = None
with att_col2:
    note = st.text_input(
        "Analyst note (signed)",
        placeholder="e.g. Concur — FPCON + manning roster trigger SP-OPSEC.",
        key="attest_note",
    )
with att_col3:
    bcol1, bcol2 = st.columns(2)
    concur_clicked = bcol1.button("CONCUR", type="primary", key="concur_btn",
                                  use_container_width=True)
    nonconcur_clicked = bcol2.button("NON-CONCUR", key="nonconcur_btn",
                                     use_container_width=True)

if (concur_clicked or nonconcur_clicked) and para_pick is not None:
    chosen = next((p for p in paragraphs
                   if str(p.get("paragraph_index")) == para_pick), None)
    if chosen:
        action = "CONCUR" if concur_clicked else "NON_CONCUR"
        decision_text = json.dumps({
            "marking": chosen.get("recommended_marking"),
            "rationale": chosen.get("rationale"),
            "caveats": chosen.get("caveats_recommended", []),
            "confidence": chosen.get("confidence"),
        }, sort_keys=True)
        entry = AUDIT.append({
            "event": f"ATTESTATION_{action}",
            "analyst_id": (analyst_id or "ANALYST/UNKNOWN").strip(),
            "doc_id": doc_id,
            "paragraph_index": int(para_pick),
            "decision": json.loads(decision_text),
            "decision_sha256": sha256_text(decision_text),
            "analyst_note": note,
            "model_surface": "Kamiwaza-deployed model",
        })
        st.success(
            f"Attestation logged. action={action} · "
            f"prev `{entry['prev_hash'][:16]}…` → "
            f"this `{entry['entry_hash'][:16]}…`"
        )

# Always log a "VIEWED" event the first time a doc loads, so the chain isn't empty
if doc_id and st.session_state.get("_last_viewed_doc") != doc_id:
    AUDIT.append({
        "event": "DOCUMENT_VIEWED",
        "analyst_id": (analyst_id or "ANALYST/UNKNOWN").strip(),
        "doc_id": doc_id,
        "paragraph_count": len(paragraphs),
        "overall_marking": brief.get("overall_marking") if brief else None,
        "model_surface": "Kamiwaza-deployed model",
    })
    st.session_state["_last_viewed_doc"] = doc_id

# ---------------- Audit chain panel ----------------------------------------

st.markdown("### 5. SHA-256 hash-chained audit log")
verify = AUDIT.verify()
mcol1, mcol2, mcol3 = st.columns(3)
mcol1.metric("Chain entries", verify.get("entries", 0))
mcol2.metric("Chain integrity", "INTACT" if verify.get("ok") else "BROKEN")
tip = verify.get("tip_hash") or ""
mcol3.metric("Tip hash", (tip[:14] + "…") if tip else "—")

chain = AUDIT.read(limit=12)
if not chain:
    st.info("Audit chain empty — interact with a paragraph to seed the genesis entry.")
else:
    rows = ["| # | Event | Analyst | Doc | ¶ | Marking | prev → this |",
            "|---|---|---|---|---|---|---|"]
    for i, e in enumerate(chain):
        decision = e.get("decision") or {}
        rows.append(
            f"| {len(chain) - i} | `{e.get('event','?')}` | "
            f"`{e.get('analyst_id','?')}` | "
            f"`{e.get('doc_id','—')}` | "
            f"{e.get('paragraph_index', '—')} | "
            f"`{decision.get('marking', e.get('overall_marking','—'))}` | "
            f"`{e.get('prev_hash','')[:10]}…` → `{e.get('entry_hash','')[:10]}…` |"
        )
    st.markdown("\n".join(rows))

# ---------------- Footer ----------------------------------------------------

st.markdown(f"""
<div class="footer">
  <span class="neon">100% Data Containment.</span>
  Set <code>KAMIWAZA_BASE_URL</code> and the same code talks to a Kamiwaza-hosted vLLM
  inside your accredited boundary.
  IL5/IL6 ready &middot; NIPR/SIPR/JWICS deployable &middot; DDIL-tolerant.
  <br/>
  <span class="kw">Powered by Kamiwaza</span>
</div>
""", unsafe_allow_html=True)
