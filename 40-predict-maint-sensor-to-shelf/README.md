# PREDICT-MAINT — Closed-Loop Predictive Maintenance for USMC LOGCOM

Sensor-to-shelf in five stages. One Streamlit app on port **3040** covering all
four LOGCOM PdM-flavored use cases at once.

## Pitch

A bearing on an MTVR rear-axle hub trips an amber threshold during yard test.
PREDICT-MAINT fires a five-stage closed loop:

1. **Sensor** — CWRU drive-end accelerometer trace → RandomForest classifier →
   RUL estimate.
2. **Forecast** — RUL drop triggers a Holt-Winters demand spike on the
   matching Class IX NSN over the next 30/60 days.
3. **Auto-reorder** — `chat_json` shape validates the spike against GCSS-MC
   stock + ICM ledger; emits `{nsn, on_hand, projected_demand, shortfall,
   recommended_reorder_qty, source_depot, lead_time_days, action_due_by}`.
4. **Depot induction** — greedy scheduler reslots the asset into the MCLB
   Albany / Barstow / Blount Island Gantt, respecting bay capacity and
   parts-ETA.
5. **Ledger** — append-only SHA-256 hash-chained audit row written to
   `data/ledger.jsonl`. Tamper-evident on next read.

A hero AI brief ("gpt-5.4", 35 s wall-clock timeout, deterministic fallback)
writes a **Closed-Loop Maintenance Action Brief** — BLUF, sensor-to-shelf
chain, named bottleneck, recommended commander action.

## Run

```bash
cd apps/40-predict-maint
pip install -r requirements.txt
python data/generate.py            # synth + precompute cached briefs
streamlit run src/app.py \
  --server.port 3040 \
  --server.headless true \
  --server.runOnSave false \
  --server.fileWatcherType none \
  --browser.gatherUsageStats false
```

Open `http://localhost:3040`, pick an asset, click `RUN 5-STAGE CHAIN`.

## Hero AI move

```
(1) Sensor      RandomForest on CWRU vibration features → fault class + RUL
(2) Forecast    Holt-Winters w/ severity-shock multiplier → 30/60 d projection
(3) Auto-reorder structured JSON validated against GCSS-MC + ICM
(4) Induction   greedy reslot into MCLB Albany / Barstow / Blount Island Gantt
(5) Ledger      SHA-256 hash chain — tamper-evident on next read
+   Closed-Loop Maintenance Action Brief (cache-first, 35 s hero timeout)
```

Multi-modal: spectrogram + classifier output + RUL + structured tool calls
fed to the brief generator in one prompt.

## Real-data plug-in (5 datasets)

`data/load_real.py` documents and stubs the swap path for each dataset. Set the
env var, drop the file, and the same downstream pipeline runs:

| # | Dataset                              | Env var                | Loader        |
|---|---------------------------------------|------------------------|---------------|
| 1 | CWRU Bearing Fault (12 kHz drive-end) | `REAL_CWRU_MAT_DIR`    | `load_cwru()` |
| 2 | NASA Pred Mx (CMAPSS turbofan RUL)    | `REAL_CMAPSS_DIR`      | `load_cmapss()` |
| 3 | Microsoft Azure Pred Mx (telemetry)   | `REAL_AZURE_PDM_DIR`   | `load_azure_pdm()` |
| 4 | GCSS-MC Supply & Maintenance          | `REAL_GCSSMC_ZIP`      | `load_gcssmc()` |
| 5 | Inventory Control Management workbook | `REAL_ICM_XLSX`        | `load_icm()`  |

## Data shape (synthetic)

| File | Shape |
|------|-------|
| `data/vibration_corpus.npz` | 200 windows × 4 fault classes, 12 kHz drive-end (CWRU stand-in) |
| `data/nsn_catalog.json`     | 39 FSC-coherent Class IX NSNs (real prices, real platforms) |
| `data/assets.json`          | 5 test assets (MTVR / JLTV / LAV-25 / AAV-7A1 / MV-22B) |
| `data/maintenance_history.csv` | 1,500+ work orders, 90 days, real PMCS codes |
| `data/depot_capacity.json`  | 3 depots × bays × shifts × skills |
| `data/inventory.csv`        | 5,000 items (ICM workbook stand-in) |
| `data/ledger.jsonl`         | SHA-256 hash-chained append-only audit log |
| `data/cached_briefs.json`   | 3 hero briefs: nominal / surge / parts-constrained |

## Stack

Streamlit (3040) · scipy (envelope, spectrogram, Hilbert) · scikit-learn
(RandomForest) · statsmodels (Holt-Winters) · Plotly (forecast charts +
Gantt) · matplotlib (spectrograms) · `shared.kamiwaza_client.chat` (LLM brief).

## Domain authenticity

- Real platforms: MTVR / JLTV / LAV-25A2 / AAV-7A1 / MV-22B
- Real depots: MCLB Albany / MCLB Barstow / Blount Island Command
- Real PMCS codes: B / D / A / W / M / Q / S / AN  (no invented "SLEP")
- Real bearing physics: SKF 6205-2RS JEM (CWRU canonical). At 1772 rpm shaft:
  BPFO 105.87 Hz · BPFI 159.93 Hz · BSF 69.60 Hz · FTF 11.76 Hz
- FSC-coherent NSNs: 3110 (bearings), 2530 (brakes/steering/axle), 2920
  (engine electrical), 4730 (hydraulic seals), etc.

## On-prem story

Sidebar shows the env-var swap. With `KAMIWAZA_BASE_URL=https://kamiwaza.local/api/v1`
the same code path runs inside the wire — air-gapped, IL5/IL6 ready, no data
movement.

---

**Powered by Kamiwaza.** Orchestration Without Migration. Execution Without
Compromise.
