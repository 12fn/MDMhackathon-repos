"""REORDER — time-series forecasting for Class IX NSN demand.

Primary engine: Holt-Winters exponential smoothing (statsmodels) with weekly
seasonality. Falls back to seasonal-naive (last-7-day mean) when the series is
too short or smoothing fails to converge — so the forecast pipeline never raises.

Output for each NSN: a dict with `actual` (90-d history), `forecast` (90 days
projected), `lo`/`hi` 80% confidence band, and aggregate 30/60/90-day demand
totals.
"""
from __future__ import annotations

import warnings
from typing import Any

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")  # silence statsmodels convergence chatter


def _daily_consumption_by_nsn(df: pd.DataFrame) -> pd.DataFrame:
    """Group work orders into a daily NSN x date qty matrix."""
    g = df.groupby(["nsn", "date"], as_index=False)["qty_consumed"].sum()
    g["date"] = pd.to_datetime(g["date"])
    return g


def _continuous_index(series: pd.Series, end_date: pd.Timestamp,
                      lookback_days: int = 90) -> pd.Series:
    """Force series onto a complete daily index, fill missing days with 0."""
    full = pd.date_range(end=end_date, periods=lookback_days, freq="D")
    return series.reindex(full, fill_value=0).astype(float)


def forecast_one(actual: pd.Series, *, horizon: int = 90) -> dict[str, Any]:
    """Forecast a single NSN's daily demand. Returns actual/forecast/lo/hi arrays."""
    actual_arr = np.asarray(actual.values, dtype=float)
    n = len(actual_arr)

    fcast: np.ndarray
    lo: np.ndarray
    hi: np.ndarray
    method = "holt-winters"

    if n >= 21 and actual_arr.sum() > 5:
        try:
            from statsmodels.tsa.holtwinters import ExponentialSmoothing
            model = ExponentialSmoothing(
                actual_arr,
                trend="add",
                seasonal="add",
                seasonal_periods=7,
                initialization_method="estimated",
            )
            fit = model.fit(optimized=True, use_brute=False)
            fcast = np.asarray(fit.forecast(horizon), dtype=float)
            # Approximate 80% CI from in-sample residual stdev.
            resid = actual_arr - np.asarray(fit.fittedvalues, dtype=float)
            sigma = float(np.std(resid)) if resid.size else 1.0
            band = 1.28 * sigma  # ~80% one-sided
            lo = np.maximum(0.0, fcast - band)
            hi = fcast + band
        except Exception:
            fcast, lo, hi, method = _seasonal_naive(actual_arr, horizon)
    else:
        fcast, lo, hi, method = _seasonal_naive(actual_arr, horizon)

    fcast = np.maximum(0.0, fcast)
    return {
        "actual":     actual_arr.tolist(),
        "forecast":   fcast.tolist(),
        "lo":         lo.tolist(),
        "hi":         hi.tolist(),
        "method":     method,
        "demand_30d": float(fcast[:30].sum()),
        "demand_60d": float(fcast[:60].sum()),
        "demand_90d": float(fcast[:90].sum()),
        "actual_30d": float(actual_arr[-30:].sum()) if n >= 30 else float(actual_arr.sum()),
    }


def _seasonal_naive(actual: np.ndarray, horizon: int) -> tuple[np.ndarray, np.ndarray, np.ndarray, str]:
    """Tile last-7-day mean across the horizon. Cheap, never fails, used as fallback."""
    if actual.size == 0:
        z = np.zeros(horizon, dtype=float)
        return z, z, z + 1.0, "zero"
    last7 = actual[-min(7, actual.size):]
    mean = float(last7.mean())
    sigma = float(last7.std()) if last7.size > 1 else max(1.0, mean * 0.4)
    fcast = np.full(horizon, mean, dtype=float)
    band = 1.28 * sigma
    lo = np.maximum(0.0, fcast - band)
    hi = fcast + band
    return fcast, lo, hi, "seasonal-naive"


def build_forecasts(df: pd.DataFrame, *, top_n: int = 12,
                    horizon: int = 90) -> dict[str, dict[str, Any]]:
    """Run forecast_one() for the top-N NSNs by trailing 30-day demand.

    Returns dict keyed by NSN -> forecast result. The order of keys reflects
    descending 30-day demand so callers can iterate "top N" naturally.
    """
    if df.empty:
        return {}

    daily = _daily_consumption_by_nsn(df)
    end_date = pd.Timestamp(daily["date"].max())

    # Trailing 30-day demand by NSN to choose the top-N.
    last30 = daily[daily["date"] >= end_date - pd.Timedelta(days=29)]
    top = (
        last30.groupby("nsn")["qty_consumed"].sum()
              .sort_values(ascending=False).head(top_n).index.tolist()
    )

    results: dict[str, dict[str, Any]] = {}
    for nsn in top:
        series = daily[daily["nsn"] == nsn].set_index("date")["qty_consumed"]
        full = _continuous_index(series, end_date)
        results[nsn] = forecast_one(full, horizon=horizon)
    return results


def shortfall_signal(projected_30d: float, on_hand: int) -> str:
    """Map projected 30-day demand vs on-hand at the forward node to GREEN/AMBER/RED."""
    if on_hand <= 0:
        return "RED"
    cover_ratio = on_hand / max(1.0, projected_30d)
    if cover_ratio >= 1.5:
        return "GREEN"
    if cover_ratio >= 0.75:
        return "AMBER"
    return "RED"
