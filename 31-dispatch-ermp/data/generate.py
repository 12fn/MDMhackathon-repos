"""Generate synthetic 911 call transcripts, dispatcher units, installation map data,
and pre-cached AI triage briefs for the DISPATCH demo.

Outputs (under data/):
    calls.json                  5 hand-written 911 transcripts (fire alarm, MVI,
                                structure fire, MASCAL, suspicious package)
    units.json                  8 named installation response units with bases
    incident_locations.geojson  building/road footprints for the demo base
    cached_briefs.json          pre-computed hero CAD entries (cache-first pattern)

Real-data pluggability: see data/load_real.py for the swap-in path (NG911 ANI/ALI
+ CAD MUNIS / Tyler Spillman + USCG Rescue 21 voice-line transcripts).

Seeded for reproducibility (seed=1776). Run any time.
"""
from __future__ import annotations

import json
import random
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

SEED = 1776
OUT = Path(__file__).parent

# ---------------------------------------------------------------------------
# 5 synthetic 911 call transcripts. Each is a sequence of (speaker, t_sec, text)
# tuples — mimics what real CAD voice-to-text segmentation produces. Locations
# point to a fictional consolidated installation footprint ("MCLB / MCB
# DISPATCH-DEMO") with plausible building names and grid references.
# ---------------------------------------------------------------------------
CENTROID_LAT = 32.6850       # rough Albany, GA area (MCLB Albany), shifted
CENTROID_LON = -84.1870
HQ = (CENTROID_LAT, CENTROID_LON)

# Five base buildings / locations (lat, lon)
LOCATIONS = {
    "Hangar 7":               (32.6892, -84.1755),
    "Building 3402 (Bachelor Quarters)": (32.6810, -84.1922),
    "Base Housing — Magnolia Loop":      (32.6770, -84.1990),
    "Range Complex Bravo (Live-Fire)":   (32.6710, -84.1810),
    "Main Gate (Gate 1)":                (32.6940, -84.1870),
    "Perimeter Road Mile 4.2":           (32.6700, -84.1690),
    "Motor Pool Charlie":                (32.6855, -84.1820),
    "Fire Station 1":                    (32.6860, -84.1880),
    "Medical Clinic":                    (32.6830, -84.1860),
}

CALLS = [
    {
        "id": "CALL-001",
        "received_at": "2026-04-27T14:02:18-04:00",
        "incident_summary_seed": "Smoke and active fire alarm at Hangar 7 with possible aviation fuel involvement.",
        "address": "Hangar 7, Flight Line East",
        "lat_lon": LOCATIONS["Hangar 7"],
        "transcript": [
            {"speaker": "Dispatcher", "t": 0.0,  "text": "9-1-1, what is the address of your emergency?"},
            {"speaker": "Caller",     "t": 2.6,  "text": "Yeah uh, this is Sergeant Ortiz at Hangar 7, we have the fire alarm going off and I can see smoke coming out of the back bay."},
            {"speaker": "Dispatcher", "t": 9.4,  "text": "Hangar 7 on the flight line, copy. Are you seeing actual flames?"},
            {"speaker": "Caller",     "t": 13.0, "text": "I see flames now, yeah. Looks like it's near where we stage the JP-8 cart, west side."},
            {"speaker": "Dispatcher", "t": 18.5, "text": "Anybody injured or trapped?"},
            {"speaker": "Caller",     "t": 21.0, "text": "Three of my Marines were inside, I've got two out, I'm missing PFC Daniels — he was in the avionics bay."},
            {"speaker": "Dispatcher", "t": 27.6, "text": "Stay on the line, we are dispatching engines and rescue. Do not re-enter the building."},
            {"speaker": "Caller",     "t": 32.5, "text": "Roger, I'm pulling the rest of the line crew back to the assembly point at the fuel pits."},
        ],
    },
    {
        "id": "CALL-002",
        "received_at": "2026-04-27T08:47:51-04:00",
        "incident_summary_seed": "Multi-vehicle injury accident on perimeter road, two vehicles, possible entrapment.",
        "address": "Perimeter Road, Mile Marker 4.2",
        "lat_lon": LOCATIONS["Perimeter Road Mile 4.2"],
        "transcript": [
            {"speaker": "Dispatcher", "t": 0.0,  "text": "9-1-1, what is your emergency?"},
            {"speaker": "Caller",     "t": 2.1,  "text": "There's a wreck on Perimeter Road, two trucks, one of them is on its side."},
            {"speaker": "Dispatcher", "t": 7.4,  "text": "What mile marker, sir?"},
            {"speaker": "Caller",     "t": 9.6,  "text": "Right around 4.2, just past the cattle guard. I can see somebody not moving in the cab."},
            {"speaker": "Dispatcher", "t": 15.2, "text": "Government vehicles or POVs?"},
            {"speaker": "Caller",     "t": 17.8, "text": "One green Humvee, one civilian Tacoma. The Tacoma is the one rolled over."},
            {"speaker": "Dispatcher", "t": 23.4, "text": "Is fuel leaking? Any fire?"},
            {"speaker": "Caller",     "t": 26.0, "text": "I smell fuel but I don't see fire. The driver of the Humvee is walking but holding his arm."},
            {"speaker": "Dispatcher", "t": 31.8, "text": "Stand by, dispatching. Stay back at least fifty feet."},
        ],
    },
    {
        "id": "CALL-003",
        "received_at": "2026-04-27T22:14:09-04:00",
        "incident_summary_seed": "Active structure fire in base family housing, family unaccounted for.",
        "address": "Magnolia Loop, House 4419, Base Housing",
        "lat_lon": LOCATIONS["Base Housing — Magnolia Loop"],
        "transcript": [
            {"speaker": "Dispatcher", "t": 0.0,  "text": "9-1-1, where is your emergency?"},
            {"speaker": "Caller",     "t": 1.8,  "text": "Magnolia Loop, the house across from me — 4419 — it's on fire, the whole back of it!"},
            {"speaker": "Dispatcher", "t": 8.0,  "text": "Are people inside?"},
            {"speaker": "Caller",     "t": 9.6,  "text": "I think so, the Hendersons live there with two kids. I haven't seen them come out."},
            {"speaker": "Dispatcher", "t": 14.7, "text": "Do not enter the structure. Are you in a safe location?"},
            {"speaker": "Caller",     "t": 18.2, "text": "I'm on my driveway across the street. The fire is going through the roof now."},
            {"speaker": "Dispatcher", "t": 23.0, "text": "Multiple engines and rescue en route. What's your name?"},
            {"speaker": "Caller",     "t": 26.5, "text": "Maria Caldwell, my husband is a Master Sergeant at MCCS."},
        ],
    },
    {
        "id": "CALL-004",
        "received_at": "2026-04-27T11:33:42-04:00",
        "incident_summary_seed": "Mass casualty during live-fire training, multiple injuries, range medic on scene.",
        "address": "Range Complex Bravo, Live-Fire Lane 3",
        "lat_lon": LOCATIONS["Range Complex Bravo (Live-Fire)"],
        "transcript": [
            {"speaker": "Dispatcher", "t": 0.0,  "text": "9-1-1, what is your emergency?"},
            {"speaker": "Caller",     "t": 1.4,  "text": "Range Bravo Lane 3 — we have a mortar mishap, multiple casualties, I count six down."},
            {"speaker": "Dispatcher", "t": 8.0,  "text": "Six casualties confirmed?"},
            {"speaker": "Caller",     "t": 9.8,  "text": "Six down, three are screaming, three are not moving. Range medic is starting triage."},
            {"speaker": "Dispatcher", "t": 16.0, "text": "Is the area secure? Any unexploded ordnance?"},
            {"speaker": "Caller",     "t": 19.2, "text": "Range is cold, ceasefire called, EOD is being notified through chain."},
            {"speaker": "Dispatcher", "t": 25.0, "text": "We are upgrading to MASCAL. Multiple ambulances and the duty surgeon team are en route."},
            {"speaker": "Caller",     "t": 31.8, "text": "Roger. Need helo evac for the worst two — head and chest trauma."},
        ],
    },
    {
        "id": "CALL-005",
        "received_at": "2026-04-27T06:18:27-04:00",
        "incident_summary_seed": "Suspicious unattended package at the main gate, possible IED indicators.",
        "address": "Main Gate (Gate 1), Visitor Inspection Lane",
        "lat_lon": LOCATIONS["Main Gate (Gate 1)"],
        "transcript": [
            {"speaker": "Dispatcher", "t": 0.0,  "text": "9-1-1, what is your emergency?"},
            {"speaker": "Caller",     "t": 1.7,  "text": "This is Corporal Bishop, gate sentry at Gate 1. We have an unattended package in the visitor lane."},
            {"speaker": "Dispatcher", "t": 8.4,  "text": "Describe the package."},
            {"speaker": "Caller",     "t": 10.0, "text": "Cardboard box, taped, maybe two by two feet. There's wires sticking out one side and a smell like motor oil."},
            {"speaker": "Dispatcher", "t": 17.2, "text": "Is the area being evacuated?"},
            {"speaker": "Caller",     "t": 19.4, "text": "We're pushing traffic back to a hundred meters and stopping inbound at the chicane."},
            {"speaker": "Dispatcher", "t": 25.0, "text": "Copy. Notifying PMO and the EOD team. Maintain stand-off, do not approach."},
            {"speaker": "Caller",     "t": 30.5, "text": "Roger, requesting K-9 sweep on the inbound lane as well."},
        ],
    },
]


# ---------------------------------------------------------------------------
# 8 named installation units, each with current location, status, and base.
# ---------------------------------------------------------------------------
UNITS = [
    {"id": "ENG-1",  "callsign": "Engine 1",    "type": "engine",    "status": "available",
     "base": "Fire Station 1",   "location": LOCATIONS["Fire Station 1"],
     "personnel": 4, "capabilities": ["structure fire", "vehicle fire", "aircraft fire"]},
    {"id": "RES-1",  "callsign": "Rescue 1",    "type": "rescue",    "status": "available",
     "base": "Fire Station 1",   "location": LOCATIONS["Fire Station 1"],
     "personnel": 4, "capabilities": ["technical rescue", "extrication", "search"]},
    {"id": "AMB-1",  "callsign": "Ambulance 1", "type": "ambulance", "status": "available",
     "base": "Medical Clinic",   "location": LOCATIONS["Medical Clinic"],
     "personnel": 2, "capabilities": ["ALS transport", "trauma"]},
    {"id": "AMB-2",  "callsign": "Ambulance 2", "type": "ambulance", "status": "available",
     "base": "Medical Clinic",   "location": LOCATIONS["Medical Clinic"],
     "personnel": 2, "capabilities": ["BLS transport", "MCI"]},
    {"id": "HAZ-1",  "callsign": "Hazmat 1",    "type": "hazmat",    "status": "available",
     "base": "Fire Station 1",   "location": LOCATIONS["Fire Station 1"],
     "personnel": 3, "capabilities": ["fuel spill", "chemical containment", "decon"]},
    {"id": "MP-3",   "callsign": "MP Unit 3",   "type": "police",    "status": "available",
     "base": "Main Gate (Gate 1)", "location": LOCATIONS["Main Gate (Gate 1)"],
     "personnel": 2, "capabilities": ["traffic control", "scene security", "force protection"]},
    {"id": "MP-7",   "callsign": "MP Unit 7",   "type": "police",    "status": "available",
     "base": "Motor Pool Charlie", "location": LOCATIONS["Motor Pool Charlie"],
     "personnel": 2, "capabilities": ["patrol", "EOD coordination"]},
    {"id": "GW-1",   "callsign": "Game Warden 1", "type": "police",  "status": "available",
     "base": "Range Complex Bravo (Live-Fire)", "location": LOCATIONS["Range Complex Bravo (Live-Fire)"],
     "personnel": 1, "capabilities": ["range security", "wildland fire spotter"]},
]


# ---------------------------------------------------------------------------
# GeoJSON-shaped building / road footprints for the dispatch map.
# Simple polygons + a perimeter LineString.
# ---------------------------------------------------------------------------
def _box(lat: float, lon: float, dlat: float = 0.0007, dlon: float = 0.0009) -> list[list[float]]:
    return [
        [lon - dlon, lat - dlat],
        [lon + dlon, lat - dlat],
        [lon + dlon, lat + dlat],
        [lon - dlon, lat + dlat],
        [lon - dlon, lat - dlat],
    ]


def _build_geojson() -> dict:
    features = []
    for name, (lat, lon) in LOCATIONS.items():
        is_critical = any(k in name for k in ["Hangar", "Housing", "Range", "Gate"])
        features.append({
            "type": "Feature",
            "geometry": {"type": "Polygon", "coordinates": [_box(lat, lon)]},
            "properties": {
                "name": name,
                "type": "critical" if is_critical else "support",
                "centroid": [lat, lon],
            },
        })
    # Perimeter ring (rough installation boundary)
    perimeter = [
        [-84.205, 32.665],
        [-84.205, 32.700],
        [-84.165, 32.700],
        [-84.165, 32.665],
        [-84.205, 32.665],
    ]
    features.append({
        "type": "Feature",
        "geometry": {"type": "LineString", "coordinates": perimeter},
        "properties": {"name": "Installation Perimeter", "type": "perimeter"},
    })
    return {"type": "FeatureCollection", "features": features}


# ---------------------------------------------------------------------------
# Helpers: deterministic baseline triage so the demo never sits frozen if
# the LLM is unreachable.
# ---------------------------------------------------------------------------
INCIDENT_KEYWORDS = {
    "fire":          ["fire", "smoke", "flames", "alarm", "burning", "structure fire", "burn"],
    "medical":       ["bleeding", "unconscious", "chest pain", "seizure", "not breathing", "injured"],
    "active_threat": ["shooter", "weapon", "armed", "hostile", "threat"],
    "hazmat":        ["fuel", "chemical", "spill", "leak", "JP-8", "vapor"],
    "mvi":           ["wreck", "crash", "accident", "rolled over", "vehicle", "humvee", "tacoma"],
    "mascal":        ["mass casualty", "MASCAL", "multiple casualties", "mortar", "six down"],
    "suspicious_package": ["package", "unattended", "wires sticking out", "IED", "suspicious"],
}


def _full_text(call: dict) -> str:
    return " ".join(seg["text"] for seg in call["transcript"]).lower()


def _baseline_triage(call: dict) -> dict:
    text = _full_text(call)
    # Score each incident type
    scored = []
    for itype, kws in INCIDENT_KEYWORDS.items():
        s = sum(text.count(k.lower()) for k in kws)
        scored.append((s, itype))
    scored.sort(reverse=True)
    incident_type = scored[0][1] if scored[0][0] > 0 else "other"

    # Severity: fire+structure or MASCAL = echo, MVI w/ entrapment = delta, etc.
    if "MASCAL" in text or "mass casualty" in text or "six down" in text:
        severity = "echo"
    elif "fire" in text and ("through the roof" in text or "missing" in text or "trapped" in text):
        severity = "echo"
    elif "wires" in text or "IED" in text.upper():
        severity = "delta"
    elif "injured" in text or "rolled over" in text:
        severity = "delta"
    elif "fire" in text or "smoke" in text:
        severity = "charlie"
    else:
        severity = "bravo"

    # Recommended units — keyed off incident type
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
    units = [{"unit_type": ut, "count": c} for ut, c in UNIT_RECIPES[incident_type]]

    return {
        "call_id": call["id"],
        "incident_type": incident_type,
        "severity": severity,
        "primary_complaint": call["incident_summary_seed"],
        "address_extracted": call["address"],
        "lat_lon": list(call["lat_lon"]),
        "recommended_units": units,
        "callback_questions": [
            "Confirm number of patients and severity.",
            "Confirm any continued threat to first responders.",
            "Confirm best ingress route for responding units.",
        ],
        "confidence": 0.62,
    }


def _baseline_cad_brief(call: dict, triage: dict) -> str:
    """Deterministic CAD entry text — mirrors the hero LLM call's shape."""
    inc_type = triage["incident_type"].replace("_", " ").upper()
    sev = triage["severity"].upper()
    units = ", ".join(f"{u['count']}x {u['unit_type']}" for u in triage["recommended_units"])
    return (
        f"INCIDENT SUMMARY:\n"
        f"  {call['incident_summary_seed']}\n"
        f"  Type: {inc_type} | Severity: {sev} | Location: {call['address']}\n\n"
        f"UNIT ASSIGNMENT RECOMMENDATION:\n"
        f"  Dispatch {units}. Stage uphill / upwind of incident at minimum 50m\n"
        f"  stand-off. PMO assumes scene command pending Battalion Chief arrival.\n\n"
        f"SCENE SAFETY BRIEF:\n"
        f"  - Approach with caution; treat all reports as potentially evolving.\n"
        f"  - Confirm utilities (gas / electrical) and fuel sources isolated.\n"
        f"  - Establish hot / warm / cold zones per NIMS; account for downwind drift.\n"
        f"  - Maintain comms on Channel 4; request mutual aid if scene exceeds initial assignment.\n"
    )


# ---------------------------------------------------------------------------
# Hero LLM precompute — cache-first. Falls back to baseline if no provider.
# ---------------------------------------------------------------------------
def _precompute_briefs(calls: list[dict]) -> dict:
    """Pre-compute hero CAD briefs for every call. Cached to cached_briefs.json."""
    print("Pre-computing CAD briefs (cache-first pattern)...")
    briefs: dict[str, dict] = {}

    # Try the LLM. If anything fails, use deterministic baseline.
    try:
        ROOT = Path(__file__).resolve().parent.parent.parent.parent
        sys.path.insert(0, str(ROOT))
        from shared.kamiwaza_client import chat_json, chat  # type: ignore

        for call in calls:
            full_text = "\n".join(f"[{s['speaker']} t+{s['t']:.1f}s] {s['text']}"
                                  for s in call["transcript"])
            try:
                triage = chat_json(
                    [
                        {"role": "system", "content": (
                            "You are an AI triage agent for an installation 9-1-1 dispatch CAD. "
                            "You output strict JSON with the requested fields."
                        )},
                        {"role": "user", "content": (
                            f"911 CALL TRANSCRIPT:\n{full_text}\n\n"
                            f"GROUND TRUTH (from CAD ANI/ALI): "
                            f"address={call['address']}, lat_lon={call['lat_lon']}, call_id={call['id']}\n\n"
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
                        )},
                    ],
                    schema_hint="triage card with incident_type, severity, units, callback_questions",
                    temperature=0.2,
                    max_tokens=600,
                )
            except Exception as e:  # noqa: BLE001
                print(f"  triage LLM failed for {call['id']}: {e}; using baseline")
                triage = _baseline_triage(call)

            try:
                cad_brief = chat(
                    [
                        {"role": "system", "content": (
                            "You are an experienced 9-1-1 dispatcher writing the CAD entry for the "
                            "responding crew. Three short labeled sections: INCIDENT SUMMARY, "
                            "UNIT ASSIGNMENT RECOMMENDATION, SCENE SAFETY BRIEF. Plain text. "
                            "Terse, professional, action-oriented. No filler."
                        )},
                        {"role": "user", "content": (
                            f"CALL TRANSCRIPT:\n{full_text}\n\n"
                            f"TRIAGE CARD:\n{json.dumps(triage, indent=2)}\n\n"
                            "Write the CAD entry for the responding crew."
                        )},
                    ],
                    temperature=0.3,
                    max_tokens=500,
                )
            except Exception as e:  # noqa: BLE001
                print(f"  brief LLM failed for {call['id']}: {e}; using baseline")
                cad_brief = _baseline_cad_brief(call, triage)

            briefs[call["id"]] = {"triage": triage, "cad_brief": cad_brief}
            print(f"  cached {call['id']} ({triage.get('incident_type','?')}/{triage.get('severity','?')})")

    except Exception as e:  # noqa: BLE001
        print(f"LLM precompute disabled ({e}); using deterministic baselines.")
        for call in calls:
            triage = _baseline_triage(call)
            briefs[call["id"]] = {"triage": triage, "cad_brief": _baseline_cad_brief(call, triage)}

    return briefs


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def _generate_data() -> None:
    rng = random.Random(SEED)
    _ = rng  # reserved for future jitter

    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "calls.json").write_text(json.dumps(CALLS, indent=2))
    (OUT / "units.json").write_text(json.dumps(UNITS, indent=2))
    (OUT / "incident_locations.geojson").write_text(json.dumps(_build_geojson(), indent=2))
    print(f"Wrote {len(CALLS)} calls, {len(UNITS)} units, "
          f"{len(LOCATIONS)+1} geojson features.")


def main() -> None:
    _generate_data()
    briefs = _precompute_briefs(CALLS)
    (OUT / "cached_briefs.json").write_text(json.dumps(briefs, indent=2))
    print(f"Wrote cached_briefs.json ({len(briefs)} entries).")


if __name__ == "__main__":
    main()
