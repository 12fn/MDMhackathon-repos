# Attribution

This portfolio of 14 apps was built for the **Modern Day Marine 2026 LOGCOM AI Forum Hackathon** (27–30 April 2026, Walter E. Washington Convention Center).

## Built on / inspired by

- **[GAI — Government Acquisitions, Inc.](https://www.governmentacquisitions.com/)** — the federal AI integrator behind the Kamiwaza-on-prem deployments these apps are designed for. GAI's role in standing up Kamiwaza inside USMC / DoD enclaves is the reason the on-prem swap pattern in `shared/kamiwaza_client.py` is the central design choice of every app in this repo.
- **[Kamiwaza](https://www.kamiwaza.ai/)** — the on-prem GenAI orchestration stack these apps deploy against. Every app uses an OpenAI-compatible client pointed at Kamiwaza by default; the integration pattern is lifted from the [`kamiwaza-ai/USMC-cursor`](https://github.com/kamiwaza-ai) reference and the Kamiwaza SDK's `client.openai.get_client()` helper. Brand colors, logo, and the on-prem positioning are Kamiwaza's.
- Every "Hero AI" call in every app is a real LLM completion (no mocks). Default model identifiers are `gpt-4o-mini` and `gpt-4o` (passed verbatim to the API surface — Kamiwaza, OpenRouter, etc. map these to whatever weights are deployed server-side).

## Datasets

Each app uses synthetic-but-plausible data shaped to match a published USMC LOGCOM hackathon dataset. The synthetic generators live in each app's `data/generate.py`. To plug in real data, see [`DATA_INGESTION.md`](DATA_INGESTION.md).

Real dataset sources (links in each app's README):

- **AIS** — NOAA / [MarineCadastre.gov](https://marinecadastre.gov/) public AIS archive (MARLIN)
- **CWRU Bearing Fault** — Case Western Reserve University Bearing Data Center (FORGE)
- **COCO8** — Ultralytics object-detection mini-set (OPTIK)
- **FIMA NFIP** — [FEMA OpenFEMA NFIP Redacted Claims v2](https://www.fema.gov/openfema-data-page/fima-nfip-redacted-claims-v2) (RIPTIDE)
- **FEMA Supply Chain Climate Resilience** — Qlik / FEMA OpenFEMA (MERIDIAN)
- **Pirate Attacks 1993–2020** — IMB Piracy Reporting Centre / NGA ASAM (CORSAIR)
- **GOOSE** — German Outdoor and Offroad Dataset (STRIDER)
- **HIT-UAV** — High-altitude Infrared Thermal Dataset for UAV-based Object Detection (RAPTOR)
- **AFCENT Logistics** — sponsored by HQ U.S. Air Forces Central, Shaw AFB (VANGUARD)
- **Military Object Detection** — published USMC PID corpus (SENTINEL)
- **NGA MSI World Port Index Pub 150** — National Geospatial-Intelligence Agency (ANCHOR)
- **NASA Earthdata** — MERRA-2, MODIS, GPM IMERG, GHRSST, WAVEWATCH III (WEATHERVANE)
- **NASA FIRMS** — Fire Information for Resource Management System (WILDFIRE, EMBER)

## License

Code: MIT (see [LICENSE](LICENSE)). Use freely as templates for your own MDM hackathon entry, learning, or production work.

Trademarks (Kamiwaza, USMC seal, etc.) belong to their respective owners and are referenced here for context only.

## Author

Built solo overnight by **Finn Norris** as a portfolio entry. Re-released here as MIT-licensed templates so other MDM 2026 competitors can fork, adapt, or learn from any app.

PRs welcome.
