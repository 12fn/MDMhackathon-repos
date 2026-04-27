# MARLIN — AIS dark-vessel and anomaly intel layer

> Hackathon template #01 of 14 — MDM 2026 LOGCOM AI Forum.
> MIT licensed. Built on [Kamiwaza](https://www.kamiwaza.ai/).

## What it does

- **Animates AIS vessel tracks** on a dark Leaflet map, with a 100-step time slider that scrubs through ~8 hours of pings.
- **Flags three anomaly classes** out of the box: AIS gaps (a vessel goes dark), loiters inside a denied/restricted polygon, and covert mid-ocean rendezvous between two vessels.
- **Click any flagged vessel** and an LLM streams a 3-paragraph intelligence narrative into the side panel, citing specific timestamps + lat/lon from the track.
- **Returns structured indicators** via a JSON-mode call (type, confidence, lat/lon, recommended action) that downstream systems can consume directly.

The mission frame in the demo data is INDOPACOM contested logistics in the Bashi Channel between Taiwan and the Philippines — but every piece is generic AIS, so swap in your own region/feed in minutes.

## Demo video

[`videos/marlin-demo.mp4`](videos/marlin-demo.mp4) — 90-second walkthrough showing track playback, anomaly click-through, and the streaming intel narrative.

## Quick start

MARLIN is split frontend / backend: a FastAPI service on port `8001` and a Next.js app on port `3001`.

### 0. Pick an LLM provider (one-time, repo-wide)

From the repo root, copy the env template and fill in **one** provider's vars. Kamiwaza is the recommended on-prem path; OpenAI/OpenRouter/Anthropic/any-OpenAI-compat all work via the same shared client.

```bash
cd /path/to/MDMhackathon-repos
cp .env.example .env
# edit .env — set KAMIWAZA_BASE_URL + KAMIWAZA_API_KEY,
# or OPENAI_API_KEY, or OPENROUTER_API_KEY, etc.
```

See [`DEPLOY.md`](../DEPLOY.md) for the full provider table.

### 1. Install deps

```bash
# Python deps (from MARLIN folder)
cd 01-marlin-ais-vessel-tracking
pip install -r requirements.txt

# Frontend deps
cd frontend && npm install && cd ..
```

### 2. Generate synthetic AIS data

```bash
python data/generate.py
```

Writes `tracks.json`, `vessels.json`, `denied_areas.json`, `anomalies.json`, `timeline.json` into `data/`.

### 3a. Run it (two-shell split)

```bash
# Shell 1 — backend on :8001
python -m uvicorn backend.app:app --host 127.0.0.1 --port 8001

# Shell 2 — frontend on :3001
cd frontend && npm run dev
```

Open <http://127.0.0.1:3001>.

### 3b. Run it (single shell)

```bash
(python -m uvicorn backend.app:app --host 127.0.0.1 --port 8001 &) && \
  cd frontend && npm run dev
```

## What's inside

```
01-marlin-ais-vessel-tracking/
├── README.md                    # this file
├── requirements.txt             # Python deps (FastAPI + LLM client deps)
├── .env.example                 # local env stub (real config lives at repo root)
├── backend/
│   └── app.py                   # FastAPI :8001 — vessels, tracks, intel SSE stream
├── frontend/                    # Next.js 15 + Tailwind + Leaflet
│   ├── app/{page,layout}.tsx    # main map + side intel panel
│   ├── app/globals.css          # Kamiwaza dark theme
│   ├── components/MarlinMap.tsx # Leaflet map renderer
│   ├── next.config.mjs          # /api/* rewrite → 127.0.0.1:8001
│   ├── package.json
│   └── tailwind.config.ts
├── data/
│   ├── generate.py              # synthesizes 10 vessel tracks + 3 anomalies
│   ├── tracks.json              # per-vessel ping arrays (gen output)
│   ├── vessels.json             # vessel roster metadata (gen output)
│   ├── denied_areas.json        # restricted polygons (gen output)
│   ├── anomalies.json           # pre-computed anomaly records (gen output)
│   └── timeline.json            # 100 evenly-spaced timestamps (gen output)
├── public/                      # static assets
└── videos/
    └── marlin-demo.mp4          # captioned 90-second demo
```

## Hero AI move

Click a red-pulsing vessel. The frontend POSTs to `/api/intel/{mmsi}/stream` and consumes a Server-Sent Events stream:

1. **`event: context`** — full JSON context blob (vessel meta, last 12 pings, nearest 5 vessels, denied polygons) so the panel renders immediately.
2. **`event: token`** — narrative tokens streamed live via the OpenAI-compatible `chat.completions.create(stream=True)` API. Three structured paragraphs (pattern of life → anomaly analysis → time-bounded recommendation), each citing specific `(timestamp, lat, lon)` tuples from the track.
3. **`event: indicators`** — a second JSON-mode call returns 2–5 structured indicators with `type`, `confidence`, `lat`, `lon`, `timestamp`, `description`, `recommended_action`. Rendered as a card list underneath the narrative.
4. **`event: done`** — stream ends.

Both calls go through `shared/kamiwaza_client.py` — no provider-specific code in `backend/app.py`. Swap providers via env vars; the same SSE stream works against Kamiwaza, OpenAI, OpenRouter, or any OpenAI-compatible endpoint.

## Plug in real data

MARLIN is a **bucket A** swap (drop-in CSV) per [`DATA_INGESTION.md`](../DATA_INGESTION.md). Suggested real source: NOAA / [MarineCadastre.gov](https://marinecadastre.gov/) AIS public archive (~4 GB per month).

**Required columns** (canonical AIS schema — what the loader and downstream anomaly detectors expect):

| Column | Type | Notes |
|---|---|---|
| `MMSI` | string | Vessel identifier (9-digit Maritime Mobile Service Identity) |
| `lat`, `lon` | float | WGS84 |
| `timestamp` | ISO 8601 | UTC |
| `sog` | float | Speed over ground, knots |
| `cog` | float | Course over ground, degrees |
| `vessel type` | string | Cargo / Tanker / Fishing / etc. |

**To swap:** rewrite `data/generate.py` (or add a thin loader) to read your CSV/Parquet and emit the same `tracks.json` / `vessels.json` shape (`{mmsi, name, type, flag, color, pings: [{t, lat, lon, course, speed_kn, mmsi}, ...]}`). The backend caches these JSON files at startup — restart `uvicorn` to pick up changes. Anomaly detection (gap, loiter, rendezvous) runs downstream of the loader on whatever pings you feed it.

## Adapt for your hackathon entry

Three directions to fork from this template:

1. **Swap the mission frame.** The prompts in `backend/app.py` (`SYSTEM_PROMPT`, `NARRATIVE_INSTRUCTIONS`) are tuned for III MEF G-2 / MIO tipping. Re-target for Coast Guard SAR, fisheries enforcement, port security, or commercial fleet ops by editing those two strings — no other code changes required.
2. **Change the anomaly rules.** The synthetic anomaly logic lives in `data/generate.py`; the runtime detection helpers (`haversine_nm`, neighbor lookup) live in `backend/app.py`. Add detectors for speed-over-rated, course-deviation-from-route, AIS-spoofing (lat/lon jumps), or zone-curfew violations.
3. **Plug a real LOGCOM AIS feed.** See the previous section. If you have a Spire / Orbcomm / MarineCadastre live feed, write a poller that updates `tracks.json` on a cron and the same UI/SSE flow shows live data.

## Built on Kamiwaza

[Kamiwaza](https://www.kamiwaza.ai/) is the on-prem GenAI orchestration stack these templates target — same OpenAI-compatible API surface, but the weights live inside your enclave. See [`ATTRIBUTION.md`](../ATTRIBUTION.md) for the full credit list.
