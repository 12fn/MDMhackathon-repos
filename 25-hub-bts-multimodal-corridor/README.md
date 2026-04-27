# HUB — Multimodal CONUS Movement Planner

> Pick origin, POE, and end-item — HUB compares road, rail, waterway, and air
> capacity, clearance, and weight limits in one pane and drafts a POE Movement
> Plan. Built for Marine logistics planners.

**Codename:** HUB · **Port:** 3025 · **Stack:** Streamlit + Folium + Plotly
**Dataset:** Bureau of Transportation Statistics — National Transportation
Atlas Database (NTAD), synthetic stand-in.

## Pitch

Marine planners moving equipment from CONUS origins (MCLB Albany / Barstow /
Blount Island / Lejeune / Pendleton) to Strategic Ports of Embarkation
(Beaumont, Charleston, Hampton Roads, Long Beach, Tacoma, …) need to overlay
end-item constraints (clearance, weight, permit) onto BTS NTAD road, rail,
navigable-waterway, and air-carrier shapes. Today this is four data sources
plus a spreadsheet. HUB fuses them into one pane and produces a named
**POE Movement Plan** — BLUF, recommended corridor, named bottlenecks,
alternates, cost-and-risk note.

## Hero AI move

Two-step LLM pipeline behind a deterministic per-mode feasibility engine:

1. `chat_json` — structured plan
   `{recommended_mode, transit_days_estimate, bottleneck_named,
     alternate_corridors[], cost_relative}`.
2. `chat` — markdown **POE Movement Plan** that reasons over the per-mode
   evidence pack. Cache-first (`data/cached_briefs.json`); wall-clock
   timeouts on both calls; deterministic baseline fallback.

## Run

```bash
cd apps/25-hub
pip install -r requirements.txt

# Generate synthetic data + pre-compute cached briefs:
python data/generate.py

# Launch on port 3025:
streamlit run src/app.py \
  --server.port 3025 \
  --server.headless true \
  --server.runOnSave false \
  --server.fileWatcherType none \
  --browser.gatherUsageStats false
```

Open http://localhost:3025.

## Real-data plug-in

Swap the synthetic corpus for the real BTS NTAD distribution via
`data/load_real.py`. Source layers (URLs in the module docstring):

- North American Roads (line)
- North American Rail Lines (line)
- Navigable Waterway Network Lines (line)
- T-100 Air Carrier Statistics (table)
- Strategic Highway Network (STRAHNET) overlay

Drop the extracted shapefiles in `REAL_DATA_PATH` and implement the
`geopandas → nodes/edges` projection. The output schema must match
`data/generate.py` exactly.

## Layout

```
apps/25-hub/
├── README.md
├── PRD.md
├── data/
│   ├── generate.py           # rerunnable synth (seed=1776) + precompute_briefs()
│   ├── load_real.py          # BTS NTAD ingestion stub
│   ├── nodes.json            # 30 hubs (MCLBs, POEs, rail terminals, river ports, airports)
│   ├── edges.csv             # typed road/rail/waterway/air edges
│   ├── end_items.json        # 10 USMC platforms
│   └── cached_briefs.json    # 3 pre-computed scenarios (cache-first)
├── src/
│   ├── agent.py              # corridor engine + chat_json + chat narrative
│   ├── charts.py             # Folium map + Plotly bars
│   └── app.py                # Streamlit shell (port 3025)
├── tests/record-demo.spec.ts
├── playwright.config.ts
├── demo-script.md
├── demo-script.json          # cue timeline (emitted by Playwright)
├── videos/hub-demo.mp4       # final captioned video
├── requirements.txt
├── .env.example
└── STATUS.txt
```

## On-prem story

The shared client (`shared/kamiwaza_client.py`) is multi-provider. Set
`KAMIWAZA_BASE_URL` and the same code runs inside the wire — air-gapped,
IL5/IL6 ready, vLLM behind an OpenAI-compatible surface.

**Powered by Kamiwaza.**
