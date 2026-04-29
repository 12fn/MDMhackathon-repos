# DRONE-DOMINANCE — Full UAS Encounter Lifecycle

**Hackathon agent #42 · Tier A · MDM 2026 LOGCOM AI Forum**
Streamlit mono on **port 3042**.

> The whole UAS-vs-FOB problem on one screen — friendly fleet quantification,
> hostile RF + thermal + visual triple-fusion, ROE-graded engagement ladder,
> hero encounter brief, egocentric AAR.

## Pitch

Modern Day Marine 2026 added **Counter-UAS** as an informal use case on top of
the published "AI Visual Quantification" and "RF Data Analysis" use cases. A
LOGCOM watch officer at a forward installation has seconds to (a) know what
own-platforms are airborne, (b) classify the inbound contact across multiple
sensor modalities, (c) pick an engagement option that matches the rule-set,
and (d) get coached on the call after the fact.

DRONE-DOMINANCE collapses all four into one screen, on one Kamiwaza-deployed
LLM, with **three multimodal calls fused in a single workflow** for the
detection step alone. CUAS decisions stay in the SCIF — set
`KAMIWAZA_BASE_URL` and the same code runs on-prem with zero changes.

## Hero AI move

1. **Friendly fleet** — visual quantification of own UAS platforms (Skydio
   X10D, Parrot Anafi USA, Teal Black Widow, Switchblade 300, Puma AE).
2. **Hostile detection — three sensor modalities fuse**:
   - **RF** spectrogram-as-image classifier (DroneRF-B Spectra-shape) →
     controller signature match against a 30-row DroneRC-shape DB
   - **Thermal IR** detector (HIT-UAV-shape) → person / vehicle / UAS via
     heuristic blob detection + multimodal vision-language confirmation
   - **Visual EO** confirmation (Drone Dataset UAV-shape) → silhouette count,
     platform shape (quad / fixed-wing / swarm)
   - Triple-fusion via Bayesian product → `{detection_class,
     confidence_per_modality, fused_confidence, contributing_sensors}`
3. **Engagement decision** — `chat_json` graded options: monitor / EW jam
   (sector or omni) / kinetic / spoof-GPS / link takeover / SkyTracker log /
   escalate-FOC. ROE-aware (10 USC 130i, DoDD 3000.09, JCO-CUAS, JP 3-01).
4. **Hero `chat`** ("gpt-5.4", 35 s wall-clock, **cache-first**) writes the
   **UAS Encounter Brief** — full SITREP citing only authorized references.
5. **Egocentric AAR** (Xperience-10M-shape) — operator's helmet-cam still +
   typed decision are scored by the multimodal model against doctrine.
   SNCO-tonal hot-wash (correct / tactical / hesitation / risky · 0-100).

## Run

```bash
# from repo root
pip install -r apps/42-drone-dominance/requirements.txt
# (re)generate synthetic data — first run also pre-computes hero briefs
SKIP_PRECOMPUTE=1 python apps/42-drone-dominance/data/generate.py     # data only
python apps/42-drone-dominance/data/generate.py                       # data + LLM cache

streamlit run apps/42-drone-dominance/src/app.py \
  --server.port 3042 --server.headless true \
  --server.runOnSave false --server.fileWatcherType none \
  --browser.gatherUsageStats false
```

Open http://localhost:3042 — the demo path runs cold-open → AAR in ~75 s.

## Real-data plug-in

Five real datasets drop in via `data/load_real.py`:

| Dataset                              | Env var                  | Notes |
|---|---|---|
| **Drone Dataset (UAV)** — Kaggle visual photos | `REAL_VISUAL_DIR` | one PNG per scenario id |
| **HIT-UAV** — thermal IR frames | `REAL_THERMAL_DIR` | PNG + paired `*.bboxes.json` |
| **DroneRF-B Spectra** — RF spectrogram tiles | `REAL_RF_SPECTRA_DIR` | `.png` (and optional `.npy`) |
| **Drone RC RF Identification** — controller signatures CSV | `REAL_RC_CSV` | columns: id, manufacturer, controller, band_ghz, hopping, protocol |
| **Xperience-10M** — egocentric helmet-cam stills | `REAL_XPERIENCE_DIR` | one PNG per AAR scenario |

Same pipeline; only the ingestion path changes. Real make/models referenced
include DJI Mavic 3, Parrot Anafi USA, Skydio 2+, Autel EVO; protocols
include OcuSync 3+, Lightbridge 2, FHSS, LoRa CSS, WiFi 802.11n.

## Provider compatibility

The shared client auto-detects the active provider in this priority:

1. `KAMIWAZA_BASE_URL` — Kamiwaza on-prem (the recommended posture for any CUAS workflow)
2. `OPENROUTER_API_KEY` — OpenRouter
3. `LLM_BASE_URL` + `LLM_API_KEY` — any OpenAI-compat (vLLM, Together, Groq, Ollama, …)
4. `ANTHROPIC_API_KEY` — Anthropic
5. `OPENAI_API_KEY` — OpenAI direct (used in this demo)

The three multimodal calls + the engagement-decision `chat_json` call all
prefer an OpenAI-compatible vision-capable provider. The hero brief is
text-only and works on every provider.

## Files

```
apps/42-drone-dominance/
├── README.md                    # this file
├── PRD.md                       # spec + scoring tie-back
├── data/
│   ├── generate.py              # synth + features + fusion + decision + cache
│   ├── load_real.py             # 5-dataset real-data plug-in
│   ├── scenarios.json           # 6-scenario manifest
│   ├── rf_id_db.csv             # 30 RF controller signatures
│   ├── engagement_options.json  # 8 ROE-graded options
│   ├── friendly_fleet.json      # Marine UAS inventory
│   ├── aar_frames.json          # 4 egocentric AAR scenarios
│   └── cached_briefs.json       # pre-computed hero briefs (cache-first)
├── sample_spectra/              # 6 RF spectrograms (.png + .npy)
├── sample_thermal/              # 6 thermal IR frames + bbox JSON
├── sample_visual/               # 6 visual EO photos
├── xperience_aar_frames/        # 4 egocentric helmet-cam stills
├── src/
│   ├── agent.py                 # triple-fuse + decision + brief + AAR
│   └── app.py                   # Streamlit UI on port 3042
├── tests/record-demo.spec.ts    # Playwright recorder
├── playwright.config.ts
├── demo-script.md               # narrator copy
├── demo-script.json             # cue timeline emitted by Playwright
├── videos/drone-dominance-demo.mp4
├── requirements.txt
├── .env.example
└── STATUS.txt
```

## Scoring tie-back

- **Mission Impact (30%)** — UAS-vs-FOB is the LOGCOM force-protection problem
  Marines stamped onto MDM 2026 informally. Touches both the published "AI
  Visual Quantification" use case (friendly fleet) and "RF Data Analysis" use
  case (RF spectrogram classifier), then layers Counter-UAS lifecycle on top.
- **Technical Innovation (25%)** — three multimodal calls in one workflow,
  Bayesian-product fusion shown transparently, `chat_json` ROE ladder, hero
  text brief, vision-language AAR scoring on a helmet-cam still. Five distinct
  AI calls per scenario.
- **Usability & Design (20%)** — Kamiwaza dark theme; one screen, one path;
  cache-first so the hero brief never spinner-stalls; per-call watchdog so a
  slow modality can't sink the workflow.
- **Security & Sustainability (15%)** — `KAMIWAZA_BASE_URL` flips the whole
  stack on-prem; CUAS decisions stay in the SCIF; multi-provider via shared
  client; real-data plug-in via `data/load_real.py`.
- **Team Collaboration (10%)** — modular code, README + PRD + demo-script,
  reproducible synth data (seed 1776), real-data swap recipe documented for
  all 5 datasets.
