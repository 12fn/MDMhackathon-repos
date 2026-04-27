# PALLET-VISION — AI Visual Quantification Engine

> Photo in. Load plan out. Multimodal vision-language for USMC LOGCOM
> palletization and lift planning. App #17 of the LOGCOM MDM 2026 hackathon
> portfolio. Streamlit on port **3017**. Powered by Kamiwaza.

## Pitch

Today, USMC logistics planners eyeball a phone snap of staged cargo and produce
manual estimates of pallet count, cube/weight, and the lift requirement. The
estimates are slow, inconsistent, and rarely cite real platform constraints
(C-130J = 6 pallets, MTVR = 4 pallets, C-17 = 18 pallets).

PALLET-VISION fixes that. Drop in a single still — warehouse, loading dock,
drone overhead, flight line, engineer yard, ship deck — and one click fires:

1. A **multimodal vision-language hero call** with strict
   `response_format=json_object`. Returns: pallet count, type estimate,
   stacking efficiency, weight/volume, recommended platforms with named
   platform constraints, and a recommended-plan one-liner.
2. A **second narrator call** that grounds the JSON in the real platform
   spec table (`data/platform_specs.csv`) and writes a 4-bullet
   **Loadmaster Brief** ready for radio.

This is the **LOGCOM-published use case verbatim**: *AI Visual Quantification
Engine — Convert images of physical goods into accurate estimates of
palletization and transportation requirements, enabling faster, more efficient
logistics planning.*

## Run it

```bash
cd apps/17-pallet-vision

# 1. Generate sample images + platform spec table (one-time)
python data/generate.py

# 2. Pre-compute hero outputs (cache-first; needed for a snappy demo)
python data/precompute_briefs.py

# 3. Launch
streamlit run src/app.py \
  --server.port 3017 \
  --server.headless true \
  --server.runOnSave false \
  --server.fileWatcherType none \
  --browser.gatherUsageStats false
```

Open <http://localhost:3017>.

## The hero AI move

A single multimodal vision-language call returns:

```json
{
  "pallets_visible": 12,
  "pallet_type_estimate": "463L",
  "stacking_efficiency_pct": 90.0,
  "estimated_volume_m3": 50.0,
  "estimated_weight_kg": 54432.0,
  "vehicles_required": [
    {"platform": "C-17 Globemaster III", "count": 1, "load_pct": 66.67}
  ],
  "constraints_named": ["C-17 pallet position constraint: 18 463L max"],
  "confidence": 0.95,
  "recommended_load_plan_brief": "Load all 12 pallets onto a single C-17 Globemaster III."
}
```

Then a second narrator call grounds this JSON in the
real `data/platform_specs.csv` table and produces a 4-bullet Loadmaster Brief
citing exact platform capacities (C-17 = 18, C-130J = 6, MTVR = 4, LCAC = 12,
etc.). All sourced from public USAF AFI 24-605, USMC MCRP 4-11.3D, and OEM
spec sheets.

## Cache-first hero pattern

Both LLM calls are pre-computed for the 6 sample images and persisted in
`data/cached_briefs.json`. The Streamlit app loads from cache on selection
(zero round-trip latency) so the demo never sits on a spinner. Click
**REGENERATE** in the sidebar to fire a fresh live call (35 s watchdog with a
deterministic baseline fallback if the model times out).

## Real-data plug-in

Two real datasets back this use case (cited per the LOGCOM portal):

- **HIT-UAV** — High-altitude Infrared Thermal UAV dataset; drone-overhead
  frames with vehicles + people; 2898 IR images.
  <https://github.com/suojiashun/HIT-UAV-Infrared-Thermal-Dataset>
- **Moving objects in construction sites** — 10,013 construction-site
  detection images; closest open-source proxy for warehouse / dock cargo.

To swap real imagery in, drop JPEG/PNG files in any folder and:

```bash
export REAL_DATA_PATH=/abs/path/to/folder/of/photos
streamlit run src/app.py --server.port 3017 ...
```

The app prepends every file in `REAL_DATA_PATH` to the sample bank as
`REAL · <filename>`. See `data/load_real.py`.

## Files

```
apps/17-pallet-vision/
├── README.md                 # this file
├── PRD.md                    # spec + scoring tie-back
├── requirements.txt          # streamlit, pillow, pandas, openai, dotenv
├── package.json              # Playwright dev-only, for demo recorder
├── playwright.config.ts
├── .env.example
├── STATUS.txt                # done | building | blocked
├── demo-script.md            # narrator copy
├── demo-script.json          # caption cue timeline (Playwright emits this)
├── data/
│   ├── generate.py           # rebuilds sample_images/ + platform_specs.csv
│   ├── precompute_briefs.py  # fills cached_briefs.json (cache-first)
│   ├── load_real.py          # REAL_DATA_PATH stub + dataset URLs
│   ├── platform_specs.csv    # 9 organic USMC/USAF lift platforms
│   ├── sample_manifest.json  # ground-truth metadata for the 6 samples
│   └── cached_briefs.json    # pre-computed hero outputs (cache-first)
├── sample_images/            # 6 procedurally-rendered scenes (1024x640 JPEG)
├── src/
│   ├── app.py                # Streamlit operator console (port 3017)
│   └── vision.py             # multimodal hero call + narrator + watchdog
├── tests/
│   └── record-demo.spec.ts   # Playwright walkthrough -> webm + cue timeline
└── videos/
    └── pallet-vision-demo.mp4  # ~85 s captioned demo
```

## Scoring tie-back

- **Mission Impact (30%):** Verbatim LOGCOM use case — *AI Visual
  Quantification Engine.* Saves the planner the manual TM 38-250 cross-
  reference; gives the loadmaster a single-pane answer.
- **Technical Innovation (25%):** Multimodal vision-language with
  `response_format=json_object` strict-JSON schema, then a second narrator
  call grounds the JSON in a real airlift/sealift platform-spec table. Two-
  call agentic chain with watchdog + deterministic fallback.
- **Usability & Design (20%):** Kamiwaza dark theme, 3-click workflow
  (pick image → run → read brief). Captioned 85-second demo.
- **Security & Sustainability (15%):** Runs entirely behind
  `KAMIWAZA_BASE_URL` for on-prem multimodal inference. IL5/IL6 ready. Real-
  data plug-in via `data/load_real.py` documenting the HIT-UAV +
  Construction Site MOD datasets.
- **Team Collaboration (10%):** Reproducible synth via `data/generate.py`
  (seed=1776). Cache-first hero pattern. Real-data swap recipe documented.

**Powered by Kamiwaza.** Orchestration Without Migration. Execution Without
Compromise.
