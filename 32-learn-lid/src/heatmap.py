# LEARN — Learning Intelligence Dashboard for USMC PME / MOS school
# Part of the MDM 2026 Hackathon Templates (https://github.com/12fn/MDMhackathon-repos)
# MIT licensed. Built on GAI (Government Acquisitions, Inc.) + Kamiwaza (https://www.kamiwaza.ai/).
"""Plotly cohort competency heatmap (students x competencies).

Single hero visual for the demo arc. Color scale tuned to Kamiwaza neon green.
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


def build_heatmap(per_student: dict[str, dict], students: list[dict]) -> go.Figure:
    """students x competencies (4) heatmap.

    Y axis = student names (rank Last). X axis = the 4 competencies.
    Value = 0-5 rubric score.
    """
    sid_order = [s["student_id"] for s in students]
    name_order = [s["name"] for s in students]

    z = []
    text = []
    customdata = []
    for sid in sid_order:
        ev = per_student.get(sid, {})
        comp = ev.get("competency_evidence", {k: 0.0 for k in COMPETENCIES})
        row = [float(comp.get(k, 0.0)) for k in COMPETENCIES]
        z.append(row)
        text.append([f"{v:.1f}" for v in row])
        intv = "INTV" if ev.get("instructor_intervention_needed") else ""
        depth = ev.get("cognitive_depth_observed", "—")
        customdata.append([f"{intv}|{depth}"] * len(COMPETENCIES))

    fig = go.Figure(
        data=go.Heatmap(
            z=z,
            x=[LABELS[k] for k in COMPETENCIES],
            y=name_order,
            text=text,
            texttemplate="%{text}",
            textfont={"size": 11, "color": "#0A0A0A"},
            colorscale=[
                [0.00, "#3A0E0E"],   # critical / weak — deep red
                [0.30, "#7A2E1E"],
                [0.50, "#3A2C0E"],   # moderate — amber
                [0.65, "#0E2F22"],
                [0.85, "#00BB7A"],   # strong — kamiwaza green
                [1.00, "#00FFA7"],   # neon highlight
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

    # Annotate intervention rows on the right edge
    sid_to_ev = {sid: per_student.get(sid, {}) for sid in sid_order}
    annotations = []
    for i, sid in enumerate(sid_order):
        ev = sid_to_ev[sid]
        if ev.get("instructor_intervention_needed"):
            annotations.append(dict(
                x=len(COMPETENCIES) - 0.40,
                y=i,
                xref="x", yref="y",
                text="● INTV",
                showarrow=False,
                font=dict(color="#FF6F66", size=10, family="Helvetica"),
                xanchor="left",
            ))

    fig.update_layout(
        height=max(420, 28 * len(sid_order) + 70),
        margin=dict(l=10, r=10, t=10, b=10),
        paper_bgcolor="#0A0A0A",
        plot_bgcolor="#0A0A0A",
        font=dict(color="#E8E8E8", family="Helvetica, Arial, sans-serif"),
        xaxis=dict(
            tickfont=dict(color="#E8E8E8", size=11),
            side="top",
            showgrid=False,
        ),
        yaxis=dict(
            tickfont=dict(color="#E8E8E8", size=11),
            autorange="reversed",
            showgrid=False,
        ),
        annotations=annotations,
    )
    return fig


def build_assignment_bars(assignment_effectiveness: list[dict]) -> go.Figure:
    """Horizontal bar chart of assignment mean grade. Used in PARA 4 panel."""
    if not assignment_effectiveness:
        return go.Figure()
    items = sorted(assignment_effectiveness, key=lambda r: r["mean_grade"])
    names = [a["name"][:42] + ("…" if len(a["name"]) > 42 else "") for a in items]
    grades = [a["mean_grade"] for a in items]
    colors = []
    for g in grades:
        if g >= 88:
            colors.append("#00FFA7")
        elif g >= 75:
            colors.append("#00BB7A")
        elif g >= 65:
            colors.append("#E0B341")
        else:
            colors.append("#D8362F")

    fig = go.Figure(go.Bar(
        x=grades, y=names, orientation="h",
        marker=dict(color=colors, line=dict(color="#0A0A0A", width=1)),
        text=[f"{g:.1f}" for g in grades],
        textposition="outside",
        textfont=dict(color="#E8E8E8", size=11),
        hovertemplate="<b>%{y}</b><br>mean=%{x:.1f}<extra></extra>",
    ))
    fig.update_layout(
        height=240,
        margin=dict(l=10, r=10, t=10, b=20),
        paper_bgcolor="#0A0A0A",
        plot_bgcolor="#0A0A0A",
        font=dict(color="#E8E8E8"),
        xaxis=dict(range=[0, 110], showgrid=True, gridcolor="#222222",
                   tickfont=dict(color="#E8E8E8")),
        yaxis=dict(showgrid=False, tickfont=dict(color="#E8E8E8", size=10)),
        showlegend=False,
    )
    return fig
