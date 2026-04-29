"""Hash-chained audit log of every fusion-cluster decision.

Every time the OMNI correlator emits a cluster (or the LLM classifier assigns
a label), we append an entry to audit_logs/fusion_chain.jsonl with:

    {
      seq:        monotonically increasing
      ts:         ISO-8601 UTC
      cluster_id: FC-XXXXXXXX
      action:     "correlate" | "classify" | "brief"
      payload:    decision body
      prev_hash:  sha256 of previous entry
      this_hash:  sha256 of (prev_hash + canonical(payload))
    }

Tamper-evident: any modification of a past entry breaks the chain.
For SIGINT/HUMINT auditability per ICD 501.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
LOG_DIR = ROOT / "audit_logs"
LOG_DIR.mkdir(exist_ok=True)
LOG_PATH = LOG_DIR / "fusion_chain.jsonl"

_lock = Lock()


def _last_state() -> tuple[int, str]:
    if not LOG_PATH.exists():
        return 0, "0" * 16
    seq = 0
    last_hash = "0" * 16
    with LOG_PATH.open() as f:
        for line in f:
            try:
                rec = json.loads(line)
                seq = rec.get("seq", seq)
                last_hash = rec.get("this_hash", last_hash)
            except Exception:
                continue
    return seq, last_hash


def append(action: str, cluster_id: str, payload: dict[str, Any]) -> dict:
    with _lock:
        seq, prev = _last_state()
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        body = f"{prev}|{seq + 1}|{ts}|{cluster_id}|{action}|{canonical}"
        this_hash = hashlib.sha256(body.encode()).hexdigest()[:16]
        entry = {
            "seq": seq + 1,
            "ts": ts,
            "cluster_id": cluster_id,
            "action": action,
            "payload": payload,
            "prev_hash": prev,
            "this_hash": this_hash,
        }
        with LOG_PATH.open("a") as f:
            f.write(json.dumps(entry) + "\n")
        return entry


def verify_chain() -> tuple[bool, int, str]:
    """Re-walk the chain and confirm every hash links. Returns (ok, n, msg)."""
    if not LOG_PATH.exists():
        return True, 0, "empty chain"
    prev = "0" * 16
    n = 0
    with LOG_PATH.open() as f:
        for line in f:
            rec = json.loads(line)
            n += 1
            canonical = json.dumps(rec["payload"], sort_keys=True, separators=(",", ":"))
            body = f"{prev}|{rec['seq']}|{rec['ts']}|{rec['cluster_id']}|{rec['action']}|{canonical}"
            check = hashlib.sha256(body.encode()).hexdigest()[:16]
            if check != rec["this_hash"]:
                return False, n, f"break at seq {rec['seq']}"
            prev = rec["this_hash"]
    return True, n, "intact"


def tail(n: int = 20) -> list[dict]:
    if not LOG_PATH.exists():
        return []
    rows: list[dict] = []
    with LOG_PATH.open() as f:
        for line in f:
            try:
                rows.append(json.loads(line))
            except Exception:
                pass
    return rows[-n:]
