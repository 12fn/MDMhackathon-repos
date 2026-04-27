# CORSAIR — per-basin pirate-attack KDE forecast + maritime intel summary

> Template #06 of 14 in the [MDM 2026 Hackathon Templates](https://github.com/12fn/MDMhackathon-repos). Mono-Streamlit. Bucket A (IMB / NGA pirate-attack incidents).

## What it does

- Fits a per-basin **2-D Gaussian KDE** on historical pirate-attack lat/lon, weighted by recency + month-of-year seasonality, and projects a **30-day forward risk grid** on a Folium dark-tile heatmap.
- Lets the operator pick the **theater of focus** (Gulf of Aden, Strait of Malacca, Gulf of Guinea, Sulu Sea, Caribbean/Venezuelan, South China Sea, or all basins) and tune the forecast horizon.
- Generates a **SIPR-format Maritime Intel Summary (MIS)** narrative — BLUF, threat picture, assessed actor, MOA pattern shifts, recommended route deviations, confidence — plus a JSON-mode **indicator board** (threat level, hotspot labels, indicators to watch).
- **Drilldown:** click a hotspot and the side panel surfaces the 3 most relevant historical incidents that informed the forecast — full date, vessel type, attack type, and narrative.

## Demo video

[`videos/corsair-demo.mp4`](videos/corsair-demo.mp4)

## Quick start

```bash
# 1. Configure your provider (see repo-root .env.example for all options)
export KAMIWAZA_BASE_URL=https://kamiwaza.local/api/v1
export KAMIWAZA_API_KEY=your-kamiwaza-key
# or fall back to: OPENAI_API_KEY / OPENROUTER_API_KEY / ANTHROPIC_API_KEY

# 2. Install + run
pip install -r requirements.txt
python data/generate.py                           # writes data/pirate_attacks.csv
streamlit run src/app.py --server.port 3006
# open http://localhost:3006
```

## What's inside

```
06-corsair-imb-pirate-attacks/
├── README.md
├── requirements.txt
├── .env.example
├── data/
│   ├── generate.py              # synthetic ASAM-shape generator (seed 1776)
│   ├── pirate_attacks.csv       # 3,000 rows
│   └── pirate_attacks.json      # 200-row sample
├── src/
│   ├── app.py                   # Streamlit UI (map + KPIs + AI panel)
│   ├── forecaster.py            # KDE + seasonality + trend delta
│   └── agent.py                 # MIS narrative + JSON indicator board
└── videos/
    └── corsair-demo.mp4
```

## Hero AI move

A lightweight **scikit-learn 2-D Gaussian KDE per basin** (Silverman-ish bandwidth heuristic, 60×60 grid) produces a normalized risk surface and top-5 hotspots with NMS spacing. The expected attack count is scaled by recency (5y rolling rate) × month-of-year seasonality. Then a **dual LLM call** (both via the shared multi-provider client):

1. `agent.generate_mis(...)` — long-form **SIPR-format MIS narrative** with the canonical six (U)-marked sections, grounded only in the inputs. The hero call passes `model="gpt-5.4"` so on-prem Kamiwaza can route the marquee call to its highest-fidelity deployed model.
2. `agent.generate_indicator_board(...)` — JSON-mode call returning a strict schema (threat level, hotspots with sector labels, MOA shift, route deviations, indicators to watch) ready for the ops board.

## Plug in real data

CORSAIR is **Bucket A** — built around the **IMB Piracy Reporting Centre** / **NGA Worldwide Threats to Shipping (ASAM)** mirror. The synthetic CSV mirrors the ASAM schema; swap it for the real export by replacing `data/pirate_attacks.csv` with a CSV that has these columns:

| column | type | notes |
|---|---|---|
| `datetime` | ISO-8601 | incident UTC timestamp |
| `lat`, `lon` | float | decimal degrees |
| `attack_type` | str | Boarded / Attempted / Hijacked / Fired Upon / Suspicious Approach |
| `vessel_type` | str | Bulk Carrier / Tanker / Container / Fishing / etc. |
| `basin` | str | one of the keys in `forecaster.BASIN_BBOX`, or extend the dict |
| `narrative` | str | free-text incident summary (fed to the LLM) |
| `month`, `year` | int | derived from `datetime` (used for seasonality) |

Public mirror: `kaggle.com/datasets/dryad/global-maritime-pirate-attacks` (1993-2020 ASAM mirror).

## Adapt

- **Swap basins** — edit `BASIN_BBOX` in `src/forecaster.py` (lat/lon bounding box per theater).
- **Adjust seasonality weighting** — tune `seasonality()` in `forecaster.py` (currently a normalized monthly-rate ratio); swap in a Fourier or holiday-aware weight if your dataset shows different cyclicity.
- **Change MIS format** — the `SYSTEM_MIS` prompt in `src/agent.py` defines the section headings and tradecraft style. Rename, re-order, or add sections (e.g. CCIRs, NAI/TAI, OPLAN cross-refs) without touching the forecaster.
- **Tune KDE bandwidth** — pass `bandwidth=` to `fit_kde()` if the default Silverman-ish heuristic over- or under-smooths your basin.

## Built on Kamiwaza

Inference is routed through the shared multi-provider client (`shared/kamiwaza_client.py`) — Kamiwaza on-prem by default, with OpenAI / OpenRouter / Anthropic / any-OpenAI-compat fallbacks for local dev. See [`ATTRIBUTION.md`](../ATTRIBUTION.md) at the repo root for full credits.
