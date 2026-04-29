"""OMNI — SHA-256 hash-chained who-saw-what audit log.

Every persona switch and every brief view writes a chained record. Pattern
lifted from apps/30-guardian. This is the Browser-AI-Governance tie-in:
the same audit chain that would record AI-agent reads of an SOR is used to
record the I-COP operator reads of cross-domain alerts. SJA / IG-replayable.

Each record:
  - prev_hash      : entry_hash of previous record (or 64x"0" genesis)
  - timestamp_utc  : ISO8601
  - persona_id     : who
  - action         : VIEW_DASHBOARD | VIEW_BRIEF | VIEW_STREAM | VIEW_ANOMALY |
                     PERSONA_SWITCH
  - target         : free-form (stream name, anomaly_id, brief, etc.)
  - meta           : dict (e.g. allowed_streams snapshot, denied_streams)
  - entry_hash     : sha256(json(body+prev_hash+timestamp_utc))
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

APP_DIR = Path(__file__).resolve().parents[1]
AUDIT_DIR = APP_DIR / "audit_logs"
AUDIT_DIR.mkdir(parents=True, exist_ok=True)
AUDIT_LOG = AUDIT_DIR / "omni_audit.jsonl"


def sha256_text(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def last_audit_hash() -> str:
    if not AUDIT_LOG.exists():
        return "0" * 64
    last = "0" * 64
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


def append_audit(entry: dict) -> dict:
    body = {k: v for k, v in entry.items() if k != "entry_hash"}
    body["prev_hash"] = last_audit_hash()
    body["timestamp_utc"] = datetime.now(timezone.utc).isoformat()
    body["entry_hash"] = sha256_text(json.dumps(body, sort_keys=True, default=str))
    with AUDIT_LOG.open("a") as f:
        f.write(json.dumps(body, default=str) + "\n")
    return body


def read_audit_chain(limit: int = 50) -> list[dict]:
    if not AUDIT_LOG.exists():
        return []
    out: list[dict] = []
    with AUDIT_LOG.open() as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return out[-limit:][::-1]  # newest first


def verify_chain() -> tuple[bool, int, str]:
    if not AUDIT_LOG.exists():
        return True, 0, "Empty chain (genesis not written yet)."
    prev = "0" * 64
    n = 0
    with AUDIT_LOG.open() as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            n += 1
            if row.get("prev_hash") != prev:
                return False, n, f"prev_hash mismatch at row {n}"
            body = {k: v for k, v in row.items() if k != "entry_hash"}
            recomputed = sha256_text(json.dumps(body, sort_keys=True, default=str))
            if recomputed != row.get("entry_hash"):
                return False, n, f"entry_hash mismatch at row {n}"
            prev = row["entry_hash"]
    return True, n, f"OK — {n} entries verified, chain integrity intact"


def reset_audit_log() -> None:
    if AUDIT_LOG.exists():
        AUDIT_LOG.unlink()
