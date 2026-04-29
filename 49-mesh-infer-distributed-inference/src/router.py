"""MESH-INFER router.

Given (task_profile, sensitivity), pick the best mesh node.

The router is **deterministic** by design — every routing decision the demo
shows is reproducible offline. When per-node Kamiwaza endpoints are configured
(see data/load_real.py), the router additionally records the resolved live
endpoint in the routing decision so the SJA can verify in the audit chain.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

DATA = Path(__file__).resolve().parent.parent / "data"


def _load(name: str) -> Any:
    return json.loads((DATA / name).read_text())


_NODES_CACHE: list[dict] | None = None
_PROFILES_CACHE: dict | None = None
_SENSITIVITY_CACHE: dict | None = None


def nodes() -> list[dict]:
    global _NODES_CACHE
    if _NODES_CACHE is None:
        _NODES_CACHE = _load("node_catalog.json")
    return _NODES_CACHE


def profiles() -> dict:
    global _PROFILES_CACHE
    if _PROFILES_CACHE is None:
        _PROFILES_CACHE = _load("task_profiles.json")
    return _PROFILES_CACHE


def sensitivities() -> dict:
    global _SENSITIVITY_CACHE
    if _SENSITIVITY_CACHE is None:
        _SENSITIVITY_CACHE = _load("sensitivity_taxonomy.json")
    return _SENSITIVITY_CACHE


def route(task_key: str, sensitivity: str) -> dict:
    """Pick the best node for (task, sensitivity). Returns a routing decision dict.

    Decision keys:
      node_id, label, model, model_class, security_posture, network_class,
      latency_s, egress_kb, rationale, candidates_considered, live_endpoint?
    """
    profile = profiles()[task_key]
    sens = sensitivities()[sensitivity]
    allowable = set(sens["allowable_nodes"])

    candidates: list[tuple[float, dict, list[str]]] = []
    for node in nodes():
        reasons: list[str] = []
        if node["node_id"] not in allowable:
            continue
        if profile["needs_capability"] not in node["supports"]:
            continue

        score = 0.0
        if node["model_class"] == profile["preferred_model_class"]:
            score += 100
            reasons.append(f"+100 model_class match ({profile['preferred_model_class']})")
        if sens["rank"] >= 2 and "scif" in node["node_id"]:
            score += 50
            reasons.append(f"+50 high-sensitivity → SCIF preferred")
        if sens["rank"] <= 1 and node["node_id"] == "edge-meusoc":
            score += 25
            reasons.append("+25 low-sensitivity + edge model = latency win")
        if sens["rank"] == 0 and "scif" in node["node_id"]:
            score -= 30
            reasons.append("-30 over-classification penalty")
        score -= node["median_latency_s"] * 0.3
        reasons.append(f"-{node['median_latency_s']*0.3:.1f} latency penalty")
        candidates.append((score, node, reasons))

    if not candidates:
        # Default safest path
        fallback = next(n for n in nodes() if n["node_id"] == "scif-marforpac-mixtral")
        return _decision(fallback, profile, sens, "No exact capability match — defaulting to SCIF-Mixtral (safest).", [])

    candidates.sort(key=lambda x: -x[0])
    chosen_score, chosen, chosen_reasons = candidates[0]

    rationale = profile["rationale_template"].format(
        sens=sensitivity, node=chosen["label"], posture=chosen["security_posture"],
    )
    return _decision(chosen, profile, sens, rationale, chosen_reasons,
                     candidates_considered=[c[1]["node_id"] for c in candidates])


def _decision(node: dict, profile: dict, sens: dict, rationale: str,
              reasons: list[str], candidates_considered: list[str] | None = None) -> dict:
    egress = node["egress_kb_per_call"] if sens["max_egress_kb"] > 0 else 0
    out = {
        "node_id": node["node_id"],
        "label": node["label"],
        "model": node["model"],
        "model_class": node["model_class"],
        "security_posture": node["security_posture"],
        "network_class": node["network_class"],
        "latency_s": node["median_latency_s"],
        "egress_kb": egress,
        "rationale": rationale,
        "score_reasons": reasons,
        "candidates_considered": candidates_considered or [],
        "task_label": profile["label"],
        "sensitivity_label": sens["label"],
    }

    # If a real Kamiwaza endpoint is configured for this node, surface it
    try:
        from data.load_real import per_node_endpoints, is_live  # type: ignore
        if is_live():
            ep = per_node_endpoints().get(node["node_id"], {})
            if ep.get("base_url"):
                out["live_endpoint"] = {
                    "base_url": ep["base_url"],
                    "model": ep["model"],
                    "active": True,
                }
            else:
                out["live_endpoint"] = {"active": False, "reason": "per-node URL not set; using sim"}
    except Exception:  # noqa: BLE001
        pass

    return out
