"""Real-data ingestion stub for FED-RAG (per-silo loaders).

The whole point of FED-RAG is that there is no single ingestion path — each
silo has its own data owner, classification, and accreditation boundary. This
module documents how each silo would plug in real records and where the
per-silo Kamiwaza Inference Mesh node would be reached.

For each silo, set the corresponding env var to point load_real_<silo>() at
real data. The function signatures match data/generate.py so src/federation.py
needs no edit.

==============================================================================
Silo A — MCLB Albany / GCSS-MC depot inventory
==============================================================================
  Authority:        DLA Manual 4140.27 (distribution + custody of materiel)
  Classification:   CUI // Distribution D
  Source endpoint:  https://gcss-mc.usmc.mil (NIPR; ELA-only access)
  Real fields:      NSN, on_hand, due_in, unit_price, lead_time_days,
                    location, last_issued
  Env var:          REAL_ALBANY_PATH (jsonl), KAMIWAZA_SILO_ALBANY_URL
  Kamiwaza node:    https://kamiwaza-albany.usmc.mil/api/v1 (Inference Mesh)

==============================================================================
Silo B — Camp Pendleton / 31st MEU LCE Technical Manual library
==============================================================================
  Authority:        DoDM 5200.01 Vol 2 (data spillage prevention)
  Classification:   CUI // FOUO
  Source endpoint:  TM PCN repository on Pendleton MIMMS server
  Real fields:      tm_number, tm_title, section, estimated_minutes, mos, tools
  Env var:          REAL_PENDLETON_PATH (jsonl), KAMIWAZA_SILO_PENDLETON_URL
  Kamiwaza node:    https://kamiwaza-pendleton.usmc.mil/api/v1

==============================================================================
Silo C — DLA Troop Support Philadelphia / Class VIII medical
==============================================================================
  Authority:        DLA Manual 4140.27 + 21 CFR (FDA traceability)
  Classification:   CUI // Distribution C
  Source endpoint:  EMALL / DMLSS Class VIII catalog (DLA Philly)
  Real fields:      NSN, on_hand, unit_cost, lot, expiry, depot, vendor,
                    storage, shelf_life
  Env var:          REAL_PHILLY_PATH (jsonl), KAMIWAZA_SILO_PHILLY_URL
  Kamiwaza node:    https://kamiwaza-philly.dla.mil/api/v1

After populating each path, re-run:
  python data/generate.py --embed --briefs-only
to rebuild per-silo embeddings and the cached federated briefs.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

APP_ROOT = Path(__file__).resolve().parent.parent
SILO_DIR = APP_ROOT / "silos"


def _load_jsonl(path: str) -> list[dict]:
    rows: list[dict] = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rows.append(json.loads(line))
    return rows


def _emit(silo_id: str, rows: list[dict]) -> Path:
    out_dir = SILO_DIR / silo_id
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / "corpus.jsonl"
    with out.open("w") as f:
        for r in rows:
            r.setdefault("silo", silo_id)
            f.write(json.dumps(r) + "\n")
    return out


def load_real_albany() -> list[dict]:
    path = os.getenv("REAL_ALBANY_PATH")
    if not path:
        raise NotImplementedError(
            "REAL_ALBANY_PATH not set. Provide a jsonl with chunks shaped like "
            "data/generate.py emits for the Albany silo."
        )
    rows = _load_jsonl(path)
    _emit("albany", rows)
    return rows


def load_real_pendleton() -> list[dict]:
    path = os.getenv("REAL_PENDLETON_PATH")
    if not path:
        raise NotImplementedError(
            "REAL_PENDLETON_PATH not set. Provide a jsonl with chunks shaped like "
            "data/generate.py emits for the Pendleton silo."
        )
    rows = _load_jsonl(path)
    _emit("pendleton", rows)
    return rows


def load_real_philly() -> list[dict]:
    path = os.getenv("REAL_PHILLY_PATH")
    if not path:
        raise NotImplementedError(
            "REAL_PHILLY_PATH not set. Provide a jsonl with chunks shaped like "
            "data/generate.py emits for the Philly silo."
        )
    rows = _load_jsonl(path)
    _emit("philly", rows)
    return rows


def load_real_all() -> dict[str, list[dict]]:
    return {
        "albany": load_real_albany(),
        "pendleton": load_real_pendleton(),
        "philly": load_real_philly(),
    }


if __name__ == "__main__":
    out = load_real_all()
    for k, v in out.items():
        print(f"{k}: {len(v)} chunks ingested")
