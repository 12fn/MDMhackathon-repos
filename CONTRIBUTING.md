# Contributing

PRs welcome from any MDM 2026 competitor (or anyone else).

## Quick PR flow

```bash
git clone https://github.com/12fn/MDMhackathon-repos.git
cd MDMhackathon-repos
cp .env.example .env  # fill in your provider
git checkout -b your-improvement
# … make changes …
git commit -m "your improvement"
gh pr create
```

## What I'd love to see

- **Real-data loaders** — if you've plugged a real LOGCOM dataset into one of these templates, send the loader back as a PR. Someone else will save hours.
- **Provider adapters** — first-class Replicate, AWS Bedrock, Azure OpenAI, Vertex AI support in `shared/kamiwaza_client.py`.
- **New apps** — if there's a published USMC dataset I missed and you want to add a template, follow the structure of any existing app folder.
- **Bug fixes** — anything that breaks under your provider, file an issue or PR.

## Style

- Python: keep it readable, no aggressive type discipline. The shared client uses Pyright-friendly hints; apps don't have to.
- Per-app code: one app, one folder, one README. Keep dependencies in the app's `requirements.txt`.
- Synthetic data generators are seeded with `random.Random(1776)` — keep it reproducible.

## Getting help

Open an issue at https://github.com/12fn/MDMhackathon-repos/issues
