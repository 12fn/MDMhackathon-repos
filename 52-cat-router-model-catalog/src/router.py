"""CAT-ROUTER — Kamiwaza Model Catalog routing engine.

Mimics what Kamiwaza's catalog API + Inference Mesh does in production:
given a task spec (modality, latency budget, security posture), score every
deployed model in the catalog and return the optimal pick with an explainable
rationale.

Catalog source: data/model_catalog.json (8 models with full metadata).
Real-Kamiwaza swap: see data/load_real.py (queries /v1/models on a live
KAMIWAZA_BASE_URL endpoint).
"""
from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import Any

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
AUDIT_PATH = DATA_DIR / "routing_audit.jsonl"


# ─────────────────────────────────────────────────────────────────────────────
# Catalog loader (cache-first; swap to load_real.py for live Kamiwaza)
# ─────────────────────────────────────────────────────────────────────────────
_CATALOG_CACHE: list[dict] | None = None
_TAXONOMY_CACHE: dict | None = None
_WORKFLOW_CACHE: dict | None = None


def load_catalog() -> list[dict]:
    """Load the model catalog. Synthetic file by default; can be swapped for a
    live Kamiwaza /v1/models query via data/load_real.py."""
    global _CATALOG_CACHE
    if _CATALOG_CACHE is None:
        with (DATA_DIR / "model_catalog.json").open() as f:
            _CATALOG_CACHE = json.load(f)
    return _CATALOG_CACHE


def load_taxonomy() -> dict:
    global _TAXONOMY_CACHE
    if _TAXONOMY_CACHE is None:
        with (DATA_DIR / "task_taxonomy.json").open() as f:
            _TAXONOMY_CACHE = json.load(f)
    return _TAXONOMY_CACHE


def load_workflows() -> dict:
    global _WORKFLOW_CACHE
    if _WORKFLOW_CACHE is None:
        with (DATA_DIR / "demo_workflow.json").open() as f:
            _WORKFLOW_CACHE = json.load(f)
    return _WORKFLOW_CACHE


def get_task_spec(task_type: str) -> dict:
    tax = load_taxonomy()
    for t in tax["task_types"]:
        if t["task_type"] == task_type:
            return t
    raise KeyError(f"Unknown task_type: {task_type!r}")


# ─────────────────────────────────────────────────────────────────────────────
# Scoring
# ─────────────────────────────────────────────────────────────────────────────
def _scar_ge(model_grade: str, floor: str) -> bool:
    rank = load_taxonomy()["scar_rank"]
    return rank.get(model_grade, 0) >= rank.get(floor, 0)


def _hard_filter(model: dict, requires: dict) -> tuple[bool, str | None]:
    """Return (passes, reason_failed)."""
    if requires.get("vision") and not model.get("vision"):
        return False, "vision required"
    if requires.get("tool_calls") and not model.get("tool_calls"):
        return False, "tool_calling required"
    if requires.get("min_context") and model.get("context_window", 0) < requires["min_context"]:
        return False, f"context_window {model.get('context_window')} < {requires['min_context']}"
    if requires.get("min_quality") and model.get("quality_score", 0) < requires["min_quality"]:
        return False, f"quality {model.get('quality_score')} < {requires['min_quality']}"
    floor = requires.get("scar_grade_floor")
    if floor and not _scar_ge(model.get("scar_grade", "IL2"), floor):
        return False, f"SCAR {model.get('scar_grade')} < {floor}"
    if requires.get("max_first_token_ms") and model.get("first_token_ms", 0) > requires["max_first_token_ms"]:
        return False, f"first_token_ms {model.get('first_token_ms')} > {requires['max_first_token_ms']}"
    return True, None


def _normalize(values: list[float], invert: bool = False) -> list[float]:
    if not values:
        return []
    lo, hi = min(values), max(values)
    if hi == lo:
        return [0.5 for _ in values]
    return [
        (1 - (v - lo) / (hi - lo)) if invert else ((v - lo) / (hi - lo))
        for v in values
    ]


def _fit_score(model: dict, task_type: str) -> float:
    """How well the model's `best_for` tags match the task. 0..1."""
    best = set(model.get("best_for", []))
    if task_type in best:
        return 1.0
    # partial credit for synonym overlap
    aliases = {
        "vision_isr": {"vision", "multimodal", "image_qa"},
        "fast_classification": {"fast_classification", "edge", "high_volume", "cheap"},
        "long_context_summarization": {"long_context_summarization", "synthesis", "rag"},
        "tool_calling": {"tool_calling", "function_calling", "agentic"},
        "long_form_prose": {"long_form_prose", "narrative", "brief_writing", "creative_writing"},
        "code_generation": {"code"},
        "math_reasoning": {"math", "reasoning", "stem"},
        "structured_extraction": {"structured_output", "tagging"},
        "redaction_tagging": {"redaction", "tagging", "enterprise", "structured_output"},
        "rag_synthesis": {"rag", "synthesis", "long_context_summarization"},
        "agentic_planning": {"agentic", "tool_calling"},
        "translation": {"multimodal"},
    }
    overlap = best & aliases.get(task_type, set())
    return min(0.6, 0.2 * len(overlap))


def score_model(model: dict, task: dict, *, mode: str = "best_quality") -> dict:
    """Score one model for one task. Returns a scoring breakdown dict.

    mode: "best_quality" uses full weights;
          "fast_cheap" rewrites weights to crush cost+speed and relaxes
          non-essential hard constraints (drops quality floor, IL5->IL4,
          drops first-token-budget). Vision and tool-calls remain hard
          constraints when the *task itself* truly requires them — but the
          quality and SCAR ceilings come down so cheaper models qualify.
    """
    requires = dict(task.get("requires", {}))
    weights = task["weight"].copy()
    if mode == "fast_cheap":
        weights = {"quality": 0.05, "speed": 0.30, "cost": 0.60, "fit": 0.05}
        # Relax non-mandatory floors so the cheap edge model qualifies for
        # everything except true vision / tool-calling tasks
        requires.pop("min_quality", None)
        requires.pop("max_first_token_ms", None)
        if requires.get("scar_grade_floor") == "IL5":
            requires["scar_grade_floor"] = "IL4"

    passes, reason = _hard_filter(model, requires)
    return {
        "model_id": model["model_id"],
        "passes_hard": passes,
        "fail_reason": reason,
        "raw": {
            "quality": model.get("quality_score", 0),
            "tps": model.get("tokens_per_second", 0),
            "ftk_ms": model.get("first_token_ms", 999),
            "cost_in": model.get("cost_per_1k_input_tokens", 0),
            "cost_out": model.get("cost_per_1k_output_tokens", 0),
            "fit": _fit_score(model, task["task_type"]),
        },
        "weights": weights,
    }


def route(task: dict, *, mode: str = "best_quality") -> dict:
    """Route a single task. Returns a verdict dict with winner + ranked + rationale."""
    catalog = load_catalog()
    spec = task if "weight" in task else get_task_spec(task["task_type"])
    if "weight" not in task:
        # caller passed a workflow task — splice in the spec
        spec = {**get_task_spec(task["task_type"]), **task}

    scored = [score_model(m, spec, mode=mode) for m in catalog]

    # Cross-model normalization for scaled axes
    raw_q = [s["raw"]["quality"] for s in scored]
    raw_speed = [s["raw"]["tps"] for s in scored]  # higher better
    raw_cost = [s["raw"]["cost_in"] + s["raw"]["cost_out"] for s in scored]  # lower better
    raw_fit = [s["raw"]["fit"] for s in scored]
    n_q = _normalize(raw_q)
    n_speed = _normalize(raw_speed)
    n_cost = _normalize(raw_cost, invert=True)
    n_fit = _normalize(raw_fit)

    for i, s in enumerate(scored):
        w = s["weights"]
        s["normalized"] = {
            "quality": n_q[i],
            "speed": n_speed[i],
            "cost": n_cost[i],
            "fit": n_fit[i],
        }
        # Composite score; hard-filter failures get a 0.0 floor but we keep them
        # in the ranking so we can show "would have been picked but lacks vision"
        composite = (
            w["quality"] * n_q[i]
            + w["speed"] * n_speed[i]
            + w["cost"] * n_cost[i]
            + w["fit"] * n_fit[i]
        )
        s["composite"] = composite if s["passes_hard"] else 0.0

    eligible = [s for s in scored if s["passes_hard"]]
    if not eligible:
        # Hard fallback: pick highest quality regardless
        eligible = sorted(scored, key=lambda s: s["raw"]["quality"], reverse=True)
    eligible.sort(key=lambda s: s["composite"], reverse=True)

    winner_id = eligible[0]["model_id"]
    winner = next(m for m in catalog if m["model_id"] == winner_id)
    rationale = _explain(winner, spec, eligible[0], mode)

    cost_est = (
        winner["cost_per_1k_input_tokens"] * (task.get("input_tokens", 0) / 1000)
        + winner["cost_per_1k_output_tokens"] * (task.get("output_tokens", 0) / 1000)
    )
    latency_est = (
        winner["first_token_ms"] / 1000.0
        + (task.get("output_tokens", 0) / max(1, winner["tokens_per_second"]))
    )

    return {
        "task_id": task.get("task_id"),
        "task_type": spec["task_type"],
        "task_label": task.get("label", spec.get("label", spec["task_type"])),
        "mode": mode,
        "winner_id": winner_id,
        "winner": winner,
        "rationale": rationale,
        "cost_estimate_usd": round(cost_est, 5),
        "latency_estimate_s": round(latency_est, 2),
        "quality_score": winner["quality_score"],
        "ranked": [
            {
                "model_id": s["model_id"],
                "composite": round(s["composite"], 4),
                "passes_hard": s["passes_hard"],
                "fail_reason": s["fail_reason"],
                "normalized": {k: round(v, 3) for k, v in s["normalized"].items()},
            }
            for s in sorted(scored, key=lambda x: x["composite"], reverse=True)
        ],
    }


def _explain(model: dict, spec: dict, score_row: dict, mode: str) -> str:
    """Build a one-line, operator-grade rationale string."""
    requires = spec.get("requires", {})
    bits: list[str] = []
    if requires.get("vision"):
        bits.append("vision required")
    if requires.get("tool_calls"):
        bits.append("tool-calling required")
    if requires.get("min_context"):
        bits.append(f"{requires['min_context']//1000}k context floor")
    if requires.get("scar_grade_floor"):
        bits.append(f"{requires['scar_grade_floor']} security floor")
    if requires.get("max_first_token_ms"):
        bits.append(f"sub-{requires['max_first_token_ms']}ms first-token budget")
    norm = score_row["normalized"]
    weights = score_row["weights"]
    dominant = max(weights, key=weights.get)
    dom_bit = {
        "quality": f"top-quartile quality ({model['quality_score']:.2f})",
        "speed": f"high throughput ({model['tokens_per_second']} tok/s)",
        "cost": f"cheap inference (${model['cost_per_1k_input_tokens']:.4f}/1k in)",
        "fit": f"best-for tag matches ({', '.join(model['best_for'][:2])})",
    }[dominant]
    home = model.get("hardware_home", "Kamiwaza pod")
    mode_tag = "FAST/CHEAP mode" if mode == "fast_cheap" else "best-quality mode"
    if not bits:
        head = f"{model['display_name']} wins under {mode_tag}"
    else:
        head = f"{' + '.join(bits)} -> {model['display_name']} wins under {mode_tag}"
    return f"{head}: {dom_bit}; deployed at {home}."


# ─────────────────────────────────────────────────────────────────────────────
# Workflow routing + audit chain
# ─────────────────────────────────────────────────────────────────────────────
def route_workflow(workflow_id: str, *, mode: str = "best_quality") -> dict:
    flows = load_workflows()
    flow = next((w for w in flows["workflows"] if w["workflow_id"] == workflow_id), None)
    if flow is None:
        raise KeyError(f"Unknown workflow_id: {workflow_id!r}")
    decisions = [route(t, mode=mode) for t in flow["tasks"]]
    total_cost = round(sum(d["cost_estimate_usd"] for d in decisions), 5)
    total_latency = round(sum(d["latency_estimate_s"] for d in decisions), 2)
    avg_quality = round(sum(d["quality_score"] for d in decisions) / len(decisions), 3)
    chain = audit_chain(workflow_id, mode, decisions)
    return {
        "workflow_id": workflow_id,
        "label": flow["label"],
        "narrator": flow["narrator"],
        "mode": mode,
        "decisions": decisions,
        "totals": {
            "cost_usd": total_cost,
            "latency_s": total_latency,
            "avg_quality": avg_quality,
            "n_unique_models": len({d["winner_id"] for d in decisions}),
        },
        "audit_chain": chain,
    }


def audit_chain(workflow_id: str, mode: str, decisions: list[dict]) -> list[dict]:
    """Hash-chain of model selections. Each row hashes (prev_hash + decision)."""
    chain: list[dict] = []
    prev = "GENESIS"
    for d in decisions:
        payload = {
            "workflow_id": workflow_id,
            "mode": mode,
            "task_id": d["task_id"],
            "task_type": d["task_type"],
            "winner_id": d["winner_id"],
            "rationale": d["rationale"],
            "cost_usd": d["cost_estimate_usd"],
        }
        body = json.dumps(payload, sort_keys=True)
        h = sha256((prev + "|" + body).encode()).hexdigest()
        chain.append({
            "prev_hash": prev[:12] + "..." if prev != "GENESIS" else "GENESIS",
            "hash": h[:12] + "...",
            "full_hash": h,
            **payload,
        })
        prev = h
    return chain


def append_audit(record: dict) -> None:
    """Append a decision record to the on-disk audit log (jsonl)."""
    AUDIT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with AUDIT_PATH.open("a") as f:
        f.write(json.dumps(record) + "\n")


# ─────────────────────────────────────────────────────────────────────────────
# Cached briefs (cache-first hero pattern)
# ─────────────────────────────────────────────────────────────────────────────
def load_cached_briefs() -> dict:
    p = DATA_DIR / "cached_briefs.json"
    if not p.exists():
        return {}
    return json.loads(p.read_text())


def precompute_all() -> dict:
    """Run every workflow under both modes and dump to cached_briefs.json."""
    flows = load_workflows()
    out: dict = {}
    for w in flows["workflows"]:
        out[w["workflow_id"]] = {
            "best_quality": route_workflow(w["workflow_id"], mode="best_quality"),
            "fast_cheap": route_workflow(w["workflow_id"], mode="fast_cheap"),
        }
    (DATA_DIR / "cached_briefs.json").write_text(json.dumps(out, indent=2, default=str))
    return out


# ─────────────────────────────────────────────────────────────────────────────
# Endpoint resolver (KAMIWAZA env-var beat)
# ─────────────────────────────────────────────────────────────────────────────
def kamiwaza_endpoint() -> str:
    return os.getenv("KAMIWAZA_BASE_URL") or "<unset> (set KAMIWAZA_BASE_URL to swap to on-prem)"


if __name__ == "__main__":
    out = precompute_all()
    print(f"Pre-computed {len(out)} workflows x 2 modes -> {DATA_DIR / 'cached_briefs.json'}")
