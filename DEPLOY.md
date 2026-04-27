# Deploy guide — pick a provider and go

Every app in this repo uses the same shared client (`shared/kamiwaza_client.py`) which auto-detects your LLM provider from environment variables. Set the env vars for one provider and every app runs.

## Quick reference

| Provider | Required env vars | When to pick |
|---|---|---|
| **Kamiwaza** (recommended) | `KAMIWAZA_BASE_URL`, `KAMIWAZA_API_KEY` | On-prem / air-gapped / IL5/IL6 / regulated environments. The reason these apps exist. |
| **OpenRouter** | `OPENROUTER_API_KEY` | Cloud, want to A/B across many models, single API key. |
| **OpenAI** | `OPENAI_API_KEY` | Cloud, fastest local-dev iteration. |
| **Anthropic (Claude)** | `ANTHROPIC_API_KEY` | Cloud, Claude-specific reasoning. *Limited support for vision / tool-calling / JSON apps.* |
| **Any OpenAI-compat** | `LLM_BASE_URL`, `LLM_API_KEY` | Together.ai, Groq, Anyscale, Fireworks, vLLM, Ollama, LM Studio, your own self-host. |

The client picks the first one it sees in env, in this priority order:

```
KAMIWAZA_BASE_URL → OPENROUTER_API_KEY → LLM_BASE_URL+LLM_API_KEY → ANTHROPIC_API_KEY → OPENAI_API_KEY
```

To force a specific one, set `LLM_PROVIDER=kamiwaza|openrouter|custom|anthropic|openai`.

## Setup

```bash
git clone https://github.com/12fn/MDMhackathon-repos.git
cd MDMhackathon-repos
cp .env.example .env
# edit .env, fill in ONE provider's vars
```

Then jump into any app folder and follow its README.

## Provider compatibility per app

Some apps need features beyond plain chat (vision input, JSON-mode, tool-calling). Use this table when picking a provider:

| App | Needs | Best on |
|---|---|---|
| MARLIN | Streaming chat + JSON-mode | Kamiwaza, OpenRouter, OpenAI |
| FORGE | Multimodal vision + JSON + tool-calling | Kamiwaza, OpenAI (Anthropic limited) |
| OPTIK | Multimodal vision + JSON + embeddings | Kamiwaza, OpenAI (Anthropic limited) |
| RIPTIDE | Streaming + JSON-mode | Kamiwaza, OpenRouter, OpenAI, Anthropic |
| MERIDIAN | JSON-mode + long-form generation | Any provider |
| CORSAIR | Chat + JSON | Any provider |
| STRIDER | Multimodal vision + JSON | Kamiwaza, OpenAI, Anthropic |
| RAPTOR | Multi-image vision (5+ frames) | Kamiwaza, OpenAI, Anthropic |
| VANGUARD | OpenAI-compat **tool-calling loop** | Kamiwaza, OpenRouter, OpenAI |
| SENTINEL | Multimodal vision + JSON | Kamiwaza, OpenAI, Anthropic |
| ANCHOR | JSON + **embeddings** + chat | Kamiwaza, OpenAI, OpenRouter |
| WEATHERVANE | JSON + chat | Any provider |
| WILDFIRE | JSON-mode | Any provider |
| EMBER | JSON + chat | Any provider |

Apps that need **embeddings** (ANCHOR, OPTIK): if you choose Anthropic, also set `EMBEDDING_BASE_URL` + `EMBEDDING_API_KEY` to any OpenAI-compat endpoint — the client will route embeddings separately.

Apps with **tool-calling** (VANGUARD): require an OpenAI-compatible provider. Anthropic's tool format is incompatible with this app's loop — use Kamiwaza, OpenRouter, or OpenAI.

## Model name overrides

The shared client passes model names like `gpt-4o-mini` and `gpt-4o` straight to your provider. Most providers accept these (Kamiwaza maps them server-side; OpenRouter routes to the named model; OpenAI uses them directly). To use a different model name for your provider:

```bash
export LLM_PRIMARY_MODEL=meta-llama/llama-3.3-70b-instruct
export LLM_FALLBACK_MODELS=meta-llama/llama-3.1-8b-instruct
```

Anthropic uses its own model names — set `ANTHROPIC_MODEL=claude-3-5-sonnet-latest` (default) or `claude-opus-4-5`, etc.

## Verifying your setup

After setting env vars, smoke-test the client:

```bash
python -c "from shared.kamiwaza_client import chat, PROVIDER; print(f'Provider: {PROVIDER}'); print(chat([{'role':'user','content':'one word: ready'}]))"
```

If it prints a one-word answer, every app in this repo will run against your provider.

## Going from cloud → on-prem

The whole point of the Kamiwaza-first design: build/test against cloud (OpenRouter, OpenAI), then flip to Kamiwaza on-prem with no code changes:

```bash
# Cloud dev:
unset KAMIWAZA_BASE_URL
export OPENROUTER_API_KEY=sk-or-...

# Production on-prem:
unset OPENROUTER_API_KEY
export KAMIWAZA_BASE_URL=https://kamiwaza.local/api/v1
export KAMIWAZA_API_KEY=...
```

Same code. Same prompts. Different backend. That's the bet.
