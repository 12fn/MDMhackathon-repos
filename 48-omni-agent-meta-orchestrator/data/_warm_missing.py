"""One-shot pre-warmer for the 5 missing demo briefs.

Reads data/cached_briefs.json, identifies the 5 missing query_ids, tries the
live agent loop first (35s budget per query), falls back to the deterministic
synthetic trace from generate.py. Marks each entry with `source` =
"live_llm" or "deterministic_baseline" so the UI / audit can tell.

Run from repo root or from anywhere — paths are absolute via __file__.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

APP_ROOT = Path(__file__).resolve().parents[1]
ROOT = APP_ROOT.parents[1]
for p in (ROOT, APP_ROOT):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

DATA_DIR = APP_ROOT / "data"
MISSING = [
    "cui_release_review",
    "pcs_combined_move",
    "compute_at_data",
    "fed_rag_silo_query",
    "pallet_count_apra",
]


def main() -> None:
    from data.generate import _build_synthetic_trace, _try_live  # type: ignore

    demos = json.loads((DATA_DIR / "demo_queries.json").read_text())["queries"]
    by_id = {d["id"]: d for d in demos}

    cached_path = DATA_DIR / "cached_briefs.json"
    cached = json.loads(cached_path.read_text()) if cached_path.exists() else {}

    have = set(cached.keys())
    todo = [qid for qid in MISSING if qid not in have]
    print(f"existing keys: {sorted(have)}")
    print(f"to warm:       {todo}")

    results: dict[str, str] = {}
    for qid in todo:
        demo = by_id.get(qid)
        if demo is None:
            print(f"  [skip] {qid}: not present in demo_queries.json")
            continue
        print(f"\n=== {qid} ===")
        print(f"  prompt: {demo['prompt'][:120]}...")
        print(f"  expected_tools: {demo.get('expected_tools')}")

        live = _try_live(demo, timeout_s=45)
        if live and live.get("final"):
            entry = live
            entry["source"] = "live_llm"
            results[qid] = "live_llm"
            print(f"  -> live OK ({entry.get('tools_fired_count', '?')} tools, "
                  f"{entry.get('total_ms', '?')}ms)")
        else:
            print(f"  -> live failed/empty; building deterministic baseline")
            entry = _build_synthetic_trace(demo)
            entry["source"] = "deterministic_baseline"
            results[qid] = "deterministic_baseline"
            print(f"  -> deterministic OK ({entry.get('tools_fired_count', '?')} tools)")
        cached[qid] = entry

    cached_path.write_text(json.dumps(cached, indent=2, default=str))
    print(f"\n[OK] wrote {cached_path} with {len(cached)} total entries")
    print(f"[OK] sources: {results}")


if __name__ == "__main__":
    main()
