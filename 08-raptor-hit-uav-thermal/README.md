# RAPTOR — drone IR INTREP from a multi-frame thermal window

Real-time Aerial Persistent Thermal Object Reasoning. A Streamlit app that turns a sliding window of thermal UAV frames into a Marine-grade INTREP an OOD or COC watchstander can act on in 30 seconds.

One of 14 templates in the **[MDM 2026 LOGCOM Hackathon](https://github.com/12fn/MDMhackathon-repos)** repo. Bucket B (drop frames into `data/frames/`).

## What it does

- **Heuristic CV pre-pass** classifies hot blobs (person / vehicle / fire / generator / exhaust plume) with OpenCV contours + intensity rules — fast, weights-free, transparent.
- **Vision call ingests current + 5 prior frames** plus the heuristic detection JSON in a single multi-image message, so the model reasons over a temporal window rather than one frame.
- **Drafts a 4-section INTREP**: SITREP / OBSERVED SIGNATURES, PATTERN OF LIFE / TREND, ASSESSED ACTIVITY (MEDIUM CONFIDENCE), RECOMMENDED ACTIONS & PIR REFINEMENT.
- **Structured JSON refinements** emit alongside the prose: `threat_level`, `observed_signatures[]`, `assessed_activity`, `recommended_actions[]`, `pir_refinements[]` — drop straight into a downstream tasker.

## Demo video

[`videos/raptor-demo.mp4`](videos/raptor-demo.mp4)

## Quick start

```bash
# Pick one provider — Kamiwaza is the recommended on-prem path
export KAMIWAZA_BASE_URL=https://kamiwaza.local/api/v1
export KAMIWAZA_API_KEY=$(cat /run/secrets/kw)
# …or any other provider supported by shared/kamiwaza_client.py
# (OPENAI_API_KEY, ANTHROPIC_API_KEY, OPENROUTER_API_KEY, LLM_BASE_URL+LLM_API_KEY)

pip install -r requirements.txt
python data/generate.py            # writes 30 synthetic thermal frames
streamlit run src/app.py --server.port 3008
```

Open <http://localhost:3008>.

## What's inside

```
08-raptor-hit-uav-thermal/
├── README.md
├── requirements.txt
├── data/
│   ├── generate.py            # synthetic 30-frame thermal scenario (seed=1776)
│   ├── frames/                # 30 grayscale 640x512 thermal frames
│   ├── frames_color/          # 30 inferno-LUT pseudo-color frames
│   ├── ground_truth.json      # per-frame box + class labels
│   └── mission.json           # mission scenario metadata
├── src/
│   ├── app.py                 # Streamlit entrypoint (port 3008)
│   ├── detect.py              # OpenCV blob detection + heuristic classify
│   └── intrep.py              # vision-language INTREP generator
└── videos/
    └── raptor-demo.mp4
```

## Hero AI move

**Multi-step vision-language reasoning over a temporal frame window.** A cheap, deterministic CV pass produces structured detections; a vision-language model then ingests the *current frame plus the five prior frames* in a single multi-image call, alongside the detection JSON, and writes the INTREP. Multi-image input over a temporal window is the bleeding edge of what production VLMs can do — and it is exactly what a watchstander does mentally when scrubbing a feed.

## Plug in real data (Bucket B)

Drop your own thermal frames into `data/frames/` named `frame_000.png`, `frame_001.png`, … (8-bit grayscale, any aspect ratio). The pipeline ingests **HIT-UAV** ([High-altitude Infrared Thermal Dataset for UAV-based Object Detection](https://github.com/suojiashun/HIT-UAV-Infrared-Thermal-Dataset)) unchanged, and works with any TIFF/PNG thermal source. Re-run `python data/generate.py` only if you also want fresh `frames_color/`, `ground_truth.json`, and `mission.json` — otherwise just refresh the colour mosaic by re-running the inferno LUT block.

## Adapt

- **Swap mission scenario** — edit the tracks and `PHASE_NARRATIVES` in `data/generate.py`, or rewrite `data/mission.json` to point at your installation, sensor, and tasking.
- **Change blob classification heuristics** — `src/detect.py::_classify` is one tidy function of `(area, aspect, mean_i, peak_i)`; tune thresholds or swap to a YOLO-tiny call without touching anything else.
- **Modify INTREP format** — `SYSTEM_PROMPT` and the JSON schema hint in `src/intrep.py` define section headers and the structured payload; both are plain strings.

## Built on Kamiwaza

Inference routes through `shared/kamiwaza_client.py`, an OpenAI-compatible client that auto-detects Kamiwaza, OpenAI, Anthropic, OpenRouter, or any OpenAI-compat endpoint from env vars. Point at a Kamiwaza-deployed VLM for the on-prem / IL5 / IL6 posture; nothing in app code changes.

See [ATTRIBUTION.md](../ATTRIBUTION.md) at the repo root.
