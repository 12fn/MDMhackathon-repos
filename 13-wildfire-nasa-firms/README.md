# WILDFIRE

**Installation wildfire predictor + auto-MASCAL comms package.**

From a NASA satellite ping to a base-wide evacuation order in 90 seconds. Template
#13 of 14 in the [MDM 2026 Hackathon Templates](https://github.com/12fn/MDMhackathon-repos).

## What it does

- **Ingests NASA FIRMS thermal-anomaly fire pixels** (lat/lon, brightness, FRP, satellite, acq time).
- **Distance-ladder ranges every installation** CLEAR -> WATCH (50 mi) -> ALERT (25 mi) -> WARNING (10 mi).
- **Wind-projected priority score** boosts fires that are blowing toward the base, even if they're farther out.
- **One JSON-mode LLM call** emits a complete 4-channel MASCAL package: MARFORRES email, intranet banner, commander SMS, evacuation brief.

## Demo video

[`videos/wildfire-demo.mp4`](videos/wildfire-demo.mp4)

## Quick start

Set Kamiwaza env vars (or any provider — the shared client auto-detects):

```bash
export KAMIWAZA_BASE_URL=https://kamiwaza.local/api/v1
export KAMIWAZA_API_KEY=...
# or fall back to: OPENAI_API_KEY / ANTHROPIC_API_KEY / etc.
```

Launch backend + frontend:

```bash
pip install -r requirements.txt
uvicorn src.api:app --port 8013 &
streamlit run src/app.py --server.port 3013
```

Open http://localhost:3013.

## What's inside

```
13-wildfire-nasa-firms/
  README.md
  requirements.txt
  .env.example
  data/
    generate.py            # synthetic 200-pixel FIRMS-shape generator + wind grid
    fire_pixels.json       # 200 synthetic pixels (seed 1776)
    fire_pixels_firms.csv  # same data in NASA FIRMS CSV shape
    wind_grid.csv          # sparse wind vector grid
    installations.json     # 5 installation polygons + inventory
    timeline.json          # 13-step burn-growth replay
  src/
    app.py                 # Streamlit frontend (port 3013)
    api.py                 # FastAPI backend (port 8013)
    risk.py                # distance + wind-projected risk scoring
    comms.py               # 4-channel MASCAL comms generator (hero call)
  videos/
    wildfire-demo.mp4
```

## Hero AI move

One structured-output JSON-mode call -> a complete 4-channel MASCAL package:

- **Formal MARFORRES email** (BLUF / situation / actions / EEIs / signature, 250-400 words)
- **Base intranet banner** (RED/AMBER/YELLOW, imperative voice, 30-50 words)
- **Commander SMS** (<= 160 chars with lat/lon + nearest road)
- **Evacuation brief** (6-10 verb-led bullets citing real evacuation routes and assembly areas from the installation record)

The model is instructed in Marine Corps register (BLUF, CCIR, EEFI), grounded with the
exact threat block and wind summary, and forced to nest into a strict schema so the
UI can render each channel into its own tab.

## Plug in real data

This is a **Bucket A** template — the data shape is real, the values are synthetic. Swap in live FIRMS data:

1. Get a free MAP_KEY from https://firms.modaps.eosdis.nasa.gov/api/map_key/
2. Pull a CSV from the FIRMS Area or Country API.
3. Drop it in `data/` and update the path constant in `src/api.py`.

Required columns (FIRMS NRT CSV native shape):
`latitude, longitude, brightness, acq_date, acq_time, frp, confidence, satellite`

## Adapt

- **Swap the installation list** — edit `data/installations.json` (polygon, centroid, personnel, evacuation_routes, assembly_areas).
- **Change the distance ladder thresholds** — `src/risk.py` (defaults: 50 / 25 / 10 mi).
- **Customize MASCAL templates for your unit** — `src/comms.py` `SYSTEM_PROMPT` + `JSON_SCHEMA_HINT` (subjects, recipient lists, tone, EOC phone).

## Built on Kamiwaza

All LLM calls route through the shared multi-provider client
(`shared/kamiwaza_client.py`) — Kamiwaza-deployed models inside your accredited
environment, with OpenAI / Anthropic / Azure / vLLM as fallbacks. See
[ATTRIBUTION.md](../ATTRIBUTION.md).

MIT licensed.
