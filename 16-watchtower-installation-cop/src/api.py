"""WATCHTOWER FastAPI backend — port 8016.

Serves the synthetic data and the hero AI endpoints (cache-first):

  GET  /health
  GET  /api/installation
  GET  /api/streams                       summary counts per stream
  GET  /api/timeline                      fused timeline (sorted)
  GET  /api/stream/{name}                 events for a single stream
  GET  /api/maintenance                   GCSS-MC asset list
  GET  /api/critical_infrastructure       HIFLD asset layer
  GET  /api/cached                        pre-computed correlation + brief
  POST /api/correlate                     live cross-stream correlator (mini)
  POST /api/brief                         live Commander's I-COP brief (hero)
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

ROOT = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(ROOT))

from shared.kamiwaza_client import PRIMARY_MODEL  # noqa: E402

try:
    from src.correlator import (  # noqa: E402
        correlate_streams, commander_brief, baseline_correlation,
        baseline_brief, HERO_MODEL,
    )
except ImportError:
    from correlator import (  # type: ignore  # noqa: E402
        correlate_streams, commander_brief, baseline_correlation,
        baseline_brief, HERO_MODEL,
    )

DATA = Path(__file__).resolve().parent.parent / "data"

app = FastAPI(title="WATCHTOWER", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

_CACHE: dict[str, Any] = {}


def _load(name: str) -> Any:
    if name not in _CACHE:
        path = DATA / name
        if not path.exists():
            raise HTTPException(500, f"data file missing: {name} — run python data/generate.py")
        _CACHE[name] = json.loads(path.read_text())
    return _CACHE[name]


def _installation() -> dict:
    insts = _load("installations.json")
    if not insts:
        raise HTTPException(500, "no installations defined")
    return insts[0]


@app.get("/health")
def health():
    return {
        "ok": True,
        "service": "WATCHTOWER",
        "primary_model": PRIMARY_MODEL,
        "hero_model": HERO_MODEL,
        "kamiwaza_endpoint": os.getenv("KAMIWAZA_BASE_URL") or "kamiwaza-default",
        "n_installations": len(_load("installations.json")),
        "n_fused_events": len(_load("fused_timeline.json")),
        "cached_briefs_present": (DATA / "cached_briefs.json").exists(),
    }


@app.get("/api/installation")
def installation():
    return _installation()


@app.get("/api/streams")
def streams():
    fused = _load("fused_timeline.json")
    by_stream: dict[str, int] = {}
    anom_by_stream: dict[str, int] = {}
    for r in fused:
        by_stream[r["stream"]] = by_stream.get(r["stream"], 0) + 1
        if r.get("is_anomaly"):
            anom_by_stream[r["stream"]] = anom_by_stream.get(r["stream"], 0) + 1
    return [
        {"stream": s, "count": c, "anomalies": anom_by_stream.get(s, 0)}
        for s, c in sorted(by_stream.items())
    ]


@app.get("/api/timeline")
def timeline():
    return _load("fused_timeline.json")


@app.get("/api/stream/{name}")
def stream(name: str):
    fname = {
        "gate": "gate_events.json",
        "utility": "utility_events.json",
        "ems": "ems_events.json",
        "massnotify": "massnotify_events.json",
        "weather": "weather.json",
        "maintenance": "maintenance.json",
    }.get(name)
    if not fname:
        raise HTTPException(404, f"unknown stream: {name}")
    return _load(fname)


@app.get("/api/maintenance")
def maintenance():
    return _load("maintenance.json")


@app.get("/api/critical_infrastructure")
def critical_infrastructure():
    inst = _installation()
    return inst.get("critical_infrastructure", [])


@app.get("/api/cached")
def cached():
    if not (DATA / "cached_briefs.json").exists():
        # Compute on the fly from baseline (still no LLM call).
        inst = _installation()
        fused = _load("fused_timeline.json")
        corr = baseline_correlation(fused)
        brief = baseline_brief(inst["name"], fused[-1]["ts_iso"] if fused else "", corr)
        return {
            "as_of_iso": fused[-1]["ts_iso"] if fused else "",
            "installation": {"id": inst["id"], "name": inst["name"], "centroid": inst["centroid"]},
            "baseline_correlation": corr,
            "baseline_brief": brief,
            "live_correlation": None,
            "live_brief": None,
        }
    return _load("cached_briefs.json")


class CorrelateRequest(BaseModel):
    use_cache: bool = True


@app.post("/api/correlate")
def correlate(req: CorrelateRequest | None = None):
    req = req or CorrelateRequest()
    inst = _installation()
    fused = _load("fused_timeline.json")
    as_of = fused[-1]["ts_iso"] if fused else ""
    if req.use_cache and (DATA / "cached_briefs.json").exists():
        cached_obj = _load("cached_briefs.json")
        live = cached_obj.get("live_correlation")
        if live and isinstance(live, dict) and "anomalies" in live:
            live["_source"] = live.get("_source", "cached_live")
            return live
        # Fall back to cached baseline so the UI never empties out.
        bc = cached_obj.get("baseline_correlation") or baseline_correlation(fused)
        bc["_source"] = bc.get("_source", "cached_baseline")
        return bc
    return correlate_streams(inst["name"], as_of, fused)


class BriefRequest(BaseModel):
    use_cache: bool = True
    correlation: dict | None = None


@app.post("/api/brief")
def brief(req: BriefRequest | None = None):
    req = req or BriefRequest()
    inst = _installation()
    fused = _load("fused_timeline.json")
    as_of = fused[-1]["ts_iso"] if fused else ""
    if req.use_cache and (DATA / "cached_briefs.json").exists():
        cached_obj = _load("cached_briefs.json")
        live = cached_obj.get("live_brief")
        if live and live.strip():
            return {"brief": live, "source": "cached_live"}
        b = cached_obj.get("baseline_brief") or ""
        if b:
            return {"brief": b, "source": "cached_baseline"}
    corr = req.correlation or correlate_streams(inst["name"], as_of, fused)
    text = commander_brief(inst["name"], as_of, corr)
    return {"brief": text, "source": "live"}


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("WATCHTOWER_BACKEND_PORT", "8016"))
    uvicorn.run("src.api:app", host="0.0.0.0", port=port, reload=False)
