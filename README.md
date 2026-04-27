# MDM 2026 — 34 LOGCOM Hackathon App Templates

Open-source AI app templates for the **Modern Day Marine 2026 LOGCOM AI Forum Hackathon** (27–30 April 2026, Walter E. Washington Convention Center).

**34 apps total — covering all 31 published datasets and all 17 published use cases on the LOGCOM portal.** Built as runnable templates so any MDM 2026 competitor can fork, plug in their own data, point at any LLM provider, and ship a credible entry in hours instead of weeks.

- **Wave 1 (apps 01-14):** one app per dataset on the LOGCOM portal (MARLIN through EMBER)
- **Wave 2 (apps 15-34):** one app per remaining dataset and one per published use case (VITALS through VOUCHER)

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

## Wave 1 — one app per LOGCOM dataset (14)

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

## Wave 2 — remaining datasets + every published use case (20)

| # | Folder | Codename | Dataset / Use Case |
|---|---|---|---|
| 15 | [15-vitals-medical-supply](15-vitals-medical-supply/) | **VITALS** | DHA RESCUE — blood-logistics decision support, hub-and-spoke risk |
| 16 | [16-watchtower-installation-cop](16-watchtower-installation-cop/) | **WATCHTOWER** | Installation Common Operating Picture (I-COP) Aggregator |
| 17 | [17-pallet-vision-drone-construction](17-pallet-vision-drone-construction/) | **PALLET-VISION** | AI Visual Quantification Engine (image → pallet/truck count) |
| 18 | [18-trace-class-i-ix-consumption](18-trace-class-i-ix-consumption/) | **TRACE** | LogTRACE — Class I-IX consumption rate estimator |
| 19 | [19-reorder-class-ix-forecast](19-reorder-class-ix-forecast/) | **REORDER** | Parts Demand Forecasting (Class IX for deployed MAGTF) |
| 20 | [20-queue-depot-throughput](20-queue-depot-throughput/) | **QUEUE** | Depot Maintenance Throughput Optimizer |
| 21 | [21-ghost-rf-fingerprinting](21-ghost-rf-fingerprinting/) | **GHOST** | RF Data Analysis (WiFi/Bluetooth pattern of life) |
| 22 | [22-stockroom-inventory-control](22-stockroom-inventory-control/) | **STOCKROOM** | Inventory Control Management |
| 23 | [23-cargo-last-mile-delivery](23-cargo-last-mile-delivery/) | **CARGO** | Last-mile expeditionary delivery — real OpenAI tool-calling agent |
| 24 | [24-chain-supply-chain-disruption](24-chain-supply-chain-disruption/) | **CHAIN** | Global supply-chain disruption forecaster for Marine PEOs |
| 25 | [25-hub-bts-multimodal-corridor](25-hub-bts-multimodal-corridor/) | **HUB** | Multimodal CONUS-to-POE corridor planner |
| 26 | [26-opengate-data-gov-rag](26-opengate-data-gov-rag/) | **OPENGATE** | Federal data discovery — production-shape RAG over data.gov |
| 27 | [27-embodied-xperience-10m](27-embodied-xperience-10m/) | **EMBODIED** | Egocentric Marine training simulator (multimodal vision) |
| 28 | [28-redline-cui-tagging](28-redline-cui-tagging/) | **REDLINE** | CUI Auto-Tagging Assistant (per-paragraph + audit chain) |
| 29 | [29-chorus-pa-audience-sim](29-chorus-pa-audience-sim/) | **CHORUS** | AI-Enabled Public Affairs Training & Audience Simulation |
| 30 | [30-guardian-browser-ai-governance](30-guardian-browser-ai-governance/) | **GUARDIAN** | Browser Based Agent Governance (Comet, manus.im detection) |
| 31 | [31-dispatch-ermp](31-dispatch-ermp/) | **DISPATCH** | ERMP — Emergency Response Modernization Project |
| 32 | [32-learn-lid](32-learn-lid/) | **LEARN** | Learning Intelligence Dashboard (PME / MOS school analytics) |
| 33 | [33-agora-multi-model-rbac](33-agora-multi-model-rbac/) | **AGORA** | Multi-model JIT context+role-aware AI support (ABAC RAG) |
| 34 | [34-voucher-dts-travel](34-voucher-dts-travel/) | **VOUCHER** | Travel Program Validation (DTS + Citi Manager reconciliation) |

Each folder has its own README with launch instructions, hero AI move, and real-data swap recipe. The full per-app rubric scorecard with rankings is in [JUDGING_V2.md](JUDGING_V2.md).

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
├── 01-marlin-ais-vessel-tracking/        # Wave 1: one folder per LOGCOM dataset
│   └── … through 14-ember-firms-ukraine/
└── 15-vitals-medical-supply/             # Wave 2: remaining datasets + every use case
    └── … through 34-voucher-dts-travel/
```

## Contributing

PRs welcome. If you adapt a template for your MDM entry and want to share back improvements, open a PR or fork freely.

## License

MIT — see [LICENSE](LICENSE). Use freely as templates for your own MDM hackathon entry, learning, or production work.
