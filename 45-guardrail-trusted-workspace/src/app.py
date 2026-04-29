"""GUARDRAIL — Trusted Marine Workspace (Streamlit, port 3045).

Four governance layers in a single shell:

  1. CUI Auto-Tagging          (REDLINE pattern)
  2. ABAC Enforcement          (AGORA / NIST SP 800-162 pattern)
  3. Browser AI Governance     (GUARDIAN pattern)
  4. Hash-chained Audit        (SHA-256 across all of the above)

Hero AI move: a "Workspace Governance Posture Brief" written by the
Kamiwaza-deployed hero model, cache-first.

Run:
    streamlit run src/app.py --server.port 3045 --server.headless true \\
        --server.runOnSave false --server.fileWatcherType none \\
        --browser.gatherUsageStats false
"""
from __future__ import annotations

import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutTimeout
from pathlib import Path

import pandas as pd
import streamlit as st

APP_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = APP_DIR / "data"
SAMPLES_DIR = APP_DIR / "sample_docs"
REPO_ROOT = APP_DIR.parents[1]
for p in (str(REPO_ROOT), str(APP_DIR)):
    if p not in sys.path:
        sys.path.insert(0, p)

from shared.kamiwaza_client import BRAND  # noqa: E402

from src import audit  # noqa: E402
from src.abac import authorize_paragraph, redaction_text  # noqa: E402
from src.ai_assist import render_answer, retrieve  # noqa: E402
from src.browser_gov import classify as browser_classify  # noqa: E402

# ---------------------------------------------------------------------------
# Page config + brand theme
# ---------------------------------------------------------------------------

st.set_page_config(
    page_title="GUARDRAIL — Trusted Marine Workspace",
    page_icon=None,
    layout="wide",
    initial_sidebar_state="expanded",
)

CSS = f"""
<style>
  html, body, [data-testid="stAppViewContainer"], [data-testid="stHeader"] {{
    background-color: {BRAND['bg']} !important;
    color: #E8E8E8 !important;
  }}
  [data-testid="stSidebar"] {{
    background-color: {BRAND['surface']} !important;
    border-right: 1px solid {BRAND['border']};
  }}
  .block-container {{
    padding-top: 0.6rem; padding-bottom: 0.6rem; max-width: 1500px;
  }}
  h1, h2, h3, h4 {{
    color: {BRAND['neon']} !important;
    font-family: Helvetica, Arial, sans-serif;
    letter-spacing: 0.4px;
  }}
  .gr-header {{
    padding: 12px 18px; border-bottom: 1px solid {BRAND['border']};
    background: linear-gradient(90deg, #000 0%, {BRAND['surface']} 100%);
    margin-bottom: 12px;
  }}
  .gr-title {{
    color: {BRAND['neon']}; font-size: 26px; letter-spacing: 4px; margin: 0;
  }}
  .gr-sub {{ color: {BRAND['text_dim']}; font-size: 13px; margin-top: 4px; }}
  .gr-pill {{
    display: inline-block; padding: 2px 9px; border-radius: 999px;
    font-size: 11px; font-weight: 700; letter-spacing: 0.6px; margin-right: 6px;
    background: {BRAND['surface_high']}; border: 1px solid {BRAND['border']};
    color: {BRAND['neon']};
  }}
  .gr-pill.allow {{ background:#0E2F22; color:#00FFA7; border-color:#00BB7A; }}
  .gr-pill.block {{ background:#3A0E0E; color:#FF6F66; border-color:#D8362F; }}
  .gr-pill.challenge {{ background:#3A2C0E; color:#E0B341; border-color:#E0B341; }}
  .persona-card {{
    background: {BRAND['surface_high']};
    border: 1px solid {BRAND['border']};
    border-radius: 6px;
    padding: 10px 12px;
    margin-bottom: 8px;
  }}
  .persona-card.active {{
    border-color: {BRAND['neon']};
    box-shadow: 0 0 0 1px {BRAND['neon']} inset;
  }}
  .persona-card .name {{ color: {BRAND['neon']}; font-weight: 700; font-size: 14px; }}
  .persona-card .billet {{ color: {BRAND['text_dim']}; font-size: 11px; margin-top: 2px; }}
  .doc-pane {{
    background: {BRAND['surface']}; border: 1px solid {BRAND['border']};
    padding: 12px; border-radius: 4px; height: 540px; overflow-y: auto;
    font-family: Menlo, monospace; font-size: 12px; line-height: 1.55;
    color: #D0D0D0;
  }}
  .marked-pane {{
    background: {BRAND['surface']}; border: 1px solid {BRAND['border']};
    padding: 12px; border-radius: 4px; height: 540px; overflow-y: auto;
  }}
  .para-block {{
    border-left: 3px solid #444; padding: 8px 10px; margin-bottom: 10px;
    background: {BRAND['surface_high']};
    font-family: Menlo, monospace; font-size: 12px; line-height: 1.5;
  }}
  .para-marking {{
    display: inline-block; padding: 2px 8px; border-radius: 3px;
    font-weight: 700; font-size: 11px; letter-spacing: 1px;
    font-family: Menlo, monospace; margin-bottom: 6px;
  }}
  .para-redacted {{
    background: #2A0E0E; border-left-color: #FF6F66 !important;
    color: #FF9C9C; font-style: italic;
  }}
  .banner-line {{
    background: #9A0E0E; color: #FFE; font-weight: 800;
    padding: 6px 12px; letter-spacing: 4px; text-align: center;
    font-family: Menlo, monospace; font-size: 13px; margin-bottom: 10px;
    border-radius: 3px;
  }}
  .gr-stream-row {{
    background: {BRAND['surface_high']}; border: 1px solid {BRAND['border']};
    border-left: 3px solid {BRAND['primary']}; border-radius: 6px;
    padding: 7px 12px; margin-bottom: 5px;
    font-family: Menlo, monospace; font-size: 11px; color: #D8D8D8;
  }}
  .gr-stream-row.block {{ border-left-color: #FF6F66; }}
  .gr-stream-row.challenge {{ border-left-color: #E0B341; }}
  .gr-card {{
    background: {BRAND['surface']}; border: 1px solid {BRAND['border']};
    border-radius: 8px; padding: 14px 18px; margin-bottom: 10px;
  }}
  .deny-box {{
    background: {BRAND['surface_high']}; border: 1px solid {BRAND['border']};
    border-left: 3px solid #FF6F66; padding: 8px 10px; border-radius: 4px;
    margin-bottom: 6px; font-size: 11.5px;
  }}
  .footer {{
    text-align: center; color: {BRAND['muted']}; padding: 14px 8px;
    border-top: 1px solid {BRAND['border']}; margin-top: 22px;
    font-size: 12px; letter-spacing: 1px;
  }}
  .footer .neon {{ color: {BRAND['neon']}; }}
  .footer .kw {{ color: {BRAND['primary']}; font-weight: 700; }}
  div[data-testid="stMetricValue"] {{ color: {BRAND['neon']} !important; }}
  div[data-testid="stMetricLabel"] {{ color: {BRAND['text_dim']} !important; letter-spacing: 0.6px; }}
</style>
"""
st.markdown(CSS, unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Data load
# ---------------------------------------------------------------------------

@st.cache_data
def load_personas() -> list[dict]:
    return json.loads((DATA_DIR / "personas.json").read_text())


@st.cache_data
def load_doc_markings() -> dict:
    p = DATA_DIR / "per_doc_markings.json"
    if not p.exists():
        return {}
    return json.loads(p.read_text())


@st.cache_data
def load_browser_events() -> list[dict]:
    p = DATA_DIR / "browser_events.jsonl"
    if not p.exists():
        return []
    out: list[dict] = []
    with p.open() as f:
        for line in f:
            line = line.strip()
            if line:
                out.append(json.loads(line))
    return out


@st.cache_data
def load_cached_briefs() -> dict:
    p = DATA_DIR / "cached_briefs.json"
    if not p.exists():
        return {}
    return json.loads(p.read_text())


@st.cache_data
def load_taxonomy() -> dict:
    return json.loads((DATA_DIR / "markings_taxonomy.json").read_text())


PERSONAS = load_personas()
DOC_MARK = load_doc_markings()
BROWSER_EVENTS = load_browser_events()
BRIEFS = load_cached_briefs()
TAXONOMY = load_taxonomy()


# ---------------------------------------------------------------------------
# Session state
# ---------------------------------------------------------------------------

if "persona_id" not in st.session_state:
    audit.reset()
    st.session_state.persona_id = PERSONAS[0]["id"]
    st.session_state.doc_id = next(iter(DOC_MARK.keys()))
    st.session_state.browser_idx = 0
    st.session_state.browser_decisions = []  # (event, decision)
    st.session_state.brief_id = next(iter(BRIEFS.keys())) if BRIEFS else None
    st.session_state.brief_override = None
    st.session_state.last_query = ""
    st.session_state.last_answer = None
    st.session_state.last_cited = []
    st.session_state.last_denied = []
    st.session_state.viewed_pairs = set()  # (persona_id, doc_id) pairs we've audited

# ---------------------------------------------------------------------------
# Header
# ---------------------------------------------------------------------------

st.markdown(f"""
<div class="gr-header">
  <h1 class="gr-title">GUARDRAIL</h1>
  <div class="gr-sub">
    Trusted Marine Workspace &middot;
    <span style="color:{BRAND['primary']}">USMC LOGCOM</span> &middot;
    CUI auto-tagging + ABAC + browser-AI governance + hash-chained audit
    &mdash; one verifiable chain across all four layers
  </div>
</div>
""", unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Sidebar — persona switcher + active policies
# ---------------------------------------------------------------------------

with st.sidebar:
    st.markdown("### Persona switcher")
    st.caption("Switch personas to watch ABAC re-redact paragraphs in real time.")
    for p in PERSONAS:
        active = p["id"] == st.session_state.persona_id
        cls = "persona-card active" if active else "persona-card"
        roles_short = ", ".join(p["abac"].get("roles", []) or ["—"])[:40]
        cav = ", ".join(p["abac"].get("caveats_held", []) or [])
        st.markdown(
            f"<div class='{cls}'>"
            f"<div class='name'>{p['icon']} &middot; {p['name']}</div>"
            f"<div class='billet'>{p['rank']} · {p['billet']}</div>"
            f"<div class='billet'>clearance: <b style='color:#E8E8E8'>{p['clearance']}</b></div>"
            f"<div class='billet'>roles: {roles_short}</div>"
            f"<div class='billet'>caveats: {cav or '—'}</div>"
            f"</div>",
            unsafe_allow_html=True,
        )
        if st.button(f"Switch to {p['name']}", key=f"sw_{p['id']}", use_container_width=True, disabled=active):
            st.session_state.persona_id = p["id"]
            st.session_state.last_answer = None  # force re-render
            st.rerun()

    st.markdown("---")
    st.markdown("### Active workspace policies")
    st.markdown(
        "<div class='gr-pill'>CUI auto-tag — DoDM 5200.01 Vol 2</div>"
        "<div class='gr-pill'>ABAC — NIST SP 800-162</div>"
        "<div class='gr-pill block'>Block known browser AI</div>"
        "<div class='gr-pill challenge'>Challenge low-entropy</div>"
        "<div class='gr-pill'>Hash-chained audit (SHA-256)</div>"
        "<div class='gr-pill'>Privacy Act 1974 / DoDD 5230.24</div>",
        unsafe_allow_html=True,
    )

    st.markdown("---")
    st.markdown("### Posture brief scenario")
    if BRIEFS:
        ids = list(BRIEFS.keys())
        labels = [BRIEFS[i]["label"] for i in ids]
        idx = ids.index(st.session_state.brief_id) if st.session_state.brief_id in ids else 0
        chosen_label = st.selectbox("Cached scenario", labels, index=idx, label_visibility="collapsed")
        st.session_state.brief_id = ids[labels.index(chosen_label)]


# Resolve active persona + doc
persona = next(p for p in PERSONAS if p["id"] == st.session_state.persona_id)


# ---------------------------------------------------------------------------
# Persona summary strip
# ---------------------------------------------------------------------------

c1, c2, c3, c4, c5 = st.columns([2, 1, 1, 1, 1])
c1.markdown(
    f"<div class='gr-card'>"
    f"<div style='font-size:10px;color:{BRAND['text_dim']};letter-spacing:1.4px;text-transform:uppercase;'>Active Persona</div>"
    f"<div style='font-size:18px;color:{BRAND['neon']};font-weight:700;'>{persona['icon']} &middot; {persona['name']}</div>"
    f"<div style='font-size:11px;color:{BRAND['text_dim']};'>{persona['rank']} · {persona['billet']} · clearance {persona['clearance']}</div>"
    f"</div>", unsafe_allow_html=True,
)
verify = audit.verify()
c2.metric("Audit chain", verify.get("entries", 0))
c3.metric("Chain integrity", "INTACT" if verify.get("ok") else "BROKEN")
counts = audit.counts_by_layer()
c4.metric("Browser blocks", counts.get("browser_gov_block", 0))
c5.metric("ABAC redactions", counts.get("abac_redaction", 0))


# ---------------------------------------------------------------------------
# Document selector + persona-aware view
# ---------------------------------------------------------------------------

st.markdown("### 1. Workspace document — left: original, right: persona-aware view")

doc_ids = list(DOC_MARK.keys())
labels = [DOC_MARK[d]["title"] for d in doc_ids]
default_idx = doc_ids.index(st.session_state.doc_id) if st.session_state.doc_id in doc_ids else 0
chosen_label = st.selectbox("Open document", labels, index=default_idx, key="doc_pick", label_visibility="collapsed")
doc_id = doc_ids[labels.index(chosen_label)]
st.session_state.doc_id = doc_id

doc = DOC_MARK[doc_id]
paragraphs = doc["paragraphs"]
brief = doc["doc_brief"]
doc_text = (SAMPLES_DIR / f"{doc_id}.txt").read_text()

# Banner line — use the most-restrictive marking
overall = brief.get("overall_marking", "—")
rel = brief.get("releasability", "—")
st.markdown(
    f"<div class='banner-line'>{overall} &nbsp;//&nbsp; {rel}</div>",
    unsafe_allow_html=True,
)

# Audit the view itself (one entry per (persona, doc) pair we render)
pair = (persona["id"], doc_id)
if pair not in st.session_state.viewed_pairs:
    audit.append({
        "layer": "cui_marking",
        "event": "DOCUMENT_OPENED",
        "persona_id": persona["id"],
        "doc_id": doc_id,
        "overall_marking": overall,
        "releasability": rel,
        "paragraph_count": len(paragraphs),
    })
    st.session_state.viewed_pairs.add(pair)

left, right = st.columns(2)
with left:
    st.markdown("**Original draft (raw)**")
    safe = (doc_text or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    safe_html = safe.replace("\n\n", "<br/><br/>").replace("\n", "<br/>")
    st.markdown(f"<div class='doc-pane'>{safe_html}</div>", unsafe_allow_html=True)

# Marking color palette (REDLINE)
MARK_COLOR = {
    "UNCLASSIFIED": ("#0E5132", "#A8FFC9"),
    "CUI//FOUO": ("#5C4E14", "#FFE680"),
    "CUI//SP-PROCURE": ("#3F2A6B", "#D7C2FF"),
    "CUI//SP-PROPIN": ("#4B2A6B", "#E0BFFF"),
    "CUI//SP-PRVCY": ("#2C4F87", "#B5D8FF"),
    "CUI//SP-OPSEC": ("#6B2A2A", "#FFB5B5"),
    "CUI//SP-EXPT": ("#7A1F1F", "#FF9C9C"),
    "CUI//SP-NF": ("#9A0E0E", "#FFC2C2"),
    "SECRET": ("#2A0E0E", "#FF6F66"),
    "TOP SECRET//SCI": ("#0E0E2A", "#FF8A8A"),
}

with right:
    st.markdown(f"**ABAC-filtered view for {persona['name']}**")
    blocks: list[str] = []
    redact_count = 0
    allow_count = 0
    for para in paragraphs:
        ok, reason = authorize_paragraph(persona, para)
        marking = para.get("recommended_marking", "UNCLASSIFIED")
        bg, fg = MARK_COLOR.get(marking, ("#222222", "#E8E8E8"))
        text = para.get("paragraph_text", "")
        ptext_html = (text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
                          .replace("\n", "<br/>"))
        muted = BRAND['muted']
        if ok:
            allow_count += 1
            blocks.append(
                f"<div class=\"para-block\" style=\"border-left-color:{fg};\">"
                f"<span class=\"para-marking\" style=\"background:{bg}; color:{fg};\">{marking}</span>"
                f"<span style=\"color:{muted}; font-size:10px; margin-left:8px;\">¶ {para['paragraph_index']}</span>"
                f"<div style=\"margin-top:4px\">{ptext_html}</div>"
                f"</div>"
            )
        else:
            redact_count += 1
            blocks.append(
                f"<div class=\"para-block para-redacted\">"
                f"<span class=\"para-marking\" style=\"background:#3A0E0E; color:#FF6F66;\">REDACTED</span>"
                f"<span style=\"color:{muted}; font-size:10px; margin-left:8px;\">¶ {para['paragraph_index']}</span>"
                f"<div style=\"margin-top:6px\">{redaction_text(persona, para, reason)}</div>"
                f"</div>"
            )
            # Audit each redaction (once per persona/doc/¶)
            audit_key = ("redact", persona["id"], doc_id, para["paragraph_index"])
            if audit_key not in st.session_state.viewed_pairs:
                audit.append({
                    "layer": "abac_redaction",
                    "event": "PARAGRAPH_REDACTED",
                    "persona_id": persona["id"],
                    "doc_id": doc_id,
                    "paragraph_index": para["paragraph_index"],
                    "marking": marking,
                    "reason": reason,
                })
                st.session_state.viewed_pairs.add(audit_key)
    st.markdown(f"<div class='marked-pane'>{''.join(blocks)}</div>", unsafe_allow_html=True)
    st.caption(
        f"{allow_count} paragraphs visible · {redact_count} redacted by ABAC "
        f"(NIST SP 800-162). Switch personas to watch the redactions move."
    )

# ---------------------------------------------------------------------------
# Browser AI gov live intercept feed
# ---------------------------------------------------------------------------

st.markdown("### 2. Browser-AI governance — live intercept feed")
st.caption(
    "Workspace boundary screens every browser event. Comet, manus.im, Skyvern, "
    "and other browser-resident AI agents are BLOCKED before they can read CUI. "
    "Each decision is appended to the unified audit chain."
)

bcols = st.columns([1, 1, 1, 5])
if bcols[0].button("STREAM 5 EVENTS", key="bs5"):
    st.session_state.browser_idx = min(st.session_state.browser_idx + 5, len(BROWSER_EVENTS))
if bcols[1].button("STREAM 20", key="bs20"):
    st.session_state.browser_idx = min(st.session_state.browser_idx + 20, len(BROWSER_EVENTS))
if bcols[2].button("RESET FEED", key="bsr"):
    st.session_state.browser_idx = 0
    st.session_state.browser_decisions = []

# Process pending events
already = len(st.session_state.browser_decisions)
target = st.session_state.browser_idx
for i in range(already, target):
    ev = BROWSER_EVENTS[i]
    decision = browser_classify(ev)
    st.session_state.browser_decisions.append((ev, decision))
    if decision["policy_action"] == "BLOCK":
        audit.append({
            "layer": "browser_gov_block",
            "event": "BROWSER_AI_BLOCKED",
            "event_id": ev["event_id"],
            "endpoint": ev["endpoint"],
            "data_class": ev["data_class"],
            "agent_detected": decision["agent_detected"],
            "confidence": decision["confidence"],
            "rationale": decision["rationale"],
        })
    elif decision["policy_action"] == "ALLOW":
        # don't audit allows individually — too noisy; collapse
        pass
    else:
        audit.append({
            "layer": "browser_gov_challenge",
            "event": "BROWSER_AI_CHALLENGED",
            "event_id": ev["event_id"],
            "endpoint": ev["endpoint"],
            "agent_detected": decision["agent_detected"],
            "confidence": decision["confidence"],
            "rationale": decision["rationale"],
        })

bleft, bright = st.columns([5, 7])
with bleft:
    st.markdown("**Intercept feed**")
    recent = list(reversed(st.session_state.browser_decisions[-12:]))
    if not recent:
        st.info("Click STREAM to start the live intercept feed.")
    for ev, d in recent:
        ts = ev["timestamp_utc"].split("T")[1][:8]
        action = d["policy_action"]
        cls = "block" if action == "BLOCK" else ("challenge" if action == "CHALLENGE_HUMAN" else "")
        action_pill = {
            "ALLOW": "<span class='gr-pill allow'>ALLOW</span>",
            "BLOCK": "<span class='gr-pill block'>BLOCK</span>",
            "CHALLENGE_HUMAN": "<span class='gr-pill challenge'>CHALLENGE</span>",
        }.get(action, f"<span class='gr-pill'>{action}</span>")
        st.markdown(
            f"<div class='gr-stream-row {cls}'>"
            f"<span style='color:{BRAND['muted']}'>{ts}Z</span> · "
            f"<code>{ev['endpoint']}</code> · "
            f"<span style='color:#E0B341'>{ev['data_class']}</span> · "
            f"<b style='color:#FF9C9C'>{d['agent_detected']}</b> "
            f"({d['confidence']:.2f}) {action_pill}"
            f"</div>",
            unsafe_allow_html=True,
        )

with bright:
    st.markdown("**Decision rationale (most-recent BLOCKs)**")
    blocks_recent = [(e, d) for e, d in reversed(st.session_state.browser_decisions[-30:])
                     if d["policy_action"] == "BLOCK"][:6]
    if not blocks_recent:
        st.info("No blocks yet. Stream events to see the workspace boundary fire.")
    for ev, d in blocks_recent:
        st.markdown(
            f"<div class='deny-box'>"
            f"<b style='color:#FF6F66;'>BLOCK · {d['agent_detected']}</b> "
            f"<span style='color:{BRAND['muted']};'>(conf {d['confidence']:.2f})</span>"
            f"<div style='color:#E8E8E8; font-size:11.5px; margin-top:4px;'>"
            f"<code>{ev['endpoint']}</code> · {ev['data_class']}"
            f"</div>"
            f"<div style='color:{BRAND['text_dim']}; font-size:11px; margin-top:4px;'>"
            f"{' · '.join(d['signals_observed'][:3])}</div>"
            f"</div>",
            unsafe_allow_html=True,
        )

# ---------------------------------------------------------------------------
# Role-aware AI assistant
# ---------------------------------------------------------------------------

st.markdown("### 3. Role-aware AI assistant — RAG over the workspace, ABAC enforced")
st.caption(
    "The AI assistant retrieves only paragraphs the active persona is "
    "authorized to read. Denied paragraphs surface in the permission audit."
)

# Build full chunk corpus across all docs
ALL_CHUNKS: list[dict] = []
for did, dd in DOC_MARK.items():
    for p in dd["paragraphs"]:
        ALL_CHUNKS.append({
            "doc_id": did,
            "paragraph_index": p["paragraph_index"],
            "paragraph_text": p["paragraph_text"],
            "recommended_marking": p.get("recommended_marking", "UNCLASSIFIED"),
            "caveats_recommended": p.get("caveats_recommended", []) or [],
        })

SAMPLE_QUERIES = [
    "What is the FPCON posture and manning roster guidance for IRON GUARDRAIL?",
    "What are the vendor labor rates and ITAR controls in the predictive-maintenance SOW?",
    "Who can view the SECRET//NOFORN intel summary key judgments and why?",
    "How does a contractor enroll in the FY26 Annual Information Security Refresher?",
]

qcol, bcol = st.columns([5, 1])
with qcol:
    q = st.text_area(
        "Ask the workspace AI assistant",
        value=st.session_state.last_query or SAMPLE_QUERIES[0],
        height=80,
        label_visibility="collapsed",
        placeholder="Ask GUARDRAIL — e.g. 'What is the FPCON posture for IRON GUARDRAIL?'",
        key="ai_query",
    )
with bcol:
    st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)
    ask = st.button("Ask GUARDRAIL", use_container_width=True, type="primary")

with st.expander("Sample questions", expanded=False):
    for i, sq in enumerate(SAMPLE_QUERIES):
        if st.button(f"-> {sq}", key=f"qex_{i}"):
            st.session_state.last_query = sq
            st.session_state.last_answer = None
            st.rerun()

if ask or (q.strip() and st.session_state.last_answer is None) or st.session_state.last_query != q:
    if q.strip():
        cited, denied = retrieve(persona, q, ALL_CHUNKS, k=4)
        with st.spinner("Drafting persona-aware answer (ABAC-filtered RAG)…"):
            answer = render_answer(persona, q, cited, hero=False, timeout=18)
        st.session_state.last_query = q
        st.session_state.last_answer = answer
        st.session_state.last_cited = cited
        st.session_state.last_denied = denied
        # Audit the AI query (cite + deny counts hashed in)
        audit.append({
            "layer": "ai_assist_query",
            "event": "AI_QUERY_ANSWERED",
            "persona_id": persona["id"],
            "query": q[:200],
            "cited_count": len(cited),
            "denied_count": len(denied),
            "cited_ids": [f"{c['doc_id']}#{c['paragraph_index']}" for c in cited],
        })

if st.session_state.last_answer:
    al, ar = st.columns([1.4, 1.0])
    with al:
        st.markdown("##### Answer (uses ONLY authorized paragraphs)")
        neon = BRAND['neon']
        primary = BRAND['primary']
        st.markdown(
            f"<div class='gr-card' style='border-left:4px solid {neon};'>"
            f"{st.session_state.last_answer}</div>",
            unsafe_allow_html=True,
        )
        st.markdown("##### Cited paragraphs")
        for c in st.session_state.last_cited:
            st.markdown(
                f"<div class='deny-box' style='border-left-color:{primary};'>"
                f"<b style='color:{neon};'>[{c['doc_id']} ¶{c['paragraph_index']}]</b> "
                f"<span class='gr-pill'>{c['recommended_marking']}</span>"
                f"<div style='color:#CCC;font-size:11.5px;margin-top:4px;'>"
                f"{c['paragraph_text'][:240]}…</div>"
                f"</div>",
                unsafe_allow_html=True,
            )
        if not st.session_state.last_cited:
            st.warning("No paragraphs were authorized for this persona on this query.")

    with ar:
        st.markdown("##### Permission audit — denied paragraphs")
        st.caption("Paragraphs the retriever WOULD have used, blocked by ABAC.")
        if not st.session_state.last_denied:
            st.success("No relevant paragraphs were denied for this persona.")
        for d in st.session_state.last_denied[:6]:
            st.markdown(
                f"<div class='deny-box'>"
                f"<b style='color:#FF6F66;'>[{d['doc_id']} ¶{d['paragraph_index']}]</b> "
                f"<span class='gr-pill block'>{d['recommended_marking']}</span>"
                f"<div style='color:#E8E8E8;font-size:11px;margin-top:4px;'>{d['_deny_reason']}</div>"
                f"</div>",
                unsafe_allow_html=True,
            )

# ---------------------------------------------------------------------------
# Hash-chained audit log (cross-layer)
# ---------------------------------------------------------------------------

st.markdown("### 4. Hash-chained audit log — one chain across all four layers")

chain = audit.read(limit=14)
if not chain:
    st.info("Audit chain empty. Open a doc, switch personas, or stream events to seed it.")
else:
    rows = []
    for c in chain:
        rows.append({
            "ts": (c.get("timestamp_utc") or "")[11:19],
            "layer": c.get("layer", "?"),
            "event": c.get("event", "?"),
            "persona": c.get("persona_id") or "—",
            "ref": c.get("doc_id") or c.get("event_id") or "—",
            "detail": (c.get("reason") or c.get("rationale") or
                       c.get("query") or c.get("marking") or "—")[:60],
            "prev": (c.get("prev_hash") or "")[:10] + "…",
            "this": (c.get("entry_hash") or "")[:10] + "…",
        })
    df = pd.DataFrame(rows)

    def _color_layer(val: str) -> str:
        return {
            "cui_marking": "background-color:#0E2F22; color:#A8FFC9;",
            "abac_redaction": "background-color:#2A0E0E; color:#FF9C9C;",
            "browser_gov_block": "background-color:#3A0E0E; color:#FF6F66;",
            "browser_gov_challenge": "background-color:#3A2C0E; color:#E0B341;",
            "ai_assist_query": "background-color:#0E2A3A; color:#56C6FF;",
        }.get(val, "")
    try:
        styled = df.style.map(_color_layer, subset=["layer"])
    except AttributeError:
        styled = df.style.applymap(_color_layer, subset=["layer"])  # pandas <2.1
    st.dataframe(styled, use_container_width=True, hide_index=True, height=380)

    vc1, vc2 = st.columns([1, 5])
    if vc1.button("VERIFY CHAIN", key="verify_chain"):
        v = audit.verify()
        if v["ok"]:
            vc2.success(f"Chain INTACT — {v['entries']} entries verified · tip {v['tip_hash'][:14]}…")
        else:
            vc2.error(f"BROKEN at row {v.get('broken_at')} · {v.get('reason')}")


# ---------------------------------------------------------------------------
# Hero — Workspace Governance Posture Brief (cache-first)
# ---------------------------------------------------------------------------

st.markdown("### 5. Workspace Governance Posture Brief — hero output")
st.caption(
    "Hero call: a long-form posture brief drafted by the Kamiwaza-deployed "
    "hero model. Cache-first per AGENT_BRIEF_V2 — pre-computed at synth time, "
    "regeneratable on demand."
)

if BRIEFS and st.session_state.brief_id:
    chosen = BRIEFS[st.session_state.brief_id]
    body = st.session_state.brief_override or chosen["brief_markdown"]
    s = chosen["stats"]
    sc1, sc2, sc3, sc4, sc5 = st.columns(5)
    sc1.metric("Documents", s["documents_open"])
    sc2.metric("Paragraphs marked", s["paragraphs_marked"])
    sc3.metric("ABAC redactions", s["abac_redactions"])
    sc4.metric("Browser-AI blocks", s["browser_ai_blocks"])
    sc5.metric("Audit entries", s["audit_chain_entries"])

    st.markdown(f"<div class='gr-card'>{body}</div>", unsafe_allow_html=True)

    rb1, rb2 = st.columns([1, 5])
    if rb1.button("REGENERATE LIVE", key="regen_brief"):
        with st.spinner("Drafting brief on the Kamiwaza-deployed hero model (≤35s)…"):
            try:
                from shared.kamiwaza_client import chat
                prompt = (
                    "You are a USMC LOGCOM cyber-governance analyst. Draft a "
                    "Workspace Governance Posture Brief for the scenario below. "
                    "Sections: BLUF, Top exfil vectors blocked, CUI exposure surface, "
                    "Recommended policy tightening, Authority anchors. ~280 words. "
                    "Cite DoDM 5200.01 Vol 2, 32 CFR Part 2002, NIST SP 800-162.\n\n"
                    f"Scenario: {chosen['label']}\n"
                    f"Stats: {json.dumps(s)}\n"
                )

                def _run() -> str:
                    return chat(
                        [{"role": "system", "content": "You are precise, defense-grade, no fluff."},
                         {"role": "user", "content": prompt}],
                        model=os.getenv("LLM_HERO_MODEL", os.getenv("LLM_PRIMARY_MODEL", "gpt-5.4")),
                        temperature=0.3,
                    )

                with ThreadPoolExecutor(max_workers=1) as ex:
                    new_body = ex.submit(_run).result(timeout=35)
                st.session_state.brief_override = new_body
                st.rerun()
            except Exception as e:  # noqa: BLE001
                rb2.warning(f"Live call timed out / failed; cached brief retained. ({e})")


# ---------------------------------------------------------------------------
# Footer — Kamiwaza beat
# ---------------------------------------------------------------------------

endpoint = os.getenv("KAMIWAZA_BASE_URL") or "Kamiwaza-deployed model (env-var swap to on-prem)"
st.markdown(f"""
<div class='footer'>
  <span class='neon'>The whole workspace stays inside the SCIF.</span>
  Set <code>KAMIWAZA_BASE_URL</code> and the same code routes through a
  vLLM-served model inside your accredited boundary.
  IL5/IL6 ready · NIPR/SIPR/JWICS deployable · DDIL-tolerant.<br/>
  Inference endpoint: <code>{endpoint}</code><br/>
  <span class='kw'>Powered by Kamiwaza</span>
</div>
""", unsafe_allow_html=True)
