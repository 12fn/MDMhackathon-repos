"""Daily ASIB composer for OMNI-INTEL -- hero LLM call wrapped in watchdog.

Cache-first: if a precomputed brief exists for the active scenario, return it.
Live regeneration uses a 35s timeout and falls back to a deterministic
baseline so the demo never sits frozen on a spinner.
"""
from __future__ import annotations

import json
import sys
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutTimeout
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CACHE_PATH = ROOT / "data" / "cached_briefs.json"

sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[2]))


def _cached() -> dict:
    if CACHE_PATH.exists():
        try:
            return json.loads(CACHE_PATH.read_text())
        except Exception:
            return {}
    return {}


def get_cached(scenario_label: str) -> str | None:
    return _cached().get(scenario_label)


SYSTEM = """You are a USMC LOGCOM CDAO all-source intelligence analyst.
Doctrine: BLUF first, EEFI awareness, IPOE-grounded, CCIR-driven recommendations.
Cite INTs by name (GEOINT, IMINT, SIGINT, MASINT, OSINT, HUMINT). Voice: terse,
declarative, US military, ZULU times. Use OPLAN-style headers. Round numbers.
Hedge only when evidence is weak. NEVER fabricate -- only cite the data given.
"""

SKELETON = """# DAILY ALL-SOURCE INTELLIGENCE BRIEF -- OMNI-INTEL
**DTG:** {date_z}  **CLASS:** UNCLASSIFIED//FOUO (DEMO)
**ORIGIN:** USMC LOGCOM CDAO / OMNI-INTEL  **SCENARIO:** {scenario}

## 1. BLUF
## 2. OBSERVED ACTIVITY BY SOURCE-TYPE
## 3. FUSED-SOURCE HIGHLIGHTS
## 4. NAMED THREATS
## 5. COLLECTION RECOMMENDATIONS (CCIR-aligned)
## 6. CONFIDENCE STATEMENT
## 7. CCDR DISTRIBUTION

CCDR distribution line: USMC LOGCOM CDAO // INDOPACOM J2 // MARFORPAC G-2 // 1st MEF G-2.
"""


def baseline_brief(scenario: str, fusion_summary: dict) -> str:
    """Deterministic fallback. Used on timeout / LLM failure."""
    today = datetime.now(timezone.utc).strftime("%d%H%MZ %b %Y").upper()
    by_int = fusion_summary.get("by_int", {})
    n_clusters = fusion_summary.get("n_clusters", 0)
    top = fusion_summary.get("top", [])
    top_lines = "\n".join(
        f"- **{c['cluster_id']}** ({c['classification']}, conf {c['confidence']:.2f}): "
        f"{c['n_sources']} sources concur near {c['centroid']}."
        for c in top[:5]
    ) or "- (none)"
    int_lines = "\n".join(f"- {k}: {v} observations" for k, v in by_int.items()) or "- (no data)"
    return f"""# DAILY ALL-SOURCE INTELLIGENCE BRIEF -- OMNI-INTEL
**DTG:** {today}  **CLASS:** UNCLASSIFIED//FOUO (DEMO)
**ORIGIN:** USMC LOGCOM CDAO / OMNI-INTEL  **SCENARIO:** {scenario}

## 1. BLUF
{n_clusters} cross-source fusion clusters detected in the 24h window across
7 INT streams. Highest-confidence event corroborated by {fusion_summary.get('best_n_ints', 0)}
distinct INT disciplines. Recommend Stand-In-Force ISR re-task.

## 2. OBSERVED ACTIVITY BY SOURCE-TYPE
{int_lines}

## 3. FUSED-SOURCE HIGHLIGHTS
{top_lines}

## 4. NAMED THREATS
- Suspected covert vessel signatures in Sulu / Sibutu corridors.
- Suspected covert UAS LRC operating from coastal platforms.

## 5. COLLECTION RECOMMENDATIONS (CCIR-aligned)
- Re-task MQ-9A onto highest-score cluster centroid for IR confirmation.
- Cue P-8A MAD/EO at AIS-gap fusion coordinates next dark-cycle pass.
- Request HUMINT confirmation through NCIS WestPac liaison.
- Direct Stand-In-Force squad to investigate beach-recon RF/IR coordinates within 6h.

## 6. CONFIDENCE STATEMENT
HIGH on event detection -- multi-INT corroboration reduces single-source error.
MED on attribution -- fused events benefit from HUMINT linguistic confirmation.

## 7. CCDR DISTRIBUTION
USMC LOGCOM CDAO // INDOPACOM J2 // MARFORPAC G-2 // 1st MEF G-2
"""


def _live_brief(scenario: str, fusion_summary: dict) -> str:
    from shared.kamiwaza_client import chat  # type: ignore
    today = datetime.now(timezone.utc).strftime("%d%H%MZ %b %Y").upper()
    user = SKELETON.format(date_z=today, scenario=scenario) + "\n\nDATA:\n" + json.dumps(
        fusion_summary, indent=2)
    msgs = [{"role": "system", "content": SYSTEM},
            {"role": "user", "content": user}]
    # Try several call shapes -- newer reasoning models reject max_tokens /
    # temperature; older chat models require them.
    for kwargs in (
        {"model": "gpt-5.4", "temperature": 0.3},
        {"model": "gpt-5.4-mini"},
        {"model": "gpt-4o-mini", "temperature": 0.3, "max_tokens": 1800},
    ):
        try:
            return chat(msgs, **kwargs).strip()
        except Exception:
            continue
    raise RuntimeError("All hero-model attempts failed.")


def compose_brief(scenario: str, fusion_summary: dict, *, timeout_s: int = 35) -> str:
    """Hero call with watchdog. Cache-first; live with 35s wall-clock fallback."""
    cached = get_cached(scenario)
    if cached:
        return cached
    with ThreadPoolExecutor(max_workers=1) as ex:
        try:
            return ex.submit(_live_brief, scenario, fusion_summary).result(timeout=timeout_s)
        except FutTimeout:
            return baseline_brief(scenario, fusion_summary)
        except Exception:
            return baseline_brief(scenario, fusion_summary)
