"""VITALS FastAPI backend — port 8015.

Endpoints:
  GET  /health                    — liveness + active model
  GET  /api/hub                   — single hub node
  GET  /api/spokes                — 12 spoke nodes
  GET  /api/inventory             — inventory rows (apply ?scenario=…)
  GET  /api/routes                — hub<->spoke routes (apply ?scenario=…)
  GET  /api/casualties            — casualty assumptions
  GET  /api/vendors               — approved buy-on-market vendors
  GET  /api/scores?scenario=…     — Step 1: per-spoke viability scoring
  GET  /api/brief?scenario=…      — Step 2: hero Commander's Decision Brief
                                    (cache-first; uses cached_briefs.json)
  GET  /api/scenarios             — list of demo scenarios
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from shared.kamiwaza_client import PRIMARY_MODEL  # noqa: E402
from src import agent  # noqa: E402


app = FastAPI(title="VITALS — DHA RESCUE", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health():
    return {
        "ok": True,
        "service": "VITALS",
        "primary_model": PRIMARY_MODEL,
        "kamiwaza_endpoint": os.getenv("KAMIWAZA_BASE_URL") or "kamiwaza-on-prem",
    }


@app.get("/api/hub")
def get_hub():
    return agent.load_hub()


@app.get("/api/spokes")
def get_spokes():
    return agent.load_spokes()


@app.get("/api/inventory")
def get_inventory(scenario: str = Query("baseline")):
    inv = agent.load_inventory()
    if scenario in agent.SCENARIOS and scenario != "baseline":
        spokes = agent.load_spokes()
        inv, _ = agent.apply_scenario(scenario, spokes, inv, agent.load_routes())
    return inv


@app.get("/api/routes")
def get_routes(scenario: str = Query("baseline")):
    rts = agent.load_routes()
    if scenario in agent.SCENARIOS and scenario != "baseline":
        spokes = agent.load_spokes()
        _, rts = agent.apply_scenario(scenario, spokes, agent.load_inventory(), rts)
    return rts


@app.get("/api/casualties")
def get_casualties():
    return agent.load_casualties()


@app.get("/api/vendors")
def get_vendors():
    return agent.load_vendors()


@app.get("/api/scenarios")
def get_scenarios():
    return [{"id": k, **v} for k, v in agent.SCENARIOS.items()]


@app.get("/api/scores")
def get_scores(scenario: str = Query("baseline")):
    """Step 1 — deterministic baseline scoring (no LLM hit on this endpoint;
    the Streamlit UI calls into agent.score_spokes for the LLM-overlayed result
    when explicitly invoked)."""
    spokes = agent.load_spokes()
    inv, rts = agent.apply_scenario(scenario, spokes, agent.load_inventory(), agent.load_routes())
    return agent.baseline_scores(spokes, inv, rts)


@app.get("/api/brief")
def get_brief(scenario: str = Query("baseline"), live: bool = Query(False)):
    """Step 2 — cache-first hero brief. ?live=true forces a fresh LLM call."""
    if not live:
        cached = agent.load_cached_briefs().get(scenario)
        if cached and cached.get("brief"):
            return cached
    out = agent.run_pipeline(scenario, hero=True)
    return {
        "scenario": scenario,
        "label": agent.SCENARIOS.get(scenario, {}).get("label", scenario),
        "constraint": agent.SCENARIOS.get(scenario, {}).get("constraint", ""),
        "brief": out["brief"],
        "scores": out["scores"],
        "generated_at": out["generated_at"],
        "source": "live",
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend.app:app", host="0.0.0.0", port=8015, reload=False)
