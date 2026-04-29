# CAT-ROUTER — Kamiwaza Model Catalog Routing

> "Five LLM tasks, five different best models — Kamiwaza picks them automatically."

CAT-ROUTER is a USMC LOGCOM 2026 hackathon demo of the Kamiwaza-specific
**Model Catalog** routing feature. A Marine analyst submits a multi-task
workflow; CAT-ROUTER reads the catalog, applies hard constraints (vision,
tool-calling, SCAR posture, context window), scores every model on a weighted
quality / speed / cost / fit composite, and returns the optimal pick per task
with an explainable, operator-grade rationale.

## Hero AI move

A 5-task workflow ("Daily intel brief on the Bashi Channel") routes across
five different Kamiwaza-deployed models — auto-picked per task:

| Task | Routed model | Why |
|---|---|---|
| Vision (4 ISR photos) | **Qwen2.5-VL-72B** @ Quantico | only vision-capable model in catalog at IL5 |
| Fast classification (200 ASAM events) | **Llama-3.1-8B** @ edge MEU pod | sub-200ms first-token, $0.0001/1k cheap |
| Long-context synthesis (50K tokens) | **Qwen2.5-72B** | 128k context + 0.93 quality |
| Tool-calling (3 functions) | **Llama-3.3-70B** | best tool-calling support |
| Hero narrative (SIPR brief) | **Mixtral-8x22B** | best long-form prose |

Toggle **Fast/Cheap** mode → catalog re-routes all non-vision tasks to
Llama-3.1-8B. Cost falls ~80%; average quality drops ~12%. Operator sees the
trade-off live, per task, with a hash-chained audit of every routing decision.

## Run

```bash
streamlit run src/app.py \
  --server.port 3052 \
  --server.headless true \
  --server.runOnSave false \
  --server.fileWatcherType none \
  --browser.gatherUsageStats false
```

Open <http://127.0.0.1:3052>.

## Real-data plug-in

The synthetic catalog at `data/model_catalog.json` mimics what Kamiwaza's
catalog API returns on a live deployment. To swap in a live Kamiwaza Model
Gateway:

```bash
export KAMIWAZA_BASE_URL=https://kamiwaza.local/api/v1
export KAMIWAZA_API_KEY=<token>
python data/load_real.py    # writes a fresh model_catalog.json from /v1/catalog/models
```

`data/load_real.py` queries the OpenAI-compatible `/v1/models` endpoint plus
the Kamiwaza `/v1/catalog/models` extension and emits a record set with the
exact same shape the router expects — so `src/router.py` runs unchanged.

## Project layout

```
apps/52-cat-router/
├── README.md
├── PRD.md
├── data/
│   ├── model_catalog.json     # 8-model catalog (synthetic)
│   ├── task_taxonomy.json     # 12 task types + routing requirements
│   ├── demo_workflow.json     # 4 workflows, 5 tasks each
│   ├── cached_briefs.json     # pre-warmed routing decisions for both modes
│   ├── routing_audit.jsonl    # append-only hash chain (created on first run)
│   ├── generate.py            # pre-compute briefs (cache-first)
│   └── load_real.py           # real-Kamiwaza catalog plug-in
├── src/
│   ├── app.py                 # Streamlit entrypoint
│   └── router.py              # routing engine + audit chain
├── tests/record-demo.spec.ts
├── playwright.config.ts
├── package.json
├── requirements.txt
├── demo-script.md / .json
├── videos/cat-router-demo.mp4
└── STATUS.txt
```

## Scoring tie-back

- **Mission Impact (30%)** — Marine analysts need to compose intel briefs
  using whatever model fits each subtask; the catalog removes the "always
  use the biggest model" tax that wastes GPU hours on the edge.
- **Technical Innovation (25%)** — explainable per-task model selection
  across an 8-model heterogeneous fleet, hash-chained audit of every
  routing decision, single-toggle fast/cheap reroute.
- **Usability & Design (20%)** — Kamiwaza dark theme, one-glance catalog
  card grid, per-task rationale strings written in operator voice.
- **Security & Sustainability (15%)** — every model carries a SCAR grade
  (IL4/IL5/IL6) and hardware-home string; routing respects the floor.
  KAMIWAZA env-var swap to on-prem documented and demonstrated.
- **Team Collaboration (10%)** — modular router, full real-data swap recipe,
  reproducible synth, captioned demo video.
