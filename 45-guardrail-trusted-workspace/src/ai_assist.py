"""GUARDRAIL — Role-aware AI assistant (RAG + ABAC).

The Marine asks a question. The AI assistant:
  1. Treats every paragraph in the open workspace as a retrievable chunk.
  2. Scores cosine-style relevance via a cheap keyword overlap (no live
     embedding call required for the demo — keeps recordings snappy).
  3. Calls authorize_paragraph() per chunk; ABAC-denied chunks go to the
     "denied docs" panel with the deny reason.
  4. Renders an answer using ONLY the authorized chunks, with [doc-¶] cites.

The hero call is wrapped in a wall-clock watchdog with a deterministic
fallback so the live demo never sits frozen.
"""
from __future__ import annotations

import os
import re
import sys
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutTimeout
from pathlib import Path

APP_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = APP_DIR.parents[1]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(APP_DIR))

from src.abac import authorize_paragraph  # noqa: E402

_TOK = re.compile(r"[a-zA-Z0-9]+")


def _tokens(s: str) -> set[str]:
    return {t.lower() for t in _TOK.findall(s) if len(t) > 2}


def score_chunk(query: str, text: str) -> float:
    qt = _tokens(query)
    if not qt:
        return 0.0
    tt = _tokens(text)
    if not tt:
        return 0.0
    inter = qt & tt
    return len(inter) / (len(qt) ** 0.5 * len(tt) ** 0.5)


def retrieve(persona: dict, query: str, all_doc_paragraphs: list[dict],
             k: int = 4) -> tuple[list[dict], list[dict]]:
    """Return (cited_chunks, denied_chunks).

    all_doc_paragraphs is a list of dicts that include doc_id, paragraph_index,
    paragraph_text, recommended_marking, caveats_recommended.
    """
    scored: list[tuple[float, dict]] = []
    for ch in all_doc_paragraphs:
        s = score_chunk(query, ch.get("paragraph_text", ""))
        scored.append((s, ch))
    scored.sort(key=lambda t: -t[0])

    cited: list[dict] = []
    denied: list[dict] = []
    for s, ch in scored:
        ok, reason = authorize_paragraph(persona, ch)
        if ok:
            if len(cited) < k:
                cited.append({**ch, "_score": round(s, 3)})
        else:
            if len(denied) < 12 and s > 0:
                denied.append({**ch, "_score": round(s, 3), "_deny_reason": reason})
    return cited, denied


ANSWER_SYS = (
    "You are GUARDRAIL, a USMC LOGCOM workspace AI assistant. You answer the "
    "Marine's question using ONLY the paragraph snippets provided. Each "
    "snippet is one the platform has already authorized for this persona's "
    "clearance, role, and need-to-know — never quote unauthorized content "
    "even if you remember it from training. Cite snippets inline as "
    "[doc_id ¶ N]. If the persona's role doesn't permit the action, say so "
    "plainly. Keep answers under 160 words."
)


def render_answer(persona: dict, query: str, cited: list[dict],
                  *, hero: bool = False, timeout: int = 18) -> str:
    if not cited:
        return (
            f"You ({persona.get('name','?')}, {persona.get('billet','?')}) "
            f"don't have access to any workspace paragraphs that match this "
            f"question under your current clearance "
            f"({persona.get('clearance','?')}) and role set "
            f"({', '.join(persona.get('abac',{}).get('roles', [])) or '—'}). "
            f"Request the appropriate role from your S-1 or run the query "
            f"under a persona that holds it."
        )

    snippets = "\n\n".join(
        f"[{c['doc_id']} ¶{c['paragraph_index']}] ({c.get('recommended_marking','UNCLASSIFIED')})\n"
        f"{c['paragraph_text']}"
        for c in cited
    )
    msgs = [
        {"role": "system", "content": ANSWER_SYS},
        {"role": "user", "content": (
            f"Persona: {persona.get('name','?')} ({persona.get('rank','?')}, "
            f"{persona.get('billet','?')}, clearance {persona.get('clearance','?')}).\n\n"
            f"Question: {query}\n\n--- Authorized paragraphs ---\n{snippets}\n--- End ---\n"
            "Answer in plain operator prose with inline [doc_id ¶N] citations."
        )},
    ]

    def _baseline() -> str:
        parts = [f"**For {persona.get('name','?')} ({persona.get('billet','?')}):**"]
        for c in cited:
            parts.append(
                f"- **[{c['doc_id']} ¶{c['paragraph_index']}]** "
                f"({c.get('recommended_marking','UNCLASSIFIED')}) — "
                f"{c['paragraph_text'][:240]}…"
            )
        cites = ", ".join(f"[{c['doc_id']} ¶{c['paragraph_index']}]" for c in cited)
        parts.append(f"\nCited: {cites}.")
        return "\n".join(parts)

    try:
        from shared.kamiwaza_client import chat
    except Exception:
        return _baseline()

    def _call() -> str:
        model = os.getenv("LLM_HERO_MODEL") if hero else os.getenv("LLM_PRIMARY_MODEL")
        return chat(msgs, model=model or None, temperature=0.3)

    try:
        with ThreadPoolExecutor(max_workers=1) as ex:
            return ex.submit(_call).result(timeout=timeout)
    except (FutTimeout, Exception):
        return _baseline()
