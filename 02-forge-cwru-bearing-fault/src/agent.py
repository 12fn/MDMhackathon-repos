# FORGE — predictive bearing failure
# Part of the MDM 2026 Hackathon Templates (https://github.com/12fn/MDMhackathon-repos)
# MIT licensed. Built on GAI (Government Acquisitions, Inc.) + Kamiwaza (https://www.kamiwaza.ai/).
"""Multimodal LLM agent: spectrogram + classifier + maintenance log + parts tool → JSON brief."""
from __future__ import annotations

import base64
import json
import sys
from io import BytesIO
from pathlib import Path
from typing import Any

# Allow running both as `from src.agent import ...` and as `python src/agent.py`
ROOT = Path(__file__).resolve().parent.parent
SHARED = ROOT.parent.parent / "shared"
if str(SHARED.parent) not in sys.path:
    sys.path.insert(0, str(SHARED.parent))

from shared.kamiwaza_client import chat_json, get_client, PRIMARY_MODEL  # noqa: E402

DATA = ROOT / "data"
CACHE_FILE = DATA / "cached_briefs.json"


def load_cached_brief(vehicle_id: str) -> dict | None:
    """Return precomputed agent result for a vehicle if cached_briefs.json exists.

    The Streamlit demo prefers cached output so the multimodal LLM call (which can
    take 10-40s and occasionally times out, killing the Streamlit websocket) never
    blocks the UI mid-recording.
    """
    if not CACHE_FILE.exists():
        return None
    try:
        cache = json.loads(CACHE_FILE.read_text())
    except Exception:
        return None
    entry = cache.get(vehicle_id)
    if not entry:
        return None
    return entry.get("agent_result")


def _load_inventory() -> dict:
    return json.loads((DATA / "parts_inventory.json").read_text())


def lookup_part_availability(nsn: str) -> dict:
    """Synthetic depot inventory tool. Returns stock at MCLB Albany + alt depots."""
    inv = _load_inventory()
    if nsn not in inv:
        return {"nsn": nsn, "found": False, "message": f"NSN {nsn} not in supply catalog."}
    rec = inv[nsn]
    qty_albany = rec["qty_albany"]
    in_stock = qty_albany > 0
    return {
        "nsn": nsn,
        "found": True,
        "name": rec["name"],
        "in_stock_at_mclb_albany": in_stock,
        "qty_albany": qty_albany,
        "alt_depots": {
            "MCLB_Barstow": rec["qty_barstow"],
            "Blount_Island_Command": rec["qty_blount_island"],
        },
        "lead_time_days_if_short": rec["lead_time_days_if_short"],
        "unit_cost_usd": rec["unit_cost_usd"],
    }


SYSTEM_PROMPT = """You are FORGE, a USMC Marine Corps Logistics Command (MARCORLOGCOM) \
predictive-maintenance analyst. You work in CDAO at MCLB Albany.

Your job: given a wheel-bearing vibration analysis package for a single ground vehicle, \
write a commander's recommendation that an E-5 maintenance chief can act on within 60 seconds.

You will be shown:
- A spectrogram image of the drive-end accelerometer trace.
- The classifier's predicted fault class + confidence + per-class probabilities.
- An estimated Remaining Useful Life (RUL) in operating hours.
- A 6-month maintenance work-order log for this vehicle.
- A part-availability lookup result from MCLB Albany supply.

Decision tree:
- If classifier says HEALTHY with high confidence and RUL > 800 hr -> recommendation = "safe_to_operate".
- If a fault is detected and RUL < 250 hr OR confidence > 0.80 with severity > 0.6 -> "induct_now".
- Else if part is in stock and trend is worsening across the maintenance log -> "induct_now".
- Else -> "monitor_closely".

Respond ONLY as a JSON object with keys:
  recommendation: one of ["induct_now","monitor_closely","monitor_routine","safe_to_operate"]
  urgency: one of ["red","amber","yellow","green"]
  rationale_bullets: list of 2-4 strings; cite specific evidence (BPFO/BPFI/BSF, work-order dates, RUL).
  commander_brief: 3 sentences. Plain English. Action-oriented. Reference NSN if inducting.
  parts_action: short string about supply (e.g., "NSN ... in stock, 14 ea at MCLB Albany; pull immediately.")
  predicted_failure_mode: string describing the failure (e.g., "Outer-race spall progressing to hub seizure within ~30 days of operation").
"""


def _spectrogram_data_url(png_bytes: bytes) -> str:
    b64 = base64.b64encode(png_bytes).decode("ascii")
    return f"data:image/png;base64,{b64}"


def commander_recommendation(
    *,
    spectrogram_png: bytes,
    classifier_result: dict,
    rul_result: dict,
    vehicle: dict,
    maintenance_log: list[dict],
    use_hero_model: bool = False,
    timeout_s: float = 12.0,
    prefer_cache: bool = True,
) -> dict:
    """Run the multimodal LLM with tool-calling for parts lookup.

    Demo-safe behavior:
      - If `prefer_cache` and `data/cached_briefs.json` has an entry for this
        vehicle, return it instantly. The hero LLM call is too slow / flaky for
        a live Playwright recording.
      - Otherwise call the LLM with a hard `timeout_s` watchdog (default 12s)
        and fall back to a deterministic rule-based brief on any failure.
    """
    parts = lookup_part_availability(vehicle["nsn"])

    if prefer_cache:
        cached = load_cached_brief(vehicle["vehicle_id"])
        if cached is not None:
            # Refresh tool-call log to show "live" parts lookup in the UI
            cached = dict(cached)
            cached["_tool_call_log"] = [
                {"tool": "lookup_part_availability", "args": {"nsn": vehicle["nsn"]}, "result": parts}
            ]
            cached.setdefault("_model", "Kamiwaza mini (cached)")
            cached["_source"] = "cache"
            return cached

    payload = {
        "vehicle": {
            "id": vehicle["vehicle_id"],
            "type": vehicle["type"],
            "unit": vehicle["unit"],
            "hub": vehicle["hub_position"],
            "operating_hours": vehicle["operating_hours"],
            "since_last_overhaul_hr": vehicle["since_last_overhaul_hr"],
            "nsn": vehicle["nsn"],
        },
        "classifier": classifier_result,
        "rul": rul_result,
        "maintenance_log": maintenance_log,
        "parts_lookup_result": parts,
    }

    user_text = (
        "Analyze this wheel-bearing vibration package and write the commander's "
        "recommendation as JSON per the schema in the system prompt.\n\n"
        f"DATA:\n{json.dumps(payload, indent=2)}"
    )

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {
            "role": "user",
            "content": [
                {"type": "text", "text": user_text},
                {
                    "type": "image_url",
                    "image_url": {"url": _spectrogram_data_url(spectrogram_png), "detail": "low"},
                },
            ],
        },
    ]

    model = "gpt-5.4" if use_hero_model else None
    try:
        # Hard timeout watchdog: a hung LLM call would otherwise block the Streamlit
        # event loop long enough that Playwright thinks the app died.
        from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutTimeout
        with ThreadPoolExecutor(max_workers=1) as ex:
            fut = ex.submit(
                chat_json,
                messages,
                schema_hint="recommendation,urgency,rationale_bullets,commander_brief,parts_action,predicted_failure_mode",
                model=model,
            )
            result = fut.result(timeout=timeout_s)
    except Exception as e:
        # Final safety net so the demo never crashes
        result = {
            "recommendation": rul_result.get("recommendation", "monitor_closely"),
            "urgency": "amber",
            "rationale_bullets": [
                f"LLM call failed ({type(e).__name__}); using fallback rule-based brief.",
                f"Classifier: {classifier_result.get('class')} @ {classifier_result.get('confidence', 0):.0%}",
                f"RUL estimate: {rul_result.get('rul_hours')} operating hours",
            ],
            "commander_brief": (
                f"{vehicle['vehicle_id']} shows {classifier_result.get('class').replace('_',' ')} "
                f"signature at {classifier_result.get('confidence', 0):.0%} confidence with ~{rul_result.get('rul_hours')} operating hours of remaining life. "
                f"Recommend {rul_result.get('recommendation','monitor').replace('_',' ')}. Replacement NSN {vehicle['nsn']} is "
                f"{'in stock' if parts.get('in_stock_at_mclb_albany') else 'short'} at MCLB Albany."
            ),
            "parts_action": (
                f"NSN {vehicle['nsn']} — {parts.get('qty_albany', 0)} ea at MCLB Albany, "
                f"{parts.get('alt_depots', {}).get('MCLB_Barstow', 0)} ea at Barstow."
            ),
            "predicted_failure_mode": f"Probable {classifier_result.get('class','?').replace('_',' ')} progression",
        }

    result["_tool_call_log"] = [
        {"tool": "lookup_part_availability", "args": {"nsn": vehicle["nsn"]}, "result": parts}
    ]
    # User-visible label only — actual API model id stays as `model` / PRIMARY_MODEL
    # above. Kamiwaza maps the OpenAI-compatible id to whatever's deployed on-prem.
    result["_model"] = "Kamiwaza hero" if model else "Kamiwaza mini"
    return result
