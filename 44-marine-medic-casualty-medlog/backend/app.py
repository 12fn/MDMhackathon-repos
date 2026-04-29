"""MARINE-MEDIC FastAPI backend — port 8044.

Endpoints:
  GET  /health                       — liveness + active model
  GET  /api/hub                      — hub
  GET  /api/spokes                   — 12 spokes
  GET  /api/routes                   — hub<->spoke edges
  GET  /api/inventory/v1             — blood inventory (~200 rows)
  GET  /api/inventory/v2             — broader Class VIII (~1000 rows)
  GET  /api/network                  — Medical Supply Network Data Model
  GET  /api/gcss-mc                  — GCSS-MC requisition log
  GET  /api/scenarios                — 5 casualty scenarios
  GET  /api/doctrine                 — TCCC / JTS triage doctrine
  GET  /api/vendors                  — approved buy-on-market vendors
  POST /api/pipeline                 — run the full 6-stage pipeline
                                        body: {scenario_id, wia_count?, location_id?, hero?}
  GET  /api/brief?scenario=…         — cache-first brief
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

ROOT = Path(__file__).resolve().parents[3]
APP_ROOT = Path(__file__).resolve().parents[1]
for p in (str(ROOT), str(APP_ROOT)):
    if p not in sys.path:
        sys.path.insert(0, p)

from shared.kamiwaza_client import PRIMARY_MODEL  # noqa: E402
from src import agent  # noqa: E402


app = FastAPI(title="MARINE-MEDIC — Class VIII / Casualty Flow", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], allow_methods=["*"], allow_headers=["*"],
)


@app.get("/health")
def health():
    return {
        "ok": True,
        "service": "MARINE-MEDIC",
        "primary_model": PRIMARY_MODEL,
        "kamiwaza_endpoint": os.getenv("KAMIWAZA_BASE_URL") or "kamiwaza-on-prem",
    }


@app.get("/api/hub")
def get_hub():
    return agent.load_hub()


@app.get("/api/spokes")
def get_spokes():
    return agent.load_spokes()


@app.get("/api/routes")
def get_routes():
    return agent.load_routes()


@app.get("/api/inventory/v1")
def get_inv_v1():
    return agent.load_inventory_v1()


@app.get("/api/inventory/v2")
def get_inv_v2():
    return agent.load_inventory_v2()


@app.get("/api/network")
def get_network():
    return agent.load_supply_network()


@app.get("/api/gcss-mc")
def get_gcss_mc():
    return agent.load_gcss_mc()


@app.get("/api/scenarios")
def get_scenarios():
    return agent.load_scenarios()


@app.get("/api/doctrine")
def get_doctrine():
    return agent.load_doctrine()


@app.get("/api/vendors")
def get_vendors():
    return agent.load_vendors()


class PipelineReq(BaseModel):
    scenario_id: str = "he_blast_mascal"
    wia_count: int | None = None
    location_id: str | None = None
    hero: bool = True


@app.post("/api/pipeline")
def run_pipeline(req: PipelineReq):
    out = agent.run_pipeline(
        req.scenario_id, hero=req.hero,
        wia_override=req.wia_count, location_override=req.location_id,
    )
    return {
        "scenario_id":  req.scenario_id,
        "scenario":     out["scenario"],
        "event":        out["event"],
        "cards":        out["cards"],
        "demand":       out["demand"],
        "gap":          out["gap"],
        "requisition":  out["requisition"],
        "brief":        out["brief"],
        "market":       out["market"],
        "audit":        out["audit"],
        "generated_at": out["generated_at"],
    }


@app.get("/api/brief")
def get_brief(scenario: str = Query("he_blast_mascal"), live: bool = Query(False)):
    if not live:
        cached = agent.load_cached_briefs().get(scenario)
        if cached and cached.get("brief"):
            return cached
    out = agent.run_pipeline(scenario, hero=True)
    return {
        "scenario": scenario,
        "brief":    out["brief"],
        "demand":   out["demand"],
        "gap":      out["gap"],
        "requisition": out["requisition"],
        "generated_at": out["generated_at"],
        "source":   "live",
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend.app:app", host="0.0.0.0", port=8044, reload=False)
