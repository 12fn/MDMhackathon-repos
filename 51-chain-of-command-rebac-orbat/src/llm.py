"""CHAIN-OF-COMMAND — LLM narration of the ReBAC graph-walk.

The engine produces a deterministic verdict + path. The LLM's job is to
narrate that path in plain operator prose so the demo reads like a human
rationale ("ALLOW via OPCON path: A Co 1/8 attached to 2/2…") rather than
graph machinery.

Cache-first pattern (from Phase 1 lessons): pre-rendered narrations live
in data/cached_briefs.json; the live call only fires on Refresh.
"""
from __future__ import annotations

import json
import sys
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutTimeout
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from shared.kamiwaza_client import chat  # noqa: E402

NARRATE_SYS = (
    "You are CHAIN-OF-COMMAND, a Marine ORBAT-aware authorization explainer. "
    "You translate a deterministic ReBAC graph-walk verdict into a one-paragraph "
    "operator rationale. Cite the actual relationship-graph edges (MEMBER_OF, "
    "ATTACHED_TO, DETACHED_TO, OPCON_TO, TACON_TO, HAS_NEED_TO_KNOW, REL_TO) by "
    "name. Always ground in JP 3-0 command relationships and DoDM 5200.02 "
    "clearance / need-to-know terminology. Keep it under 110 words. End with "
    "the literal verdict ALLOW or DENY. Never invent edges that aren't in the "
    "verdict input."
)


def _baseline_narration(verdict: dict, query: dict | None = None) -> str:
    """Deterministic stitched narration if the LLM call times out."""
    decision = verdict.get("decision", "?")
    summary = verdict.get("reason_summary", "")
    parts = [f"**{decision}** — {summary}."]
    for chk in verdict.get("checks", []):
        marker = "✓" if chk["ok"] else "✗"
        parts.append(f"  {marker} {chk['reason']}")
    return "\n".join(parts)


def narrate_access(verdict: dict, query: dict | None = None, *, hero: bool = False, timeout: int = 16) -> str:
    """Narrate the verdict using the LLM. Falls back deterministically on timeout."""
    if verdict.get("decision") == "ERROR":
        return f"ERROR: {verdict.get('reason_summary', 'unknown')}"

    msgs = [
        {"role": "system", "content": NARRATE_SYS},
        {"role": "user", "content": (
            f"Query: {query.get('label') if query else ''}\n\n"
            f"Verdict JSON (deterministic ReBAC engine output):\n"
            f"{json.dumps(verdict, indent=2, default=str)}\n\n"
            "Write the operator-grade rationale paragraph."
        )},
    ]

    def _call() -> str:
        return chat(msgs, temperature=0.3)

    with ThreadPoolExecutor(max_workers=1) as ex:
        try:
            return ex.submit(_call).result(timeout=timeout)
        except FutTimeout:
            return _baseline_narration(verdict, query)
        except Exception as e:  # noqa: BLE001
            return _baseline_narration(verdict, query) + f"\n\n_(fallback: {e})_"
