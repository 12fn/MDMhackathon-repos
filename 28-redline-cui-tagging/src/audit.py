"""SHA-256 hash-chained audit log for REDLINE marking decisions.

Every entry includes:
  - prev_hash: SHA-256 of the previous entry (genesis = 64 zeros)
  - timestamp_utc: ISO-8601 UTC
  - body fields (event, analyst_id, doc_id, paragraph_index, decision)
  - entry_hash: SHA-256 of the json-serialized body (sorted keys)

Tamper-evident: any modification to a prior entry breaks the chain because
every following entry_hash depends on prev_hash.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

GENESIS = "0" * 64


def sha256_text(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


class AuditChain:
    """File-backed append-only hash-chained log."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def last_hash(self) -> str:
        if not self.path.exists():
            return GENESIS
        last = GENESIS
        with self.path.open() as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    last = json.loads(line).get("entry_hash", last)
                except json.JSONDecodeError:
                    continue
        return last

    def append(self, body: dict[str, Any]) -> dict[str, Any]:
        """Compute and append a chained entry. Returns the full entry."""
        entry = {k: v for k, v in body.items() if k != "entry_hash"}
        entry["prev_hash"] = self.last_hash()
        entry["timestamp_utc"] = datetime.now(timezone.utc).isoformat()
        entry["entry_hash"] = sha256_text(
            json.dumps(entry, sort_keys=True, default=str)
        )
        with self.path.open("a") as f:
            f.write(json.dumps(entry, default=str) + "\n")
        return entry

    def read(self, limit: int | None = 25) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        out: list[dict[str, Any]] = []
        with self.path.open() as f:
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

    def verify(self) -> dict[str, Any]:
        """Re-compute every entry_hash and confirm the chain is intact."""
        if not self.path.exists():
            return {"ok": True, "entries": 0, "broken_at": None}
        prev = GENESIS
        entries: list[dict[str, Any]] = []
        with self.path.open() as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entries.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
        for i, e in enumerate(entries):
            stored = e.get("entry_hash")
            body = {k: v for k, v in e.items() if k != "entry_hash"}
            recomputed = sha256_text(json.dumps(body, sort_keys=True, default=str))
            if e.get("prev_hash") != prev:
                return {"ok": False, "entries": len(entries),
                        "broken_at": i, "reason": "prev_hash mismatch"}
            if recomputed != stored:
                return {"ok": False, "entries": len(entries),
                        "broken_at": i, "reason": "entry_hash mismatch"}
            prev = stored
        return {"ok": True, "entries": len(entries), "broken_at": None,
                "tip_hash": prev}
