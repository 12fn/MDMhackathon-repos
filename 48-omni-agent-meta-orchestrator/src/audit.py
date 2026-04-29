"""SHA-256 hash-chained audit log of every OMNI-AGENT tool invocation.

Each line is a JSON record:
  { "ts": "...", "query_id": "...", "tool": "...", "args": {...},
    "result_digest": "<sha256 of canonical-JSON result>",
    "prev_hash": "...", "hash": "..." }

The chain seeds at "GENESIS". Tampering with any earlier record breaks the
chain — the verify_chain() helper proves it.
"""
from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path

AUDIT_PATH = Path(__file__).resolve().parent.parent / "audit_logs" / "orchestrator_audit.jsonl"
AUDIT_PATH.parent.mkdir(parents=True, exist_ok=True)


def _last_hash() -> str:
    if not AUDIT_PATH.exists():
        return "GENESIS"
    last = "GENESIS"
    with AUDIT_PATH.open() as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
                last = rec.get("hash", last)
            except json.JSONDecodeError:
                continue
    return last


def _digest_result(result: dict) -> str:
    body = json.dumps(result, sort_keys=True, default=str)
    return sha256(body.encode()).hexdigest()


def append(query_id: str, tool: str, args: dict, result: dict,
           latency_ms: int) -> dict:
    """Append a tool invocation record. Returns the full record (with hash)."""
    prev = _last_hash()
    payload = {
        "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "query_id": query_id,
        "tool": tool,
        "args": args,
        "result_digest": _digest_result(result),
        "result_codename": result.get("codename"),
        "result_app_dir": result.get("app_dir"),
        "result_port": result.get("port"),
        "latency_ms": latency_ms,
        "prev_hash": prev,
    }
    body = json.dumps(payload, sort_keys=True)
    h = sha256((prev + "|" + body).encode()).hexdigest()
    rec = {**payload, "hash": h}
    with AUDIT_PATH.open("a") as f:
        f.write(json.dumps(rec) + "\n")
    return rec


def tail(n: int = 25) -> list[dict]:
    if not AUDIT_PATH.exists():
        return []
    out: list[dict] = []
    with AUDIT_PATH.open() as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return out[-n:]


def verify_chain() -> tuple[bool, int, str]:
    """Return (ok, n_records, message)."""
    if not AUDIT_PATH.exists():
        return True, 0, "empty"
    prev = "GENESIS"
    n = 0
    with AUDIT_PATH.open() as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                return False, n, f"bad json at record {n}"
            n += 1
            payload = {k: v for k, v in rec.items() if k != "hash"}
            body = json.dumps(payload, sort_keys=True)
            expect = sha256((prev + "|" + body).encode()).hexdigest()
            if expect != rec.get("hash"):
                return False, n, f"hash mismatch at record {n}"
            if rec.get("prev_hash") != prev:
                return False, n, f"prev_hash mismatch at record {n}"
            prev = rec["hash"]
    return True, n, f"verified {n} records"


def reset() -> None:
    """Wipe the audit log. Used by tests + the demo prep."""
    if AUDIT_PATH.exists():
        AUDIT_PATH.unlink()
