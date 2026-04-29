"""OMNI-AGENT — Streamlit mono-page meta-orchestrator.

Single page, three regions:
  - Left rail: governed Tool Shed (14 sibling apps) + KAMIWAZA env-var beat
  - Center:    operator query box + cached demos + the streamed brief
  - Right rail: live tool-call trace + hash-chained audit log

Cache-first: 5 demo queries pre-warmed to data/cached_briefs.json so the
demo recording is snappy. Live-call mode fires the real agent loop.
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

# Allow `from src.X` imports when streamlit launches src/app.py directly
ROOT = Path(__file__).resolve().parents[3]
APP_ROOT = Path(__file__).resolve().parents[1]
for p in (ROOT, APP_ROOT):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

import streamlit as st

from shared.kamiwaza_client import BRAND, PROVIDER  # noqa: E402

from src.agent import stream_run  # noqa: E402
from src import audit  # noqa: E402

DATA_DIR = APP_ROOT / "data"


# ─────────────────────────────────────────────────────────────────────────────
# Page config + brand CSS
# ─────────────────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="OMNI-AGENT — Kamiwaza Meta-Orchestrator",
    page_icon="◆",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(f"""
<style>
.stApp {{
    background: {BRAND['bg']};
    color: #E6E6E6;
}}
[data-testid="stSidebar"] {{
    background: {BRAND['surface']};
    border-right: 1px solid {BRAND['border']};
}}
.kw-pill {{
    display: inline-block; padding: 2px 10px; border-radius: 999px;
    background: {BRAND['surface_high']}; border: 1px solid {BRAND['border']};
    color: {BRAND['neon']}; font-size: 11px; font-weight: 600;
    letter-spacing: 0.04em; margin-right: 6px;
}}
.kw-tool-card {{
    padding: 8px 10px; margin-bottom: 6px;
    background: {BRAND['surface_high']};
    border: 1px solid {BRAND['border']};
    border-left: 3px solid {BRAND['primary']};
    border-radius: 6px; font-size: 12.5px;
}}
.kw-tool-card .codename {{ color: {BRAND['neon']}; font-weight: 700; }}
.kw-tool-card .meta {{ color: {BRAND['muted']}; font-size: 11px; }}
.kw-trace {{
    padding: 8px 10px; margin-bottom: 4px;
    background: {BRAND['surface']};
    border: 1px solid {BRAND['border']};
    border-radius: 6px; font-family: ui-monospace, SFMono-Regular, monospace;
    font-size: 12px;
}}
.kw-trace.user {{ border-left: 3px solid #88AAEE; }}
.kw-trace.tool_call {{ border-left: 3px solid {BRAND['primary']}; }}
.kw-trace.tool_result {{ border-left: 3px solid {BRAND['neon']}; }}
.kw-trace.model {{ border-left: 3px solid #DDDDDD; }}
.kw-trace.final {{ border-left: 3px solid #FFD700;
                    background: {BRAND['surface_high']}; }}
.kw-brief {{
    padding: 16px 18px; background: {BRAND['surface_high']};
    border: 1px solid {BRAND['border']}; border-radius: 8px;
    border-left: 4px solid {BRAND['primary']};
    font-family: ui-monospace, SFMono-Regular, monospace; font-size: 13px;
    white-space: pre-wrap;
}}
.kw-footer {{
    color: {BRAND['muted']}; text-align: center; padding-top: 24px;
    font-size: 11px; letter-spacing: 0.06em; text-transform: uppercase;
}}
.kw-tagline {{ color: {BRAND['neon']}; font-weight: 600; }}
.kw-env {{
    background: #050505; border: 1px solid {BRAND['border']};
    padding: 8px 10px; border-radius: 4px; color: {BRAND['neon']};
    font-family: ui-monospace, monospace; font-size: 11px;
}}
h1 {{ color: #FFFFFF; }}
h2, h3 {{ color: {BRAND['neon']}; }}
</style>
""", unsafe_allow_html=True)


# ─────────────────────────────────────────────────────────────────────────────
# Data loaders
# ─────────────────────────────────────────────────────────────────────────────
@st.cache_data
def load_tool_registry() -> list[dict]:
    return json.loads((DATA_DIR / "tool_registry.json").read_text())["tools"]


@st.cache_data
def load_demo_queries() -> list[dict]:
    return json.loads((DATA_DIR / "demo_queries.json").read_text())["queries"]


@st.cache_data
def load_cached_briefs() -> dict:
    p = DATA_DIR / "cached_briefs.json"
    if not p.exists():
        return {}
    return json.loads(p.read_text())


TOOLS = load_tool_registry()
DEMOS = load_demo_queries()
CACHED = load_cached_briefs()


# ─────────────────────────────────────────────────────────────────────────────
# Header
# ─────────────────────────────────────────────────────────────────────────────
header_l, header_r = st.columns([4, 1])
with header_l:
    st.markdown(
        f"# OMNI-AGENT &nbsp;&nbsp;"
        f"<span class='kw-pill'>META-ORCHESTRATOR</span>"
        f"<span class='kw-pill'>{len(TOOLS)} GOVERNED TOOLS</span>"
        f"<span class='kw-pill'>HASH-CHAINED AUDIT</span>",
        unsafe_allow_html=True,
    )
    st.markdown(
        "<span class='kw-tagline'>One ring to rule them all.</span> "
        "&nbsp;Your Marines have 53 different AI tools — "
        "OMNI-AGENT picks the right ones, fires them in order, and writes "
        "you the fused commander's brief. One question in. One brief out.",
        unsafe_allow_html=True,
    )
with header_r:
    st.image(BRAND["logo_url"], width=140)


# ─────────────────────────────────────────────────────────────────────────────
# Sidebar — Tool Shed + env beat
# ─────────────────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("### TOOL SHED")
    st.caption(f"{len(TOOLS)} sibling apps wired as governed tools")
    for t in TOOLS:
        st.markdown(
            f"<div class='kw-tool-card'>"
            f"<div><span class='codename'>{t['codename']}</span> "
            f"&nbsp;<span class='meta'>:{t['port']} &middot; {t['app_dir']}</span></div>"
            f"<div class='meta'>{t['summary']}</div>"
            f"<div class='meta'><b>dataset:</b> {t['dataset'][:60]}</div>"
            f"</div>",
            unsafe_allow_html=True,
        )
    st.markdown("---")
    st.markdown("### KAMIWAZA ENDPOINT")
    base = os.getenv("KAMIWAZA_BASE_URL")
    if base:
        st.markdown(
            f"<div class='kw-env'>KAMIWAZA_BASE_URL={base}</div>",
            unsafe_allow_html=True,
        )
        st.success("On-prem mode: orchestration stays inside the wire.")
    else:
        st.markdown(
            "<div class='kw-env'>KAMIWAZA_BASE_URL=&lt;unset&gt;</div>",
            unsafe_allow_html=True,
        )
        st.caption("Set KAMIWAZA_BASE_URL to swap to on-prem inference.")
    st.markdown(
        f"<div class='kw-env'>provider={PROVIDER} &middot; "
        f"engine=Kamiwaza-deployed</div>",
        unsafe_allow_html=True,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Main area — query, then brief, then trace
# ─────────────────────────────────────────────────────────────────────────────
left, right = st.columns([1.55, 1])

with left:
    st.markdown("### OPERATOR QUERY")
    demo_labels = [f"{d['label']} - {d['narrator']}" for d in DEMOS]
    default_idx = next((i for i, d in enumerate(DEMOS)
                        if d.get("demo_default")), 0)
    sel = st.selectbox(
        "Pick a demo cross-domain query (or type your own below):",
        options=list(range(len(DEMOS))),
        index=default_idx,
        format_func=lambda i: demo_labels[i],
    )
    selected_demo = DEMOS[sel]

    user_msg = st.text_area(
        "Your question",
        value=selected_demo["prompt"],
        height=110,
        label_visibility="collapsed",
    )

    col_a, col_b, col_c = st.columns([1, 1, 1.5])
    with col_a:
        run_cached = st.button("FIRE (cached)", type="primary",
                               use_container_width=True)
    with col_b:
        run_live = st.button("FIRE (live)", use_container_width=True)
    with col_c:
        st.caption(f"Expected tools: {', '.join(selected_demo.get('expected_tools', []))}")

    st.markdown("### FUSED BRIEF")
    brief_slot = st.empty()
    trace_summary = st.empty()

with right:
    st.markdown("### LIVE TOOL-CALL TRACE")
    trace_slot = st.container()
    st.markdown("### HASH-CHAINED AUDIT")
    audit_slot = st.container()


# ─────────────────────────────────────────────────────────────────────────────
# Render helpers
# ─────────────────────────────────────────────────────────────────────────────
def _hero_label(model: str | None) -> str:
    """Map raw model name to a UI-safe label. Never leak 'gpt' to the screen."""
    if not model:
        return "Hero model"
    if "deterministic" in model.lower():
        return "deterministic fallback"
    return "Kamiwaza-deployed model"


def _trace_chip(ev: dict) -> str:
    t = ev["type"]
    if t == "user":
        return (f"<div class='kw-trace user'>operator -&gt; "
                f"{ev['content'][:140]}{'...' if len(ev['content'])>140 else ''}</div>")
    if t == "model_chosen":
        return (f"<div class='kw-trace model'>turn={ev['turn']} -&gt; "
                f"<b>{_hero_label(ev.get('model'))}</b></div>")
    if t == "model_message":
        return (f"<div class='kw-trace model'>AI engine -&gt; "
                f"{ev['content'][:160]}{'...' if len(ev['content'])>160 else ''}</div>")
    if t == "tool_call":
        meta = ev.get("meta", {})
        codename = meta.get("codename", "?")
        port = meta.get("port", "?")
        return (f"<div class='kw-trace tool_call'>tool_call -&gt; "
                f"<b>{ev['name']}</b> "
                f"<span style='color:{BRAND['neon']}'>[{codename}:{port}]</span> "
                f"args={json.dumps(ev['arguments'], default=str)[:140]}</div>")
    if t == "tool_result":
        a = ev.get("audit", {})
        return (f"<div class='kw-trace tool_result'>tool_result &lt;- "
                f"<b>{ev['name']}</b> {ev['ms']}ms "
                f"audit_hash={a.get('hash','?')}</div>")
    if t == "final":
        return (f"<div class='kw-trace final'>final brief synthesized by "
                f"<b>{_hero_label(ev.get('model'))}</b> "
                f"({len(ev['content'])} chars)</div>")
    return f"<div class='kw-trace'>{t}</div>"


def _render_audit():
    rows = audit.tail(8)
    ok, n, msg = audit.verify_chain()
    pill = (f"<span class='kw-pill' style='color:{BRAND['neon']}'>VERIFIED &check; {n}</span>"
            if ok else
            f"<span class='kw-pill' style='color:#FF6B6B'>BROKEN &times; {n}</span>")
    audit_slot.markdown(f"{pill} &nbsp;{msg}", unsafe_allow_html=True)
    if not rows:
        audit_slot.caption("(no records yet)")
        return
    for r in rows[-6:]:
        audit_slot.markdown(
            f"<div class='kw-trace tool_result'>"
            f"{r['ts']} | <b>{r['tool']}</b> "
            f"({r.get('result_codename','?')}:{r.get('result_port','?')}) "
            f"hash={r['hash'][:10]}... prev={r['prev_hash'][:10] if r['prev_hash']!='GENESIS' else 'GENESIS'} "
            f"&middot; {r['latency_ms']}ms"
            f"</div>",
            unsafe_allow_html=True,
        )


def _serve_cached(demo_id: str) -> dict | None:
    return CACHED.get(demo_id)


def _render_cached(payload: dict):
    trace_slot.empty()
    for ev in payload.get("trace", []):
        trace_slot.markdown(_trace_chip(ev), unsafe_allow_html=True)
    brief_slot.markdown(
        f"<div class='kw-brief'>{payload.get('final','(empty)')}</div>",
        unsafe_allow_html=True,
    )
    trace_summary.caption(
        f"Cached run | tools fired: {payload.get('tools_fired_count','?')} | "
        f"engine: {_hero_label(payload.get('model'))} | "
        f"total ms: {payload.get('total_ms','?')}"
    )


def _render_live(user_msg: str):
    trace_slot.empty()
    brief_slot.markdown(
        "<div class='kw-brief'>(agent thinking - watch the trace on the right)</div>",
        unsafe_allow_html=True,
    )
    t0 = time.time()
    tools_fired = 0
    final = ""
    for ev in stream_run(user_msg, hero=True):
        trace_slot.markdown(_trace_chip(ev), unsafe_allow_html=True)
        if ev["type"] == "tool_result":
            tools_fired += 1
        if ev["type"] == "final":
            final = ev["content"]
        # Re-render audit panel as the chain grows
        _render_audit()
    elapsed = int((time.time() - t0) * 1000)
    brief_slot.markdown(
        f"<div class='kw-brief'>{final}</div>",
        unsafe_allow_html=True,
    )
    trace_summary.caption(
        f"Live run | tools fired: {tools_fired} | total ms: {elapsed}"
    )


# ─────────────────────────────────────────────────────────────────────────────
# Dispatch
# ─────────────────────────────────────────────────────────────────────────────
if run_cached:
    payload = _serve_cached(selected_demo["id"])
    if payload is None:
        brief_slot.warning(f"No cached run for '{selected_demo['id']}'. "
                           "Run `python data/generate.py` first or click FIRE (live).")
    else:
        _render_cached(payload)
elif run_live:
    _render_live(user_msg)
else:
    # On first paint: show the default demo's cached brief
    payload = _serve_cached(selected_demo["id"])
    if payload:
        _render_cached(payload)
    else:
        brief_slot.markdown(
            "<div class='kw-brief'>Click FIRE (cached) for the pre-warmed demo, "
            "or FIRE (live) to run the real OpenAI tool-calling loop end-to-end."
            "</div>",
            unsafe_allow_html=True,
        )

_render_audit()


# ─────────────────────────────────────────────────────────────────────────────
# Footer
# ─────────────────────────────────────────────────────────────────────────────
st.markdown(
    f"<div class='kw-footer'>{BRAND['footer']} &middot; "
    f"OMNI-AGENT meta-orchestrator &middot; "
    f"governed access to {len(TOOLS)} sibling apps &middot; "
    f"hash-chained audit for SJA forensics</div>",
    unsafe_allow_html=True,
)
