"""GUARDRAIL — SHA-256 hash-chained audit log.

ONE chain across all four governance layers:
  - CUI marking decisions
  - ABAC enforcement (paragraph view / redaction)
  - Browser-AI gov (allow / block)
  - AI assistant queries (RAG + denied docs)

Every entry binds the previous entry's hash; tampering with any row breaks
the chain at verify time. Pattern lifted from REDLINE / GUARDIAN audit chains.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

GENESIS = "0" * 64

APP_DIR = Path(__file__).resolve().parents[1]
AUDIT_DIR = APP_DIR / "audit_logs"
AUDIT_DIR.mkdir(parents=True, exist_ok=True)
AUDIT_LOG = AUDIT_DIR / "guardrail_audit.jsonl"


def sha256_text(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def last_hash() -> str:
    if not AUDIT_LOG.exists():
        return GENESIS
    last = GENESIS
    with AUDIT_LOG.open() as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                last = json.loads(line).get("entry_hash", last)
            except json.JSONDecodeError:
                continue
    return last


def append(body: dict[str, Any]) -> dict[str, Any]:
    """Append a chained entry. Returns the full record."""
    entry = {k: v for k, v in body.items() if k != "entry_hash"}
    entry["prev_hash"] = last_hash()
    entry["timestamp_utc"] = datetime.now(timezone.utc).isoformat()
    entry["entry_hash"] = sha256_text(json.dumps(entry, sort_keys=True, default=str))
    with AUDIT_LOG.open("a") as f:
        f.write(json.dumps(entry, default=str) + "\n")
    return entry


def read(limit: int | None = 25) -> list[dict[str, Any]]:
    if not AUDIT_LOG.exists():
        return []
    out: list[dict[str, Any]] = []
    with AUDIT_LOG.open() as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    if limit:
        out = out[-limit:]
    return out[::-1]  # newest first


def verify() -> dict[str, Any]:
    """Walk the chain end-to-end. Returns ok flag + counts."""
    if not AUDIT_LOG.exists():
        return {"ok": True, "entries": 0, "tip_hash": GENESIS}
    prev = GENESIS
    entries: list[dict[str, Any]] = []
    with AUDIT_LOG.open() as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    for i, e in enumerate(entries):
        body = {k: v for k, v in e.items() if k != "entry_hash"}
        recomputed = sha256_text(json.dumps(body, sort_keys=True, default=str))
        if e.get("prev_hash") != prev:
            return {"ok": False, "entries": len(entries), "broken_at": i, "reason": "prev_hash mismatch"}
        if recomputed != e.get("entry_hash"):
            return {"ok": False, "entries": len(entries), "broken_at": i, "reason": "entry_hash mismatch"}
        prev = e["entry_hash"]
    return {"ok": True, "entries": len(entries), "tip_hash": prev}


def reset() -> None:
    if AUDIT_LOG.exists():
        AUDIT_LOG.unlink()


def counts_by_layer() -> dict[str, int]:
    chain = read(limit=10_000)
    out: dict[str, int] = {}
    for c in chain:
        layer = c.get("layer", "?")
        out[layer] = out.get(layer, 0) + 1
    return out
