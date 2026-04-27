"""Multi-provider LLM client used by every app in this repo.

Auto-detects the active provider from environment variables. Order of preference:

  1. KAMIWAZA_BASE_URL      → Kamiwaza on-prem (OpenAI-compatible surface)
  2. OPENROUTER_API_KEY     → OpenRouter (OpenAI-compatible surface)
  3. LLM_BASE_URL + LLM_API_KEY → any other OpenAI-compatible endpoint
                              (Together.ai, Groq, Anyscale, vLLM, Ollama, …)
  4. ANTHROPIC_API_KEY      → Anthropic Messages API (chat / chat_json only;
                              vision and tool-calling apps prefer an OpenAI-
                              compat provider)
  5. OPENAI_API_KEY         → OpenAI direct

Override the auto-detection with `LLM_PROVIDER=kamiwaza|openai|openrouter|
anthropic|custom`.

The function names `chat`, `chat_json`, `embed` are stable — every app calls
them, so swapping providers requires zero code changes inside the apps.

If you're a hackathon competitor: copy this whole repo, set the env vars for
your provider of choice, and every app runs against your endpoint.
"""
from __future__ import annotations

import json as _json
import os
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterable

try:
    from dotenv import load_dotenv
    for p in (Path.cwd() / ".env", Path(__file__).resolve().parent.parent / ".env"):
        if p.exists():
            load_dotenv(p)
            break
except ImportError:
    pass

from openai import OpenAI


# ─────────────────────────────────────────────────────────────────────────────
# Defaults — override via env vars
# ─────────────────────────────────────────────────────────────────────────────
PRIMARY_MODEL = os.getenv("LLM_PRIMARY_MODEL") or os.getenv(
    "OPENAI_PRIMARY_MODEL", "gpt-4o-mini"
)
FALLBACKS = [
    m.strip()
    for m in (
        os.getenv("LLM_FALLBACK_MODELS")
        or os.getenv("OPENAI_FALLBACK_MODELS", "gpt-4o-mini,gpt-4o")
    ).split(",")
    if m.strip()
]


# ─────────────────────────────────────────────────────────────────────────────
# Provider detection
# ─────────────────────────────────────────────────────────────────────────────
def _detect_provider() -> str:
    explicit = (os.getenv("LLM_PROVIDER") or "").strip().lower()
    if explicit:
        return explicit
    if os.getenv("KAMIWAZA_BASE_URL"):
        return "kamiwaza"
    if os.getenv("OPENROUTER_API_KEY"):
        return "openrouter"
    if os.getenv("LLM_BASE_URL") and os.getenv("LLM_API_KEY"):
        return "custom"
    if os.getenv("ANTHROPIC_API_KEY"):
        return "anthropic"
    if os.getenv("OPENAI_API_KEY"):
        return "openai"
    raise RuntimeError(
        "No LLM provider configured. Set one of:\n"
        "  • KAMIWAZA_BASE_URL + KAMIWAZA_API_KEY  (Kamiwaza on-prem)\n"
        "  • OPENROUTER_API_KEY                    (OpenRouter cloud)\n"
        "  • LLM_BASE_URL + LLM_API_KEY            (any OpenAI-compat endpoint)\n"
        "  • ANTHROPIC_API_KEY                     (Anthropic Claude)\n"
        "  • OPENAI_API_KEY                        (OpenAI direct)\n"
        "Or override with LLM_PROVIDER=<name>. See DEPLOY.md for details."
    )


PROVIDER = _detect_provider()


def _provider_config() -> tuple[str | None, str]:
    """(base_url, api_key) for the OpenAI-compat path. Returns ("", "") for Anthropic."""
    if PROVIDER == "kamiwaza":
        url = os.getenv("KAMIWAZA_BASE_URL")
        key = os.getenv("KAMIWAZA_API_KEY") or "kamiwaza"
        return url, key
    if PROVIDER == "openrouter":
        url = os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
        key = os.getenv("OPENROUTER_API_KEY", "")
        return url, key
    if PROVIDER == "custom":
        return os.getenv("LLM_BASE_URL"), os.getenv("LLM_API_KEY", "")
    if PROVIDER == "openai":
        return None, os.getenv("OPENAI_API_KEY", "")
    if PROVIDER == "anthropic":
        return "", ""  # handled separately
    raise RuntimeError(f"Unknown LLM_PROVIDER: {PROVIDER!r}")


@lru_cache(maxsize=1)
def get_client():
    """Return the live SDK client for the active provider."""
    if PROVIDER == "anthropic":
        try:
            from anthropic import Anthropic
        except ImportError as e:
            raise RuntimeError(
                "Anthropic provider selected but `anthropic` package not installed. "
                "Run: pip install anthropic"
            ) from e
        return Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
    base_url, api_key = _provider_config()
    if not api_key:
        raise RuntimeError(
            f"Provider {PROVIDER!r} selected but no API key found in environment."
        )
    return OpenAI(base_url=base_url, api_key=api_key)


# ─────────────────────────────────────────────────────────────────────────────
# Anthropic message translation
# ─────────────────────────────────────────────────────────────────────────────
def _split_system(messages: list[dict[str, Any]]) -> tuple[str, list[dict[str, Any]]]:
    """Anthropic takes `system` as a top-level param, not a message."""
    system_parts: list[str] = []
    rest: list[dict[str, Any]] = []
    for m in messages:
        if m.get("role") == "system":
            content = m.get("content")
            if isinstance(content, str):
                system_parts.append(content)
        else:
            rest.append(m)
    return "\n\n".join(system_parts), rest


def _anthropic_chat(messages: list[dict[str, Any]], *, model: str | None,
                    temperature: float, max_tokens: int | None, **kw) -> str:
    client = get_client()
    system, msgs = _split_system(messages)
    # Anthropic requires alternating user/assistant; coalesce consecutive same-role
    cleaned: list[dict[str, Any]] = []
    for m in msgs:
        role = "assistant" if m.get("role") == "assistant" else "user"
        content = m.get("content", "")
        if cleaned and cleaned[-1]["role"] == role and isinstance(content, str) and isinstance(cleaned[-1]["content"], str):
            cleaned[-1]["content"] = cleaned[-1]["content"] + "\n\n" + content
        else:
            cleaned.append({"role": role, "content": content})
    chosen_model = model or os.getenv("ANTHROPIC_MODEL") or "claude-3-5-sonnet-latest"
    resp = client.messages.create(  # type: ignore[union-attr]
        model=chosen_model,
        system=system or "You are a helpful assistant.",
        messages=cleaned,  # type: ignore[arg-type]
        max_tokens=max_tokens or 4096,
        temperature=temperature,
    )
    # Concat any text blocks
    out_parts = [getattr(b, "text", "") for b in resp.content if getattr(b, "type", None) == "text"]
    return "".join(out_parts)


# ─────────────────────────────────────────────────────────────────────────────
# Public API — apps call these
# ─────────────────────────────────────────────────────────────────────────────
def chat(
    messages: list[dict[str, Any]],
    *,
    model: str | None = None,
    temperature: float = 0.4,
    max_tokens: int | None = None,
    response_format: dict | None = None,
    tools: list | None = None,
    **kw,
) -> str:
    """One-shot chat with model fallback. Returns the assistant message string.

    Provider-aware: routes to Anthropic Messages API when ANTHROPIC_API_KEY is the
    active provider; OpenAI-compatible (Kamiwaza, OpenRouter, OpenAI, custom) for
    the rest. Tool-calling and JSON-mode work best on the OpenAI-compatible path —
    apps that need them should set an OpenAI-compat provider (Kamiwaza is the
    primary recommendation).
    """
    if PROVIDER == "anthropic":
        return _anthropic_chat(messages, model=model, temperature=temperature,
                               max_tokens=max_tokens)

    client = get_client()
    chain: Iterable[str] = [model] if model else [PRIMARY_MODEL, *FALLBACKS]
    last_err: Exception | None = None
    for m in chain:
        try:
            kwargs: dict[str, Any] = {"model": m, "messages": messages, "temperature": temperature, **kw}
            if max_tokens:
                kwargs["max_tokens"] = max_tokens
            if response_format:
                kwargs["response_format"] = response_format
            if tools:
                kwargs["tools"] = tools
            resp = client.chat.completions.create(**kwargs)  # type: ignore[union-attr]
            return resp.choices[0].message.content or ""
        except Exception as e:  # noqa: BLE001
            last_err = e
            continue
    raise RuntimeError(f"All models failed. Last error: {last_err}")


def chat_json(messages: list[dict], *, schema_hint: str = "", **kw) -> dict:
    """Chat with JSON-mode response_format. schema_hint can describe expected keys.

    On Anthropic (no native JSON mode), prompts the model to return JSON and
    parses defensively.
    """
    if schema_hint and not any("json" in (m.get("content") or "").lower() for m in messages):
        messages = [
            *messages,
            {"role": "user", "content": f"Respond as JSON. Schema hint: {schema_hint}"},
        ]
    if PROVIDER == "anthropic":
        # Force JSON via prompt; Anthropic returns text we have to parse
        messages = messages + [{
            "role": "user",
            "content": "Output only valid JSON. No prose, no code fences, no markdown."
        }]
        raw = chat(messages, **kw)
        # Strip code fences if the model added them anyway
        s = raw.strip()
        if s.startswith("```"):
            s = s.split("\n", 1)[1] if "\n" in s else s
            if s.endswith("```"):
                s = s[: -3]
            s = s.strip()
            if s.startswith("json"):
                s = s[4:].lstrip()
        return _json.loads(s)
    raw = chat(messages, response_format={"type": "json_object"}, **kw)
    return _json.loads(raw)


def embed(texts: list[str], model: str = "text-embedding-3-small") -> list[list[float]]:
    """Embed a batch of texts.

    Anthropic does not provide first-party embeddings — apps that need embeddings
    should set an OpenAI-compatible provider (Kamiwaza, OpenAI, OpenRouter, etc.).
    Override the embedding provider independently with EMBEDDING_PROVIDER /
    EMBEDDING_BASE_URL / EMBEDDING_API_KEY env vars if you want to mix
    (e.g. Anthropic for chat, OpenAI for embeddings).
    """
    if PROVIDER == "anthropic":
        emb_url = os.getenv("EMBEDDING_BASE_URL")
        emb_key = os.getenv("EMBEDDING_API_KEY") or os.getenv("OPENAI_API_KEY")
        if not emb_key:
            raise RuntimeError(
                "Anthropic provider has no native embeddings. Set EMBEDDING_BASE_URL "
                "+ EMBEDDING_API_KEY (any OpenAI-compatible endpoint) or set "
                "OPENAI_API_KEY as a fallback embedding source."
            )
        client = OpenAI(base_url=emb_url, api_key=emb_key)
    else:
        client = get_client()
    resp = client.embeddings.create(input=texts, model=model)  # type: ignore[union-attr]
    return [d.embedding for d in resp.data]


# ─────────────────────────────────────────────────────────────────────────────
# Brand constants — apps use these for theming
# ─────────────────────────────────────────────────────────────────────────────
BRAND = {
    "primary": "#00BB7A",
    "primary_hover": "#0DCC8A",
    "neon": "#00FFA7",
    "deep_green": "#065238",
    "bg": "#0A0A0A",
    "surface": "#0E0E0E",
    "surface_high": "#111111",
    "border": "#222222",
    "muted": "#6A6969",
    "text_dim": "#7E7E7E",
    "logo_url": "https://www.kamiwaza.ai/hubfs/logo-light.svg",
    "tagline_default": "Orchestration Without Migration. Execution Without Compromise.",
    "footer": "Powered by Kamiwaza",
}
