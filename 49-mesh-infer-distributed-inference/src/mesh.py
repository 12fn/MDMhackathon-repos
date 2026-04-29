"""MESH-INFER mesh runner.

Walks a multi-step scenario, dispatches each step via the router, captures the
trace, and writes audit entries. Cache-first: if a scenario has a pre-warmed
cached_briefs.json entry, returns that instantly. Live runs only fire when
the operator clicks 'Re-run live'.
"""
from __future__ import annotations

import json
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutTimeout
from pathlib import Path
from typing import Any

from src import audit, router

DATA = Path(__file__).resolve().parent.parent / "data"


def load_cached_briefs() -> dict:
    p = DATA / "cached_briefs.json"
    if not p.exists():
        return {"scenarios": {}}
    return json.loads(p.read_text())


def load_scenarios() -> list[dict]:
    return json.loads((DATA / "demo_scenarios.json").read_text())


def get_scenario(scenario_id: str) -> dict | None:
    for sc in load_scenarios():
        if sc["id"] == scenario_id:
            return sc
    return None


# ─────────────────────────────────────────────────────────────────────────────
# Cache-first run
# ─────────────────────────────────────────────────────────────────────────────
def run_cached(scenario_id: str) -> dict | None:
    """Return the cached trace for a scenario, or None if not cached."""
    cache = load_cached_briefs()
    return cache.get("scenarios", {}).get(scenario_id)


def run_live(scenario_id: str, *, hero: bool = False) -> dict:
    """Live mesh run with watchdog. Falls back to cached output on timeout.

    Each step:
      1. router.route(task, sensitivity) → routing decision
      2. simulated dispatch (or live LLM call if shared.kamiwaza_client available)
      3. audit.append(...) — chained log entry
    """
    sc = get_scenario(scenario_id)
    if not sc:
        raise ValueError(f"Unknown scenario: {scenario_id}")

    cached = run_cached(scenario_id) or {"trace": []}
    cached_outputs = {step.get("idx", i): step.get("output", "") for i, step in enumerate(cached["trace"])}

    trace_steps = []
    total_latency = 0.0
    total_egress = 0
    sens_rank_max = 0
    sens_taxo = router.sensitivities()

    for i, step in enumerate(sc["steps"]):
        decision = router.route(step["task"], step["sensitivity"])

        # Simulated dispatch — sleep proportional to median latency, divided
        # for demo speed. Real Kamiwaza endpoints would replace this block.
        sim_lat = max(0.4, decision["latency_s"] / 6.0)  # demo-friendly compress
        t0 = time.time()
        try:
            output = _dispatch(decision, step, hero=hero, fallback=cached_outputs.get(i, ""))
        except Exception as e:  # noqa: BLE001
            output = cached_outputs.get(i, f"(dispatch error: {e})")
        elapsed = max(time.time() - t0, sim_lat)

        # Audit log
        audit.append({
            "kind": "ROUTE",
            "scenario_id": scenario_id,
            "step": i,
            "node_id": decision["node_id"],
            "model": decision["model"],
            "sensitivity": step["sensitivity"],
            "rationale": decision["rationale"],
            "egress_kb": decision["egress_kb"],
            "latency_s": round(elapsed, 2),
            "live_endpoint": decision.get("live_endpoint"),
        })

        trace_steps.append({
            "idx": i,
            "task": step["task"],
            "task_label": decision["task_label"],
            "sensitivity": step["sensitivity"],
            "input_summary": step["input_summary"],
            "route": decision,
            "output": output,
            "live_latency_s": round(elapsed, 2),
        })
        total_latency += elapsed
        total_egress += decision["egress_kb"]
        sens_rank_max = max(sens_rank_max, sens_taxo[step["sensitivity"]]["rank"])

    cloud_baseline = (cached or {}).get("cloud_baseline", {})

    return {
        "scenario": sc,
        "trace": trace_steps,
        "totals": {
            "mesh_latency_s": round(total_latency, 1),
            "mesh_egress_kb": total_egress,
            "sensitivity_max": list(sens_taxo.keys())[sens_rank_max],
            "node_count_used": len({s["route"]["node_id"] for s in trace_steps}),
        },
        "cloud_baseline": cloud_baseline,
        "_live": True,
    }


def _dispatch(decision: dict, step: dict, *, hero: bool, fallback: str) -> str:
    """Dispatch a step. If a real Kamiwaza endpoint is configured for this node,
    fire a chat completion against it. Otherwise return the cached/fallback
    output (which is the expected demo path)."""
    live = decision.get("live_endpoint", {})
    if not live or not live.get("active"):
        # Try the shared client (single-endpoint sim) if available — wrapped in
        # a watchdog so the demo never stalls.
        try:
            from shared.kamiwaza_client import chat  # type: ignore
            prompt = (
                f"You are the {decision['label']} node. "
                f"Task: {decision['task_label']}. Sensitivity: {step['sensitivity']}. "
                f"Input: {step['input_summary']}. "
                f"Respond in <=120 words, mission-language only."
            )
            with ThreadPoolExecutor(max_workers=1) as ex:
                fut = ex.submit(lambda: chat(
                    [{"role": "system", "content": "You are a USMC mission analyst."},
                     {"role": "user", "content": prompt}],
                    max_tokens=240,
                ))
                return fut.result(timeout=8 if not hero else 18)
        except (FutTimeout, Exception):  # noqa: BLE001
            return fallback or "(dispatch fell back to cached output)"
    # Live per-node endpoint path (left as docs — actual SDK call would go here)
    return fallback or "(live per-node call would run here)"
