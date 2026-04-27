# WATCHTOWER

> **Installation Common Operating Picture (I-COP) Aggregator**
> Seven disparate installation feeds, one cross-stream picture, one tab.

App #16 of the **USMC LOGCOM CDAO AI Forum Hackathon** at Modern Day Marine 2026.
Maps to the **published LOGCOM I-COP Aggregator** use case. Extends Installation
Incident Response (MARADMIN 131/26 Problem #3) from reactive to proactive.

## Powered by a Kamiwaza-deployed model

All LLM calls — the JSON-mode cross-stream correlator and the hero
Commander's I-COP Brief writer — route through a **Kamiwaza-deployed
model** running inside your accredited environment (set
`KAMIWAZA_BASE_URL`). The shared OpenAI-compatible client remains
available as a fallback for local development. Same model IDs, same
calls — flip the base URL and 100% of traffic stays on the wire.

## What it does

WATCHTOWER fuses seven installation data streams into a single dashboard
for the commander's watch officer:

| Stream | Shape | Real source |
|---|---|---|
| Gate ingress / egress | hourly per-gate counts | DBIDS |
| Utility readings | hourly water psi / power MW / fuel inv | DPW SCADA |
| Fire / EMS dispatches | per-call CAD | Tyler / Motorola CAD |
| Mass notification | per-broadcast severity + text | AtHoc / Giant Voice |
| Weather | hourly wind / temp / RH / precip | NASA Earthdata MERRA-2 |
| Maintenance status | per-asset FMC / PMC / NMC | GCSS-MC |
| Critical infrastructure | static asset overlay | HIFLD |

The hero AI move is **multi-stream anomaly correlation**: a `chat_json`
cross-stream correlator analyzes the 24h fused window and emits anomaly
cards naming every stream contributing evidence. A second hero call
(`gpt-5.4`, 35s timeout) writes the Commander's I-COP Brief.

| Layer | Tech |
|---|---|
| Map | Streamlit + folium + Leaflet |
| Backend | FastAPI on port 8016 |
| Frontend | Streamlit on port 3016 |
| LLM | Kamiwaza-deployed model (OpenAI-compat fallback) |
| Hero call | `chat` (gpt-5.4) for Commander's Brief; `chat_json` for correlator |

## Run it

```bash
cd apps/16-watchtower
pip install -r requirements.txt
python data/generate.py            # ~500 fused events + cached_briefs.json
# Backend (FastAPI) on 8016
python -m uvicorn src.api:app --port 8016 &
# Frontend (Streamlit) on 3016
streamlit run src/app.py \
  --server.port 3016 --server.headless true \
  --server.runOnSave false --server.fileWatcherType none \
  --browser.gatherUsageStats false
```

Open http://localhost:3016.

The Streamlit page opens to **Overview**. Click through to **Correlations**
to see the cross-stream anomaly cards (cache-first), and **Commander's Brief**
for the hero text. Toggle "Cache-first hero outputs" off in the sidebar to
fire the live LLM calls (timeout-bounded, deterministic fallback).

## Real dataset provenance

This demo runs on synthetic data shaped to match three real sources plus
four installation-local systems. To plug in real data, see
[`data/load_real.py`](data/load_real.py) — every stream has a loader stub
documenting the source URL, file format, env var, and required fields.

- **HIFLD** — https://hifld-geoplatform.opendata.arcgis.com/ (GeoJSON / shapefile)
- **NASA Earthdata** — https://earthdata.nasa.gov/ (MERRA-2 / GEOS-FP NetCDF4)
- **GCSS-MC** — Global Combat Support System – Marine Corps (CSV extract via LOGCOM)
- **DBIDS / DPW SCADA / CAD / AtHoc** — installation-local systems

## Files

```
apps/16-watchtower/
  PRD.md                    # spec, scoring tie-back
  README.md                 # this file
  requirements.txt
  .env.example
  data/
    generate.py             # rerunnable synthesizer (seed 1776) + precompute_briefs()
    load_real.py            # real-data ingestion stub (HIFLD / NASA / GCSS-MC / +)
    installations.json
    weather.json
    maintenance.json
    gate_events.json
    utility_events.json
    ems_events.json
    massnotify_events.json
    fused_timeline.json
    cached_briefs.json      # cache-first hero outputs
  src/
    app.py                  # Streamlit UI (frontend, port 3016)
    api.py                  # FastAPI backend (port 8016)
    correlator.py           # cross-stream correlator + brief writer
  tests/
    record-demo.spec.ts     # Playwright recorder
  playwright.config.ts
  package.json
  demo-script.md
  demo-script.json          # produced by Playwright at record time
  videos/watchtower-demo.mp4
  STATUS.txt
```

## Powered by Kamiwaza
