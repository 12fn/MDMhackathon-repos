"""REDLINE synthetic data generator.

Produces:
  - markings_taxonomy.json     : DoDM 5200.01 CUI categories + caveats (synth)
  - sample_docs/*.txt          : 4 demo drafts (already authored by hand)
  - cached_briefs.json         : pre-analyzed per-paragraph + document briefs
                                  for all 4 sample docs (cache-first hero)

Run:
    python data/generate.py            # produces taxonomy + cached briefs
    PRECOMPUTE=1 python data/generate.py   # also fires LLM for fresh cache

Seed: random.Random(1776). No real CUI/PII used; documents written for demo.
"""
from __future__ import annotations

import json
import os
import random
import sys
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutTimeout
from pathlib import Path

ROOT = Path(__file__).resolve().parent
APP_DIR = ROOT.parent
SAMPLES_DIR = APP_DIR / "sample_docs"
REPO_ROOT = APP_DIR.parent.parent

sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(APP_DIR))

RNG = random.Random(1776)


def list_sample_docs() -> list[dict]:
    docs = []
    for p in sorted(SAMPLES_DIR.glob("*.txt")):
        docs.append({
            "doc_id": p.stem,
            "title": p.stem.replace("_", " ").upper(),
            "path": str(p.relative_to(APP_DIR)),
            "text": p.read_text(),
        })
    return docs


# ---------------- per-paragraph and hero brief LLM calls ---------------------

def split_paragraphs(text: str) -> list[str]:
    """Split on blank lines; tolerate either Windows or Unix newlines."""
    parts = [p.strip() for p in text.replace("\r\n", "\n").split("\n\n")]
    return [p for p in parts if p]


def deterministic_paragraph_marking(paragraph: str) -> dict:
    """Rule-based fallback if the LLM call fails or times out."""
    p = paragraph.lower()
    # Order matters: most-specific wins
    rules: list[tuple[str, str, list[str], str, list[str]]] = [
        ("source selection", "CUI//SP-PROCURE",
         ["source selection", "BAFO", "competitive", "evaluation"],
         "FAR 3.104 source-selection sensitive content present.",
         ["FED ONLY"]),
        ("ITAR", "CUI//SP-EXPT",
         ["ITAR", "USML", "deemed-export", "TDP"],
         "ITAR / USML export-control language present.",
         ["NOFORN"]),
        ("itar", "CUI//SP-EXPT",
         ["ITAR", "USML"],
         "ITAR / USML export-control language present.",
         ["NOFORN"]),
        ("nsn", "CUI//SP-CTI",
         ["NSN", "TDP", "spec"],
         "Controlled technical / sustainment data referenced.",
         []),
        ("force protection", "CUI//SP-OPSEC",
         ["FPCON", "vulnerability", "manning roster", "rotation schedule"],
         "OPSEC indicators referenced (FPCON, vulnerability, manning).",
         ["NOFORN"]),
        ("manning roster", "CUI//SP-OPSEC",
         ["manning roster", "rotation schedule"],
         "OPSEC indicators referenced.",
         ["NOFORN"]),
        ("vendor", "CUI//SP-PROPIN",
         ["vendor", "rate card", "labor rate", "BAFO", "ODC"],
         "Vendor-proprietary cost / pricing data present.",
         ["FED ONLY"]),
        ("proprietary", "CUI//SP-PROPIN",
         ["proprietary", "trade secret"],
         "Proprietary business information present.",
         []),
        ("ssn", "CUI//SP-PRVCY",
         ["SSN", "DOB", "EDIPI", "home address"],
         "PII triggers present under DoD 5400.11-R.",
         ["FED ONLY"]),
        ("edipi", "CUI//SP-PRVCY",
         ["EDIPI", "DOB", "personal email"],
         "PII triggers present.",
         ["FED ONLY"]),
        ("noforn", "CUI//SP-NF",
         ["NOFORN", "U.S. only", "no foreign disclosure"],
         "Author explicitly invokes NOFORN handling.",
         ["NOFORN"]),
        ("u.s. only", "CUI//SP-NF",
         ["U.S. only"],
         "Document marks U.S.-only handling.",
         ["NOFORN"]),
        ("public release", "UNCLASSIFIED",
         ["public release", "unrestricted"],
         "Author requests public / unrestricted release.",
         []),
        ("unrestricted", "UNCLASSIFIED",
         ["unrestricted distribution"],
         "Unrestricted distribution explicitly requested.",
         []),
        ("pre-decisional", "CUI//FOUO",
         ["pre-decisional", "draft", "working paper"],
         "Pre-decisional / working-paper status warrants FOUO.",
         []),
        ("internal use", "CUI//FOUO",
         ["internal use", "do not release"],
         "Internal-use-only language.",
         []),
    ]
    for trigger, marking, phrases, rationale, caveats in rules:
        if trigger in p:
            present_phrases = [ph for ph in phrases if ph.lower() in p]
            return {
                "recommended_marking": marking,
                "rationale": rationale,
                "trigger_phrases": present_phrases or [trigger],
                "caveats_recommended": caveats,
                "confidence": 0.78,
            }
    # Default: low-risk admin paragraph
    return {
        "recommended_marking": "UNCLASSIFIED",
        "rationale": "No CUI category triggers detected; routine administrative content.",
        "trigger_phrases": [],
        "caveats_recommended": [],
        "confidence": 0.62,
    }


PARAGRAPH_SCHEMA_HINT = (
    "Object with EXACT keys (use these spellings, not synonyms): "
    "recommended_marking (string from taxonomy), "
    "rationale (1-line string citing DoDM 5200.01 marking category), "
    "trigger_phrases (array of short strings copied from the paragraph), "
    "caveats_recommended (array of caveat strings or []), "
    "confidence (float 0-1). Do NOT use CUI_marking, recommended_caveats, or any other key names."
)


def _normalize_paragraph_result(res: dict) -> dict:
    """Map common key variants to canonical schema."""
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
    # Carry through any extras
    for k, v in res.items():
        if k not in out and k not in [a for opts in aliases.values() for a in opts]:
            out[k] = v
    return out


def llm_mark_paragraph(paragraph: str, taxonomy: dict, idx: int, *, timeout: int = 12) -> dict:
    """Call chat_json for one paragraph; fall back to rules on timeout/error."""
    from shared.kamiwaza_client import chat_json

    cats = "\n".join(
        f"- {c['marking']}: {c['description']}" for c in taxonomy["categories"]
    )
    caveats = "\n".join(
        f"- {c['caveat']}: {c['expansion']} (use when {c['use_when']})"
        for c in taxonomy["caveats"]
    )
    sys_prompt = (
        "You are REDLINE, a CUI marking analyst supporting USMC LOGCOM under "
        "DoDM 5200.01 Vol 2 and 32 CFR Part 2002. For one paragraph of a "
        "draft document, recommend the single most-appropriate CUI marking, "
        "the rationale (one line, citing the marking category), the trigger "
        "phrases that drove the call, recommended caveats, and your "
        "confidence 0-1. Be conservative: if the paragraph is truly "
        "administrative with no CUI indicators, return UNCLASSIFIED."
    )
    user_prompt = (
        f"CUI MARKING TAXONOMY:\n{cats}\n\nCAVEATS:\n{caveats}\n\n"
        f"PARAGRAPH (index {idx}):\n\"\"\"\n{paragraph}\n\"\"\"\n\n"
        "Return JSON only."
    )

    def call() -> dict:
        return chat_json(
            [
                {"role": "system", "content": sys_prompt},
                {"role": "user", "content": user_prompt},
            ],
            schema_hint=PARAGRAPH_SCHEMA_HINT,
            temperature=0.2,
            max_tokens=400,
        )

    try:
        with ThreadPoolExecutor(max_workers=1) as ex:
            raw = ex.submit(call).result(timeout=timeout)
        return _normalize_paragraph_result(raw)
    except (FutTimeout, Exception) as e:  # noqa: BLE001
        out = deterministic_paragraph_marking(paragraph)
        out["_fallback"] = f"rule-based (LLM error: {type(e).__name__})"
        return out


def llm_doc_brief(doc_text: str, paragraph_results: list[dict], taxonomy: dict,
                  *, timeout: int = 35) -> dict:
    """Hero call: document-level marking brief. Cache-first via generate.py."""
    from shared.kamiwaza_client import chat_json

    cats = "\n".join(c["marking"] for c in taxonomy["categories"])
    para_summary = "\n".join(
        f"  para {p['paragraph_index']}: {p['recommended_marking']} "
        f"(conf {p['confidence']:.2f}) — {p['rationale']}"
        for p in paragraph_results
    )
    sys_prompt = (
        "You are REDLINE. You are writing the Document Marking Brief that "
        "the III MEF Information Protection Officer will read before "
        "approving a draft for distribution. Be specific. Identify the "
        "single overall recommended document marking, the releasability "
        "call (NOFORN vs REL TO partners), and explicitly weigh the risk "
        "of over-marking (slows coalition sharing) against the risk of "
        "under-marking (compromise + spillage). Cite DoDM 5200.01 by "
        "marking category."
    )
    user_prompt = (
        f"AVAILABLE MARKINGS: {cats}\n\n"
        f"PER-PARAGRAPH ANALYSIS:\n{para_summary}\n\n"
        f"FULL DOCUMENT TEXT:\n\"\"\"\n{doc_text}\n\"\"\"\n\n"
        "Return JSON with keys: "
        "overall_marking (single string), "
        "releasability (single string, e.g. 'NOFORN' or 'REL TO USA, FVEY'), "
        "executive_brief (3-5 sentence narrative paragraph), "
        "over_marking_risk (1 sentence), "
        "under_marking_risk (1 sentence), "
        "ipo_recommendation (1 sentence imperative)."
    )

    def call() -> dict:
        return chat_json(
            [
                {"role": "system", "content": sys_prompt},
                {"role": "user", "content": user_prompt},
            ],
            schema_hint="document marking brief",
            temperature=0.3,
            max_tokens=900,
        )

    try:
        with ThreadPoolExecutor(max_workers=1) as ex:
            return ex.submit(call).result(timeout=timeout)
    except (FutTimeout, Exception) as e:  # noqa: BLE001
        return deterministic_doc_brief(paragraph_results, error=str(e))


def deterministic_doc_brief(paragraph_results: list[dict],
                            error: str | None = None) -> dict:
    """Fallback hero brief — picks the most-restrictive paragraph marking."""
    order = [
        "UNCLASSIFIED",
        "CUI//FOUO",
        "CUI//SP-PROCURE",
        "CUI//SP-PROPIN",
        "CUI//SP-PRVCY",
        "CUI//SP-CTI",
        "CUI//SP-OPSEC",
        "CUI//SP-EXPT",
        "CUI//SP-LEI",
        "CUI//SP-NF",
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
            f"DoDM 5200.01 Vol 2. Recommend {overall} with releasability {rel}. "
            f"Source-selection, ITAR, OPSEC, and PII paragraphs (where present) "
            f"warrant portion-marking and split-distribution handling."
        ),
        "over_marking_risk": (
            "Marking the entire document NOFORN when only one paragraph requires "
            "it would block coalition partners from reading otherwise-shareable "
            "operational content."
        ),
        "under_marking_risk": (
            "Releasing without the controlling marking would risk spillage of "
            "controlled CUI categories and trigger an incident report."
        ),
        "ipo_recommendation": (
            f"Apply {overall} {rel} at the banner line; portion-mark sensitive "
            f"paragraphs; split annexes containing PII for FED-only handling."
        ),
        "_fallback": f"rule-based (LLM error: {error})" if error else "rule-based",
    }


# ---------------- Cache builder ---------------------------------------------

def precompute_briefs() -> None:
    taxonomy = json.loads((ROOT / "markings_taxonomy.json").read_text())
    docs = list_sample_docs()
    out: dict[str, dict] = {}
    use_llm = bool(os.getenv("PRECOMPUTE")) or bool(os.getenv("OPENAI_API_KEY")) or \
        bool(os.getenv("KAMIWAZA_BASE_URL"))

    for doc in docs:
        print(f"[{doc['doc_id']}] splitting + marking…")
        paragraphs = split_paragraphs(doc["text"])
        para_results = []
        for i, para in enumerate(paragraphs):
            t0 = time.time()
            if use_llm:
                res = llm_mark_paragraph(para, taxonomy, i)
            else:
                res = deterministic_paragraph_marking(para)
            # Defensive defaults (normalize already runs in llm path)
            res.setdefault("recommended_marking", "UNCLASSIFIED")
            res.setdefault("rationale", "")
            res.setdefault("trigger_phrases", [])
            res.setdefault("caveats_recommended", [])
            res.setdefault("confidence", 0.0)
            res["paragraph_index"] = i
            res["paragraph_text"] = para
            res["_latency_ms"] = int((time.time() - t0) * 1000)
            para_results.append(res)
            print(f"  para {i}: {res['recommended_marking']} "
                  f"(conf {float(res.get('confidence') or 0):.2f})")
        if use_llm:
            brief = llm_doc_brief(doc["text"], para_results, taxonomy)
        else:
            brief = deterministic_doc_brief(para_results)
        out[doc["doc_id"]] = {
            "doc_id": doc["doc_id"],
            "title": doc["title"],
            "path": doc["path"],
            "paragraphs": para_results,
            "doc_brief": brief,
        }

    cache = ROOT / "cached_briefs.json"
    cache.write_text(json.dumps(out, indent=2))
    print(f"\nWrote {cache} ({cache.stat().st_size:,} bytes) for {len(out)} docs.")


def main() -> None:
    # Taxonomy is hand-authored; just confirm it's present
    tax = ROOT / "markings_taxonomy.json"
    if not tax.exists():
        raise SystemExit(f"missing {tax} — author it before running generate.")
    print(f"Taxonomy OK: {tax} ({tax.stat().st_size} bytes)")
    precompute_briefs()


if __name__ == "__main__":
    main()
