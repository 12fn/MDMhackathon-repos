# FED-RAG — Federated RAG via the Kamiwaza Distributed Data Engine

> **Codename:** FED-RAG &nbsp;-&nbsp; **Port:** 3050 &nbsp;-&nbsp; **Stack:** Streamlit + NetworkX + Plotly + per-silo numpy embedding indexes

Federated retrieval across data silos that **cannot legally or technically be merged.** Each silo runs its own local Kamiwaza Inference Mesh node, embeds the planner's encrypted query against its **own** local index, and returns only the top-K snippets + provenance. Raw silo data never moves. A central node composes one synthesis brief grounded in all 3 silos and cites every fact back to its silo of origin.

---

## The hero AI move

A MARFORPAC G-4 planner asks: **"How should I sustain the 31st MEU at Itbayat through D+30?"**

Three locked silos light up in parallel:

| Silo | Holder | Authority | Raw data |
|---|---|---|---|
| **Albany** — GCSS-MC depot inventory | DLA / MCLB Albany Maintenance Center | DLA Manual 4140.27 | 50 GB (never moves) |
| **Pendleton** — 31st MEU LCE TM library | 31st MEU Logistics Combat Element | DoDM 5200.01 Vol 2 | 12 GB (never moves) |
| **Philly** — DLA Class VIII medical | DLA Troop Support Medical | DLA Manual 4140.27 | 30 GB (never moves) |

Each silo cosine-retrieves locally against its **own** `silos/<name>/embeddings.npy`. The wire only carries:

- **In:** the encrypted planner query (~3 KB)
- **Out:** ~5 KB of retrieved snippets per silo

The central Kamiwaza node composes one Federated Sustainment Brief with explicit per-silo citations:

> *"Class IX availability: Albany GCSS-MC chunk #44 ... TM 9-2320-387-23 §3.1: Pendleton TM library chunk #12 ... Class VIII insulin shelf life: DLA Philly chunk #89..."*

A side-by-side panel shows what naive central RAG would have moved instead: **92 GB across the wire** -> compliance violation + DDIL bandwidth disaster.

---

## Why this is the differentiator

This app is the **only** end-to-end demonstration in the hackathon of the Kamiwaza **Distributed Data Engine (DDE)** doing what it was built to do: federated retrieval where the data physically and legally cannot be merged. Every other RAG app in the catalog assumes one centralized index. FED-RAG is built around three.

The federation is **real, not visual**:

- 3 separate `silos/<name>/embeddings.npy` files on disk — each loaded by its own `SiloNode`
- 3 independent cosine-retrieval calls, no cross-silo data sharing in the retrieval path
- Per-silo provenance attribution in the synthesis brief
- Append-only network audit log (`audit/network_traffic.jsonl`) capturing every cross-silo packet (size + content type)
- Per-silo Kamiwaza Inference Mesh endpoints wired through `KAMIWAZA_SILO_<NAME>_URL` env-vars

---

## Run

```bash
# 1. Generate per-silo corpora + embeddings + cached briefs (one-time, ~30s)
python data/generate.py --embed

# 2. Launch the Streamlit app on port 3050
streamlit run src/app.py \
  --server.port 3050 \
  --server.headless true \
  --server.runOnSave false \
  --server.fileWatcherType none \
  --browser.gatherUsageStats false
```

Open <http://127.0.0.1:3050>.

Three demo planner queries are pre-loaded and cache-served. Click **Regenerate** to fire a live federated synthesis with the 35 s watchdog.

---

## Real-data plug-in

`data/load_real.py` documents the per-silo ingestion path. Each silo has its own loader and env-var:

| Silo | Env var | Source |
|---|---|---|
| Albany | `REAL_ALBANY_PATH` + `KAMIWAZA_SILO_ALBANY_URL` | GCSS-MC export (NIPR, Distribution D) |
| Pendleton | `REAL_PENDLETON_PATH` + `KAMIWAZA_SILO_PENDLETON_URL` | TM PCN repository on Pendleton MIMMS |
| Philly | `REAL_PHILLY_PATH` + `KAMIWAZA_SILO_PHILLY_URL` | EMALL / DMLSS Class VIII catalog |

After loading, re-run `python data/generate.py --embed --briefs-only` to rebuild per-silo indexes and cached briefs.

---

## Compliance authorities cited

- **DLA Manual 4140.27** — distribution and custody of materiel records (Albany + Philly silos)
- **DoDM 5200.01 Vol 2** — data spillage prevention across enclaves (Pendleton silo)
- **DDIL / EMCON** — disconnected, intermittent, low-bandwidth ops (the federation justification)

---

## Files

- `src/app.py` — Streamlit UI (port 3050); network diagram, per-silo cards, audit log, naive-central comparison, hero brief
- `src/federation.py` — `SiloNode`, `federated_query()`, `hero_brief()` with watchdog + baseline fallback, audit logging
- `data/generate.py` — synthesizes per-silo corpora, embeds each silo independently, pre-computes cached briefs
- `data/load_real.py` — per-silo real-data ingestion stubs
- `data/cached_briefs.json` — 4 pre-computed federated briefs (cache-first)
- `silos/<name>/embeddings.npy` — per-silo local embedding indexes (proves federation is real)
- `silos/<name>/corpus.jsonl` — per-silo chunks
- `silos/<name>/manifest.json` — silo identity + classification + authority
- `audit/network_traffic.jsonl` — append-only cross-silo packet log
- `tests/record-demo.spec.ts` — Playwright walkthrough recorder
- `videos/fedrag-demo.mp4` — captioned demo

---

*Powered by Kamiwaza. Orchestration Without Migration. Execution Without Compromise.*
