"""CHAIN-OF-COMMAND — Marine ORBAT ReBAC graph + live authorization explainer.

Run:
    streamlit run src/app.py --server.port 3051 --server.headless true \
        --server.runOnSave false --server.fileWatcherType none \
        --browser.gatherUsageStats false
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import folium
import networkx as nx
import streamlit as st
from streamlit_folium import st_folium

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
APP = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP))

from shared.kamiwaza_client import BRAND  # noqa: E402

from src import audit  # noqa: E402
from src.engine import (  # noqa: E402
    compute_access, get_graph, three_way_compare,
    load_personnel, load_documents, load_demo_queries, load_cached_briefs,
    load_relationship_types, RBAC_ROLE_ACL, COMMAND_EDGE_TYPES,
)
from src.llm import narrate_access  # noqa: E402

st.set_page_config(
    page_title="CHAIN-OF-COMMAND — ReBAC Authorization on the Marine ORBAT",
    page_icon=":shield:",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ─────────────────────────────────────────────────────────────────────────────
# Theme
# ─────────────────────────────────────────────────────────────────────────────
CSS = f"""
<style>
  .stApp {{ background: {BRAND['bg']}; color: #E8E8E8; }}
  [data-testid="stHeader"] {{ background: transparent; }}
  [data-testid="stToolbar"] {{ display: none; }}
  section[data-testid="stSidebar"] {{
    background: {BRAND['surface']};
    border-right: 1px solid {BRAND['border']};
  }}
  .coc-hero {{
    background: linear-gradient(135deg, {BRAND['surface']} 0%, {BRAND['bg']} 100%);
    border: 1px solid {BRAND['border']};
    border-left: 4px solid {BRAND['primary']};
    border-radius: 8px;
    padding: 16px 22px;
    margin-bottom: 12px;
  }}
  .coc-hero h1 {{
    color: {BRAND['neon']};
    font-family: 'Helvetica Neue', sans-serif;
    font-size: 26px;
    margin: 0;
    letter-spacing: -0.5px;
  }}
  .coc-hero p {{
    color: {BRAND['text_dim']};
    margin: 4px 0 0 0;
    font-size: 13px;
  }}
  .coc-pill {{
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
  .coc-card {{
    background: {BRAND['surface']};
    border: 1px solid {BRAND['border']};
    border-radius: 6px;
    padding: 12px 16px;
    margin-bottom: 8px;
  }}
  .coc-allow {{ color: {BRAND['primary']}; font-weight: 700; letter-spacing: 0.5px; }}
  .coc-deny  {{ color: #FF6B6B; font-weight: 700; letter-spacing: 0.5px; }}
  .coc-edge {{
    font-family: 'SFMono-Regular', Menlo, monospace;
    background: #000;
    border: 1px solid {BRAND['border']};
    color: {BRAND['neon']};
    padding: 1px 8px;
    border-radius: 3px;
    font-size: 11px;
    margin: 0 3px;
  }}
  .coc-cmp {{
    border: 1px solid {BRAND['border']};
    border-radius: 6px;
    padding: 12px 14px;
    margin-bottom: 8px;
    background: {BRAND['surface']};
  }}
  .coc-cmp.allow {{ border-left: 4px solid {BRAND['primary']}; }}
  .coc-cmp.deny  {{ border-left: 4px solid #FF6B6B; }}
  .coc-footer {{
    color: {BRAND['text_dim']};
    font-size: 12px;
    text-align: center;
    padding: 16px 0 4px 0;
    border-top: 1px solid {BRAND['border']};
    margin-top: 28px;
  }}
  .coc-footer span {{ color: {BRAND['primary']}; font-weight: 600; }}
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
  hr {{ border-color: {BRAND['border']}; }}
</style>
"""
st.markdown(CSS, unsafe_allow_html=True)

# ─────────────────────────────────────────────────────────────────────────────
# Hero
# ─────────────────────────────────────────────────────────────────────────────
HERO = """
<div class="coc-hero">
  <h1>CHAIN-OF-COMMAND — ReBAC Authorization on the Marine ORBAT</h1>
  <p><strong>Relationship-Based Access Control</strong> (Google Zanzibar / OpenFGA-style)
     modeled as the actual Marine ORBAT graph with OPCON / TACON / attached / detached
     command relationships. Authorization is a <em>graph walk</em>.</p>
  <p style="margin-top:8px;">
    <span class="coc-pill">ReBAC graph-walk</span>
    <span class="coc-pill">JP 3-0 OPCON / TACON</span>
    <span class="coc-pill">DoDM 5200.02 clearance</span>
    <span class="coc-pill">Hash-chained audit</span>
    <span class="coc-pill">USMC LOGCOM 2026</span>
  </p>
</div>
"""
st.markdown(HERO, unsafe_allow_html=True)

# ─────────────────────────────────────────────────────────────────────────────
# Load data
# ─────────────────────────────────────────────────────────────────────────────
PERSONNEL = load_personnel()
DOCS = load_documents()
QUERIES = load_demo_queries()
CACHE = load_cached_briefs()
RELTYPES = load_relationship_types()

# ─────────────────────────────────────────────────────────────────────────────
# Session state
# ─────────────────────────────────────────────────────────────────────────────
if "subject_id" not in st.session_state:
    st.session_state.subject_id = "P_SMITH"
if "object_id" not in st.session_state:
    st.session_state.object_id = "DOC_008"
if "opcon_target" not in st.session_state:
    st.session_state.opcon_target = "USINDOPACOM"
if "verdict" not in st.session_state:
    st.session_state.verdict = None
if "narration" not in st.session_state:
    st.session_state.narration = None

# ─────────────────────────────────────────────────────────────────────────────
# Sidebar — query builder + the OPCON live-flip dial
# ─────────────────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("### Access query")
    st.caption("Subject (Marine) requests Object (Document). The engine walks the relationship graph.")

    sub_options = {f"{p['name']}  ·  {p['rank']}  ·  {p['nationality']}  ·  {p['clearance']}": p["id"]
                   for p in PERSONNEL}
    sub_label = st.selectbox(
        "Subject",
        list(sub_options.keys()),
        index=list(sub_options.values()).index(st.session_state.subject_id)
              if st.session_state.subject_id in sub_options.values() else 0,
    )
    st.session_state.subject_id = sub_options[sub_label]

    obj_options = {f"{d['id']}  ·  {d['classification']}  ·  {d['title'][:40]}": d["id"] for d in DOCS}
    obj_label = st.selectbox(
        "Document",
        list(obj_options.keys()),
        index=list(obj_options.values()).index(st.session_state.object_id)
              if st.session_state.object_id in obj_options.values() else 0,
    )
    st.session_state.object_id = obj_options[obj_label]

    st.markdown("---")
    st.markdown("### Pre-warmed scenarios")
    st.caption("Six demo queries demonstrate different graph-walks (cache-first).")
    for q in QUERIES:
        if st.button(f"-> {q['label']}", key=f"q_{q['id']}", use_container_width=True):
            st.session_state.subject_id = q["subject"]
            st.session_state.object_id = q["object"]
            st.session_state.verdict = None
            st.session_state.narration = None
            st.session_state.demo_query_id = q["id"]
            st.rerun()

    st.markdown("---")
    st.markdown("### Live OPCON dial")
    st.caption("Mutate the 24th MEU's OPCON relationship and watch Smith's access flip.")
    target_options = ["USINDOPACOM", "USEUCOM", "USCENTCOM", "(detach — no OPCON)"]
    new_target = st.selectbox(
        "24th MEU is OPCON to:",
        target_options,
        index=target_options.index(st.session_state.opcon_target)
              if st.session_state.opcon_target in target_options else 0,
    )
    if new_target != st.session_state.opcon_target:
        st.session_state.opcon_target = new_target
        st.session_state.verdict = None
        st.session_state.narration = None
        st.rerun()

    st.markdown("---")
    st.markdown("### Relationship taxonomy")
    for rt in RELTYPES:
        st.markdown(
            f'<div style="font-size:11px;color:{BRAND["text_dim"]};margin-bottom:2px;">'
            f'<span class="coc-edge" style="color:{rt["color"]};">{rt["id"]}</span> &nbsp;'
            f'{rt["label"]}</div>',
            unsafe_allow_html=True,
        )


# ─────────────────────────────────────────────────────────────────────────────
# Build current overrides for the OPCON dial
# ─────────────────────────────────────────────────────────────────────────────
def _current_overrides() -> dict:
    target = st.session_state.opcon_target
    rem = [{"src": "24MEU", "dst": "USINDOPACOM", "rel": "OPCON_TO"}]
    add: list[dict] = []
    if target != "(detach — no OPCON)" and target != "USINDOPACOM":
        add.append({"src": "24MEU", "dst": target, "rel": "OPCON_TO",
                    "order_ref": "operator override (live demo)",
                    "effective": "now"})
    elif target == "USINDOPACOM":
        # Restore the default
        rem = []
    return {"add": add, "remove": rem}


overrides = _current_overrides()

# ─────────────────────────────────────────────────────────────────────────────
# Run the verdict (cached if scenario, live otherwise)
# ─────────────────────────────────────────────────────────────────────────────
def _try_cached() -> dict | None:
    if st.session_state.opcon_target != "USINDOPACOM":
        return None  # Operator mutated graph — re-run live
    qid = st.session_state.get("demo_query_id")
    if not qid:
        return None
    cached = CACHE.get("queries", {}).get(qid)
    if not cached:
        return None
    if cached["verdict"].get("subject", {}).get("id") != st.session_state.subject_id:
        return None
    if cached["verdict"].get("object", {}).get("id") != st.session_state.object_id:
        return None
    return cached


if st.session_state.verdict is None:
    cached = _try_cached()
    if cached:
        st.session_state.verdict = cached["verdict"]
        st.session_state.narration = cached.get("narration")
        st.session_state._cached = True
    else:
        with st.status("Walking the relationship graph…", expanded=False) as status:
            v = compute_access(st.session_state.subject_id,
                               st.session_state.object_id,
                               overrides=overrides)
            st.session_state.verdict = v
            st.session_state._cached = False
            status.update(label="Graph walk complete.", state="complete")
        # Append to audit chain
        try:
            audit.append({
                "layer": "rebac_query",
                "event": "ACCESS_DECIDED",
                "subject_id": st.session_state.subject_id,
                "object_id": st.session_state.object_id,
                "decision": st.session_state.verdict.get("decision"),
                "opcon_override": st.session_state.opcon_target,
                "path_len": len(st.session_state.verdict.get("authorizing_path", {}).get("edges", [])
                                if st.session_state.verdict.get("authorizing_path") else []),
            })
        except Exception:
            pass

verdict = st.session_state.verdict


# ─────────────────────────────────────────────────────────────────────────────
# Top: verdict banner + three-way compare
# ─────────────────────────────────────────────────────────────────────────────
def _verdict_banner(v: dict) -> None:
    decision = v.get("decision", "?")
    cls = "coc-allow" if decision == "ALLOW" else "coc-deny"
    summary = v.get("reason_summary", "")
    st.markdown(
        f'<div class="coc-card" style="border-left:4px solid '
        f'{BRAND["primary"] if decision == "ALLOW" else "#FF6B6B"}; padding:14px 18px;">'
        f'<div style="font-size:11px;color:{BRAND["text_dim"]};letter-spacing:1.2px;'
        f'text-transform:uppercase;">ReBAC verdict</div>'
        f'<div style="font-size:28px;" class="{cls}">{decision}</div>'
        f'<div style="color:{BRAND["text_dim"]};font-size:13px;margin-top:4px;">{summary}</div>'
        f'</div>',
        unsafe_allow_html=True,
    )


_verdict_banner(verdict)

# Three-way compare
cmp = three_way_compare(st.session_state.subject_id, st.session_state.object_id, overrides=overrides)
c1, c2, c3 = st.columns(3)
for col, name, label, deck in zip(
    (c1, c2, c3),
    ("rbac", "abac", "rebac"),
    ("RBAC (role list)", "ABAC (attribute match)", "ReBAC (graph walk)"),
    (cmp["rbac"], cmp["abac"], cmp["rebac"]),
):
    decision = deck.get("decision", "?")
    cls = "coc-cmp allow" if decision == "ALLOW" else "coc-cmp deny"
    badge_cls = "coc-allow" if decision == "ALLOW" else "coc-deny"
    reason = deck.get("reason") or deck.get("reason_summary", "")
    col.markdown(
        f'<div class="{cls}">'
        f'<div style="font-size:11px;color:{BRAND["text_dim"]};letter-spacing:1.2px;text-transform:uppercase;">{label}</div>'
        f'<div class="{badge_cls}" style="font-size:18px;margin:2px 0 6px 0;">{decision}</div>'
        f'<div style="font-size:11px;color:#CCC;">{reason}</div>'
        f'</div>',
        unsafe_allow_html=True,
    )

# ─────────────────────────────────────────────────────────────────────────────
# Authorizing path — visual graph walk
# ─────────────────────────────────────────────────────────────────────────────
st.markdown("&nbsp;")
st.markdown("##### Authorizing path (graph-walk computation)")
st.caption(
    "ReBAC walks the actual ORBAT — MEMBER_OF for organic chain, ATTACHED_TO / "
    "DETACHED_TO for task-org, OPCON_TO / TACON_TO for command relationships. "
    "Need-to-know inherits down the OPCON path; clearance + REL_TO are checked at the leaf."
)

path = verdict.get("authorizing_path")
if path:
    nodes = path["nodes"]
    edges = path["edges"]
    edge_html = []
    for i, e in enumerate(edges):
        rel_color = next((rt["color"] for rt in RELTYPES if rt["id"] == e["rel"]), BRAND["neon"])
        edge_html.append(
            f'<span style="color:{BRAND["text_dim"]};">{nodes[i]}</span> '
            f'<span class="coc-edge" style="color:{rel_color};border-color:{rel_color};">{e["rel"]}</span> '
        )
    edge_html.append(f'<span style="color:{BRAND["neon"]};font-weight:700;">{nodes[-1]}</span>')
    st.markdown(
        f'<div class="coc-card" style="font-size:13px;line-height:1.9;">'
        f'{"".join(edge_html)}'
        f'</div>',
        unsafe_allow_html=True,
    )
else:
    st.markdown(
        f'<div class="coc-card" style="border-left:4px solid #FF6B6B;font-size:13px;">'
        f'No authorizing path. The graph walk did not reach an org with HAS_NEED_TO_KNOW '
        f'for this document.'
        f'</div>',
        unsafe_allow_html=True,
    )

# ─────────────────────────────────────────────────────────────────────────────
# The three checks broken out
# ─────────────────────────────────────────────────────────────────────────────
st.markdown("##### Three checks")
left, right = st.columns([1.4, 1.0])

with left:
    for chk in verdict.get("checks", []):
        ok = chk.get("ok")
        marker = "✓" if ok else "✗"
        cls = "coc-allow" if ok else "coc-deny"
        st.markdown(
            f'<div class="coc-card" style="border-left:3px solid '
            f'{BRAND["primary"] if ok else "#FF6B6B"};">'
            f'<div style="font-size:11px;color:{BRAND["text_dim"]};letter-spacing:1.2px;text-transform:uppercase;">{chk["name"]}</div>'
            f'<div class="{cls}">{marker} &nbsp; {chk["reason"]}</div>'
            f'</div>',
            unsafe_allow_html=True,
        )

with right:
    st.markdown("##### LLM operator narration")
    st.caption("AI-narrated rationale (cache-first; click Refresh for live).")
    if st.session_state.narration:
        st.markdown(
            f'<div class="coc-card" style="border-left:3px solid {BRAND["neon"]};font-size:13px;">'
            f'{st.session_state.narration}</div>',
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            f'<div class="coc-card" style="font-size:12px;color:{BRAND["text_dim"]};">'
            f'No narration cached for this query. Click "Refresh narration" for a live call.</div>',
            unsafe_allow_html=True,
        )
    if st.button("Refresh narration", use_container_width=True):
        with st.spinner("Calling Kamiwaza-deployed model…"):
            st.session_state.narration = narrate_access(
                verdict, {"label": f"{st.session_state.subject_id} → {st.session_state.object_id}"}
            )
        st.rerun()

# ─────────────────────────────────────────────────────────────────────────────
# ORBAT graph viz — Folium map of MEUs / units, colored edges for command relations
# ─────────────────────────────────────────────────────────────────────────────
st.markdown("&nbsp;")
st.markdown("##### Marine ORBAT — geo overlay")
st.caption(
    "Units pinned at their garrison / float locations. Command edges (OPCON, TACON, "
    "ATTACHED, DETACHED) drawn between units. The authorizing path for this query is "
    "highlighted in neon."
)

g = get_graph(overrides)


def _build_map(g: nx.MultiDiGraph, path: dict | None) -> folium.Map:
    fmap = folium.Map(location=[20, -30], zoom_start=2, tiles="cartodbdark_matter",
                      control_scale=True)
    # Highlight set
    highlight_edges: set[tuple[str, str, str]] = set()
    highlight_nodes: set[str] = set()
    if path:
        for n in path["nodes"]:
            highlight_nodes.add(n)
        for e in path["edges"]:
            highlight_edges.add((e["src"], e["dst"], e["rel"]))

    # Pin units that have lat/lon
    for nid, nd in g.nodes(data=True):
        if nd.get("kind") in ("ccmd", "marfor", "mef", "div", "meu", "regt", "bn", "co", "plt", "sqd"):
            lat, lon = nd.get("lat"), nd.get("lon")
            if lat is None or lon is None:
                continue
            on_path = nid in highlight_nodes
            color = BRAND["neon"] if on_path else BRAND["primary"]
            radius = 9 if on_path else 5
            folium.CircleMarker(
                location=[lat, lon],
                radius=radius,
                color=color,
                fill=True,
                fill_color=color,
                fill_opacity=0.85 if on_path else 0.55,
                weight=3 if on_path else 1,
                popup=folium.Popup(
                    f"<b>{nd.get('label', nid)}</b><br>"
                    f"echelon: {nd.get('echelon', '?')}<br>"
                    f"id: {nid}",
                    max_width=250,
                ),
                tooltip=nd.get("label", nid),
            ).add_to(fmap)

    # Draw command edges
    for u, v, k, d in g.edges(keys=True, data=True):
        rel = d.get("rel", k)
        if rel not in COMMAND_EDGE_TYPES:
            continue
        u_data, v_data = g.nodes[u], g.nodes[v]
        if u_data.get("lat") is None or v_data.get("lat") is None:
            continue
        on_path = (u, v, rel) in highlight_edges
        rt = next((r for r in RELTYPES if r["id"] == rel), None)
        color = rt["color"] if rt else "#666"
        if on_path:
            color = BRAND["neon"]
        folium.PolyLine(
            locations=[(u_data["lat"], u_data["lon"]), (v_data["lat"], v_data["lon"])],
            color=color,
            weight=5 if on_path else 2,
            opacity=1.0 if on_path else 0.45,
            tooltip=f"{u} —[{rel}]→ {v}",
        ).add_to(fmap)
    return fmap


fmap = _build_map(g, path if verdict.get("decision") == "ALLOW" else None)
st_folium(fmap, width=None, height=420, returned_objects=[], key="orbat_map")

# ─────────────────────────────────────────────────────────────────────────────
# ORBAT subtree (text indented) for the subject — readable path explainer
# ─────────────────────────────────────────────────────────────────────────────
st.markdown("##### Subject ORBAT context")
sub = next(p for p in PERSONNEL if p["id"] == st.session_state.subject_id)
chain = []
cur = sub["current_unit"]
visited = set()
while cur and cur not in visited:
    visited.add(cur)
    if cur in g.nodes:
        nd = g.nodes[cur]
        chain.append((cur, nd.get("label", cur), nd.get("echelon", "?")))
    # parent via MEMBER_OF
    parents = [(v, d.get("rel", k)) for u, v, k, d in g.out_edges(cur, keys=True, data=True)
               if d.get("rel", k) == "MEMBER_OF"]
    cur = parents[0][0] if parents else None

cols_chain = st.columns(min(len(chain), 8) or 1)
for i, (cid, lbl, ech) in enumerate(chain):
    cols_chain[i % len(cols_chain)].markdown(
        f'<div class="coc-card" style="text-align:center;padding:8px 6px;">'
        f'<div style="font-size:10px;color:{BRAND["text_dim"]};letter-spacing:1px;">{ech}</div>'
        f'<div style="font-size:13px;color:{BRAND["neon"]};font-weight:700;">{lbl}</div>'
        f'</div>',
        unsafe_allow_html=True,
    )

# Show the dynamic command edges leaving the subject's chain
st.caption(
    "Dynamic command edges in play (computed live from current overrides):"
)
dyn_edges = []
for cid, _, _ in chain:
    for u, v, k, d in g.out_edges(cid, keys=True, data=True):
        rel = d.get("rel", k)
        if rel in ("OPCON_TO", "TACON_TO", "ATTACHED_TO", "DETACHED_TO"):
            dyn_edges.append((u, rel, v, d.get("order_ref", ""), d.get("effective", "")))
if dyn_edges:
    for u, rel, v, ref, eff in dyn_edges:
        rel_color = next((rt["color"] for rt in RELTYPES if rt["id"] == rel), BRAND["neon"])
        st.markdown(
            f'<div style="font-size:12px;margin:2px 0;color:#CCC;">'
            f'<span style="color:{BRAND["text_dim"]};">{u}</span> &nbsp;'
            f'<span class="coc-edge" style="color:{rel_color};border-color:{rel_color};">{rel}</span>&nbsp;'
            f'<span style="color:{BRAND["primary"]};">{v}</span> &nbsp;·&nbsp; '
            f'<span style="color:{BRAND["text_dim"]};">{ref} ({eff})</span>'
            f'</div>',
            unsafe_allow_html=True,
        )
else:
    st.markdown(
        f'<div style="font-size:12px;color:{BRAND["text_dim"]};">'
        f'(No dynamic command edges on this subject\'s chain right now — '
        f'authorization will rely on organic MEMBER_OF only.)</div>',
        unsafe_allow_html=True,
    )

# ─────────────────────────────────────────────────────────────────────────────
# Audit chain
# ─────────────────────────────────────────────────────────────────────────────
st.markdown("&nbsp;")
with st.expander("Hash-chained audit (last 10 verdicts)", expanded=False):
    chain_status = audit.verify()
    if chain_status.get("ok"):
        st.markdown(
            f'<div style="color:{BRAND["primary"]};font-family:monospace;font-size:12px;">'
            f'CHAIN OK — {chain_status["entries"]} entries, '
            f'tip = {chain_status.get("tip_hash", "?")[:16]}…</div>',
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            f'<div style="color:#FF6B6B;font-family:monospace;font-size:12px;">'
            f'CHAIN BROKEN at row {chain_status.get("broken_at")}: '
            f'{chain_status.get("reason")}</div>',
            unsafe_allow_html=True,
        )
    last = audit.read(limit=10)
    if last:
        for entry in last:
            st.markdown(
                f'<div style="font-family:monospace;font-size:11px;color:{BRAND["text_dim"]};margin-bottom:4px;">'
                f'<span style="color:{BRAND["primary"]};">[{entry.get("event", "?")}]</span> '
                f'{entry.get("subject_id")} → {entry.get("object_id")} '
                f'<span style="color:{BRAND["neon"]};">{entry.get("decision")}</span> '
                f'· path_len={entry.get("path_len")} · '
                f'opcon={entry.get("opcon_override")} · '
                f'hash={entry.get("entry_hash", "?")[:12]}…'
                f'</div>',
                unsafe_allow_html=True,
            )
    else:
        st.caption("No verdicts yet. Run a query to populate the audit chain.")

# ─────────────────────────────────────────────────────────────────────────────
# Footer
# ─────────────────────────────────────────────────────────────────────────────
import os
endpoint = os.getenv("KAMIWAZA_BASE_URL") or "Kamiwaza-deployed model (env-var swap to on-prem)"
st.markdown(
    f'<div class="coc-footer">'
    f'<span>Powered by Kamiwaza</span> &nbsp;·&nbsp; '
    f'Inference endpoint: <code>{endpoint}</code> &nbsp;·&nbsp; '
    f'ReBAC engine: NetworkX BFS over JP 3-0 command-relationship graph &nbsp;·&nbsp; '
    f'Synthetic stand-in for DEERS / MOL ORBAT + Keycloak realm export'
    f'</div>',
    unsafe_allow_html=True,
)
