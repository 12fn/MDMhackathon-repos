"""AGORA — Persona + role-aware AI support agent for a USMC web ecosystem.

Run:
    streamlit run src/app.py --server.port 3033 --server.headless true \
        --server.runOnSave false --server.fileWatcherType none \
        --browser.gatherUsageStats false
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import streamlit as st

ROOT = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(ROOT))
APP = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(APP))

from shared.kamiwaza_client import BRAND  # noqa: E402
from src.retrieval import (  # noqa: E402
    answer_for_persona, load_personas, load_corpus,
    load_cached_briefs, authorize_doc, ROLE_RANK,
)

st.set_page_config(
    page_title="AGORA — Role-Aware AI Support",
    page_icon=":shield:",
    layout="wide",
    initial_sidebar_state="expanded",
)

CSS = f"""
<style>
  .stApp {{ background: {BRAND['bg']}; color: #E8E8E8; }}
  [data-testid="stHeader"] {{ background: transparent; }}
  [data-testid="stToolbar"] {{ display: none; }}
  section[data-testid="stSidebar"] {{
    background: {BRAND['surface']};
    border-right: 1px solid {BRAND['border']};
  }}
  .agora-hero {{
    background: linear-gradient(135deg, {BRAND['surface']} 0%, {BRAND['bg']} 100%);
    border: 1px solid {BRAND['border']};
    border-left: 4px solid {BRAND['primary']};
    border-radius: 8px;
    padding: 16px 22px;
    margin-bottom: 12px;
  }}
  .agora-hero h1 {{
    color: {BRAND['neon']};
    font-family: 'Helvetica Neue', sans-serif;
    font-size: 26px;
    margin: 0;
    letter-spacing: -0.5px;
  }}
  .agora-hero p {{
    color: {BRAND['text_dim']};
    margin: 4px 0 0 0;
    font-size: 13px;
  }}
  .agora-pill {{
    display: inline-block;
    background: {BRAND['surface_high']};
    color: {BRAND['primary']};
    border: 1px solid {BRAND['primary']};
    border-radius: 999px;
    padding: 2px 10px;
    font-size: 11px;
    margin-right: 6px;
    letter-spacing: 0.5px;
  }}
  .agora-card {{
    background: {BRAND['surface']};
    border: 1px solid {BRAND['border']};
    border-radius: 6px;
    padding: 12px 16px;
    margin-bottom: 8px;
  }}
  .agora-persona {{
    border-radius: 6px;
    padding: 10px 12px;
    margin-bottom: 8px;
    border: 1px solid {BRAND['border']};
    background: {BRAND['surface_high']};
  }}
  .agora-persona.active {{
    border-color: {BRAND['neon']};
    box-shadow: 0 0 0 1px {BRAND['neon']} inset;
  }}
  .agora-persona .name {{
    color: {BRAND['neon']};
    font-weight: 700;
    font-size: 14px;
  }}
  .agora-persona .billet {{
    color: {BRAND['text_dim']};
    font-size: 11px;
    margin-top: 2px;
  }}
  .agora-allow {{ color: {BRAND['primary']}; font-weight: 600; }}
  .agora-deny  {{ color: #FF6B6B; font-weight: 600; }}
  .agora-cite {{
    background: {BRAND['surface_high']};
    border: 1px solid {BRAND['border']};
    border-left: 3px solid {BRAND['primary']};
    padding: 10px 12px;
    border-radius: 4px;
    margin-bottom: 6px;
  }}
  .agora-deny-box {{
    background: {BRAND['surface_high']};
    border: 1px solid {BRAND['border']};
    border-left: 3px solid #FF6B6B;
    padding: 8px 10px;
    border-radius: 4px;
    margin-bottom: 6px;
    font-size: 12px;
  }}
  .agora-footer {{
    color: {BRAND['text_dim']};
    font-size: 12px;
    text-align: center;
    padding: 16px 0 4px 0;
    border-top: 1px solid {BRAND['border']};
    margin-top: 28px;
  }}
  .agora-footer span {{ color: {BRAND['primary']}; font-weight: 600; }}
  div.stButton > button:first-child {{
    background: {BRAND['primary']};
    color: #000;
    border: 0;
    font-weight: 600;
    border-radius: 4px;
    padding: 6px 18px;
  }}
  div.stButton > button:hover {{
    background: {BRAND['primary_hover']};
    color: #000;
  }}
  textarea, input {{
    background: {BRAND['surface_high']} !important;
    color: #E8E8E8 !important;
    border-color: {BRAND['border']} !important;
  }}
  hr {{ border-color: {BRAND['border']}; }}
  .agora-kbd {{
    font-family: 'SFMono-Regular', Menlo, monospace;
    background: #000;
    border: 1px solid {BRAND['border']};
    border-radius: 3px;
    padding: 1px 6px;
    color: {BRAND['neon']};
    font-size: 11px;
  }}
</style>
"""
st.markdown(CSS, unsafe_allow_html=True)

# ── Hero ─────────────────────────────────────────────────────────────────
HERO = f"""
<div class="agora-hero">
  <h1>AGORA — Role-Aware AI Support Agents</h1>
  <p><strong>Multi-Model JIT Context+Role-Aware AI Support for Web Ecosystems</strong> &nbsp;·&nbsp;
     Persona + ABAC/RBAC-filtered RAG over a 60-doc ecosystem corpus (LMS · CMS · BBB · Keycloak)</p>
  <p style="margin-top:8px;">
    <span class="agora-pill">Persona-Aware RAG</span>
    <span class="agora-pill">ABAC + RBAC Audit</span>
    <span class="agora-pill">Cache-First</span>
    <span class="agora-pill">USMC LOGCOM 2026</span>
  </p>
</div>
"""
st.markdown(HERO, unsafe_allow_html=True)

# ── Load data ────────────────────────────────────────────────────────────
PERSONAS = load_personas()
DOCS = load_corpus()
CACHE = load_cached_briefs()

if "persona_id" not in st.session_state:
    st.session_state.persona_id = PERSONAS[0]["id"]

# ── Sidebar: persona switcher + permission audit ─────────────────────────
with st.sidebar:
    st.markdown(f"### Persona switcher")
    st.caption("Switch personas to watch ABAC/RBAC re-filter the same query in real time.")
    for p in PERSONAS:
        active = p["id"] == st.session_state.persona_id
        cls = "agora-persona active" if active else "agora-persona"
        roles_short = " · ".join(
            f"{a}:{r['role']}" for a, r in p["roles"].items() if r["role"] != "none"
        ) or "no app roles"
        st.markdown(
            f'<div class="{cls}">'
            f'<div class="name">{p["icon"]} &nbsp; {p["name"]}</div>'
            f'<div class="billet">{p["rank"]} · {p["billet"]}</div>'
            f'<div class="billet" style="margin-top:4px;">{roles_short}</div>'
            f'<div class="billet" style="margin-top:4px;">max_class: {p["abac"]["max_class"]} · '
            f'unit_scope: {", ".join(p["abac"]["unit_scope"]) or "—"}</div>'
            f'</div>',
            unsafe_allow_html=True,
        )
        if st.button(f"Switch to {p['name']}", key=f"sw_{p['id']}", use_container_width=True,
                     disabled=active):
            st.session_state.persona_id = p["id"]
            # Clear any cached result so the new persona re-evaluates
            for k in ("last_result", "last_query"):
                st.session_state.pop(k, None)
            st.rerun()

    st.markdown("---")
    st.markdown("### Corpus")
    by_app: dict = {}
    for d in DOCS:
        by_app[d["app"]] = by_app.get(d["app"], 0) + 1
    for a, n in by_app.items():
        st.markdown(
            f'<div style="font-size:12px;color:{BRAND["text_dim"]};">'
            f'<span class="agora-kbd">{a}</span> &nbsp; {n} docs</div>',
            unsafe_allow_html=True,
        )
    st.caption(f"Total: {len(DOCS)} docs across {len(by_app)} apps.")

# ── Active persona summary ───────────────────────────────────────────────
persona = next(p for p in PERSONAS if p["id"] == st.session_state.persona_id)
c1, c2, c3, c4 = st.columns(4)

# Pre-compute global readable counts for the active persona (independent of query)
readable_per_app = {a: 0 for a in ("LMS", "CMS", "BBB", "Keycloak")}
for d in DOCS:
    ok, _ = authorize_doc(persona, d)
    if ok:
        readable_per_app[d["app"]] = readable_per_app.get(d["app"], 0) + 1

c1.markdown(
    f'<div class="agora-card"><div style="font-size:11px;color:{BRAND["text_dim"]};letter-spacing:1.2px;text-transform:uppercase;">Active Persona</div>'
    f'<div style="font-size:18px;color:{BRAND["neon"]};font-weight:700;">{persona["name"]}</div>'
    f'<div style="font-size:11px;color:{BRAND["text_dim"]};">{persona["rank"]} · {persona["billet"]}</div></div>',
    unsafe_allow_html=True,
)
for col, app in zip((c2, c3, c4), ("LMS", "CMS", "Keycloak")):
    role = persona["roles"].get(app, {}).get("role", "none")
    n = readable_per_app[app]
    col.markdown(
        f'<div class="agora-card"><div style="font-size:11px;color:{BRAND["text_dim"]};letter-spacing:1.2px;text-transform:uppercase;">{app}</div>'
        f'<div style="font-size:18px;color:{BRAND["neon"]};font-weight:700;">role: {role}</div>'
        f'<div style="font-size:11px;color:{BRAND["text_dim"]};">{n} readable docs</div></div>',
        unsafe_allow_html=True,
    )

st.markdown("&nbsp;")

# ── Query bar ────────────────────────────────────────────────────────────
SCENARIOS = list(CACHE.get("scenarios", {}).items())
SCENARIO_QUERIES = [v["query"] for _, v in SCENARIOS] if SCENARIOS else [
    "How do I pull a battalion-wide transcript report and approve a CUI course for publication?",
    "I'm a vendor — can I see uniformed Marines' transcripts and edit a battalion announcement?",
    "I forgot my password and I need to enroll in the new MarineNet course. What do I do?",
]

if "query" not in st.session_state:
    st.session_state.query = SCENARIO_QUERIES[0]

cq, cb = st.columns([5, 1])
with cq:
    q = st.text_area(
        "Ecosystem support question",
        value=st.session_state.query,
        height=80,
        label_visibility="collapsed",
        placeholder="Ask AGORA — e.g. 'How do I approve a CUI course?'",
    )
with cb:
    st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)
    run = st.button("Ask AGORA", use_container_width=True, type="primary")
    hero = st.toggle("Hero model", value=False, help="Route to the Kamiwaza-deployed hero model")

with st.expander("Sample scenarios", expanded=False):
    for i, sq in enumerate(SCENARIO_QUERIES):
        if st.button(f"-> {sq}", key=f"ex_{i}"):
            st.session_state.query = sq
            st.session_state.pop("last_result", None)
            st.rerun()

# ── Run pipeline (cache-first) ───────────────────────────────────────────
def _maybe_cached(query: str, persona_id: str) -> dict | None:
    """Return a cached brief if the query matches a known scenario."""
    for sid, sc in CACHE.get("scenarios", {}).items():
        if sc.get("query", "").strip() == query.strip():
            per = sc.get("by_persona", {}).get(persona_id)
            if per and per.get("answer") and not per["answer"].startswith("(cache miss"):
                return {"_cached": True, "scenario_id": sid, **per}
    return None


need_run = run or "last_result" not in st.session_state or st.session_state.get("last_query") != q
if need_run and q.strip():
    cached = _maybe_cached(q, persona["id"])
    if cached and not run:
        # Show cached + denied set materialized live (cheap, no LLM call)
        # We still re-run authorization to get a fresh denied list with reasons.
        live_denied: list = []
        live_allowed_count = 0
        for d in DOCS:
            ok, why = authorize_doc(persona, d)
            if ok:
                live_allowed_count += 1
            else:
                live_denied.append({
                    "doc_id": d["doc_id"], "app": d["app"], "title": d["title"],
                    "min_role": d["min_role"], "classification": d["classification"],
                    "scope": d["scope"], "reason": why,
                })
        st.session_state.last_result = {
            "persona": persona,
            "intent": {"target_apps": [c["app"] for c in cached.get("cited_docs", [])],
                       "topic": q[:64], "action": "view",
                       "needs_role_at_least": "viewer", "sensitive": False,
                       "rationale": "Cached scenario — intent shown abbreviated."},
            "cited": [{**next((dd for dd in DOCS if dd["doc_id"] == c["doc_id"]), {}),
                       "similarity": 0.0} for c in cached.get("cited_docs", [])],
            "denied_top": live_denied,
            "raw_top_ids": [c["doc_id"] for c in cached.get("cited_docs", [])],
            "answer": cached["answer"],
            "_cached": True,
        }
    else:
        with st.status("Persona-aware RAG over the ecosystem corpus...", expanded=True) as status:
            st.write("- Parsing intent + persona role tree (chat_json)")
            st.write("- Authorizing every doc against persona ABAC/RBAC")
            st.write(f"- Embedding query and cosine-ranking authorized docs ({len(DOCS)} total)")
            st.write("- Hero answer using ONLY authorized docs, with citations")
            res = answer_for_persona(persona["id"], q, k=3, hero=hero)
            st.session_state.last_result = res
            status.update(label="Retrieval + auth complete.", state="complete", expanded=False)
    st.session_state.last_query = q

result = st.session_state.get("last_result")

# ── Layout: answer + permission audit ────────────────────────────────────
if result:
    left, right = st.columns([1.5, 1.0])
    with left:
        st.markdown("##### Answer")
        if result.get("_cached"):
            st.caption("Served from cached brief (cache-first pattern). Click 'Ask AGORA' to refresh live.")
        st.markdown(
            f'<div class="agora-card" style="border-left:4px solid {BRAND["neon"]};">{result["answer"]}</div>',
            unsafe_allow_html=True,
        )

        st.markdown("##### Citations (authorized docs)")
        for d in result["cited"]:
            st.markdown(
                f'<div class="agora-cite">'
                f'<span class="agora-allow">[{d["doc_id"]}]</span> '
                f'<strong>{d["title"]}</strong> '
                f'<span style="color:{BRAND["text_dim"]};font-size:11px;">'
                f'  {d["app"]} · min_role={d["min_role"]} · class={d["classification"]} · scope={d["scope"]}'
                f'</span>'
                f'<div style="color:#CCC;font-size:12px;margin-top:4px;">{d["body"][:240]}…</div>'
                f'</div>',
                unsafe_allow_html=True,
            )
        if not result["cited"]:
            st.warning("No authorized docs matched. Persona may need elevated access.")

        with st.expander("Parsed intent (LLM-structured)", expanded=False):
            st.json(result.get("intent", {}))

    with right:
        st.markdown("##### Permission audit")
        st.caption("Docs the model would have seen — but did NOT — under this persona.")

        # Highlight: what would have been retrieved without ABAC vs. what got cited
        cited_ids = {d["doc_id"] for d in result["cited"]}
        raw_ids = result.get("raw_top_ids", [])
        excluded_top = [r for r in raw_ids if r not in cited_ids]
        if excluded_top:
            st.markdown(
                f'<div class="agora-deny-box">'
                f'<span class="agora-deny">EXCLUDED FROM TOP-K:</span> '
                f'{", ".join(excluded_top)} '
                f'— these would have ranked highest without role filtering.'
                f'</div>',
                unsafe_allow_html=True,
            )
        else:
            st.markdown(
                f'<div class="agora-deny-box" style="border-left-color:{BRAND["primary"]};">'
                f'<span class="agora-allow">No top-K exclusions</span> — '
                f'this persona was authorized for everything the ranker preferred.'
                f'</div>',
                unsafe_allow_html=True,
            )

        # Show top denials (most relevant misses)
        denied = result.get("denied_top", [])
        st.markdown(f"**Denied docs ({len(denied)} total)** — top relevant shown:")
        # Sort: prefer docs that target the intent's apps
        target_apps = set(result.get("intent", {}).get("target_apps", []))
        denied_sorted = sorted(denied, key=lambda d: (0 if d["app"] in target_apps else 1, d["doc_id"]))
        for d in denied_sorted[:8]:
            st.markdown(
                f'<div class="agora-deny-box">'
                f'<span class="agora-deny">[{d["doc_id"]}]</span> '
                f'<strong style="color:#E8E8E8;">{d["title"]}</strong>'
                f'<span style="color:{BRAND["text_dim"]};font-size:11px;"> · {d["app"]}</span>'
                f'<div style="color:{BRAND["text_dim"]};font-size:11px;margin-top:2px;">{d["reason"]}</div>'
                f'</div>',
                unsafe_allow_html=True,
            )
        if len(denied) > 8:
            st.caption(f"...and {len(denied)-8} more denials. Toggle persona to see them open up.")

# ── Footer ───────────────────────────────────────────────────────────────
import os
endpoint = os.getenv("KAMIWAZA_BASE_URL") or "Kamiwaza-deployed model (env-var swap to on-prem)"
st.markdown(
    f'<div class="agora-footer">'
    f'<span>Powered by Kamiwaza</span> &nbsp;·&nbsp; '
    f'Inference endpoint: <code>{endpoint}</code> &nbsp;·&nbsp; '
    f'Synthetic stand-in for a real Keycloak realm export + LMS/CMS/BBB/Keycloak help corpus'
    f'</div>',
    unsafe_allow_html=True,
)
