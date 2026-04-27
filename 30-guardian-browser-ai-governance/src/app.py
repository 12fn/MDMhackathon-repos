"""GUARDIAN — Browser Agent Governance Console (Streamlit, port 3030).

One-screen demo:
  1. Live event-feed (synthetic browser intercepts)
  2. Per-event chat_json policy decisions (color-coded table)
  3. Audit chain panel (SHA-256 hash-chained, forensics-ready)
  4. Sidebar: 8 active policies + cached hero "Posture Brief" picker

Run:
    streamlit run src/app.py --server.port 3030 --server.headless true \\
        --server.runOnSave false --server.fileWatcherType none \\
        --browser.gatherUsageStats false
"""
from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import streamlit as st

# Make `shared` and `src` importable
APP_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = APP_DIR.parents[1]
for p in (str(REPO_ROOT), str(APP_DIR)):
    if p not in sys.path:
        sys.path.insert(0, p)

from shared.kamiwaza_client import BRAND  # noqa: E402
from src import audit, policy  # noqa: E402

DATA_DIR = APP_DIR / "data"
EVENTS_PATH = DATA_DIR / "events.jsonl"
POLICIES_PATH = DATA_DIR / "policies.json"
BRIEFS_PATH = DATA_DIR / "cached_briefs.json"


# ---------- Page config + theme ---------------------------------------------
st.set_page_config(
    page_title="GUARDIAN — Browser Agent Governance",
    page_icon="G",
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
  h1, h2, h3, h4 {{ color: #FFFFFF !important; letter-spacing: 0.4px; }}
  .g-tagline {{
    color: {BRAND['neon']};
    font-family: Helvetica, Arial, sans-serif;
    font-weight: 600;
    letter-spacing: 1.4px;
    text-transform: uppercase;
    font-size: 12px;
  }}
  .g-headline {{
    color: #FFFFFF;
    font-family: Helvetica, Arial, sans-serif;
    font-weight: 700;
    font-size: 28px;
    line-height: 1.18;
    margin-top: 4px;
  }}
  .g-card {{
    background: {BRAND['surface']};
    border: 1px solid {BRAND['border']};
    border-radius: 10px;
    padding: 14px 18px;
    margin-bottom: 10px;
  }}
  .g-policy {{
    background: {BRAND['surface_high']};
    border: 1px solid {BRAND['border']};
    border-left: 3px solid {BRAND['neon']};
    border-radius: 6px;
    padding: 8px 10px;
    margin-bottom: 8px;
  }}
  .g-policy .name {{ color: {BRAND['neon']}; font-weight: 700; letter-spacing: 0.6px; font-size: 12px; }}
  .g-policy .desc {{ color: #B8B8B8; font-size: 11px; margin-top: 2px; }}
  .g-pill {{
    display: inline-block; padding: 2px 9px; border-radius: 999px;
    font-size: 10px; font-weight: 700; letter-spacing: 0.6px; margin-left: 6px;
  }}
  .pill-allow   {{ background:#0E2F22; color:#00FFA7; border:1px solid #00BB7A; }}
  .pill-block   {{ background:#3A0E0E; color:#FF6F66; border:1px solid #D8362F; }}
  .pill-challenge {{ background:#3A2C0E; color:#E0B341; border:1px solid #E0B341; }}
  .pill-redact  {{ background:#0E2A3A; color:#56C6FF; border:1px solid #2C82C9; }}
  .g-stream-row {{
    background: {BRAND['surface_high']};
    border: 1px solid {BRAND['border']};
    border-left: 3px solid {BRAND['primary']};
    border-radius: 6px;
    padding: 8px 12px;
    margin-bottom: 6px;
    font-family: Menlo, monospace;
    font-size: 11px;
    color: #D8D8D8;
  }}
  .g-stream-row .ts {{ color: {BRAND['muted']}; }}
  .g-stream-row .ep {{ color: {BRAND['neon']}; }}
  .g-stream-row .cls {{ color: #E0B341; font-weight: 700; }}
  .g-footer {{
    color: {BRAND['muted']}; text-align: center;
    margin-top: 28px; padding: 14px; border-top: 1px solid {BRAND['border']};
    font-size: 12px; letter-spacing: 1.2px; text-transform: uppercase;
  }}
  .g-footer .kamiwaza {{ color: {BRAND['primary']}; font-weight: 700; }}
  .stButton > button {{
    background: {BRAND['primary']}; color: #0A0A0A; border: 0; font-weight: 700;
    letter-spacing: 0.6px;
  }}
  .stButton > button:hover {{ background: {BRAND['primary_hover']}; color: #000; }}
  div[data-testid="stMetricValue"] {{ color: {BRAND['neon']} !important; }}
  div[data-testid="stMetricLabel"] {{ color: {BRAND['text_dim']} !important; letter-spacing: 0.8px; }}
  pre, code {{ font-family: Menlo, monospace !important; font-size: 11px !important; }}
</style>
"""
st.markdown(CSS, unsafe_allow_html=True)


# ---------- Load synthetic data ---------------------------------------------
@st.cache_data
def load_events() -> list[dict]:
    if not EVENTS_PATH.exists():
        return []
    out: list[dict] = []
    with EVENTS_PATH.open() as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            out.append(json.loads(line))
    return out


@st.cache_data
def load_policies() -> list[dict]:
    if not POLICIES_PATH.exists():
        return []
    return json.loads(POLICIES_PATH.read_text())


@st.cache_data
def load_cached_briefs() -> dict:
    if not BRIEFS_PATH.exists():
        return {}
    return json.loads(BRIEFS_PATH.read_text())


EVENTS = load_events()
POLICIES = load_policies()
BRIEFS = load_cached_briefs()


# ---------- Session state ----------------------------------------------------
if "stream_idx" not in st.session_state:
    # Reset audit log on cold start so the demo is deterministic.
    audit.reset_audit_log()
    st.session_state.stream_idx = 0
    st.session_state.decisions = []  # list of (event, decision, mode)
    st.session_state.use_llm = False
    st.session_state.streaming = False
    st.session_state.brief_id = next(iter(BRIEFS.keys()), None) if BRIEFS else None
    st.session_state.brief_override = None  # filled when "Regenerate live" is hit


# ---------- Sidebar: policies + brief scenario ------------------------------
with st.sidebar:
    st.markdown(
        f"<div class='g-tagline'>AI Inside Your Security Boundary</div>"
        f"<div class='g-headline'>GUARDIAN</div>"
        f"<div style='color:{BRAND['text_dim']};font-size:12px;margin-top:4px;'>"
        f"Browser Agent Governance · LOGCOM"
        f"</div>",
        unsafe_allow_html=True,
    )
    st.markdown("---")
    st.markdown("#### Active policies")
    st.caption(f"{len(POLICIES)} rules loaded · synthetic LOGCOM ruleset")
    for p in POLICIES:
        st.markdown(
            f"<div class='g-policy'>"
            f"<div class='name'>{p['name']}</div>"
            f"<div class='desc'>{p['description']}</div>"
            f"<div style='color:{BRAND['muted']};font-size:10px;margin-top:4px;'>"
            f"default: <b>{p['default_action']}</b> · severity: {p['severity']}"
            f"</div></div>",
            unsafe_allow_html=True,
        )
    st.markdown("---")
    st.markdown("#### Decision engine")
    st.session_state.use_llm = st.toggle(
        "Use Kamiwaza-deployed model (per-event chat_json)",
        value=st.session_state.use_llm,
        help="Off = fast deterministic baseline (no network). On = structured-JSON call to the active model with watchdog fallback.",
    )
    st.markdown("---")
    st.markdown("#### Posture brief scenario")
    if BRIEFS:
        ids = list(BRIEFS.keys())
        labels = [BRIEFS[i]["label"] for i in ids]
        idx = ids.index(st.session_state.brief_id) if st.session_state.brief_id in ids else 0
        chosen_label = st.selectbox("Cached scenario", labels, index=idx, label_visibility="collapsed")
        st.session_state.brief_id = ids[labels.index(chosen_label)]
    else:
        st.warning("Run `python data/generate.py` to populate cached briefs.")


# ---------- Header ----------------------------------------------------------
st.markdown(
    f"<div style='padding:6px 0 4px 0;'>"
    f"<span class='g-tagline'>BROWSER AGENT GOVERNANCE · USMC LOGCOM</span>"
    f"<div class='g-headline'>Stop Comet, manus.im, and rogue browser AI from acting on internal apps.</div>"
    f"<div style='color:{BRAND['text_dim']};font-size:13px;margin-top:6px;'>"
    f"Live middleware screens every browser intercept against {len(POLICIES)} policies, "
    f"emits a strict-JSON decision per event, and writes a SHA-256 hash-chained audit "
    f"entry — all on a Kamiwaza-deployed model behind <code>KAMIWAZA_BASE_URL</code>."
    f"</div></div>",
    unsafe_allow_html=True,
)
st.write("")

# ---------- Top metrics ------------------------------------------------------
def _decision_counts() -> dict:
    counts = {"ALLOW": 0, "BLOCK": 0, "CHALLENGE_HUMAN": 0, "REDACT_PII": 0}
    for _, d, _ in st.session_state.decisions:
        counts[d["policy_action"]] = counts.get(d["policy_action"], 0) + 1
    return counts


m1, m2, m3, m4, m5 = st.columns(5)
counts = _decision_counts()
m1.metric("Events screened", st.session_state.stream_idx)
m2.metric("Allowed", counts["ALLOW"])
m3.metric("Blocked", counts["BLOCK"])
m4.metric("Challenged", counts["CHALLENGE_HUMAN"])
m5.metric("Redacted", counts["REDACT_PII"])

# ---------- Stream controls --------------------------------------------------
ctl1, ctl2, ctl3, ctl4 = st.columns([1, 1, 1, 2])
if ctl1.button("STREAM 1 EVENT", key="step1"):
    st.session_state.streaming = False
    st.session_state.stream_idx = min(st.session_state.stream_idx + 1, len(EVENTS))
if ctl2.button("STREAM 10", key="step10"):
    st.session_state.streaming = False
    st.session_state.stream_idx = min(st.session_state.stream_idx + 10, len(EVENTS))
if ctl3.button("STREAM ALL", key="streamall"):
    st.session_state.streaming = True
    st.session_state.stream_idx = len(EVENTS)
if ctl4.button("RESET DEMO", key="reset"):
    st.session_state.stream_idx = 0
    st.session_state.decisions = []
    st.session_state.brief_override = None
    audit.reset_audit_log()
    load_events.clear()
    st.rerun()


# ---------- Process newly-streamed events -----------------------------------
def process_pending():
    """Consume any events the user just streamed in. Decision per event,
    audit-append per event."""
    already = len(st.session_state.decisions)
    target = st.session_state.stream_idx
    if target <= already:
        return
    use_llm = st.session_state.use_llm
    for i in range(already, target):
        ev = EVENTS[i]
        if use_llm:
            d = policy.decide_with_llm(ev, POLICIES)
            mode = "llm"
        else:
            d = policy.decide_baseline(ev, POLICIES)
            mode = "baseline"
        # Audit append — the hash chain binds (event, decision, mode)
        audit.append_audit({
            "event": "POLICY_DECISION",
            "engine_mode": mode,
            "event_summary": {
                "event_id": ev["event_id"],
                "internal_app": ev["internal_app"],
                "endpoint": ev["endpoint"],
                "data_class": ev["data_class"],
                "client_ip": ev["client_ip"],
            },
            "decision": d,
        })
        st.session_state.decisions.append((ev, d, mode))


process_pending()

# ---------- Layout: live feed (left) + decisions (right) --------------------
left, right = st.columns([5, 7])

with left:
    st.markdown("### Live event feed")
    st.caption("Synthetic browser intercepts streaming through the GUARDIAN middleware.")
    feed_box = st.container()
    # Auto-scrolling: render newest 14 first
    recent = list(reversed(st.session_state.decisions[-14:]))
    if not recent:
        feed_box.info("Click STREAM to start the live event feed.")
    for ev, d, mode in recent:
        ts = ev["timestamp_utc"].split("T")[1][:8]
        feed_box.markdown(
            f"<div class='g-stream-row'>"
            f"<span class='ts'>{ts}Z</span> · "
            f"<span class='ep'>{ev['internal_app']}</span> "
            f"<span style='color:#888'>{ev['method']}</span> "
            f"<code>{ev['endpoint']}</code> · "
            f"<span class='cls'>{ev['data_class']}</span> · "
            f"<span style='color:#888'>{ev['client_ip']}</span>"
            f"</div>",
            unsafe_allow_html=True,
        )

with right:
    st.markdown("### Per-event policy decisions")
    st.caption("Strict-JSON decisions from the engine. Color-coded by action.")
    if not st.session_state.decisions:
        st.info("No decisions yet — stream events to populate.")
    else:
        rows = []
        for ev, d, mode in reversed(st.session_state.decisions[-14:]):
            rows.append({
                "event_id": d["event_id"],
                "agent_detected": d["agent_detected"],
                "confidence": d["confidence"],
                "policy_action": d["policy_action"],
                "rationale": d["rationale"][:80] + ("..." if len(d["rationale"]) > 80 else ""),
                "engine": mode,
            })
        df = pd.DataFrame(rows)

        def _color_action(val: str) -> str:
            if val == "ALLOW":   return "background-color:#0E2F22; color:#00FFA7;"
            if val == "BLOCK":   return "background-color:#3A0E0E; color:#FF6F66;"
            if val == "CHALLENGE_HUMAN": return "background-color:#3A2C0E; color:#E0B341;"
            if val == "REDACT_PII": return "background-color:#0E2A3A; color:#56C6FF;"
            return ""

        styled = df.style.applymap(_color_action, subset=["policy_action"])
        st.dataframe(styled, use_container_width=True, hide_index=True, height=440)

        # Show the most recent JSON in detail
        last_ev, last_d, last_mode = st.session_state.decisions[-1]
        with st.expander(f"Most recent decision JSON — {last_d['event_id']} (engine: {last_mode})", expanded=False):
            st.code(json.dumps(last_d, indent=2), language="json")


# ---------- Audit chain ------------------------------------------------------
st.markdown("---")
st.markdown("### Hash-chained audit log")
st.caption("Append-only, SHA-256 prev_hash chain. Forensics-ready. Tamper on any "
           "row breaks the chain at verify time.")

chain = audit.read_audit_chain(limit=10)
if not chain:
    st.info("Audit chain empty. Stream events to seed the genesis entry.")
else:
    arows = []
    for c in chain:
        d = c.get("decision") or {}
        es = c.get("event_summary") or {}
        arows.append({
            "ts": c.get("timestamp_utc", "")[:19].replace("T", " "),
            "event": c.get("event"),
            "event_id": es.get("event_id", "—"),
            "endpoint": es.get("endpoint", "—"),
            "data_class": es.get("data_class", "—"),
            "agent": d.get("agent_detected", "—"),
            "action": d.get("policy_action", "—"),
            "engine": c.get("engine_mode", "—"),
            "prev_hash": (c.get("prev_hash") or "")[:14] + "...",
            "entry_hash": (c.get("entry_hash") or "")[:14] + "...",
        })
    st.dataframe(pd.DataFrame(arows), use_container_width=True, hide_index=True, height=300)

    vc1, vc2 = st.columns([1, 4])
    if vc1.button("VERIFY CHAIN", key="verify"):
        ok, n, msg = audit.verify_chain()
        (vc2.success if ok else vc2.error)(f"{msg}")


# ---------- Hero brief (cache-first) ----------------------------------------
st.markdown("---")
st.markdown("### Browser Agent Governance Posture Brief")
st.caption("Hero call: long-form posture brief drafted by the Kamiwaza-deployed "
           "hero model. Cache-first per AGENT_BRIEF_V2 — pre-computed at synth time, "
           "regeneratable on demand.")

if BRIEFS and st.session_state.brief_id:
    chosen = BRIEFS[st.session_state.brief_id]
    body = st.session_state.brief_override or chosen["brief_markdown"]
    sc1, sc2, sc3, sc4, sc5 = st.columns(5)
    s = chosen["summary_stats"]
    sc1.metric("Events", s["total_events"])
    sc2.metric("Blocked", s["blocked"])
    sc3.metric("Challenged", s["challenged"])
    sc4.metric("Redacted", s["redacted"])
    sc5.metric("Allowed", s["allowed"])

    with st.container():
        st.markdown(f"<div class='g-card'>{body}</div>", unsafe_allow_html=True)

    rb1, rb2 = st.columns([1, 4])
    if rb1.button("REGENERATE LIVE", key="regen"):
        with st.spinner("Drafting brief on the Kamiwaza-deployed hero model (≤35s)..."):
            try:
                from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutTimeout
                from shared.kamiwaza_client import chat
                prompt = (
                    "You are a USMC LOGCOM cyber-governance analyst. Draft a "
                    "Browser Agent Governance Posture Brief for the scenario below. "
                    "Sections: BLUF, Top exfil vectors (numbered), Recommended policy "
                    "tightening (bulleted), False-positive risk. ~250 words.\n\n"
                    f"Scenario: {chosen['label']}\n"
                    f"Stats: {json.dumps(s)}\n"
                    f"Active policies: {[p['name'] for p in POLICIES]}\n"
                )

                def _run() -> str:
                    return chat(
                        [
                            {"role": "system", "content": "You are precise, defense-grade, no fluff."},
                            {"role": "user", "content": prompt},
                        ],
                        model=os.getenv("LLM_PRIMARY_MODEL", "gpt-5.4"),
                        temperature=0.4,
                    )

                with ThreadPoolExecutor(max_workers=1) as ex:
                    new_body = ex.submit(_run).result(timeout=35)
                st.session_state.brief_override = new_body
                st.rerun()
            except Exception as e:  # noqa: BLE001
                rb2.warning(f"Live call timed out / failed; cached brief retained. ({e})")


# ---------- Footer ----------------------------------------------------------
st.markdown(
    f"<div class='g-footer'>"
    f"<span style='color:{BRAND['neon']}'>100% Data Containment.</span> "
    f"Set <code>KAMIWAZA_BASE_URL</code> and the same code routes through a "
    f"vLLM-served model inside your accredited boundary. "
    f"IL5/IL6 ready · NIPR/SIPR/JWICS deployable · DDIL-tolerant.<br/>"
    f"<span class='kamiwaza'>Powered by Kamiwaza</span>"
    f"</div>",
    unsafe_allow_html=True,
)
