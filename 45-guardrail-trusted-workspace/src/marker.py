"""GUARDRAIL — CUI marker (live + cached).

Mirrors the REDLINE pattern but with the GUARDRAIL taxonomy that includes
SECRET / TS//SCI tiers (so the ABAC layer has something to clamp). All live
calls are watchdog-protected with deterministic fallback.
"""
from __future__ import annotations

import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutTimeout
from pathlib import Path
from typing import Any

APP_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = APP_DIR / "data"
REPO_ROOT = APP_DIR.parents[1]
sys.path.insert(0, str(REPO_ROOT))


def load_taxonomy() -> dict:
    return json.loads((DATA_DIR / "markings_taxonomy.json").read_text())


def load_cached_markings() -> dict:
    p = DATA_DIR / "per_doc_markings.json"
    if not p.exists():
        return {}
    return json.loads(p.read_text())


def split_paragraphs(text: str) -> list[str]:
    parts = [p.strip() for p in text.replace("\r\n", "\n").split("\n\n")]
    return [p for p in parts if p]


# Reuse the deterministic rule set from the generator
from data.generate import _rule_paragraph as _rule  # noqa: E402

PARAGRAPH_SCHEMA_HINT = (
    "Object with EXACT keys (no synonyms): "
    "recommended_marking (string), rationale (1-line string), "
    "trigger_phrases (array of strings), caveats_recommended (array of strings), "
    "confidence (float 0-1)."
)


def _llm_paragraph(paragraph: str, taxonomy: dict, idx: int) -> dict:
    from shared.kamiwaza_client import chat_json
    cats = "\n".join(f"- {c['marking']}: {c['description']}" for c in taxonomy["categories"])
    sys_p = (
        "You are GUARDRAIL, a CUI marking analyst supporting USMC LOGCOM under "
        "DoDM 5200.01 Vol 2 and 32 CFR Part 2002. For one paragraph, recommend "
        "the single most-appropriate CUI/classified marking, rationale, trigger "
        "phrases, recommended caveats, and confidence 0-1. Be conservative."
    )
    user_p = (
        f"MARKING CATEGORIES:\n{cats}\n\nPARAGRAPH (index {idx}):\n\"\"\"\n{paragraph}\n\"\"\"\n\nReturn JSON only."
    )
    return chat_json(
        [{"role": "system", "content": sys_p}, {"role": "user", "content": user_p}],
        schema_hint=PARAGRAPH_SCHEMA_HINT,
        temperature=0.1,
        max_tokens=400,
    )


def _normalize(res: dict) -> dict:
    aliases = {
        "recommended_marking": ["recommended_marking", "marking", "CUI_marking", "Marking"],
        "rationale": ["rationale", "Rationale"],
        "trigger_phrases": ["trigger_phrases", "triggers"],
        "caveats_recommended": ["caveats_recommended", "caveats", "recommended_caveats"],
        "confidence": ["confidence", "Confidence"],
    }
    out: dict = {}
    for canon, opts in aliases.items():
        for o in opts:
            if o in res and res[o] not in (None, ""):
                out[canon] = res[o]
                break
    out.setdefault("recommended_marking", "UNCLASSIFIED")
    out.setdefault("rationale", "")
    out.setdefault("trigger_phrases", [])
    out.setdefault("caveats_recommended", [])
    out.setdefault("confidence", 0.0)
    return out


def mark_paragraph(paragraph: str, taxonomy: dict, idx: int, *, timeout: int = 12) -> dict:
    """Live LLM-backed paragraph marking with deterministic watchdog fallback."""
    try:
        with ThreadPoolExecutor(max_workers=1) as ex:
            raw = ex.submit(_llm_paragraph, paragraph, taxonomy, idx).result(timeout=timeout)
        return _normalize(raw)
    except (FutTimeout, Exception) as e:  # noqa: BLE001
        out = _rule(paragraph)
        out["_fallback"] = f"deterministic baseline ({type(e).__name__})"
        return out
