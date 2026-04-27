"""OPENGATE — Federal-data discovery RAG over a synthetic data.gov catalog.

Pipeline (production-shape five-stage):

  1. parse_query(query)        — chat_json: free text -> structured filter
  2. apply_filters(filters)    — Python: agency / date / format / tag filter
  3. cosine_search(query, ids) — numpy: vector rerank candidate set
  4. comparison_json(query, k) — chat_json: structured per-dataset table
  5. hero_brief(query, k, c)   — chat: 250-350 word "Analyst Discovery Brief"

Hero call wrapped in ThreadPoolExecutor with 35 s wall-clock timeout.
On timeout, falls back to deterministic baseline_brief(...).
"""
from __future__ import annotations

import json
import sys
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutTimeout
from datetime import date, datetime
from functools import lru_cache
from pathlib import Path
from typing import Any

import numpy as np

ROOT = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(ROOT))

from shared.kamiwaza_client import (  # noqa: E402
    PRIMARY_MODEL,
    chat,
    chat_json,
    embed,
)

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
EMBED_CACHE = DATA_DIR / "embeddings.npy"
EMBED_IDS = DATA_DIR / "embedding_ids.json"


# ─────────────────────────────────────────────────────────────────────────────
# Data load
# ─────────────────────────────────────────────────────────────────────────────
@lru_cache(maxsize=1)
def load_datasets() -> list[dict]:
    return json.loads((DATA_DIR / "datasets.json").read_text())


@lru_cache(maxsize=1)
def load_cached_briefs() -> dict:
    p = DATA_DIR / "cached_briefs.json"
    if not p.exists():
        return {}
    return json.loads(p.read_text())


# ─────────────────────────────────────────────────────────────────────────────
# Embedding index
# ─────────────────────────────────────────────────────────────────────────────
def build_embeddings(force: bool = False) -> tuple[np.ndarray, list[str]]:
    """Embed every dataset abstract; cache to disk. Returns (matrix, ids)."""
    rows = load_datasets()
    if not force and EMBED_CACHE.exists() and EMBED_IDS.exists():
        ids = json.loads(EMBED_IDS.read_text())
        if len(ids) == len(rows):
            mat = np.load(EMBED_CACHE)
            return mat, ids

    abstracts = [
        f"{r['title']}. {r['abstract']} Tags: {', '.join(r['tags'])}."
        for r in rows
    ]
    ids = [r["dataset_id"] for r in rows]
    batch = 64
    vecs: list[list[float]] = []
    for i in range(0, len(abstracts), batch):
        chunk = abstracts[i : i + batch]
        vecs.extend(embed(chunk))
    mat = np.array(vecs, dtype=np.float32)
    norms = np.linalg.norm(mat, axis=1, keepdims=True) + 1e-12
    mat = mat / norms
    np.save(EMBED_CACHE, mat)
    EMBED_IDS.write_text(json.dumps(ids))
    return mat, ids


def cosine_search(query: str, k: int = 12,
                  candidate_ids: list[str] | None = None) -> list[tuple[str, float]]:
    """Top-k (dataset_id, cosine_score) for the query, optionally restricted."""
    mat, ids = build_embeddings()
    qvec = np.array(embed([query])[0], dtype=np.float32)
    qvec = qvec / (np.linalg.norm(qvec) + 1e-12)
    scores = mat @ qvec

    if candidate_ids is not None:
        cand = set(candidate_ids)
        mask = np.array([i in cand for i in ids])
        scores = np.where(mask, scores, -1.0)

    top_idx = np.argsort(-scores)[:k]
    return [(ids[i], float(scores[i])) for i in top_idx if scores[i] > -1.0]


# ─────────────────────────────────────────────────────────────────────────────
# Stage 1: intent parser
# ─────────────────────────────────────────────────────────────────────────────
KNOWN_AGENCIES = ["NOAA", "NASA", "FEMA", "DOT", "DOD", "USDA", "USGS", "EIA",
                  "DHS", "State", "USAID", "Census", "EPA", "VA", "BLS"]

FILTER_SCHEMA_HINT = (
    "Keys: agencies (array of agency short codes from this allowed list: "
    f"{KNOWN_AGENCIES}; only include if the analyst constrained agencies), "
    "topic_keywords (array of 2-6 single- or hyphenated-word topic terms), "
    "min_last_updated (ISO date YYYY-MM-DD, optional — only set if analyst "
    "implied recency), "
    "preferred_formats (array of strings: CSV, JSON, NetCDF, GeoTIFF, SHP, "
    "GeoJSON, HDF5, API, PDF — optional), "
    "regions (array of region phrases the analyst mentioned, e.g. "
    "['Indo-Pacific', 'South China Sea']), "
    "intent_summary (string, ONE sentence describing what the analyst wants)."
)

PARSER_SYSTEM = (
    "You are a Marine Corps Logistics Command (MARCORLOGCOM) data-discovery "
    "assistant. You convert a Marine analyst's free-text question about "
    "federal datasets into a strict JSON filter object that downstream code "
    "applies against a data.gov-shape catalog. Only set keys the analyst "
    "actually constrained — leave others unset. Always include "
    "`intent_summary` (one sentence)."
)


def parse_query(query: str) -> dict:
    out = chat_json(
        [
            {"role": "system", "content": PARSER_SYSTEM},
            {"role": "user", "content": f"Analyst asked: {query}\n\nReturn the JSON filter."},
        ],
        schema_hint=FILTER_SCHEMA_HINT,
        temperature=0.1,
    )
    # Defensive normalization
    if isinstance(out.get("agencies"), str):
        out["agencies"] = [out["agencies"]]
    if isinstance(out.get("topic_keywords"), str):
        out["topic_keywords"] = [out["topic_keywords"]]
    return out


# ─────────────────────────────────────────────────────────────────────────────
# Stage 2: hard filter
# ─────────────────────────────────────────────────────────────────────────────
def apply_filters(filters: dict) -> list[dict]:
    rows = load_datasets()
    out: list[dict] = []
    agencies = {a.upper() for a in (filters.get("agencies") or [])}
    formats = {f.upper() for f in (filters.get("preferred_formats") or [])}
    min_dt = None
    if filters.get("min_last_updated"):
        try:
            min_dt = datetime.fromisoformat(filters["min_last_updated"]).date()
        except ValueError:
            min_dt = None

    topic_kws = [k.lower() for k in (filters.get("topic_keywords") or [])]
    region_kws = [k.lower() for k in (filters.get("regions") or [])]

    for r in rows:
        if agencies and r["agency"].upper() not in agencies:
            continue
        if formats and r["format"].upper() not in formats:
            continue
        if min_dt:
            try:
                rd = datetime.fromisoformat(r["last_updated"]).date()
            except ValueError:
                rd = date.today()
            if rd < min_dt:
                continue
        # Soft topic / region filter — only excludes if BOTH keyword sets are
        # set AND we get zero hits anywhere in the record. This keeps filtering
        # forgiving so vector rerank does the real work.
        if topic_kws or region_kws:
            haystack = " ".join([
                r["title"], r["abstract"], " ".join(r["tags"]),
                r["topic_seed"], r["region_seed"],
            ]).lower()
            kw_hit = any(k in haystack for k in topic_kws) if topic_kws else True
            rg_hit = any(k in haystack for k in region_kws) if region_kws else True
            if not (kw_hit or rg_hit):
                continue
        out.append(r)
    return out


# ─────────────────────────────────────────────────────────────────────────────
# Stage 3: end-to-end retrieve
# ─────────────────────────────────────────────────────────────────────────────
def retrieve(query: str, k: int = 8) -> dict:
    filters = parse_query(query)
    candidates = apply_filters(filters)

    if not candidates:
        # Soft-fail: drop all hard filters except agency, retry
        loose = {kk: vv for kk, vv in filters.items()
                 if kk in ("agencies",)}
        candidates = apply_filters(loose)

    if not candidates:
        candidates = load_datasets()  # global fallback

    cand_ids = [c["dataset_id"] for c in candidates]
    ranked_pairs = cosine_search(query, k=min(k, len(cand_ids)),
                                 candidate_ids=cand_ids)
    by_id = {c["dataset_id"]: c for c in candidates}
    ranked_records = []
    for did, score in ranked_pairs:
        rec = dict(by_id[did])
        rec["similarity"] = round(score, 4)
        ranked_records.append(rec)

    return {
        "filters": filters,
        "candidate_count": len(candidates),
        "ranked": ranked_records,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Stage 4: structured comparison table
# ─────────────────────────────────────────────────────────────────────────────
COMPARISON_SYSTEM = (
    "You are a Marine Corps data-discovery analyst. Given the analyst's "
    "question and a short list of candidate federal datasets (as JSON), "
    "produce a strict JSON object with key `comparison` mapped to an array. "
    "Each array element MUST contain exactly: dataset_id, title, agency, "
    "relevance_score (0-10 numeric), why_relevant (one short sentence), "
    "suggested_use (one short sentence on how a Marine analyst would use it), "
    "freshness_concern (one of: 'fresh', 'acceptable', 'stale-review', "
    "'outdated'). Only score datasets you were given — do not invent."
)


def comparison_json(query: str, ranked: list[dict]) -> dict:
    payload = [
        {k: v for k, v in r.items() if k not in ("topic_seed", "region_seed")}
        for r in ranked
    ]
    return chat_json(
        [
            {"role": "system", "content": COMPARISON_SYSTEM},
            {"role": "user", "content": (
                f"Analyst question:\n{query}\n\n"
                f"Candidate datasets JSON:\n{json.dumps(payload, indent=2)}\n\n"
                "Return JSON now."
            )},
        ],
        schema_hint="{ comparison: [ {dataset_id, title, agency, relevance_score, why_relevant, suggested_use, freshness_concern}, ... ] }",
        temperature=0.2,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Stage 5: hero "Analyst Discovery Brief"
# ─────────────────────────────────────────────────────────────────────────────
BRIEF_SYSTEM = (
    "You are a senior Marine Corps intelligence-data analyst writing an "
    "Analyst Discovery Brief for a MARCORLOGCOM action officer. Use this "
    "structure verbatim: "
    "1) BLUF (one sentence). "
    "2) Top 3 Datasets (titled bullets — for each: dataset name, agency, "
    "what it could enable, and one specific number from its abstract). "
    "3) Gaps in Available Data (1-2 short bullets — what the catalog "
    "did NOT surface that the analyst probably wanted). "
    "4) Recommendation (one bullet — the next 24-hour analytic action). "
    "Use 250-350 words. Reference specific agencies, dataset titles, and "
    "any concrete numbers (record counts, refresh cadences, last-updated "
    "dates) you see in the payload. Do not hedge with disclaimers. Do not "
    "mention model providers."
)


def _hero_call(query: str, ranked: list[dict], comparison: dict,
               *, model: str) -> str:
    payload = {
        "analyst_question": query,
        "ranked_datasets": [
            {k: v for k, v in r.items() if k not in ("topic_seed", "region_seed")}
            for r in ranked[:6]
        ],
        "comparison": comparison.get("comparison", []),
    }
    # NOTE: do NOT pass max_tokens — gpt-5* family rejects it (OpenAI requires
    # `max_completion_tokens` for newer models). Letting the server choose
    # keeps us provider-portable across Kamiwaza / OpenAI / OpenRouter.
    return chat(
        [
            {"role": "system", "content": BRIEF_SYSTEM},
            {"role": "user", "content": json.dumps(payload, indent=2)},
        ],
        model=model,
        temperature=0.4,
    )


def baseline_brief(query: str, ranked: list[dict], comparison: dict) -> str:
    """Deterministic fallback when the hero LLM call times out / fails."""
    rows = (comparison or {}).get("comparison") or []
    if not rows and ranked:
        rows = [
            {
                "title": r["title"],
                "agency": r["agency"],
                "relevance_score": r.get("similarity", 0.0) * 10,
                "why_relevant": r["abstract"][:160] + "...",
                "freshness_concern": "acceptable",
            }
            for r in ranked[:3]
        ]
    top3 = rows[:3]
    bullets = []
    for i, r in enumerate(top3, 1):
        bullets.append(
            f"{i}. **{r.get('title', 'Untitled')}** "
            f"({r.get('agency', '')}). "
            f"{r.get('why_relevant') or r.get('suggested_use') or ''}"
        )
    body = "\n".join(bullets) if bullets else "No candidates surfaced."
    return (
        f"**BLUF.** Top {len(top3)} federal datasets retrieved against the "
        f"analyst's query — vector-reranked over the catalog.\n\n"
        f"**Top Datasets**\n{body}\n\n"
        f"**Gaps in Available Data.** Cached fallback brief — full LLM brief "
        f"timed out at 35 s. Re-trigger via the Regenerate button or "
        f"narrow the query.\n\n"
        f"**Recommendation.** Open the top-ranked dataset in the catalog and "
        f"validate format / refresh cadence before tasking the staff section."
    )


def hero_brief(query: str, ranked: list[dict], comparison: dict,
               *, use_hero_model: bool = True, timeout_s: int = 35) -> str:
    """Hero LLM call, watchdog-wrapped. Falls back to baseline_brief on fail."""
    model = "gpt-5.4" if use_hero_model else PRIMARY_MODEL
    try:
        with ThreadPoolExecutor(max_workers=1) as ex:
            fut = ex.submit(_hero_call, query, ranked, comparison, model=model)
            return fut.result(timeout=timeout_s)
    except FutTimeout:
        return baseline_brief(query, ranked, comparison)
    except Exception:  # noqa: BLE001 - never crash the UI
        return baseline_brief(query, ranked, comparison)
