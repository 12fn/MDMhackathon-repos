"""Pirate-risk KDE overlay used by the route planner.

Lightweight 2-D Gaussian KDE on (lat, lon) of historical attacks.
Per-corridor risk = mean density along sample points of the great-circle
segment.

Falls back to a deterministic basin lookup table if sklearn is unavailable.
"""
from __future__ import annotations

import math
from functools import lru_cache
from pathlib import Path

import pandas as pd

DATA_DIR = Path(__file__).resolve().parents[1] / "data"


@lru_cache(maxsize=1)
def _attacks() -> pd.DataFrame:
    df = pd.read_csv(DATA_DIR / "pirate_attacks.csv")
    return df


@lru_cache(maxsize=1)
def _kde():
    try:
        from sklearn.neighbors import KernelDensity
        import numpy as np
        df = _attacks()
        # Recency-weighted: use last 10 years
        df["datetime"] = pd.to_datetime(df["datetime"])
        cutoff = df["datetime"].max() - pd.Timedelta(days=365 * 10)
        recent = df[df["datetime"] >= cutoff]
        latlon = recent[["lat", "lon"]].to_numpy()
        std = latlon.std(axis=0).mean()
        bw = max(0.5, 1.06 * std * (len(latlon) ** -0.2))
        kde = KernelDensity(kernel="gaussian", bandwidth=bw)
        kde.fit(latlon)
        return kde
    except Exception:
        return None


def _segment_points(lat1, lon1, lat2, lon2, n=12):
    return [(lat1 + (lat2 - lat1) * t / (n - 1),
             lon1 + (lon2 - lon1) * t / (n - 1)) for t in range(n)]


def basin_lookup_risk(basin: str) -> float:
    return {
        "Bab-el-Mandeb": 0.92,
        "Strait of Malacca": 0.78,
        "Sulu Sea": 0.71,
        "Gulf of Guinea": 0.68,
        "South China Sea": 0.42,
        "Luzon Strait": 0.31,
        "Bashi Channel": 0.24,
        "Open Pacific": 0.05,
        "Coral Sea": 0.10,
        "Indian Ocean": 0.20,
        "Red Sea": 0.55,
        "East China Sea": 0.18,
        "Philippine Sea": 0.12,
        "Panama Canal": 0.08,
        "Celebes-Sulu": 0.62,
    }.get(basin, 0.20)


def lane_risk(from_lat: float, from_lon: float, to_lat: float, to_lon: float,
              fallback_basin: str = "") -> float:
    """Return 0..1 piracy risk along the segment using the KDE if available."""
    kde = _kde()
    if kde is None:
        return basin_lookup_risk(fallback_basin)
    try:
        import numpy as np
        pts = _segment_points(from_lat, from_lon, to_lat, to_lon, n=12)
        log_d = kde.score_samples(np.array(pts))
        d = np.exp(log_d)
        # Normalize against a calibrated max density (Bab-el-Mandeb hotspot)
        log_d_max = kde.score_samples(np.array([[13.0, 49.0]]))
        d_max = float(np.exp(log_d_max)[0]) or 1e-6
        risk = float(d.mean() / d_max)
        return max(0.0, min(1.0, risk))
    except Exception:
        return basin_lookup_risk(fallback_basin)


def hotspots(top_k: int = 5) -> list[dict]:
    """Return top-K piracy hotspot centroids (degrees)."""
    df = _attacks()
    grouped = df.groupby("basin").agg(
        lat=("lat", "mean"),
        lon=("lon", "mean"),
        n=("attack_id", "count"),
    ).reset_index().sort_values("n", ascending=False).head(top_k)
    return [
        {"basin": r["basin"], "lat": float(r["lat"]), "lon": float(r["lon"]),
         "n_attacks": int(r["n"]),
         "risk": basin_lookup_risk(r["basin"])}
        for _, r in grouped.iterrows()
    ]
