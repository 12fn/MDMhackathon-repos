"""NetworkX + Plotly node-graph for the 4-node mesh.

Renders the 4 nodes laid out by region (edge afloat / rear CONUS / SCIF), with
edges from the operator origin to each node lit up only when that node served
a step in the current scenario.
"""
from __future__ import annotations

from typing import Iterable

import networkx as nx
import plotly.graph_objects as go


BRAND = {
    "primary": "#00BB7A",
    "neon": "#00FFA7",
    "deep_green": "#065238",
    "bg": "#0A0A0A",
    "surface": "#0E0E0E",
    "border": "#222222",
    "muted": "#7E7E7E",
    "warn": "#FFB454",
    "danger": "#FF6B6B",
}


def build_mesh_graph(nodes: list[dict]) -> nx.Graph:
    g = nx.Graph()
    g.add_node("operator", label="Marine Planner", role="operator", color="#FFFFFF")
    for n in nodes:
        g.add_node(n["node_id"], **{k: v for k, v in n.items() if k != "node_id"})
        g.add_edge("operator", n["node_id"])
    return g


# Hand-laid coords so the diagram reads left→right: edge — operator — rear — scif
LAYOUT = {
    "operator":              (0.0, 0.0),
    "edge-meusoc":           (-1.4, 0.4),
    "rear-quantico":         ( 1.0, 0.6),
    "scif-marforpac-mixtral":( 1.7,-0.3),
    "scif-marforpac-vl":     ( 1.7,-1.0),
}


def render_plot(nodes: list[dict], used_node_ids: Iterable[str], *,
                step_meta: dict[str, dict] | None = None) -> go.Figure:
    """Plotly figure of the mesh.

    used_node_ids — nodes that served at least one step (lit up).
    step_meta     — node_id -> dict with 'step_idx', 'sensitivity', 'task_label'
                    so we can annotate which node ran which step.
    """
    used = set(used_node_ids)
    step_meta = step_meta or {}

    # Edges
    edge_x: list[float] = []
    edge_y: list[float] = []
    edge_lit_x: list[float] = []
    edge_lit_y: list[float] = []
    for n in nodes:
        ox, oy = LAYOUT["operator"]
        nx_, ny_ = LAYOUT.get(n["node_id"], (0, 0))
        if n["node_id"] in used:
            edge_lit_x += [ox, nx_, None]
            edge_lit_y += [oy, ny_, None]
        else:
            edge_x += [ox, nx_, None]
            edge_y += [oy, ny_, None]

    edge_dim = go.Scatter(
        x=edge_x, y=edge_y, mode="lines",
        line=dict(width=1, color=BRAND["border"]),
        hoverinfo="none", showlegend=False,
    )
    edge_lit = go.Scatter(
        x=edge_lit_x, y=edge_lit_y, mode="lines",
        line=dict(width=3, color=BRAND["neon"]),
        hoverinfo="none", showlegend=False,
    )

    # Nodes
    node_x: list[float] = []
    node_y: list[float] = []
    node_color: list[str] = []
    node_size: list[int] = []
    node_text: list[str] = []
    node_hover: list[str] = []
    node_border: list[str] = []
    for nid, (x, y) in LAYOUT.items():
        node_x.append(x)
        node_y.append(y)
        if nid == "operator":
            node_color.append("#FFFFFF")
            node_size.append(30)
            node_text.append("Operator<br><span style='font-size:10px'>Marine Planner</span>")
            node_hover.append("Marine planner — issues the multi-step query.")
            node_border.append(BRAND["neon"])
            continue
        n = next((nn for nn in nodes if nn["node_id"] == nid), None)
        if not n:
            continue
        is_used = nid in used
        node_color.append(n["color"] if is_used else "#202020")
        node_size.append(46 if is_used else 32)
        meta = step_meta.get(nid, {})
        step_tag = f" <span style='color:{BRAND['neon']}'>step {meta['step_idx']+1}</span>" if meta else ""
        node_text.append(
            f"<b>{n['label']}</b>{step_tag}<br>"
            f"<span style='font-size:10px'>{n['model']} · {n['security_posture']}</span>"
        )
        node_hover.append(
            f"<b>{n['label']}</b><br>"
            f"Hardware: {n['hardware']}<br>"
            f"Model: {n['model']} ({n['parameters_b']}B, {n['quantization']})<br>"
            f"Serving: {n['serving']}<br>"
            f"Posture: {n['security_posture']} · Net: {n['network_class']}<br>"
            f"Median latency: {n['median_latency_s']}s · Egress: {n['egress_kb_per_call']} kB"
        )
        node_border.append(BRAND["neon"] if is_used else BRAND["border"])

    node_trace = go.Scatter(
        x=node_x, y=node_y, mode="markers+text",
        marker=dict(
            size=node_size,
            color=node_color,
            line=dict(width=2, color=node_border),
            symbol="circle",
        ),
        text=node_text,
        textposition="bottom center",
        textfont=dict(family="Helvetica Neue, Arial", color="#E8E8E8", size=11),
        hovertext=node_hover,
        hoverinfo="text",
        showlegend=False,
    )

    # Region annotations
    annotations = [
        dict(x=-1.4, y=1.0, text="<b>EDGE</b> · NIPR / DDIL", showarrow=False,
             font=dict(color=BRAND["primary"], size=11)),
        dict(x=0.0, y=0.55, text="<b>OPERATOR</b>", showarrow=False,
             font=dict(color="#FFFFFF", size=11)),
        dict(x=1.0, y=1.05, text="<b>REAR DEPOT</b> · NIPR+SIPR", showarrow=False,
             font=dict(color=BRAND["primary"], size=11)),
        dict(x=1.7, y=0.25, text="<b>SCIF</b> · JWICS · airgap", showarrow=False,
             font=dict(color=BRAND["primary"], size=11)),
        # SCIF perimeter rectangle
        dict(x=1.7, y=-1.5, text="No bandwidth out of SCIF",
             showarrow=False, font=dict(color=BRAND["muted"], size=10)),
    ]

    fig = go.Figure(data=[edge_dim, edge_lit, node_trace])
    # SCIF perimeter shape
    fig.update_layout(
        shapes=[
            dict(
                type="rect", xref="x", yref="y",
                x0=1.25, y0=-1.35, x1=2.15, y1=0.15,
                line=dict(color=BRAND["primary"], width=1, dash="dot"),
                fillcolor="rgba(0,187,122,0.05)",
            ),
        ],
        annotations=annotations,
        showlegend=False,
        margin=dict(l=10, r=10, t=10, b=10),
        xaxis=dict(showgrid=False, zeroline=False, visible=False, range=[-2.2, 2.5]),
        yaxis=dict(showgrid=False, zeroline=False, visible=False, range=[-1.7, 1.3]),
        plot_bgcolor=BRAND["bg"],
        paper_bgcolor=BRAND["bg"],
        height=460,
    )
    return fig
