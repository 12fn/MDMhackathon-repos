# CARGO

**Last-Mile Expeditionary Delivery Optimizer.**
A natural-language push planner for a Marine forward depot resupplying eight dispersed squads across thirty kilometers of austere terrain inside a forty-eight-hour window.

> *"An expeditionary unit needs supplies pushed from a forward depot to dispersed squad-level positions across 30 km of austere terrain in 48 hours. Optimize routing, batching, and platform assignment."*

## What it does
Type a push in plain English:

> *Push 8,000 lb of Class I and 2,400 rounds-equivalent Class V from FOB Raven to alpha through hotel squads by 0600 tomorrow, lowest threat exposure.*

CARGO's LLM agent calls four tools — `list_squad_positions`, `compute_route`, `check_threat_overlay`, `compare_options` — in a real OpenAI-compatible function-calling loop on a **Kamiwaza-deployed model** and returns a ranked 3-option Last-Mile Push Brief: convoy composition, timing, threat windows, and risk mitigation. Every tool call streams live in a "Reasoning" sidebar; the recommended route animates on a dark Folium map with threat-zone overlays.

## Mission frame
**Use case framing:** Last-mile expeditionary delivery — orphan dataset (LaDe) pivoted into a Marine logistics frame. Falls under the MARADMIN 131/26 umbrella of "contested logistics, supply chain management, and expeditionary operations."

**Dataset (real, plug-in ready):** **Last Mile Delivery (LaDe)** — public last-mile delivery dataset released by Cainiao / Alibaba. The repo ships a synthetic but plausible Marine-flavored stand-in: 1 forward depot, 8 squad positions, 4 vehicle classes (MTVR / JLTV / ARV-L / autonomous resupply UGV), 3 named threat zones. Real-data swap recipe in `data/load_real.py`.

## Run

```bash
# from repo root
cp .env.example .env
# Today: OPENAI_API_KEY (cloud fallback)
# Tomorrow: KAMIWAZA_BASE_URL=https://<host>/v1 + KAMIWAZA_API_KEY=<token>
.venv/bin/pip install -r apps/23-cargo/requirements.txt
cd apps/23-cargo
.venv/bin/python data/generate.py    # synth data + precompute hero briefs
.venv/bin/streamlit run src/app.py \
  --server.port 3023 --server.headless true \
  --server.runOnSave false --server.fileWatcherType none \
  --browser.gatherUsageStats false
```

Open http://localhost:3023. Click **Plan Push (cache-first)** for instant demo, **Regenerate Live** to fire the live agent.

## Architecture

```
apps/23-cargo/
├── data/
│   ├── generate.py          # seeded synth (random.Random(1776)) + brief precompute
│   ├── load_real.py         # LaDe ingestion stub (Cainiao/Alibaba)
│   ├── depots.json          # 1 forward depot
│   ├── squads.json          # 8 squad positions w/ demand profile
│   ├── vehicles.csv         # 4 classes (MTVR / JLTV / ARV / UGV)
│   ├── threat_zones.json    # 3 named windows (UAS / sniper / IED-cleared)
│   └── cached_briefs.json   # cache-first hero outputs
├── src/
│   ├── tools.py             # 4 tools + OpenAI tool-calling JSON schemas
│   ├── agent.py             # multi-turn tool-calling loop, watchdog + fallback
│   └── app.py               # Streamlit dark-theme UI + Folium AntPath route
├── tests/record-demo.spec.ts
├── playwright.config.ts
├── demo-script.md
├── requirements.txt
└── videos/cargo-demo.mp4
```

## Hero AI move
Real OpenAI-compatible tool-calling loop. The first turn uses the hero model (configurable via `OPENAI_HERO_MODEL`); subsequent turns use the primary model with auto-fallback through the wrapper's chain. `tool_choice="auto"`, multi-turn until `finish_reason="stop"`. Wall-clock watchdog (35 s hero / 20 s subsequent) wraps each call with a deterministic baseline brief if the LLM is unreachable — the UI never spins.

## On-prem by default
All LLM calls go through `shared.kamiwaza_client.get_client()` — `KAMIWAZA_BASE_URL` + `KAMIWAZA_API_KEY` swap routes inference inside the accredited boundary. **100% data containment — squad positions, demand profiles, and threat overlays never leave your network.**

## Real-data swap (LaDe)
LaDe ships per-city CSVs (`LaDe_pickup_<city>.csv`) with order-level lat/lon/time/courier fields. `data/load_real.py` groups by `region_id` → top-8 regions become the 8 "squad positions"; parcel counts proxy demand. Vehicle and threat-zone tables stay synthetic (LaDe carries neither). Tool signatures don't change.

```bash
export REAL_DATA_PATH=/path/to/LaDe_pickup_Shanghai.csv
# then re-run data/generate.py to merge in
```

Powered by Kamiwaza.
