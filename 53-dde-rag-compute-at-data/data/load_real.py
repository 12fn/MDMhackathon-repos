"""Real-Kamiwaza DDE plug-in for DDE-RAG.

This stub documents how to point DDE-RAG at a real Kamiwaza Distributed Data
Engine deployment. The synthetic generator (`data/generate.py`) is shaped
exactly like the real path so the rest of the app does not change.

Real-data path:

  1. Deploy Kamiwaza Stack at each data-bearing site (Albany, Lejeune, Quantico).
     The Inference Mesh component schedules an inference container on each
     node, co-located with its native data store (CockroachDB / Milvus / file
     share). vLLM or llama.cpp serves the model on a private OpenAI-compatible
     surface.

  2. Register each node with the central Model Gateway. The gateway is the
     only egress point — operators talk to it; it federates queries.

  3. Set `KAMIWAZA_DDE_NODES` in the operator workstation env to a comma-
     separated list of `<host>:<port>` pairs in the order Albany, Lejeune,
     Quantico.

  4. Set `KAMIWAZA_BASE_URL` to the Model Gateway. The shared
     `shared.kamiwaza_client` will route compose / synthesis through it
     while the per-node retrieval stays at the data nodes.

ICD 503 / DCSA spillage:

  Each node's data NEVER leaves its accreditation boundary. The compute
  (model weights + query string) crosses the wire INTO the enclave; only the
  per-node textual answer crosses back OUT. The Quantico node is treated as
  CUI/FOUO — its egress is gated by the local DLP rule defined in
  `data/audit_logs/dde_audit.jsonl` (hash-chained).

Bandwidth math:

  Naive central RAG cost = sum(node.data_size_gb) * 8 (Gb) / shared_link_mbps
  DDE cost              = sum(model_weights_mb + query_kb) per node, parallel

Required environment:

  - KAMIWAZA_DDE_NODES=albany.gcssmc.usmc.mil:8443,lejeune.icm.usmc.mil:8443,quantico.tm.usmc.mil:8443
  - KAMIWAZA_BASE_URL=https://kamiwaza-gateway.local/api/v1   (optional)
  - KAMIWAZA_API_KEY=<token from Kamiwaza control plane>      (optional)
"""
from __future__ import annotations

import os


def load_real_nodes() -> list[dict]:
    """Parse KAMIWAZA_DDE_NODES into the same shape as data/nodes.json.

    Falls back to NotImplementedError so the synthetic data path remains the
    authoritative demo source unless the operator explicitly opts in.
    """
    raw = os.getenv("KAMIWAZA_DDE_NODES")
    if not raw:
        raise NotImplementedError(
            "KAMIWAZA_DDE_NODES not set. Synthetic nodes will be loaded from "
            "data/nodes.json. See module docstring for the real-deployment recipe."
        )
    parsed: list[dict] = []
    for i, ep in enumerate(raw.split(",")):
        ep = ep.strip()
        if not ep:
            continue
        host = ep.split(":", 1)[0]
        node_id = host.split(".", 1)[0].lower()
        parsed.append({
            "id": node_id,
            "label": host,
            "node_endpoint": ep,
            "compute_posture": "DDE inference container (real)",
            "_real": True,
        })
    return parsed
