"""Precompute Class IX sustainment briefs for all default scenarios and cache
to disk so the Streamlit demo can render the LLM hero output instantly.

    cd apps/19-reorder
    python -m data.precompute_briefs

Writes data/cached_briefs.json keyed by scenario id.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
REPO_ROOT = ROOT.parent.parent
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(ROOT))

from data.generate import synth_maintenance_history  # noqa: E402
from src import agent, forecast  # noqa: E402

DATA = ROOT / "data"


def main() -> None:
    catalog = json.loads((DATA / "nsn_catalog.json").read_text())
    catalog_by_nsn = {c["nsn"]: c for c in catalog}
    forward_nodes = json.loads((DATA / "forward_nodes.json").read_text())
    scenarios = json.loads((DATA / "scenarios.json").read_text())
    # Default forward node for the precomputed briefs: Okinawa Forward.
    forward = next(n for n in forward_nodes if n["id"] == "OKI-FWD")

    cache: dict[str, dict] = {}
    for sc in scenarios:
        print(f"\n[{sc['id']}] Synthesizing 90 days, forecasting top 12 NSNs…")
        records = synth_maintenance_history(
            catalog, days=90,
            magtf_size=sc["magtf_size"],
            optempo=sc["optempo"],
            environment=sc["environment"],
        )
        df = pd.DataFrame(records)
        forecasts = forecast.build_forecasts(df, top_n=12, horizon=90)
        judged = agent.judge_top_nsns(forecasts, catalog_by_nsn, forward,
                                      scenario=sc)
        try:
            brief = agent.write_brief(judged, sc, forward,
                                      hero=True, use_cache=False)
            print(f"  -> brief generated ({len(brief)} chars)")
        except Exception as e:
            print(f"  ! LLM failed ({e}); writing baseline brief.")
            brief = agent.baseline_brief(judged, sc, forward)
        cache[sc["id"]] = {
            "brief": brief,
            "judged": judged,
            "scenario": sc,
            "forward_node_id": forward["id"],
        }

    (DATA / "cached_briefs.json").write_text(json.dumps(cache, indent=2))
    print(f"\nWrote {DATA / 'cached_briefs.json'} for {len(cache)} scenarios.")


if __name__ == "__main__":
    main()
