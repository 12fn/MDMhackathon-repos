"""MESH-INFER — synthetic data + cache-first scenario brief generator.

Produces:
  - node_catalog.json         4 nodes (edge / rear / SCIF-mixtral / SCIF-VL)
  - task_profiles.json        8 task types with routing requirements
  - sensitivity_taxonomy.json U / CUI / S / TS-SCI -> allowable nodes
  - demo_scenarios.json       4 multi-step scenarios
  - routing_audit.jsonl       hash-chained audit log seed
  - cached_briefs.json        4 scenarios pre-warmed (per-step routing trace)

Seed: 1776.
"""
from __future__ import annotations

import hashlib
import json
import random
import sys
from pathlib import Path

OUT = Path(__file__).parent
SEED = 1776

ROOT = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(ROOT))
APP = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(APP))


# ─────────────────────────────────────────────────────────────────────────────
# 1. Node catalog — 4 simulated mesh nodes
# ─────────────────────────────────────────────────────────────────────────────
NODE_CATALOG = [
    {
        "node_id": "edge-meusoc",
        "label": "Edge — MEU SOC",
        "location": "MEU SOC, embarked aboard LHD-7",
        "hardware": "NVIDIA Jetson Orin AGX 64 GB",
        "model": "Qwen2.5-VL-7B",
        "model_class": "vision-language",
        "parameters_b": 7,
        "quantization": "AWQ-INT4",
        "serving": "vLLM (single-GPU)",
        "security_posture": "IL2 (UNCLASS)",
        "network_class": "NIPR / DDIL-tolerant",
        "max_sensitivity": "CUI",
        "supports": ["vision", "ocr", "asr-short", "lightweight-classify"],
        "median_latency_s": 0.8,
        "egress_kb_per_call": 12,
        "lat_lon": [21.30, -157.86],   # Pearl Harbor area (LHD-7 op area)
        "color": "#00FFA7",
    },
    {
        "node_id": "rear-quantico",
        "label": "Rear Depot — MCB Quantico",
        "location": "MCB Quantico, VA — Marine Corps Cyberspace Operations Group",
        "hardware": "Lambda Labs DGX H100 (8x H100 80 GB)",
        "model": "Llama 3.3 70B FP8",
        "model_class": "general-purpose-large",
        "parameters_b": 70,
        "quantization": "FP8 (TensorRT-LLM)",
        "serving": "vLLM, tensor-parallel=8",
        "security_posture": "IL5 (CUI)",
        "network_class": "NIPR + SIPR (gateway)",
        "max_sensitivity": "SECRET",
        "supports": ["classify", "json-extract", "summarize", "rerank", "embed"],
        "median_latency_s": 9.2,
        "egress_kb_per_call": 240,
        "lat_lon": [38.52, -77.31],
        "color": "#0DCC8A",
    },
    {
        "node_id": "scif-marforpac-mixtral",
        "label": "SCIF — MARFORPAC HQ (Mixtral)",
        "location": "MARFORPAC HQ, Camp H.M. Smith — JWICS enclave",
        "hardware": "On-prem 4x H200 144 GB cluster (airgapped)",
        "model": "Mixtral 8x22B",
        "model_class": "general-purpose-mixture-of-experts",
        "parameters_b": 141,
        "quantization": "FP16 (full precision)",
        "serving": "vLLM, pipeline-parallel=2 + tensor-parallel=2",
        "security_posture": "IL6 (SECRET / TS)",
        "network_class": "JWICS (no internet egress)",
        "max_sensitivity": "TS-SCI",
        "supports": ["draft", "cable", "policy", "long-context", "json-extract"],
        "median_latency_s": 18.4,
        "egress_kb_per_call": 0,
        "lat_lon": [21.36, -157.91],
        "color": "#00BB7A",
    },
    {
        "node_id": "scif-marforpac-vl",
        "label": "SCIF — MARFORPAC HQ (Vision)",
        "location": "MARFORPAC HQ, Camp H.M. Smith — JWICS enclave",
        "hardware": "On-prem 2x H100 80 GB (airgapped)",
        "model": "Qwen2.5-VL-72B",
        "model_class": "vision-language-large",
        "parameters_b": 72,
        "quantization": "FP16",
        "serving": "vLLM, tensor-parallel=2",
        "security_posture": "IL6 (SECRET / TS)",
        "network_class": "JWICS (no internet egress)",
        "max_sensitivity": "TS-SCI",
        "supports": ["vision-classified", "geoint-imagery", "humint-recommend", "long-context"],
        "median_latency_s": 14.0,
        "egress_kb_per_call": 0,
        "lat_lon": [21.36, -157.91],
        "color": "#065238",
    },
]


# ─────────────────────────────────────────────────────────────────────────────
# 2. Task profiles — 8 task types with routing requirements
# ─────────────────────────────────────────────────────────────────────────────
TASK_PROFILES = {
    "vision-thermal-ir": {
        "label": "Vision — thermal IR / EO classification",
        "needs_capability": "vision",
        "preferred_model_class": "vision-language",
        "min_context_k": 2,
        "expected_latency_band": "sub-second",
        "default_sensitivity": "UNCLASS",
        "rationale_template": "Step needs vision → routed to a VL model. Sensitivity = {sens} → {posture} OK.",
    },
    "vision-classified-imagery": {
        "label": "Vision — classified GEOINT imagery",
        "needs_capability": "vision-classified",
        "preferred_model_class": "vision-language-large",
        "min_context_k": 8,
        "expected_latency_band": "10-20s",
        "default_sensitivity": "SECRET",
        "rationale_template": "Step needs classified vision → must stay in SCIF. Routed to SCIF-VL.",
    },
    "classify-intent-json": {
        "label": "Classify intent → structured JSON",
        "needs_capability": "json-extract",
        "preferred_model_class": "general-purpose-large",
        "min_context_k": 4,
        "expected_latency_band": "8-12s",
        "default_sensitivity": "CUI",
        "rationale_template": "Step needs structured JSON over CUI → routed to {node} (Llama 3.3 70B FP8).",
    },
    "draft-cable-sipr": {
        "label": "Draft SIPR cable (SECRET)",
        "needs_capability": "draft",
        "preferred_model_class": "general-purpose-mixture-of-experts",
        "min_context_k": 8,
        "expected_latency_band": "15-25s",
        "default_sensitivity": "SECRET",
        "rationale_template": "SECRET drafting → must stay in SCIF. Routed to {node} (Mixtral 8x22B). Bandwidth out = 0.",
    },
    "humint-recommend": {
        "label": "HUMINT tipping recommendation (TS-SCI)",
        "needs_capability": "humint-recommend",
        "preferred_model_class": "vision-language-large",
        "min_context_k": 8,
        "expected_latency_band": "10-18s",
        "default_sensitivity": "TS-SCI",
        "rationale_template": "TS-SCI HUMINT recommendation → SCIF-only. Routed to {node}. No egress permitted.",
    },
    "summarize-cui": {
        "label": "Summarize CUI brief",
        "needs_capability": "summarize",
        "preferred_model_class": "general-purpose-large",
        "min_context_k": 6,
        "expected_latency_band": "6-10s",
        "default_sensitivity": "CUI",
        "rationale_template": "CUI summarization → rear-depot Llama acceptable. Routed to {node}.",
    },
    "asr-radio-traffic": {
        "label": "ASR — short radio cut",
        "needs_capability": "asr-short",
        "preferred_model_class": "vision-language",
        "min_context_k": 1,
        "expected_latency_band": "sub-second",
        "default_sensitivity": "UNCLASS",
        "rationale_template": "Short ASR cut → edge VL model handles audio. Routed to {node}.",
    },
    "rerank-citations": {
        "label": "Rerank citations / docs",
        "needs_capability": "rerank",
        "preferred_model_class": "general-purpose-large",
        "min_context_k": 4,
        "expected_latency_band": "3-6s",
        "default_sensitivity": "CUI",
        "rationale_template": "Rerank over CUI corpus → rear-depot Llama. Routed to {node}.",
    },
}


# ─────────────────────────────────────────────────────────────────────────────
# 3. Sensitivity taxonomy — which classifications can run on which node
# ─────────────────────────────────────────────────────────────────────────────
SENSITIVITY_TAXONOMY = {
    "UNCLASS": {
        "rank": 0,
        "label": "U — Unclassified",
        "allowable_nodes": ["edge-meusoc", "rear-quantico", "scif-marforpac-mixtral", "scif-marforpac-vl"],
        "max_egress_kb": 1024,
        "network_classes": ["NIPR", "SIPR", "JWICS"],
        "notes": "Routable anywhere. Prefer edge for latency.",
    },
    "CUI": {
        "rank": 1,
        "label": "CUI — Controlled Unclassified",
        "allowable_nodes": ["edge-meusoc", "rear-quantico", "scif-marforpac-mixtral", "scif-marforpac-vl"],
        "max_egress_kb": 512,
        "network_classes": ["NIPR (encrypted)", "SIPR", "JWICS"],
        "notes": "Edge OK if data already at edge; otherwise rear-depot preferred.",
    },
    "SECRET": {
        "rank": 2,
        "label": "S — SECRET",
        "allowable_nodes": ["rear-quantico", "scif-marforpac-mixtral", "scif-marforpac-vl"],
        "max_egress_kb": 0,
        "network_classes": ["SIPR", "JWICS"],
        "notes": "Cannot leave the SIPR/JWICS perimeter. Rear-depot OK if SIPR-attached.",
    },
    "TS-SCI": {
        "rank": 3,
        "label": "TS-SCI — Top Secret / SCI",
        "allowable_nodes": ["scif-marforpac-mixtral", "scif-marforpac-vl"],
        "max_egress_kb": 0,
        "network_classes": ["JWICS"],
        "notes": "SCIF-only. Bandwidth-out is physically blocked.",
    },
}


# ─────────────────────────────────────────────────────────────────────────────
# 4. Demo scenarios — 4 multi-step missions
# ─────────────────────────────────────────────────────────────────────────────
DEMO_SCENARIOS = [
    {
        "id": "threat_vessel_sipr",
        "title": "Threat-vessel ID → SIPR cable → HUMINT tip",
        "operator_prompt": (
            "Identify the threat vessel in this thermal IR feed, classify intent, "
            "draft a SIPR cable to MARFORPAC G-2, and recommend a HUMINT tipping "
            "to the on-station HET."
        ),
        "context_blurb": "MEU SOC, vicinity South China Sea. Thermal IR feed off the LHD-7 hangar bay.",
        "steps": [
            {"task": "vision-thermal-ir", "sensitivity": "UNCLASS",
             "input_summary": "12-frame thermal IR clip, fishing-trawler silhouette, low signature."},
            {"task": "classify-intent-json", "sensitivity": "CUI",
             "input_summary": "Vessel + AIS-gap + heading toward restricted lane → intent inference."},
            {"task": "draft-cable-sipr", "sensitivity": "SECRET",
             "input_summary": "SIPR cable: subject vessel, intent, recommended COA."},
            {"task": "humint-recommend", "sensitivity": "TS-SCI",
             "input_summary": "Cross-ref to TS-SCI HUMINT graph → tip-and-cue recommendation."},
        ],
    },
    {
        "id": "convoy_ied_brief",
        "title": "Convoy IED indicator → CUI summary → SECRET COA",
        "operator_prompt": (
            "Summarize the last 24h of convoy ISR for IED indicators in AO-FALCON, "
            "then draft a SECRET commander's update with recommended route changes."
        ),
        "context_blurb": "I-MEF G-3, AO-FALCON. NIPR ISR feeds + SIPR overlay.",
        "steps": [
            {"task": "summarize-cui", "sensitivity": "CUI",
             "input_summary": "240 ISR events, NIPR-tagged, last 24h, 7 hot spots."},
            {"task": "rerank-citations", "sensitivity": "CUI",
             "input_summary": "Rerank top 40 citations against IED-indicator schema."},
            {"task": "draft-cable-sipr", "sensitivity": "SECRET",
             "input_summary": "SECRET commander's update + COA — route changes for next 12h."},
        ],
    },
    {
        "id": "uav_geoint_assess",
        "title": "GEOINT imagery (TS) → SCIF-only assessment",
        "operator_prompt": (
            "Assess the new MQ-9 GEOINT pass over OBJ-COBALT (TS-SCI), then draft "
            "a J-2 read-in summary that stays inside the SCIF."
        ),
        "context_blurb": "II MEF G-2 SCIF, JWICS-only feeds.",
        "steps": [
            {"task": "vision-classified-imagery", "sensitivity": "TS-SCI",
             "input_summary": "MQ-9 EO/IR pass, OBJ-COBALT, 0.3 m GSD."},
            {"task": "draft-cable-sipr", "sensitivity": "SECRET",
             "input_summary": "Read-in summary — downgraded SECRET version for forward use."},
            {"task": "humint-recommend", "sensitivity": "TS-SCI",
             "input_summary": "HUMINT cross-cue against COBALT entity graph."},
        ],
    },
    {
        "id": "marfor_ops_briefing",
        "title": "Multi-source ops briefing — edge ASR → rear classify → SCIF draft",
        "operator_prompt": (
            "Take this 30-second tactical radio cut, classify the reporter's "
            "intent, then draft an OPSUM for the MARFORPAC battle watch."
        ),
        "context_blurb": "MEU SOC pier-side. Single radio cut + situational context.",
        "steps": [
            {"task": "asr-radio-traffic", "sensitivity": "UNCLASS",
             "input_summary": "30 s tactical radio cut, single voice, callsign HOTEL-2."},
            {"task": "classify-intent-json", "sensitivity": "CUI",
             "input_summary": "Map intent → JSON schema (event_type, urgency, recommended_actor)."},
            {"task": "draft-cable-sipr", "sensitivity": "SECRET",
             "input_summary": "OPSUM for MARFORPAC battle watch — SECRET formatting."},
        ],
    },
]


# ─────────────────────────────────────────────────────────────────────────────
# 5. Hash-chained audit seed
# ─────────────────────────────────────────────────────────────────────────────
def _hash(prev_hash: str, payload: dict) -> str:
    h = hashlib.sha256()
    h.update(prev_hash.encode("utf-8"))
    h.update(json.dumps(payload, sort_keys=True).encode("utf-8"))
    return h.hexdigest()


def make_audit_seed() -> list[dict]:
    """Seed line so the chain has a known genesis."""
    genesis = {
        "ts": "2026-04-27T00:00:00Z",
        "kind": "GENESIS",
        "operator": "system",
        "scenario_id": None,
        "step": None,
        "node_id": None,
        "model": None,
        "sensitivity": None,
        "rationale": "MESH-INFER audit chain genesis.",
        "egress_kb": 0,
        "latency_s": 0.0,
        "prev_hash": "0" * 64,
    }
    genesis["entry_hash"] = _hash("0" * 64, genesis)
    return [genesis]


# ─────────────────────────────────────────────────────────────────────────────
# 6. Cached briefs — pre-warmed per-step routing trace per scenario
# ─────────────────────────────────────────────────────────────────────────────
def _route_for_step(task_key: str, sensitivity: str) -> dict:
    """Mirror src/router.py's routing decision, but inline + deterministic for cache."""
    profile = TASK_PROFILES[task_key]
    sens = SENSITIVITY_TAXONOMY[sensitivity]
    allowable = set(sens["allowable_nodes"])

    # Score each candidate node
    candidates = []
    for node in NODE_CATALOG:
        if node["node_id"] not in allowable:
            continue
        if profile["needs_capability"] not in node["supports"]:
            continue
        # Score: prefer matching model_class, then lowest latency that meets the band
        score = 0
        if node["model_class"] == profile["preferred_model_class"]:
            score += 100
        # Sensitivity-fit bonus
        if sens["rank"] >= 2 and "scif" in node["node_id"]:
            score += 50
        if sens["rank"] <= 1 and node["node_id"] == "edge-meusoc":
            score += 25
        # Penalize over-spec'd routes for low-sensitivity
        if sens["rank"] == 0 and "scif" in node["node_id"]:
            score -= 30
        score -= node["median_latency_s"] * 0.3
        candidates.append((score, node))
    if not candidates:
        return {"node_id": "scif-marforpac-mixtral", "rationale": "No exact match — defaulting to SCIF-Mixtral (safest)."}

    candidates.sort(key=lambda x: -x[0])
    chosen = candidates[0][1]
    rationale = profile["rationale_template"].format(
        sens=sensitivity, node=chosen["label"], posture=chosen["security_posture"],
    )
    return {
        "node_id": chosen["node_id"],
        "label": chosen["label"],
        "model": chosen["model"],
        "rationale": rationale,
        "latency_s": chosen["median_latency_s"],
        "egress_kb": chosen["egress_kb_per_call"] if SENSITIVITY_TAXONOMY[sensitivity]["max_egress_kb"] > 0 else 0,
        "security_posture": chosen["security_posture"],
        "network_class": chosen["network_class"],
    }


def _synthesize_step_output(scenario: dict, step_idx: int, step: dict, route: dict) -> str:
    """Deterministic synthesized step output — what each node 'returned'.
    These are intentionally short, plausible mission-language strings — not
    LLM-generated, so the demo is fully reproducible offline."""
    task = step["task"]
    if task == "vision-thermal-ir":
        return ("VESSEL DETECTED — small craft, ~22 m LOA, low thermal signature, "
                "two crew, no nav lights. Hull profile consistent with modified "
                "fishing trawler (PRC-flagged class observed in prior weeks). "
                "Confidence 0.81.")
    if task == "vision-classified-imagery":
        return ("OBJ-COBALT pass — 14 hardstand vehicles, 3 covered. New berm "
                "construction NW corner since last collect. Two POL bladders "
                "added. (Full coordinates retained in SCIF — not propagated.)")
    if task == "classify-intent-json":
        return json.dumps({
            "event_type": "suspected-ISR-or-smuggling",
            "urgency": "moderate",
            "indicators": ["AIS-gap", "heading-restricted-lane", "low-thermal"],
            "recommended_actor": "MEU-SOC-watch",
            "confidence": 0.74,
        }, indent=2)
    if task == "draft-cable-sipr":
        return ("SUBJ: SUSPECTED VESSEL OF INTEREST — VICINITY [REDACTED]\n"
                "1. (S) At 271830Z APR 26, MEU SOC observed a 22 m vessel "
                "exiting AIS coverage on heading toward restricted lane. "
                "Thermal indicates 2 crew, low signature, profile consistent "
                "with previously-tracked PRC-flagged trawler class.\n"
                "2. (S) RECOMMEND: MARFORPAC G-2 cue national means; on-station "
                "HET to attempt source contact.\n"
                "3. POC: WATCH OFFICER, MEU SOC.")
    if task == "humint-recommend":
        return ("HUMINT TIP: route source HOTEL-7 (vetted, last contact 11 d) "
                "for proximity collection on subject vessel's likely return "
                "port. Cross-cue to TS-SCI link diagram entity 'COBALT-3'. "
                "Recommend TS-SCI handling. (Full diagram retained SCIF-side.)")
    if task == "summarize-cui":
        return ("Last-24h ISR summary, AO-FALCON: 240 events, 7 IED-indicator "
                "clusters concentrated along MSR-TAMPA km 14-21. 3 culvert "
                "anomalies, 2 dismount-loiter events, 2 emplaced-object "
                "detections. Trend: rising.")
    if task == "asr-radio-traffic":
        return ("HOTEL-2 reports: 'Two pax, white pickup, observed at grid "
                "REDACTED, moving south. Possible advance scout. Request "
                "QRF posture confirmation.'")
    if task == "rerank-citations":
        return ("Reranked 40 → 8 high-relevance citations. Top 3: ISR-FRAG-"
                "0712 (culvert), HUMINT-WX-2261 (advance-scout pattern), "
                "SIGINT-LP-0033 (radio handshake on freq F-7).")
    return f"[stub output for {task}]"


def precompute_cached_briefs() -> dict:
    """Walk every scenario, route every step, capture full trace + audit chain."""
    out: dict = {"scenarios": {}}
    for sc in DEMO_SCENARIOS:
        trace_steps = []
        total_latency = 0.0
        total_egress = 0
        sensitivity_max_rank = 0
        for i, step in enumerate(sc["steps"]):
            route = _route_for_step(step["task"], step["sensitivity"])
            output = _synthesize_step_output(sc, i, step, route)
            trace_steps.append({
                "idx": i,
                "task": step["task"],
                "task_label": TASK_PROFILES[step["task"]]["label"],
                "sensitivity": step["sensitivity"],
                "input_summary": step["input_summary"],
                "route": route,
                "output": output,
            })
            total_latency += route["latency_s"]
            total_egress += route["egress_kb"]
            sensitivity_max_rank = max(sensitivity_max_rank, SENSITIVITY_TAXONOMY[step["sensitivity"]]["rank"])

        # Commercial-cloud equivalent (single-endpoint baseline)
        cloud_baseline = {
            "endpoint": "single commercial cloud LLM (cloud-only)",
            "model": "single multi-tenant frontier model",
            "total_latency_s": round(total_latency * 0.85, 1),  # cloud is faster on average
            "total_egress_kb": sum(max(40, len(s["input_summary"])) for s in sc["steps"]) + 600,
            "would_leak": [s for s in sc["steps"] if SENSITIVITY_TAXONOMY[s["sensitivity"]]["rank"] >= 2],
            "leak_count": sum(1 for s in sc["steps"] if SENSITIVITY_TAXONOMY[s["sensitivity"]]["rank"] >= 2),
            "verdict": "FAIL — classified content would egress." if any(
                SENSITIVITY_TAXONOMY[s["sensitivity"]]["rank"] >= 2 for s in sc["steps"]
            ) else "OK at UNCLASS, but no per-step routing.",
        }

        out["scenarios"][sc["id"]] = {
            "scenario": sc,
            "trace": trace_steps,
            "totals": {
                "mesh_latency_s": round(total_latency, 1),
                "mesh_egress_kb": total_egress,
                "sensitivity_max": list(SENSITIVITY_TAXONOMY.keys())[sensitivity_max_rank],
                "node_count_used": len({s["route"]["node_id"] for s in trace_steps}),
            },
            "cloud_baseline": cloud_baseline,
        }
    return out


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────
def main() -> None:
    rng = random.Random(SEED)  # noqa: F841 — held for future jitter
    OUT.mkdir(parents=True, exist_ok=True)

    (OUT / "node_catalog.json").write_text(json.dumps(NODE_CATALOG, indent=2))
    (OUT / "task_profiles.json").write_text(json.dumps(TASK_PROFILES, indent=2))
    (OUT / "sensitivity_taxonomy.json").write_text(json.dumps(SENSITIVITY_TAXONOMY, indent=2))
    (OUT / "demo_scenarios.json").write_text(json.dumps(DEMO_SCENARIOS, indent=2))

    # Audit seed (jsonl)
    audit_path = OUT / "routing_audit.jsonl"
    with audit_path.open("w") as f:
        for entry in make_audit_seed():
            f.write(json.dumps(entry) + "\n")

    # Cached briefs (the cache-first pattern hero)
    briefs = precompute_cached_briefs()
    (OUT / "cached_briefs.json").write_text(json.dumps(briefs, indent=2))

    print(f"Wrote {len(NODE_CATALOG)} nodes, {len(TASK_PROFILES)} task profiles, "
          f"{len(SENSITIVITY_TAXONOMY)} sensitivity tiers, "
          f"{len(DEMO_SCENARIOS)} scenarios, {len(briefs['scenarios'])} cached briefs.")
    print(f"All artifacts at {OUT}")


if __name__ == "__main__":
    main()
