"""STORM-SHIFT — Plotly chart helpers (Sankey cascade, stacked bar, 72h timeline)."""
from __future__ import annotations

import plotly.graph_objects as go

NEON = "#00FFA7"
PRIMARY = "#00BB7A"
AMBER = "#E0B341"
RED = "#FF6F66"
DEEP = "#065238"
BG = "#0A0A0A"
PANEL = "#0E0E0E"


# ─────────────────────────────────────────────────────────────────────────────
# 1. Sankey — cascade chain (storm → flood → supply gap → inventory red)
# ─────────────────────────────────────────────────────────────────────────────

def cascade_sankey(rollup: dict) -> go.Figure:
    inst = rollup["installation_id"]
    scn = rollup["scenario_id"]
    fl = rollup["flood"]
    su = rollup["supply"]
    inv = rollup["inventory"]
    fi = rollup["fire"]
    bi = rollup["base_impact"]

    storm_label = f"Storm: {scn}"
    inst_label = f"Base: {inst}"
    flood_label = f"Flood ${fl['total_usd']/1e6:,.0f}M"
    supply_label = f"Supply gap ({su['suppliers_affected']} suppliers)"
    inv_label = f"Inv RED ({inv['items_red']})"
    cons_label = f"Consumption x{rollup['consumption']['shelter_days']}d"
    fire_label = f"Fire 2nd risk {fi['ignition_risk_score']}"
    impact_label = f"$ {bi['total_dollar_exposure_usd']/1e9:.2f}B / {bi['days_to_mission_capable']}d-MC"

    labels = [
        storm_label, inst_label, flood_label, supply_label,
        inv_label, cons_label, fire_label, impact_label,
    ]
    # source -> target indices, with relative flow weights
    src = [0, 0, 1, 2, 3, 1, 6, 4, 5, 2, 3, 4, 5, 6]
    tgt = [1, 2, 2, 3, 4, 5, 7, 7, 7, 7, 7, 7, 7, 7]
    val = [
        50,  # storm hits installation
        30,  # storm direct → flood
        25,  # installation amplifies flood
        max(5, su['suppliers_affected'] / 2),
        max(3, inv['items_red'] * 6),
        max(5, rollup['consumption']['shelter_days'] * 3),
        max(2, fi['ignition_risk_score'] * 30),
        max(3, inv['items_red'] * 5),
        max(3, rollup['consumption']['shelter_days'] * 2),
        max(2, fl['total_usd'] / 1e8),
        max(2, su['suppliers_affected'] / 3),
        max(2, inv['items_red'] * 3),
        max(2, rollup['consumption']['shelter_days']),
        max(2, fi['estimated_damage_usd'] / 1e8),
    ]

    node_colors = [PRIMARY, NEON, "#3A4FC4", "#C46B3A", RED, AMBER, "#C43A8B", "#FFFFFF"]
    link_colors = ["rgba(0,255,167,0.25)"] * len(src)

    fig = go.Figure(data=[go.Sankey(
        node=dict(
            pad=18, thickness=20,
            line=dict(color="#222", width=0.5),
            label=labels,
            color=node_colors,
        ),
        link=dict(source=src, target=tgt, value=val, color=link_colors),
    )])
    fig.update_layout(
        paper_bgcolor=BG, plot_bgcolor=BG,
        font=dict(color="#E8E8E8", family="Helvetica, Arial, sans-serif", size=12),
        height=380, margin=dict(l=10, r=10, t=20, b=10),
    )
    return fig


# ─────────────────────────────────────────────────────────────────────────────
# 2. Stacked bar — impact by category
# ─────────────────────────────────────────────────────────────────────────────

def impact_stacked_bar(rollup: dict) -> go.Figure:
    bi = rollup["base_impact"]
    comps = bi["components_usd"]

    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=["Total exposure"],
        y=[comps["flood_damage"]],
        name="Flood damage",
        marker_color="#3A4FC4",
        text=f"${comps['flood_damage']/1e6:,.0f}M",
        textposition="inside",
    ))
    fig.add_trace(go.Bar(
        x=["Total exposure"],
        y=[comps["supply_chain"]],
        name="Supply chain",
        marker_color="#C46B3A",
        text=f"${comps['supply_chain']/1e6:,.0f}M",
        textposition="inside",
    ))
    fig.add_trace(go.Bar(
        x=["Total exposure"],
        y=[comps["inventory_red_premium"]],
        name="Inventory red premium",
        marker_color=RED,
        text=f"${comps['inventory_red_premium']/1e6:,.0f}M",
        textposition="inside",
    ))
    fig.add_trace(go.Bar(
        x=["Total exposure"],
        y=[comps["fire_secondary"]],
        name="Fire-secondary",
        marker_color="#C43A8B",
        text=f"${comps['fire_secondary']/1e6:,.0f}M",
        textposition="inside",
    ))
    fig.update_layout(
        barmode="stack",
        paper_bgcolor=BG, plot_bgcolor=PANEL,
        font=dict(color="#E8E8E8", family="Helvetica, Arial, sans-serif"),
        height=320, margin=dict(l=10, r=10, t=20, b=10),
        legend=dict(bgcolor="rgba(0,0,0,0)", bordercolor="#222", font=dict(color="#E8E8E8")),
        yaxis=dict(title="USD", gridcolor="#222"),
        xaxis=dict(showgrid=False),
    )
    return fig


# ─────────────────────────────────────────────────────────────────────────────
# 3. 72h cascade timeline
# ─────────────────────────────────────────────────────────────────────────────

def cascade_timeline(rollup: dict) -> go.Figure:
    """Plot each projection as a horizontal bar across the cascade window."""
    scn_kind = rollup["scenario_id"]
    fi = rollup["fire"]
    inv = rollup["inventory"]
    cons = rollup["consumption"]

    # Bars: (start_h, end_h, label, color)
    bars = [
        (-12, 0,  "Pre-landfall window",                 PRIMARY),
        (0,   8,  "Landfall + immediate flood",          "#3A4FC4"),
        (4,   24, "Storm surge / wind damage",           "#C46B3A"),
        (12,  inv["shelter_days"]*24, "Shelter posture", AMBER),
        (24,  48, "Supply chain disruption peak",        RED),
        (36,  60, "Inventory red items begin",           "#C43A8B"),
    ]
    if fi.get("ignition_risk_score", 0) > 0.4:
        lag = fi.get("time_lag_days", 0) * 24
        bars.append((lag, lag + 36, f"Fire-secondary risk window (lag {fi.get('time_lag_days',0)}d)", "#FF8533"))

    fig = go.Figure()
    for i, (s, e, label, color) in enumerate(bars):
        fig.add_trace(go.Bar(
            x=[e - s],
            y=[label],
            base=s,
            orientation="h",
            marker_color=color,
            text=f"H+{s} → H+{e}",
            textposition="inside",
            showlegend=False,
            hovertemplate=f"{label}: H+{s} to H+{e}<extra></extra>",
        ))
    fig.update_layout(
        paper_bgcolor=BG, plot_bgcolor=PANEL,
        font=dict(color="#E8E8E8", family="Helvetica, Arial, sans-serif"),
        height=340, margin=dict(l=10, r=10, t=30, b=30),
        xaxis=dict(title="Hours from landfall (H)", gridcolor="#222", zerolinecolor=NEON),
        yaxis=dict(autorange="reversed", gridcolor="#161616"),
        title=dict(text="72h cascade timeline", font=dict(color=NEON, size=14)),
    )
    return fig


# ─────────────────────────────────────────────────────────────────────────────
# 4. Inventory hours-to-red bar
# ─────────────────────────────────────────────────────────────────────────────

def inventory_hours_bar(rollup: dict) -> go.Figure:
    rows = rollup["inventory"]["rows"]
    rows = sorted(rows, key=lambda r: r["hours_to_red"])
    colors = [RED if r["status"] == "RED" else (AMBER if r["status"] == "AMBER" else PRIMARY)
              for r in rows]

    fig = go.Figure(go.Bar(
        x=[r["hours_to_red"] for r in rows],
        y=[r["class"] for r in rows],
        orientation="h",
        marker_color=colors,
        text=[f"{r['hours_to_red']:.0f}h" for r in rows],
        textposition="outside",
    ))
    fig.update_layout(
        paper_bgcolor=BG, plot_bgcolor=PANEL,
        font=dict(color="#E8E8E8", family="Helvetica, Arial, sans-serif"),
        height=340, margin=dict(l=10, r=10, t=30, b=10),
        xaxis=dict(title="Hours to RED", gridcolor="#222"),
        yaxis=dict(gridcolor="#161616"),
        title=dict(text="Inventory cascade — hours to RED by class",
                   font=dict(color=NEON, size=14)),
    )
    return fig
