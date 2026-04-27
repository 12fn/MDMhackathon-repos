# WILDFIRE — installation wildfire predictor + auto-MASCAL comms
# Part of the MDM 2026 Hackathon Templates (https://github.com/12fn/MDMhackathon-repos)
# MIT licensed. Built on GAI (Government Acquisitions, Inc.) + Kamiwaza (https://www.kamiwaza.ai/).
"""WILDFIRE FastAPI backend — port 8013.

Endpoints:
  GET  /health                          liveness
  GET  /api/installations               5 installation polygons + inventory
  GET  /api/fires                       fire pixels (optionally filter ?step=N)
  GET  /api/wind                        wind grid (CSV-derived JSON)
  GET  /api/timeline                    13-step burn-growth timeline
  GET  /api/threats?step=N              installation threat blocks at step N
  POST /api/comms/{installation_id}     hero call: 4-channel MASCAL package
"""
from __future__ import annotations

import csv
import json
import os
import sys
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# Import shared client
ROOT = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(ROOT))

from shared.kamiwaza_client import chat_json, PRIMARY_MODEL  # noqa: E402

# Local imports — both relative-to-src and absolute work depending on launcher
try:
    from src.risk import installation_threats, alert_band, haversine_mi
    from src.comms import generate_comms_package, quick_wind_summary, HERO_MODEL
except ImportError:  # uvicorn launched from inside src/
    from risk import installation_threats, alert_band, haversine_mi  # type: ignore
    from comms import generate_comms_package, quick_wind_summary, HERO_MODEL  # type: ignore

DATA = Path(__file__).resolve().parent.parent / "data"

app = FastAPI(title="WILDFIRE", version="1.0.0")
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


def _load_wind() -> list[dict]:
    if "wind" not in _CACHE:
        rows = []
        with (DATA / "wind_grid.csv").open() as f:
            for r in csv.DictReader(f):
                rows.append({
                    "latitude": float(r["latitude"]),
                    "longitude": float(r["longitude"]),
                    "u_mps": float(r["u_mps"]),
                    "v_mps": float(r["v_mps"]),
                    "speed_mps": float(r["speed_mps"]),
                    "from_dir_deg": float(r["from_dir_deg"]),
                    "valid_at": r["valid_at"],
                    "label": r["label"],
                })
        _CACHE["wind"] = rows
    return _CACHE["wind"]


def _visible_at(step: int | None) -> set[str] | None:
    if step is None:
        return None
    timeline = _load_json("timeline.json")
    if step < 0 or step >= len(timeline):
        raise HTTPException(400, f"step out of range 0..{len(timeline)-1}")
    return set(timeline[step]["fire_ids"])


# ---------------------------------------------------------------------------
@app.get("/health")
def health():
    return {
        "ok": True,
        "service": "WILDFIRE",
        "primary_model": PRIMARY_MODEL,
        "hero_model": HERO_MODEL,
        "kamiwaza_endpoint": os.getenv("KAMIWAZA_BASE_URL") or "kamiwaza-default",
        "n_installations": len(_load_json("installations.json")),
        "n_fire_pixels": len(_load_json("fire_pixels.json")),
        "n_wind_points": len(_load_wind()),
        "n_timeline_steps": len(_load_json("timeline.json")),
    }


@app.get("/api/installations")
def installations():
    return _load_json("installations.json")


@app.get("/api/fires")
def fires(step: int | None = None):
    fps = _load_json("fire_pixels.json")
    vis = _visible_at(step)
    if vis is None:
        return fps
    return [f for f in fps if f["id"] in vis]


@app.get("/api/wind")
def wind():
    return _load_wind()


@app.get("/api/timeline")
def timeline():
    return _load_json("timeline.json")


@app.get("/api/threats")
def threats(step: int | None = None):
    insts = _load_json("installations.json")
    fires_all = _load_json("fire_pixels.json")
    vis = _visible_at(step)
    return installation_threats(insts, fires_all, _load_wind(), visible_ids=vis)


# ---------------------------------------------------------------------------
class CommsRequest(BaseModel):
    step: int | None = None
    use_hero_model: bool = True


@app.post("/api/comms/{installation_id}")
def comms(installation_id: str, req: CommsRequest | None = None):
    """Hero AI call — multi-recipient comms package generator.

    Computes the threat block for the named installation at the given timeline
    step, then makes ONE structured-output JSON-mode LLM call that produces
    all four channel drafts (email, banner, SMS, evac brief).
    """
    req = req or CommsRequest()
    insts = _load_json("installations.json")
    inst = next((i for i in insts if i["id"] == installation_id), None)
    if not inst:
        raise HTTPException(404, f"installation {installation_id} not found")

    fires_all = _load_json("fire_pixels.json")
    vis = _visible_at(req.step)
    threats_all = installation_threats(insts, fires_all, _load_wind(), visible_ids=vis)
    block = next((t for t in threats_all if t["installation_id"] == installation_id), None)
    if not block:
        raise HTTPException(500, "threat block missing")

    wind_summary = quick_wind_summary(block)
    model = HERO_MODEL if req.use_hero_model else None
    pkg = generate_comms_package(chat_json, inst, block, wind_summary, model=model)
    return {
        "installation": {"id": inst["id"], "name": inst["name"], "centroid": inst["centroid"]},
        "step": req.step,
        "threat": block,
        "wind_summary": wind_summary,
        "comms_package": pkg,
    }


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("WILDFIRE_BACKEND_PORT", "8013"))
    uvicorn.run("src.api:app", host="0.0.0.0", port=port, reload=False)
