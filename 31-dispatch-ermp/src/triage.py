"""DISPATCH — triage + CAD-brief LLM helpers.

Three-stage pipeline:
  1) "playback" of the call transcript (no LLM — display-only on the FE)
  2) chat_json triage card — fast, structured, JSON-mode
  3) chat CAD brief (hero) — long-form dispatcher entry, 15s timeout, fallback

All hero calls are wrapped in concurrent.futures.ThreadPoolExecutor with a
wall-clock timeout so the UI never sits frozen. Cache-first: pre-computed
results live in data/cached_briefs.json.
"""
from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutTimeout
from pathlib import Path
from typing import Any

# Hero model (premium); falls back through PRIMARY_MODEL via shared client.
HERO_MODEL = "gpt-5.4"
TRIAGE_TIMEOUT_S = 15
BRIEF_TIMEOUT_S = 15

DATA = Path(__file__).resolve().parent.parent / "data"


def _full_text(call: dict) -> str:
    return "\n".join(
        f"[{s['speaker']} t+{s['t']:.1f}s] {s['text']}" for s in call["transcript"]
    )


# ---------------------------------------------------------------------------
# Deterministic baselines — used on LLM timeout / failure.
# ---------------------------------------------------------------------------
INCIDENT_KEYWORDS = {
    "fire":          ["fire", "smoke", "flames", "alarm", "burning", "JP-8"],
    "medical":       ["bleeding", "unconscious", "chest pain", "seizure", "not breathing", "injured"],
    "active_threat": ["shooter", "weapon", "armed", "hostile", "threat"],
    "hazmat":        ["fuel", "chemical", "spill", "leak", "vapor"],
    "mvi":           ["wreck", "crash", "accident", "rolled over", "vehicle", "humvee", "tacoma"],
    "mascal":        ["mass casualty", "MASCAL", "multiple casualties", "mortar", "six down"],
    "suspicious_package": ["package", "unattended", "wires sticking out", "IED", "suspicious"],
}


def baseline_triage(call: dict) -> dict:
    text = " ".join(s["text"] for s in call["transcript"]).lower()
    scored = sorted(
        ((sum(text.count(k.lower()) for k in kws), itype)
         for itype, kws in INCIDENT_KEYWORDS.items()),
        reverse=True,
    )
    incident_type = scored[0][1] if scored[0][0] > 0 else "other"

    if "mascal" in text or "mass casualty" in text or "six down" in text:
        severity = "echo"
    elif "fire" in text and ("through the roof" in text or "missing" in text or "trapped" in text):
        severity = "echo"
    elif "wires" in text or "ied" in text:
        severity = "delta"
    elif "injured" in text or "rolled over" in text:
        severity = "delta"
    elif "fire" in text or "smoke" in text:
        severity = "charlie"
    else:
        severity = "bravo"

    UNIT_RECIPES = {
        "fire":               [("engine", 2), ("rescue", 1), ("ambulance", 1), ("police", 1)],
        "medical":            [("ambulance", 1), ("police", 1)],
        "active_threat":      [("police", 3), ("ambulance", 1)],
        "hazmat":             [("hazmat", 1), ("engine", 1), ("ambulance", 1), ("police", 1)],
        "mvi":                [("rescue", 1), ("ambulance", 2), ("police", 1), ("engine", 1)],
        "mascal":             [("ambulance", 2), ("rescue", 1), ("engine", 1), ("police", 2)],
        "suspicious_package": [("police", 3), ("hazmat", 1), ("ambulance", 1)],
        "other":              [("police", 1), ("ambulance", 1)],
    }
    return {
        "call_id": call["id"],
        "incident_type": incident_type,
        "severity": severity,
        "primary_complaint": call.get("incident_summary_seed", ""),
        "address_extracted": call["address"],
        "lat_lon": list(call["lat_lon"]),
        "recommended_units": [
            {"unit_type": ut, "count": c} for ut, c in UNIT_RECIPES[incident_type]
        ],
        "callback_questions": [
            "Confirm patient count and severity.",
            "Confirm any continued threat to first responders.",
            "Confirm best ingress route for responding units.",
        ],
        "confidence": 0.62,
    }


def baseline_cad_brief(call: dict, triage: dict) -> str:
    inc_type = triage["incident_type"].replace("_", " ").upper()
    sev = triage["severity"].upper()
    units = ", ".join(
        f"{u['count']}x {u['unit_type']}" for u in triage["recommended_units"]
    )
    return (
        "INCIDENT SUMMARY:\n"
        f"  {triage['primary_complaint']}\n"
        f"  Type: {inc_type} | Severity: {sev} | Location: {call['address']}\n\n"
        "UNIT ASSIGNMENT RECOMMENDATION:\n"
        f"  Dispatch {units}. Stage uphill / upwind of incident at minimum 50m\n"
        "  stand-off. PMO assumes scene command pending Battalion Chief arrival.\n\n"
        "SCENE SAFETY BRIEF:\n"
        "  - Approach with caution; treat all reports as potentially evolving.\n"
        "  - Confirm utilities (gas / electrical) and fuel sources isolated.\n"
        "  - Establish hot / warm / cold zones per NIMS; account for downwind drift.\n"
        "  - Maintain comms on Channel 4; request mutual aid if scene exceeds initial assignment.\n"
    )


# ---------------------------------------------------------------------------
# Live LLM helpers (with watchdog + deterministic fallback).
# ---------------------------------------------------------------------------
def live_triage(chat_json_fn, call: dict) -> dict:
    transcript_text = _full_text(call)
    payload = (
        f"911 CALL TRANSCRIPT:\n{transcript_text}\n\n"
        f"GROUND TRUTH (CAD ANI/ALI): address={call['address']}, "
        f"lat_lon={call['lat_lon']}, call_id={call['id']}\n\n"
        "Produce JSON: {"
        "\"call_id\":str,"
        "\"incident_type\":\"fire|medical|active_threat|hazmat|mvi|mascal|suspicious_package|other\","
        "\"severity\":\"alpha|bravo|charlie|delta|echo\","
        "\"primary_complaint\":str,"
        "\"address_extracted\":str,"
        "\"lat_lon\":[float,float],"
        "\"recommended_units\":[{\"unit_type\":str,\"count\":int}],"
        "\"callback_questions\":[str],"
        "\"confidence\":float"
        "}. Severity uses APCO MPDS letter scale (echo = highest)."
    )

    def _call() -> dict:
        return chat_json_fn(
            [
                {"role": "system", "content": (
                    "You are an AI triage agent for an installation 9-1-1 dispatch CAD. "
                    "You output strict JSON with the requested fields."
                )},
                {"role": "user", "content": payload},
            ],
            schema_hint="triage card",
            temperature=0.2,
            max_tokens=600,
        )

    with ThreadPoolExecutor(max_workers=1) as ex:
        try:
            return ex.submit(_call).result(timeout=TRIAGE_TIMEOUT_S)
        except (FutTimeout, Exception):
            return baseline_triage(call)


def live_cad_brief(chat_fn, call: dict, triage: dict, *, model: str = HERO_MODEL) -> str:
    transcript_text = _full_text(call)
    payload = (
        f"CALL TRANSCRIPT:\n{transcript_text}\n\n"
        f"TRIAGE CARD:\n{json.dumps(triage, indent=2)}\n\n"
        "Write the CAD entry for the responding crew."
    )

    def _call() -> str:
        return chat_fn(
            [
                {"role": "system", "content": (
                    "You are an experienced 9-1-1 dispatcher writing the CAD entry for the "
                    "responding crew. Three short labeled sections: INCIDENT SUMMARY, "
                    "UNIT ASSIGNMENT RECOMMENDATION, SCENE SAFETY BRIEF. Plain text. "
                    "Terse, professional, action-oriented. No filler."
                )},
                {"role": "user", "content": payload},
            ],
            temperature=0.3,
            max_tokens=500,
            model=model,
        )

    with ThreadPoolExecutor(max_workers=1) as ex:
        try:
            return ex.submit(_call).result(timeout=BRIEF_TIMEOUT_S)
        except (FutTimeout, Exception):
            return baseline_cad_brief(call, triage)


# ---------------------------------------------------------------------------
# Cache loader
# ---------------------------------------------------------------------------
_CACHE: dict[str, Any] | None = None


def cached_brief(call_id: str) -> dict | None:
    global _CACHE
    if _CACHE is None:
        p = DATA / "cached_briefs.json"
        if p.exists():
            _CACHE = json.loads(p.read_text())
        else:
            _CACHE = {}
    return _CACHE.get(call_id)


# ---------------------------------------------------------------------------
# Unit dispatch helpers — geo + selection.
# ---------------------------------------------------------------------------
import math


def haversine_mi(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R_MI = 3958.756
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * R_MI * math.asin(min(1.0, math.sqrt(a)))


# Fuzzy mapping from any LLM-suggested unit string -> our canonical types.
# Order in the value list matters when multiple candidates apply.
_UNIT_TYPE_ALIASES = {
    "engine":     ["engine", "fire_engine", "fire engine", "pumper", "ladder", "truck"],
    "rescue":     ["rescue", "rescue_unit", "rescue squad", "extrication", "tech rescue"],
    "ambulance":  ["ambulance", "ems", "medic", "als", "bls", "transport"],
    "hazmat":     ["hazmat", "haz mat", "decon", "spill", "chemical"],
    "police":     ["police", "police_unit", "mp", "military police", "pmo",
                   "k-9", "k9", "eod", "game warden", "patrol", "security"],
}


def _canonical_unit_type(raw: str) -> str | None:
    if not raw:
        return None
    s = raw.lower().strip()
    # Direct match wins
    if s in _UNIT_TYPE_ALIASES:
        return s
    for canon, aliases in _UNIT_TYPE_ALIASES.items():
        for a in aliases:
            if a in s:
                return canon
    return None


def select_units(units: list[dict], triage: dict) -> list[dict]:
    """Greedy pick: for each recommended (unit_type, count), grab the closest
    available units of that type to the incident lat/lon. Unknown unit types
    get fuzz-mapped to our canonical roster types (ambulance / engine / rescue
    / hazmat / police) so the geospatial pane is always populated."""
    incident_lat, incident_lon = triage["lat_lon"]
    selected: list[dict] = []
    used_ids: set[str] = set()
    for rec in triage.get("recommended_units", []):
        canon = _canonical_unit_type(rec.get("unit_type", ""))
        if canon is None:
            # Default to police for "other" specialty units (EOD, K-9, PMO)
            canon = "police"
        n = int(rec.get("count", 1))
        candidates = [u for u in units
                      if u["type"] == canon and u["id"] not in used_ids]
        candidates.sort(key=lambda u: haversine_mi(
            u["location"][0], u["location"][1], incident_lat, incident_lon))
        for u in candidates[:n]:
            used_ids.add(u["id"])
            d_mi = haversine_mi(u["location"][0], u["location"][1],
                                incident_lat, incident_lon)
            # Rough ETA at 35 mph average installation speed
            eta_min = max(1, round((d_mi / 35.0) * 60.0))
            selected.append({
                **u,
                "distance_mi": round(d_mi, 2),
                "eta_min": eta_min,
                "assigned_to": triage["call_id"],
                "requested_as": rec.get("unit_type", canon),
            })
    # Safety net: never return an empty list — always send at least the
    # closest ambulance + police so the dispatch map shows something useful.
    if not selected:
        for canon in ("ambulance", "police"):
            cands = sorted(
                [u for u in units if u["type"] == canon],
                key=lambda u: haversine_mi(u["location"][0], u["location"][1],
                                           incident_lat, incident_lon),
            )
            if cands:
                u = cands[0]
                d_mi = haversine_mi(u["location"][0], u["location"][1],
                                    incident_lat, incident_lon)
                selected.append({
                    **u,
                    "distance_mi": round(d_mi, 2),
                    "eta_min": max(1, round((d_mi / 35.0) * 60.0)),
                    "assigned_to": triage["call_id"],
                    "requested_as": canon,
                })
    return selected
