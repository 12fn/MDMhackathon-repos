"""OMNI FastAPI backend — port 8038.

Serves the synthetic data, ABAC-filtered views, the cross-domain correlator,
the Commander's Brief, and the SHA-256 hash-chained who-saw-what audit log.

Endpoints:
  GET  /health
  GET  /api/installation
  GET  /api/personas
  GET  /api/streams                         summary counts per stream
  GET  /api/streams/{persona_id}            ABAC-filtered summary (redacted rows kept)
  GET  /api/timeline                        fused timeline (sorted)
  GET  /api/timeline/{persona_id}           ABAC-filtered fused timeline
  GET  /api/stream/{name}                   raw events for one stream
  GET  /api/maintenance                     GCSS-MC asset list
  GET  /api/critical_infrastructure         HIFLD asset layer
  GET  /api/cached                          pre-computed correlation + brief
  POST /api/correlate                       live cross-domain correlator
  POST /api/correlate/{persona_id}          ABAC-filtered correlation
  POST /api/brief                           live Commander's I-COP brief
  POST /api/audit                           append a who-saw-what audit row
  GET  /api/audit                           recent audit chain (newest first)
  GET  /api/audit/verify                    verify integrity of the whole chain
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
    from src.abac import (  # noqa: E402
        filter_streams_summary, filter_timeline, filter_anomalies,
        can_view_brief,
    )
    from src.audit import (  # noqa: E402
        append_audit, read_audit_chain, verify_chain, reset_audit_log,
    )
except ImportError:
    from correlator import (  # type: ignore  # noqa: E402
        correlate_streams, commander_brief, baseline_correlation,
        baseline_brief, HERO_MODEL,
    )
    from abac import (  # type: ignore  # noqa: E402
        filter_streams_summary, filter_timeline, filter_anomalies,
        can_view_brief,
    )
    from audit import (  # type: ignore  # noqa: E402
        append_audit, read_audit_chain, verify_chain, reset_audit_log,
    )

DATA = Path(__file__).resolve().parent.parent / "data"

app = FastAPI(title="OMNI", version="1.0.0")
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


def _persona(pid: str) -> dict:
    for p in _load("personas.json"):
        if p["id"].upper() == pid.upper():
            return p
    raise HTTPException(404, f"unknown persona: {pid}")


@app.on_event("startup")
def _startup() -> None:
    # Cold demos: start with a clean audit chain.
    if os.getenv("OMNI_RESET_AUDIT_ON_START", "1") != "0":
        reset_audit_log()
        append_audit({
            "persona_id": "SYSTEM",
            "action": "GENESIS",
            "target": "audit_chain",
            "meta": {"installation": _installation()["name"]},
        })


@app.get("/health")
def health():
    return {
        "ok": True,
        "service": "OMNI",
        "primary_model": PRIMARY_MODEL,
        "hero_model": HERO_MODEL,
        "kamiwaza_endpoint": os.getenv("KAMIWAZA_BASE_URL") or "kamiwaza-default",
        "n_installations": len(_load("installations.json")),
        "n_fused_events": len(_load("fused_timeline.json")),
        "n_personas": len(_load("personas.json")),
        "cached_briefs_present": (DATA / "cached_briefs.json").exists(),
    }


@app.get("/api/installation")
def installation():
    return _installation()


@app.get("/api/personas")
def personas():
    return _load("personas.json")


def _streams_summary() -> list[dict]:
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


@app.get("/api/streams")
def streams():
    return _streams_summary()


@app.get("/api/streams/{persona_id}")
def streams_for_persona(persona_id: str):
    p = _persona(persona_id)
    return filter_streams_summary(_streams_summary(), p)


@app.get("/api/timeline")
def timeline():
    return _load("fused_timeline.json")


@app.get("/api/timeline/{persona_id}")
def timeline_for_persona(persona_id: str):
    p = _persona(persona_id)
    return filter_timeline(_load("fused_timeline.json"), p)


@app.get("/api/stream/{name}")
def stream(name: str):
    fname = {
        "gate": "gate_events.json",
        "utility": "utility_events.json",
        "ems": "ems_events.json",
        "massnotify": "massnotify_events.json",
        "weather": "weather.json",
        "maintenance": "maintenance.json",
        "rf": "rf_events.json",
        "drone_rf": "drone_rf_events.json",
        "firms": "firms.json",
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


def _resolve_correlation(use_cache: bool) -> dict:
    inst = _installation()
    fused = _load("fused_timeline.json")
    as_of = fused[-1]["ts_iso"] if fused else ""
    if use_cache and (DATA / "cached_briefs.json").exists():
        cached_obj = _load("cached_briefs.json")
        live = cached_obj.get("live_correlation")
        if live and isinstance(live, dict) and "anomalies" in live:
            live["_source"] = live.get("_source", "cached_live")
            return live
        bc = cached_obj.get("baseline_correlation") or baseline_correlation(fused)
        bc["_source"] = bc.get("_source", "cached_baseline")
        return bc
    return correlate_streams(inst["name"], as_of, fused)


@app.post("/api/correlate")
def correlate(req: CorrelateRequest | None = None):
    req = req or CorrelateRequest()
    return _resolve_correlation(req.use_cache)


@app.post("/api/correlate/{persona_id}")
def correlate_for_persona(persona_id: str, req: CorrelateRequest | None = None):
    req = req or CorrelateRequest()
    p = _persona(persona_id)
    raw = _resolve_correlation(req.use_cache)
    return filter_anomalies(raw, p)


class BriefRequest(BaseModel):
    use_cache: bool = True
    correlation: dict | None = None
    persona_id: str | None = None


@app.post("/api/brief")
def brief(req: BriefRequest | None = None):
    req = req or BriefRequest()
    inst = _installation()
    fused = _load("fused_timeline.json")
    as_of = fused[-1]["ts_iso"] if fused else ""
    if req.persona_id:
        p = _persona(req.persona_id)
        if not can_view_brief(p):
            raise HTTPException(403, f"persona {p['id']} not authorized to view brief")
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


class AuditRequest(BaseModel):
    persona_id: str
    action: str
    target: str | None = None
    meta: dict | None = None


@app.post("/api/audit")
def audit_append(req: AuditRequest):
    return append_audit({
        "persona_id": req.persona_id,
        "action": req.action,
        "target": req.target,
        "meta": req.meta or {},
    })


@app.get("/api/audit")
def audit_read(limit: int = 50):
    return read_audit_chain(limit=limit)


@app.get("/api/audit/verify")
def audit_verify():
    ok, n, msg = verify_chain()
    return {"ok": ok, "rows_checked": n, "message": msg}


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("OMNI_BACKEND_PORT", "8038"))
    uvicorn.run("src.api:app", host="0.0.0.0", port=port, reload=False)
