"""LLM-backed paragraph + document marking with watchdog + cache.

Public API:
  - load_taxonomy()
  - load_cached_briefs()
  - mark_paragraph(text, taxonomy, idx)             -> dict (per-paragraph)
  - document_brief(text, paragraph_results, tax)    -> dict (hero call)
  - split_paragraphs(text)
"""
from __future__ import annotations

import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutTimeout
from pathlib import Path
from typing import Any

APP_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = APP_DIR / "data"
REPO_ROOT = APP_DIR.parent.parent
sys.path.insert(0, str(REPO_ROOT))


def load_taxonomy() -> dict:
    return json.loads((DATA_DIR / "markings_taxonomy.json").read_text())


def load_cached_briefs() -> dict:
    p = DATA_DIR / "cached_briefs.json"
    if not p.exists():
        return {}
    return json.loads(p.read_text())


def split_paragraphs(text: str) -> list[str]:
    parts = [p.strip() for p in text.replace("\r\n", "\n").split("\n\n")]
    return [p for p in parts if p]


# ---------------- deterministic fallbacks (mirror data/generate.py) ---------

def _rule_paragraph(paragraph: str) -> dict:
    p = paragraph.lower()
    rules: list[tuple[str, str, list[str], str, list[str]]] = [
        ("source selection", "CUI//SP-PROCURE",
         ["source selection", "BAFO", "competitive", "evaluation"],
         "FAR 3.104 source-selection sensitive content present.", ["FED ONLY"]),
        ("itar", "CUI//SP-EXPT",
         ["ITAR", "USML", "deemed-export", "TDP"],
         "ITAR / USML export-control language present.", ["NOFORN"]),
        ("force protection", "CUI//SP-OPSEC",
         ["FPCON", "vulnerability", "manning roster", "rotation schedule"],
         "OPSEC indicators referenced (FPCON, vulnerability, manning).",
         ["NOFORN"]),
        ("manning roster", "CUI//SP-OPSEC",
         ["manning roster", "rotation schedule"],
         "OPSEC indicators referenced.", ["NOFORN"]),
        ("vendor", "CUI//SP-PROPIN",
         ["vendor", "rate card", "labor rate", "BAFO", "ODC"],
         "Vendor-proprietary cost / pricing data present.", ["FED ONLY"]),
        ("proprietary", "CUI//SP-PROPIN",
         ["proprietary", "trade secret"],
         "Proprietary business information present.", []),
        ("ssn", "CUI//SP-PRVCY",
         ["SSN", "DOB", "EDIPI", "home address"],
         "PII triggers present under DoD 5400.11-R.", ["FED ONLY"]),
        ("edipi", "CUI//SP-PRVCY",
         ["EDIPI", "DOB", "personal email"],
         "PII triggers present.", ["FED ONLY"]),
        ("noforn", "CUI//SP-NF",
         ["NOFORN", "U.S. only", "no foreign disclosure"],
         "Author explicitly invokes NOFORN handling.", ["NOFORN"]),
        ("u.s. only", "CUI//SP-NF",
         ["U.S. only"], "Document marks U.S.-only handling.", ["NOFORN"]),
        ("public release", "UNCLASSIFIED",
         ["public release", "unrestricted"],
         "Author requests public / unrestricted release.", []),
        ("unrestricted", "UNCLASSIFIED",
         ["unrestricted distribution"],
         "Unrestricted distribution explicitly requested.", []),
        ("pre-decisional", "CUI//FOUO",
         ["pre-decisional", "draft", "working paper"],
         "Pre-decisional / working-paper status warrants FOUO.", []),
        ("internal use", "CUI//FOUO",
         ["internal use", "do not release"],
         "Internal-use-only language.", []),
    ]
    for trigger, marking, phrases, rationale, caveats in rules:
        if trigger in p:
            present = [ph for ph in phrases if ph.lower() in p]
            return {
                "recommended_marking": marking,
                "rationale": rationale,
                "trigger_phrases": present or [trigger],
                "caveats_recommended": caveats,
                "confidence": 0.78,
            }
    return {
        "recommended_marking": "UNCLASSIFIED",
        "rationale": "No CUI category triggers detected; routine administrative content.",
        "trigger_phrases": [],
        "caveats_recommended": [],
        "confidence": 0.62,
    }


def _rule_doc_brief(paragraph_results: list[dict],
                    error: str | None = None) -> dict:
    order = [
        "UNCLASSIFIED", "CUI//FOUO", "CUI//SP-PROCURE", "CUI//SP-PROPIN",
        "CUI//SP-PRVCY", "CUI//SP-CTI", "CUI//SP-OPSEC", "CUI//SP-EXPT",
        "CUI//SP-LEI", "CUI//SP-NF",
    ]
    rank = {m: i for i, m in enumerate(order)}
    best = max(paragraph_results,
               key=lambda r: rank.get(r.get("recommended_marking", "UNCLASSIFIED"), 0))
    overall = best.get("recommended_marking", "CUI//FOUO")
    has_noforn = any(
        "NOFORN" in (cv or "") for r in paragraph_results
        for cv in r.get("caveats_recommended", []) or []
    )
    rel = "NOFORN" if has_noforn or "NF" in overall else "REL TO USA, FVEY"
    return {
        "overall_marking": overall,
        "releasability": rel,
        "executive_brief": (
            f"Document contains paragraphs spanning UNCLASSIFIED through {overall}. "
            f"Most-restrictive paragraph drives the banner-line marking under "
            f"DoDM 5200.01 Vol 2. Recommend {overall} with releasability {rel}."
        ),
        "over_marking_risk": (
            "Marking the entire document NOFORN when only one paragraph requires "
            "it would block coalition partners from reading otherwise-shareable content."
        ),
        "under_marking_risk": (
            "Releasing without the controlling marking would risk spillage of "
            "controlled CUI categories and trigger an incident report."
        ),
        "ipo_recommendation": (
            f"Apply {overall} {rel} at the banner line; portion-mark sensitive paragraphs."
        ),
        "_fallback": f"deterministic baseline (LLM error: {error})" if error else "deterministic baseline",
    }


# ---------------- Live LLM calls --------------------------------------------

PARAGRAPH_SCHEMA_HINT = (
    "Object with EXACT keys (use these spellings, not synonyms): "
    "recommended_marking (string), rationale (1-line string), "
    "trigger_phrases (array of strings), caveats_recommended (array of strings), "
    "confidence (float 0-1). Do NOT use CUI_marking, recommended_caveats, or any other key names."
)


def _normalize_paragraph_result(res: dict) -> dict:
    aliases = {
        "recommended_marking": ["recommended_marking", "CUI_marking", "CUI_Marking",
                                 "cui_marking", "marking", "Marking"],
        "rationale": ["rationale", "Rationale"],
        "trigger_phrases": ["trigger_phrases", "Trigger_Phrases", "triggers", "phrases"],
        "caveats_recommended": ["caveats_recommended", "recommended_caveats",
                                 "Recommended_Caveats", "Caveats_Recommended", "caveats"],
        "confidence": ["confidence", "Confidence"],
    }
    out: dict = {}
    for canon, options in aliases.items():
        for o in options:
            if o in res and res[o] not in (None, ""):
                out[canon] = res[o]
                break
    for k, v in res.items():
        if k not in out and k not in [a for opts in aliases.values() for a in opts]:
            out[k] = v
    out.setdefault("recommended_marking", "UNCLASSIFIED")
    out.setdefault("rationale", "")
    out.setdefault("trigger_phrases", [])
    out.setdefault("caveats_recommended", [])
    out.setdefault("confidence", 0.0)
    return out


def _llm_paragraph(paragraph: str, taxonomy: dict, idx: int) -> dict:
    from shared.kamiwaza_client import chat_json

    cats = "\n".join(
        f"- {c['marking']}: {c['description']}" for c in taxonomy["categories"]
    )
    caveats = "\n".join(
        f"- {c['caveat']}: {c['expansion']}" for c in taxonomy["caveats"]
    )
    sys_p = (
        "You are REDLINE, a CUI marking analyst supporting USMC LOGCOM under "
        "DoDM 5200.01 Vol 2. For one paragraph, recommend the single most-"
        "appropriate CUI marking, the rationale (cite the marking category), "
        "trigger phrases, recommended caveats, and confidence 0-1. Be conservative."
    )
    user_p = (
        f"CUI MARKING CATEGORIES:\n{cats}\n\nCAVEATS:\n{caveats}\n\n"
        f"PARAGRAPH (index {idx}):\n\"\"\"\n{paragraph}\n\"\"\"\n\nReturn JSON only."
    )
    return chat_json(
        [{"role": "system", "content": sys_p},
         {"role": "user", "content": user_p}],
        schema_hint=PARAGRAPH_SCHEMA_HINT,
        temperature=0.2,
        max_tokens=400,
    )


def mark_paragraph(paragraph: str, taxonomy: dict, idx: int,
                   *, timeout: int = 12) -> dict:
    try:
        with ThreadPoolExecutor(max_workers=1) as ex:
            raw = ex.submit(_llm_paragraph, paragraph, taxonomy, idx).result(timeout=timeout)
        return _normalize_paragraph_result(raw)
    except (FutTimeout, Exception) as e:  # noqa: BLE001
        out = _rule_paragraph(paragraph)
        out["_fallback"] = f"deterministic baseline (LLM error: {type(e).__name__})"
        return out


def _llm_doc_brief(doc_text: str, paragraph_results: list[dict],
                   taxonomy: dict) -> dict:
    from shared.kamiwaza_client import chat_json

    cats = "\n".join(c["marking"] for c in taxonomy["categories"])
    para_summary = "\n".join(
        f"  para {p.get('paragraph_index', i)}: "
        f"{p['recommended_marking']} (conf {p.get('confidence', 0):.2f}) "
        f"— {p['rationale']}"
        for i, p in enumerate(paragraph_results)
    )
    sys_p = (
        "You are REDLINE. Write the Document Marking Brief that the III MEF "
        "Information Protection Officer reads before approving distribution. "
        "Identify overall marking, releasability call, and explicitly weigh "
        "the risk of over-marking (slows coalition sharing) against the risk "
        "of under-marking (compromise + spillage). Cite DoDM 5200.01."
    )
    user_p = (
        f"AVAILABLE MARKINGS: {cats}\n\nPER-PARAGRAPH ANALYSIS:\n{para_summary}\n\n"
        f"FULL DOCUMENT TEXT:\n\"\"\"\n{doc_text}\n\"\"\"\n\n"
        "Return JSON with keys: overall_marking, releasability, "
        "executive_brief (3-5 sentence narrative), over_marking_risk (1 sentence), "
        "under_marking_risk (1 sentence), ipo_recommendation (1 imperative sentence)."
    )
    # Hero model for the document brief
    hero_model = os.getenv("LLM_HERO_MODEL") or os.getenv("OPENAI_HERO_MODEL")
    kw: dict[str, Any] = {"temperature": 0.3, "max_tokens": 900}
    if hero_model:
        kw["model"] = hero_model
    return chat_json(
        [{"role": "system", "content": sys_p},
         {"role": "user", "content": user_p}],
        schema_hint="document marking brief",
        **kw,
    )


def document_brief(doc_text: str, paragraph_results: list[dict],
                   taxonomy: dict, *, timeout: int = 35) -> dict:
    try:
        with ThreadPoolExecutor(max_workers=1) as ex:
            return ex.submit(_llm_doc_brief, doc_text, paragraph_results, taxonomy).result(timeout=timeout)
    except (FutTimeout, Exception) as e:  # noqa: BLE001
        return _rule_doc_brief(paragraph_results, error=type(e).__name__)
