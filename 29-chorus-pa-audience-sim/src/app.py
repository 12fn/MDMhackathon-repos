"""CHORUS — Streamlit app (port 3029).

AI-Enabled Public Affairs Training & Audience Simulation. Trainees pick a
scenario, draft a 200-500 word public statement, and CHORUS simulates how a
balanced 5-persona audience panel will react. The hero call writes a Message
Effectiveness Brief.

Run with:
    cd apps/29-chorus
    streamlit run src/app.py --server.port 3029 --server.headless true
"""
from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

import streamlit as st

# Make `shared` and `src` importable.
APP_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = APP_ROOT.parents[1]
for p in (str(REPO_ROOT), str(APP_ROOT)):
    if p not in sys.path:
        sys.path.insert(0, p)

from shared.kamiwaza_client import BRAND  # noqa: E402
from src import agent  # noqa: E402


# ---------- Page config + theme ---------------------------------------------

st.set_page_config(
    page_title="CHORUS — PA / IO Audience Simulation",
    page_icon="◆",
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
  h1, h2, h3, h4 {{
    color: #FFFFFF !important;
    letter-spacing: 0.4px;
  }}
  .chorus-tagline {{
    color: {BRAND['neon']};
    font-family: Helvetica, Arial, sans-serif;
    font-weight: 600;
    letter-spacing: 1.2px;
    text-transform: uppercase;
    font-size: 12px;
  }}
  .chorus-headline {{
    color: #FFFFFF;
    font-family: Helvetica, Arial, sans-serif;
    font-weight: 700;
    font-size: 28px;
    line-height: 1.2;
    margin-top: 4px;
  }}
  .chorus-card {{
    background: {BRAND['surface']};
    border: 1px solid {BRAND['border']};
    border-radius: 10px;
    padding: 14px 16px;
    margin-bottom: 10px;
  }}
  .chorus-persona-card {{
    background: {BRAND['surface']};
    border-radius: 10px;
    padding: 12px 14px;
    margin-bottom: 8px;
    height: 100%;
    min-height: 320px;
    display: flex;
    flex-direction: column;
  }}
  .chorus-pid {{
    color: {BRAND['muted']};
    font-size: 10px;
    letter-spacing: 1px;
    text-transform: uppercase;
  }}
  .chorus-plabel {{
    color: #FFFFFF;
    font-weight: 700;
    font-size: 13px;
    margin-top: 2px;
    line-height: 1.3;
  }}
  .chorus-tier {{
    color: {BRAND['text_dim']};
    font-size: 11px;
    margin-top: 2px;
  }}
  .chorus-delta {{
    font-size: 30px;
    font-weight: 800;
    letter-spacing: -1px;
    margin: 6px 0 0 0;
  }}
  .chorus-row {{
    display: flex;
    justify-content: space-between;
    font-size: 11px;
    color: #C8C8C8;
    margin-top: 4px;
  }}
  .chorus-perceived {{
    color: #DADADA;
    font-size: 12px;
    margin-top: 8px;
    line-height: 1.4;
  }}
  .chorus-concerns {{
    color: #B0B0B0;
    font-size: 11px;
    margin-top: 8px;
    line-height: 1.35;
  }}
  .chorus-pill {{
    display: inline-block;
    padding: 2px 8px;
    border-radius: 999px;
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 0.6px;
  }}
  .pill-low    {{ background:#0E2F22; color:#00FFA7; border:1px solid #00BB7A; }}
  .pill-med    {{ background:#3A2C0E; color:#E0B341; border:1px solid #E0B341; }}
  .pill-high   {{ background:#3A0E0E; color:#FF6F66; border:1px solid #D8362F; }}
  .chorus-footer {{
    color:{BRAND['muted']};
    text-align:center;
    margin-top:30px;
    padding:14px;
    border-top:1px solid {BRAND['border']};
    font-size:12px;
    letter-spacing: 1.2px;
    text-transform: uppercase;
  }}
  .stButton > button {{
    background: {BRAND['primary']};
    color: #0A0A0A;
    border: 0;
    font-weight: 700;
    letter-spacing: 0.6px;
  }}
  .stButton > button:hover {{
    background: {BRAND['primary_hover']};
    color: #0A0A0A;
  }}
  div[data-testid="stMetricValue"] {{
    color: {BRAND['neon']} !important;
  }}
  textarea {{
    background: {BRAND['surface_high']} !important;
    color: #E8E8E8 !important;
    border: 1px solid {BRAND['border']} !important;
  }}
</style>
"""
st.markdown(CSS, unsafe_allow_html=True)


# ---------- Helpers ---------------------------------------------------------

def trust_color(delta: int) -> str:
    if delta >= 4:
        return "#00FFA7"
    if delta >= 0:
        return "#7FE3B8"
    if delta >= -4:
        return "#E0B341"
    if delta >= -7:
        return "#E36F2C"
    return "#FF6F66"


def risk_pill(risk: str) -> str:
    cls = {"LOW": "pill-low", "MEDIUM": "pill-med", "HIGH": "pill-high"}.get(risk, "pill-med")
    return f'<span class="chorus-pill {cls}">{risk}</span>'


def render_persona_card(reaction: dict, persona: dict) -> str:
    delta = reaction["trust_delta"]
    color = trust_color(delta)
    border_color = color if abs(delta) >= 4 else BRAND["border"]
    sign = "+" if delta > 0 else ""
    concerns_html = "".join(
        f"<div>• {c}</div>" for c in reaction.get("key_concerns_raised", [])[:2]
    )
    return (
        f"<div class='chorus-persona-card' style='border:1px solid {border_color};'>"
        f"<div class='chorus-pid'>{reaction['persona_id']}</div>"
        f"<div class='chorus-plabel'>{persona.get('label','')}</div>"
        f"<div class='chorus-tier'>{persona.get('tier','')}</div>"
        f"<div class='chorus-delta' style='color:{color};'>{sign}{delta}</div>"
        f"<div class='chorus-row'>"
        f"<span>Trust delta</span>"
        f"<span>{risk_pill(reaction['narrative_risk'])}</span>"
        f"</div>"
        f"<div class='chorus-row'>"
        f"<span style='color:{BRAND['muted']};'>Predicted action</span>"
        f"<span style='color:#FFFFFF;font-weight:700;'>{reaction['predicted_action'].upper()}</span>"
        f"</div>"
        f"<div class='chorus-perceived'><b>Perceived:</b> {reaction['perceived_message']}</div>"
        f"<div class='chorus-concerns'><b>Key concerns:</b><br/>{concerns_html}</div>"
        f"</div>"
    )


# ---------- Session state ---------------------------------------------------

if "result" not in st.session_state:
    st.session_state.result = None
if "scenario_id" not in st.session_state:
    st.session_state.scenario_id = None
if "draft_message" not in st.session_state:
    st.session_state.draft_message = ""


# ---------- Load static data once ------------------------------------------

PERSONAS = agent.load_personas()
SCENARIOS = agent.load_scenarios()
CACHED = agent.load_cached_briefs()
PANEL = agent.pick_personas(PERSONAS, n=5)


# ---------- Sidebar ---------------------------------------------------------

with st.sidebar:
    st.markdown(
        f"<div class='chorus-tagline'>{BRAND['footer']}</div>"
        f"<div class='chorus-headline'>CHORUS</div>"
        f"<div style='color:{BRAND['text_dim']};font-size:12px;margin-top:6px;'>"
        "PA / IO Training &amp; Audience Simulation<br/>for USMC Public Affairs"
        "</div>",
        unsafe_allow_html=True,
    )
    st.markdown("---")
    st.markdown("**MISSION FRAME**")
    st.markdown(
        "<span style='color:#9A9A9A;font-size:12px;'>"
        "AI-Enabled Public Affairs Training &amp; Audience Simulation. "
        "Trainees draft a public statement; CHORUS simulates how 5 audience "
        "personas across 3 information environments will react — and explains why."
        "</span>",
        unsafe_allow_html=True,
    )
    st.markdown("---")
    st.markdown("**PERSONA LIBRARY**")
    st.markdown(
        f"<span style='color:#9A9A9A;font-size:12px;'>"
        f"<b>15</b> reusable synthetic personas across <b>3</b> tiers: "
        "Domestic media &amp; oversight · Host-nation &amp; coalition · Adversary / contested IE. "
        "Methodology after Park et al. 2024 "
        "(<a href='https://arxiv.org/abs/2403.20252' style='color:#00FFA7;'>arXiv:2403.20252</a>)."
        "</span>",
        unsafe_allow_html=True,
    )
    st.markdown("---")
    st.markdown("**ACTIVE PANEL** (5 of 15)")
    for p in PANEL:
        st.markdown(
            f"<div style='font-size:11px;line-height:1.4;margin-bottom:4px;'>"
            f"<span style='color:{BRAND['neon']};font-weight:700;'>{p['persona_id']}</span> "
            f"<span style='color:#C8C8C8;'>· {p['label']}</span>"
            f"</div>",
            unsafe_allow_html=True,
        )
    st.markdown("---")
    hero = st.toggle(
        "Hero brief (Kamiwaza-deployed hero model)",
        value=True,
        help="When ON, the Message Effectiveness Brief is drafted by the Kamiwaza-deployed hero model with a 35s timeout. When OFF, uses the mini chain.",
    )


# ---------- Header ----------------------------------------------------------

col_a, col_b = st.columns([0.65, 0.35])
with col_a:
    st.markdown(
        "<div class='chorus-tagline'>PA/IO trainee feedback · audience simulation</div>"
        "<div class='chorus-headline'>Every public statement meets five audiences. CHORUS rehearses all five before you press send.</div>",
        unsafe_allow_html=True,
    )
with col_b:
    st.markdown(
        f"<div class='chorus-card' style='text-align:right;'>"
        f"<div style='color:{BRAND['muted']};font-size:11px;letter-spacing:1px;'>CLASSIFICATION</div>"
        f"<div style='color:{BRAND['neon']};font-weight:700;letter-spacing:1.2px;'>UNCLASSIFIED // FOR TRAINING USE</div>"
        f"<div style='color:{BRAND['muted']};font-size:11px;letter-spacing:1px;margin-top:8px;'>POSTURE</div>"
        f"<div style='color:#FFFFFF;font-weight:700;'>On-prem · Kamiwaza Stack</div>"
        f"</div>",
        unsafe_allow_html=True,
    )

st.markdown("---")


# ---------- Scenario picker + message composer -----------------------------

st.markdown("### 1. Pick a training scenario")
scenario_options = {s["scenario_id"]: s["title"] for s in SCENARIOS}
scenario_id = st.radio(
    "Scenario",
    options=list(scenario_options.keys()),
    format_func=lambda k: scenario_options[k],
    horizontal=True,
    label_visibility="collapsed",
    key="scenario_radio",
)
scenario = next(s for s in SCENARIOS if s["scenario_id"] == scenario_id)

st.markdown(
    f"<div class='chorus-card'>"
    f"<div class='chorus-pid'>Theater · {scenario['theater']}</div>"
    f"<div style='color:#E8E8E8;font-size:13px;margin-top:6px;line-height:1.45;'>{scenario['mission_context']}</div>"
    f"<div style='color:{BRAND['neon']};font-size:12px;margin-top:8px;letter-spacing:0.5px;'>"
    f"OBJECTIVE: <span style='color:#FFFFFF;'>{scenario['trainee_objective']}</span></div>"
    f"</div>",
    unsafe_allow_html=True,
)

# Default the textarea to the cached sample message for this scenario, so
# the demo opens with realistic content and the cache hits on first SIMULATE.
default_message = ""
if scenario_id in CACHED:
    default_message = CACHED[scenario_id].get("trainee_message", "")

# Reset draft when scenario changes
if st.session_state.scenario_id != scenario_id:
    st.session_state.scenario_id = scenario_id
    st.session_state.draft_message = default_message
    st.session_state.result = None

st.markdown("### 2. Draft your public statement (200 - 500 words)")
draft = st.text_area(
    "Draft message",
    value=st.session_state.draft_message or default_message,
    height=240,
    key="draft_text",
    label_visibility="collapsed",
    placeholder="Compose the statement you would release. CHORUS will run it past 5 audience personas.",
)
st.session_state.draft_message = draft

word_count = len(draft.split()) if draft else 0
wc_color = (
    BRAND["neon"] if 200 <= word_count <= 500
    else (BRAND["text_dim"] if word_count else "#FF6F66")
)
st.markdown(
    f"<div style='display:flex;justify-content:space-between;font-size:12px;color:{BRAND['muted']};'>"
    f"<span>Target: 200–500 words</span>"
    f"<span style='color:{wc_color};font-weight:700;'>{word_count} words</span>"
    f"</div>",
    unsafe_allow_html=True,
)

st.markdown("")
c1, c2, c3 = st.columns([0.34, 0.33, 0.33])
with c1:
    run = st.button(
        "▶ SIMULATE 5 AUDIENCES",
        use_container_width=True,
        type="primary",
        key="btn_simulate",
    )
with c2:
    st.metric("Personas in panel", "5", help="Balanced across all 3 audience tiers.")
with c3:
    st.metric("Library size", f"{len(PERSONAS)} personas", help="15 reusable persona cards across 3 tiers.")


# ---------- Pipeline trigger -----------------------------------------------

if run:
    with st.spinner("Step 1/2 — simulating 5 personas in parallel (chat_json)…"):
        result = agent.run_pipeline(
            scenario_id=scenario_id,
            message=draft,
            personas_n=5,
            hero=hero,
            use_cache=True,
        )
    # If we hit cache, the brief is already there; the spinner above is enough.
    if result.get("source") == "live":
        with st.spinner("Step 2/2 — drafting Message Effectiveness Brief (Kamiwaza-deployed)…"):
            # write_brief was already called inside run_pipeline; this spinner
            # just gives the demo recording a beat to read the step label.
            pass
    st.session_state.result = result


# ---------- Default render (no run yet) ------------------------------------

if not st.session_state.result:
    st.markdown("---")
    st.markdown("### 3. Audience reactions will appear here")
    st.info(
        "Click **▶ SIMULATE 5 AUDIENCES** to score the draft against the panel. "
        "The default text is a realistic baseline draft — the cache lights up "
        "instantly so you can see the full output. Edit the message and re-run "
        "to see the panel re-rank in seconds."
    )
    # Show empty persona scaffolding so the page is never blank.
    st.markdown("#### Active panel preview")
    cols = st.columns(5)
    by_id = {p["persona_id"]: p for p in PERSONAS}
    for i, p in enumerate(PANEL):
        placeholder = {
            "persona_id": p["persona_id"],
            "perceived_message": "(awaiting trainee message)",
            "trust_delta": 0,
            "narrative_risk": "MEDIUM",
            "predicted_action": "ignore",
            "key_concerns_raised": [
                f"Values: {', '.join(p['values'][:2])}",
                f"Lens: {p['lens'][:90]}",
            ],
        }
        with cols[i]:
            st.markdown(render_persona_card(placeholder, p), unsafe_allow_html=True)

else:
    r = st.session_state.result
    by_id = {p["persona_id"]: p for p in PERSONAS}
    st.markdown("---")
    st.markdown("### 3. Audience reactions — 5-persona panel")
    st.caption(
        f"Generated {r['generated_at']} · source: {r['source']} · "
        f"scenario: {r['scenario']['title']}"
    )
    cols = st.columns(5)
    # Sort the cards left-to-right worst-to-best so the eye lands on the riskiest first.
    ordered = sorted(r["reactions"], key=lambda x: x["trust_delta"])
    for i, reaction in enumerate(ordered):
        persona = by_id.get(reaction["persona_id"], {"label": reaction["persona_id"], "tier": ""})
        with cols[i]:
            st.markdown(render_persona_card(reaction, persona), unsafe_allow_html=True)

    # Aggregate metrics row
    m1, m2, m3, m4 = st.columns(4)
    avg_delta = sum(x["trust_delta"] for x in r["reactions"]) / max(1, len(r["reactions"]))
    high_n = sum(1 for x in r["reactions"] if x["narrative_risk"] == "HIGH")
    counter_n = sum(1 for x in r["reactions"] if x["predicted_action"] == "counter-message")
    share_n = sum(1 for x in r["reactions"] if x["predicted_action"] == "share")
    with m1:
        st.metric("Avg trust delta", f"{avg_delta:+.1f}")
    with m2:
        st.metric("High narrative risk", f"{high_n} / 5")
    with m3:
        st.metric("Likely to counter-message", str(counter_n))
    with m4:
        st.metric("Likely to share", str(share_n))

    st.markdown("---")
    st.markdown("### 4. Message Effectiveness Brief")
    st.caption("Drafted by the Kamiwaza-deployed hero model. Cache-first so the demo is instant; live regen on every new draft.")
    st.markdown(
        "<div class='chorus-card' style='padding:22px 28px;'>",
        unsafe_allow_html=True,
    )
    st.markdown(r["brief"])
    st.markdown("</div>", unsafe_allow_html=True)

    with st.expander("Suggested message revisions (paste-ready)"):
        # Pull the revisions section from the brief if present; else show a hint.
        body = r["brief"]
        if "## Suggested Revisions" in body:
            rev = body.split("## Suggested Revisions", 1)[1]
            # stop at next h2 if any (no other h2 expected after Revisions)
            if "\n## " in rev:
                rev = rev.split("\n## ", 1)[0]
            st.markdown(rev.strip())
        else:
            st.write("Open the brief above for suggested revisions.")

    with st.expander("Show raw persona reactions (JSON)"):
        st.json({reaction["persona_id"]: {k: v for k, v in reaction.items() if k != "persona_id"}
                 for reaction in r["reactions"]})


# ---------- Footer ---------------------------------------------------------

st.markdown(
    f"<div class='chorus-footer'>"
    f"Powered by Kamiwaza · 100% Data Containment — Nothing ever leaves your accredited environment."
    f"</div>",
    unsafe_allow_html=True,
)
