# CONTESTED-LOG (app 39)

**End-to-end CONUS-to-squad sustainment in a contested INDOPACOM AOR.**

Tier-A mega-app fusing **eight** datasets into one Contested Sustainment
COA Brief: BTS NTAD + MSI WPI + AIS + ASAM Pirate Attacks + AFCENT
Logistics + GCSS-MC + LaDe Last-Mile + Global SC Disruption.

Operator types one sentence:

> "Push 200 pallets MREs from MCLB Albany to 31st MEU at Itbayat by D+14,
> contested INDOPACOM, lowest pirate-risk."

Agent fires **6 typed tools** end-to-end:

1. `route_conus()` — BTS NTAD rail/road/water leg, weight-class + bridge clearance
2. `check_port_capacity()` — MSI WPI berth + LCAC pad check at the SDDC SPOE
3. `forecast_pirate_risk()` — live KDE on 3,000 ASAM-shape attack records
4. `check_supply_chain_disruption()` — rolling 60-day events feed
5. `compute_last_mile()` — LaDe + GCSS-MC fused squad-level push
6. `compare_options()` — rank 3 end-to-end COAs

Returns a "Contested Sustainment COA Brief" — BLUF + full route narrative
(named bottlenecks, risk windows, alt routes) + days-of-supply check
(200 MRE pallets ≈ 21 days for 31st MEU(SOC), cross-checked against
MEU(SOC) doctrine).

## Hero AI move

A single `chat` call into the **hero model** (35 s wall-clock budget,
cache-first) drives a multi-turn tool-calling loop. Watchdog fallback to
deterministic baseline so the demo never spins. Three scenarios (INDOPACOM
standard, EUCOM cold-weather, AFRICOM Bab-el-Mandeb shut) are pre-rendered
to `data/cached_briefs.json` at generate-time.

## Run

```bash
cd apps/39-contested-log
pip install -r requirements.txt
python data/generate.py             # synth 8 datasets + precompute briefs
streamlit run src/app.py \
  --server.port 3039 --server.headless true \
  --server.runOnSave false --server.fileWatcherType none \
  --browser.gatherUsageStats false
# → http://localhost:3039
```

## Real-data plug-in

`data/load_real.py` documents the swap path for each of the 8 datasets:

| Dataset | Source | Loader |
|---|---|---|
| BTS NTAD | geodata.bts.gov shapefiles | `load_real_ntad()` |
| MSI WPI | NGA WPI.csv | `load_real_wpi()` |
| AIS | MarineCadastre.gov tracks | `load_real_ais()` |
| ASAM | NGA Anti-Shipping Activity Messages | `load_real_pirate()` |
| AFCENT Logistics | LMDC/TMR system feed | `load_real_afcent_stocks()` |
| GCSS-MC | enterprise data warehouse export | `load_real_gcss()` |
| LaDe | Cainiao/Alibaba public release | `load_real_lade()` |
| Global SC Disruption | Resilinc EventWatchAI / Everstream IQ | `load_real_sc_disruption()` |

Each loader is a docstring + `NotImplementedError` raise that names the
expected schema. Set the matching `REAL_*_PATH` env var to wire it up.

## Stack

- **Streamlit** (port 3039)
- **PyDeck** dark theatre map (full Pacific basin)
- **Plotly** Gantt timeline of the recommended COA
- **scikit-learn** KernelDensity for the live pirate-risk overlay
- **OpenAI tool-calling** loop with cache-first hero pattern
- **Multi-provider** via `shared.kamiwaza_client` — same code, swap to
  Kamiwaza on-prem by setting `KAMIWAZA_BASE_URL`.

## Scoring tie-back

- **Mission Impact (30%):** Three concurrent LOGCOM use cases — TMR
  Automation, LogTRACE consumption-rate cross-check, and I-COP aggregator —
  in one pane. Verbatim Force Design 2030 / contested logistics frame.
- **Technical Innovation (25%):** Real OpenAI tool-calling loop firing 6
  typed tools end-to-end; live KDE on 3,000-record piracy dataset;
  cross-domain (CONUS → blue-water → squad) fusion.
- **Usability & Design (20%):** Kamiwaza dark theme; one-sentence operator
  input drives the entire pipeline; live agent reasoning sidebar; captioned
  demo.
- **Security & Sustainability (15%):** On-prem via Kamiwaza Stack
  (KAMIWAZA_BASE_URL beat); IL5/IL6 ready; 8 documented real-data swap
  paths.
- **Team Collaboration (10%):** Modular tools, reproducible synth (seed
  1776), per-dataset real-data recipes.
