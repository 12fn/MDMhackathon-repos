# OMNI-AGENT — Kamiwaza Meta-Orchestrator (port 3048)

> **One ring to rule them all.** Your Marines have 53 different AI tools.
> OMNI-AGENT picks the right ones, fires them in order, and writes you the
> fused commander's brief. **One question in. One brief out.**

## Pitch

Modern Marine planners drown in dashboards. We have apps for blood logistics
(VITALS), weather windowing (WEATHERVANE), MARFORPAC node risk (MERIDIAN),
contested CONUS-to-EABO sustainment (CONTESTED-LOG), Class IX forecasting
(REORDER), counter-UAS (CUAS-DETECT), installation ICOP (OMNI), all-source
intel (OMNI-INTEL), TCCC triage (MARINE-MEDIC) — and dozens more. Operators
don't know which one to fire first.

**OMNI-AGENT is the meta-orchestrator.** A real OpenAI tool-calling agent
that exposes 14 of the most distinctive sibling apps as governed tools.
The user types one cross-domain natural-language question; the model picks
the right tools (often 2–4 in sequence), invokes them, fuses the results,
and writes a 1-page Commander-grade brief — **with full provenance.**

This is the canonical demo of the **Kamiwaza Tool Garden**: a governed
catalog of AI capabilities, brokered by an inference-mesh-aware orchestrator,
all hash-chain audited for SJA forensics — running entirely inside your
accredited boundary.

## Hero AI move

Cross-domain reasoning across the entire portfolio:

> *"What's our blood readiness in INDOPACOM right now, and are any spokes
> affected by typhoons in the next 72h? If yes, draft me a Commander's
> MEDLOG OPORD recommending action."*

Agent decomposes:
1. `query_vitals(question="blood readiness in INDOPACOM")` → spoke scores + MEDLOG brief
2. `query_weathervane(aoi="INDOPACOM", window="72h")` → TC 03W go/no-go window
3. `query_meridian(scope="MARFORPAC sustainment nodes affected by weather")` → 5-paragraph node brief
4. Hero `gpt-5.4` synthesis writes the fused 1-page Commander's MEDLOG OPORD

The **live tool-call trace** sidebar shows the operator each app being
called, its latency, its return shape. The **hash-chained audit log**
captures every invocation for after-action review.

## Run it

```bash
cd apps/48-omni-agent
pip install -r requirements.txt
cp .env.example .env  # add your OPENAI_API_KEY (or KAMIWAZA_BASE_URL)
python data/generate.py    # pre-warm the 7 cached demo briefs (cache-first pattern)
streamlit run src/app.py \
    --server.port 3048 \
    --server.headless true \
    --server.runOnSave false \
    --server.fileWatcherType none \
    --browser.gatherUsageStats false
```

Open http://localhost:3048.

- Click **FIRE (cached)** to render the pre-warmed demo (snappy).
- Click **FIRE (live)** to run the real OpenAI tool-calling loop end-to-end.
- Watch the **LIVE TOOL-CALL TRACE** on the right as the agent reasons.
- Watch the **HASH-CHAINED AUDIT** verify after every invocation.

## What's wired

14 sibling-app tools (out of 53):

| # | Tool | Codename | App dir | Dataset / use case |
|---|---|---|---|---|
| 1 | `query_vitals` | VITALS | `15-vitals` | DHA blood logistics (hub-and-spoke) |
| 2 | `query_weathervane` | WEATHERVANE | `12-weathervane` | NOAA + JTWC mission weather |
| 3 | `query_meridian` | MERIDIAN | `05-meridian` | MARFORPAC node climate-risk |
| 4 | `query_contested_log` | CONTESTED-LOG | `39-contested-log` | CONUS-to-EABO contested sustainment |
| 5 | `query_trace` | TRACE | `18-trace` | Class I-IX consumption-rate estimator |
| 6 | `query_reorder` | REORDER | `19-reorder` | Class IX parts forecast |
| 7 | `query_cuas_detect` | CUAS-DETECT | `35-cuas-detect` | RF-spectrogram drone classification |
| 8 | `query_omni` | OMNI | `38-omni` | Installation ICOP fusion (ABAC) |
| 9 | `query_omni_intel` | OMNI-INTEL | `43-omni-intel` | Daily ASIB |
| 10 | `query_learn` | LEARN | `32-learn` | Marine LMS cohort assessment |
| 11 | `query_schoolhouse` | SCHOOLHOUSE | `47-schoolhouse` | Schoolhouse competency rollup |
| 12 | `query_cadence` | CADENCE | `37-cadence` | Per-Marine assessment + feedback |
| 13 | `query_cat_router` | CAT-ROUTER | `52-cat-router` | Kamiwaza model-catalog routing |
| 14 | `query_marine_medic` | MARINE-MEDIC | `44-marine-medic` | TCCC triage |

7 cross-domain demo queries pre-loaded:

1. **MEDLOG x weather x sustainment** (default) — VITALS + WEATHERVANE + MERIDIAN
2. **C-UAS posture (Pendleton 7-day)** — CUAS-DETECT + OMNI + WEATHERVANE
3. **31st MEU EABO Itbayat (30-day)** — CONTESTED-LOG + TRACE + REORDER + VITALS
4. **Daily ASIB** — OMNI-INTEL
5. **1st Bn 8th Marines training readiness** — LEARN + SCHOOLHOUSE + CADENCE
6. **Model routing for MEDLOG workflow** — CAT-ROUTER
7. **TCCC mass-cas triage** — MARINE-MEDIC + OMNI

## How it works (architecture)

```
┌─────────────────────────────────────────────────────────────────┐
│ Streamlit UI (port 3048)                                        │
│   left: Tool Shed     center: query + brief    right: trace+audit│
└────────────┬────────────────────────────────────────────────────┘
             │
             ▼
┌─────────────────────────────────────────────────────────────────┐
│ src/agent.py — OpenAI tool-calling loop                         │
│   chat.completions.create(tools=TOOL_SCHEMAS, tool_choice=auto) │
│   loop until finish_reason='stop' or max_turns                  │
│   watchdog timeout, deterministic fallback                      │
└────────────┬────────────────────────────────────────────────────┘
             │
             ▼
┌─────────────────────────────────────────────────────────────────┐
│ src/tools.py — 14 typed wrappers                                │
│   each: thin dispatcher into apps/<NN>-<codename>/data/cached_*.json│
│   each tool returns {codename, port, dataset, ...}              │
└────────────┬────────────────────────────────────────────────────┘
             │
             ▼
┌─────────────────────────────────────────────────────────────────┐
│ src/audit.py — SHA-256 hash-chained audit log                   │
│   audit_logs/orchestrator_audit.jsonl                           │
│   verify_chain() proves no tampering                            │
└─────────────────────────────────────────────────────────────────┘
```

## Cache-first pattern

`data/generate.py` runs every demo query through the agent (or its
deterministic equivalent) at build time and writes
`data/cached_briefs.json`. The Streamlit UI reads from this cache on
**FIRE (cached)** so the demo recording is snappy. **FIRE (live)** fires
the real OpenAI tool-calling loop, with a 35s hero-call watchdog and a
deterministic fallback so the spinner never gets stuck.

## Real-data plug-in

OMNI-AGENT inherits real-data plug-in for free: each sibling app already
ships its own `data/load_real.py` documenting how to ingest its primary
dataset (DHA Medical Supply Network, NOAA NDFD, GCSS-MC, NASA Pred-Mx,
etc.). When a sibling's real-data path goes live, OMNI-AGENT's wrapper
inherits it automatically.

To swap the orchestrator's LLM to Kamiwaza on-prem:

```bash
export KAMIWAZA_BASE_URL=https://kamiwaza.local/api/v1
export KAMIWAZA_API_KEY=...
```

The shared client routes every chat completion through that endpoint —
zero code change in OMNI-AGENT.

## Scoring tie-back

- **Mission Impact (30%)**: Solves the operator's #1 complaint — "I have
  53 AI tools, which one do I fire first?" One question in, one brief out,
  full provenance.
- **Technical Innovation (25%)**: Real OpenAI tool-calling agent (multi-
  turn until `finish_reason='stop'`) brokering 14 sibling apps as governed
  tools; live tool-call trace; hash-chained SHA-256 audit log; cache-first
  hero-call pattern with watchdog + deterministic fallback.
- **Usability & Design (20%)**: Single Streamlit page; Kamiwaza dark theme
  verbatim from `BRAND` dict; 7 pre-loaded cross-domain demos; 3-click
  workflow (pick demo → fire → read fused brief).
- **Security & Sustainability (15%)**: KAMIWAZA env-var swap to on-prem;
  hash-chained audit log for SJA cross-app forensics; multi-provider via
  `shared.kamiwaza_client`; `data/load_real.py` documents the Tool-Garden
  ingestion path.
- **Team Collaboration (10%)**: Modular code (tools.py / agent.py /
  audit.py / app.py separation); reproducible synth via `data/generate.py`;
  full PRD; `STATUS.txt = done`.

---

**Powered by Kamiwaza** · OMNI-AGENT meta-orchestrator · governed access to 14 sibling apps · hash-chained audit
