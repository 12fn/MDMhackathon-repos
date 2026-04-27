# STRIDER — off-road terrain GO/NO-GO matrix per vehicle class

One image of dirt, mud, water, or rock in; a per-vehicle green/amber/red
trafficability call out — with the binding constraint named in plain English.

Part of the [MDM 2026 Hackathon Templates](https://github.com/12fn/MDMhackathon-repos)
(template #07 of 14). Built on [Kamiwaza](https://www.kamiwaza.ai/).

## What it does

- **Vision call** — multimodal LLM turns a terrain frame into structured terrain JSON (`cover_type`, `slope_estimate_pct`, `water_depth_in_est`, `obstacles[]`, `surface_firmness`, `confidence`, …).
- **Reasoner** cross-references the terrain JSON against a fleet spec table (ground clearance, fording depth, max grade, side slope) and emits a GO / CAUTION / NO-GO row per vehicle.
- **Streaming radio-voice convoy brief** — calm, terse narrator paragraph for the convoy commander ("ALPV: GO. JLTV: GO with caution. ATT-EV: NO-GO due to soft sand.").
- **Per-vehicle binding constraint** is named in plain English on every row, so the operator sees *why* a vehicle was scrubbed, not just *that* it was.

## Demo video

[`videos/strider-demo.mp4`](videos/strider-demo.mp4)

## Quick start

```bash
# 1. Configure your provider (Kamiwaza on-prem, or any OpenAI-compatible endpoint)
export KAMIWAZA_BASE_URL=https://kamiwaza.local/api/v1
export KAMIWAZA_API_KEY=...
# (or set OPENAI_API_KEY for cloud dev)

# 2. Install + run
pip install -r requirements.txt
python data/generate.py            # writes vehicle_specs.csv + 6 sample images
python src/app.py                  # http://localhost:3007
```

## What's inside

```
07-strider-goose-offroad-terrain/
├── README.md
├── requirements.txt
├── .env.example
├── data/
│   ├── generate.py                synthetic GOOSE-style swatches + fleet spec CSV
│   └── vehicle_specs.csv          (generated)
├── sample_images/                 6 procedural terrain swatches
├── src/
│   └── app.py                     Gradio app (port 3007)
└── videos/
    └── strider-demo.mp4
```

## Hero AI move

Three coordinated LLM calls, all routed through the shared multi-provider client:

1. **Vision JSON** — `gpt-4o`-style multimodal call returns a strict-schema terrain report.
2. **Reasoner cross-ref** — second call ingests the terrain JSON + fleet spec table and emits a structured per-vehicle matrix with the binding constraint named.
3. **Streaming narrator** — third call streams a radio-voice convoy brief token-by-token into the UI.

The vision model is pinned to `gpt-4o` (the API string is forwarded verbatim — Kamiwaza, OpenRouter, etc. map it to whatever multimodal weights you have deployed). Reasoner + narrator use the shared client's default model chain.

## Plug in real data (Bucket B)

This template is **drop-frames-and-go**. Replace the synthetic swatches with anything:

- Real [GOOSE — German Outdoor and Offroad Dataset](https://goose-dataset.de) frames (50 GB labelled off-road semantic segmentation, free academic).
- Forward-rover dashcam stills, ISR captures, drone frames, phone photos.
- Just drop new `.jpg` / `.png` files into `data/terrain/` or `sample_images/` — the dropdown picks them up on app restart.

The vision call returns the same structured terrain JSON regardless of source, so the reasoner + narrator pipeline downstream needs zero changes.

## Adapt

- **Swap the fleet spec table** — edit `data/generate.py` (or hand-author `data/vehicle_specs.csv`) with your own vehicles, ground clearances, fording depths, max grades.
- **Change firmness / depth thresholds** — edit the rule list in `MATRIX_SYSTEM` inside `src/app.py` (e.g., raise the soft-surface clearance cutoff, tune the side-slope CAUTION-vs-NO-GO gap).
- **Tune the narrator persona** — edit the `stream_narrator` system prompt in `src/app.py` (radio-voice convoy brief → SITREP, CONOPS paragraph, civilian-friendly summary, etc.).
- **Different cover types** — extend the `cover_type` enum in `TERRAIN_SCHEMA` (snow, ice, urban-rubble, …).

## Built on Kamiwaza

All inference routes through the shared multi-provider client (`shared/kamiwaza_client.py` at the repo root). Set `KAMIWAZA_BASE_URL` and the same code runs on-prem on a Kamiwaza Inference Mesh; nothing leaves the accredited environment. See [ATTRIBUTION.md](../ATTRIBUTION.md) for full credits.
