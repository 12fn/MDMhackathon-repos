"""HUB charts — Folium routing map + Plotly per-mode throughput bars."""
from __future__ import annotations

from typing import Any

import folium
import plotly.graph_objects as go

# Mode → routing color (kept neon-friendly on the dark Kamiwaza theme)
MODE_COLOR = {
    "road":     "#FFB347",  # amber
    "rail":     "#00FFA7",  # neon green (Kamiwaza highlight)
    "waterway": "#5DADE2",  # sky blue
    "air":      "#E36F66",  # rose
    "_node":    "#00BB7A",
}

KIND_COLOR = {
    "mclb":       "#00BB7A",
    "poe":        "#FFB347",
    "rail_term":  "#00FFA7",
    "intermodal": "#00FFA7",
    "river_port": "#5DADE2",
    "airport":    "#E36F66",
}


def build_routing_map(plan: dict, *, focus_mode: str | None = None) -> folium.Map:
    """Render a CONUS Folium map with all nodes and the selected corridor(s).

    If `focus_mode` is provided and feasible, only that corridor is drawn
    (highlighted). Otherwise every available mode is drawn for comparison.
    """
    o = plan["origin"]
    d = plan["destination"]
    nodes = plan.get("_all_nodes")  # may be passed in by app.py for full plotting
    per_mode = plan["per_mode"]

    # Center on midpoint of origin / destination, zoom to fit CONUS-ish.
    center_lat = (o["lat"] + d["lat"]) / 2
    center_lon = (o["lon"] + d["lon"]) / 2
    fmap = folium.Map(
        location=[center_lat, center_lon],
        zoom_start=4,
        tiles="CartoDB dark_matter",
        control_scale=True,
    )

    # Add a faint base of all nodes if provided
    if nodes:
        for n in nodes:
            color = KIND_COLOR.get(n["kind"], "#888888")
            folium.CircleMarker(
                location=[n["lat"], n["lon"]],
                radius=3,
                color=color,
                fill=True,
                fill_opacity=0.55,
                weight=1,
                popup=folium.Popup(
                    f"<b>{n['name']}</b><br>{n['id']} · {n['kind']} · {n['state']}<br>"
                    f"Throughput: {n['throughput_tpd']:,} tpd",
                    max_width=240,
                ),
            ).add_to(fmap)

    # Build a node lookup so we can plot edges
    node_lut: dict[str, dict] = {}
    if nodes:
        for n in nodes:
            node_lut[n["id"]] = n
    # Add origin/dest in case nodes wasn't passed
    node_lut.setdefault(o["id"], o)
    node_lut.setdefault(d["id"], d)

    # Draw each mode's path (or just the focused one)
    modes_to_draw = [focus_mode] if focus_mode else list(per_mode.keys())
    for mode in modes_to_draw:
        mp = per_mode.get(mode)
        if not mp or not mp.get("available"):
            continue
        path_ids = mp["node_path"]
        coords = []
        for nid in path_ids:
            n = node_lut.get(nid)
            if n:
                coords.append([n["lat"], n["lon"]])
        if len(coords) < 2:
            continue
        color = MODE_COLOR.get(mode, "#FFFFFF")
        weight = 6 if mode == focus_mode else 4
        opacity = 0.95 if mode == focus_mode else 0.55
        folium.PolyLine(
            coords,
            color=color,
            weight=weight,
            opacity=opacity,
            tooltip=f"{mode.upper()} · {mp['summary']['miles']} mi · "
                    f"{mp['transit_days']} d · feasible={mp['summary']['feasible']}",
        ).add_to(fmap)
        # Drop bottleneck markers on legs that have a named choke point
        for edge in mp.get("edge_path", []):
            if not edge.get("bottleneck_named"):
                continue
            a_n = node_lut.get(edge["a"]); b_n = node_lut.get(edge["b"])
            if not a_n or not b_n:
                continue
            mid = [(a_n["lat"] + b_n["lat"]) / 2, (a_n["lon"] + b_n["lon"]) / 2]
            folium.Marker(
                mid,
                icon=folium.DivIcon(html=(
                    f"<div style='background:#3A1A0E;color:#FFB347;"
                    f"border:1px solid #FFB347;border-radius:4px;"
                    f"padding:2px 6px;font-size:10px;font-family:Menlo,monospace;"
                    f"white-space:nowrap;'>"
                    f"⚠ {edge['bottleneck_named']}"
                    f"</div>"
                )),
            ).add_to(fmap)

    # Origin & destination — large, labeled
    for tag, n, color in (("ORIGIN", o, "#00FFA7"), ("POE", d, "#FFB347")):
        folium.CircleMarker(
            [n["lat"], n["lon"]],
            radius=10,
            color=color,
            fill=True,
            fill_opacity=0.95,
            weight=2,
            popup=folium.Popup(
                f"<b>{tag}</b><br>{n['name']}<br>{n['id']} · {n['kind']}",
                max_width=240,
            ),
        ).add_to(fmap)
        folium.Marker(
            [n["lat"], n["lon"]],
            icon=folium.DivIcon(html=(
                f"<div style='color:{color};font-weight:700;font-family:Menlo,monospace;"
                f"font-size:11px;text-shadow:0 0 4px #000;'>"
                f"{tag}: {n['name']}</div>"
            )),
        ).add_to(fmap)

    return fmap


def build_throughput_bars(plan: dict) -> go.Figure:
    """Per-mode capacity / transit-days / cost mini bar chart."""
    modes = ["road", "rail", "waterway", "air"]
    pm = plan["per_mode"]
    capacities, transit, cost, feasible_text = [], [], [], []
    for m in modes:
        mp = pm.get(m, {})
        if not mp.get("available"):
            capacities.append(0); transit.append(0); cost.append(0)
            feasible_text.append("no path")
            continue
        capacities.append(mp["summary"]["min_capacity_tpd"])
        transit.append(mp["transit_days"])
        cost.append(mp["cost_index"])
        feasible_text.append("feasible" if mp["summary"]["feasible"] else "blocked")

    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=modes,
        y=capacities,
        name="Min capacity (tons/day)",
        marker_color=[MODE_COLOR.get(m, "#888") for m in modes],
        text=[f"{c:,}" if c else "—" for c in capacities],
        textposition="outside",
        textfont=dict(color="#E8E8E8", size=11),
        hovertemplate="<b>%{x}</b><br>min capacity: %{y:,} tpd<extra></extra>",
    ))
    fig.update_layout(
        title=dict(text="Per-mode minimum corridor capacity (short-tons/day)",
                   font=dict(color="#FFFFFF", size=13)),
        plot_bgcolor="#0A0A0A",
        paper_bgcolor="#0A0A0A",
        font=dict(color="#E8E8E8"),
        height=240,
        margin=dict(l=10, r=10, t=40, b=20),
        xaxis=dict(showgrid=False, color="#E8E8E8"),
        yaxis=dict(gridcolor="#222222", color="#9A9A9A"),
        showlegend=False,
    )
    return fig


def build_transit_cost_chart(plan: dict) -> go.Figure:
    """Side-by-side transit-days vs cost-index bar."""
    modes = ["road", "rail", "waterway", "air"]
    pm = plan["per_mode"]
    transit, cost = [], []
    for m in modes:
        mp = pm.get(m, {})
        if not mp.get("available"):
            transit.append(0); cost.append(0)
            continue
        transit.append(mp["transit_days"])
        cost.append(mp["cost_index"])
    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=modes, y=transit, name="Transit days",
        marker_color="#00BB7A",
        text=[f"{t}d" if t else "—" for t in transit],
        textposition="outside",
        textfont=dict(color="#E8E8E8", size=11),
        yaxis="y",
    ))
    fig.add_trace(go.Bar(
        x=modes, y=cost, name="Cost index",
        marker_color="#FFB347",
        text=[f"{c}" if c else "—" for c in cost],
        textposition="outside",
        textfont=dict(color="#E8E8E8", size=11),
        yaxis="y2",
    ))
    fig.update_layout(
        title=dict(text="Transit days  vs  Cost index (per mode)",
                   font=dict(color="#FFFFFF", size=13)),
        plot_bgcolor="#0A0A0A",
        paper_bgcolor="#0A0A0A",
        font=dict(color="#E8E8E8"),
        height=240,
        margin=dict(l=10, r=10, t=40, b=20),
        xaxis=dict(showgrid=False, color="#E8E8E8"),
        yaxis=dict(title="Days",  gridcolor="#222222", color="#9A9A9A"),
        yaxis2=dict(title="Cost", overlaying="y", side="right",
                    gridcolor="#222222", color="#9A9A9A"),
        legend=dict(orientation="h", yanchor="bottom", y=1.02,
                    xanchor="right", x=1, font=dict(color="#E8E8E8")),
        barmode="group",
    )
    return fig
