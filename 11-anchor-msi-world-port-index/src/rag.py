# ANCHOR — agentic RAG port-capability assessor
# Part of the MDM 2026 Hackathon Templates (https://github.com/12fn/MDMhackathon-repos)
# MIT licensed. Built on GAI (Government Acquisitions, Inc.) + Kamiwaza (https://www.kamiwaza.ai/).
"""ANCHOR — Agentic RAG over the World Port Index corpus.

Two-stage retrieval:
  1. Hard filters (parsed from the user query via chat_json) → candidate set.
  2. Vector cosine similarity over the candidate profiles → ranked top-K.

Then two model calls:
  - chat_json(...) writes a structured comparison table.
  - chat(...) streams a narrative recommendation in OPORD-adjacent prose.
"""
from __future__ import annotations

import json
import math
import os
import sys
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterator

import numpy as np

ROOT = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(ROOT))

from shared.kamiwaza_client import chat, chat_json, embed, get_client, PRIMARY_MODEL  # noqa: E402

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
EMBED_CACHE = DATA_DIR / "embeddings.npy"
EMBED_IDS = DATA_DIR / "embedding_ids.json"


# --- Data load -----------------------------------------------------------
@lru_cache(maxsize=1)
def load_ports() -> list[dict]:
    return json.loads((DATA_DIR / "ports.json").read_text())


# --- Embedding index -----------------------------------------------------
def build_embeddings(force: bool = False) -> tuple[np.ndarray, list[str]]:
    """Embed every port profile, cache to disk. Returns (matrix, port_ids)."""
    ports = load_ports()
    if not force and EMBED_CACHE.exists() and EMBED_IDS.exists():
        ids = json.loads(EMBED_IDS.read_text())
        if len(ids) == len(ports):
            mat = np.load(EMBED_CACHE)
            return mat, ids

    profiles = [p["profile"] for p in ports]
    ids = [p["port_id"] for p in ports]

    # Batch (OpenAI accepts up to 2048 inputs per call but we'll chunk for safety)
    batch = 64
    vecs: list[list[float]] = []
    for i in range(0, len(profiles), batch):
        chunk = profiles[i : i + batch]
        vecs.extend(embed(chunk))

    mat = np.array(vecs, dtype=np.float32)
    # L2-normalize so dot product == cosine similarity
    norms = np.linalg.norm(mat, axis=1, keepdims=True) + 1e-12
    mat = mat / norms

    np.save(EMBED_CACHE, mat)
    EMBED_IDS.write_text(json.dumps(ids))
    return mat, ids


def cosine_search(query: str, k: int = 12, candidate_ids: list[str] | None = None) -> list[tuple[str, float]]:
    """Return top-k (port_id, score) for a free-text query, optionally restricted."""
    mat, ids = build_embeddings()
    qvec_raw = embed([query])[0]
    q = np.array(qvec_raw, dtype=np.float32)
    q = q / (np.linalg.norm(q) + 1e-12)

    scores = mat @ q  # (N,) cosine similarities

    if candidate_ids is not None:
        cand_set = set(candidate_ids)
        mask = np.array([pid in cand_set for pid in ids])
        scores = np.where(mask, scores, -1.0)

    top_idx = np.argsort(-scores)[:k]
    return [(ids[i], float(scores[i])) for i in top_idx if scores[i] > -1.0]


# --- Geo helpers ---------------------------------------------------------
def haversine_nm(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R_NM = 3440.065  # nautical miles
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * R_NM * math.asin(math.sqrt(a))


# --- Query parser (LLM → structured filters) -----------------------------
FILTER_SCHEMA_HINT = (
    "Keys: min_draft_m (number, optional), min_channel_depth_m (number, optional), "
    "min_loa_m (number, optional), min_berths (integer, optional), "
    "roro_required (boolean, optional), bunker_required (boolean, optional), "
    "max_political_risk (number 0-10, optional), "
    "regions (array of strings — any of: Western Pacific, Indian Ocean, Mediterranean, "
    "South Pacific / Oceania, Eastern Pacific / Americas), "
    "hostnation_in (array of strings — any of: US_TERRITORY, ALLY, PARTNER, NEUTRAL, DENIED), "
    "near (object with optional name string, lat number, lon number, radius_nm number), "
    "intent_summary (string, 1 sentence describing what the planner wants)."
)

PARSER_SYSTEM = (
    "You are a Marine Corps Logistics Command (MARCORLOGCOM) planning assistant for the "
    "Maritime Prepositioning Force (MPF) under Blount Island Command. "
    "You convert a planner's free-text question about port selection into a strict JSON "
    "filter object that downstream code can apply against a World Port Index database. "
    "Only set keys that the user actually constrained — leave others unset. "
    "If the user names a known port (e.g. 'Subic Bay', 'Apra', 'Diego Garcia', 'Naha', 'Rota'), "
    "infer approximate lat/lon and put it in `near` with their stated radius (default 500 nm if unstated). "
    "Always include a one-sentence `intent_summary`."
)

# A tiny atlas the parser can lean on for `near` references it sees a lot.
KNOWN_REFERENCE_POINTS = {
    "subic": (14.79, 120.27),
    "subic bay": (14.79, 120.27),
    "apra": (13.45, 144.66),
    "guam": (13.45, 144.66),
    "diego garcia": (-7.31, 72.41),
    "naha": (26.21, 127.68),
    "okinawa": (26.21, 127.68),
    "rota": (36.62, -6.35),  # Rota, Spain
    "yokosuka": (35.29, 139.67),
    "sasebo": (33.16, 129.72),
    "darwin": (-12.46, 130.84),
    "manama": (26.22, 50.58),
    "bahrain": (26.22, 50.58),
    "djibouti": (11.59, 43.15),
    "souda": (35.49, 24.13),
    "naples": (40.84, 14.25),
    "pearl harbor": (21.36, -157.97),
    "pearl": (21.36, -157.97),
}


def parse_query(query: str) -> dict:
    """LLM-parse the planner's question into a filter dict."""
    out = chat_json(
        [
            {"role": "system", "content": PARSER_SYSTEM},
            {"role": "user", "content": f"Planner asked: {query}\n\nReturn the JSON filter."},
        ],
        schema_hint=FILTER_SCHEMA_HINT,
        temperature=0.1,
    )

    # Backfill `near` lat/lon from atlas if the parser only gave a name
    near = out.get("near") or {}
    if isinstance(near, dict) and near.get("name") and not (near.get("lat") and near.get("lon")):
        key = near["name"].lower().strip()
        for atlas_key, (lat, lon) in KNOWN_REFERENCE_POINTS.items():
            if atlas_key in key or key in atlas_key:
                near["lat"], near["lon"] = lat, lon
                break
        out["near"] = near
    return out


# --- Hard-filter applier -------------------------------------------------
def apply_filters(filters: dict) -> list[dict]:
    """Return ports passing the hard filters (capability + geography)."""
    ports = load_ports()
    out = []
    near = filters.get("near") or {}
    radius = float(near.get("radius_nm") or 0)
    nlat = near.get("lat")
    nlon = near.get("lon")

    for p in ports:
        if (md := filters.get("min_draft_m")) is not None and p["max_draft_m"] < md:
            continue
        if (mc := filters.get("min_channel_depth_m")) is not None and p["channel_depth_m"] < mc:
            continue
        if (ml := filters.get("min_loa_m")) is not None and p["max_loa_m"] < ml:
            continue
        if (mb := filters.get("min_berths")) is not None and p["berths"] < mb:
            continue
        if filters.get("roro_required") and not p["roro_capable"]:
            continue
        if filters.get("bunker_required") and not p["bunker_available"]:
            continue
        if (mr := filters.get("max_political_risk")) is not None and p["political_risk"] > mr:
            continue
        if (regs := filters.get("regions")):
            if p["region"] not in regs:
                continue
        if (hns := filters.get("hostnation_in")):
            if p["hostnation_status"] not in hns:
                continue
        if nlat is not None and nlon is not None and radius > 0:
            d = haversine_nm(nlat, nlon, p["lat"], p["lon"])
            if d > radius:
                continue
            p = {**p, "_distance_nm": round(d, 1)}
        out.append(p)
    return out


# --- End-to-end retrieval ------------------------------------------------
def retrieve(query: str, k: int = 8) -> dict:
    """Full agentic-RAG step: parse → filter → vector rerank → top-K records."""
    filters = parse_query(query)
    candidates = apply_filters(filters)

    if not candidates:
        # Soft-fail: keep filters but drop hard radius/region for retry
        loose = {kk: vv for kk, vv in filters.items()
                 if kk not in ("near", "regions", "hostnation_in")}
        candidates = apply_filters(loose)

    cand_ids = [c["port_id"] for c in candidates]
    if not cand_ids:
        return {"filters": filters, "candidates": [], "ranked": []}

    ranked = cosine_search(query, k=min(k, len(cand_ids)), candidate_ids=cand_ids)
    by_id = {c["port_id"]: c for c in candidates}
    ranked_records = []
    for pid, score in ranked:
        rec = dict(by_id[pid])
        rec["similarity"] = round(score, 4)
        ranked_records.append(rec)

    return {
        "filters": filters,
        "candidate_count": len(candidates),
        "ranked": ranked_records,
    }


# --- Comparison table (chat_json) ----------------------------------------
COMPARISON_SYSTEM = (
    "You are an MPF planning analyst at Blount Island Command. "
    "Given the planner's question and a short list of candidate ports (as JSON), "
    "produce a strict JSON object with key `comparison` mapped to an array. "
    "Each array element MUST contain exactly: "
    "port_id, name, country, fit_score (0-10 numeric), "
    "key_strengths (array of <=3 short strings), "
    "key_risks (array of <=3 short strings), "
    "recommended_role (one of: 'Primary MPF Offload', 'Backup Offload', 'Bunker/Replenishment Only', 'Anchorage Only', 'Avoid'). "
    "Score on capability fit + risk posture. Do not invent ports — only score those provided."
)


def comparison_json(query: str, ranked: list[dict]) -> dict:
    payload = [
        {k: v for k, v in r.items() if k != "profile"}
        for r in ranked
    ]
    return chat_json(
        [
            {"role": "system", "content": COMPARISON_SYSTEM},
            {"role": "user", "content": (
                f"Planner question:\n{query}\n\n"
                f"Candidate ports JSON:\n{json.dumps(payload, indent=2)}\n\n"
                "Return JSON now."
            )},
        ],
        schema_hint="{ comparison: [ {port_id, name, country, fit_score, key_strengths, key_risks, recommended_role}, ... ] }",
        temperature=0.2,
    )


# --- Narrative recommendation (chat — streamed) --------------------------
NARRATIVE_SYSTEM = (
    "You are a senior MPF planner at Marine Corps Blount Island Command. "
    "Write a concise (250-350 word) operator-grade recommendation to a Marine Corps "
    "Logistics Command (MARCORLOGCOM) action officer. Use this structure verbatim: "
    "1) BLUF (one sentence).  2) Recommended Primary Port.  3) Backup Option.  "
    "4) Risk Notes (host-nation, weather, capability gaps).  5) Next Action (one bullet). "
    "Reference specific numbers (draft, channel depth, distance). Do not hedge with disclaimers."
)


def narrative_stream(query: str, ranked: list[dict], comparison: dict, *, hero: bool = False) -> Iterator[str]:
    """Yield streaming chunks of the narrative recommendation."""
    client = get_client()
    payload = {
        "planner_question": query,
        "ranked_ports": [
            {k: v for k, v in r.items() if k != "profile"} for r in ranked[:6]
        ],
        "comparison": comparison.get("comparison", []),
    }
    model = "gpt-5.4" if hero else PRIMARY_MODEL
    chain = [model, "gpt-5.4-mini", "gpt-5-mini", "gpt-4o-mini", "gpt-4o"]

    last_err: Exception | None = None
    for m in chain:
        try:
            stream = client.chat.completions.create(
                model=m,
                messages=[
                    {"role": "system", "content": NARRATIVE_SYSTEM},
                    {"role": "user", "content": json.dumps(payload, indent=2)},
                ],
                temperature=0.4,
                stream=True,
            )
            for chunk in stream:
                delta = chunk.choices[0].delta.content if chunk.choices else None
                if delta:
                    yield delta
            return
        except Exception as e:  # noqa: BLE001
            last_err = e
            continue
    yield f"\n\n[Narrative generation failed: {last_err}]"
