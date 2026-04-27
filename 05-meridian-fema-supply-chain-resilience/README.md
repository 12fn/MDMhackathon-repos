# MERIDIAN — daily MARFORPAC sustainment-node climate brief in OPORD format

Template **#05 / 14** — [MDM 2026 Hackathon Templates](https://github.com/12fn/MDMhackathon-repos).

## What it does

- **Ingests** a corpus of NOAA / JTWC / FEMA / INDOPACOM-style reports across a 60-day window.
- **Scores** every MARFORPAC sustainment node 0-10 with a structured-JSON LLM call (`chat_json`).
- **Renders** a NetworkX + Plotly supply-line topology with risk-colored nodes and edges.
- **Drafts** a one-page USMC OPORD-format brief (PARA 1-5) — top-3 named threats and recommended COA per CCDR.

## Demo video

[`videos/meridian-demo.mp4`](videos/meridian-demo.mp4)

## Quick start

```bash
# 1. install
python3 -m pip install -r requirements.txt

# 2. point at Kamiwaza (or any OpenAI-compatible endpoint)
export KAMIWAZA_BASE_URL=https://kamiwaza.local/api/v1
export KAMIWAZA_API_KEY=...
# dev fallback (laptop only):
# export OPENAI_API_KEY=sk-...

# 3. seed synthetic data + run
python data/generate.py && streamlit run src/app.py --server.port 3005
```

Open http://localhost:3005, click **GENERATE TODAYS BRIEF**, try **Inject incident** to re-rank.

## What's inside

```
05-meridian-fema-supply-chain-resilience/
├── README.md
├── requirements.txt
├── .env.example
├── data/
│   ├── generate.py            # seeded synthetic data generator
│   ├── nodes.json             # MARFORPAC sustainment nodes
│   ├── edges.json             # supply-line topology
│   ├── reports/*.md           # 30 NOAA / JTWC / FEMA / J2 / G-4 reports
│   ├── reports_manifest.json
│   └── cached_brief.json      # warm-start brief
├── src/
│   ├── agent.py               # two-step LLM pipeline (scoring + OPORD)
│   ├── graph.py               # NetworkX + Plotly topology
│   └── app.py                 # Streamlit UI (port 3005)
└── videos/
    └── meridian-demo.mp4
```

## Hero AI move

Two-step LLM agent on the shared Kamiwaza client:

1. **`chat_json`** scores **all nodes 0-10** with a strict schema —
   `{node_id, risk_index, top_threat, confidence, rationale}` — so the topology
   colors and the ranked node card list always render.
2. **Hero `chat`** call drafts a one-page **OPORD PARA 1-5** brief (Situation,
   Mission, Execution, Sustainment, Command & Signal) naming the top-3 threats
   and a recommended COA per CCDR. Uses `model="gpt-5.4"` for narrative polish,
   with timeout-bounded fallback to the mini chain so the demo window is never
   blocked.

## Plug in real data

**Bucket A** — designed against the **FEMA Supply Chain Climate Resilience**
indicator dataset (and the related FEMA Supply Chain Resilience Guidance PDF).

Required columns to swap synthetic for real:

| Column            | Type    | Example          |
|-------------------|---------|------------------|
| node ID           | string  | `APRA`           |
| lat               | float   | `13.443`         |
| lon               | float   | `144.660`        |
| type              | string  | `port` / `runway`|
| criticality       | int 1-10| `10`             |
| climate exposure  | float   | `0.0 - 1.0`      |
| primary peril     | string  | `typhoon`        |

Drop the FEMA CSV into `data/`, point `data/generate.py` at it (one
`pandas.read_csv` swap), and the rest of the pipeline is unchanged.

## Adapt

- **Swap node list** — edit `data/nodes.json` (any sustainment / logistics graph works: AFCENT, EUCOM, AFRICOM).
- **Change CCDR scope** — INDOPACOM today; AFRICOM, EUCOM, NORTHCOM are one column edit.
- **Modify OPORD format** — swap PARA 1-5 for FRAGO, WARNORD, or a civilian SITREP in `src/agent.py`.
- **Plug different intel feeds** — replace the synthetic generator with NOAA marine forecasts, JTWC TC warnings, INDOPACOM J2 RSS, or any classified feed mounted on the Kamiwaza Distributed Data Engine.

## Built on Kamiwaza

Every LLM call routes through `shared.kamiwaza_client` — auto-detects Kamiwaza
vLLM endpoints, OpenAI, or Anthropic. See [ATTRIBUTION.md](../ATTRIBUTION.md)
in the repo root for full credits.
