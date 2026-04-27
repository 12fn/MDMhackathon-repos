"""Tiny synthetic data utilities used by app data/generate.py scripts.

Every app generator is seeded with `random.Random(1776)` so synthetic datasets
are reproducible. To plug in real data: swap or wrap the `_generate_*` calls
inside each app's `data/generate.py` to read your real source instead. See
DATA_INGESTION.md for per-app recipes.
"""
from __future__ import annotations

import csv
import json
import random
from pathlib import Path
from typing import Any, Iterable


def seeded(seed: int = 1776) -> random.Random:
    """Return a deterministic RNG. 1776 is the canonical seed for this repo."""
    return random.Random(seed)


def jitter_track(rng: random.Random, lat: float, lon: float, n: int,
                 step_km: float = 5.0) -> list[tuple[float, float]]:
    """Return n waypoints starting at (lat, lon) with small random jitter."""
    pts = []
    for _ in range(n):
        dlat = rng.gauss(0, step_km / 111.0)
        dlon = rng.gauss(0, step_km / 111.0)
        lat += dlat
        lon += dlon
        pts.append((lat, lon))
    return pts


def write_csv(path: Path, rows: Iterable[dict[str, Any]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, default=str))
