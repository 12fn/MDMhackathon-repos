# SENTINEL — explainable mil-asset PID with cryptographic chain-of-custody

Vision-language Positive Identification of foreign and friendly military platforms with analyst-style numbered reasoning, releasability classification, and a SHA-256 hash-chained audit log that survives SJA / IG / classification review.

One of 14 templates in the **[MDM 2026 LOGCOM Hackathon](https://github.com/12fn/MDMhackathon-repos)** repo. Bucket B (drop images into `data/imagery/`).

## What it does

- **Drop an image** of a foreign or US military platform into the Gradio UI.
- **A vision-language model** returns `{asset_class, country_of_origin, platform_type, confidence, distinguishing_features, similar_known_examples, releasability}` grounded against a 30-platform reference library (armor / rotary / fixed-wing / UAS / naval).
- **Analyst-style numbered reasoning** explains the PID step-by-step — each step cites the visible cue and what it implies / rules out — so an E-5 to O-3 can defend the call months later.
- **SHA-256 hash-chained audit entry** appends to `audit_logs/sentinel_audit.jsonl`: image hash, decision hash, prompt hash, prev-entry hash, and a CONCUR / NON-CONCUR analyst attestation chained on top — immutable chain-of-custody for every VLM decision.

## Demo video

[`videos/sentinel-demo.mp4`](videos/sentinel-demo.mp4)

## Quick start

```bash
# Pick one provider — Kamiwaza is the recommended on-prem path
export KAMIWAZA_BASE_URL=https://kamiwaza.local/api/v1
export KAMIWAZA_API_KEY=$(cat /run/secrets/kw)
# …or any other provider supported by shared/kamiwaza_client.py
# (OPENAI_API_KEY, ANTHROPIC_API_KEY, OPENROUTER_API_KEY, LLM_BASE_URL+LLM_API_KEY)

pip install -r requirements.txt
python data/generate.py            # builds reference_library.csv + 8 sample tiles
python src/app.py                  # Gradio on :3010
```

Open <http://localhost:3010>.

## What's inside

```
10-sentinel-military-object-detection/
├── README.md
├── requirements.txt
├── src/
│   └── app.py                     # Gradio app: vision PID + reasoning + audit chain
├── data/
│   ├── generate.py                # synthetic reference library + sample tile generator
│   ├── reference_library.csv      # 30 known platforms (T-72, M1A2, MQ-9, Bayraktar, …)
│   ├── sample_manifest.json       # 8 demo images + Wikimedia source URLs
│   └── imagery/                   # (Bucket B) drop your real frames here
├── audit_logs/
│   └── .gitkeep                   # sentinel_audit.jsonl is appended at runtime
└── videos/
    └── sentinel-demo.mp4
```

## Hero AI move

**VLM Positive ID + analyst-style reasoning trace + immutable cryptographic audit chain — ready for SJA / IG / classification review.** Every PID is a real vision-language call grounded against a structured reference library; every decision is hashed (SHA-256 over the input image, the prompt, and the JSON decision payload) and chained to the previous entry's hash. The analyst types a note and clicks CONCUR / NON-CONCUR; that attestation is itself chained. The full chain is one `jsonl` file you can hand to a reviewer with a one-line `sha256sum` integrity check.

## Plug in real data (Bucket B)

Drop any image into `data/imagery/` (or directly into the Gradio UI) — JPG, PNG, sensor capture, screen grab, anything PIL can decode. The pipeline works on any image input. To plug in the real **Military Object Detection Dataset** (~4 GB, classification labels for armor, rotary, fixed-wing, UAS, and naval platforms), drop the label hierarchy into `data/reference_library.csv` (the schema is already compatible) and the model grounds against your taxonomy on the next run.

## Adapt

- **Swap the reference library** — replace the rows in `data/reference_library.csv` with your own asset taxonomy (`asset_class, country_of_origin, type, distinguishing_features`); the system prompt grounds against whatever you load.
- **Change releasability tiers** — edit the `releasability` enum in `PID_INSTRUCTIONS` (`src/app.py`) to match your marking guide (e.g. `SECRET//NOFORN`, `TS//SI`, coalition-release strings).
- **Upgrade the chain to HMAC** — swap `hashlib.sha256` for `hmac.new(key, msg, sha256)` in `src/app.py` and load a per-deployment key for cryptographic-grade tamper detection (the chain structure is unchanged).

## Built on Kamiwaza

Inference routes through `shared/kamiwaza_client.py`, an OpenAI-compatible client that auto-detects Kamiwaza, OpenAI, Anthropic, OpenRouter, or any OpenAI-compat endpoint from env vars. Point at a Kamiwaza-deployed VLM (Qwen2.5-VL / InternVL recommended on-prem) for the IL5 / IL6 posture; nothing in app code changes — the SHA-256 audit chain, releasability calls, and reasoning trace run identically on NIPR, SIPR, and JWICS.

See [ATTRIBUTION.md](../ATTRIBUTION.md) at the repo root.

## Sec note

The cryptographic audit pattern is the actual production-grade differentiator here. Computer vision is only useful in defense if you can defend the decision; SENTINEL builds a real chain-of-custody for VLM decisions at inference time, not bolted on after. Every PID and every analyst attestation is hashed and linked — break any link and the chain stops verifying.
