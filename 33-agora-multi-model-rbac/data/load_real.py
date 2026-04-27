"""Real-data ingestion stub for AGORA.

To plug in real data:
  - personas.json comes from a Keycloak realm export. Map each user object's
    `attributes` (max_class, unit_scope, audit_groups) and `realmRoles` /
    `clientRoles` per app into the persona JSON tree shape produced by
    data/generate.py. Required fields per persona:
      - id, name, rank, billet, clearance, duty_org
      - roles[<app>]: {role: str, perms: list[str]}
      - abac: {max_class: str, unit_scope: list[str], audit_groups: list[str]}

  - corpus.jsonl is the union of help-content from the four target apps.
    Suggested sources:
      - LMS (MarineNet)            → official MarineNet KB export (HTML → text)
      - CMS                         → CCLEPP / TECOM portal page exports
      - BBB (Big Blue Button)       → BBB admin doc set + USMC integration FAQ
      - Keycloak                    → Keycloak admin guide + USMC realm runbook
    Each doc must carry: doc_id, app, title, body, min_role, classification
    (UNCLASS|CUI|FOUO), scope (ALL|UNIT|BATTALION|VENDOR), tags[].

  - embeddings.npy is rebuilt by re-running data/generate.py with real corpus
    in place (it'll re-call shared.kamiwaza_client.embed()).

Then point the app at the new data via env: REAL_DATA_DIR=/path/to/exports
"""
import os
from pathlib import Path


def load_real():
    path = os.getenv("REAL_DATA_DIR")
    if not path:
        raise NotImplementedError(
            "REAL_DATA_DIR not set. See docstring for required schema."
        )
    p = Path(path)
    if not (p / "personas.json").exists() or not (p / "corpus.jsonl").exists():
        raise FileNotFoundError(
            f"Expected personas.json and corpus.jsonl in {p}. See docstring."
        )
    return {
        "personas": (p / "personas.json").read_text(),
        "corpus": (p / "corpus.jsonl").read_text(),
    }
