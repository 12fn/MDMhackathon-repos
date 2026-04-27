# CORSAIR — pirate-attack KDE forecast + maritime intel summary
# Part of the MDM 2026 Hackathon Templates (https://github.com/12fn/MDMhackathon-repos)
# MIT licensed. Built on GAI (Government Acquisitions, Inc.) + Kamiwaza (https://www.kamiwaza.ai/).
"""CORSAIR LLM agent — drafts a SIPR-style Maritime Intel Summary (MIS) and a
structured indicator board JSON. Uses the shared kamiwaza_client (multi-provider
auto-detect: Kamiwaza on-prem, OpenAI, OpenRouter, Anthropic, or any
OpenAI-compatible endpoint)."""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

# allow `from shared.kamiwaza_client import chat` even when run from this app dir
ROOT = Path(__file__).resolve().parent.parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from shared.kamiwaza_client import chat, chat_json  # noqa: E402


SYSTEM_MIS = """You are a USMC LOGCOM Maritime Intelligence Officer producing a
classified-format SIPR Maritime Intel Summary (MIS) for an MEU/MSC routing
decision. You write tight, declarative tradecraft prose with operator-actionable
specificity. NEVER hallucinate placenames or actor names that are not in the
input data. Use only the basin name, hotspot coords, and incident excerpts that
were provided. Output sections must be exactly:

(U) BLUF
(U) Threat Picture
(U) Assessed Threat Actor
(U) Modus Operandi Pattern Shifts
(U) Recommended Route Deviations
(U) Confidence

Each section is one short paragraph. Lead with the BLUF in 2 sentences max.
End with explicit confidence (LOW/MED/HIGH) with one-line justification.
Mark every paragraph with the leading (U) marking. No markdown bullets.
"""


def build_mis_prompt(basin: str, asof: str, hotspots: list[dict],
                     trend: dict, recent_incidents: list[dict],
                     expected_30d: float) -> list[dict]:
    hs_lines = "\n".join(
        f"- Hotspot {i+1}: {h['lat']:.2f}N/{h['lon']:.2f}E  (relative-risk {h['risk']:.2f}, "
        f"expected ~{h['expected']:.2f} attacks/30d)"
        for i, h in enumerate(hotspots)
    )
    inc_lines = "\n".join(
        f"- {r['datetime'][:10]}  {r['vessel_type']:<18}  {r['attack_type']:<14}  "
        f"basin={r['basin']}\n    {r['narrative']}"
        for r in recent_incidents
    )
    trend_line = (
        f"Recent 5y attacks: {trend['n_recent_5y']} vs prior 5y: {trend['n_prior_5y']}  "
        f"({trend['delta_pct']:+.1f}%). "
        f"Dominant MOA recent={trend['moa_recent']}, prior={trend['moa_prior']}, "
        f"shift={'YES' if trend['shift'] else 'no'}."
    )
    user = f"""Generate a Maritime Intel Summary (MIS) for the next 30 days.

THEATER OF FOCUS: {basin}
AS-OF: {asof}
FORECAST: ~{expected_30d:.1f} attacks expected in next 30 days within basin.

TOP-5 RISK HOTSPOTS (KDE forecast on synthetic ASAM-style data):
{hs_lines}

TREND DELTA:
{trend_line}

RECENT INCIDENT EXCERPTS (up to 6 narratives that informed the model):
{inc_lines}

Write the MIS now. Reference at least two hotspot coordinates, the trend delta,
and at least one specific incident detail in the narrative. Keep total length
under ~280 words.
"""
    return [
        {"role": "system", "content": SYSTEM_MIS},
        {"role": "user", "content": user},
    ]


def generate_mis(basin: str, asof: str, hotspots: list[dict], trend: dict,
                  recent_incidents: list[dict], expected_30d: float,
                  *, model: str | None = None) -> str:
    msgs = build_mis_prompt(basin, asof, hotspots, trend, recent_incidents, expected_30d)
    # Hero call — caller may pass the Kamiwaza-deployed hero model once for the marquee narrative.
    return chat(msgs, model=model, temperature=0.4, max_tokens=600)


SYSTEM_INDICATOR = """You are CORSAIR's structured-output engine. Given the
forecast inputs, produce a STRICT JSON indicator board for an MEU operations
center. Do not editorialize. Use only the inputs provided. Return valid JSON
matching the schema in the user message — no markdown, no commentary."""


def build_indicator_prompt(basin: str, hotspots: list[dict], trend: dict,
                            expected_30d: float, recent_incidents: list[dict]) -> list[dict]:
    user = f"""Inputs:
basin: {basin}
expected_attacks_30d: {expected_30d:.2f}
trend: {trend}
hotspots: {hotspots}
sample_incidents: {[{
    'date': r['datetime'][:10],
    'vessel': r['vessel_type'],
    'type': r['attack_type'],
    'lat': r['lat'], 'lon': r['lon'],
} for r in recent_incidents[:6]]}

Schema (JSON):
{{
  "basin": str,
  "threat_level": one of ["LOW","GUARDED","ELEVATED","HIGH","SEVERE"],
  "expected_attacks_30d": number,
  "delta_pct_vs_prior_5y": number,
  "top_hotspots": [{{
      "rank": int, "lat": number, "lon": number, "risk": number,
      "label": str   // short label like 'Bab-el-Mandeb approaches' if obvious from coords, else 'Sector A/B/C'
  }}, ... up to 5],
  "moa_pattern_shift": str,
  "recommended_route_deviations": [str, str, str],
  "indicators_to_watch": [str, str, str]
}}
Return only the JSON object."""
    return [
        {"role": "system", "content": SYSTEM_INDICATOR},
        {"role": "user", "content": user},
    ]


def generate_indicator_board(basin: str, hotspots: list[dict], trend: dict,
                              expected_30d: float, recent_incidents: list[dict]) -> dict[str, Any]:
    msgs = build_indicator_prompt(basin, hotspots, trend, expected_30d, recent_incidents)
    return chat_json(
        msgs,
        schema_hint="basin, threat_level, expected_attacks_30d, delta_pct_vs_prior_5y, "
                    "top_hotspots[5], moa_pattern_shift, recommended_route_deviations[3], "
                    "indicators_to_watch[3]",
        temperature=0.2,
        max_tokens=700,
    )
