"""NetworkX + Plotly supply-line topology with risk-colored edges."""
from __future__ import annotations

import networkx as nx
import plotly.graph_objects as go


def _risk_color(r: float) -> str:
    """0 -> Kamiwaza green, 5 -> amber, 10 -> red."""
    if r < 4.0:
        return "#00BB7A"  # Kamiwaza green = green/low
    if r < 6.5:
        return "#E0B341"  # amber
    if r < 8.0:
        return "#E36F2C"  # orange
    return "#D8362F"      # red


def _edge_color(risk_a: float, risk_b: float) -> str:
    return _risk_color((risk_a + risk_b) / 2)


def build_figure(nodes: list[dict], edges: list[dict],
                 scores: list[dict] | None = None) -> go.Figure:
    """Render a geographic-ish topology of the 12 critical nodes.

    Coordinates come straight from node lat/lon — no real basemap so it lives
    cleanly inside the Kamiwaza dark theme without external tile dependencies.
    """
    score_by_id = {s["node_id"]: s for s in (scores or [])}
    by_id = {n["id"]: n for n in nodes}

    # Use lon as x, lat as y for an easy map-ish layout.
    pos = {n["id"]: (n["lon"], n["lat"]) for n in nodes}

    edge_traces = []
    for e in edges:
        a, b = e["a"], e["b"]
        if a not in pos or b not in pos:
            continue
        ra = score_by_id.get(a, {}).get("risk_index", 4.0)
        rb = score_by_id.get(b, {}).get("risk_index", 4.0)
        c = _edge_color(ra, rb)
        x0, y0 = pos[a]; x1, y1 = pos[b]
        dash = {"sea": "solid", "air": "dash", "road": "dot", "cable": "dashdot"}.get(e["mode"], "solid")
        edge_traces.append(go.Scatter(
            x=[x0, x1, None], y=[y0, y1, None],
            mode="lines",
            line=dict(color=c, width=2.4, dash=dash),
            hoverinfo="text",
            text=f"{by_id[a]['name']} ↔ {by_id[b]['name']}<br>"
                 f"Mode: {e['mode'].upper()}  •  {e['leg_nm']} nm<br>"
                 f"Edge risk: {(ra + rb) / 2:.1f}/10",
            showlegend=False,
        ))

    # Nodes
    xs, ys, texts, colors, sizes, labels = [], [], [], [], [], []
    for n in nodes:
        s = score_by_id.get(n["id"], {})
        risk = s.get("risk_index", 4.0)
        threat = s.get("top_threat", "—")
        conf = s.get("confidence", "—")
        xs.append(n["lon"]); ys.append(n["lat"])
        labels.append(n["id"])
        colors.append(_risk_color(risk))
        sizes.append(14 + n["criticality"] * 1.2)
        texts.append(
            f"<b>{n['name']}</b> ({n['id']}) — {n['ccdr']}<br>"
            f"Type: {n['kind']}  •  Criticality {n['criticality']}/10<br>"
            f"Throughput: {n['throughput_tpd']:,} short tons/day<br>"
            f"Fuel storage: {n['fuel_storage_kgal']:,} kgal<br>"
            f"Runway: {n['runway_ft']:,} ft<br>"
            f"<b>Risk index: {risk:.1f}/10</b>  ({conf})<br>"
            f"Top threat: {threat}"
        )

    node_trace = go.Scatter(
        x=xs, y=ys, mode="markers+text",
        marker=dict(size=sizes, color=colors, line=dict(color="#0A0A0A", width=2)),
        text=labels, textposition="top center",
        textfont=dict(color="#E8E8E8", size=11, family="Helvetica"),
        hovertext=texts, hoverinfo="text",
        showlegend=False,
    )

    fig = go.Figure(data=[*edge_traces, node_trace])
    fig.update_layout(
        paper_bgcolor="#0A0A0A",
        plot_bgcolor="#0A0A0A",
        font=dict(color="#E8E8E8", family="Helvetica"),
        margin=dict(l=10, r=10, t=10, b=10),
        height=520,
        xaxis=dict(visible=False, scaleanchor=None),
        yaxis=dict(visible=False),
        hoverlabel=dict(bgcolor="#0E0E0E", bordercolor="#00BB7A",
                        font=dict(color="#E8E8E8", family="Helvetica")),
    )
    return fig
