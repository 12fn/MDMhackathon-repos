"""CAT-ROUTER — synth catalog + workflow generator.

Catalog and taxonomy are checked-in static JSON (model_catalog.json,
task_taxonomy.json, demo_workflow.json). This generator just (re-)runs the
pre-compute step that warms cached_briefs.json with the routing decisions
for every workflow under both routing modes.

Real-Kamiwaza plug-in: see data/load_real.py — queries /v1/models on a live
KAMIWAZA_BASE_URL endpoint and emits a model_catalog.json in the same shape.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent.parent
APP_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(APP_ROOT))


def main() -> None:
    from src.router import precompute_all  # noqa: WPS433

    out = precompute_all()
    n_decisions = sum(len(v["best_quality"]["decisions"]) for v in out.values())
    print(f"Generated routing for {len(out)} workflows ({n_decisions} task decisions x 2 modes)")
    for wid, payload in out.items():
        bq = payload["best_quality"]["totals"]
        fc = payload["fast_cheap"]["totals"]
        print(
            f"  {wid:28s}  best_quality: ${bq['cost_usd']:.4f} / {bq['avg_quality']:.2f}q "
            f"|  fast_cheap: ${fc['cost_usd']:.4f} / {fc['avg_quality']:.2f}q"
        )


if __name__ == "__main__":
    main()
