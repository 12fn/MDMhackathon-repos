# Setting up Kamiwaza

Every app in this repo is built to run against a **Kamiwaza-deployed model** as the primary path. This doc walks you through getting Kamiwaza installed and pointing the apps at it.

If you'd rather use a cloud LLM (OpenAI, Anthropic, OpenRouter, etc.), skip this doc and see [`DEPLOY.md`](DEPLOY.md) instead — every app supports those too.

## Official Kamiwaza resources

- **Docs site:** https://docs.kamiwaza.ai/
- **Quickstart:** https://docs.kamiwaza.ai/quickstart
- **Installation guide:** https://docs.kamiwaza.ai/installation/installation_process
- **Get in touch / sign up:** https://www.kamiwaza.ai/get-started
- **Support:** https://www.kamiwaza.ai/support

The docs site is the source of truth. The summary below is current as of Kamiwaza v0.9.3 — if anything below disagrees with the official docs, trust the docs.

## TL;DR — install, start, verify

### Supported platforms
- **Linux:** Ubuntu 22.04 / 24.04, RHEL 9
- **macOS:** Community Edition only
- **Windows:** Community Edition via WSL2

### Prerequisites
- ≥ 16 GB RAM
- Stable internet for the initial model download
- Ubuntu/RHEL recommended for production; macOS / WSL2 fine for local dev

### Install (Ubuntu x86_64 example)

```bash
sudo apt-get update
curl -LO https://packages.kamiwaza.ai/deb/kamiwaza_v0.9.3_noble_x86_64.deb
sudo dpkg -i kamiwaza_v0.9.3_noble_x86_64.deb
sudo apt-get install -f
```

### Install (RHEL 9)

```bash
curl -LO https://packages.kamiwaza.ai/rpm/kamiwaza_v0.9.3_rhel9_x86_64.rpm
sudo -E KAMIWAZA_ACCEPT_LICENSE=yes dnf install ./kamiwaza_v0.9.3_rhel9_x86_64.rpm
```

### Install (Windows)
Download the MSI installer from https://docs.kamiwaza.ai/installation/installation_process and run it. Restart if prompted.

### Start the service

```bash
kamiwaza stop
kamiwaza start
kamiwaza status
```

### Verify
- Frontend UI: `https://localhost`
- API docs: `http://localhost/api/docs`
- Default login: username `admin`, password `kamiwaza`

### Deploy your first model
From the Kamiwaza UI, deploy the **Qwen3-0.6B-GGUF** model to start (495 MB, CPU-friendly, fast first-load). You can swap to bigger weights once you've confirmed everything's wired.

## Pointing this repo's apps at your Kamiwaza endpoint

Once Kamiwaza is running and you've deployed at least one model, set these env vars in `.env` at the repo root:

```bash
KAMIWAZA_BASE_URL=https://localhost/api/v1     # your Kamiwaza endpoint (or wherever it lives)
KAMIWAZA_API_KEY=your-kamiwaza-key             # see Kamiwaza UI → Settings → API Keys
LLM_PRIMARY_MODEL=Qwen3-0.6B                   # or whatever model name you deployed
LLM_FALLBACK_MODELS=Qwen3-0.6B
```

Then jump into any app folder and follow its README. Smoke-test the connection from the repo root:

```bash
python -c "from shared.kamiwaza_client import chat, PROVIDER; print(f'Provider: {PROVIDER}'); print(chat([{'role':'user','content':'one word: ready'}]))"
```

If it prints a one-word answer, every app in this repo will run against your Kamiwaza endpoint. No code changes required — just env vars.

## Going from local dev → on-prem production

The whole design point of these apps: build/test against cloud (OpenAI, OpenRouter), then flip to Kamiwaza on-prem with no code change. See [`DEPLOY.md`](DEPLOY.md) for the multi-provider matrix.

```bash
# Local dev with cloud:
unset KAMIWAZA_BASE_URL
export OPENAI_API_KEY=sk-...

# Production on-prem:
unset OPENAI_API_KEY
export KAMIWAZA_BASE_URL=https://kamiwaza.your-enclave.local/api/v1
export KAMIWAZA_API_KEY=...
```

Same code, same prompts, different backend.

## Need help?

- **Kamiwaza-specific questions** (install, deployment, model loading, performance): the official docs at https://docs.kamiwaza.ai/ and the Kamiwaza support page at https://www.kamiwaza.ai/support are your first stop.
- **Hackathon / template questions** (anything about adapting these 14 apps for your MDM 2026 entry, plugging in real LOGCOM data, swapping providers): reach out to **Finn Norris** or anyone on the **GAI (Government Acquisitions, Inc.)** / **Kamiwaza** team — we're at the event and happy to walk you through any of it.
- **Bugs in this repo specifically:** open an issue at https://github.com/12fn/MDMhackathon-repos/issues or send a PR.

GAI handles the federal-side AI integration work that put Kamiwaza inside USMC enclaves in the first place. They (and the Kamiwaza team) will be present at MDM 2026 — just ask.
