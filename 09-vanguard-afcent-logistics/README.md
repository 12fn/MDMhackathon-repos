# VANGUARD

**Natural-language TMR routing with a real tool-calling agent loop.**

VANGUARD is a Streamlit app that turns one English sentence into a ranked, defensible Course of Action for a CENTCOM Transportation Movement Request — air, sea, or ground — by driving a real OpenAI-compatible function-calling loop over a typed multimodal routing graph.

## What it does

- **Planner types one sentence** like *"Move 40 pallets of MREs from Camp Arifjan to Erbil within 72 hours, lowest fuel burn."*
- **Agent calls 4 typed tools** in a real `chat.completions` loop until `finish_reason="stop"` — `list_assets`, `compute_route`, `check_feasibility`, `compare_options`.
- **Live reasoning sidebar** streams every tool call, arguments, result summary, and latency as the agent fires them.
- **3-card UI** lays out air-direct / tactical-air / sealift / ground-convoy options with sorties, hours, fuel cost, distance, and risk; the recommended option pulses neon green on a dark PyDeck theater map.

## Demo video

[`videos/vanguard-demo.mp4`](videos/vanguard-demo.mp4) — ~90 s walkthrough.

## Quick start

```bash
cp .env.example .env
# Point at any OpenAI-compatible endpoint:
#   KAMIWAZA_BASE_URL=https://<your-kamiwaza-host>/v1
#   KAMIWAZA_API_KEY=<token>
# Or fall back to OPENROUTER_API_KEY / OPENAI_API_KEY / LLM_BASE_URL+LLM_API_KEY.

pip install -r requirements.txt
python data/generate.py        # writes bases.csv / assets.csv / graph.json
streamlit run src/app.py --server.port 3009
```

Open http://localhost:3009 and click **Plan TMR**.

## Provider note

This app uses an **OpenAI-compatible tool-calling loop** (`chat.completions.create(tools=[...], tool_choice="auto")`). Pick **Kamiwaza**, **OpenRouter**, **OpenAI**, or any other OpenAI-compat endpoint (vLLM, Together, Groq, Anyscale, Ollama, etc.). Anthropic's tool-use format differs from OpenAI's and is **not** supported by this app's loop — use one of the OpenAI-compat options above.

## What's inside

```
09-vanguard-afcent-logistics/
├── data/
│   ├── generate.py     # seeded synthesizer (random.Random(1776))
│   ├── bases.csv       # 50 CENTCOM nodes (air/sea/land/joint)
│   ├── assets.csv      # 200 transport assets (C-17, C-130J, KC-46, M1083, T-AKE, ...)
│   └── graph.json      # adjacency list, ~1.4k directed multimodal edges
├── src/
│   ├── tools.py        # 4 tools + OpenAI tool-calling JSON schemas
│   ├── agent.py        # multi-turn chat.completions loop, tool_choice="auto"
│   └── app.py          # Streamlit UI (dark theme + PyDeck map)
├── videos/
│   └── vanguard-demo.mp4
├── requirements.txt
└── README.md
```

## Hero AI move

A **real multi-turn tool-calling agent loop**. The model decides, in order, to call:

1. `list_assets(theater="CENTCOM", ...)` — scope inventory.
2. `compute_route(origin, destination, mode)` — Dijkstra over the typed graph.
3. `check_feasibility(asset_class, pallets, deadline_hours, route)` — sorties, hours, fuel, risk.
4. `compare_options(origin, destination, pallets, deadline_hours, objective)` — score and rank 3 candidate options.

Every call is dispatched against a local `TOOL_REGISTRY`, the result is appended back into the message history, and the next turn lets the model see what it learned. Each call streams to the sidebar in real time so a judge can watch the agent reason.

## Plug in real data

This is **Bucket A** — the AFCENT Logistics Data (Air / Land / Sea) TMR archive. To swap the synthetic CSVs for the real AFCENT TMR feed, replace `data/bases.csv` and `data/assets.csv` and rebuild `data/graph.json`. The expected canonical TMR fields are:

| Required column | Maps to |
|---|---|
| `TMR ID` | request identifier |
| `origin` | resolved via `_resolve_base_code()` in `src/tools.py` |
| `destination` | resolved via `_resolve_base_code()` in `src/tools.py` |
| `cargo class` | matched against asset `class` in `check_feasibility` |
| `weight` / pallet count | drives `sorties_required = ceil(pallets / cap_pallets)` |
| `mode` | one of `air` / `sea` / `land` / `road` / `any` / `intermodal` |
| `priority` | feeds the `objective` weighting (`fastest`/`cheapest`/`safest`/`balanced`) |
| `requested ship date` | drives `deadline_hours` |

See `src/tools.py` for the canonical field names and the `compute_route` / `check_feasibility` signatures.

## Adapt

- **Swap the base list** — replace `BASES_RAW` in `data/generate.py` (or drop in your own `bases.csv`).
- **Add a new tool** — write a function, register it in `TOOL_REGISTRY`, and add its JSON schema to `TOOL_SCHEMAS` in `src/tools.py`. The agent loop picks it up automatically.
- **Change route optimizer constraints** — edit `_shortest_path` in `src/tools.py` (Dijkstra), the per-mode `LEG_OVERHEAD_HR` / `FUEL_COST_PER_LB` / `MODE_RISK` constants, or the candidate set in `compare_options`.
- **Re-tune scoring** — adjust the objective-keyed weight tuples in `compare_options`.

## Built on Kamiwaza

Built on [Kamiwaza](https://www.kamiwaza.ai/) — see [ATTRIBUTION.md](../ATTRIBUTION.md) at the repo root.
