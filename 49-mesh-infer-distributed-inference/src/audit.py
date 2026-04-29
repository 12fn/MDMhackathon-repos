"""Hash-chained routing audit log for MESH-INFER.

Every routing decision is appended to data/routing_audit.jsonl with a SHA-256
chain over the previous entry's hash + the new payload. The SJA can verify
end-to-end that no entry was tampered with — and answer questions like
"did step 3 of scenario X ever leave the SCIF?" with one jq query.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

AUDIT_PATH = Path(__file__).resolve().parent.parent / "data" / "routing_audit.jsonl"


def _hash(prev_hash: str, payload: dict) -> str:
    h = hashlib.sha256()
    h.update(prev_hash.encode("utf-8"))
    h.update(json.dumps(payload, sort_keys=True).encode("utf-8"))
    return h.hexdigest()


def _last_hash() -> str:
    if not AUDIT_PATH.exists():
        return "0" * 64
    last = "0" * 64
    with AUDIT_PATH.open() as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                last = json.loads(line)["entry_hash"]
            except Exception:  # noqa: BLE001
                continue
    return last


def append(entry: dict[str, Any]) -> dict[str, Any]:
    """Append a routing audit entry with SHA-256 chain. Returns the entry with hash."""
    AUDIT_PATH.parent.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    payload = {
        "ts": ts,
        "kind": entry.get("kind", "ROUTE"),
        "operator": entry.get("operator", "demo-operator"),
        "scenario_id": entry.get("scenario_id"),
        "step": entry.get("step"),
        "node_id": entry.get("node_id"),
        "model": entry.get("model"),
        "sensitivity": entry.get("sensitivity"),
        "rationale": entry.get("rationale", ""),
        "egress_kb": entry.get("egress_kb", 0),
        "latency_s": entry.get("latency_s", 0.0),
        "live_endpoint": entry.get("live_endpoint"),
    }
    prev = _last_hash()
    payload["prev_hash"] = prev
    payload["entry_hash"] = _hash(prev, payload)
    with AUDIT_PATH.open("a") as f:
        f.write(json.dumps(payload) + "\n")
    return payload


def tail(n: int = 12) -> list[dict]:
    """Return last n audit entries."""
    if not AUDIT_PATH.exists():
        return []
    lines = AUDIT_PATH.read_text().splitlines()
    out = []
    for line in lines[-n:]:
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except Exception:  # noqa: BLE001
            continue
    return out


def verify_chain() -> tuple[bool, int, str]:
    """Walk the chain end-to-end. Returns (ok, entries_checked, error_or_ok_message)."""
    if not AUDIT_PATH.exists():
        return True, 0, "No audit log yet."
    prev = "0" * 64
    n = 0
    with AUDIT_PATH.open() as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            entry = json.loads(line)
            n += 1
            saved_prev = entry.get("prev_hash")
            saved_hash = entry.get("entry_hash")
            if saved_prev != prev:
                return False, n, f"Chain break at entry {n}: prev_hash mismatch."
            payload = {k: v for k, v in entry.items() if k != "entry_hash"}
            recomputed = _hash(prev, payload)
            if recomputed != saved_hash:
                return False, n, f"Chain break at entry {n}: hash mismatch."
            prev = saved_hash
    return True, n, f"Chain verified end-to-end ({n} entries)."
