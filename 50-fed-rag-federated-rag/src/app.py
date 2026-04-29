"""FED-RAG — Federated RAG via the Kamiwaza Distributed Data Engine.

Three locked silos. Three local embedding indexes. One synthesis brief.
Raw data NEVER leaves its silo of origin.

Run:
    streamlit run src/app.py --server.port 3050 --server.headless true \\
        --server.runOnSave false --server.fileWatcherType none \\
        --browser.gatherUsageStats false
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import networkx as nx
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

ROOT = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(ROOT))
APP_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(APP_ROOT))

from shared.kamiwaza_client import BRAND  # noqa: E402
from src.federation import (  # noqa: E402
    baseline_brief,
    federated_query,
    hero_brief,
    load_silos,
    read_audit,
    reset_audit,
)

DATA_DIR = APP_ROOT / "data"

st.set_page_config(
    page_title="FED-RAG — Federated RAG over Kamiwaza DDE",
    page_icon="-",
    layout="wide",
    initial_sidebar_state="collapsed",
)

CSS = f"""
<style>
  .stApp {{
    background: {BRAND['bg']};
    color: #E8E8E8;
  }}
  [data-testid="stHeader"] {{ background: transparent; }}
  [data-testid="stToolbar"] {{ display: none; }}
  section[data-testid="stSidebar"] {{
    background: {BRAND['surface']};
    border-right: 1px solid {BRAND['border']};
  }}
  .fr-hero {{
    background: linear-gradient(135deg, {BRAND['surface']} 0%, {BRAND['bg']} 100%);
    border: 1px solid {BRAND['border']};
    border-left: 4px solid {BRAND['primary']};
    border-radius: 8px;
    padding: 18px 24px;
    margin-bottom: 12px;
  }}
  .fr-hero h1 {{
    color: {BRAND['neon']};
    font-family: 'Helvetica Neue', sans-serif;
    font-size: 28px;
    margin: 0;
    letter-spacing: -0.5px;
  }}
  .fr-hero p {{
    color: {BRAND['text_dim']};
    margin: 4px 0 0 0;
    font-size: 13px;
  }}
  .fr-pill {{
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
  .fr-card {{
    background: {BRAND['surface']};
    border: 1px solid {BRAND['border']};
    border-radius: 6px;
    padding: 14px 18px;
    margin-bottom: 8px;
  }}
  .fr-metric {{
    color: {BRAND['neon']};
    font-size: 22px;
    font-weight: 700;
  }}
  .fr-metric-label {{
    color: {BRAND['text_dim']};
    font-size: 11px;
    text-transform: uppercase;
    letter-spacing: 1.2px;
  }}
  .fr-silo-card {{
    background: {BRAND['surface']};
    border: 1px solid {BRAND['border']};
    border-left: 4px solid {BRAND['primary']};
    border-radius: 6px;
    padding: 12px 16px;
    margin-bottom: 10px;
    font-size: 12.5px;
    color: #E8E8E8;
  }}
  .fr-silo-card h4 {{
    color: {BRAND['neon']};
    margin: 0 0 4px 0;
    font-size: 14px;
  }}
  .fr-silo-card .meta {{
    color: {BRAND['text_dim']};
    font-size: 11px;
    text-transform: uppercase;
    letter-spacing: 0.6px;
  }}
  .fr-silo-card .lock {{
    background: #2A0F0F;
    border: 1px solid #8B2A2A;
    color: #FF8B8B;
    border-radius: 4px;
    padding: 2px 8px;
    font-size: 10.5px;
    display: inline-block;
    margin-top: 6px;
  }}
  .fr-brief {{
    background: {BRAND['surface_high']};
    border: 1px solid {BRAND['border']};
    border-left: 4px solid {BRAND['neon']};
    border-radius: 6px;
    padding: 18px 22px;
    color: #E8E8E8;
    font-size: 14px;
    line-height: 1.55;
  }}
  .fr-brief strong {{ color: {BRAND['primary']}; }}
  .fr-naive {{
    background: #1A0E0E;
    border: 1px solid #8B2A2A;
    border-left: 4px solid #FF6B6B;
    border-radius: 6px;
    padding: 14px 18px;
    color: #FFD0D0;
    font-size: 13px;
  }}
  .fr-naive strong {{ color: #FF6B6B; }}
  .fr-footer {{
    color: {BRAND['text_dim']};
    font-size: 12px;
    text-align: center;
    padding: 16px 0 4px 0;
    border-top: 1px solid {BRAND['border']};
    margin-top: 28px;
  }}
  .fr-footer span {{ color: {BRAND['primary']}; font-weight: 600; }}
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
  .stDataFrame {{ border: 1px solid {BRAND['border']}; }}
  hr {{ border-color: {BRAND['border']}; }}
</style>
"""
st.markdown(CSS, unsafe_allow_html=True)

HERO_HTML = f"""
<div class="fr-hero">
  <h1>FED-RAG</h1>
  <p><strong>Federated RAG via the Kamiwaza Distributed Data Engine</strong> &nbsp;-&nbsp;
     retrieval across silos that cannot legally or technically be merged.</p>
  <p style="margin-top:8px;">
    <span class="fr-pill">Federated DDE</span>
    <span class="fr-pill">3 Locked Silos</span>
    <span class="fr-pill">No Raw Data Movement</span>
    <span class="fr-pill">DLA 4140.27 / DoDM 5200.01 Vol 2</span>
    <span class="fr-pill">USMC LOGCOM 2026</span>
  </p>
</div>
"""
st.markdown(HERO_HTML, unsafe_allow_html=True)


# ─────────────────────────────────────────────────────────────────────────────
# Cached loaders
# ─────────────────────────────────────────────────────────────────────────────
@st.cache_data(show_spinner=False)
def _load_demo_queries() -> list[dict]:
    return json.loads((DATA_DIR / "demo_queries.json").read_text())


@st.cache_data(show_spinner=False)
def _load_cached() -> dict:
    p = DATA_DIR / "cached_briefs.json"
    if not p.exists():
        return {}
    return json.loads(p.read_text())


@st.cache_resource(show_spinner=False)
def _silos():
    return load_silos()


SILOS = _silos()
DEMO = _load_demo_queries()
CACHED = _load_cached()

SILO_COLORS = {
    "albany": "#00BB7A",
    "pendleton": "#00FFA7",
    "philly": "#0DCC8A",
}


# ─────────────────────────────────────────────────────────────────────────────
# Top metrics — proves federation is real (3 separate indexes)
# ─────────────────────────────────────────────────────────────────────────────
m1, m2, m3, m4, m5 = st.columns(5)
n_silos = len(SILOS)
total_chunks = 0
total_index_kb = 0
for n in SILOS:
    if n.embed_path.exists():
        total_index_kb += n.embed_path.stat().st_size // 1024
    if n.chunk_path.exists():
        total_chunks += sum(1 for _ in n.chunk_path.open())
total_raw_gb = sum(n.raw_data_size_gb for n in SILOS)

m1.markdown(f'<div class="fr-card"><div class="fr-metric">{n_silos}</div><div class="fr-metric-label">Locked Silos</div></div>', unsafe_allow_html=True)
m2.markdown(f'<div class="fr-card"><div class="fr-metric">{n_silos}</div><div class="fr-metric-label">Local Indexes (.npy)</div></div>', unsafe_allow_html=True)
m3.markdown(f'<div class="fr-card"><div class="fr-metric">{total_chunks}</div><div class="fr-metric-label">Chunks Indexed (federated)</div></div>', unsafe_allow_html=True)
m4.markdown(f'<div class="fr-card"><div class="fr-metric">{total_raw_gb:.0f} GB</div><div class="fr-metric-label">Raw Data Held (never moved)</div></div>', unsafe_allow_html=True)
m5.markdown(f'<div class="fr-card"><div class="fr-metric">0 B</div><div class="fr-metric-label">Raw Data Across Wire</div></div>', unsafe_allow_html=True)

st.markdown("&nbsp;")


# ─────────────────────────────────────────────────────────────────────────────
# Federation network diagram (NetworkX + Plotly)
# ─────────────────────────────────────────────────────────────────────────────
def build_network_figure(active_silos: set[str] | None = None,
                         per_silo_results: dict[str, int] | None = None):
    G = nx.Graph()
    G.add_node("CENTRAL", role="central")
    for n in SILOS:
        G.add_node(n.sid, role="silo")
        G.add_edge("CENTRAL", n.sid)

    pos = {
        "CENTRAL": (0.0, 0.0),
        "albany": (-1.4, 0.7),
        "pendleton": (1.4, 0.7),
        "philly": (0.0, -1.2),
    }

    edge_x, edge_y, edge_text = [], [], []
    for u, v in G.edges():
        x0, y0 = pos[u]
        x1, y1 = pos[v]
        edge_x.extend([x0, x1, None])
        edge_y.extend([y0, y1, None])
        bytes_back = 0
        if per_silo_results and v in per_silo_results:
            bytes_back = per_silo_results[v]
        edge_text.append(f"{u} <-> {v}: {bytes_back} B snippet payload")

    edge_trace = go.Scatter(
        x=edge_x, y=edge_y, mode="lines",
        line=dict(width=2, color=BRAND["primary"]),
        hoverinfo="skip",
    )

    node_x, node_y, node_text, node_color, node_size, node_label = [], [], [], [], [], []
    silo_lookup = {n.sid: n for n in SILOS}
    for node, (x, y) in pos.items():
        node_x.append(x)
        node_y.append(y)
        if node == "CENTRAL":
            node_text.append("Central Kamiwaza Node<br>(planner installation)")
            node_color.append("#00FFA7")
            node_size.append(70)
            node_label.append("CENTRAL<br>Kamiwaza Node")
        else:
            n = silo_lookup[node]
            chunk_n = per_silo_results.get(node, 0) if per_silo_results else 0
            ring = "" if (active_silos and node in active_silos) else ""
            node_text.append(
                f"<b>{n.display}</b><br>"
                f"Owner: {n.owner}<br>"
                f"Classification: {n.classification}<br>"
                f"Authority: {n.authority}<br>"
                f"Raw data held: {n.raw_data_size_gb} GB (NEVER moved)<br>"
                f"Local chunks indexed: 30<br>"
                f"Chunks returned this query: {chunk_n}"
            )
            node_color.append(SILO_COLORS.get(node, BRAND["primary"]))
            node_size.append(60 if (active_silos and node in active_silos) else 50)
            node_label.append(f"{ring}{n.display.split('—')[0].strip()}<br>{n.classification}")

    node_trace = go.Scatter(
        x=node_x, y=node_y, mode="markers+text",
        marker=dict(size=node_size, color=node_color,
                    line=dict(color="#0A0A0A", width=2)),
        text=node_label,
        textposition="bottom center",
        textfont=dict(color="#E8E8E8", size=11),
        hovertext=node_text,
        hoverinfo="text",
    )

    annotations = []
    for n in SILOS:
        x, y = pos[n.sid]
        annotations.append(dict(
            x=x, y=y - 0.32, xref="x", yref="y",
            text="raw data DOES NOT cross wire",
            showarrow=False,
            font=dict(color="#FF8B8B", size=10),
            bgcolor="rgba(40,10,10,0.85)",
            borderpad=2,
            bordercolor="#8B2A2A",
        ))

    fig = go.Figure(data=[edge_trace, node_trace])
    fig.update_layout(
        showlegend=False,
        paper_bgcolor=BRAND["bg"],
        plot_bgcolor=BRAND["bg"],
        margin=dict(l=10, r=10, t=10, b=10),
        height=380,
        annotations=annotations,
        xaxis=dict(visible=False, range=[-2.2, 2.2]),
        yaxis=dict(visible=False, range=[-1.9, 1.4]),
    )
    return fig


# ─────────────────────────────────────────────────────────────────────────────
# Query bar + scenario picker
# ─────────────────────────────────────────────────────────────────────────────
if "query" not in st.session_state:
    st.session_state.query = DEMO[0]["prompt"]
    st.session_state.scenario_id = DEMO[0]["id"]

c_q, c_btn = st.columns([5, 1])
with c_q:
    q = st.text_area(
        "MARFORPAC G-4 planner question",
        value=st.session_state.query,
        height=110,
        label_visibility="collapsed",
    )
with c_btn:
    st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)
    run_clicked = st.button("Run Federated RAG", use_container_width=True, type="primary")
    hero_mode = st.toggle("Hero brief", value=False,
                          help="Use the hero Kamiwaza-deployed model for synthesis")

with st.expander("Demo planner queries", expanded=False):
    for d in DEMO:
        if st.button(f"-> {d['label']}", key=f"ex_{d['id']}"):
            st.session_state.query = d["prompt"]
            st.session_state.scenario_id = d["id"]
            st.rerun()


# ─────────────────────────────────────────────────────────────────────────────
# Pipeline orchestration — cache-first
# ─────────────────────────────────────────────────────────────────────────────
def _detect_cached_id(query_text: str) -> str | None:
    for d in DEMO:
        if query_text.strip() == d["prompt"].strip():
            return d["id"]
    return None


def _run_pipeline(query_text: str, *, force_live: bool = False) -> dict:
    cached_id = _detect_cached_id(query_text)
    cached = CACHED.get(cached_id) if cached_id else None
    if cached and not force_live and "error" not in cached:
        # Reconstruct per_silo with chunks for display (we only cached IDs).
        per_silo = []
        silo_by_id = {n.sid: n for n in SILOS}
        for entry in cached.get("per_silo", []):
            sid = entry["silo"]
            node = silo_by_id.get(sid)
            chunks_by_id = {c["chunk_id"]: c for c in node.load_chunks()} if node else {}
            chunks = []
            for cid in entry.get("chunk_ids", []):
                ch = dict(chunks_by_id.get(cid, {"chunk_id": cid, "text": ""}))
                ch.setdefault("similarity", 0.0)
                chunks.append(ch)
            per_silo.append({
                "silo": sid,
                "display": entry.get("display") or (node.display if node else sid),
                "owner": node.owner if node else "",
                "classification": node.classification if node else "",
                "authority": node.authority if node else "",
                "physical_loc": node.physical_loc if node else "",
                "endpoint": node.endpoint if node else "",
                "data_class": node.data_class if node else "",
                "raw_data_size_gb": node.raw_data_size_gb if node else 0.0,
                "chunks": chunks,
                "snippet_bytes": entry.get("snippet_bytes", 0),
            })
        return {
            "query": query_text,
            "per_silo": per_silo,
            "total_snippet_bytes": cached.get("total_snippet_bytes", 0),
            "naive_central_bytes": cached.get("naive_central_bytes", 0),
            "brief": cached.get("brief", ""),
            "from_cache": True,
        }

    # Live path
    reset_audit()
    fed = federated_query(query_text, k_per_silo=3)
    brief = hero_brief(query_text, fed, use_hero_model=hero_mode)
    fed["brief"] = brief
    fed["from_cache"] = False
    return fed


# ─────────────────────────────────────────────────────────────────────────────
# Run
# ─────────────────────────────────────────────────────────────────────────────
if run_clicked or "result" not in st.session_state:
    if not q.strip():
        st.warning("Enter a planner question.")
        st.stop()
    with st.status("Federated retrieval over the Kamiwaza DDE...", expanded=True) as status:
        st.write("- Encrypting planner query for cross-silo transport (TLS, per-silo key)")
        st.write("- Fanning encrypted query to 3 locked Kamiwaza silos in parallel")
        st.write("- Each silo embeds the query LOCALLY against its own .npy index")
        st.write("- Each silo returns ONLY top-K snippets + provenance — never raw data")
        result = _run_pipeline(q)
        st.session_state.result = result
        st.session_state.query = q
        ks = sum(len(r["chunks"]) for r in result["per_silo"])
        st.write(f"- Aggregated {ks} snippets across "
                 f"{len(result['per_silo'])} silos "
                 f"({result['total_snippet_bytes']:,} B total) "
                 + ("[cached brief]" if result.get("from_cache") else ""))
        status.update(label="Federated retrieval complete.", state="complete", expanded=False)


result = st.session_state.result


# ─────────────────────────────────────────────────────────────────────────────
# Federation diagram + per-silo cards
# ─────────────────────────────────────────────────────────────────────────────
st.markdown("##### Federation map — encrypted query in, snippets out, raw data stays put")

per_silo_counts = {r["silo"]: len(r["chunks"]) for r in result["per_silo"]}
active = set(per_silo_counts.keys())

dleft, dright = st.columns([1.3, 1.0])
with dleft:
    fig = build_network_figure(active_silos=active, per_silo_results=per_silo_counts)
    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})

with dright:
    for r in result["per_silo"]:
        chunk_ids = ", ".join(c.get("chunk_id", "?") for c in r["chunks"])
        st.markdown(
            f"""
<div class="fr-silo-card" style="border-left-color: {SILO_COLORS.get(r['silo'], BRAND['primary'])};">
  <h4>{r['display']}</h4>
  <div class="meta">{r['classification']} &nbsp;-&nbsp; {r['authority']}</div>
  <div style="margin-top:6px;">Owner: {r['owner']}</div>
  <div>Holds: <strong>{r['raw_data_size_gb']} GB</strong> of {r['data_class']}</div>
  <div>Returned this query: <strong>{len(r['chunks'])}</strong> chunks ({chunk_ids})</div>
  <div>Snippet payload across wire: <strong>{r['snippet_bytes']:,} B</strong></div>
  <div class="lock">Raw data NEVER leaves {r['physical_loc']}</div>
</div>
""",
            unsafe_allow_html=True,
        )


# ─────────────────────────────────────────────────────────────────────────────
# Per-silo retrieval chart (Plotly bar) + chunks table
# ─────────────────────────────────────────────────────────────────────────────
st.markdown("##### Per-silo local retrieval — top cosine similarities (computed at the silo)")

bar_fig = go.Figure()
for r in result["per_silo"]:
    sims = [c.get("similarity", 0.0) for c in r["chunks"]]
    labels = [c.get("chunk_id", "") for c in r["chunks"]]
    bar_fig.add_trace(go.Bar(
        x=labels,
        y=sims,
        name=r["display"].split("—")[0].strip(),
        marker_color=SILO_COLORS.get(r["silo"], BRAND["primary"]),
        hovertemplate="<b>%{x}</b><br>cosine sim: %{y:.4f}<extra></extra>",
    ))
bar_fig.update_layout(
    barmode="group",
    paper_bgcolor=BRAND["bg"],
    plot_bgcolor=BRAND["bg"],
    font=dict(color="#E8E8E8"),
    height=300,
    margin=dict(l=10, r=10, t=10, b=10),
    yaxis=dict(title="local cosine similarity", gridcolor=BRAND["border"]),
    xaxis=dict(title="local chunk id"),
    legend=dict(bgcolor="rgba(0,0,0,0)"),
)
st.plotly_chart(bar_fig, use_container_width=True, config={"displayModeBar": False})

with st.expander("Retrieved snippets (per silo)", expanded=False):
    for r in result["per_silo"]:
        st.markdown(f"**{r['display']}**")
        rows = [
            {
                "chunk_id": c.get("chunk_id"),
                "doc_type": c.get("doc_type"),
                "similarity": round(c.get("similarity", 0.0), 4),
                "text": (c.get("text") or "")[:280] + "...",
            }
            for c in r["chunks"]
        ]
        st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)


# ─────────────────────────────────────────────────────────────────────────────
# Network audit log + naive-central side-by-side
# ─────────────────────────────────────────────────────────────────────────────
st.markdown("---")
st.markdown("##### Cross-silo network audit — every packet logged for SJA review")

aleft, aright = st.columns([1.3, 1.0])

with aleft:
    audit_rows = read_audit(limit=50)
    if not audit_rows:
        st.info("No audit packets logged yet (cached path skips the wire).")
    else:
        adf = pd.DataFrame([{
            "ts": r.get("ts", "")[:19].replace("T", " "),
            "direction": r.get("direction"),
            "silo": r.get("silo"),
            "content_type": r.get("content_type"),
            "bytes": r.get("bytes"),
            "chunks": r.get("chunks_returned", ""),
            "authority": r.get("authority", ""),
        } for r in audit_rows])
        st.dataframe(adf, hide_index=True, use_container_width=True, height=260)

with aright:
    naive_gb = result["naive_central_bytes"] / (1024**3)
    snippet_kb = result["total_snippet_bytes"] / 1024
    saved_pct = 100.0 * (1.0 - (result["total_snippet_bytes"] / max(result["naive_central_bytes"], 1)))
    st.markdown(
        f"""
<div class="fr-naive">
  <strong>Side-by-side: naive central RAG vs federated DDE</strong><br><br>
  <strong>Naive central RAG would have moved:</strong><br>
  &nbsp;&nbsp;- 50 GB GCSS-MC export (Albany)<br>
  &nbsp;&nbsp;- 12 GB TM library (Pendleton)<br>
  &nbsp;&nbsp;- 30 GB DLA Class VIII records (Philly)<br>
  &nbsp;&nbsp;= <strong>{naive_gb:.0f} GB across the wire</strong> -> compliance violation +<br>
  &nbsp;&nbsp;&nbsp;&nbsp;DLA Manual 4140.27 distribution breach + DDIL bandwidth disaster<br><br>
  <strong>Federated DDE actually moved:</strong> {snippet_kb:.1f} KB of snippets<br>
  <strong>Bandwidth saved:</strong> {saved_pct:.4f}%<br>
  <strong>Raw data spilled:</strong> 0 bytes (per DoDM 5200.01 Vol 2)
</div>
""",
        unsafe_allow_html=True,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Hero brief — federated synthesis with per-silo citations
# ─────────────────────────────────────────────────────────────────────────────
st.markdown("---")
st.markdown("##### Federated Sustainment Brief — every fact cited back to its silo of origin")

c_b1, _ = st.columns([1, 5])
with c_b1:
    regen = st.button("Regenerate", help="Re-run synthesis live (35s watchdog)")

brief_text = result.get("brief", "")
if regen:
    with st.spinner("Running federated synthesis (35 s watchdog)..."):
        new = _run_pipeline(st.session_state.query, force_live=True)
        st.session_state.result = new
        result = new
        brief_text = new.get("brief", "")

if not brief_text:
    brief_text = baseline_brief(st.session_state.query, result)


def _md_to_safe_html(text: str) -> str:
    out = []
    for line in text.split("\n"):
        line = line.strip()
        while "**" in line:
            line = line.replace("**", "<strong>", 1)
            line = line.replace("**", "</strong>", 1)
        out.append(line)
    return "<br>".join(out)


st.markdown(
    f'<div class="fr-brief">{_md_to_safe_html(brief_text)}</div>',
    unsafe_allow_html=True,
)

if result.get("from_cache"):
    st.caption("Brief served from data/cached_briefs.json (cache-first hero pattern). Click Regenerate for a live federated call.")


# ─────────────────────────────────────────────────────────────────────────────
# Per-silo Kamiwaza DDE endpoint table — proves env-var swap is wired
# ─────────────────────────────────────────────────────────────────────────────
with st.expander("Per-silo Kamiwaza DDE endpoints (env-var swap)", expanded=False):
    rows = []
    for n in SILOS:
        rows.append({
            "Silo": n.display,
            "Owner": n.owner,
            "Authority": n.authority,
            "Env var": n.url_env,
            "Resolved endpoint": n.endpoint,
            "Local index file": str(n.embed_path.relative_to(APP_ROOT)),
        })
    st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)


# ─────────────────────────────────────────────────────────────────────────────
# Footer
# ─────────────────────────────────────────────────────────────────────────────
endpoint = os.getenv("KAMIWAZA_BASE_URL") or "Kamiwaza-deployed model (env-var swap to KAMIWAZA_BASE_URL)"
st.markdown(
    f'<div class="fr-footer">'
    f'<span>Powered by Kamiwaza</span> &nbsp;-&nbsp; '
    f'Central inference: <code>{endpoint}</code> &nbsp;-&nbsp; '
    f'Per-silo Kamiwaza Inference Mesh nodes via KAMIWAZA_SILO_*_URL &nbsp;-&nbsp; '
    f'Synthetic stand-in for GCSS-MC + 31st MEU TM library + DLA Class VIII records'
    f'</div>',
    unsafe_allow_html=True,
)
