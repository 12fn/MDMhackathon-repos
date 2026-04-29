"""DDE execution simulator.

The point of this module is to compute, for any (query, set-of-nodes) pair,
two execution traces:

  - "naive":   pull every byte of every involved node into a central embedder
               then query. Bandwidth-heavy, slow, spillage-risky.
  - "dde":     ship the query + a small (~10 MB) inference payload to each
               involved node, run compute LOCALLY, return only per-node text
               answers (~tens of KB). Fast, bandwidth-light, zero data
               movement.

The simulator is fully deterministic and side-effect free — it does NOT call
any network. The LLM call is a separate concern handled in src/agent.py and
gated by the cache-first pattern.
"""
from __future__ import annotations

from pathlib import Path
import json

DATA_DIR = Path(__file__).resolve().parents[1] / "data"

# Reasonable, citation-able estimates
INFERENCE_PAYLOAD_MB = 10        # model delta + tokenizer + query, per node
ANSWER_PAYLOAD_KB    = 35        # per-node textual answer back to the gateway
GATEWAY_COMPOSE_KB   = 80        # final composed answer back to the operator
MIN_RTT_MS           = 40        # control-plane RTT floor


def _gb_to_bits(gb: float) -> float:
    return gb * (1024 ** 3) * 8


def _mb_to_bits(mb: float) -> float:
    return mb * (1024 ** 2) * 8


def _kb_to_bits(kb: float) -> float:
    return kb * 1024 * 8


def _xfer_seconds(payload_bits: float, link_mbps: float) -> float:
    """Wall-clock seconds to push `payload_bits` over `link_mbps`."""
    return payload_bits / max(1.0, link_mbps * 1_000_000)


def load_nodes() -> list[dict]:
    p = DATA_DIR / "nodes.json"
    return json.loads(p.read_text()) if p.exists() else []


def load_queries() -> list[dict]:
    p = DATA_DIR / "queries.json"
    return json.loads(p.read_text()) if p.exists() else []


def load_corpus(node_id: str) -> list[dict]:
    p = DATA_DIR / "mock_corpora" / f"{node_id}.jsonl"
    if not p.exists():
        return []
    return [json.loads(line) for line in p.read_text().splitlines() if line.strip()]


def naive_trace(query: dict, nodes: list[dict]) -> dict:
    """Pull every byte of every involved node into a central embedder + LLM."""
    involved = [n for n in nodes if n["id"] in query.get("involves", [n["id"] for n in nodes])]
    steps: list[dict] = []
    total_bits = 0.0
    total_seconds = 0.0
    spillage_flags: list[str] = []
    for n in involved:
        bits = _gb_to_bits(n["data_size_gb"])
        secs = _xfer_seconds(bits, n["bandwidth_mbps"])
        total_bits += bits
        total_seconds += secs
        spill = "ICD 503" in (n.get("compliance_authority") or "") or \
                "CUI" in (n.get("security_posture") or "")
        if spill:
            spillage_flags.append(
                f"DCSA SPILLAGE RISK: {n['label']} corpus copied out of "
                f"{n['security_posture']} enclave."
            )
        steps.append({
            "node":      n["id"],
            "label":     n["label"],
            "direction": "out",
            "kind":      "DATA",
            "bytes":     int(bits / 8),
            "seconds":   round(secs, 2),
            "note":      f"Pull {n['data_size_gb']:.0f} GB of "
                         f"{n['data_kind']} over {n['bandwidth_mbps']} Mbps link",
        })
    # Plus the central embedder write + query roundtrip (negligible vs above)
    central_overhead_bits = _kb_to_bits(GATEWAY_COMPOSE_KB)
    central_overhead_seconds = MIN_RTT_MS / 1000
    total_bits += central_overhead_bits
    total_seconds += central_overhead_seconds
    steps.append({
        "node":      "central",
        "label":     "Central embedder + LLM cluster",
        "direction": "in",
        "kind":      "ANSWER",
        "bytes":     int(central_overhead_bits / 8),
        "seconds":   round(central_overhead_seconds, 3),
        "note":      "Composed answer back to operator.",
    })
    return {
        "mode":           "naive",
        "label":          "Naive central RAG",
        "steps":          steps,
        "bytes":          int(total_bits / 8),
        "seconds":        round(total_seconds, 1),
        "compliance":     ("RED — UNCLASSIFIED bandwidth class. "
                           "DCSA spillage risk on CUI/ICD-503 nodes."),
        "spillage_flags": spillage_flags,
    }


def dde_trace(query: dict, nodes: list[dict]) -> dict:
    """Push compute (model + query) into each node; only answers come back."""
    involved = [n for n in nodes if n["id"] in query.get("involves", [n["id"] for n in nodes])]
    steps: list[dict] = []
    total_bits = 0.0
    # All nodes run in parallel — wall-clock is the slowest leg
    longest_seconds = 0.0
    for n in involved:
        # 1) Inbound compute payload (small)
        in_bits = _mb_to_bits(INFERENCE_PAYLOAD_MB)
        in_secs = _xfer_seconds(in_bits, n["bandwidth_mbps"])
        # 2) On-node inference time (modeled — not transferred)
        inference_secs = 0.8
        # 3) Outbound answer text (tiny)
        out_bits = _kb_to_bits(ANSWER_PAYLOAD_KB)
        out_secs = _xfer_seconds(out_bits, n["bandwidth_mbps"])
        node_secs = in_secs + inference_secs + out_secs
        longest_seconds = max(longest_seconds, node_secs)
        total_bits += in_bits + out_bits
        steps.append({
            "node":      n["id"],
            "label":     n["label"],
            "direction": "in",
            "kind":      "COMPUTE",
            "bytes":     int(in_bits / 8),
            "seconds":   round(in_secs, 3),
            "note":      f"Spawn DDE inference container at {n['node_endpoint']} "
                         f"(model weights + query, ~{INFERENCE_PAYLOAD_MB} MB).",
        })
        steps.append({
            "node":      n["id"],
            "label":     n["label"],
            "direction": "out",
            "kind":      "ANSWER",
            "bytes":     int(out_bits / 8),
            "seconds":   round(out_secs, 3),
            "note":      f"Per-node answer ({ANSWER_PAYLOAD_KB} KB) back to gateway. "
                         f"Data stayed inside {n['security_posture']}.",
        })
    # Gateway compose cost
    compose_bits = _kb_to_bits(GATEWAY_COMPOSE_KB)
    longest_seconds += MIN_RTT_MS / 1000
    total_bits += compose_bits
    steps.append({
        "node":      "gateway",
        "label":     "Kamiwaza Model Gateway",
        "direction": "out",
        "kind":      "COMPOSED",
        "bytes":     int(compose_bits / 8),
        "seconds":   round(MIN_RTT_MS / 1000, 3),
        "note":      "Federated answer composed and returned to operator.",
    })
    return {
        "mode":           "dde",
        "label":          "Kamiwaza Distributed Data Engine",
        "steps":          steps,
        "bytes":          int(total_bits / 8),
        "seconds":        round(longest_seconds, 2),
        "compliance":     ("GREEN — Compute-at-data. Zero data egress. "
                           "ICD 503 / DCSA boundary preserved."),
        "spillage_flags": [],
    }


def simulate_execution(query: dict, nodes: list[dict]) -> dict:
    """Return both traces side-by-side, plus a savings summary."""
    naive = naive_trace(query, nodes)
    dde   = dde_trace(query, nodes)
    return {
        "query_id":      query["id"],
        "naive":         naive,
        "dde":           dde,
        "savings": {
            "bytes_ratio":     round(max(1, naive["bytes"]) / max(1, dde["bytes"]), 1),
            "seconds_ratio":   round(max(0.001, naive["seconds"])
                                     / max(0.001, dde["seconds"]), 1),
            "bytes_saved":     naive["bytes"] - dde["bytes"],
            "seconds_saved":   round(naive["seconds"] - dde["seconds"], 1),
        },
    }


def humanize_bytes(b: int | float) -> str:
    b = float(b)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if b < 1024 or unit == "TB":
            return f"{b:,.1f} {unit}"
        b /= 1024
    return f"{b:.1f} PB"


def humanize_seconds(s: float) -> str:
    if s < 1:
        return f"{s * 1000:,.0f} ms"
    if s < 90:
        return f"{s:,.1f} s"
    if s < 3600:
        return f"{s / 60:,.1f} min"
    return f"{s / 3600:,.1f} hr"
