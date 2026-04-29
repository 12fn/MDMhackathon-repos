"""Real-Kamiwaza plug-in for MESH-INFER.

The simulated 4-node mesh shipped in `data/node_catalog.json` is a stand-in
for a real Kamiwaza Inference Mesh deployment. To swap each "node" for a real
Kamiwaza-deployed endpoint, set the per-node env vars below and the router in
`src/router.py` will dispatch to them automatically.

Required env vars (per node):

    # Edge node — Jetson Orin at MEU SOC. Vision + low-latency / DDIL-friendly.
    KAMIWAZA_EDGE_URL=https://edge.meu-soc.local/api/v1
    KAMIWAZA_EDGE_API_KEY=<edge-key>
    KAMIWAZA_EDGE_MODEL=qwen2.5-vl-7b

    # Rear depot — Lambda DGX H100 at MCB Quantico (vLLM tensor-parallel=8)
    KAMIWAZA_REAR_URL=https://depot.quantico.usmc.mil/api/v1
    KAMIWAZA_REAR_API_KEY=<rear-key>
    KAMIWAZA_REAR_MODEL=llama-3.3-70b-fp8

    # SCIF node — MARFORPAC HQ JWICS enclave (Mixtral 8x22B)
    KAMIWAZA_SCIF_URL=https://scif.marforpac.smil.mil/api/v1
    KAMIWAZA_SCIF_API_KEY=<scif-key>
    KAMIWAZA_SCIF_MODEL=mixtral-8x22b
    KAMIWAZA_SCIF_VL_MODEL=qwen2.5-vl-72b

The Kamiwaza endpoints expose an OpenAI-compatible REST surface at
`/v1/chat/completions`, so the router uses the same OpenAI Python SDK with a
per-node `base_url` swap. No per-node SDK or per-vendor adapter required.

If a per-node URL is unset, the router falls back to the shared
`shared.kamiwaza_client` (single-endpoint simulation) and the mesh is
visualized as if routing happened. That's how the demo runs out-of-box.

To prove the routing happens at the mesh layer (not in app code), inspect
`data/routing_audit.jsonl` after a run — every routing decision is logged
with the resolved endpoint, model, latency, egress bytes, and a chained
SHA-256 hash so the SJA can verify the chain end-to-end:

    tail -f data/routing_audit.jsonl | jq

Real-data ingest path for the mission inputs (thermal IR clips, AIS gaps,
HUMINT reports) goes through Kamiwaza's Distributed Data Engine (DDE) — the
data stays where it lives (no movement) and the router just resolves the
right node for each step.
"""
from __future__ import annotations

import os


def per_node_endpoints() -> dict:
    """Return resolved per-node endpoints from env. Empty string if unset."""
    return {
        "edge-meusoc": {
            "base_url": os.getenv("KAMIWAZA_EDGE_URL", ""),
            "api_key": os.getenv("KAMIWAZA_EDGE_API_KEY", ""),
            "model": os.getenv("KAMIWAZA_EDGE_MODEL", "qwen2.5-vl-7b"),
        },
        "rear-quantico": {
            "base_url": os.getenv("KAMIWAZA_REAR_URL", ""),
            "api_key": os.getenv("KAMIWAZA_REAR_API_KEY", ""),
            "model": os.getenv("KAMIWAZA_REAR_MODEL", "llama-3.3-70b-fp8"),
        },
        "scif-marforpac-mixtral": {
            "base_url": os.getenv("KAMIWAZA_SCIF_URL", ""),
            "api_key": os.getenv("KAMIWAZA_SCIF_API_KEY", ""),
            "model": os.getenv("KAMIWAZA_SCIF_MODEL", "mixtral-8x22b"),
        },
        "scif-marforpac-vl": {
            "base_url": os.getenv("KAMIWAZA_SCIF_URL", ""),
            "api_key": os.getenv("KAMIWAZA_SCIF_API_KEY", ""),
            "model": os.getenv("KAMIWAZA_SCIF_VL_MODEL", "qwen2.5-vl-72b"),
        },
    }


def is_live() -> bool:
    """True iff at least one per-node endpoint is configured for a live mesh."""
    return any(v["base_url"] for v in per_node_endpoints().values())


if __name__ == "__main__":
    eps = per_node_endpoints()
    for nid, cfg in eps.items():
        status = "LIVE" if cfg["base_url"] else "simulated"
        print(f"  {nid:<28} [{status}] model={cfg['model']} url={cfg['base_url'] or '—'}")
    print(f"\nMesh live: {is_live()}")
