"""Plotly cohort competency heatmap (students × 4 competencies).

Color scale tuned to Kamiwaza dark theme + neon green.
"""
from __future__ import annotations

import plotly.graph_objects as go

COMPETENCIES = ["critical_thinking", "communication",
                "doctrinal_knowledge", "problem_solving"]
LABELS = {
    "critical_thinking": "Critical<br>Thinking",
    "communication": "Communication",
    "doctrinal_knowledge": "Doctrinal<br>Knowledge",
    "problem_solving": "Problem<br>Solving",
}


def build_heatmap(comp_summary: dict[str, dict[str, float]],
                  students: list[dict]) -> go.Figure:
    sid_order = [s["student_id"] for s in students]
    name_order = [f"{s['rank']} {s['name'].split()[-1]}" for s in students]

    z = []
    text = []
    for sid in sid_order:
        comp = comp_summary.get(sid, {})
        row = [float(comp.get(k, 0.0)) for k in COMPETENCIES]
        z.append(row)
        text.append([f"{v:.1f}" for v in row])

    fig = go.Figure(
        data=go.Heatmap(
            z=z,
            x=[LABELS[k] for k in COMPETENCIES],
            y=name_order,
            text=text,
            texttemplate="%{text}",
            textfont={"size": 12, "color": "#0A0A0A"},
            colorscale=[
                [0.00, "#3A0E0E"],
                [0.30, "#7A2E1E"],
                [0.50, "#3A2C0E"],
                [0.65, "#0E2F22"],
                [0.85, "#00BB7A"],
                [1.00, "#00FFA7"],
            ],
            zmin=0,
            zmax=5,
            colorbar=dict(
                title=dict(text="0-5", font=dict(color="#E8E8E8", size=11)),
                tickfont=dict(color="#E8E8E8", size=10),
                outlinecolor="#222222",
                thickness=12,
            ),
            hovertemplate="<b>%{y}</b><br>%{x}: <b>%{z:.2f}</b>/5<extra></extra>",
        )
    )

    fig.update_layout(
        height=max(280, 44 * len(sid_order) + 70),
        margin=dict(l=10, r=10, t=10, b=10),
        paper_bgcolor="#0A0A0A",
        plot_bgcolor="#0A0A0A",
        font=dict(color="#E8E8E8", family="Helvetica, Arial, sans-serif"),
        xaxis=dict(tickfont=dict(color="#E8E8E8", size=11), side="top", showgrid=False),
        yaxis=dict(tickfont=dict(color="#E8E8E8", size=11), autorange="reversed", showgrid=False),
    )
    return fig


def build_persona_panel_chart(reactions: list[dict]) -> go.Figure:
    """Horizontal trust-delta bar chart for the PA persona panel."""
    if not reactions:
        return go.Figure()
    items = sorted(reactions, key=lambda r: r["trust_delta"])
    names = [r["persona_id"] for r in items]
    deltas = [r["trust_delta"] for r in items]
    colors = []
    for d in deltas:
        if d >= 4:
            colors.append("#00FFA7")
        elif d >= 0:
            colors.append("#00BB7A")
        elif d >= -4:
            colors.append("#E0B341")
        else:
            colors.append("#D8362F")
    fig = go.Figure(go.Bar(
        x=deltas, y=names, orientation="h",
        marker=dict(color=colors, line=dict(color="#0A0A0A", width=1)),
        text=[f"{d:+d}" for d in deltas],
        textposition="outside",
        textfont=dict(color="#E8E8E8", size=12),
        hovertemplate="<b>%{y}</b><br>trust delta=%{x:+d}<extra></extra>",
    ))
    fig.update_layout(
        height=max(180, 36 * len(items) + 60),
        margin=dict(l=10, r=20, t=10, b=20),
        paper_bgcolor="#0A0A0A",
        plot_bgcolor="#0A0A0A",
        font=dict(color="#E8E8E8"),
        xaxis=dict(range=[-11, 11], showgrid=True, gridcolor="#222222",
                   zeroline=True, zerolinecolor="#444444",
                   tickfont=dict(color="#E8E8E8")),
        yaxis=dict(showgrid=False, tickfont=dict(color="#E8E8E8", size=11)),
        showlegend=False,
    )
    return fig
