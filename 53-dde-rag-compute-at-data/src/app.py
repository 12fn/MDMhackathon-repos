"""DDE-RAG — Streamlit single-page app on port 3053.

The whole point: VISIBLY contrast naive central RAG vs Kamiwaza Distributed
Data Engine for the same federated question. Three nodes (Albany / Lejeune /
Quantico), each with its native data sized to scale (50 / 8 / 12 GB). Top
half of the diagram animates the naive path: large outbound data arrows.
Bottom half animates the DDE path: tiny inbound compute arrows + tiny
outbound answers. Counters tick up in lockstep.

Cache-first: 5 demo queries pre-warmed in data/cached_briefs.json. "Run live"
hits the LLM behind a 35s timeout w/ deterministic fallback. Every dispatch
decision appended to a SHA-256 hash-chained audit log.
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

import plotly.graph_objects as go
import streamlit as st

# Make repo + app roots importable
APP_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = Path(__file__).resolve().parents[3]
for p in (str(REPO_ROOT), str(APP_ROOT)):
    if p not in sys.path:
        sys.path.insert(0, p)

from shared.kamiwaza_client import BRAND  # noqa: E402

from src.agent import (  # noqa: E402
    append_audit,
    compose_answer,
    load_audit,
    load_cached_briefs,
)
from src.dde import (  # noqa: E402
    humanize_bytes,
    humanize_seconds,
    load_nodes,
    load_queries,
    simulate_execution,
)


# ---------------------------------------------------------------------------
# Page chrome + theme
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="DDE-RAG — Distributed Data Engine RAG",
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
      .dde-card {{ background-color: {BRAND['surface_high']};
                   border: 1px solid {BRAND['border']}; border-radius: 8px;
                   padding: 14px 18px; margin-bottom: 10px; }}
      .dde-card-naive {{ border-left: 4px solid #b04040; }}
      .dde-card-dde   {{ border-left: 4px solid {BRAND['neon']}; }}
      .dde-pill {{ display: inline-block; padding: 2px 10px; margin-right: 6px;
                   border-radius: 999px; background: {BRAND['primary']}; color: #0A0A0A;
                   font-weight: 600; font-size: 12px; }}
      .dde-pill-neon {{ background: {BRAND['neon']}; color: #062F1F; }}
      .dde-pill-amber{{ background: #d2a233; color: #0A0A0A; }}
      .dde-pill-red  {{ background: #b04040; color: #fff; }}
      .dde-metric-num{{ font-size: 26px; font-weight: 700; color: {BRAND['neon']}; }}
      .dde-metric-lbl{{ color: {BRAND['text_dim']}; font-size: 12px; }}
      .dde-trace     {{ color: {BRAND['neon']};
                        font-family: ui-monospace, Menlo, monospace;
                        font-size: 12px; white-space: pre-wrap; }}
      .dde-footer    {{ color: {BRAND['muted']}; text-align: center; font-size: 12px;
                        margin-top: 24px; padding-top: 12px;
                        border-top: 1px solid {BRAND['border']}; }}
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
                        letter-spacing:.06em;">DDE-RAG</div>
            <div style="color:{BRAND['text_dim']}; font-size:13px;">
              Distributed Data Engine RAG &mdash;
              <i>don't move the data, move the compute.</i>
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
          <span class="dde-pill">LOGCOM</span>
          <span class="dde-pill dde-pill-neon">DDE</span>
          <span class="dde-pill dde-pill-amber">ICD 503</span>
          <div style="color:{BRAND['text_dim']}; font-size:11px; margin-top:6px;">
            Kamiwaza pushes inference TO the data, not data to the inference.
            Federated answers in seconds, with zero data egress.
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

st.markdown("---")


# ---------------------------------------------------------------------------
# Data load (cached)
# ---------------------------------------------------------------------------
@st.cache_data(show_spinner=False)
def _nodes() -> list[dict]:
    return load_nodes()


@st.cache_data(show_spinner=False)
def _queries() -> list[dict]:
    return load_queries()


nodes = _nodes()
queries = _queries()
cached_briefs = load_cached_briefs()

if not nodes or not queries:
    st.error("No node/query data found. Run `python data/generate.py` first.")
    st.stop()


# ---------------------------------------------------------------------------
# Sidebar — DDE node config
# ---------------------------------------------------------------------------
with st.sidebar:
    st.markdown(
        f"### <span style='color:{BRAND['neon']}'>DDE Node Mesh</span>",
        unsafe_allow_html=True,
    )
    st.markdown(
        f"<div style='color:{BRAND['text_dim']}; font-size:12px;'>"
        "Three Kamiwaza-deployed inference containers, one per data node. "
        "The control plane reads endpoints from <code>KAMIWAZA_DDE_NODES</code>.</div>",
        unsafe_allow_html=True,
    )
    env_endpoints = os.getenv("KAMIWAZA_DDE_NODES", "(unset — using synthetic defaults)")
    st.code(f"KAMIWAZA_DDE_NODES={env_endpoints}", language="bash")

    for n in nodes:
        st.markdown(
            f"""
            <div class='dde-card' style='border-left: 4px solid {n['color']};'>
              <div style='font-weight:700; color:{n['color']};'>{n['label']}</div>
              <div style='color:{BRAND['text_dim']}; font-size:12px;'>
                {n['installation']}<br/>
                <b>Data:</b> {n['data_size_gb']:.0f} GB &nbsp;|&nbsp;
                <b>Link:</b> {n['bandwidth_mbps']} Mbps<br/>
                <b>Posture:</b> {n['security_posture']}<br/>
                <b>Authority:</b> {n['compliance_authority']}<br/>
                <b>Endpoint:</b> <code>{n['node_endpoint']}</code>
              </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    st.markdown(
        f"<div style='color:{BRAND['text_dim']}; font-size:11px; margin-top:8px;'>"
        "Real-Kamiwaza plug-in: see <code>data/load_real.py</code>. "
        "Synthetic mode is on by default.</div>",
        unsafe_allow_html=True,
    )


# ---------------------------------------------------------------------------
# Top — query picker
# ---------------------------------------------------------------------------
st.markdown("### Pick a federated question")
st.markdown(
    f"<div style='color:{BRAND['text_dim']}; font-size:13px; margin-bottom:8px;'>"
    "Each question requires data that lives across <b>two or more</b> "
    "installations. The naive path tries to centralize the data; the DDE path "
    "spawns inference where the data already is.</div>",
    unsafe_allow_html=True,
)

if "active_query_id" not in st.session_state:
    st.session_state.active_query_id = queries[0]["id"]

q_titles = [q["title"] for q in queries]
q_ids = [q["id"] for q in queries]
default_idx = q_ids.index(st.session_state.active_query_id)

picker_l, picker_r = st.columns([0.7, 0.3])
with picker_l:
    pick = st.selectbox(
        "Query",
        options=q_titles,
        index=default_idx,
        label_visibility="collapsed",
    )
    st.session_state.active_query_id = q_ids[q_titles.index(pick)]
with picker_r:
    run_clicked = st.button("Run side-by-side", type="primary",
                            use_container_width=True, key="run_btn")

active_query = next(q for q in queries if q["id"] == st.session_state.active_query_id)

st.markdown(
    f"""
    <div class='dde-card'>
      <div style='font-weight:700; color:{BRAND['neon']}; font-size:15px;'>
        {active_query['title']}
      </div>
      <div style='color:#E6E6E6; margin-top:4px; font-size:14px;'>
        &ldquo;{active_query['question']}&rdquo;
      </div>
      <div style='color:{BRAND['text_dim']}; font-size:12px; margin-top:6px;'>
        <b>Frame:</b> {active_query['frame']}<br/>
        <b>Stakes:</b> {active_query['stakes']}<br/>
        <b>Involves:</b> {", ".join(active_query['involves'])}
      </div>
    </div>
    """,
    unsafe_allow_html=True,
)


# ---------------------------------------------------------------------------
# Build trace
# ---------------------------------------------------------------------------
trace = simulate_execution(active_query, nodes)
naive = trace["naive"]
dde = trace["dde"]
savings = trace["savings"]


# ---------------------------------------------------------------------------
# Side-by-side execution-path diagram
# ---------------------------------------------------------------------------
st.markdown("### Side-by-side execution paths")
st.markdown(
    f"<div style='color:{BRAND['text_dim']}; font-size:12px; margin-bottom:8px;'>"
    "<b>Top:</b> naive central RAG &mdash; data flows OUT (large arrows). "
    "<b>Bottom:</b> Kamiwaza DDE &mdash; compute flows IN (small arrows), "
    "only answers come back. Animation runs once per query selection.</div>",
    unsafe_allow_html=True,
)

involved_ids = active_query["involves"]
involved_nodes = [n for n in nodes if n["id"] in involved_ids]


def _build_diagram(progress: float = 1.0) -> go.Figure:
    """Build the dual-path diagram. progress in [0,1] grows arrow widths."""
    fig = go.Figure()
    # Two horizontal bands: y=2 (naive), y=0 (dde). Center column = consumer.
    central_x = 4.5
    consumer_x = -0.5
    # Node x positions (left column)
    n_count = len(involved_nodes)
    ys_naive = [2 + 1.0 * (i - (n_count - 1) / 2) for i in range(n_count)]
    ys_dde = [0 + 1.0 * (i - (n_count - 1) / 2) for i in range(n_count)]

    # Background labels for the two bands
    fig.add_annotation(
        x=consumer_x, y=3.5, text="<b>NAIVE CENTRAL RAG</b>",
        showarrow=False, font=dict(color="#b04040", size=14), xanchor="left",
    )
    fig.add_annotation(
        x=consumer_x, y=1.5, text="<b>KAMIWAZA DDE</b>",
        showarrow=False, font=dict(color=BRAND["neon"], size=14), xanchor="left",
    )

    # ── NAIVE path ────────────────────────────────────────────────────────
    # Big arrows DATA → central
    for i, n in enumerate(involved_nodes):
        # Data lump at the node
        fig.add_trace(go.Scatter(
            x=[1.5], y=[ys_naive[i]],
            mode="markers+text",
            marker=dict(
                size=20 + n["data_size_gb"] * 1.2,
                color=n["color"], opacity=0.85,
                line=dict(color="#b04040", width=2),
            ),
            text=[f"{n['data_size_gb']:.0f} GB"],
            textfont=dict(color="#0A0A0A", size=11),
            textposition="middle center",
            hovertext=f"{n['label']} — {n['data_size_gb']:.0f} GB at "
                      f"{n['bandwidth_mbps']} Mbps",
            hoverinfo="text",
            showlegend=False,
        ))
        # Big outbound arrow scaled by GB
        width = max(2, min(18, n["data_size_gb"] * 0.5)) * progress
        fig.add_trace(go.Scatter(
            x=[1.7, central_x - 0.4],
            y=[ys_naive[i], 2],
            mode="lines+markers",
            line=dict(color="#b04040", width=width),
            marker=dict(symbol="arrow", size=14, angleref="previous",
                        color="#b04040"),
            opacity=0.7,
            hovertext=f"{n['label']} → central: {n['data_size_gb']:.0f} GB",
            hoverinfo="text",
            showlegend=False,
        ))
        # Node label
        fig.add_annotation(
            x=1.5, y=ys_naive[i] + 0.45,
            text=f"<b>{n['label']}</b>",
            showarrow=False,
            font=dict(color="#E6E6E6", size=10),
            xanchor="center",
        )

    # Central embedder
    fig.add_trace(go.Scatter(
        x=[central_x], y=[2], mode="markers+text",
        marker=dict(size=42, color="#b04040",
                    line=dict(color="#fff", width=2)),
        text=["Central<br>RAG"],
        textfont=dict(color="#fff", size=10),
        textposition="middle center",
        hovertext="Central embedder + LLM cluster (must hold ALL data).",
        hoverinfo="text",
        showlegend=False,
    ))
    # Consumer (operator) — naive
    fig.add_trace(go.Scatter(
        x=[consumer_x + 5.5], y=[2], mode="markers+text",
        marker=dict(size=22, color="#666"),
        text=["Operator"],
        textfont=dict(color="#fff", size=10),
        textposition="top center",
        showlegend=False,
    ))
    fig.add_trace(go.Scatter(
        x=[central_x + 0.4, consumer_x + 5.4],
        y=[2, 2], mode="lines",
        line=dict(color="#b04040", width=1.5, dash="dot"),
        opacity=0.6,
        showlegend=False,
    ))

    # ── DDE path ──────────────────────────────────────────────────────────
    for i, n in enumerate(involved_nodes):
        # Same data lump — but it stays put
        fig.add_trace(go.Scatter(
            x=[1.5], y=[ys_dde[i]],
            mode="markers+text",
            marker=dict(
                size=20 + n["data_size_gb"] * 1.2,
                color=n["color"], opacity=0.85,
                line=dict(color=BRAND["neon"], width=2),
            ),
            text=[f"{n['data_size_gb']:.0f} GB"],
            textfont=dict(color="#0A0A0A", size=11),
            textposition="middle center",
            hovertext=f"{n['label']} — DATA STAYS HERE",
            hoverinfo="text",
            showlegend=False,
        ))
        # Tiny INBOUND compute arrow (gateway → node)
        fig.add_trace(go.Scatter(
            x=[central_x - 0.4, 1.7],
            y=[0, ys_dde[i]],
            mode="lines+markers",
            line=dict(color=BRAND["neon"], width=2 * progress),
            marker=dict(symbol="arrow", size=10, angleref="previous",
                        color=BRAND["neon"]),
            opacity=0.9,
            hovertext=f"Gateway → {n['label']}: ~10 MB compute payload",
            hoverinfo="text",
            showlegend=False,
        ))
        # Tiny OUTBOUND answer arrow (node → gateway)
        fig.add_trace(go.Scatter(
            x=[1.7, central_x - 0.4],
            y=[ys_dde[i] + 0.08, 0 + 0.08],
            mode="lines+markers",
            line=dict(color=BRAND["primary"], width=1.5 * progress, dash="dash"),
            marker=dict(symbol="arrow", size=8, angleref="previous",
                        color=BRAND["primary"]),
            opacity=0.85,
            hovertext=f"{n['label']} → Gateway: ~35 KB answer",
            hoverinfo="text",
            showlegend=False,
        ))
        # Node label
        fig.add_annotation(
            x=1.5, y=ys_dde[i] + 0.45,
            text=f"<b>{n['label']}</b>",
            showarrow=False,
            font=dict(color="#E6E6E6", size=10),
            xanchor="center",
        )

    # Gateway
    fig.add_trace(go.Scatter(
        x=[central_x], y=[0], mode="markers+text",
        marker=dict(size=42, color=BRAND["neon"],
                    line=dict(color="#0A0A0A", width=2)),
        text=["Kamiwaza<br>Gateway"],
        textfont=dict(color="#062F1F", size=10),
        textposition="middle center",
        hovertext="Federated answer composed here. No raw data ingressed.",
        hoverinfo="text",
        showlegend=False,
    ))
    # Consumer (operator) — dde
    fig.add_trace(go.Scatter(
        x=[consumer_x + 5.5], y=[0], mode="markers+text",
        marker=dict(size=22, color="#666"),
        text=["Operator"],
        textfont=dict(color="#fff", size=10),
        textposition="top center",
        showlegend=False,
    ))
    fig.add_trace(go.Scatter(
        x=[central_x + 0.4, consumer_x + 5.4],
        y=[0, 0], mode="lines",
        line=dict(color=BRAND["neon"], width=2),
        opacity=0.85,
        showlegend=False,
    ))

    fig.update_layout(
        height=480,
        margin=dict(l=10, r=10, t=10, b=10),
        plot_bgcolor=BRAND["bg"],
        paper_bgcolor=BRAND["bg"],
        xaxis=dict(visible=False, range=[-1, 6]),
        yaxis=dict(visible=False, range=[-1.5, 4]),
        showlegend=False,
    )
    return fig


diagram_slot = st.empty()
diagram_slot.plotly_chart(_build_diagram(1.0), use_container_width=True,
                          key="dde_diagram_static")


# ---------------------------------------------------------------------------
# Bytes-transferred & wall-clock comparison panel (always shown)
# ---------------------------------------------------------------------------
st.markdown("### Bytes-transferred &amp; wall-clock comparison")

cmp_l, cmp_r = st.columns(2)
with cmp_l:
    st.markdown(
        f"""
        <div class='dde-card dde-card-naive'>
          <div style='font-weight:700; color:#b04040; font-size:14px;'>
            Naive central RAG
          </div>
          <div style='display:flex; gap:18px; margin-top:8px;'>
            <div>
              <div class='dde-metric-num' style='color:#b04040;'>
                {humanize_bytes(naive['bytes'])}
              </div>
              <div class='dde-metric-lbl'>bytes transferred</div>
            </div>
            <div>
              <div class='dde-metric-num' style='color:#b04040;'>
                {humanize_seconds(naive['seconds'])}
              </div>
              <div class='dde-metric-lbl'>wall-clock</div>
            </div>
          </div>
          <div style='margin-top:10px;'>
            <span class='dde-pill dde-pill-red'>{naive['compliance']}</span>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
with cmp_r:
    st.markdown(
        f"""
        <div class='dde-card dde-card-dde'>
          <div style='font-weight:700; color:{BRAND['neon']}; font-size:14px;'>
            Kamiwaza DDE (compute-at-data)
          </div>
          <div style='display:flex; gap:18px; margin-top:8px;'>
            <div>
              <div class='dde-metric-num'>
                {humanize_bytes(dde['bytes'])}
              </div>
              <div class='dde-metric-lbl'>bytes transferred</div>
            </div>
            <div>
              <div class='dde-metric-num'>
                {humanize_seconds(dde['seconds'])}
              </div>
              <div class='dde-metric-lbl'>wall-clock</div>
            </div>
          </div>
          <div style='margin-top:10px;'>
            <span class='dde-pill dde-pill-neon'>{dde['compliance']}</span>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

# Bytes bar chart (log-scale; emphasizes the gap)
bar = go.Figure()
bar.add_trace(go.Bar(
    x=["Naive central RAG", "Kamiwaza DDE"],
    y=[naive["bytes"], dde["bytes"]],
    marker=dict(color=["#b04040", BRAND["neon"]]),
    text=[humanize_bytes(naive["bytes"]), humanize_bytes(dde["bytes"])],
    textposition="outside",
    textfont=dict(color="#E6E6E6", size=14),
))
bar.update_layout(
    height=260,
    margin=dict(l=10, r=10, t=20, b=20),
    plot_bgcolor=BRAND["bg"],
    paper_bgcolor=BRAND["bg"],
    yaxis=dict(type="log", color="#E6E6E6", gridcolor="#222",
               title="bytes (log)"),
    xaxis=dict(color="#E6E6E6"),
)
st.plotly_chart(bar, use_container_width=True, key="bytes_bar")

st.markdown(
    f"""
    <div class='dde-card' style='border-color:{BRAND['neon']};'>
      <span class='dde-pill dde-pill-neon'>{savings['bytes_ratio']:,.0f}× less data over the wire</span>
      <span class='dde-pill'>{savings['seconds_ratio']:,.0f}× faster end-to-end</span>
      <span class='dde-pill dde-pill-amber'>
        {humanize_bytes(savings['bytes_saved'])} not crossing the wire
      </span>
    </div>
    """,
    unsafe_allow_html=True,
)


# ---------------------------------------------------------------------------
# Animation + run
# ---------------------------------------------------------------------------
if run_clicked:
    naive_byte_slot, dde_byte_slot = st.columns(2)
    naive_meter = naive_byte_slot.empty()
    dde_meter = dde_byte_slot.empty()
    diagram_anim_slot = st.empty()
    n_steps = 12
    for k in range(1, n_steps + 1):
        prog = k / n_steps
        # Animate the diagram with growing arrow widths
        diagram_anim_slot.plotly_chart(
            _build_diagram(prog), use_container_width=True,
            key=f"dde_diagram_anim_{k}")
        # Tick the byte counters
        naive_meter.markdown(
            f"<div class='dde-card dde-card-naive'>"
            f"<div class='dde-metric-num' style='color:#b04040;'>"
            f"{humanize_bytes(int(naive['bytes'] * prog))}</div>"
            f"<div class='dde-metric-lbl'>naive bytes (in flight)</div>"
            f"</div>",
            unsafe_allow_html=True,
        )
        dde_meter.markdown(
            f"<div class='dde-card dde-card-dde'>"
            f"<div class='dde-metric-num'>"
            f"{humanize_bytes(int(dde['bytes'] * prog))}</div>"
            f"<div class='dde-metric-lbl'>DDE bytes (in flight)</div>"
            f"</div>",
            unsafe_allow_html=True,
        )
        time.sleep(0.18)
    # Append to audit (cache-source by default; live below)
    rec = append_audit(active_query, trace, source="cache_run")
    try:
        st.toast(f"Logged dispatch decision (hash {rec['hash'][:10]}…)", icon="✅")
    except Exception:
        st.caption(f"Logged dispatch decision (hash {rec['hash'][:10]}…)")


# ---------------------------------------------------------------------------
# Federated answer
# ---------------------------------------------------------------------------
st.markdown("### Federated answer")

if "answer_text" not in st.session_state:
    st.session_state.answer_text = ""
    st.session_state.answer_source = "none"
    st.session_state.answer_query_id = ""

# Refresh from cache when query changes
if st.session_state.answer_query_id != active_query["id"]:
    cached = cached_briefs.get(active_query["id"], {})
    st.session_state.answer_text = cached.get("answer", "")
    st.session_state.answer_source = "cache" if cached.get("answer") else "none"
    st.session_state.answer_query_id = active_query["id"]

ans_l, ans_r = st.columns([0.78, 0.22])
with ans_r:
    if st.button("Run live (LLM)", use_container_width=True, key="live_btn"):
        with st.spinner("Composing federated answer (35s timeout, deterministic fallback)…"):
            text = compose_answer(active_query, nodes, trace, use_cache=False)
        st.session_state.answer_text = text
        st.session_state.answer_source = "hero"
        rec = append_audit(active_query, trace, source="hero_live")
        try:
            st.toast(f"Logged live dispatch (hash {rec['hash'][:10]}…)", icon="✅")
        except Exception:
            st.caption(f"Logged live dispatch (hash {rec['hash'][:10]}…)")

# Final fallback if nothing on screen
if not st.session_state.answer_text:
    st.session_state.answer_text = compose_answer(
        active_query, nodes, trace, use_cache=False)
    st.session_state.answer_source = "fallback"

src_label = {
    "cache":    '<span class="dde-pill dde-pill-neon">CACHED</span>',
    "hero":     '<span class="dde-pill">HERO LIVE</span>',
    "fallback": '<span class="dde-pill dde-pill-amber">DETERMINISTIC FALLBACK</span>',
    "none":     '<span class="dde-pill dde-pill-red">EMPTY</span>',
}.get(st.session_state.answer_source, "")

with ans_l:
    st.markdown(
        f"<div class='dde-card' style='border-color:{BRAND['neon']};'>"
        f"<b>Source:</b> {src_label} &nbsp;|&nbsp; "
        f"<b>Composed by:</b> Kamiwaza Model Gateway from {len(active_query['involves'])} "
        f"per-node DDE responses</div>",
        unsafe_allow_html=True,
    )

st.markdown(st.session_state.answer_text)


# ---------------------------------------------------------------------------
# Per-step transit log (technical detail beat)
# ---------------------------------------------------------------------------
st.markdown("### Transit log")
log_l, log_r = st.columns(2)
with log_l:
    st.markdown(
        f"<div style='color:#b04040; font-weight:700;'>Naive central RAG</div>",
        unsafe_allow_html=True,
    )
    rows = "\n".join(
        f"  [{s['kind']:<8}] {s['label']}: "
        f"{humanize_bytes(s['bytes'])} in {humanize_seconds(s['seconds'])}\n"
        f"           ↳ {s['note']}"
        for s in naive["steps"]
    )
    st.markdown(f"<pre class='dde-trace'>{rows}</pre>", unsafe_allow_html=True)
    if naive["spillage_flags"]:
        for flag in naive["spillage_flags"]:
            st.markdown(
                f"<div class='dde-card' style='border-left:4px solid #b04040;'>"
                f"<span class='dde-pill dde-pill-red'>SPILLAGE</span> {flag}</div>",
                unsafe_allow_html=True,
            )
with log_r:
    st.markdown(
        f"<div style='color:{BRAND['neon']}; font-weight:700;'>Kamiwaza DDE</div>",
        unsafe_allow_html=True,
    )
    rows = "\n".join(
        f"  [{s['kind']:<8}] {s['label']}: "
        f"{humanize_bytes(s['bytes'])} in {humanize_seconds(s['seconds'])}\n"
        f"           ↳ {s['note']}"
        for s in dde["steps"]
    )
    st.markdown(f"<pre class='dde-trace'>{rows}</pre>", unsafe_allow_html=True)
    st.markdown(
        f"<div class='dde-card' style='border-left:4px solid {BRAND['neon']};'>"
        f"<span class='dde-pill dde-pill-neon'>GREEN</span> "
        f"Zero data egress; ICD 503 + DCSA boundary preserved per node.</div>",
        unsafe_allow_html=True,
    )


# ---------------------------------------------------------------------------
# Hash-chained audit log
# ---------------------------------------------------------------------------
st.markdown("### Hash-chained DDE audit")
st.markdown(
    f"<div style='color:{BRAND['text_dim']}; font-size:12px; margin-bottom:8px;'>"
    "Every dispatch decision is appended to "
    "<code>data/audit_logs/dde_audit.jsonl</code> with SHA-256 chaining "
    "(<i>prev_hash</i> &rarr; <i>hash</i>). Tamper-evident, ICD-503 friendly.</div>",
    unsafe_allow_html=True,
)
audit = load_audit(tail=8)
if audit:
    audit_view = []
    for r in audit:
        audit_view.append({
            "ts": r.get("ts", ""),
            "query_id": r.get("query_id", ""),
            "dispatched_to": ", ".join(r.get("dispatched_to") or []),
            "naive_bytes": humanize_bytes(r.get("naive_bytes", 0)),
            "dde_bytes":   humanize_bytes(r.get("dde_bytes", 0)),
            "source":      r.get("source", ""),
            "hash":        (r.get("hash", "") or "")[:14] + "…",
            "prev_hash":   (r.get("prev_hash", "") or "")[:14] + "…",
        })
    st.dataframe(audit_view, use_container_width=True, hide_index=True, height=280)
else:
    st.info("Audit log empty — run a query above to populate.")


# ---------------------------------------------------------------------------
# Footer
# ---------------------------------------------------------------------------
st.markdown(
    f"<div class='dde-footer'>"
    f"Powered by Kamiwaza &nbsp;|&nbsp; Distributed Data Engine &mdash; "
    f"<code>KAMIWAZA_DDE_NODES</code> swap routes against your real Inference "
    f"Mesh. ICD 503 / IL5 / DDIL ready, air-gapped, zero data movement.</div>",
    unsafe_allow_html=True,
)
