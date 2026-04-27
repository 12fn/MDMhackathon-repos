"""Real-data ingestion stub for CHORUS.

CHORUS ships with synthetic personas (see data/generate.py). The real-data
swap is **not** a single CSV — it's a directory of curated audience-persona
markdown cards plus a YAML registry of training scenarios.

To plug in real data, implement load_real() to read from REAL_DATA_PATH and
emit the same shape as data/generate.py produces:

  personas.json — list[dict] with keys:
    persona_id (str), tier (str), label (str), demographics (str),
    values (list[str]), concerns (list[str]), trust_baseline (int -10..+10),
    lens (str), trigger_phrases_negative (list[str]),
    trigger_phrases_positive (list[str])

  scenarios.json — list[dict] with keys:
    scenario_id (str), title (str), theater (str), classification_band (str),
    mission_context (str), trainee_objective (str), constraints (list[str])

Then point src/app.py at it via env: REAL_DATA_PATH=/path/to/persona-library/

Recommended real-source plug-ins (none of which are shipped here):
  - DoD Office of People Analytics (OPA) audience segmentation studies
  - DEFENSE.GOV PA reading-list stylometric profiles
  - State Dept R/PPR audience-research microdata (declassified portions)
  - Open-source persona libraries from RAND IO research
  - Park et al. 2024 "Generative Agent Simulations of 1,000 People"
    (arXiv:2403.20252) — the canonical methodology reference
"""
from __future__ import annotations

import json
import os
from pathlib import Path


def load_real() -> tuple[list[dict], list[dict]]:
    """Return (personas, scenarios) read from REAL_DATA_PATH.

    Expected layout under REAL_DATA_PATH:
        personas/                 # one .md or .json per persona
        scenarios/                # one .md or .json per scenario

    Implementations should validate against the schemas in this docstring.
    """
    path_str = os.getenv("REAL_DATA_PATH")
    if not path_str:
        raise NotImplementedError(
            "REAL_DATA_PATH not set. See module docstring for expected layout. "
            "For demo, use the synthetic generator at data/generate.py."
        )
    base = Path(path_str)
    personas_dir = base / "personas"
    scenarios_dir = base / "scenarios"
    if not personas_dir.exists() or not scenarios_dir.exists():
        raise NotImplementedError(
            f"Expected {personas_dir} and {scenarios_dir} to exist. "
            "See module docstring for expected layout."
        )
    personas = [json.loads(p.read_text()) for p in sorted(personas_dir.glob("*.json"))]
    scenarios = [json.loads(p.read_text()) for p in sorted(scenarios_dir.glob("*.json"))]
    return personas, scenarios
