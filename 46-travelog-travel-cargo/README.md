# TRAVELOG — Combined PCS Travel + Cargo + LogTRACE

**Hackathon app #46.** USMC LOGCOM AI Forum @ Modern Day Marine 2026.
Codename: **TRAVELOG**.  Port: **3046** (Streamlit mono).

## Pitch

A Marine doing a PCS today opens **DTS** for travel, **GCSS-MC** for cargo,
and emails their **S-1** for the paperwork. Three different systems for one
move. **TRAVELOG collapses that to one sentence in, one plan out** —
pre-filling both the DTS travel voucher and the cargo TMR from a single
natural-language intent.

## Use cases (3) covered in one app — Tier A

1. **Travel Program Validation** — JTR-compliant per-diem, GTCC, mode-of-travel,
   lodging projection on the DTS authorization pre-fill.
2. **TMR Automation** — VANGUARD-style real OpenAI tool-calling fires
   `submit_tmr` to auto-populate the cargo movement form, validates against
   installation movement policy (DTR 4500.9-R), routes to the AO.
3. **LogTRACE** — last-mile push (LaDe) from receiving installation port →
   receiving unit warehouse, synced to GCSS-MC.

## Datasets (4) fused into one agent

1. **Synthetic DTS authorizations** — VOUCHER schema (doc_number, ta_number,
   ao_edipi, traveler_edipi, JTR-aligned per-diem)
2. **AFCENT Logistics Data** — VANGUARD shape (asset class, mode, capacity,
   fuel burn, current base)
3. **Bureau of Transportation Statistics (BTS NTAD)** — HUB shape (multimodal
   nodes + edges across CONUS road / rail / sea / air corridors)
4. **Last Mile Delivery (LaDe)** — CARGO shape (parcel waybill, courier,
   pickup/delivery lat/lon, ETA)

## Hero AI move

A 3-pipeline merge in **one** agent:

```
Marine intent (one sentence)
    ↓
[1] compare_modes        — BTS NTAD + AFCENT lift data
    fly+ship cargo / drive+ship cargo / drive escort cargo / fly+air-freight
    Per-mode: time, $, fuel, JTR per-diem, cargo lead time
    ↓
[2] Auto-TMR             — submit_tmr tool-call (VANGUARD-style)
    Auto-populates cargo movement form, validates against installation
    movement policy, routes to AO
    ↓
[3] DTS voucher pre-fill — VOUCHER-style
    JTR-compliant per-diem, GTCC, mode-of-travel, lodging projection
    ↓
[4] Last-mile push       — LaDe + GCSS-MC
    Pickup → delivery to receiving unit on the new base
    ↓
[5] Cross-validate       — chat_json: travel + cargo + arrival window all sync?
    ↓
[6] Hero brief           — gpt-5.4, 35 s timeout, cache-first
    "Combined Travel + Cargo Action Plan" with BLUF + recommendation
    + DTS pre-fill + TMR pre-fill + lead-time gantt
```

## Run

```bash
cd apps/46-travelog
pip install -r requirements.txt
python data/generate.py             # builds the 4 datasets + cached briefs
streamlit run src/app.py \
  --server.port 3046 --server.headless true \
  --server.runOnSave false --server.fileWatcherType none \
  --browser.gatherUsageStats false
```

## Three-button workflow (idiot-proof)

The whole UI is three buttons — same VOUCHER-style requirement:

1. **View Options** — 4-mode comparison: Folium route map + Plotly cost
   stack + table.
2. **Submit Both** — fires DTS voucher + TMR pre-fill cards side by side,
   plus the LaDe last-mile + cross-validation verdict + lead-time Gantt.
   Includes an expander that runs the **real OpenAI tool-calling agent**
   loop live (compare_modes → prefill_dts_voucher → submit_tmr →
   plan_last_mile_push → cross_validate_plan).
3. **Print Brief** — cached hero brief (instant). Optional regenerate fires
   the gpt-5.4 hero call under a 35 s wall-clock timeout.

## Real-data plug-in

Swap the synthetic data for the four real upstream datasets via env vars and
the loaders in `data/load_real.py`:

| Dataset | Env var | Notes |
|---|---|---|
| DTS authorizations | `REAL_DTS_PATH` | DTS Reporting → Authorization Detail CSV |
| AFCENT logistics  | `REAL_ASSETS_PATH` | AFCENT consolidated readiness extract |
| BTS NTAD nodes    | `REAL_BTS_NODES`  | https://geodata.bts.gov/ (CSV/GeoJSON) |
| BTS NTAD edges    | `REAL_BTS_EDGES`  | as above |
| LaDe              | `REAL_LADE_PATH`  | https://github.com/wenhaomin/LaDe |

Required column shapes documented in `data/load_real.py`.

## On-prem story

The shared client is multi-provider. Set `KAMIWAZA_BASE_URL` and TRAVELOG
runs against an on-prem Kamiwaza-deployed model behind your installation's
boundary. CUI never leaves the perimeter. **IL5/IL6 ready.**

```bash
export KAMIWAZA_BASE_URL=https://kamiwaza.<installation>.usmc.mil
export KAMIWAZA_API_KEY=<your-key>
streamlit run src/app.py --server.port 3046 ...
```

## Authorities cited

- **JTR Ch 2** (CONUS per-diem) — DTMO via GSA
- **JTR Ch 3** (OCONUS per-diem) — DTMO
- **DoDFMR Vol 9 Ch 5** — GTCC oversight
- **DTR 4500.9-R Part II** — TMR / cargo movement
- **DoDI 5154.31** — APC oversight

## Files

```
apps/46-travelog/
├── README.md                       # this file
├── PRD.md
├── data/
│   ├── generate.py                 # 4-dataset synthesizer + precompute_briefs
│   ├── load_real.py                # real-data ingestion stubs (4 sources)
│   ├── per_diem_rates.json
│   ├── pcs_scenarios.json          # 30 PCS scenarios
│   ├── dts_records.csv
│   ├── logistics_assets.csv
│   ├── bts_nodes.json
│   ├── bts_edges.csv
│   ├── lade_records.csv
│   ├── manifest.json
│   └── cached_briefs.json          # 3 cached hero briefs (cache-first)
├── src/
│   ├── app.py                      # Streamlit UI (3046, three buttons)
│   ├── agent.py                    # 3-pipeline orchestrator + hero brief
│   └── tools.py                    # 5 tools exposed via OpenAI tool-calling
├── tests/record-demo.spec.ts
├── playwright.config.ts
├── demo-script.md / demo-script.json
├── requirements.txt
├── package.json
├── .env.example
├── videos/travelog-demo.mp4
└── STATUS.txt
```

Powered by Kamiwaza.
