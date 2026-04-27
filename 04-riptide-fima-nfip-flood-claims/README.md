# RIPTIDE — installation flood-risk + dollar-denominated impact assessment

Forecast the flood before it floods readiness. Pick a Marine installation + a storm scenario and get a streaming Operational Impact Assessment with a dollar exposure projection, days-to-mission-capable estimate, and a prioritized 5-action response checklist.

## What it does

- Fuses historic FEMA NFIP-shaped flood-claim density with five named USMC installation footprints (Lejeune, Cherry Point, Albany, Yuma, Pendleton).
- Runs a haversine geo-aggregation of claims within a configurable nautical-mile radius of any installation.
- Streams an Operational Impact Assessment from a hero LLM call grounded in the claim history + scenario severity.
- Returns a structured JSON 5-action prioritized response checklist (priority, asset, lead time, cost, rationale).

## Demo video

[`videos/riptide-demo.mp4`](videos/riptide-demo.mp4)

## Quick start

```bash
# 1. Install
pip install -r requirements.txt

# 2. Configure (Kamiwaza-first; cloud fallback when KAMIWAZA_BASE_URL is unset)
cp .env.example .env
# Production (Kamiwaza on-prem):
#   KAMIWAZA_BASE_URL=https://kamiwaza.local/api/v1
#   KAMIWAZA_API_KEY=<your-token>
# Dev fallback:
#   OPENAI_API_KEY=sk-...
# (or ANTHROPIC_API_KEY, OPENROUTER_API_KEY, LLM_BASE_URL+LLM_API_KEY — auto-detected)

# 3. Generate synthetic data (idempotent, seeded)
python data/generate.py

# 4. Launch FastAPI backend + Streamlit frontend
uvicorn backend.app:app --port 8004 &
BACKEND_URL=http://localhost:8004 streamlit run frontend/app.py --server.port 3004
```

Open <http://localhost:3004>.

## What's inside

```
04-riptide-fima-nfip-flood-claims/
├── README.md                  ← this file
├── .env.example               ← env-var template (Kamiwaza first, cloud fallback)
├── requirements.txt           ← Python deps
├── backend/
│   └── app.py                 ← FastAPI: /api/installations, /api/claims/aggregate,
│                                /api/assess (hero LLM), /api/actions (JSON LLM)
├── frontend/
│   └── app.py                 ← Streamlit UI: folium heatmap, KPI cards, OIA stream
├── data/
│   ├── generate.py            ← synthetic NFIP-shape generator (5k rows, seed 1776)
│   ├── installations.json     ← 5 reference USMC installations + inventories
│   ├── nfip_claims.json       ← generated synthetic claims (drop in real FIMA NFIP)
│   └── nfip_claims.parquet    ← same, parquet for fast load
└── videos/
    └── riptide-demo.mp4       ← demo recording
```

## Hero AI move

**Dual LLM call** on every "Run Operational Impact Assessment" click:

1. **Streaming Operational Impact Assessment** — hero call to `model="gpt-5.4"` (un-mini'd, `RIPTIDE_HERO_MODEL` overridable) via the shared client. Returns a 4-paragraph commander-grade narrative grounded in the claim history + scenario severity + installation inventory.
2. **Parallel JSON 5-action recommendations** — `chat_json` call with strict schema (`priority`, `action`, `asset`, `lead_time_hrs`, `cost_estimate_usd`, `rationale`) for a deterministic prioritized response table.

Both calls flow through `shared/kamiwaza_client.py` so swapping providers (Kamiwaza on-prem ↔ OpenAI ↔ Anthropic ↔ OpenRouter ↔ any OpenAI-compatible endpoint) is zero code change.

## Plug in real data (Bucket A)

This template ships with 5,000 schema-true synthetic records. To run on the real FIMA NFIP redacted claims dataset:

1. Download from FEMA: <https://www.fema.gov/openfema-data-page/fima-nfip-redacted-claims-v2>
2. Drop the CSV into `data/raw/` (create the dir).
3. Edit the loader in `backend/app.py` (`_load()`) to read the CSV instead of the bundled parquet.

**Required columns** (FEMA schema names):

- `id` — policy / claim identifier
- `dateOfLoss` (and derived `yearOfLoss`) — claim date
- `amountPaidOnBuildingClaim` + `amountPaidOnContentsClaim` — dollar amounts
- `latitude`, `longitude` — for haversine radius aggregation
- `state`, `countyCode` — for leaderboards
- `eventDesignation`, `floodZone` — peril context
- `buildingType`, `occupancyType` — risk weighting

The installation list (`data/installations.json`) carries the base name, lat/lon (FIPS optional), and per-base inventory (housing units, hangars, etc.) used to scale the projection. Add your own bases by appending to that file.

## Adapt

- **Swap installation list** — edit `data/installations.json` (or the `INSTALLATIONS` block in `data/generate.py`) to add/remove bases. Inventory keys feed the structures-at-risk math in `backend/app.py::_aggregate`.
- **Change scenario presets** — `SCENARIOS` dict in `backend/app.py` maps scenario id → severity multiplier, structures-impacted %, and downtime days. Add monsoons, ice storms, wildfire-driven debris flows, etc.
- **Tune currency normalization** — adjust the `avg_paid` calculation and `severity_multiplier` weights in `_aggregate` to match your insurance / replacement-cost basis.

## Built on Kamiwaza

This template is part of the [MDM 2026 Hackathon Templates](https://github.com/12fn/MDMhackathon-repos). LLM calls flow through the shared multi-provider client and run on-prem against a Kamiwaza-deployed model when `KAMIWAZA_BASE_URL` is set. See [ATTRIBUTION.md](../ATTRIBUTION.md) for dataset and tooling credits. MIT licensed.
