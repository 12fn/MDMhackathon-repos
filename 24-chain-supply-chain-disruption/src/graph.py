"""NetworkX + Plotly supply-chain topology with risk-colored nodes/edges.

Three layers:
  1. Suppliers (square markers, sized by annual_value_musd)
  2. Chokepoints (diamond, status-colored)
  3. USMC end-items (circle, neon-outlined)

Edges are weighted by annual flow $M; thickness scales with flow.
"""
from __future__ import annotations

import math

import networkx as nx
import plotly.graph_objects as go


def _risk_color(r: float) -> str:
    if r < 4.0:
        return "#00BB7A"  # green
    if r < 6.5:
        return "#E0B341"  # amber
    if r < 8.0:
        return "#E36F2C"  # orange
    return "#D8362F"      # red


def _kind_symbol(kind: str) -> str:
    return {"supplier": "square", "chokepoint": "diamond",
            "end_item": "circle"}.get(kind, "circle")


def build_figure(suppliers: list[dict], edges: list[dict],
                 risk: dict[str, float] | None = None,
                 *, layout: str = "geo") -> go.Figure:
    """Render the 30-node topology.

    layout="geo": use lat/lon (with end-items clustered at Pentagon).
    layout="spring": NetworkX spring layout (more readable for the graph view).
    """
    risk = risk or {}
    by_id = {n["id"]: n for n in suppliers}

    if layout == "spring":
        g = nx.Graph()
        for n in suppliers:
            g.add_node(n["id"])
        for e in edges:
            if e["a"] in by_id and e["b"] in by_id:
                g.add_edge(e["a"], e["b"], weight=e.get("annual_value_musd", 1))
        pos = nx.spring_layout(g, seed=1776, k=0.45, iterations=80)
    else:
        # Geo layout — separate end-items into a vertical stack on the right
        end_items = [n for n in suppliers if n["kind"] == "end_item"]
        for i, n in enumerate(end_items):
            n["_lon"] = -60.0
            n["_lat"] = 40.0 - (i - len(end_items) / 2) * 6
        pos = {n["id"]: (n.get("_lon", n["lon"]), n.get("_lat", n["lat"]))
               for n in suppliers}

    # Edges
    edge_traces = []
    max_flow = max((e.get("annual_value_musd", 1) for e in edges), default=1)
    for e in edges:
        a, b = e["a"], e["b"]
        if a not in pos or b not in pos:
            continue
        ra = risk.get(a, 4.0); rb = risk.get(b, 4.0)
        c = _risk_color((ra + rb) / 2)
        x0, y0 = pos[a]; x1, y1 = pos[b]
        flow = e.get("annual_value_musd", 1)
        width = 0.6 + 4.0 * math.sqrt(flow / max_flow)
        edge_traces.append(go.Scatter(
            x=[x0, x1, None], y=[y0, y1, None],
            mode="lines",
            line=dict(color=c, width=width),
            hoverinfo="text",
            text=f"{by_id[a]['name']} → {by_id[b]['name']}<br>"
                 f"Mode: {e.get('mode','—').upper()}  •  Flow: ${flow:,}M/yr<br>"
                 f"Edge risk: {(ra + rb) / 2:.1f}/10",
            opacity=0.55,
            showlegend=False,
        ))

    # Nodes — split into three traces by kind for distinct symbols
    traces_by_kind: dict[str, dict] = {
        "supplier":   {"xs": [], "ys": [], "text": [], "color": [], "size": [], "label": []},
        "chokepoint": {"xs": [], "ys": [], "text": [], "color": [], "size": [], "label": []},
        "end_item":   {"xs": [], "ys": [], "text": [], "color": [], "size": [], "label": []},
    }
    max_value = max((n.get("annual_value_musd", 1) for n in suppliers), default=1)
    for n in suppliers:
        x, y = pos[n["id"]]
        bucket = traces_by_kind.setdefault(n["kind"], traces_by_kind["supplier"])
        r = risk.get(n["id"], 4.0)
        bucket["xs"].append(x); bucket["ys"].append(y)
        bucket["color"].append(_risk_color(r))
        bucket["size"].append(14 + 22 * math.sqrt(n.get("annual_value_musd", 1) / max_value))
        bucket["label"].append(n["id"])
        bucket["text"].append(
            f"<b>{n['name']}</b> ({n['id']})<br>"
            f"Kind: {n['kind']}  •  Country: {n['country']}<br>"
            f"Category: {n['category']}<br>"
            f"Annual flow: ${n.get('annual_value_musd', 0):,}M<br>"
            f"<b>Risk index: {r:.1f}/10</b>"
        )

    node_traces = []
    for kind, b in traces_by_kind.items():
        if not b["xs"]:
            continue
        node_traces.append(go.Scatter(
            x=b["xs"], y=b["ys"], mode="markers+text",
            marker=dict(symbol=_kind_symbol(kind), size=b["size"], color=b["color"],
                        line=dict(color="#0A0A0A", width=2)),
            text=b["label"], textposition="top center",
            textfont=dict(color="#E8E8E8", size=10, family="Helvetica"),
            hovertext=b["text"], hoverinfo="text",
            name=kind.replace("_", " ").title(),
            showlegend=True,
        ))

    fig = go.Figure(data=[*edge_traces, *node_traces])
    fig.update_layout(
        paper_bgcolor="#0A0A0A",
        plot_bgcolor="#0A0A0A",
        font=dict(color="#E8E8E8", family="Helvetica"),
        margin=dict(l=10, r=10, t=10, b=10),
        height=560,
        xaxis=dict(visible=False),
        yaxis=dict(visible=False),
        legend=dict(orientation="h", yanchor="bottom", y=1.0, xanchor="right", x=1.0,
                    bgcolor="rgba(14,14,14,0.6)", bordercolor="#222222",
                    font=dict(color="#E8E8E8", size=11)),
        hoverlabel=dict(bgcolor="#0E0E0E", bordercolor="#00BB7A",
                        font=dict(color="#E8E8E8", family="Helvetica")),
    )
    return fig


def build_chokepoint_map(chokepoints: list[dict]) -> go.Figure:
    """Folium-equivalent in Plotly: physical map of the four chokepoints + Taiwan."""
    color_map = {"WATCH": "#E0B341", "ELEVATED": "#E36F2C",
                 "DEGRADED": "#E36F2C", "CRITICAL": "#D8362F"}
    fig = go.Figure(go.Scattergeo(
        lon=[c["lon"] for c in chokepoints],
        lat=[c["lat"] for c in chokepoints],
        text=[f"<b>{c['name']}</b><br>Status: {c['status']}<br>"
              f"Daily transit: ${c['daily_transit_musd']:,}M<br>"
              f"Current event: {c['current_event']}" for c in chokepoints],
        marker=dict(
            size=[12 + c["daily_transit_musd"] / 1000 for c in chokepoints],
            color=[color_map.get(c["status"], "#7E7E7E") for c in chokepoints],
            line=dict(color="#0A0A0A", width=2),
            symbol="diamond",
        ),
        hoverinfo="text",
        mode="markers+text",
        textfont=dict(color="#E8E8E8", size=10),
        textposition="top center",
        name="Chokepoints",
    ))
    fig.update_geos(
        projection_type="natural earth",
        showland=True, landcolor="#111111",
        showocean=True, oceancolor="#0A0A0A",
        showcountries=True, countrycolor="#222222",
        showcoastlines=True, coastlinecolor="#222222",
        bgcolor="#0A0A0A",
    )
    fig.update_layout(
        paper_bgcolor="#0A0A0A", plot_bgcolor="#0A0A0A",
        font=dict(color="#E8E8E8"),
        margin=dict(l=0, r=0, t=10, b=10), height=380,
        showlegend=False,
    )
    return fig
