# RIPTIDE — installation flood-risk + impact assessment
# Part of the MDM 2026 Hackathon Templates (https://github.com/12fn/MDMhackathon-repos)
# MIT licensed. Built on GAI (Government Acquisitions, Inc.) + Kamiwaza (https://www.kamiwaza.ai/).
"""RIPTIDE backend — FastAPI service for flood-risk + claims-cost forecasting.

Routes:
    GET  /health
    GET  /api/installations               — list reference USMC installations
    GET  /api/claims/aggregate            — aggregate historic claims for an installation+scenario
    POST /api/assess                      — narrative Operational Impact Assessment (LLM)
    POST /api/actions                     — structured recommended_actions[] (LLM JSON mode)
"""
from __future__ import annotations

import json
import math
import os
import sys
from pathlib import Path
from typing import Any

import pandas as pd
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# Make shared/ importable.
ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from shared.kamiwaza_client import chat, chat_json, BRAND  # noqa: E402

DATA_DIR = Path(__file__).resolve().parents[1] / "data"

app = FastAPI(title="RIPTIDE Backend", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------- Data load (cached on import) ----------

def _load() -> tuple[pd.DataFrame, list[dict]]:
    pq = DATA_DIR / "nfip_claims.parquet"
    inst = DATA_DIR / "installations.json"
    if not pq.exists() or not inst.exists():
        raise RuntimeError(
            f"Missing data files. Run: python {DATA_DIR.parent}/data/generate.py"
        )
    df = pd.read_parquet(pq)
    with inst.open() as f:
        installations = json.load(f)
    return df, installations


CLAIMS_DF, INSTALLATIONS = _load()
INSTALL_BY_ID = {i["id"]: i for i in INSTALLATIONS}


# ---------- Geo helpers ----------

def haversine_nm(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R_nm = 3440.065  # earth radius in nautical miles
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * R_nm * math.asin(math.sqrt(a))


# ---------- Aggregation ----------

SCENARIOS = {
    "baseline": {
        "label": "Baseline (climatology)",
        "severity_multiplier": 1.0,
        "structures_pct": 0.05,
        "downtime_days": 1,
    },
    "tropical_storm": {
        "label": "Tropical Storm",
        "severity_multiplier": 1.4,
        "structures_pct": 0.10,
        "downtime_days": 2,
    },
    "cat1": {
        "label": "Category 1 Hurricane",
        "severity_multiplier": 1.9,
        "structures_pct": 0.18,
        "downtime_days": 3,
    },
    "cat2": {
        "label": "Category 2 Hurricane",
        "severity_multiplier": 2.7,
        "structures_pct": 0.28,
        "downtime_days": 5,
    },
    "cat3": {
        "label": "Category 3 Hurricane",
        "severity_multiplier": 4.0,
        "structures_pct": 0.42,
        "downtime_days": 8,
    },
    "cat4": {
        "label": "Category 4 Hurricane",
        "severity_multiplier": 6.2,
        "structures_pct": 0.58,
        "downtime_days": 14,
    },
    "atmospheric_river": {
        "label": "Atmospheric River (CA)",
        "severity_multiplier": 1.6,
        "structures_pct": 0.12,
        "downtime_days": 3,
    },
    "monsoon_flash": {
        "label": "Monsoon Flash Flood (AZ)",
        "severity_multiplier": 1.3,
        "structures_pct": 0.08,
        "downtime_days": 2,
    },
}


def _aggregate(installation_id: str, scenario_id: str, radius_nm: float = 50.0) -> dict[str, Any]:
    if installation_id not in INSTALL_BY_ID:
        raise HTTPException(404, f"Unknown installation '{installation_id}'")
    if scenario_id not in SCENARIOS:
        raise HTTPException(400, f"Unknown scenario '{scenario_id}'")
    inst = INSTALL_BY_ID[installation_id]
    sc = SCENARIOS[scenario_id]

    df = CLAIMS_DF.copy()
    df["dist_nm"] = df.apply(
        lambda r: haversine_nm(inst["lat"], inst["lon"], r["latitude"], r["longitude"]),
        axis=1,
    )
    nearby = df[df["dist_nm"] <= radius_nm]
    if nearby.empty:
        # widen as fallback
        nearby = df[df["dist_nm"] <= radius_nm * 2]

    # By-year counts (for sparkline).
    by_year = nearby.groupby("yearOfLoss").size().reset_index(name="count")
    by_year = by_year.sort_values("yearOfLoss")

    # Avg paid per claim (historic baseline).
    avg_paid = (
        (nearby["amountPaidOnBuildingClaim"] + nearby["amountPaidOnContentsClaim"]).mean()
        if not nearby.empty
        else 12_000.0
    )
    # Project: number of structures impacted = installation footprint * scenario pct;
    # scaled cost = structures * avg_paid * severity_multiplier
    inv = inst["inventory"]
    total_structures = (
        inv.get("family_housing_units", 0)
        + inv.get("barracks", 0)
        + inv.get("motor_pools", 0) * 4
        + inv.get("aircraft_hangars", 0) * 3
        + inv.get("ammo_storage_bunkers", 0)
        + inv.get("critical_c2_nodes", 0) * 2
    )
    structures_at_risk = int(round(total_structures * sc["structures_pct"]))
    projected_claims_usd = float(structures_at_risk * avg_paid * sc["severity_multiplier"])
    days_to_mc = sc["downtime_days"] + (
        2 if inv.get("aircraft_hangars", 0) > 0 and "Hurricane" in sc["label"] else 0
    )

    # Heat-map points (lat/lon + paid) for the front-end map.
    heat = nearby.assign(
        paid=nearby["amountPaidOnBuildingClaim"] + nearby["amountPaidOnContentsClaim"]
    )[["latitude", "longitude", "paid", "yearOfLoss", "eventDesignation", "state"]].head(1500).to_dict("records")

    # Top states (for any leaderboard).
    state_counts = nearby["state"].value_counts().head(5).to_dict()

    return {
        "installation": inst,
        "scenario": {"id": scenario_id, **sc},
        "radius_nm": radius_nm,
        "claims_in_radius": int(len(nearby)),
        "historic_paid_usd": float(
            nearby["amountPaidOnBuildingClaim"].sum() + nearby["amountPaidOnContentsClaim"].sum()
        ),
        "avg_paid_per_claim_usd": float(avg_paid),
        "structures_at_risk": structures_at_risk,
        "projected_claims_usd": projected_claims_usd,
        "days_to_mission_capable": days_to_mc,
        "by_year": by_year.to_dict("records"),
        "state_counts": state_counts,
        "heat": heat,
    }


# ---------- LLM prompt construction ----------

ASSESS_SYSTEM = """You are a USMC LOGCOM senior installation-resilience analyst.
You write Operational Impact Assessments (OIA) for installation commanders.
Tone: confident, terse, actionable. 4 short paragraphs maximum.
Always reference dollar projections and mission-capable timelines using the numbers provided.
Anchor your assessment in the historical NFIP claim pattern around the installation.
End with one sentence that names the single most consequential pre-positioning action.
Never invent installations or storms not given in the input. Do not use markdown headers.
"""

ACTIONS_SYSTEM = """You are a USMC LOGCOM logistics planner.
Given an installation, scenario, and projected impact figures, output a STRICT JSON object with key "actions"
whose value is a list of EXACTLY 5 prioritized response actions.
Each action object MUST have these keys:
  priority      (int 1-5, 1=highest)
  action        (short imperative sentence, max 14 words)
  asset         (specific resource, e.g. "MEP-806B 60kW generator x4")
  lead_time_hrs (int)
  cost_estimate_usd (int)
  rationale     (one sentence tying back to the input numbers)
Order by priority. Do not add other top-level keys. Respond with ONLY the JSON.
"""


def _assess_user_prompt(agg: dict[str, Any]) -> str:
    inst = agg["installation"]
    sc = agg["scenario"]
    return f"""INSTALLATION
  Name: {inst['name']}  ({inst['state']})
  Personnel: {inst['personnel']:,}
  Inventory: {json.dumps(inst['inventory'])}
  History: {inst['notable_history']}

SCENARIO
  Type: {sc['label']}
  Severity multiplier vs climatology: {sc['severity_multiplier']:.1f}x

HISTORIC NFIP CLAIM PATTERN within {agg['radius_nm']:.0f} nm
  Claims on record: {agg['claims_in_radius']:,}
  Historic $ paid: ${agg['historic_paid_usd']:,.0f}
  Avg paid per claim: ${agg['avg_paid_per_claim_usd']:,.0f}
  Top affected states: {agg['state_counts']}

MODEL PROJECTION
  Structures at risk: {agg['structures_at_risk']:,}
  Projected claims dollars: ${agg['projected_claims_usd']:,.0f}
  Days to restore mission-capable status: {agg['days_to_mission_capable']}

Write the Operational Impact Assessment now."""


# ---------- Routes ----------

class AssessRequest(BaseModel):
    installation_id: str
    scenario_id: str
    radius_nm: float = 50.0


@app.get("/health")
def health() -> dict:
    return {"ok": True, "claims_loaded": int(len(CLAIMS_DF)), "installations": len(INSTALLATIONS), "brand": BRAND}


@app.get("/api/installations")
def list_installations() -> list[dict]:
    return INSTALLATIONS


@app.get("/api/scenarios")
def list_scenarios() -> dict:
    return SCENARIOS


@app.get("/api/claims/aggregate")
def claims_aggregate(installation: str, scenario: str = "cat3", radius_nm: float = 50.0) -> dict:
    return _aggregate(installation, scenario, radius_nm)


@app.post("/api/assess")
def assess(req: AssessRequest) -> dict:
    agg = _aggregate(req.installation_id, req.scenario_id, req.radius_nm)
    msgs = [
        {"role": "system", "content": ASSESS_SYSTEM},
        {"role": "user", "content": _assess_user_prompt(agg)},
    ]
    # Hero call — try un-mini'd 5.4 first per brief; wrapper falls back.
    narrative = chat(msgs, model=os.getenv("RIPTIDE_HERO_MODEL", "gpt-5.4"), temperature=0.5)
    return {"narrative": narrative, "aggregate": agg}


@app.post("/api/actions")
def actions(req: AssessRequest) -> dict:
    agg = _aggregate(req.installation_id, req.scenario_id, req.radius_nm)
    msgs = [
        {"role": "system", "content": ACTIONS_SYSTEM},
        {"role": "user", "content": _assess_user_prompt(agg)},
    ]
    try:
        out = chat_json(msgs, schema_hint='{"actions":[{priority, action, asset, lead_time_hrs, cost_estimate_usd, rationale}]}')
        if "actions" not in out:
            out = {"actions": out.get("recommended_actions", [])}
        return {"actions": out["actions"], "aggregate": agg}
    except Exception as e:  # noqa: BLE001
        # graceful fallback so demo never breaks
        return {
            "actions": [
                {"priority": 1, "action": "Pre-position 60 kW generators at C2 nodes",
                 "asset": "MEP-806B 60kW x6", "lead_time_hrs": 36,
                 "cost_estimate_usd": 90000,
                 "rationale": f"Fallback: LLM unavailable ({type(e).__name__})"},
            ],
            "aggregate": agg,
            "error": str(e),
        }


@app.get("/")
def root() -> dict:
    return {
        "service": "RIPTIDE backend",
        "tagline": "Forecast the flood before it floods readiness.",
        "routes": ["/health", "/api/installations", "/api/scenarios", "/api/claims/aggregate", "/api/assess", "/api/actions"],
    }
