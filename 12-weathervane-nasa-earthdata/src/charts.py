"""Plotly charts for WEATHERVANE — Kamiwaza-themed."""
from __future__ import annotations

from datetime import datetime
from typing import Any

import pandas as pd
import plotly.graph_objects as go

# Brand
BG = "#0A0A0A"
SURFACE = "#0E0E0E"
PRIMARY = "#00BB7A"
NEON = "#00FFA7"
BORDER = "#222222"
MUTED = "#7E7E7E"
TEXT = "#FFFFFF"

CHARTS = [
    {"col": "hs_m", "title": "Significant Wave Height (Hs)", "unit": "m",
     "source": "WAVEWATCH III ensemble", "color": "#00FFA7"},
    {"col": "wind_kn", "title": "10-m Wind Speed", "unit": "kn",
     "source": "NASA MERRA-2 reanalysis", "color": "#00BB7A"},
    {"col": "precip_mmhr", "title": "Precipitation Rate", "unit": "mm/hr",
     "source": "NASA GPM IMERG", "color": "#56C2FF"},
    {"col": "sst_c", "title": "Sea-Surface Temperature", "unit": "deg C",
     "source": "NASA GHRSST", "color": "#FFB347"},
    {"col": "cloud_pct", "title": "Cloud Cover", "unit": "%",
     "source": "NASA MODIS Terra/Aqua", "color": "#B19CD9"},
]


def _ts(s: str | None) -> Any:
    if not s:
        return None
    return pd.to_datetime(s, utc=True)


def make_chart(df: pd.DataFrame, spec: dict, recommended_window: dict | None = None) -> go.Figure:
    df = df.copy()
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    fig = go.Figure()

    fig.add_trace(go.Scatter(
        x=df["timestamp"], y=df[spec["col"]],
        mode="lines", line=dict(color=spec["color"], width=2),
        name=spec["title"],
        hovertemplate=f"%{{x|%d %b %H:%MZ}}<br>%{{y:.2f}} {spec['unit']}<extra></extra>",
    ))

    # Highlight recommended window in green
    if recommended_window:
        rs, re = _ts(recommended_window.get("start")), _ts(recommended_window.get("end"))
        if rs is not None and re is not None:
            fig.add_vrect(
                x0=rs, x1=re,
                fillcolor="rgba(0, 255, 167, 0.18)",
                line=dict(color=NEON, width=1),
                annotation=dict(text="RECOMMENDED H-HOUR WINDOW",
                                font=dict(color=NEON, size=10),
                                x=rs, xanchor="left", y=1.0, yanchor="top",
                                showarrow=False),
                layer="below",
            )

    fig.update_layout(
        title=dict(
            text=f"<b>{spec['title']}</b> <span style='color:{MUTED};font-size:11px'>"
                 f"  source: {spec['source']}</span>",
            x=0.0, xanchor="left", font=dict(color=TEXT, size=15),
        ),
        paper_bgcolor=SURFACE,
        plot_bgcolor=SURFACE,
        font=dict(color=TEXT, family="Helvetica, Arial, sans-serif", size=12),
        margin=dict(l=20, r=20, t=46, b=30),
        height=240,
        showlegend=False,
        xaxis=dict(gridcolor=BORDER, zerolinecolor=BORDER, linecolor=BORDER, color=MUTED),
        yaxis=dict(gridcolor=BORDER, zerolinecolor=BORDER, linecolor=BORDER, color=MUTED,
                   title=dict(text=spec["unit"], font=dict(color=MUTED, size=11))),
    )
    return fig
