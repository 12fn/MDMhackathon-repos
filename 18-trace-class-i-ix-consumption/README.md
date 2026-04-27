# TRACE — LogTRACE Class I-IX consumption estimator

> *Sustainment estimates in seconds. Doctrine-aware. Source-aware.*

**Codename:** TRACE  ·  **Port:** 3018  ·  **Stack:** Streamlit (mono)  ·  **Use case:** LogTRACE (LOGCOM published)

LogTRACE turns a unit composition (e.g. *"MEU(SOC), 2,200 personnel, 30 days,
expeditionary austere, high tempo"*) into a doctrine-grounded Class I through
IX consumption estimate plus a 1-page Sustainment Estimate Brief.

## Hero AI move

A two-step agentic pipeline:

1. `chat_json` returns **all 9 supply classes** with daily consumption,
   30-day window total, variance band, and recommended pre-positioning sources
   from a synthetic GCSS-MC depot list — in **one** structured response.
2. `chat` narrates a 1-page Sustainment Estimate Brief (5 OPORD-shaped
   paragraphs) with risks and contingency sourcing options.

Cache-first on disk; both calls wrapped in a wall-clock watchdog with
deterministic baseline fallback so the UI never hangs.

## Run it

```bash
cd apps/18-trace
pip install -r requirements.txt
python data/generate.py            # writes synthetic data + cached_briefs
streamlit run src/app.py \
    --server.port 3018 --server.headless true \
    --server.runOnSave false --server.fileWatcherType none \
    --browser.gatherUsageStats false
# open http://localhost:3018
```

The shared client (`shared/kamiwaza_client.py`) auto-detects the active
provider (Kamiwaza on-prem first, then OpenAI / OpenRouter / Anthropic /
custom). Set the env from `.env.example`.

## Datasets — synthetic stand-ins (real-data swap shipped)

| Source | Synthetic location | Real-data plug-in |
|---|---|---|
| GCSS-MC Supply & Maintenance | `data/depots.json`, `data/gcssmc_depots.csv` | `data/load_real.py::load_real_depots()` — set `REAL_DEPOT_CSV` |
| Logistics-and-supply-chain (California, Kaggle) | implicit in doctrine rates | `data/load_real.py::load_real_lsc()` — set `REAL_LSC_CSV` |
| MCWP 4-11 / MCRP 3-40D consumption rates | `data/doctrine_rates.json` | replace JSON with real rate tables |

## What's in the UI

- **Sidebar:** scenario picker (MEU/RCT/MAGTF), free-form unit-type input,
  personnel + days steppers, climate selector (temperate / tropical / arid /
  cold-weather / expeditionary austere), opscale selector (low / medium / high),
  hero-model toggle.
- **Top metrics:** personnel, window days, total lift (lbs-equivalent).
- **Stacked bar:** Plotly stacked bar of all 9 supply classes over the
  operation window, lbs-equivalent.
- **Class breakdown table:** daily, window total, variance per class.
- **Sources panel:** per-class cards naming the top-3 GCSS-MC depots that
  can supply that class, with on-hand quantity and % of window covered.
- **Sustainment Estimate Brief:** 1-page OPORD-shaped narrative with risk
  callouts and contingency sourcing.

## Architecture

```
sidebar inputs ──> live_scenario dict ──> agent.estimate_consumption(scenario)
                                              │
                                              ├── baseline_estimate (always)
                                              └── chat_json (Step 1, ≤25s, cache-first)
                                              │
                                              v
                                          merged estimate
                                              │
                                              v
                                          agent.write_brief(scenario, est)
                                              ├── chat hero (Step 2, ≤35s, cache-first)
                                              └── baseline_brief (fallback)
                                              │
                                              v
                                          1-page Sustainment Estimate Brief
```

## Footer

*Powered by Kamiwaza · 100% Data Containment — Nothing ever leaves your accredited environment.*
