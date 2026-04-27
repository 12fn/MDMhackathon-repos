"""AGORA — Persona + role-aware RAG retrieval.

Hero AI move:
  1) chat_json parses intent + checks role permissions for the persona.
  2) embed() over the synthetic ecosystem doc corpus.
  3) Cosine retrieves top-3 docs the persona is *authorized* to see
     (others are filtered out by ABAC/RBAC and surface in the audit panel).
  4) chat() answers using ONLY the authorized docs, with explicit citations.
"""
from __future__ import annotations

import json
import sys
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutTimeout
from functools import lru_cache
from pathlib import Path
from typing import Any

import numpy as np

ROOT = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(ROOT))

from shared.kamiwaza_client import chat, chat_json, embed, PRIMARY_MODEL  # noqa: E402

DATA = Path(__file__).resolve().parent.parent / "data"

# Role rank — used for min_role gating
ROLE_RANK = {
    "none": 0,
    "viewer": 1, "student": 1,
    "instructor": 2, "author": 2, "moderator": 2, "host": 2, "operator": 2,
    "manager": 3, "approver": 3,
    "admin": 4, "auditor": 4,
}

CLASS_RANK = {"UNCLASS": 0, "FOUO": 1, "CUI": 2, "SECRET": 3}


# ─────────────────────────────────────────────────────────────────────────────
# Data load
# ─────────────────────────────────────────────────────────────────────────────
@lru_cache(maxsize=1)
def load_personas() -> list[dict]:
    return json.loads((DATA / "personas.json").read_text())


@lru_cache(maxsize=1)
def load_corpus() -> list[dict]:
    docs = []
    with (DATA / "corpus.jsonl").open() as f:
        for line in f:
            line = line.strip()
            if line:
                docs.append(json.loads(line))
    return docs


@lru_cache(maxsize=1)
def load_embeddings() -> np.ndarray:
    return np.load(DATA / "embeddings.npy")


@lru_cache(maxsize=1)
def load_cached_briefs() -> dict:
    p = DATA / "cached_briefs.json"
    if not p.exists():
        return {"scenarios": {}}
    return json.loads(p.read_text())


# ─────────────────────────────────────────────────────────────────────────────
# Authorization (RBAC + ABAC)
# ─────────────────────────────────────────────────────────────────────────────
def authorize_doc(persona: dict, doc: dict) -> tuple[bool, str]:
    """Return (is_authorized, human_reason). Reason is empty when authorized."""
    app = doc["app"]
    persona_app = persona["roles"].get(app, {"role": "none", "perms": []})
    persona_role = persona_app.get("role", "none")
    p_rank = ROLE_RANK.get(persona_role, 0)
    d_rank = ROLE_RANK.get(doc["min_role"], 0)

    # 1. RBAC — role must meet min_role for the app
    if p_rank < d_rank:
        return False, (
            f"RBAC: needs {app} role '{doc['min_role']}' (rank {d_rank}); "
            f"persona has '{persona_role}' (rank {p_rank})."
        )

    # 2. ABAC — classification must be ≤ persona max_class
    pmax = persona["abac"]["max_class"]
    if CLASS_RANK.get(doc["classification"], 0) > CLASS_RANK.get(pmax, 0):
        return False, (
            f"ABAC: doc classification '{doc['classification']}' > persona max_class '{pmax}'."
        )

    # 3. ABAC — scope match. VENDOR-scoped docs are vendor-only
    scope = doc.get("scope", "ALL")
    units = persona["abac"].get("unit_scope", [])
    is_vendor = any("VENDOR" in u for u in units)
    if scope == "VENDOR" and not is_vendor:
        return False, "ABAC: scope=VENDOR; persona is not in a vendor unit_scope."
    if scope in ("UNIT", "BATTALION") and is_vendor:
        return False, f"ABAC: scope={scope}; vendor scope cannot read uniformed-unit docs."
    if scope == "BATTALION" and p_rank < ROLE_RANK["manager"]:
        return False, (
            "ABAC: scope=BATTALION; persona role rank insufficient for battalion-scoped content."
        )

    return True, ""


def cosine_topk(qvec: np.ndarray, mat: np.ndarray, allowed_idx: list[int], k: int = 3) -> list[tuple[int, float]]:
    """Cosine similarity over allowed rows only. Returns (idx, score) descending."""
    if not allowed_idx:
        return []
    sub = mat[allowed_idx]            # (m, d)
    scores = sub @ qvec                # (m,)
    order = np.argsort(-scores)[:k]
    return [(allowed_idx[i], float(scores[i])) for i in order]


# ─────────────────────────────────────────────────────────────────────────────
# Intent parser (LLM → structured)
# ─────────────────────────────────────────────────────────────────────────────
INTENT_SYS = (
    "You are AGORA, a context- and role-aware AI support agent for a USMC "
    "ecosystem of web apps (LMS, CMS, BBB, Keycloak). A user with a known "
    "persona just asked a support question. Convert their question into a "
    "strict JSON intent object so downstream code can route + authorize. "
    "Never invent permissions the persona does not have."
)

INTENT_HINT = (
    "Keys: target_apps (array of any of: LMS, CMS, BBB, Keycloak), "
    "topic (short string), action (one of: 'view','create','submit','approve','publish','export','admin','login','reset','other'), "
    "needs_role_at_least (one of: 'viewer','student','instructor','author','moderator','host','operator','manager','approver','admin','auditor'), "
    "sensitive (boolean — true if the request implies CUI / unit-scoped data), "
    "rationale (one sentence explaining why this intent matches)."
)


def parse_intent(persona: dict, query: str, *, timeout: int = 12) -> dict:
    msgs = [
        {"role": "system", "content": INTENT_SYS},
        {"role": "user", "content": (
            f"Persona JSON:\n{json.dumps({k: persona[k] for k in ('id','name','rank','billet','roles','abac')}, indent=2)}\n\n"
            f"User asked: {query}\n\nReturn the JSON intent."
        )},
    ]

    def _call() -> dict:
        return chat_json(msgs, schema_hint=INTENT_HINT, temperature=0.1)

    with ThreadPoolExecutor(max_workers=1) as ex:
        try:
            return ex.submit(_call).result(timeout=timeout)
        except FutTimeout:
            return _baseline_intent(persona, query)
        except Exception:
            return _baseline_intent(persona, query)


def _baseline_intent(persona: dict, query: str) -> dict:
    """Deterministic fallback so the demo never freezes."""
    q = query.lower()
    apps = []
    for a in ("LMS", "CMS", "BBB", "Keycloak"):
        if a.lower() in q or (a == "LMS" and "marinenet" in q):
            apps.append(a)
    if not apps:
        # Crude heuristic
        if any(w in q for w in ("course", "transcript", "enroll", "grade")):
            apps = ["LMS"]
        elif any(w in q for w in ("page", "publish", "announce")):
            apps = ["CMS"]
        elif any(w in q for w in ("meeting", "record", "host")):
            apps = ["BBB"]
        elif any(w in q for w in ("login", "password", "role", "audit")):
            apps = ["Keycloak"]
        else:
            apps = ["LMS"]
    return {
        "target_apps": apps,
        "topic": query[:64],
        "action": "view",
        "needs_role_at_least": "viewer",
        "sensitive": "cui" in q or "approve" in q or "audit" in q,
        "rationale": "Heuristic fallback (LLM intent parse unavailable).",
    }


# ─────────────────────────────────────────────────────────────────────────────
# Answer rendering — uses ONLY authorized docs, with citations
# ─────────────────────────────────────────────────────────────────────────────
ANSWER_SYS = (
    "You are AGORA, a persona-aware AI support agent for a USMC ecosystem of "
    "web apps (LMS, CMS, BBB, Keycloak). You answer the user's question using "
    "ONLY the help-content snippets provided. Each snippet carries an "
    "authorization tag — the platform has already enforced ABAC/RBAC, so "
    "every snippet you receive is one this persona is allowed to read. "
    "Cite snippets inline as [DOC-NNN]. If the persona's role doesn't permit "
    "the action they're asking about, say so plainly and suggest the correct "
    "next step (e.g. 'request the manager role from your S-1' or 'route this "
    "to your S-3 approver'). Never invent doc IDs. Never quote unauthorized "
    "content even if you remember it from training. Keep answers under 180 words."
)


def render_answer(persona: dict, query: str, docs: list[dict], *, hero: bool = False, timeout: int = 18) -> str:
    if not docs:
        return (
            f"You ({persona['name']}, {persona['billet']}) don't have access to any "
            f"help content that matches this request given your current roles "
            f"({json.dumps({a: r['role'] for a, r in persona['roles'].items()})}). "
            f"If you believe you should, request the appropriate role from your unit's "
            f"Keycloak operator or your S-1."
        )

    snippets = "\n\n".join(
        f"[{d['doc_id']}] ({d['app']} · min_role={d['min_role']} · class={d['classification']} · scope={d['scope']})\n"
        f"{d['title']}\n{d['body']}"
        for d in docs
    )
    msgs = [
        {"role": "system", "content": ANSWER_SYS},
        {"role": "user", "content": (
            f"Persona: {persona['name']} ({persona['rank']}, {persona['billet']}). "
            f"Roles: {json.dumps(persona['roles'])}. ABAC: {json.dumps(persona['abac'])}.\n\n"
            f"User question: {query}\n\n"
            f"--- Authorized help snippets ---\n{snippets}\n--- End snippets ---\n\n"
            "Answer in plain operator prose with inline [DOC-NNN] citations."
        )},
    ]
    model = None if not hero else (PRIMARY_MODEL if PRIMARY_MODEL.endswith("mini") else PRIMARY_MODEL)
    # 'hero' is a UI affordance — we keep the call routed through PRIMARY_MODEL by default.

    def _call() -> str:
        return chat(msgs, model=model, temperature=0.3)

    with ThreadPoolExecutor(max_workers=1) as ex:
        try:
            return ex.submit(_call).result(timeout=timeout)
        except FutTimeout:
            return _baseline_answer(persona, query, docs)
        except Exception as e:  # noqa: BLE001
            return _baseline_answer(persona, query, docs) + f"\n\n_(fallback — live model unavailable: {e})_"


def _baseline_answer(persona: dict, query: str, docs: list[dict]) -> str:
    """Deterministic stitched answer if the LLM call times out."""
    cites = ", ".join(f"[{d['doc_id']}]" for d in docs)
    parts = [f"**For {persona['name']} ({persona['billet']}):**"]
    for d in docs:
        parts.append(f"- **[{d['doc_id']}] ({d['app']}) {d['title']}** — {d['body'][:220]}…")
    parts.append(f"\nSources: {cites}.")
    return "\n".join(parts)


# ─────────────────────────────────────────────────────────────────────────────
# End-to-end
# ─────────────────────────────────────────────────────────────────────────────
def answer_for_persona(persona_id: str, query: str, *, k: int = 3, hero: bool = False) -> dict:
    """Full pipeline. Returns dict the UI consumes."""
    personas = load_personas()
    persona = next(p for p in personas if p["id"] == persona_id)
    docs = load_corpus()
    embeddings = load_embeddings()

    # Embed query (separate try — fall back to a uniform vec)
    try:
        qraw = embed([query])[0]
        qvec = np.array(qraw, dtype=np.float32)
        qvec = qvec / (np.linalg.norm(qvec) + 1e-12)
    except Exception:
        qvec = np.ones(embeddings.shape[1], dtype=np.float32)
        qvec /= np.linalg.norm(qvec)

    # Authorize every doc, partition into allowed/denied
    allowed_idx: list[int] = []
    denied: list[dict] = []
    for i, d in enumerate(docs):
        ok, why = authorize_doc(persona, d)
        if ok:
            allowed_idx.append(i)
        else:
            denied.append({
                "doc_id": d["doc_id"], "app": d["app"], "title": d["title"],
                "min_role": d["min_role"], "classification": d["classification"],
                "scope": d["scope"], "reason": why,
            })

    # Cosine over authorized only
    top = cosine_topk(qvec, embeddings, allowed_idx, k=k)
    cited = [{**docs[i], "similarity": round(score, 4)} for i, score in top]
    intent = parse_intent(persona, query)
    answer = render_answer(persona, query, cited, hero=hero)

    # Compute "would have retrieved" — the top-K if no ABAC/RBAC was applied
    all_idx = list(range(len(docs)))
    raw_top = cosine_topk(qvec, embeddings, all_idx, k=k)
    raw_ids = [docs[i]["doc_id"] for i, _ in raw_top]

    return {
        "persona": persona,
        "intent": intent,
        "cited": cited,
        "denied_top": denied,        # full denied list — UI shows the top relevant
        "raw_top_ids": raw_ids,       # for the "would-have" comparison
        "answer": answer,
    }
