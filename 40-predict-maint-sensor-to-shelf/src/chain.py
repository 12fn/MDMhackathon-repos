"""5-stage sensor-to-shelf closed-loop pipeline.

  (1) Sensor      — RandomForest classifier + RUL on the CWRU vibration trace
  (2) Forecast    — Holt-Winters spike projection on the matching NSN
  (3) Auto-reorder— GCSS-MC stock check + structured JSON action card
  (4) Induction   — greedy reslot into MCLB Albany / Barstow / Blount Island
  (5) Ledger      — append-only SHA-256 chained audit row

The chain is fully deterministic; the LLM brief in `agent.py` consumes the
chain output as a structured payload.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"

# ---------------------------------------------------------------------------
# Stage 2 — Holt-Winters forecasting
# ---------------------------------------------------------------------------
import warnings
warnings.filterwarnings("ignore")


def _daily_consumption_for_nsn(history_df: pd.DataFrame, nsn: str) -> pd.Series:
    df = history_df[history_df["nsn"] == nsn].copy()
    if df.empty:
        return pd.Series(dtype=float)
    df["date"] = pd.to_datetime(df["date"])
    daily = df.groupby("date")["qty_consumed"].sum()
    full = pd.date_range(end=daily.index.max(), periods=90, freq="D")
    return daily.reindex(full, fill_value=0).astype(float)


def forecast_demand(actual: pd.Series, *, horizon: int = 60,
                    severity_boost: float = 1.0) -> dict[str, Any]:
    """Holt-Winters projection with seasonal-naive fallback. severity_boost
    multiplies the forecast (the RUL drop "shock" injection)."""
    arr = np.asarray(actual.values, dtype=float)
    n = len(arr)
    method = "holt-winters"

    if n >= 21 and arr.sum() > 5:
        try:
            from statsmodels.tsa.holtwinters import ExponentialSmoothing
            model = ExponentialSmoothing(
                arr, trend="add", seasonal="add",
                seasonal_periods=7, initialization_method="estimated",
            )
            fit = model.fit(optimized=True, use_brute=False)
            fcast = np.asarray(fit.forecast(horizon), dtype=float)
            resid = arr - np.asarray(fit.fittedvalues, dtype=float)
            sigma = float(np.std(resid)) if resid.size else 1.0
            band = 1.28 * sigma
        except Exception:
            fcast, sigma, method = _seasonal_naive(arr, horizon)
            band = 1.28 * sigma
    else:
        fcast, sigma, method = _seasonal_naive(arr, horizon)
        band = 1.28 * sigma

    fcast = np.maximum(0.0, fcast * severity_boost)
    lo = np.maximum(0.0, fcast - band)
    hi = fcast + band

    return {
        "actual": arr.tolist(),
        "forecast": fcast.tolist(),
        "lo": lo.tolist(),
        "hi": hi.tolist(),
        "method": method,
        "demand_30d": float(fcast[:30].sum()),
        "demand_60d": float(fcast[:60].sum()),
        "actual_30d": float(arr[-30:].sum()) if n >= 30 else float(arr.sum()),
        "spike_ratio": (
            float(fcast[:30].sum()) / max(1.0, float(arr[-30:].sum()))
            if n >= 30 else 1.0
        ),
    }


def _seasonal_naive(actual: np.ndarray,
                    horizon: int) -> tuple[np.ndarray, float, str]:
    if actual.size == 0:
        return np.zeros(horizon), 1.0, "zero"
    last7 = actual[-min(7, actual.size):]
    mean = float(last7.mean())
    sigma = float(last7.std()) if last7.size > 1 else max(1.0, mean * 0.4)
    fcast = np.full(horizon, mean, dtype=float)
    return fcast, sigma, "seasonal-naive"


# ---------------------------------------------------------------------------
# Stage 3 — Auto-reorder (GCSS-MC stock check)
# ---------------------------------------------------------------------------
@dataclass
class ReorderCard:
    nsn: str
    on_hand: int
    projected_demand_30d: int
    shortfall: int
    recommended_reorder_qty: int
    source_depot: str
    lead_time_days: int
    action_due_by: str
    rebuild_not_buy: bool


def stock_at_depots(inventory_df: pd.DataFrame, nsn: str) -> dict:
    """Sum on-hand at MCLB Albany / Barstow / Blount Island."""
    if inventory_df.empty or "nsn" not in inventory_df.columns:
        return {"ALB": 0, "BAR": 0, "BIC": 0, "TOTAL": 0}
    rel = inventory_df[inventory_df["nsn"] == nsn]
    if rel.empty:
        return {"ALB": 0, "BAR": 0, "BIC": 0, "TOTAL": 0}
    qty_alb = int(rel[rel["location_id"].str.contains("ALB", na=False)]
                  ["qty_on_hand"].sum())
    qty_bar = int(rel[rel["location_id"].str.contains("BAR", na=False)]
                  ["qty_on_hand"].sum())
    qty_bic = int(rel[rel["location_id"].str.contains("BIC", na=False)]
                  ["qty_on_hand"].sum())
    return {
        "ALB": qty_alb,
        "BAR": qty_bar,
        "BIC": qty_bic,
        "TOTAL": qty_alb + qty_bar + qty_bic,
    }


def build_reorder_card(*, nsn: str, projected_30d: float,
                       inventory_df: pd.DataFrame, catalog: list[dict],
                       today: datetime | None = None) -> ReorderCard:
    today = today or datetime(2026, 4, 27, tzinfo=timezone.utc)
    stock = stock_at_depots(inventory_df, nsn)
    on_hand = stock["ALB"]
    part = next((c for c in catalog if c["nsn"] == nsn), None)
    rebuild = bool(part and part.get("rebuild_not_buy"))
    long_pole = bool(part and part.get("long_pole"))
    lead_time = 31 if long_pole and on_hand == 0 else (
        18 if on_hand == 0 else 11
    )
    shortfall = max(0, int(round(projected_30d - on_hand)))
    rec_qty = int(round(shortfall * 1.25))
    due = today + timedelta(days=max(2, 14 - lead_time // 4))
    return ReorderCard(
        nsn=nsn,
        on_hand=int(on_hand),
        projected_demand_30d=int(round(projected_30d)),
        shortfall=int(shortfall),
        recommended_reorder_qty=int(rec_qty),
        source_depot="MCLB Albany",
        lead_time_days=lead_time,
        action_due_by=due.strftime("%Y-%m-%d"),
        rebuild_not_buy=rebuild,
    )


# ---------------------------------------------------------------------------
# Stage 4 — Greedy depot induction reslot
# ---------------------------------------------------------------------------
@dataclass
class InductionTask:
    asset_id: str
    depot: str
    depot_name: str
    bay: int
    start: str
    end: str
    labor_hours: int
    rebuild_not_buy: bool


def reslot_induction(asset: dict, depots: list[dict],
                     reorder: ReorderCard,
                     base_gantt: list[dict] | None = None,
                     today: datetime | None = None) -> tuple[InductionTask, list[dict]]:
    """Greedy: place asset at its primary depot in the next available bay-day
    pair, after reorder delivery if any. Return (task, updated_gantt)."""
    today = today or datetime(2026, 4, 27, tzinfo=timezone.utc)
    gantt = list(base_gantt or _default_baseline_gantt(depots, today))
    target_depot = next(
        (d for d in depots if d["id"] == asset["depot"]), depots[0]
    )
    earliest = today
    if reorder.shortfall > 0:
        earliest = today + timedelta(days=reorder.lead_time_days)
    # Find next free bay (occupancy <= bays - 1 on that day)
    cal_days = 11 if asset["type"].startswith("MV-22B") else 9
    for offset in range(0, 30):
        day = earliest + timedelta(days=offset)
        # count tasks already in this depot active that day
        active = [
            t for t in gantt
            if t["depot"] == target_depot["id"]
            and t["start"] <= day.strftime("%Y-%m-%d") <= t["end"]
        ]
        if len(active) < target_depot["bays"]:
            bay = len(active) + 1
            start = day
            end = day + timedelta(days=cal_days)
            labor_hours = int(reorder.recommended_reorder_qty * 8 + 220)
            task = InductionTask(
                asset_id=asset["asset_id"],
                depot=target_depot["id"],
                depot_name=target_depot["name"],
                bay=bay,
                start=start.strftime("%Y-%m-%d"),
                end=end.strftime("%Y-%m-%d"),
                labor_hours=labor_hours,
                rebuild_not_buy=reorder.rebuild_not_buy,
            )
            gantt.append(asdict(task))
            return task, gantt
    # Fallback: tail-load it
    start = earliest + timedelta(days=29)
    end = start + timedelta(days=cal_days)
    task = InductionTask(
        asset_id=asset["asset_id"],
        depot=target_depot["id"],
        depot_name=target_depot["name"],
        bay=target_depot["bays"],
        start=start.strftime("%Y-%m-%d"),
        end=end.strftime("%Y-%m-%d"),
        labor_hours=400,
        rebuild_not_buy=reorder.rebuild_not_buy,
    )
    gantt.append(asdict(task))
    return task, gantt


def _default_baseline_gantt(depots: list[dict],
                            today: datetime) -> list[dict]:
    """Seed each depot with a few in-progress baseline jobs so the Gantt is
    populated before the chain fires."""
    out = []
    families = [
        ("MTVR-1004", "MTVR", 8),
        ("LAV-25-1208", "LAV-25", 12),
        ("MTVR-1101", "MTVR", 6),
        ("AAV-7A1-2210", "AAV-7A1", 14),
        ("LAV-25-1311", "LAV-25", 10),
        ("MV-22B-167410", "MV-22B", 16),
        ("MV-22B-167511", "MV-22B", 14),
    ]
    base = today
    for i, (asset_id, fam, dur) in enumerate(families):
        depot = depots[i % len(depots)]
        offset = (i % 4) * 2
        start = base + timedelta(days=offset)
        end = start + timedelta(days=dur)
        out.append({
            "asset_id": asset_id,
            "depot": depot["id"],
            "depot_name": depot["name"],
            "bay": (i % depot["bays"]) + 1,
            "start": start.strftime("%Y-%m-%d"),
            "end": end.strftime("%Y-%m-%d"),
            "labor_hours": 240 + i * 30,
            "rebuild_not_buy": True,
            "baseline": True,
        })
    return out


# ---------------------------------------------------------------------------
# Stage 5 — SHA-256 chained ledger
# ---------------------------------------------------------------------------
LEDGER_PATH = DATA / "ledger.jsonl"


def sha256_chain(prev_hash: str, payload: dict) -> str:
    body = (prev_hash + json.dumps(payload, sort_keys=True, default=str)).encode("utf-8")
    return hashlib.sha256(body).hexdigest()


def append_ledger(payload: dict) -> dict:
    """Append a hash-chained row to data/ledger.jsonl. Idempotent on file load.
    Returns the full ledger row including hash."""
    LEDGER_PATH.parent.mkdir(parents=True, exist_ok=True)
    if not LEDGER_PATH.exists():
        prev_hash = "0" * 64
    else:
        last_line = ""
        for ln in LEDGER_PATH.read_text().splitlines():
            if ln.strip():
                last_line = ln
        try:
            prev_hash = json.loads(last_line)["hash"]
        except Exception:
            prev_hash = "0" * 64
    row = {**payload, "prev_hash": prev_hash}
    row["hash"] = sha256_chain(prev_hash, payload)
    with LEDGER_PATH.open("a") as f:
        f.write(json.dumps(row, default=str) + "\n")
    return row


def read_ledger(tail: int = 12) -> list[dict]:
    if not LEDGER_PATH.exists():
        return []
    rows = []
    for ln in LEDGER_PATH.read_text().splitlines():
        if ln.strip():
            try:
                rows.append(json.loads(ln))
            except Exception:
                continue
    return rows[-tail:]


def verify_ledger() -> bool:
    """Walk the chain; True if every prev_hash matches and every row hash is valid."""
    if not LEDGER_PATH.exists():
        return True
    prev = "0" * 64
    for ln in LEDGER_PATH.read_text().splitlines():
        if not ln.strip():
            continue
        try:
            row = json.loads(ln)
        except Exception:
            return False
        if row.get("prev_hash") != prev:
            return False
        payload = {k: v for k, v in row.items() if k not in ("prev_hash", "hash")}
        if sha256_chain(prev, payload) != row.get("hash"):
            return False
        prev = row["hash"]
    return True


# ---------------------------------------------------------------------------
# End-to-end chain (stages 1-5 wired together)
# ---------------------------------------------------------------------------
@dataclass
class ChainTrace:
    asset: dict
    sensor: dict
    forecast: dict
    reorder: ReorderCard
    induction: InductionTask
    gantt: list[dict]
    ledger_row: dict
    stage_timings_ms: dict[str, float] = field(default_factory=dict)


def run_chain(*, asset: dict, classifier_result: dict, rul_result: dict,
              history_df: pd.DataFrame, inventory_df: pd.DataFrame,
              catalog: list[dict], depots: list[dict]) -> ChainTrace:
    """Fire all 5 stages and return the full trace."""
    import time
    timings = {}

    # Stage 1: sensor classifier (already computed; package it)
    t0 = time.time()
    sensor = {
        "class": classifier_result["class"],
        "confidence": classifier_result["confidence"],
        "rul_hours": rul_result["rul_hours"],
        "recommendation": rul_result["recommendation"],
        "severity": rul_result.get("model_severity", 0.0),
    }
    timings["stage1_sensor_ms"] = round((time.time() - t0) * 1000, 1)

    # Stage 2: forecast spike on this asset's NSN
    t0 = time.time()
    actual = _daily_consumption_for_nsn(history_df, asset["nsn"])
    # severity-shock: a fault flagged hot pulls up the forecast (RUL-driven)
    boost = 1.0 + (1.5 * float(sensor["severity"])
                   if sensor["class"] != "healthy" else 0.0)
    forecast = forecast_demand(actual, horizon=60, severity_boost=boost)
    timings["stage2_forecast_ms"] = round((time.time() - t0) * 1000, 1)

    # Stage 3: auto-reorder against GCSS-MC stock + ICM
    t0 = time.time()
    reorder = build_reorder_card(
        nsn=asset["nsn"], projected_30d=forecast["demand_30d"],
        inventory_df=inventory_df, catalog=catalog,
    )
    timings["stage3_reorder_ms"] = round((time.time() - t0) * 1000, 1)

    # Stage 4: depot induction reslot
    t0 = time.time()
    induction, gantt = reslot_induction(asset, depots, reorder)
    timings["stage4_induction_ms"] = round((time.time() - t0) * 1000, 1)

    # Stage 5: ledger append
    t0 = time.time()
    payload = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "kind": "PREDICT_MAINT_ACTION",
        "actor": "PREDICT-MAINT pipeline",
        "asset_id": asset["asset_id"],
        "nsn": asset["nsn"],
        "fault_class": sensor["class"],
        "rul_hours": sensor["rul_hours"],
        "projected_demand_30d": reorder.projected_demand_30d,
        "on_hand": reorder.on_hand,
        "shortfall": reorder.shortfall,
        "recommended_reorder_qty": reorder.recommended_reorder_qty,
        "source_depot": reorder.source_depot,
        "lead_time_days": reorder.lead_time_days,
        "action_due_by": reorder.action_due_by,
        "induction_depot": induction.depot,
        "induction_window": f"{induction.start} -> {induction.end}",
    }
    ledger_row = append_ledger(payload)
    timings["stage5_ledger_ms"] = round((time.time() - t0) * 1000, 1)

    return ChainTrace(
        asset=asset, sensor=sensor, forecast=forecast,
        reorder=reorder, induction=induction, gantt=gantt,
        ledger_row=ledger_row, stage_timings_ms=timings,
    )
