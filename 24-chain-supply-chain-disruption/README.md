# CHAIN — Global Supply-Chain Disruption Forecaster for Marine Sustainment

**Codename:** CHAIN · **Port:** 3024 · **Stack:** Streamlit (mono) + NetworkX + Plotly
**Use case:** Critical-component risk for USMC PEO Land Systems & PEO Aviation in a
polycrisis world. When a Taiwan Strait, Suez, Bab-el-Mandeb, or Malacca disruption
hits, which Marine procurement programs (ACV, AMPV, JLTV, MV-22, F-35B, CH-53K,
HIMARS) are exposed and what are the mitigation options?

## What it does

1. **30-node supply-network topology** — TSMC, ASML, Maxar, Northrop, BAE, Lockheed,
   rare-earth mines (Lynas, MP Materials, Baotou Steel), 4 maritime chokepoints
   (Malacca, Suez, Panama, Bab-el-Mandeb), Taiwan Strait, and 8 USMC end-items.
   NetworkX graph, weighted edges = annual flow $M, risk-colored from a synthetic
   60-day disruption events feed (typhoons, cyber incidents, export restrictions).
2. **Hero AI move (cache-first):**
   - **Step 1 (`chat_json`)** — analyzes the disrupted network and emits structured
     `{affected_marine_program[], substitute_supplier[], lead_time_impact_days,
     mitigation_actions[]}`.
   - **Step 2 (`chat`, gpt-5.4)** — writes a *Critical-Component Risk Brief for USMC
     PEO Land Systems*: BLUF, exposed programs (e.g. ACV / AMPV / JLTV chokes on
     rare-earth magnets sourced from Baotou), mitigation playbook, decision required.
3. **Three pre-baked scenarios** — Taiwan Strait closure (PLAN exercise →
   quarantine), Suez + Bab-el-Mandeb compound disruption, PRC rare-earth export
   freeze. Briefs are warmed in `data/cached_briefs.json` so the demo path is
   instant; user can click *GENERATE RISK BRIEF* to re-run live.

## Run

```bash
cd apps/24-chain
pip install -r requirements.txt
python data/generate.py     # synth data + warm hero cache
streamlit run src/app.py \
  --server.port 3024 \
  --server.headless true \
  --server.runOnSave false \
  --server.fileWatcherType none \
  --browser.gatherUsageStats false
```

## Real-data plug-in

Synthetic stand-in for three real Kaggle datasets (cited verbatim so judges can
plug them in):

1. **Global Supply Chain Disruption & Resilience** (Kaggle / datasetengineer)
2. **Global supply-chain risk and logistics** (Kaggle / dshahidul)
3. **Global trade 2024-2026** (Kaggle / kanchana1990)

Implementer maps real columns to CHAIN's normalized shape inside
`data/load_real.py` (docstring describes target schema). Activate with:

```bash
REAL_DATA_DIR=/path/to/three/csvs python data/load_real.py
```

## Hero AI move (verbatim)

CHAIN runs a NetworkX graph + a two-step LLM pipeline. First, the disrupted
subnetwork goes through `chat_json` for a structured JSON analysis. Second, that
JSON drives a hero `chat` ("gpt-5.4", 35 s budget) that writes a polished
*Critical-Component Risk Brief for USMC PEO Land Systems*. Cache-first by
construction — every brief is warmed during data generation and persisted to
`data/cached_briefs.json`. The Streamlit demo path serves from cache instantly;
the "GENERATE" button re-runs live with timeout-and-baseline backstops.

## Files

```
apps/24-chain/
├── README.md                    # this file
├── PRD.md                       # spec + scoring tie-back
├── data/
│   ├── generate.py              # synth + precompute_briefs() (seed=1776)
│   ├── load_real.py             # real-data swap stub (3 Kaggle datasets)
│   ├── suppliers.json           # 30 nodes
│   ├── edges.json               # 35 weighted edges
│   ├── chokepoints.json         # 5 chokepoints w/ status
│   ├── disruption_events.csv    # 132 events over 60 days
│   └── cached_briefs.json       # 3 pre-warmed hero briefs
├── src/
│   ├── agent.py                 # 2-step LLM pipeline + baseline backstop
│   ├── graph.py                 # NetworkX/Plotly topology + chokepoint Plotly geo map
│   └── app.py                   # Streamlit UI (port 3024)
├── tests/record-demo.spec.ts    # Playwright recorder
├── playwright.config.ts
├── package.json
├── requirements.txt
├── .env.example
├── demo-script.md               # narrator copy
├── videos/chain-demo.mp4        # captioned ≤ 90 s demo
└── STATUS.txt                   # done
```
