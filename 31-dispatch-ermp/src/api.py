"""DISPATCH FastAPI backend — port 8031.

Endpoints:
  GET  /health                                liveness
  GET  /api/calls                             5 synthetic 911 transcripts
  GET  /api/calls/{call_id}                   one call
  GET  /api/units                             8 installation response units
  GET  /api/locations                         building/road geojson
  POST /api/triage/{call_id}                  AI triage card (cache-first)
  POST /api/brief/{call_id}                   hero CAD entry (cache-first)
  POST /api/dispatch/{call_id}                pipeline: triage + brief + unit pick
  GET  /api/transcript/{call_id}/stream       SSE streaming-text playback
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

ROOT = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(ROOT))

from shared.kamiwaza_client import chat, chat_json, PRIMARY_MODEL  # noqa: E402

try:
    from src.triage import (  # type: ignore
        live_triage, live_cad_brief, baseline_triage, baseline_cad_brief,
        cached_brief, select_units, HERO_MODEL,
    )
except ImportError:
    from triage import (  # type: ignore
        live_triage, live_cad_brief, baseline_triage, baseline_cad_brief,
        cached_brief, select_units, HERO_MODEL,
    )

DATA = Path(__file__).resolve().parent.parent / "data"

app = FastAPI(title="DISPATCH", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

_CACHE: dict[str, Any] = {}


def _load_json(name: str):
    if name not in _CACHE:
        _CACHE[name] = json.loads((DATA / name).read_text())
    return _CACHE[name]


# ---------------------------------------------------------------------------
@app.get("/health")
def health():
    return {
        "ok": True,
        "service": "DISPATCH",
        "primary_model": PRIMARY_MODEL,
        "hero_model": HERO_MODEL,
        "kamiwaza_endpoint": os.getenv("KAMIWAZA_BASE_URL") or "kamiwaza-default",
        "n_calls": len(_load_json("calls.json")),
        "n_units": len(_load_json("units.json")),
    }


@app.get("/api/calls")
def calls():
    return _load_json("calls.json")


@app.get("/api/calls/{call_id}")
def one_call(call_id: str):
    for c in _load_json("calls.json"):
        if c["id"] == call_id:
            return c
    raise HTTPException(404, f"call {call_id} not found")


@app.get("/api/units")
def units():
    return _load_json("units.json")


@app.get("/api/locations")
def locations():
    return _load_json("incident_locations.geojson")


def _find_call(call_id: str) -> dict:
    for c in _load_json("calls.json"):
        if c["id"] == call_id:
            return c
    raise HTTPException(404, f"call {call_id} not found")


# ---------------------------------------------------------------------------
class StageRequest(BaseModel):
    use_cache: bool = True
    use_hero_model: bool = True


@app.post("/api/triage/{call_id}")
def triage(call_id: str, req: StageRequest | None = None):
    req = req or StageRequest()
    call = _find_call(call_id)
    if req.use_cache:
        cb = cached_brief(call_id)
        if cb and "triage" in cb:
            return {"call_id": call_id, "triage": cb["triage"], "cached": True}
    out = live_triage(chat_json, call)
    return {"call_id": call_id, "triage": out, "cached": False}


@app.post("/api/brief/{call_id}")
def brief(call_id: str, req: StageRequest | None = None):
    req = req or StageRequest()
    call = _find_call(call_id)
    if req.use_cache:
        cb = cached_brief(call_id)
        if cb and "cad_brief" in cb:
            return {
                "call_id": call_id,
                "triage": cb["triage"],
                "cad_brief": cb["cad_brief"],
                "cached": True,
            }
    triage_card = live_triage(chat_json, call)
    cad_brief = live_cad_brief(
        chat, call, triage_card,
        model=(HERO_MODEL if req.use_hero_model else PRIMARY_MODEL),
    )
    return {
        "call_id": call_id,
        "triage": triage_card,
        "cad_brief": cad_brief,
        "cached": False,
    }


@app.post("/api/dispatch/{call_id}")
def dispatch(call_id: str, req: StageRequest | None = None):
    """Full pipeline: triage card + CAD brief + greedy unit selection."""
    req = req or StageRequest()
    call = _find_call(call_id)
    units_all = _load_json("units.json")

    if req.use_cache:
        cb = cached_brief(call_id)
        if cb:
            triage_card = cb["triage"]
            brief_text = cb["cad_brief"]
            cached = True
        else:
            triage_card = live_triage(chat_json, call)
            brief_text = live_cad_brief(
                chat, call, triage_card,
                model=(HERO_MODEL if req.use_hero_model else PRIMARY_MODEL),
            )
            cached = False
    else:
        triage_card = live_triage(chat_json, call)
        brief_text = live_cad_brief(
            chat, call, triage_card,
            model=(HERO_MODEL if req.use_hero_model else PRIMARY_MODEL),
        )
        cached = False

    selected = select_units(units_all, triage_card)
    return {
        "call_id": call_id,
        "call": call,
        "triage": triage_card,
        "cad_brief": brief_text,
        "assigned_units": selected,
        "cached": cached,
    }


# ---------------------------------------------------------------------------
@app.get("/api/transcript/{call_id}/stream")
def transcript_stream(call_id: str):
    """SSE-stream the call transcript at the cadence captured in the data.

    Mimics live Whisper-style transcription appearing as the dispatcher
    listens. No LLM call — pure replay.
    """
    call = _find_call(call_id)

    async def event_gen():
        yield f"event: meta\ndata: {json.dumps({'call_id': call_id, 'address': call['address']})}\n\n"
        last_t = 0.0
        for seg in call["transcript"]:
            wait = max(0.0, seg["t"] - last_t)
            # Cap so the demo doesn't drag on a slow segment
            await asyncio.sleep(min(wait * 0.4, 1.6))
            yield f"event: segment\ndata: {json.dumps(seg)}\n\n"
            last_t = seg["t"]
        yield "event: done\ndata: {}\n\n"

    return StreamingResponse(event_gen(), media_type="text/event-stream")


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("DISPATCH_BACKEND_PORT", "8031"))
    uvicorn.run("src.api:app", host="0.0.0.0", port=port, reload=False)
