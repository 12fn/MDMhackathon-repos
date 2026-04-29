# MESH-INFER — Distributed Inference Mesh

> *"One query. Four sensitivities. Four right answers."*

A Kamiwaza Inference Mesh visualizer: routes each step of a multi-step Marine
planner query to the right node (edge / rear depot / SCIF) based on **task
profile** + **data sensitivity**, then proves it with a hash-chained audit log
and a side-by-side cloud-leak comparison.

## What it shows
- **4-node mesh**: Edge (Jetson Orin, Qwen2.5-VL-7B) · Rear depot (Lambda DGX,
  Llama 3.3 70B FP8 via vLLM tensor-parallel) · SCIF (Mixtral 8x22B) · SCIF
  (Qwen2.5-VL — for classified imagery).
- **Per-step routing decision** with rationale ("step 3 needs SECRET drafting →
  routed to SCIF Mixtral; bandwidth out = 0").
- **Live latency / bandwidth / sensitivity** counters per step.
- **Side-by-side commercial-cloud panel** — same query, single endpoint, all
  data egresses, classified content leaks.
- **Hash-chained audit log** — SJA can prove no SCIF data ever crossed the
  airgap.
- **KAMIWAZA env-var beat** — per-node endpoint swap pattern shown verbatim.

## Run

```bash
cd apps/49-mesh-infer
pip install -r requirements.txt
python data/generate.py            # synth + cache pre-computed briefs
streamlit run src/app.py \
  --server.port 3049 \
  --server.headless true \
  --server.runOnSave false \
  --server.fileWatcherType none \
  --browser.gatherUsageStats false
```

Open http://localhost:3049

## Hero AI move

Pick a scenario (default: *threat-vessel intent + SIPR cable + HUMINT tip*) and
hit **Route through the Mesh**. The 4-node graph lights up step-by-step, each
step with:

- which node served it
- which model deployed (Qwen2.5-VL-7B / Llama 3.3 70B FP8 / Mixtral 8x22B)
- latency (sub-second at edge → 25 s in the SCIF)
- bandwidth (low at edge / mid at rear / **0 in the SCIF — airgapped**)
- sensitivity tag (UNCLASS / CUI / SECRET / TS-SCI)
- routing rationale (why this node, not the others)

Then compare to the **commercial-cloud equivalent** panel: one endpoint, full
egress, all classifications collapsed to "send everything to OpenAI".

## Real-data plug-in

`data/load_real.py` documents how to point each "node" at a real Kamiwaza
endpoint via per-node env vars:

```bash
export KAMIWAZA_EDGE_URL=https://edge.meu-soc.local/api/v1
export KAMIWAZA_EDGE_API_KEY=<edge-key>
export KAMIWAZA_REAR_URL=https://depot.quantico.usmc.mil/api/v1
export KAMIWAZA_REAR_API_KEY=<rear-key>
export KAMIWAZA_SCIF_URL=https://scif.marforpac.smil.mil/api/v1
export KAMIWAZA_SCIF_API_KEY=<scif-key>
```

The router reads these and dispatches each step to the right node. Until
those env vars are set, MESH-INFER simulates routing locally via the shared
`kamiwaza_client`.

## Why this is Kamiwaza-only

- **Inference Mesh** routes by data locality + security context — a
  Kamiwaza-native primitive (see `KAMIWAZA_BRIEF.md`).
- **No data movement** — SCIF steps physically cannot leave the SCIF.
- **Hardware-agnostic** — Jetson Orin at the edge, DGX at the depot, whatever
  the SCIF has behind JWICS.
- **OpenAI-compatible per-node surface** — every node still presents
  `/v1/chat/completions`, so existing tooling drops in.

A commercial-cloud LLM endpoint cannot demo this — by design.

## Files

```
apps/49-mesh-infer/
├── README.md              # this file
├── PRD.md                 # spec + scoring tie-back
├── STATUS.txt             # done
├── requirements.txt
├── .env.example
├── package.json
├── playwright.config.ts
├── demo-script.md
├── demo-script.json
├── data/
│   ├── generate.py
│   ├── load_real.py
│   ├── node_catalog.json
│   ├── task_profiles.json
│   ├── sensitivity_taxonomy.json
│   ├── demo_scenarios.json
│   ├── routing_audit.jsonl
│   └── cached_briefs.json
├── src/
│   ├── app.py
│   ├── mesh.py
│   ├── router.py
│   ├── audit.py
│   └── graph.py
├── tests/record-demo.spec.ts
└── videos/mesh-infer-demo.mp4
```

Powered by Kamiwaza.
