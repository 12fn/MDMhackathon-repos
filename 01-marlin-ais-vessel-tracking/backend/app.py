# MARLIN — AIS dark-vessel + anomaly intel layer
# Part of the MDM 2026 Hackathon Templates (https://github.com/12fn/MDMhackathon-repos)
# MIT licensed. Built on GAI (Government Acquisitions, Inc.) + Kamiwaza (https://www.kamiwaza.ai/).
"""MARLIN FastAPI backend — port 8001.

Endpoints:
  GET  /health                            — liveness + active provider/model
  GET  /api/vessels                       — vessel roster
  GET  /api/tracks                        — full track data (all pings, all vessels)
  GET  /api/denied                        — denied/restricted area polygons
  GET  /api/anomalies                     — pre-computed + live-detected anomalies
  GET  /api/timeline                      — 100-step timeline for the slider
  POST /api/intel/{mmsi}                  — JSON: 3-paragraph intel narrative + indicators
  POST /api/intel/{mmsi}/stream           — SSE: stream the narrative
"""
from __future__ import annotations

import asyncio
import json
import math
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

# Make repo importable for shared/
ROOT = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(ROOT))

from shared.kamiwaza_client import chat, chat_json, get_client, PRIMARY_MODEL, PROVIDER  # noqa: E402

DATA = Path(__file__).resolve().parent.parent / "data"

app = FastAPI(title="MARLIN", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# --- Lazy load JSON ---------------------------------------------------------
def _load(name: str) -> Any:
    return json.loads((DATA / name).read_text())


_CACHE: dict[str, Any] = {}


def cache(key: str) -> Any:
    if key not in _CACHE:
        _CACHE[key] = _load(f"{key}.json")
    return _CACHE[key]


# --- Routes -----------------------------------------------------------------
def _provider_endpoint() -> str:
    """Surface the active provider's endpoint for the UI header (no secrets)."""
    if PROVIDER == "kamiwaza":
        return os.getenv("KAMIWAZA_BASE_URL", "kamiwaza-on-prem")
    if PROVIDER == "openrouter":
        return os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
    if PROVIDER == "custom":
        return os.getenv("LLM_BASE_URL", "openai-compatible")
    if PROVIDER == "anthropic":
        return "anthropic-api"
    if PROVIDER == "openai":
        return "api.openai.com"
    return PROVIDER


@app.get("/health")
def health():
    return {
        "ok": True,
        "service": "MARLIN",
        "provider": PROVIDER,
        "primary_model": PRIMARY_MODEL,
        "endpoint": _provider_endpoint(),
        # Back-compat alias for older UI builds
        "kamiwaza_endpoint": _provider_endpoint(),
    }


@app.get("/api/vessels")
def vessels():
    return cache("vessels")


@app.get("/api/tracks")
def tracks():
    return cache("tracks")


@app.get("/api/denied")
def denied():
    return cache("denied_areas")


# Alias used by build_context
def denied_list():
    return cache("denied_areas")


@app.get("/api/anomalies")
def anomalies():
    return cache("anomalies")


@app.get("/api/timeline")
def timeline():
    return cache("timeline")


# --- Vessel + context lookup -----------------------------------------------
def find_vessel(mmsi: str) -> dict:
    for t in cache("tracks"):
        if t["mmsi"] == mmsi:
            return t
    raise HTTPException(404, f"vessel {mmsi} not found")


def build_context(mmsi: str) -> dict:
    """Assemble the LLM context blob for a flagged vessel."""
    vessel = find_vessel(mmsi)
    anoms = [a for a in cache("anomalies")
             if a.get("mmsi") == mmsi or mmsi in a.get("partners", [])]
    # Last 12 pings as the "track snippet"
    snippet = vessel["pings"][-12:]
    # Nearby vessels: any track whose final ping is within 5 nm of this one
    last = vessel["pings"][-1]
    nearby = []
    for t in cache("tracks"):
        if t["mmsi"] == mmsi:
            continue
        lp = t["pings"][-1]
        d_nm = haversine_nm(last["lat"], last["lon"], lp["lat"], lp["lon"])
        if d_nm < 50:
            nearby.append({
                "mmsi": t["mmsi"], "name": t["name"], "type": t["type"],
                "flag": t["flag"], "distance_nm": round(d_nm, 1),
                "last_lat": lp["lat"], "last_lon": lp["lon"],
            })
    nearby.sort(key=lambda x: x["distance_nm"])
    return {
        "vessel": {k: v for k, v in vessel.items() if k != "pings"},
        "track_snippet": snippet,
        "anomalies": anoms,
        "nearby_vessels": nearby[:5],
        "denied_areas": denied_list(),
    }


def haversine_nm(lat1, lon1, lat2, lon2) -> float:
    R_NM = 3440.065
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * R_NM * math.asin(min(1.0, math.sqrt(a)))


# --- Prompt builders --------------------------------------------------------
SYSTEM_PROMPT = """You are an all-source maritime intelligence analyst supporting USMC LOGCOM and III MEF G-2 in INDOPACOM contested logistics operations.

Your audience is a Marine Logistics Group watch officer (E-7 to O-3) who must decide in <90 seconds whether to escalate to a Maritime Interdiction Operation (MIO) request. Be precise, cite specific pings (timestamp + lat/lon), and end with a clear, time-bounded recommendation.

Tone: terse, professional, action-oriented. No hedging filler. Treat every datum in the provided JSON as ground truth observed by AIS receivers and ISR cueing."""


NARRATIVE_INSTRUCTIONS = """Write exactly THREE paragraphs:

PARAGRAPH 1 — Pattern of Life Assessment.
Describe what the vessel has been doing, citing at least two specific (timestamp, lat, lon) tuples from the track snippet. Compare against expected behavior for the vessel's declared type and flag.

PARAGRAPH 2 — Anomaly Analysis.
For each anomaly in the context, explain (a) what the technical indicator is, (b) why it matters operationally for Marine sustainment in the second island chain, and (c) what nearby vessel activity (cite MMSIs) corroborates or amplifies the concern.

PARAGRAPH 3 — Recommendation.
State a single recommended course of action with a time horizon (e.g., "Recommend MIO interrogation by [unit] within [N] min before vessel exits radar horizon"). Include one CCIR-style EEI the watch officer should task next."""


# --- Hero endpoint: structured intel ----------------------------------------
class IntelResponse(BaseModel):
    narrative: str
    indicators: list[dict]
    context: dict


@app.post("/api/intel/{mmsi}")
def intel(mmsi: str) -> IntelResponse:
    ctx = build_context(mmsi)

    # Call 1: narrative
    narrative = chat(
        [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": (
                f"CONTEXT (JSON):\n{json.dumps(ctx, indent=2)}\n\n"
                f"TASK:\n{NARRATIVE_INSTRUCTIONS}"
            )},
        ],
        temperature=0.4,
        max_tokens=900,
    )

    # Call 2: structured indicators (JSON-mode)
    try:
        indicators_obj = chat_json(
            [
                {"role": "system", "content": (
                    SYSTEM_PROMPT + " You output strict JSON conforming to the requested schema."
                )},
                {"role": "user", "content": (
                    f"CONTEXT:\n{json.dumps(ctx, indent=2)}\n\n"
                    "Produce JSON: {\"indicators\":[{\"id\":str,\"type\":\"AIS_GAP|LOITER|RENDEZVOUS|DENIED_AREA|FLAG_OF_CONVENIENCE|OTHER\","
                    "\"confidence\":0..1,\"timestamp\":iso8601,\"lat\":float,\"lon\":float,"
                    "\"description\":str,\"recommended_action\":str}]} -- 2 to 5 indicators."
                )},
            ],
            schema_hint="indicators[] with id, type, confidence, timestamp, lat, lon, description, recommended_action",
            temperature=0.2,
            max_tokens=600,
        )
        indicators = indicators_obj.get("indicators", [])
    except Exception as e:  # noqa: BLE001
        indicators = [{"id": "FALLBACK", "type": "OTHER", "confidence": 0.5,
                       "timestamp": ctx["track_snippet"][-1]["t"],
                       "lat": ctx["track_snippet"][-1]["lat"],
                       "lon": ctx["track_snippet"][-1]["lon"],
                       "description": f"LLM JSON-mode error: {e}",
                       "recommended_action": "Re-run analysis"}]

    return IntelResponse(narrative=narrative, indicators=indicators, context=ctx)


# --- Streaming variant for the hero demo ------------------------------------
@app.post("/api/intel/{mmsi}/stream")
def intel_stream(mmsi: str):
    ctx = build_context(mmsi)
    client = get_client()

    def event_gen():
        # Send the context first so the UI can render the side panel header
        yield f"event: context\ndata: {json.dumps(ctx)}\n\n"

        # Stream the narrative
        try:
            stream = client.chat.completions.create(
                model=PRIMARY_MODEL,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": (
                        f"CONTEXT (JSON):\n{json.dumps(ctx, indent=2)}\n\n"
                        f"TASK:\n{NARRATIVE_INSTRUCTIONS}"
                    )},
                ],
                temperature=0.4,
                max_tokens=900,
                stream=True,
            )
            for chunk in stream:
                delta = chunk.choices[0].delta.content if chunk.choices else None
                if delta:
                    yield f"event: token\ndata: {json.dumps({'t': delta})}\n\n"
        except Exception as e:  # noqa: BLE001
            # Fall back to non-streaming
            try:
                txt = chat(
                    [
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": (
                            f"CONTEXT:\n{json.dumps(ctx, indent=2)}\n\n{NARRATIVE_INSTRUCTIONS}"
                        )},
                    ],
                    temperature=0.4,
                    max_tokens=900,
                )
                yield f"event: token\ndata: {json.dumps({'t': txt})}\n\n"
            except Exception as e2:  # noqa: BLE001
                yield f"event: error\ndata: {json.dumps({'error': str(e2)})}\n\n"

        # Then issue the structured indicators
        try:
            indicators_obj = chat_json(
                [
                    {"role": "system", "content": SYSTEM_PROMPT + " Output strict JSON."},
                    {"role": "user", "content": (
                        f"CONTEXT:\n{json.dumps(ctx, indent=2)}\n\n"
                        "Produce JSON: {\"indicators\":[{\"id\":str,\"type\":\"AIS_GAP|LOITER|RENDEZVOUS|DENIED_AREA|FLAG_OF_CONVENIENCE|OTHER\","
                        "\"confidence\":0..1,\"timestamp\":iso8601,\"lat\":float,\"lon\":float,"
                        "\"description\":str,\"recommended_action\":str}]} -- 2 to 5 indicators."
                    )},
                ],
                schema_hint="indicators[]",
                temperature=0.2,
                max_tokens=600,
            )
            yield f"event: indicators\ndata: {json.dumps(indicators_obj)}\n\n"
        except Exception as e:  # noqa: BLE001
            yield f"event: indicators\ndata: {json.dumps({'indicators': [], 'error': str(e)})}\n\n"

        yield "event: done\ndata: {}\n\n"

    return StreamingResponse(event_gen(), media_type="text/event-stream")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend.app:app", host="0.0.0.0", port=8001, reload=False)
