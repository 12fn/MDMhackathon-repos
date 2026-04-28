"""SHA-256 chained append-only audit log for CADENCE.

Pattern lifted from apps/10-sentinel/src/app.py and apps/32-learn/src/agent.py.

Every assessment CADENCE makes about a Marine — analysis, study plan, peer
suggestion — is appended to data/audit_logs/cadence_audit.jsonl with a
SHA-256 chain so any cognitive-developer / IG / SJA can replay how the
recommendation was made months later. Records governance for these
Military Education Records: **Privacy Act of 1974 (5 U.S.C. § 552a) and
DoDI 1322.35 "Military Education Records"** — NOT FERPA. FERPA governs
K-12 / civilian higher-ed; active-duty military training records are
Privacy-Act-and-DoDI-1322.35 governed.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

APP_ROOT = Path(__file__).resolve().parents[1]
AUDIT_DIR = APP_ROOT / "data" / "audit_logs"
AUDIT_DIR.mkdir(parents=True, exist_ok=True)
AUDIT_LOG = AUDIT_DIR / "cadence_audit.jsonl"


def sha256_text(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def _last_hash() -> str:
    if not AUDIT_LOG.exists():
        return "0" * 64
    last = "0" * 64
    with AUDIT_LOG.open() as f:
        for ln in f:
            ln = ln.strip()
            if not ln:
                continue
            try:
                last = json.loads(ln).get("entry_hash", last)
            except json.JSONDecodeError:
                continue
    return last


def append(entry: dict) -> dict:
    """Append a chained entry. entry_hash = sha256(json(prev_hash + body))."""
    body = {k: v for k, v in entry.items() if k != "entry_hash"}
    body["prev_hash"] = _last_hash()
    body["timestamp_utc"] = datetime.now(timezone.utc).isoformat()
    body["entry_hash"] = sha256_text(json.dumps(body, sort_keys=True, default=str))
    with AUDIT_LOG.open("a") as f:
        f.write(json.dumps(body, default=str) + "\n")
    return body


def read_chain(limit: int = 25) -> list[dict]:
    if not AUDIT_LOG.exists():
        return []
    out: list[dict] = []
    with AUDIT_LOG.open() as f:
        for ln in f:
            ln = ln.strip()
            if not ln:
                continue
            try:
                out.append(json.loads(ln))
            except json.JSONDecodeError:
                continue
    return out[-limit:][::-1]  # newest first
