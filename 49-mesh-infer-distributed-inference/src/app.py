"""MESH-INFER — Distributed Inference Mesh visualizer.

Run:
    streamlit run src/app.py --server.port 3049 --server.headless true \
      --server.runOnSave false --server.fileWatcherType none \
      --browser.gatherUsageStats false
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(ROOT))
APP = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(APP))

from shared.kamiwaza_client import BRAND  # noqa: E402

from src import audit, mesh, router  # noqa: E402
from src.graph import render_plot  # noqa: E402

st.set_page_config(
    page_title="MESH-INFER — Distributed Inference Mesh",
    page_icon=":satellite:",
    layout="wide",
    initial_sidebar_state="collapsed",
)

CSS = f"""
<style>
  .stApp {{ background: {BRAND['bg']}; color: #E8E8E8; }}
  [data-testid="stHeader"] {{ background: transparent; }}
  [data-testid="stToolbar"] {{ display: none; }}
  section[data-testid="stSidebar"] {{ background: {BRAND['surface']}; border-right: 1px solid {BRAND['border']}; }}

  .mi-hero {{
    background: linear-gradient(135deg, {BRAND['surface']} 0%, {BRAND['bg']} 100%);
    border: 1px solid {BRAND['border']};
    border-left: 4px solid {BRAND['primary']};
    border-radius: 8px;
    padding: 14px 22px;
    margin-bottom: 12px;
  }}
  .mi-hero h1 {{
    color: {BRAND['neon']}; font-size: 24px; margin: 0; letter-spacing:-0.5px;
    font-family: 'Helvetica Neue', sans-serif;
  }}
  .mi-hero p {{ color: {BRAND['text_dim']}; margin: 4px 0 0 0; font-size: 13px; }}

  .mi-pill {{
    display:inline-block; background:{BRAND['surface_high']};
    color:{BRAND['primary']}; border:1px solid {BRAND['primary']};
    border-radius:999px; padding:2px 10px; font-size:11px;
    margin-right:6px; letter-spacing:0.4px;
  }}
  .mi-card {{
    background:{BRAND['surface']}; border:1px solid {BRAND['border']};
    border-radius:6px; padding:12px 16px; margin-bottom:8px;
  }}
  .mi-step {{
    background:{BRAND['surface_high']}; border:1px solid {BRAND['border']};
    border-left:4px solid {BRAND['primary']};
    border-radius:6px; padding:10px 14px; margin-bottom:8px;
  }}
  .mi-step.scif {{ border-left-color:#FF6B6B; }}
  .mi-step.rear {{ border-left-color:{BRAND['primary']}; }}
  .mi-step.edge {{ border-left-color:{BRAND['neon']}; }}
  .mi-step .h {{ color:{BRAND['neon']}; font-weight:700; font-size:14px; }}
  .mi-step .meta {{ color:{BRAND['text_dim']}; font-size:11px; margin-top:2px; }}
  .mi-step .out {{ color:#DDD; font-size:12px; margin-top:6px;
                   background:#000; border:1px solid {BRAND['border']};
                   padding:6px 8px; border-radius:4px; white-space:pre-wrap; }}
  .mi-step .why {{ color:#9FD6BB; font-size:11px; margin-top:4px; font-style: italic; }}

  .mi-cloudpanel {{
    background:#1A0A0A; border:1px solid #441818;
    border-left:4px solid #FF6B6B; border-radius:6px;
    padding:12px 16px; margin-bottom:8px;
  }}
  .mi-cloudpanel h4 {{ color:#FF8585; margin:0 0 6px 0; font-size:14px; }}
  .mi-cloudpanel .leak {{ color:#FFB454; font-size:12px; margin-top:4px; }}

  .mi-counter {{
    background:{BRAND['surface_high']}; border:1px solid {BRAND['border']};
    border-radius:6px; padding:8px 12px; text-align:center;
  }}
  .mi-counter .v {{ color:{BRAND['neon']}; font-size:22px; font-weight:700; }}
  .mi-counter .l {{ color:{BRAND['text_dim']}; font-size:10px; letter-spacing:1.2px; text-transform:uppercase; }}

  .mi-audit {{
    background:#000; border:1px solid {BRAND['border']}; border-radius:4px;
    padding:8px 10px; font-family:'SFMono-Regular',Menlo,monospace;
    font-size:10px; color:#9FD6BB; max-height:200px; overflow:auto;
  }}
  .mi-audit .hash {{ color:{BRAND['muted']}; }}
  .mi-audit .ok   {{ color:{BRAND['primary']}; font-weight:600; }}
  .mi-audit .deny {{ color:#FF6B6B; font-weight:600; }}

  .mi-footer {{
    color:{BRAND['text_dim']}; font-size:12px; text-align:center;
    padding:14px 0 4px 0; border-top:1px solid {BRAND['border']}; margin-top:24px;
  }}
  .mi-footer span {{ color:{BRAND['primary']}; font-weight:600; }}

  div.stButton > button:first-child {{
    background:{BRAND['primary']}; color:#000; border:0;
    font-weight:600; border-radius:4px; padding:6px 18px;
  }}
  div.stButton > button:hover {{ background:{BRAND['primary_hover']}; color:#000; }}

  .mi-kbd {{
    font-family:'SFMono-Regular',Menlo,monospace; background:#000;
    border:1px solid {BRAND['border']}; border-radius:3px; padding:1px 6px;
    color:{BRAND['neon']}; font-size:11px;
  }}
</style>
"""
st.markdown(CSS, unsafe_allow_html=True)

# ── Hero ─────────────────────────────────────────────────────────────────
st.markdown(
    f"""
    <div class="mi-hero">
      <h1>MESH-INFER — Kamiwaza Distributed Inference Mesh</h1>
      <p><strong>One query · Four sensitivities · Four right answers.</strong>
         Per-step routing across edge / rear depot / SCIF — visualized live.</p>
      <p style="margin-top:6px;">
        <span class="mi-pill">Inference Mesh</span>
        <span class="mi-pill">Per-step routing</span>
        <span class="mi-pill">Hash-chained audit</span>
        <span class="mi-pill">Cache-first</span>
        <span class="mi-pill">USMC LOGCOM 2026</span>
      </p>
    </div>
    """,
    unsafe_allow_html=True,
)

# ── Load data ────────────────────────────────────────────────────────────
NODES = router.nodes()
PROFILES = router.profiles()
SENS = router.sensitivities()
SCENARIOS = mesh.load_scenarios()
CACHED = mesh.load_cached_briefs()

if "scenario_id" not in st.session_state:
    st.session_state.scenario_id = SCENARIOS[0]["id"]
if "result" not in st.session_state:
    st.session_state.result = mesh.run_cached(st.session_state.scenario_id)

# ── Scenario picker + run controls ───────────────────────────────────────
left, right = st.columns([3, 2])
with left:
    sc_options = {sc["id"]: sc["title"] for sc in SCENARIOS}
    sid = st.selectbox(
        "Mission scenario",
        options=list(sc_options.keys()),
        format_func=lambda k: sc_options[k],
        index=list(sc_options.keys()).index(st.session_state.scenario_id),
        key="scenario_select",
    )
    if sid != st.session_state.scenario_id:
        st.session_state.scenario_id = sid
        st.session_state.result = mesh.run_cached(sid)
        st.rerun()

with right:
    st.markdown("<div style='height:18px'></div>", unsafe_allow_html=True)
    c1, c2 = st.columns(2)
    run_live = c1.button("Route through the Mesh", use_container_width=True, type="primary")
    hero_toggle = c2.toggle("Hero model", value=False, help="Live re-run via Kamiwaza-deployed hero model")

scenario = mesh.get_scenario(st.session_state.scenario_id)
st.caption(f"Operator prompt: *{scenario['operator_prompt']}*")
st.caption(f"Context: {scenario['context_blurb']}")

if run_live:
    with st.status("Routing through the Inference Mesh...", expanded=True) as s:
        s.write("- Decomposing into typed steps (vision / classify / draft / recommend)")
        s.write("- Scoring each candidate node against task profile + sensitivity")
        s.write("- Dispatching each step → matched node")
        s.write("- Writing chained audit log entries")
        st.session_state.result = mesh.run_live(st.session_state.scenario_id, hero=hero_toggle)
        s.update(label=f"Mesh run complete — {st.session_state.scenario_id}.", state="complete", expanded=False)

result = st.session_state.result or mesh.run_cached(st.session_state.scenario_id)

# ── Mesh graph + counters ────────────────────────────────────────────────
st.markdown("### Inference mesh — live routing")

trace = result.get("trace", [])
used_node_ids = [step["route"]["node_id"] for step in trace]
step_meta = {}
for i, step in enumerate(trace):
    step_meta.setdefault(step["route"]["node_id"], {
        "step_idx": i,
        "sensitivity": step["sensitivity"],
        "task_label": step["task_label"],
    })

g_col, m_col = st.columns([1.6, 1.0])
with g_col:
    fig = render_plot(NODES, used_node_ids, step_meta=step_meta)
    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})

with m_col:
    totals = result.get("totals", {})
    cb = result.get("cloud_baseline", {})

    cc1, cc2 = st.columns(2)
    cc1.markdown(
        f'<div class="mi-counter"><div class="v">{totals.get("mesh_latency_s", 0)}s</div>'
        f'<div class="l">Mesh total latency</div></div>',
        unsafe_allow_html=True,
    )
    cc2.markdown(
        f'<div class="mi-counter"><div class="v">{totals.get("mesh_egress_kb", 0)} kB</div>'
        f'<div class="l">Egress (out of perimeter)</div></div>',
        unsafe_allow_html=True,
    )
    cc3, cc4 = st.columns(2)
    cc3.markdown(
        f'<div class="mi-counter"><div class="v">{totals.get("sensitivity_max", "—")}</div>'
        f'<div class="l">Highest sensitivity</div></div>',
        unsafe_allow_html=True,
    )
    cc4.markdown(
        f'<div class="mi-counter"><div class="v">{totals.get("node_count_used", 0)}/4</div>'
        f'<div class="l">Mesh nodes engaged</div></div>',
        unsafe_allow_html=True,
    )

    st.markdown("&nbsp;", unsafe_allow_html=True)
    st.markdown(
        f"""
        <div class="mi-cloudpanel">
          <h4>Commercial-cloud equivalent</h4>
          <div style="color:#E8E8E8;font-size:12px;">
            Single endpoint, single multi-tenant model, no per-step routing.
          </div>
          <div style="color:{BRAND['text_dim']};font-size:11px;margin-top:4px;">
            Total latency ~{cb.get('total_latency_s', '?')}s ·
            Total egress {cb.get('total_egress_kb', '?')} kB
          </div>
          <div class="leak"><strong>{cb.get('leak_count', 0)}</strong> step(s) would leak classified content.</div>
          <div style="color:#FF6B6B;font-size:12px;margin-top:4px;">
            Verdict: {cb.get('verdict', '—')}
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

# ── Per-step routing trace ───────────────────────────────────────────────
st.markdown("### Per-step routing decisions")
for i, step in enumerate(trace):
    r = step["route"]
    sens = step["sensitivity"]
    nid = r["node_id"]
    cls = "edge" if "edge" in nid else ("scif" if "scif" in nid else "rear")
    sens_color = {
        "UNCLASS": BRAND["neon"],
        "CUI": BRAND["primary"],
        "SECRET": "#FFB454",
        "TS-SCI": "#FF6B6B",
    }.get(sens, BRAND["primary"])
    egress_text = "0 (airgap)" if r["egress_kb"] == 0 else f"{r['egress_kb']} kB"
    live_text = ""
    le = r.get("live_endpoint")
    if le and le.get("active"):
        live_text = f" &nbsp;·&nbsp; <span style='color:{BRAND['primary']}'>LIVE @ {le['base_url']}</span>"
    st.markdown(
        f"""
        <div class="mi-step {cls}">
          <div class="h">Step {i+1} · {step['task_label']}
            &nbsp;<span style="color:{sens_color};font-size:11px;">[{SENS[sens]['label']}]</span>
          </div>
          <div class="meta">
            Routed to: <strong>{r['label']}</strong> &nbsp;·&nbsp;
            Model: <span class="mi-kbd">{r['model']}</span> &nbsp;·&nbsp;
            Posture: {r['security_posture']} &nbsp;·&nbsp;
            Net: {r['network_class']}{live_text}
          </div>
          <div class="meta">
            Latency: <strong>{r['latency_s']}s</strong> &nbsp;·&nbsp;
            Egress: <strong>{egress_text}</strong> &nbsp;·&nbsp;
            Input: {step['input_summary']}
          </div>
          <div class="why">why: {r['rationale']}</div>
          <div class="out">{step['output']}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

# ── Audit log + verify ──────────────────────────────────────────────────
audit_col, env_col = st.columns([1.4, 1.0])
with audit_col:
    st.markdown("### Hash-chained routing audit")
    ok, n_entries, msg = audit.verify_chain()
    badge = ('<span class="ok">CHAIN OK</span>' if ok else '<span class="deny">CHAIN BROKEN</span>')
    st.markdown(
        f'<div class="mi-audit"><div>{badge} &nbsp;·&nbsp; {n_entries} entries &nbsp;·&nbsp; {msg}</div>',
        unsafe_allow_html=True,
    )
    last = audit.tail(8)
    rows = []
    for e in last:
        rows.append(
            f"<div>"
            f"<span class='hash'>{e.get('entry_hash','')[:10]}…</span> "
            f"<strong>{e.get('kind','?')}</strong> "
            f"sc=<span style='color:#9FD6BB'>{e.get('scenario_id') or '—'}</span> "
            f"step=<span style='color:#9FD6BB'>{e.get('step') if e.get('step') is not None else '—'}</span> "
            f"node=<span style='color:#9FD6BB'>{e.get('node_id') or '—'}</span> "
            f"sens={e.get('sensitivity') or '—'} "
            f"lat={e.get('latency_s')}s egress={e.get('egress_kb')}kB"
            f"</div>"
        )
    st.markdown("\n".join(rows) + "</div>", unsafe_allow_html=True)
    st.caption(
        "SJA query: `did step 3 ever leave the SCIF?` → "
        "`jq 'select(.step==3) | {node_id, egress_kb}' data/routing_audit.jsonl`"
    )

with env_col:
    st.markdown("### KAMIWAZA — multi-endpoint env-var pattern")
    edge_url = os.getenv("KAMIWAZA_EDGE_URL", "(unset — sim)")
    rear_url = os.getenv("KAMIWAZA_REAR_URL", "(unset — sim)")
    scif_url = os.getenv("KAMIWAZA_SCIF_URL", "(unset — sim)")
    st.markdown(
        f"""
        <div class="mi-card" style="font-family:monospace;font-size:11px;">
          <div><span class="mi-kbd">KAMIWAZA_EDGE_URL</span> = {edge_url}</div>
          <div><span class="mi-kbd">KAMIWAZA_REAR_URL</span> = {rear_url}</div>
          <div><span class="mi-kbd">KAMIWAZA_SCIF_URL</span> = {scif_url}</div>
          <div style="color:{BRAND['text_dim']};margin-top:6px;">
            Set per-node endpoints and the router dispatches each step to the matching
            real Kamiwaza-deployed node — zero code change.
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

# ── Footer ───────────────────────────────────────────────────────────────
endpoint = os.getenv("KAMIWAZA_BASE_URL") or "Kamiwaza-deployed mesh (env-var swap to on-prem)"
st.markdown(
    f'<div class="mi-footer">'
    f'<span>Powered by Kamiwaza</span> &nbsp;·&nbsp; '
    f'Mesh endpoint: <code>{endpoint}</code> &nbsp;·&nbsp; '
    f'<em>"Orchestration without migration. Execution without compromise."</em>'
    f'</div>',
    unsafe_allow_html=True,
)
