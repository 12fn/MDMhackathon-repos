# MARINE-MEDIC (44)

> Full medical pipeline: blood at the hub, casualty triage at the point of
> injury, Class VIII resupply through GCSS-MC. One 6-stage agentic chain.

- **Codename:** MARINE-MEDIC
- **Stack:** Streamlit FE (port **3044**) + FastAPI BE (port **8044**)
- **Tier:** A — full medical flow, 4 datasets, 3 use cases
- **Use cases:** DHA RESCUE, Inventory Control Management, LogTRACE (Class VIII)
- **Datasets:** Medical Supply Inventory v1 + v2 + Network Data Model + GCSS-MC

## Pitch
Casualty in 30 minutes. Supply chain in 30 hours. MARINE-MEDIC closes the loop
across both — fuses TCCC / JTS triage doctrine with hub-spoke logistics so a
13th MEU FRSS gunnery sergeant and a III MEF J-4 MEDLOG planner are reading
off the same one-page Action Brief.

## Run

```bash
cd apps/44-marine-medic

# Generate the synthetic dataset (seed=1776) and pre-bake the hero briefs
python data/generate.py

# Frontend (Streamlit, port 3044)
streamlit run src/app.py \
  --server.port 3044 \
  --server.headless true \
  --server.runOnSave false \
  --server.fileWatcherType none \
  --browser.gatherUsageStats false

# Backend (FastAPI, port 8044) — optional, useful for headless callers / Next.js
uvicorn backend.app:app --host 0.0.0.0 --port 8044
```

## Hero AI move — 6-stage agentic chain
1. **Casualty event injection** — pick scenario + WIA count + location
2. **Triage cascade** (`chat_json`) — per-WIA card: Routine / Priority / Urgent / Urgent-Surgical, Role of care (Role 1 BAS / Role 2 FRSS / Role 2E / Role 3 NMRTC), Class VIII bundle
3. **Class VIII demand projection** — time-phased over 1 / 6 / 12 / 24 h
4. **Hub-spoke supply check** — does receiving spoke + APRA hub have enough? (cross-VITALS pattern)
5. **GCSS-MC requisition trigger** — auto-build the Class VIII requisition with FAD priority, source depot, lead-time
6. **Hero brief** (`chat`, gpt-5.4, 35 s, cache-first) — *Medical Sustainment Action Brief* with BLUF, casualty-flow projection (Role 1 -> 2 -> 2E -> 3), Class VIII gap, supplier action plan, regional-hub posture, mortality risk window

Bonus: **Stage 7 buy-on-market evaluation** per DHA RESCUE prompt; **multi-modal** photo-of-injury vision-language triage hint via `gpt-4o`.

## Datasets (synthetic stand-ins)
- `data/inventory_v1.json` — 200 PRBC/FFP/PLASMA/PLT/LTOWB rows w/ expiration
- `data/inventory_v2.json` — 1,000 broader Class VIII items
- `data/supply_network.json` — Medical Supply Network Data Model (hub + 12 spokes + edges)
- `data/gcss_mc.json` — 180 synthetic GCSS-MC Class VIII requisitions
- `data/casualty_scenarios.json` — 5 mass-cas scenarios (squad ambush, HE blast, burn MASCAL, CBRN, MVI)
- `data/triage_doctrine.json` — TCCC / JTS triage rules + Role-of-care thresholds + per-injury Class VIII planning factors
- `data/vendors.json` — 7 approved buy-on-market vendors (cold-chain, lift, donor-network, surgical sets)
- `data/cached_briefs.json` — pre-baked hero Action Briefs (cache-first pattern)

## Real-data plug-in
The synthetic data is a stand-in for real LOGCOM-portal datasets. Drop the
real exports in and run unchanged:

```bash
export REAL_INVENTORY_V1=/secure/path/medical_supply_inventory_v1.csv
export REAL_INVENTORY_V2=/secure/path/medical_supply_inventory_v2.xlsx
export REAL_NETWORK_PATH=/secure/path/medical_supply_network.json
export REAL_GCSS_PATH=/secure/path/gcss_mc_class_viii.json
streamlit run src/app.py --server.port 3044
```

See `data/load_real.py` for column-mapping notes (LOGCOM portal -> our
schema), including NDC/ISBT-128 lookups for blood products and FAD-code
conversions for FAD I-V priorities.

## On-prem story
Set `KAMIWAZA_BASE_URL` and the same code runs behind the wire. Casualty data
stays in the IL5/IL6 accredited environment — never leaves. All 6 stages emit
hash-chained audit events (HIPAA / NDAA Section 1739 flavored).

## Demo
- 90-second captioned demo: `videos/marine-medic-demo.mp4`
- Narrator script: `demo-script.md`
- Cue file (Playwright-emitted): `demo-script.json`

## File map
```
apps/44-marine-medic/
├── README.md                       <- this file
├── PRD.md                          <- problem / solution / scoring tie-back
├── requirements.txt                <- Python deps
├── package.json                    <- Playwright recorder
├── playwright.config.ts
├── .env.example
├── data/
│   ├── generate.py                 <- seed=1776 synth + cache precompute
│   ├── load_real.py                <- real-data swap recipe (4 datasets)
│   ├── hub.json
│   ├── spokes.json
│   ├── routes.json
│   ├── inventory_v1.json
│   ├── inventory_v2.json
│   ├── supply_network.json
│   ├── gcss_mc.json
│   ├── casualty_scenarios.json
│   ├── triage_doctrine.json
│   ├── vendors.json
│   └── cached_briefs.json
├── src/
│   ├── agent.py                    <- 6-stage pipeline
│   └── app.py                      <- Streamlit FE (port 3044)
├── backend/
│   └── app.py                      <- FastAPI BE (port 8044)
├── tests/record-demo.spec.ts
├── videos/marine-medic-demo.mp4
├── demo-script.md
├── demo-script.json
└── STATUS.txt
```

Powered by Kamiwaza.
