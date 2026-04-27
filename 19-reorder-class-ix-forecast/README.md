# REORDER

**Class IX (repair parts) demand forecasting for a deployed MAGTF in contested logistics.**

LOGCOM published the use case: predict Class IX consumption for a deployed
MAGTF based on OPTEMPO, environmental conditions, and historical maintenance
data. Output: pre-positioning recommendations for contested-logistics
scenarios where the resupply window is narrow or denied.

## Pitch

The first contested-logistics fight is for the parts pipeline. REORDER ingests
90 days of GCSS-MC-shaped work orders across MTVR / LAV / JLTV / M88A2 /
HMMWV, runs a Holt-Winters time-series forecaster per NSN, and then asks a
Kamiwaza-deployed model to (a) judge each top-N NSN as GREEN / AMBER / RED
with a one-line pre-position recommendation and (b) draft a one-page
**Class IX Sustainment Risk Brief** — BLUF, top RED NSNs, contested-logistics
implications, and three pre-positioning courses of action.

## Hero AI move

Two-stage agent:

1. **Forecaster** — `statsmodels.ExponentialSmoothing` (Holt-Winters, weekly
   seasonality) projects 30/60/90-day demand per NSN with an 80% confidence
   band. Falls back to seasonal-naive when a series is too short. Deterministic
   and never raises.
2. **Per-NSN judge** — `chat_json` returns a structured JSON object per NSN
   matching the schema: `{nsn, part_name, platform_consuming,
   projected_30d_demand, current_stock_at_forward_node, shortfall_risk,
   preposition_recommendation, alt_supplier_or_substitution}`.
3. **Hero narrative** — `chat` (`gpt-5.4`) drafts the Class IX Sustainment
   Risk Brief. Cache-first via `data/cached_briefs.json`; deterministic
   baseline if the LLM hangs.

## Run

```bash
cd apps/19-reorder
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python data/generate.py            # produce synthetic CSV/JSON
python -m data.precompute_briefs   # warm the cached briefs (optional)
streamlit run src/app.py \
  --server.port 3019 \
  --server.headless true \
  --server.runOnSave false \
  --server.fileWatcherType none \
  --browser.gatherUsageStats false
```

Then open <http://localhost:3019>. Pick a scenario (MEU/MEB/MEF · OPTEMPO ·
environment) in the sidebar, click **GENERATE 90-DAY FORECAST**, read the
risk table, the per-NSN forecast chart, the forward-node map, and the
Sustainment Risk Brief.

## Real-data plug-in

```bash
export REAL_DATA_PATH=/path/to/gccsmc_workorders.csv
```

`data/load_real.py` documents the required schema (date, work_order_id,
platform, vehicle_id, environment, optempo, magtf_size, nsn, part_name,
qty_consumed, subsystem). Drop the CSV at `REAL_DATA_PATH`, the same
forecaster + agent pipeline runs against real GCSS-MC + NASA Predictive
Maintenance + Microsoft Azure Predictive Maintenance feeds.

## Datasets (provenance)

- **NASA Predictive Maintenance** — turbofan degradation curves; analog for
  vehicle subsystem wear → NSN consumption.
- **Microsoft Azure Predictive Maintenance** — synthetic component failure
  records with telemetry + maintenance events.
- **GCSS-MC Supply & Maintenance** — Marine Corps work-order + requisition
  system of record (synthetic stand-in here).

## On-prem story

Set `KAMIWAZA_BASE_URL` and `KAMIWAZA_API_KEY` and the same code runs inside
the wire. No data movement, IL5/IL6-ready posture via the Kamiwaza Stack.

Powered by Kamiwaza.
