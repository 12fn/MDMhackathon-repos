# EMBER — combat-fire signature analytics + SIPR-style ASIB brief

App #14 of 14 in the [MDM 2026 Hackathon Templates](https://github.com/12fn/MDMhackathon-repos).
Reads NASA FIRMS active-fire pixels over a conflict zone, separates combat
burns from wildfires, and drafts a SIPR-style **All-Source Intelligence Brief
(ASIB)** the way an analyst would.

## What it does

- **DBSCAN spatiotemporal clustering** over (lat, lon, scaled-time) groups raw
  FIRMS fire pixels into discrete combustion events.
- **Per-cluster `chat_json` classification** labels each cluster as one of
  `combat_artillery`, `combat_armor`, `industrial`, `wildfire`, or `structure`,
  with a confidence and a one-line rationale tied to the feature vector.
- **Hero ASIB composer** generates a full markdown DAILY ALL-SOURCE
  INTELLIGENCE BRIEF (BLUF, observed activity, infrastructure events,
  collection recommendations, confidence statement) in seconds.
- **Deterministic heuristic baseline** ensures graceful degradation — every
  cluster gets a label even if the LLM endpoint is unreachable.

## Demo video

[`videos/ember-demo.mp4`](videos/ember-demo.mp4)

## Quick start

```bash
cp .env.example .env                 # set KAMIWAZA_BASE_URL + KAMIWAZA_API_KEY (or OPENAI_API_KEY as fallback)
pip install -r requirements.txt
python data/generate.py              # writes data/firms_ukraine.json (5,000 synthetic FIRMS pixels)
streamlit run src/app.py --server.port 3014
```

Open http://localhost:3014.

## What's inside

```
14-ember-firms-ukraine/
  README.md
  requirements.txt
  .env.example
  data/
    generate.py           # seeded FIRMS-shape synthesizer
    firms_ukraine.json    # 5,000 synthetic pixels, 24 months
  src/
    app.py                # Streamlit UI, Plotly map, time scrubber, brief button
    cluster.py            # DBSCAN + heuristic + LLM (chat_json) classifier
    brief.py              # Hero ASIB composer (chat free-form)
  videos/
    ember-demo.mp4        # captioned walkthrough
```

## Hero AI move

Three different AI moves stitched into one workflow:

1. **DBSCAN** unsupervised clustering reduces thousands of raw pixels to a
   handful of meaningful events.
2. **`chat_json` per-cluster classification** uses JSON-mode structured output
   to tag each cluster against a fixed taxonomy with confidence and rationale.
3. **Free-form `chat` ASIB generation** composes the daily brief in
   military-analyst voice using the classified clusters as evidence.

Each step has a deterministic fallback: heuristic classifier mirrors the LLM
taxonomy, and the brief degrades to a stats-only block if the hero call fails.

## Plug in real data

This template is **Bucket A** — synthetic data shaped exactly like the real
NASA FIRMS export, so swapping in a real download is a path change.

- **Source:** NASA FIRMS Country Archive — https://firms.modaps.eosdis.nasa.gov/country/
- **Coverage:** any country, any window up to 24 months, JSON / CSV.
- **Required columns:** `latitude, longitude, brightness, scan, track,
  acq_date, acq_time, satellite, confidence, frp` — schema-byte-compatible
  with the canonical FIRMS VIIRS / MODIS active-fire product.

Drop the file at `data/firms_ukraine.json` (or repoint `app.py`) and the
clustering, classification, and brief pipeline run unchanged.

## Adapt

- **Swap the AOI:** point `data/generate.py` (or your real FIRMS export) at any
  region — the geography is just lat/lon.
- **Tune DBSCAN:** edit `LAT_SCALE`, `LON_SCALE`, `TIME_HOURS_SCALE` and
  `eps / min_samples` in `src/cluster.py` to match your sensor cadence and
  expected event size.
- **Change the cluster classes:** edit the label list in `llm_classify` and
  `heuristic_classify` for your domain (e.g. `flare, gas_leak, controlled_burn`
  for an energy-infrastructure use case).
- **Modify the ASIB format:** rewrite the `PROMPT_TEMPLATE` in `src/brief.py`
  to match your unit's reporting requirements (CCIR, INTREP, SITREP, etc.).

## Built on Kamiwaza

All LLM calls route through `shared/kamiwaza_client.py`, which auto-detects
Kamiwaza / OpenAI / Anthropic / OpenRouter from environment variables. Same
code path for local development and accredited-enclave deployment.

See [ATTRIBUTION.md](../ATTRIBUTION.md) at the repo root for full
acknowledgements.
