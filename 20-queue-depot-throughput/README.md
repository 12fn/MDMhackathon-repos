# QUEUE — Depot Maintenance Throughput Optimizer

**App #20** | port **3020** | LOGCOM published use case
**Datasets (frame):** GCSS-MC Supply & Maintenance Data + Predictive Maintenance Data — synthetic stand-in.

> *AI-driven scheduling tool that optimizes induction sequencing, workforce allocation, and parts availability to increase monthly throughput on priority end items.*
> — verbatim from the LOGCOM AI Forum Hackathon use case portal

## What it does

Re-sequences ~80 inducted-or-pending end items (MTVR, AAV, LAV, MV-22, M1A1) across **MCLB Albany / Barstow / Blount Island Command** to maximize 30-day depot throughput. Two-layer pipeline:

1. **Classical scheduler** — greedy priority-weighted induction sequencer over (a) backlog with FD-1..4 priority + estimated labor hours, (b) per-depot bay/shift/skill capacity, (c) parts availability keyed by NSN with on-hand + ETA. Outputs a 30-day Plotly Gantt and per-depot bay/labor utilization.
2. **AI reasoning layer (hero)** — `chat_json` analyzes the schedule and emits `{bottleneck_resource, throughput_uplift_pct, mitigation_actions[], parts_at_risk[], alternative_sequences[]}`; `chat` then renders the **Depot Throughput Optimization Brief** — BLUF, named bottleneck (e.g. "Bay 4 hydraulic lift availability — MCLB Albany"), parts-availability cascading effects, top-5 actions to lift throughput by N% over the next 30 days. Cache-first per AGENT_BRIEF_V2 §A.

## Run

```bash
# from repo root
.venv/bin/python apps/20-queue/data/generate.py        # synth + precompute briefs
cd apps/20-queue
streamlit run src/app.py \
  --server.port 3020 \
  --server.headless true \
  --server.runOnSave false \
  --server.fileWatcherType none \
  --browser.gatherUsageStats false
```

Then visit http://localhost:3020.

## Hero AI move

- Multi-step pipeline: structured-output JSON analyst (`chat_json`) feeds an OPORD-grade narrative composer (`chat`).
- Hero call uses `gpt-5.4` (cap 35 s wall-clock); falls back to the standard chain on timeout, then to a deterministic OPORD-shaped brief so the demo never sits on a spinner.
- Three pre-computed scenario briefs ship in `data/cached_briefs.json` (baseline / surge / parts-constrained).

## Real-data plug-in

`data/load_real.py` documents the GCSS-MC ingest path. Set `QUEUE_REAL_DATA_DIR=/path/to/extracts` and the same code reads real backlog + parts + capacity tables. Set `KAMIWAZA_BASE_URL` and inference flips to a Kamiwaza-deployed model behind the wire.

## File map

```
apps/20-queue/
├── README.md                      # this file
├── PRD.md                         # spec + scoring tie-back
├── STATUS.txt                     # building | done
├── requirements.txt
├── .env.example
├── playwright.config.ts
├── demo-script.md                 # narrator hand-off
├── demo-script.json               # cue timeline (emitted by Playwright)
├── data/
│   ├── generate.py                # rerunnable synth + precompute_briefs()
│   ├── load_real.py               # GCSS-MC ingest stub
│   ├── backlog.csv                # 80 end items
│   ├── parts_availability.csv     # 15 NSNs
│   ├── depot_capacity.json        # 3 depots
│   ├── scenarios.json             # 3 demo scenarios
│   └── cached_briefs.json         # pre-computed hero briefs
├── src/
│   ├── app.py                     # Streamlit (port 3020)
│   ├── optimizer.py               # greedy priority-weighted scheduler
│   └── agent.py                   # 2-step AI reasoning layer
├── tests/record-demo.spec.ts      # Playwright recorder
└── videos/queue-demo.mp4          # captioned demo (≤90 s)
```

Built on the Kamiwaza Stack. Powered by Kamiwaza.
