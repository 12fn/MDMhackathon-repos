# MDM 2026 — 14 LOGCOM Hackathon App Templates

Open-source AI app templates for the **Modern Day Marine 2026 LOGCOM AI Forum Hackathon** (27–30 April 2026, Walter E. Washington Convention Center).

**14 apps, one per published USMC LOGCOM dataset.** Built as runnable templates so any MDM 2026 competitor can fork, plug in their own data, point at any LLM provider, and ship a credible entry in hours instead of weeks.

Every app is end-to-end working today: real LLM calls, real processing, polished UI, captioned demo video. The data is synthetic-but-plausible (per-app `data/generate.py`) — swap in your real dataset using [DATA_INGESTION.md](DATA_INGESTION.md).

> Built on / inspired by **[GAI](https://www.governmentacquisitions.com/) (Government Acquisitions, Inc.)** + **[Kamiwaza](https://www.kamiwaza.ai/)** — the federal AI integrator and the on-prem GenAI orchestration stack these apps deploy against. See [ATTRIBUTION.md](ATTRIBUTION.md).

## Quick start

```bash
git clone https://github.com/12fn/MDMhackathon-repos.git
cd MDMhackathon-repos
cp .env.example .env
# Edit .env — fill in ONE provider's vars (Kamiwaza / OpenAI / Anthropic / OpenRouter / any OpenAI-compat)
```

Then jump into any app folder and follow its README.

## Pick your LLM provider

The shared client (`shared/kamiwaza_client.py`) auto-detects from env vars. Set one:

| Provider | Env vars | Notes |
|---|---|---|
| **Kamiwaza** (recommended) | `KAMIWAZA_BASE_URL` + `KAMIWAZA_API_KEY` | On-prem / air-gapped / IL5/IL6. The reason these apps exist. |
| **OpenRouter** | `OPENROUTER_API_KEY` | Cloud, multi-model marketplace. |
| **OpenAI** | `OPENAI_API_KEY` | Cloud, fast iteration. |
| **Anthropic** | `ANTHROPIC_API_KEY` | Native Claude. Limited support for tool-calling apps. |
| **Any OpenAI-compat** | `LLM_BASE_URL` + `LLM_API_KEY` | Together.ai, Groq, Anyscale, vLLM, Ollama, your self-host. |

Full provider compatibility matrix and per-app notes in [DEPLOY.md](DEPLOY.md). To install Kamiwaza locally and point the apps at it, see [KAMIWAZA_SETUP.md](KAMIWAZA_SETUP.md).

## The 14 apps

| # | Folder | Codename | Dataset | Mission frame |
|---|---|---|---|---|
| 01 | [01-marlin-ais-vessel-tracking](01-marlin-ais-vessel-tracking/) | **MARLIN** | AIS Aug 2024 (NOAA / MarineCadastre) | Maritime dark-vessel + anomaly intel layer for INDOPACOM contested logistics |
| 02 | [02-forge-cwru-bearing-fault](02-forge-cwru-bearing-fault/) | **FORGE** | CWRU Bearing Fault | MTVR / JLTV / LAV bearing CBM+ predictive maintenance |
| 03 | [03-optik-coco8-vision-tm](03-optik-coco8-vision-tm/) | **OPTIK** | COCO8 (Ultralytics) | Maintainer photo → TM citation + NSN lookup (vision RAG) |
| 04 | [04-riptide-fima-nfip-flood-claims](04-riptide-fima-nfip-flood-claims/) | **RIPTIDE** | FIMA NFIP Redacted Claims | Installation flood-risk + dollar-denominated impact assessment |
| 05 | [05-meridian-fema-supply-chain-resilience](05-meridian-fema-supply-chain-resilience/) | **MERIDIAN** | FEMA Supply Chain Climate | MARFORPAC sustainment-node climate brief in OPORD format |
| 06 | [06-corsair-imb-pirate-attacks](06-corsair-imb-pirate-attacks/) | **CORSAIR** | Pirate Attacks 1993–2020 | Per-basin pirate-attack KDE forecast + maritime intel summary |
| 07 | [07-strider-goose-offroad-terrain](07-strider-goose-offroad-terrain/) | **STRIDER** | GOOSE Off-Road | Off-road terrain GO/NO-GO matrix per vehicle class |
| 08 | [08-raptor-hit-uav-thermal](08-raptor-hit-uav-thermal/) | **RAPTOR** | HIT-UAV Thermal IR | Drone IR INTREP from a multi-frame thermal window |
| 09 | [09-vanguard-afcent-logistics](09-vanguard-afcent-logistics/) | **VANGUARD** | AFCENT Logistics CSV | Natural-language TMR routing with real tool-calling agent loop |
| 10 | [10-sentinel-military-object-detection](10-sentinel-military-object-detection/) | **SENTINEL** | Military Object Detection | Vision-language PID + SHA-256 hash-chained audit log |
| 11 | [11-anchor-msi-world-port-index](11-anchor-msi-world-port-index/) | **ANCHOR** | NGA MSI WPI Pub 150 | Agentic RAG port-capability assessor for MPF / BIC planners |
| 12 | [12-weathervane-nasa-earthdata](12-weathervane-nasa-earthdata/) | **WEATHERVANE** | NASA Earthdata | Mission-window environmental brief for amphibious planners |
| 13 | [13-wildfire-nasa-firms](13-wildfire-nasa-firms/) | **WILDFIRE** | NASA FIRMS | Installation wildfire predictor + auto-MASCAL comms package |
| 14 | [14-ember-firms-ukraine](14-ember-firms-ukraine/) | **EMBER** | NASA FIRMS Ukraine 24-mo | Combat-fire signature analytics + SIPR-style ASIB brief |

Each folder has its own README with launch instructions, hero AI move, and real-data swap recipe.

## Use as templates

These are templates, not finished products. The intent is:

1. **Pick an app** that's closest to what you want to build.
2. **Plug in your real data** — see [DATA_INGESTION.md](DATA_INGESTION.md) for per-app recipes (most are < 30 min).
3. **Adapt the prompts and UI** for your hackathon entry.
4. **Pick your provider** — these apps work against Kamiwaza on-prem, any cloud LLM API, or even local models (vLLM, Ollama).

The shared scaffolding you get for free:
- `shared/kamiwaza_client.py` — multi-provider LLM client (5 providers auto-detected)
- `shared/synth.py` — synthetic-data utilities
- Brand kit (Kamiwaza dark theme constants in `BRAND` dict)
- Common patterns: streaming SSE, JSON-mode, vision-language, tool-calling, embeddings + RAG

## Repo layout

```
MDMhackathon-repos/
├── README.md                  # this file
├── DEPLOY.md                  # multi-provider config + compatibility per app
├── KAMIWAZA_SETUP.md          # install + connect to a Kamiwaza endpoint
├── DATA_INGESTION.md          # how to plug real data into each app
├── ATTRIBUTION.md             # credits to GAI, Kamiwaza, datasets, etc.
├── LICENSE                    # MIT
├── .env.example               # one env file, all providers
├── shared/
│   ├── kamiwaza_client.py     # multi-provider LLM client
│   └── synth.py               # synth-data utilities
└── 01-marlin-ais-vessel-tracking/   # one folder per app, each with own README
    └── … through 14-ember-firms-ukraine/
```

## Contributing

PRs welcome. If you adapt a template for your MDM entry and want to share back improvements, open a PR or fork freely.

## License

MIT — see [LICENSE](LICENSE). Use freely as templates for your own MDM hackathon entry, learning, or production work.
