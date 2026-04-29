"""Real-data ingestion stub for CHAIN-OF-COMMAND.

The synthetic ORBAT graph in `data/generate.py` is a stand-in for three real
data sources you would plug together on an accredited platform:

  1. **DEERS / MOL personnel + ORBAT roster**
     - Source of truth for personnel ↔ unit MEMBER_OF edges.
     - Required fields per Marine: EDIPI, name, rank, MOS, current UIC.
     - The UIC tree (UIC → parent UIC) becomes the organic MEMBER_OF chain
       (fire-team → squad → platoon → company → battalion → regiment → div).
     - Exporter: `mol_export.py` — typically a nightly dump from MOL or
       GCSS-MC/JCOMS.

  2. **GCSS-MC unit table — task-org overlay**
     - Provides the dynamic edges: OPCON_TO, TACON_TO, ATTACHED_TO,
       DETACHED_TO. Each row is keyed on UIC + effective window + order
       reference (FRAGO / OPORD).
     - Required fields: UIC, command_relationship, supported_org,
       effective_start, effective_end, order_ref.

  3. **Keycloak realm export — clearance + caveats + nationality**
     - Keycloak realm-export JSON, filtered to attribute claims:
       `clearance` (UNCLASS|CUI|SECRET|TS), `nationality` (ISO-3),
       `caveats_held` (NOFORN|FVEY|NATO|REL_TO_X).
     - Bound to the EDIPI by the OIDC `sub` claim.

  4. **(Optional) DoD PKI cert chain**
     - The CAC certificate's subject DN gives the EDIPI; the issuer chain
       proves the realm. We treat realm-of-issue as a coarse nationality
       confirmation when DEERS is silent (allied PKI subjects present
       differently).

Then point the app at the real data via env:
    REAL_ORBAT_DIR=/path/to/orbat-export
    REAL_KEYCLOAK_EXPORT=/path/to/realm-export.json
    REAL_GCSS_TASK_ORG=/path/to/gcss-mc-task-org.csv

The shape produced should match `data/orbat.json`, `data/personnel.json`,
and `data/documents.json` so `src/engine.py` runs without modification.
"""
from __future__ import annotations

import os
from pathlib import Path


def load_real():
    orbat_dir = os.getenv("REAL_ORBAT_DIR")
    kc_export = os.getenv("REAL_KEYCLOAK_EXPORT")
    gcss = os.getenv("REAL_GCSS_TASK_ORG")
    if not (orbat_dir and kc_export and gcss):
        raise NotImplementedError(
            "Required env vars not set: REAL_ORBAT_DIR, REAL_KEYCLOAK_EXPORT, "
            "REAL_GCSS_TASK_ORG. See module docstring for the source-of-truth "
            "list and required field shapes."
        )
    p_orbat = Path(orbat_dir)
    if not p_orbat.exists():
        raise FileNotFoundError(f"REAL_ORBAT_DIR not found: {p_orbat}")
    return {
        "orbat_dir": str(p_orbat),
        "keycloak_export": kc_export,
        "gcss_task_org": gcss,
        "next_steps": [
            "Parse the MOL/DEERS dump → personnel.json (one row per Marine).",
            "Walk the UIC parent chain to emit MEMBER_OF edges into orbat.json.",
            "Overlay GCSS-MC task-org rows as OPCON/TACON/ATTACHED/DETACHED edges.",
            "Project Keycloak realm attributes into HAS_CLEARANCE pseudo-edges.",
            "Re-run `python data/generate.py --skip-briefs` to regenerate "
            "documents/relationship-types from the synthetic seed (or replace "
            "documents.json from the originator's records system).",
        ],
    }
