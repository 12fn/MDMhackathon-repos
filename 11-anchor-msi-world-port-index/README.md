# ANCHOR — agentic RAG port-capability assessor for MPF/BIC planners

Template #11 of 14 in the [MDM 2026 Hackathon Templates](https://github.com/12fn/MDMhackathon-repos).
Mission frame: Maritime Prepositioning Force (MPF) / Blount Island Command (BIC) port selection over the NGA MSI **World Port Index (WPI)**, Pub 150.

## What it does

- Planner types a natural-language question ("ports within 500 nm of Subic Bay that can offload a BIC-class T-AKR with 12 m channel depth").
- `chat_json` parses the question into a strict filter object (capability, geography, host-nation posture).
- Hard-filter pass over the corpus by capability + haversine geography to a candidate set.
- Embed candidates + query, cosine-rerank to top-K (cached embeddings under `data/embeddings.npy`).
- `chat_json` emits a structured comparison table; `chat` streams an OPORD-adjacent narrative recommendation (BLUF / Primary / Backup / Risk / Next Action).

## Demo video

[`videos/anchor-demo.mp4`](videos/anchor-demo.mp4)

## Quick start

```bash
cp .env.example .env       # fill in one provider (Kamiwaza / OpenAI / OpenRouter / Anthropic)
pip install -r requirements.txt
python data/generate.py    # rebuilds 250 synthetic ports → ports.json + ports.parquet
streamlit run src/app.py --server.port 3011
```

Open http://localhost:3011. First query takes ~10 s extra to build the embedding index; subsequent queries are ~4 s end-to-end.

## Provider note

ANCHOR is a RAG app — it needs **embeddings**. Use Kamiwaza, OpenAI, OpenRouter, or any OpenAI-compatible endpoint and you get both chat and embeddings out of the box. If you want to run **Anthropic** (Claude) for chat, also set `EMBEDDING_BASE_URL` + `EMBEDDING_API_KEY` to point embeddings at any OpenAI-compatible provider. See [`../DEPLOY.md`](../DEPLOY.md).

## What's inside

```
11-anchor-msi-world-port-index/
├── README.md
├── requirements.txt
├── .env.example
├── data/
│   ├── generate.py          # synthesizes 250 plausible WPI records (seed=1776)
│   ├── ports.json           # corpus
│   ├── ports.parquet
│   ├── embeddings.npy       # cached on first query
│   └── embedding_ids.json
├── src/
│   ├── rag.py               # parse → hard-filter → vector rerank → compare → narrate
│   └── app.py               # Streamlit UI (folium map + comparison + streamed narrative)
└── videos/
    └── anchor-demo.mp4
```

## Hero AI move

Production-shape two-stage RAG: **hard filter → vector rerank → structured comparison → streamed narrative**. The agent doesn't dump every port at the LLM — it parses the planner's intent into a JSON filter, narrows the candidate set deterministically, then uses cosine similarity to rerank and only the top-K records ever go into the comparison + narrative prompts. Same pattern that ships in real RAG products.

## Plug in real data (Bucket C — needs custom code)

The included corpus is a synthetic 250-port stand-in. To use the real NGA MSI WPI Pub 150:

1. Pull the WPI shapefile bundle from https://msi.nga.mil/Publications/WPI.
2. Write a loader using `geopandas` to read the shapefile, then map WPI fields to the schema in `data/generate.py` (berth depth, channel depth, crane count, fuel availability, RoRo capability, host-nation posture proxy).
3. Emit `data/ports.json` in the existing record shape and rebuild embeddings: `python -c "from src.rag import build_embeddings; build_embeddings(force=True)"`.
4. Zero changes required in `src/rag.py` or `src/app.py`.

## Adapt

- Swap the corpus for a different geo dataset (airfields, FOBs, casualty receiving facilities) — keep the JSON schema, the agent works as-is.
- Change the capability schema in `FILTER_SCHEMA_HINT` and `apply_filters` to match your domain.
- Retune the embedding model via `EMBEDDING_BASE_URL` / `text-embedding-3-large`.
- Add new RAG layers (BM25 hybrid retrieval, cross-encoder rerank, query expansion) between filter and rerank.

## Built on Kamiwaza

ANCHOR runs on a [Kamiwaza](https://www.kamiwaza.ai/)-deployed model by default — same code path against any OpenAI-compatible endpoint. See [`../ATTRIBUTION.md`](../ATTRIBUTION.md).
