# OPTIK — maintainer photo to TM citation, on-prem vision RAG

> Template #03 of 14 — MDM 2026 LOGCOM AI Forum Hackathon. Built on [Kamiwaza](https://www.kamiwaza.ai/).

A maintainer drops a phone photo of a broken thing. OPTIK identifies it, retrieves the right Technical Manual snippet, and narrates a maintainer-grade brief with TM number, NSNs, torque spec, and procedure. Pure vision RAG over a local TM corpus — no data leaves the wire.

## What it does

- **Take a photo** — drag-drop a field shot (or use webcam) into a single Gradio page.
- **Vision-detects equipment** — one multimodal call returns structured JSON: scene, primary subject, bboxes, search query.
- **Embeds + retrieves** — the search query is embedded and cosine-searched against an index of TM snippets; top-3 hits returned with citations.
- **Narrates a maintainer brief** — a senior-NCO-voice LLM call combines detection + retrieved snippets into a markdown brief (TM, action, NSNs, why it matters) and emits a parts JSON ready for GCSS-MC.

## Demo video

[`videos/optik-demo.mp4`](videos/optik-demo.mp4) — captioned end-to-end run.

## Quick start

```bash
# 1. Pick a provider (see DEPLOY.md). Kamiwaza on-prem is the headline path:
export KAMIWAZA_BASE_URL=https://kamiwaza.local/api/v1
export KAMIWAZA_API_KEY=...

# 2. Install + generate synthetic TM corpus + embedding index + sample images:
pip install -r requirements.txt
python data/generate.py --embed

# 3. Launch:
python src/app.py    # http://localhost:3003
```

Drag a sample image (or `placeholder_valve.jpg`), add an optional Marine's note, click **Identify + Retrieve TM**.

## Provider note — embeddings required

OPTIK needs **both** chat/vision **and** embeddings. Pick any of:

- **Kamiwaza** (recommended) — both surfaces on the same on-prem mesh.
- **OpenAI** — direct, fastest local-dev iteration.
- **OpenRouter** — cloud, multi-model.
- **Any OpenAI-compat endpoint** — Together, Groq, vLLM, Ollama, etc. (`LLM_BASE_URL` + `LLM_API_KEY`).
- **Anthropic** — works for chat/vision, **but has no native embeddings**. Also set:
  ```bash
  export EMBEDDING_BASE_URL=https://api.openai.com/v1
  export EMBEDDING_API_KEY=sk-...
  ```
  See repo-root [`DEPLOY.md`](../DEPLOY.md) for the full provider matrix.

## What's inside

```
03-optik-coco8-vision-tm/
├── README.md
├── requirements.txt
├── .env.example
├── src/
│   ├── app.py        # Gradio UI + orchestration
│   ├── vision.py     # multimodal detection -> structured JSON
│   └── rag.py        # numpy cosine search over embedded TM snippets
├── data/
│   ├── generate.py   # synthetic TM corpus + COCO8 sample fetch + embedding index
│   ├── tm_snippets.json
│   └── tm_index.npz  # 30 x N float32 embedding matrix
├── sample_images/    # 5 COCO8 photos + 1 generated placeholder
└── videos/optik-demo.mp4
```

## Hero AI move

One multimodal call → embed → cosine search → narrator brief, all behind a single auto-detecting client.

1. **Vision-language with `response_format=json_object`** — image + system prompt return a typed `{scene, primary_subject, detections[bbox+confidence+rationale], search_query}` record.
2. **Bbox quality logic** (`src/app.py::_normalize_bbox`) — rejects degenerate / near-full-frame / zero-area boxes; falls back to a demo bbox if the model returned nothing usable, so the overlay always renders.
3. **Embed + cosine RAG** — pure NumPy over a `(N, dim)` matrix; no Milvus, no FAISS — demo-grade, swap to a real vector DB at production scale.
4. **Maintainer-brief narrator** — second LLM call grounded in the retrieved snippets with a tight markdown schema (`ID / TM / Action / NSNs / Why it matters`).

## Plug in real data (Bucket B)

OPTIK is a [Bucket B template](../DATA_INGESTION.md#bucket-b--drop-files-in-a-folder-5-apps) — drop files in a folder.

```bash
# 1. Drop maintainer field photos into the samples directory:
mkdir -p data/samples
cp /path/to/your/photos/*.jpg data/samples/
# (or keep using sample_images/ — both are listed by the UI)

# 2. Replace the synthetic TM corpus with real excerpts:
#    edit data/tm_snippets.json — same schema (id, tm, vehicle, section,
#    component, primary_nsn, gasket_nsn, seal_nsn, echelon, class, fluid,
#    failure, figure, keywords, text)

# 3. Rebuild the embedding index:
python data/generate.py --embed
```

See [`DATA_INGESTION.md`](../DATA_INGESTION.md) at the repo root for the full Bucket B walkthrough across all five image-input templates.

## Adapt

- **Different equipment manuals** — swap the TM corpus for any structured maintenance text (aviation TMs, naval engineering manuals, civilian vehicle service bulletins). The RAG layer is schema-agnostic; only the narrator prompt mentions "USMC motor pool" — tune it in `src/app.py::NARRATIVE_SYSTEM`.
- **Different embedding model** — change the `model=` arg in `shared/kamiwaza_client.py::embed`, or set `LLM_PRIMARY_MODEL`. Kamiwaza maps server-side; OpenAI accepts `text-embedding-3-large` for higher quality.
- **Different maintainer workflows** — the Gradio layout in `src/app.py` is one file; replace the brief panel with a checklist, a parts cart, an MMS work-order draft, etc.

## Built on Kamiwaza

OPTIK is part of the MDM 2026 Hackathon Templates. Default provider is [Kamiwaza](https://www.kamiwaza.ai/) — OpenAI-compatible on-prem inference mesh. See [`ATTRIBUTION.md`](../ATTRIBUTION.md) for full credits and dataset provenance (COCO8 / Ultralytics).

MIT licensed.
