# OPENGATE — Federal-Data Discovery RAG for Marine Analysts

> Production-shape RAG over the data.gov federal-dataset catalog.
> Built for the USMC LOGCOM AI Forum Hackathon (MDM 2026).

## Pitch

A Marine analyst spinning up an HA/DR cell, an OSINT prep, or a
contested-logistics study cannot keyword-search 300,000 federal datasets in a
decision window. **OPENGATE** collapses that workflow into a single
natural-language query against a five-stage RAG pipeline that understands
data.gov CKAN fields natively and writes an OPORD-adjacent **Analyst
Discovery Brief** the action officer can use.

## Hero AI move

Production-shape multi-stage RAG (the same pattern ANCHOR uses for the
World Port Index):

1. `chat_json` parses the analyst's free-text question into a structured
   filter object (agencies, topic keywords, date range, formats, regions).
2. Python applies the filter to the synthetic 200-dataset catalog -> candidate
   set.
3. `embed()` vectors over each abstract; numpy cosine-rerank against the
   query embedding -> top-K.
4. `chat_json` produces a structured per-dataset comparison row
   (`relevance_score`, `why_relevant`, `suggested_use`, `freshness_concern`).
5. Hero `chat` ("gpt-5.4", 35 s wall-clock watchdog, cache-first) writes the
   250-350 word **Analyst Discovery Brief** (BLUF, top 3 datasets, gaps,
   recommended next 24-hour action).

Hero call is wrapped in `ThreadPoolExecutor` with a 35 s watchdog; on
timeout we fall back to a deterministic `baseline_brief`. Three canonical
queries are pre-briefed at `data/generate.py` time and cached in
`data/cached_briefs.json` so the demo is snappy.

## Run

```bash
# Once: synthesize 200 datasets, embed every abstract, pre-compute briefs.
python data/generate.py --embed

# Then launch (port 3026, mono-page Streamlit):
streamlit run src/app.py \
  --server.port 3026 \
  --server.headless true \
  --server.runOnSave false \
  --server.fileWatcherType none \
  --browser.gatherUsageStats false
```

The shared client (`shared/kamiwaza_client.py`) auto-detects the active
provider from env vars in this order: `KAMIWAZA_BASE_URL` >
`OPENROUTER_API_KEY` > `LLM_BASE_URL` > `ANTHROPIC_API_KEY` >
`OPENAI_API_KEY`. OPENGATE needs embeddings; if you set `ANTHROPIC_API_KEY`,
also set `EMBEDDING_BASE_URL` + `EMBEDDING_API_KEY` (any OpenAI-compatible
endpoint).

## Real-data plug-in

`data/load_real.py` is a working CKAN ingester for
`https://catalog.data.gov/api/3/action/package_search` (300,000+ packages,
no auth). Output shape matches `data/generate.py` byte-for-byte, so
`src/rag.py` needs zero edits. After ingesting:

```bash
REAL_DATA_PATH=$(pwd)/data/datasets.json python data/load_real.py
python data/generate.py --embed --briefs-only
```

## Files

```
apps/26-opengate/
├── README.md                           # this file
├── PRD.md                              # spec + scoring tie-back
├── data/
│   ├── generate.py                     # synth + embed + brief precompute
│   ├── load_real.py                    # CKAN ingester (live data.gov)
│   ├── datasets.json                   # 200 synthetic federal datasets
│   ├── embeddings.npy                  # (200, 1536) cosine-normalized
│   ├── embedding_ids.json              # parallel dataset_id list
│   └── cached_briefs.json              # 3 pre-computed scenario briefs
├── src/
│   ├── app.py                          # Streamlit UI (port 3026)
│   └── rag.py                          # 5-stage RAG pipeline
├── tests/record-demo.spec.ts           # Playwright recorder
├── playwright.config.ts
├── demo-script.md                      # narrator script
├── demo-script.json                    # cue timeline
├── videos/opengate-demo.mp4            # captioned 90s demo
├── requirements.txt
├── .env.example
└── STATUS.txt
```

## Pick one tagline (visual variety)

> **300,000 federal datasets. Four-second answer.**

## Powered by Kamiwaza
