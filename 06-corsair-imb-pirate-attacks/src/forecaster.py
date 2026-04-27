# CORSAIR — pirate-attack KDE forecast + maritime intel summary
# Part of the MDM 2026 Hackathon Templates (https://github.com/12fn/MDMhackathon-repos)
# MIT licensed. Built on GAI (Government Acquisitions, Inc.) + Kamiwaza (https://www.kamiwaza.ai/).
"""Spatiotemporal piracy risk forecaster.

Train a 2-D KDE on (lat, lon) of historical attacks within a chosen basin and a
recency-weighted time window. Render a 30-day forward risk grid by:
  1. Estimating density on a basin-bounded mesh.
  2. Scaling by an empirical seasonality factor (month-of-year baseline).
  3. Projecting expected attacks in the next 30 days using the recent attack rate.

This is intentionally lightweight (sklearn KernelDensity) so it can run on a
laptop CPU and ship inside the on-prem Kamiwaza Inference Mesh footprint.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.neighbors import KernelDensity

DATA_PATH = Path(__file__).resolve().parent.parent / "data" / "pirate_attacks.csv"

BASIN_BBOX = {
    # name: (lat_min, lat_max, lon_min, lon_max)
    "Gulf of Aden":          (8.0,  18.0, 42.0, 56.0),
    "Strait of Malacca":     (-1.0,  8.0, 96.0, 106.0),
    "Gulf of Guinea":        (-3.0, 10.0, -3.0, 12.0),
    "Sulu Sea":              (3.0,   9.0, 117.0, 124.0),
    "Caribbean / Venezuelan":(8.0,  15.0, -71.0, -60.0),
    "South China Sea":       (4.0,  16.0, 107.0, 119.0),
    "All Basins":            (-10.0, 25.0, -75.0, 130.0),
}


@dataclass
class Forecast:
    basin: str
    grid_lat: np.ndarray
    grid_lon: np.ndarray
    risk: np.ndarray            # normalized 0..1
    expected_attacks_30d: float
    hotspots: list[dict]        # top-K [{lat, lon, risk, expected}]
    asof: datetime
    n_train: int
    bandwidth: float


def load_attacks(path: Path = DATA_PATH) -> pd.DataFrame:
    df = pd.read_csv(path)
    df["datetime"] = pd.to_datetime(df["datetime"])
    return df


def _basin_filter(df: pd.DataFrame, basin: str) -> pd.DataFrame:
    if basin == "All Basins":
        return df
    return df[df["basin"] == basin]


def _bbox(basin: str) -> tuple[float, float, float, float]:
    return BASIN_BBOX.get(basin, BASIN_BBOX["All Basins"])


def fit_kde(latlon: np.ndarray, *, bandwidth: float | None = None) -> KernelDensity:
    if bandwidth is None:
        # Silverman-ish heuristic on the 1-D scale
        std = np.std(latlon, axis=0).mean()
        bandwidth = max(0.15, 1.06 * std * (len(latlon) ** -0.2))
    kde = KernelDensity(kernel="gaussian", bandwidth=bandwidth)
    kde.fit(latlon)
    return kde


def make_grid(basin: str, n: int = 60) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    lat_min, lat_max, lon_min, lon_max = _bbox(basin)
    lats = np.linspace(lat_min, lat_max, n)
    lons = np.linspace(lon_min, lon_max, n)
    LON, LAT = np.meshgrid(lons, lats)
    grid = np.column_stack([LAT.ravel(), LON.ravel()])
    return lats, lons, grid


def seasonality(df: pd.DataFrame, target_month: int) -> float:
    """Normalized monthly attack rate vs annual mean. >1 means above-average month."""
    counts = df.groupby("month").size().reindex(range(1, 13), fill_value=0)
    base = counts.mean()
    if base == 0:
        return 1.0
    return float(counts.loc[target_month] / base)


def recent_rate_per_30d(df: pd.DataFrame, asof: datetime, lookback_years: int = 5) -> float:
    cutoff = asof - timedelta(days=365 * lookback_years)
    recent = df[df["datetime"] >= cutoff]
    if recent.empty:
        return float(len(df)) / max(1, (asof - df["datetime"].min()).days) * 30.0
    span_days = max(1, (asof - recent["datetime"].min()).days)
    return float(len(recent)) / span_days * 30.0


def forecast(basin: str, asof: datetime | None = None, *,
             grid_n: int = 60, top_k: int = 5, df: pd.DataFrame | None = None) -> Forecast:
    if df is None:
        df = load_attacks()
    if asof is None:
        asof = pd.Timestamp.now().to_pydatetime()
    sub = _basin_filter(df, basin)
    if len(sub) < 30:
        sub = df  # graceful fallback
    latlon = sub[["lat", "lon"]].to_numpy()
    kde = fit_kde(latlon)
    lats, lons, grid = make_grid(basin, n=grid_n)
    log_density = kde.score_samples(grid)
    density = np.exp(log_density).reshape(len(lats), len(lons))
    if density.max() > 0:
        risk = density / density.max()
    else:
        risk = density
    season = seasonality(sub, target_month=((asof.month % 12) + 1))
    base_rate = recent_rate_per_30d(sub, asof)
    expected_30d = float(base_rate * season)
    # Top-K hotspots (pick local maxima by simple top-N grid cells with NMS)
    flat = [(risk[i, j], lats[i], lons[j]) for i in range(len(lats)) for j in range(len(lons))]
    flat.sort(reverse=True, key=lambda x: x[0])
    hotspots: list[dict] = []
    min_sep_deg = max(1.0, (lats.max() - lats.min()) / 12)
    for r, la, lo in flat:
        if all((la - h["lat"]) ** 2 + (lo - h["lon"]) ** 2 > min_sep_deg ** 2 for h in hotspots):
            hotspots.append({
                "lat": float(la), "lon": float(lo), "risk": float(r),
                "expected": float(r * expected_30d / max(1e-6, sum(h_[0] for h_ in flat[:top_k * 4]))) * top_k,
            })
        if len(hotspots) >= top_k:
            break
    return Forecast(
        basin=basin,
        grid_lat=lats,
        grid_lon=lons,
        risk=risk,
        expected_attacks_30d=expected_30d,
        hotspots=hotspots,
        asof=asof,
        n_train=int(len(sub)),
        bandwidth=float(kde.bandwidth),
    )


def nearest_historical(df: pd.DataFrame, lat: float, lon: float, k: int = 3) -> pd.DataFrame:
    d2 = (df["lat"] - lat) ** 2 + (df["lon"] - lon) ** 2
    idx = d2.nsmallest(k).index
    return df.loc[idx].sort_values("datetime", ascending=False)


def trend_delta(df: pd.DataFrame, basin: str) -> dict:
    """5y vs prior 5y attack delta + dominant attack-type drift, for the indicator board."""
    sub = _basin_filter(df, basin)
    asof = sub["datetime"].max()
    cutoff_recent = asof - pd.Timedelta(days=365 * 5)
    cutoff_prior = cutoff_recent - pd.Timedelta(days=365 * 5)
    recent = sub[sub["datetime"] >= cutoff_recent]
    prior = sub[(sub["datetime"] >= cutoff_prior) & (sub["datetime"] < cutoff_recent)]
    n_recent, n_prior = len(recent), max(1, len(prior))
    delta_pct = (n_recent - n_prior) / n_prior * 100.0
    # MOA shift: top attack type in each window
    top_recent = recent["attack_type"].mode().iloc[0] if not recent.empty else "n/a"
    top_prior = prior["attack_type"].mode().iloc[0] if not prior.empty else "n/a"
    return {
        "n_recent_5y": n_recent,
        "n_prior_5y": n_prior,
        "delta_pct": round(delta_pct, 1),
        "moa_recent": top_recent,
        "moa_prior": top_prior,
        "shift": top_recent != top_prior,
    }


if __name__ == "__main__":
    df = load_attacks()
    fc = forecast("Gulf of Aden", df=df)
    print("Basin:", fc.basin, "n_train:", fc.n_train, "bandwidth:", round(fc.bandwidth, 3))
    print("Expected attacks next 30d:", round(fc.expected_attacks_30d, 1))
    for i, h in enumerate(fc.hotspots, 1):
        print(f"  Hotspot #{i}: ({h['lat']:.2f},{h['lon']:.2f})  risk={h['risk']:.2f}")
    print("Trend:", trend_delta(df, "Gulf of Aden"))
