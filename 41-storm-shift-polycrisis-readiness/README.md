# STORM-SHIFT

> Polycrisis storm-scenario gameboard for USMC installations. Six parallel
> projection agents fuse five public datasets into one cascading readiness
> picture.

**Codename:** STORM-SHIFT  ·  **App #41**  ·  **Port:** `3141` (Streamlit mono — 3041 is held by MARLIN's Docker fallback)

## Hero AI move

Operator picks a storm scenario (Cat-3 hurricane, atmospheric river, Santa
Ana fire-following, etc.), an installation (Lejeune, Cherry Point, Albany,
Yuma, Pendleton), and an optional co-occurring scenario. **Six projection
agents fan out in parallel:**

1. **Flood damage**         — NFIP claim density × storm severity haversine
2. **Supply chain**         — FEMA Supply Chain Climate Resilience + Logistics-CA disruption rollup
3. **Inventory cascade**    — on-hand stocks ÷ surge demand → red items in N hours
4. **Consumption surge**    — Class I-IX consumption × shelter days × headcount
5. **Base impact rollup**   — total $ exposure + days-to-MC
6. **Fire-secondary risk**  — NASA FIRMS pixels × scenario wind-projected ignition score

A **Sankey diagram** renders the cascade chain (storm → flood → supply gap →
inventory red); a **polycrisis multiplier card** surfaces non-linear compounding
when two scenarios co-occur (e.g. atmospheric river + Santa Ana = 1.60×).

The hero LLM call (Kamiwaza-deployed, 35 s watchdog) writes a one-page
**Polycrisis Readiness Brief** — BLUF, top 3 cascading effects, pre/post-
landfall actions, dollar exposure summary, days-to-MC.

**Cache-first**: 3 polycrisis briefs are pre-computed in `data/cached_briefs.json`
so the page renders instantly. Live regenerate uses the hero model.

## Datasets (5) — synthetic, real-data plug-in via `data/load_real.py`

| # | Dataset                                       | Real source                                                                  | Loader                          |
|---|-----------------------------------------------|-------------------------------------------------------------------------------|---------------------------------|
| 1 | NASA Earthdata (GPM IMERG hourly grids)       | https://earthdata.nasa.gov/  (GES DISC GPM IMERG L3 v07)                      | `load_real_nasa_earthdata()`    |
| 2 | NASA FIRMS (active fire pixels)               | https://firms.modaps.eosdis.nasa.gov/active_fire/  (MODIS C6 / VIIRS)         | `load_real_nasa_firms()`        |
| 3 | FEMA NFIP Redacted Claims v2                  | https://www.fema.gov/openfema-data-page/fima-nfip-redacted-claims-v2          | `load_real_nfip()`              |
| 4 | FEMA Supply Chain Climate Resilience          | FEMA / Qlik Open Data (Supply Chain Climate Resilience)                       | `load_real_fema_sc_climate()`   |
| 5 | Logistics-and-supply-chain-dataset (CA)       | Kaggle `logistics-and-supply-chain-dataset` (or DOT California freight)       | `load_real_logistics_ca()`      |

## Use cases (3) — LOGCOM portal verbatim

- **Common Operating Picture (I-COP) Aggregator** — fused 6-projection panel + Sankey + map
- **Inventory Control Management** — hours-to-RED bar, Class I-IX surge tracker
- **LogTRACE** — Class I-IX consumption surge math driven by shelter days × headcount × severity

## Domain authenticity (Tier A)

Real installations with real lat/lon and verified storm history:
- **MCB Camp Lejeune** — Hurricane Florence 2018 caused $3.6B+ in damage; recovery 18 months
- **MCAS Cherry Point** — Florence flooded 800+ buildings; MAG-14 relocated
- **MCLB Albany** — January 2017 tornado outbreak damaged 60% of LOGCOM HQ
- **MCAS Yuma** — Hurricane Hilary (2023) closed I-8; annual monsoon flash floods
- **MCB Camp Pendleton** — Atmos rivers (2023, 2024) flooded San Onofre Creek; Santa Ana fire-following

## Run

```bash
cd apps/41-storm-shift

# 1. install
pip install -r requirements.txt

# 2. generate synthetic corpus + pre-compute briefs
python data/generate.py

# 3. launch the gameboard
streamlit run src/app.py \
  --server.port 3141 --server.headless true \
  --server.runOnSave false --server.fileWatcherType none \
  --browser.gatherUsageStats false
```

Open http://localhost:3141 — the gameboard renders **immediately** with cached
projections + brief. Click **RUN 6 PARALLEL PROJECTIONS** to refresh from a
new operator picks. Toggle **Hero AI brief** to use the Kamiwaza-deployed hero
model (live regenerate).

## Real-data swap recipe

Set the relevant env var(s) to a path on disk; `src/projections.py` will pick
up real data without code changes:

```bash
export REAL_NASA_EARTHDATA_PATH=/data/earthdata/grid.csv
export REAL_NASA_FIRMS_PATH=/data/firms/MODIS_C6_USA_24h.csv
export REAL_NFIP_PATH=/data/openfema/nfip_redacted_claims_v2.parquet
export REAL_FEMA_SC_CLIMATE_PATH=/data/openfema/fema-sc-climate.csv
export REAL_LOGISTICS_CA_PATH=/data/kaggle/logistics_california.csv
```

Schema requirements + provenance per dataset are documented in `data/load_real.py`.

## Record demo

```bash
npm install
npx playwright install chromium
APP_URL=http://localhost:3141 npx playwright test tests/record-demo.spec.ts

# caption + finalize
mkdir -p videos
python ../../shared/caption_overlay.py \
  --video test-results/storm-shift-polycrisis-walkthrough/video.webm \
  --script demo-script.json \
  --out videos/storm-shift-demo.mp4
```

## Footprint

- **Port:** 3141
- **Stack:** Streamlit + Plotly + Folium + streamlit-folium
- **Hero call:** `gpt-5.4` (Kamiwaza-deployed) with 35 s watchdog → cache-first → deterministic fallback
- **Brand:** Kamiwaza dark theme via `shared.kamiwaza_client.BRAND`

Powered by Kamiwaza · Storm models stay in your enclave · No cloud egress.
