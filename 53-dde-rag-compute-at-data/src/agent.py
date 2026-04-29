"""DDE-RAG agent — composes the federated answer from per-node retrievals.

Cache-first hero call: pre-warmed answers live in data/cached_briefs.json.
The "Run live" button hits the LLM behind a 35s wall-clock timeout with a
deterministic markdown-template fallback so the demo never sits on a spinner.
"""
from __future__ import annotations

import hashlib
import json
import sys
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutTimeout
from datetime import datetime, timezone
from pathlib import Path

APP_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = Path(__file__).resolve().parents[3]
DATA_DIR = APP_ROOT / "data"
CACHE_PATH = DATA_DIR / "cached_briefs.json"
AUDIT_PATH = DATA_DIR / "audit_logs" / "dde_audit.jsonl"

for p in (str(REPO_ROOT), str(APP_ROOT)):
    if p not in sys.path:
        sys.path.insert(0, p)

from src.dde import load_corpus  # noqa: E402

HERO_SYSTEM = """You are DDE-RAG, an analyst running on the Kamiwaza
Distributed Data Engine. You federate a USMC LOGCOM question across three
data-bearing installations:

  - MCLB Albany    (GCSS-MC work orders)
  - MCB Lejeune    (ICM lateral-transfer + parts records)
  - MCB Quantico   (NSN-tagged technical-manual library — CUI/ICD-503 enclave)

The data NEVER leaves its node. You receive only the per-node retrievals.
Compose a polished BLUF-first answer in markdown with these EXACT sections:

  ### BLUF
  ### Findings (per-node)
  ### Federated recommendation
  ### Compute-at-data posture

Constraints:
  - BLUF: one bold sentence stating the federated answer.
  - Findings: one bullet per involved node, prefixed with the node label,
    citing concrete serials / NSNs / units pulled from the retrievals.
  - Recommendation: 2-3 numbered actions tied to a specific Marine, depot, or
    NSN.
  - Compute-at-data posture: one short paragraph reaffirming that the answer
    was composed without moving any source data; cite ICD 503 + DCSA
    spillage controls where relevant.
  - Do NOT mention the underlying AI provider or model name.
"""


def _retrieve(query: dict) -> dict[str, list[dict]]:
    """Naive keyword retrieval against each involved node's local corpus."""
    q = (query.get("question") or "").lower()
    keywords = [w.strip(".,?\"'") for w in q.split() if len(w) > 3]
    out: dict[str, list[dict]] = {}
    for node_id in query.get("involves", []):
        chunks = load_corpus(node_id)
        scored: list[tuple[int, dict]] = []
        for ch in chunks:
            text = (ch.get("summary", "") + " " +
                    json.dumps(ch.get("metadata", {}))).lower()
            score = sum(1 for k in keywords if k in text)
            if score:
                scored.append((score, ch))
        scored.sort(key=lambda x: -x[0])
        # If nothing matched, surface the first 3 chunks — this is a demo and
        # the synthetic corpora are small.
        if scored:
            out[node_id] = [ch for _, ch in scored[:5]]
        else:
            out[node_id] = chunks[:3]
    return out


def _fallback_answer(query: dict, nodes: list[dict],
                     trace: dict, retrieved: dict[str, list[dict]]) -> str:
    nodes_by_id = {n["id"]: n for n in nodes}
    findings = []
    for node_id, chunks in retrieved.items():
        n = nodes_by_id.get(node_id, {"label": node_id})
        if not chunks:
            findings.append(f"- **{n.get('label', node_id)}** — no matching records "
                            "within the local corpus window.")
            continue
        bullet_lines = "; ".join(
            ch.get("summary", "")[:160].rstrip(".") for ch in chunks[:2]
        )
        findings.append(f"- **{n.get('label', node_id)}** — {bullet_lines}.")

    primary_node_id = query.get("primary_node") or (
        next(iter(retrieved.keys()), "albany"))
    primary_node = nodes_by_id.get(primary_node_id, {"label": primary_node_id})

    return (
        f"### BLUF\n"
        f"**Federated DDE answer composed across "
        f"{len(retrieved)} data nodes with **zero data movement** — see "
        f"per-node findings below.**\n\n"
        f"### Findings (per-node)\n"
        + "\n".join(findings) + "\n\n"
        f"### Federated recommendation\n"
        f"1. Direct the supply NCO at **{primary_node.get('label')}** to action the "
        f"highest-confidence finding above before EOB.\n"
        f"2. Push a Class IX lateral-transfer request from the node holding the "
        f"surplus inventory; route through the Kamiwaza Model Gateway (no data "
        f"copies, just the lateral plan).\n"
        f"3. Re-run this question after 24h to validate the recommendation has "
        f"closed the readiness gap.\n\n"
        f"### Compute-at-data posture\n"
        f"Inference containers ran AT each data node. The Quantico TM corpus "
        f"never left its CUI/ICD-503 enclave; the GCSS-MC work-order rows never "
        f"left Albany; the ICM workbook never left the Lejeune deployable cell. "
        f"Total wire-traffic: **{trace['dde']['bytes']:,} bytes** "
        f"(vs **{trace['naive']['bytes']:,} bytes** for the naive central-RAG path). "
        f"DCSA spillage class: GREEN.\n"
    )


def compose_answer(query: dict, nodes: list[dict], trace: dict,
                   *, use_cache: bool = True, timeout_s: int = 35) -> str:
    """Compose the federated answer. Cache → live LLM → deterministic fallback."""
    if use_cache:
        cached = load_cached_briefs()
        if query["id"] in cached and cached[query["id"]].get("answer"):
            return cached[query["id"]]["answer"]

    retrieved = _retrieve(query)

    # Try the LLM, but never let it block past the timeout
    try:
        from shared.kamiwaza_client import chat
    except Exception:
        chat = None  # type: ignore[assignment]

    if chat is not None:
        prompt = _build_prompt(query, nodes, trace, retrieved)
        try:
            with ThreadPoolExecutor(max_workers=1) as ex:
                fut = ex.submit(
                    lambda: chat(
                        [
                            {"role": "system", "content": HERO_SYSTEM},
                            {"role": "user",   "content": prompt},
                        ],
                        temperature=0.3,
                    )
                )
                text = fut.result(timeout=timeout_s)
            if text and "BLUF" in text:
                return text
        except FutTimeout:
            pass
        except Exception:
            pass

    return _fallback_answer(query, nodes, trace, retrieved)


def _build_prompt(query: dict, nodes: list[dict], trace: dict,
                  retrieved: dict[str, list[dict]]) -> str:
    nodes_by_id = {n["id"]: n for n in nodes}
    blocks: list[str] = []
    for node_id, chunks in retrieved.items():
        n = nodes_by_id.get(node_id, {})
        head = (f"### {n.get('label', node_id)} — "
                f"{n.get('security_posture', '')} ({n.get('compliance_authority','')})")
        body = "\n".join(f"- {ch.get('summary','')}" for ch in chunks)
        blocks.append(f"{head}\n{body}")
    return (
        f"FEDERATED QUESTION (id={query['id']}): {query.get('question')}\n"
        f"FRAME: {query.get('frame')}\n"
        f"STAKES: {query.get('stakes')}\n\n"
        f"PER-NODE RETRIEVALS (compute already ran AT the data; only these "
        f"summaries crossed the wire):\n\n"
        + "\n\n".join(blocks)
        + f"\n\nDDE EXECUTION TRACE: "
          f"naive={trace['naive']['bytes']:,}B / {trace['naive']['seconds']}s, "
          f"dde={trace['dde']['bytes']:,}B / {trace['dde']['seconds']}s.\n\n"
          "Compose the federated answer now."
    )


def load_cached_briefs() -> dict[str, dict]:
    if CACHE_PATH.exists():
        try:
            return json.loads(CACHE_PATH.read_text())
        except Exception:
            return {}
    return {}


# ---------------------------------------------------------------------------
# Hash-chained DDE audit log
# ---------------------------------------------------------------------------
def _last_hash() -> str:
    if not AUDIT_PATH.exists():
        return "0" * 64
    last = ""
    for line in AUDIT_PATH.read_text().splitlines():
        line = line.strip()
        if line:
            last = line
    if not last:
        return "0" * 64
    try:
        return json.loads(last).get("hash", "0" * 64)
    except Exception:
        return "0" * 64


def append_audit(query: dict, trace: dict, *, source: str) -> dict:
    """Append a single dispatch decision to the hash-chained audit log."""
    AUDIT_PATH.parent.mkdir(parents=True, exist_ok=True)
    nodes = [s.get("node") for s in trace["dde"]["steps"]
             if s.get("kind") == "COMPUTE"]
    rec = {
        "ts":          datetime.now(timezone.utc).isoformat(),
        "query_id":    query["id"],
        "question":    query.get("question", ""),
        "dispatched_to": nodes,
        "naive_bytes":   trace["naive"]["bytes"],
        "dde_bytes":     trace["dde"]["bytes"],
        "naive_seconds": trace["naive"]["seconds"],
        "dde_seconds":   trace["dde"]["seconds"],
        "compliance":    trace["dde"]["compliance"],
        "source":        source,
        "prev_hash":     _last_hash(),
    }
    payload = json.dumps(rec, sort_keys=True).encode("utf-8")
    rec["hash"] = hashlib.sha256(payload).hexdigest()
    with open(AUDIT_PATH, "a") as f:
        f.write(json.dumps(rec) + "\n")
    return rec


def load_audit(tail: int = 12) -> list[dict]:
    if not AUDIT_PATH.exists():
        return []
    lines = AUDIT_PATH.read_text().strip().splitlines()
    out = []
    for ln in lines[-tail:]:
        try:
            out.append(json.loads(ln))
        except Exception:
            continue
    return out
