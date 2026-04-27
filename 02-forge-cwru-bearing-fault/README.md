# FORGE — predictive bearing-failure for the Marine ground fleet

> Forecasted Onset of Rotational-Gear Endpoint. Vibration in, commander brief out.

One of 14 application templates in the [MDM 2026 Hackathon Templates](https://github.com/12fn/MDMhackathon-repos) repo. Fork it, point it at your data, ship.

## What it does

- Reads a 12 kHz drive-end accelerometer trace for a USMC ground vehicle (MTVR / JLTV / LAV).
- Runs a hand-crafted-feature RandomForest classifier to call the fault class (Healthy / Inner Race / Outer Race / Ball) and a severity-driven RUL estimator.
- Computes the envelope spectrum, lights up the bearing characteristic frequencies (BPFO / BPFI / BSF / FTF), and renders a spectrogram image.
- Hands the spectrogram + classifier + RUL + 6-month maintenance log + a `lookup_part_availability(NSN)` tool call to a multimodal LLM, which returns a structured JSON commander recommendation an E-5 maintenance chief can act on in 60 seconds.

## Demo video

[`videos/forge-demo.mp4`](videos/forge-demo.mp4)

## Quick start

```bash
# 1. Set provider env vars (Kamiwaza-first)
export KAMIWAZA_BASE_URL=https://kamiwaza.local/api/v1
export KAMIWAZA_API_KEY=...
# Or use any OpenAI-compatible provider — see ../DEPLOY.md

# 2. Install
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# 3. Generate synthetic vibration corpus + maintenance log
python data/generate.py

# 4. Run
streamlit run src/app.py --server.port 3002
```

Multi-provider support (Kamiwaza, OpenAI, OpenRouter, Anthropic, custom OpenAI-compatible endpoints) is handled by `shared/kamiwaza_client.py` — no app code changes needed. See `../DEPLOY.md`.

## What's inside

```
02-forge-cwru-bearing-fault/
├── README.md                    — this file
├── requirements.txt             — python deps (streamlit, sklearn, scipy, openai, anthropic, ...)
├── src/
│   ├── app.py                   — Streamlit operator console (single-page UI)
│   ├── agent.py                 — multimodal LLM hero call: spectrogram + classifier + log + tool → JSON brief
│   ├── classifier.py            — RandomForest fault classifier + severity-driven RUL estimator
│   └── signal_proc.py           — FFT, Hilbert envelope spectrum, characteristic-frequency math
├── data/
│   ├── generate.py              — synthetic CWRU-shape vibration corpus generator
│   ├── precompute_briefs.py     — caches LLM commander briefs to disk for snappy demos
│   ├── vibration_corpus.npz     — generated 12 kHz / 1 s windows / 4 classes × 50 samples
│   ├── vehicles.json            — three test assets (MTVR / JLTV / LAV)
│   ├── maintenance_log.json     — synthetic 6-month work-order history per vehicle
│   ├── parts_inventory.json     — synthetic MCLB Albany NSN inventory for the agent's tool call
│   └── cached_briefs.json       — precomputed agent output (used when LLM is slow / offline)
└── videos/
    └── forge-demo.mp4           — captioned demo recording
```

## Hero AI move

The single densest AI call lives in `src/agent.py::commander_recommendation`:

- **Vision:** spectrogram PNG of the live vibration trace, sent inline as a data URL.
- **Classifier output:** fault class, confidence, full per-class probability vector.
- **Telemetry:** RUL estimate, severity index, vehicle metadata.
- **Unstructured context:** 6-month free-text maintenance work-order log.
- **Tool call:** `lookup_part_availability(nsn)` resolves stock at MCLB Albany + alt depots.
- **Output:** strict JSON with `recommendation`, `urgency`, `rationale_bullets`, `commander_brief`, `parts_action`, `predicted_failure_mode` — directly consumable by a downstream GCSS-MC integration.

That's vision + structured prediction + tool use + log reasoning + JSON-mode output, all in one round trip.

## Plug in real data

FORGE is a **Bucket B** app per `../DATA_INGESTION.md` — drop files in a folder.

- **Real source:** Case Western Reserve University Bearing Data Center (12 kHz drive-end accelerometer) or any equivalent 12 kHz vibration time series.
- **Format:** single-column CSV of float samples (one sample per row), recorded at 12,000 Hz.
- **Where:** drop files in `data/signals/<asset_id>.csv` (e.g. `data/signals/MTVR-2491.csv`).
- **Loader change:** edit the `pick_signal_for_class` path in `src/app.py` to pull from `data/signals/` instead of the synthetic `vibration_corpus.npz`. The classifier, envelope spectrum, RUL estimator, and agent all run unchanged on any 12 kHz vibration signal.

## Adapt for your hackathon entry

- **Different vehicle classes / assets:** edit `VEHICLES` in `data/generate.py` and the `vehicles.json` it produces. The asset roster, NSNs, units, and maintenance log all flow from there.
- **Different bearing geometry:** edit `N_BALLS`, `BALL_DIA_IN`, `PITCH_DIA_IN`, `F_SHAFT` in `data/generate.py` and `characteristic_freqs()` in `src/signal_proc.py` to compute BPFO / BPFI / BSF / FTF for your bearing.
- **Different fault taxonomy:** the `CLASSES` constant + the `synth_signal()` per-class branch in `data/generate.py` define the synthetic faults; the classifier and agent will pick up new classes once the corpus is regenerated.
- **Different sensor:** any 1-D time series at any sample rate works — change `FS` and `WIN_SEC` in `data/generate.py` and the dependent constants in `src/signal_proc.py`.
- **Different agent prompt / schema:** `src/agent.py::SYSTEM_PROMPT` defines the decision tree and the JSON schema the LLM emits. Tune for your domain.

## Built on Kamiwaza

This template runs on [Kamiwaza](https://www.kamiwaza.ai/) for air-gapped, IL5/IL6-ready on-prem inference, and falls back to any OpenAI-compatible endpoint for off-network demos. See `../ATTRIBUTION.md` for credits and dataset citations.

MIT licensed.
