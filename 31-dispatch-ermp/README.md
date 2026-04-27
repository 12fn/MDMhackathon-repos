# DISPATCH

> **Emergency Response Modernization Project** — installation 911 + CAD, AI-augmented.
> From "9-1-1, what is your emergency?" to units rolling in under 30 seconds.

App #31 of 34 for the **USMC LOGCOM CDAO AI Forum Hackathon** at Modern Day Marine 2026.
Maps verbatim to the LOGCOM-published **ERMP — Emergency Response Modernization Project**
use case (Installation Incident Response category).

## Powered by a Kamiwaza-deployed model

All LLM calls — primary triage and hero CAD entry — route through a
**Kamiwaza-deployed model** running inside your accredited environment (set
`KAMIWAZA_BASE_URL`). The shared OpenAI-compatible client remains available
as a fallback for local dev when no Kamiwaza endpoint is configured. Same
model IDs, same `chat_json` triage call, same `chat` CAD brief — just swap
the base URL and 100% of traffic stays on the wire.

## What it does

DISPATCH is a 3-pane operator UI for the installation 911 watch officer:

- **Stage 1 — Live transcript** of the inbound 911 call (segment-by-segment,
  speaker-labeled). In production this is Whisper / wav2vec2; in the demo
  it's a pre-written transcript replayed at recording cadence.
- **Stage 2 — AI triage card** via `chat_json` structured-output: incident
  type (fire / medical / active_threat / hazmat / mvi / mascal /
  suspicious_package), APCO-MPDS letter severity (alpha-echo), extracted
  address + lat/lon, recommended units, and three callback questions.
- **Stage 3 — Geospatial unit dispatch.** Greedy nearest-of-type selection
  off the unit roster, ETA at 35 mph average installation speed, plotted
  on a Folium installation map with 50 / 100 / 250 m stand-off rings.
- **Hero CAD entry** — three-section dispatcher entry (incident summary /
  unit assignment / scene safety brief) drafted by a Kamiwaza-deployed
  hero model. 15-second watchdog with deterministic fallback. Cache-first.

| Layer | Tech |
|---|---|
| Frontend | Streamlit on port 3031 |
| Backend | FastAPI on port 8031 |
| Map | folium + Leaflet (`streamlit-folium`) |
| LLM | Kamiwaza-deployed model (OpenAI-compat fallback via env-var) |
| Triage | `chat_json` structured-output |
| Hero brief | `chat` (15s timeout + baseline fallback, cache-first) |

## Run it

```bash
cd apps/31-dispatch
pip install -r requirements.txt
python data/generate.py            # 5 calls + 8 units + base map + cached briefs

# Backend (FastAPI) on 8031
python -m src.api &

# Frontend (Streamlit) on 3031
streamlit run src/app.py \
  --server.port 3031 \
  --server.headless true \
  --server.runOnSave false \
  --server.fileWatcherType none \
  --browser.gatherUsageStats false
```

Open http://localhost:3031.

## Real dataset provenance

This demo runs on synthetic 911 transcripts (5 hand-written calls + 8 named
units, seed `1776`). To plug in real data:

- **NG911 ANI/ALI feed** — NENA i3 SIP-INVITE + PIDF-LO Location Object;
  call recordings -> Whisper / wav2vec2 transcription
- **CAD export** — Tyler Spillman / Hexagon CAD / Mark43 / Motorola
  Premier One in NIEM-CAD XML or CSV
- **USCG Rescue 21** voice / OpsCenter feeds (for joint installations)
- **MC-CAD** Marine Corps Computer-Aided Dispatch (where deployed),
  ReBAC-gated through the Kamiwaza Tool Shed for ICS-209 / NIMS exports

See `data/load_real.py` for the loader stub and required field shape.

## Mission frame

> "Open-source, AI-integrated emergency dispatch platform that provides a
> unified operating picture by automating call transcription, incident
> classification, and unit recommendations. Requirements include real-time
> transcription, an automated triage agent, and geospatial orchestration
> for unit tracking and automated routing."
> -- LOGCOM portal, ERMP use case (Installation Incident Response)

## Files

```
apps/31-dispatch/
  PRD.md                       # the spec, with scoring tie-back
  README.md                    # this file
  requirements.txt
  package.json                 # Playwright recorder
  playwright.config.ts
  .env.example
  data/
    generate.py                # rerunnable synthesizer (seed 1776) + cache precompute
    load_real.py               # NG911 / CAD / USCG / MC-CAD swap stub
    calls.json                 # 5 synthetic 911 transcripts
    units.json                 # 8 named installation response units
    incident_locations.geojson # building polygons + perimeter
    cached_briefs.json         # pre-computed triage + CAD brief per call
  src/
    app.py                     # Streamlit 3-pane UI (frontend, port 3031)
    api.py                     # FastAPI backend (port 8031)
    triage.py                  # chat_json triage + hero CAD + unit selection
  tests/
    record-demo.spec.ts        # Playwright recorder
  demo-script.md
  demo-script.json             # produced by Playwright
  videos/dispatch-demo.mp4
  STATUS.txt
```

## Powered by Kamiwaza
