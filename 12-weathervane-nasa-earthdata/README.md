# WEATHERVANE

*Mission-window environmental brief for amphibious / expeditionary planners.*

A planner picks an AOI, a date window, and a mission profile (LCAC landing, helo insert, drone ISR). WEATHERVANE fuses NASA Earth-observation timeseries into a graded environmental brief with a recommended 4-hour H-hour window highlighted on every chart.

## What it does

- Ingests **5 NASA Earth-observation timeseries** per AOI: MERRA-2 winds, GPM IMERG precipitation, GHRSST SST, MODIS cloud cover, WAVEWATCH III significant wave height.
- Fuses them via a **two-stage LLM call** (typed JSON H-hour recommendation, then narrative brief) against a per-mission constraint profile.
- Renders **plotly charts** with a green-shaded recommended window across all five variables.
- Outputs a **5-section BLUF brief** (BLUF, Sea State, Atmospherics, Risk Callouts, Recommendation) with a GO / CAUTION / NO-GO grade and confidence score.

## Demo video

[`videos/weathervane-demo.mp4`](videos/weathervane-demo.mp4)

## Quick start

```bash
export KAMIWAZA_BASE_URL=https://kamiwaza.local/api/v1
export KAMIWAZA_API_KEY=km-...
# OR fall back to OpenAI-compatible:
# export OPENAI_API_KEY=sk-...

pip install -r requirements.txt
python data/generate.py
streamlit run src/app.py --server.port 3012
```

Open http://localhost:3012.

## What's inside

```
12-weathervane-nasa-earthdata/
├── README.md
├── requirements.txt
├── .env.example
├── data/
│   ├── generate.py        # 30-day hourly synthetic timeseries + manifest
│   ├── manifest.json
│   └── *.csv              # 4 AOIs (Subic Bay, Yemen, Norway, MARFORPAC)
├── src/
│   ├── app.py             # Streamlit UI
│   ├── agent.py           # two-stage LLM fusion + mission profiles
│   └── charts.py          # plotly helpers w/ recommended-window shading
└── videos/
    └── weathervane-demo.mp4
```

## Hero AI move

Two-stage LLM in `src/agent.py`:

1. **`chat_json`** — typed H-hour recommendation. Schema-constrained JSON: `grade` (GO / CAUTION / NO-GO), `recommended_window` (~4h block within the planning horizon), `alt_window`, `confidence_pct`, `top_risks` (1-4 short tags), `one_liner`. Fed a compact summary (min/mean/max/p90 per variable + a pre-computed calmest-4h candidate).
2. **`chat`** — narrative brief. Five-section BLUF prose, conditioned on the JSON recommendation so the planner-facing text and the machine-readable grade never disagree. Routed through the `hero_model=` API parameter when the hero toggle is on.

## Plug in real data

This is a **Bucket C** template — the demo emits flat hourly CSV, but real NASA Earthdata is multi-dimensional HDF / NetCDF rasters. To swap:

- Add an `xarray` / `rioxarray` loader against NASA Earthdata Cloud (`https://search.earthdata.nasa.gov`) using your Earthdata login.
- Pull MERRA-2 (M2T1NXSLV), GPM IMERG (GPM_3IMERGHH), GHRSST (MUR), MODIS (MOD06_L2), and a WW3 ensemble for the AOI bounding box + time window.
- Reduce each grid to a per-AOI hourly timeseries (mean / point-extract), then emit the same `timestamp, hs_m, wind_kn, precip_mmhr, sst_c, cloud_pct` schema the agent already expects. No agent changes required.

## Adapt

- **Mission constraints** — edit `MISSION_PROFILES` in `src/agent.py` (LCAC Hs limit, helo wind limit, UAS precip / cloud limits) to match your unit's go/no-go matrix.
- **AOI list** — add entries to `LOCATIONS` in `data/generate.py` (or to your real Earthdata loader) with lat/lon and climate priors.
- **Provider** — all LLM calls go through `shared.kamiwaza_client`, which auto-detects Kamiwaza vs OpenAI-compatible vs Anthropic from env vars.

## Built on Kamiwaza

This template ships against [Kamiwaza](https://www.kamiwaza.ai/) for on-prem inference with no data egress. Same code path runs against any OpenAI-compatible endpoint for local dev.

See [ATTRIBUTION.md](../ATTRIBUTION.md) at the repo root for full data-source and model attribution. MIT licensed.
