"""CARGO tool implementations — last-mile expeditionary delivery.

Each function is exposed to the LLM via OpenAI tool-calling. Pure tools:
they read the synthetic data files and return JSON-serializable dicts.

Tools:
  - list_squad_positions(filters)        — squad nodes with demand
  - compute_route(depot, stops, vehicle, terrain) — distance / time / fuel
  - check_threat_overlay(route)          — risk windows along the route
  - compare_options(plans)               — rank candidate plans
"""
from __future__ import annotations

import json
import math
from functools import lru_cache
from pathlib import Path
from typing import Any

import pandas as pd

DATA_DIR = Path(__file__).resolve().parents[1] / "data"


# ---------------------------------------------------------------------------
# Cached data loaders
# ---------------------------------------------------------------------------
@lru_cache(maxsize=1)
def load_depots() -> list[dict]:
    return json.loads((DATA_DIR / "depots.json").read_text())


@lru_cache(maxsize=1)
def load_squads() -> list[dict]:
    return json.loads((DATA_DIR / "squads.json").read_text())


@lru_cache(maxsize=1)
def load_vehicles() -> pd.DataFrame:
    return pd.read_csv(DATA_DIR / "vehicles.csv")


@lru_cache(maxsize=1)
def load_threat_zones() -> list[dict]:
    return json.loads((DATA_DIR / "threat_zones.json").read_text())


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _haversine_km(a: dict, b: dict) -> float:
    R_km = 6371.0
    p1, p2 = math.radians(a["lat"]), math.radians(b["lat"])
    dp = math.radians(b["lat"] - a["lat"])
    dl = math.radians(b["lon"] - a["lon"])
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * R_km * math.asin(math.sqrt(h))


def _resolve_squad(query: str) -> dict | None:
    if not query:
        return None
    q = query.strip().upper()
    for s in load_squads():
        if s["id"] == q or s["callsign"] == q:
            return s
    # substring
    for s in load_squads():
        if q in s["callsign"]:
            return s
    return None


def _resolve_depot(query: str | None) -> dict:
    depots = load_depots()
    if not query:
        return depots[0]
    q = query.strip().upper()
    for d in depots:
        if d["id"].upper() == q or d["name"].upper() == q:
            return d
    return depots[0]


def _resolve_vehicle(query: str) -> dict | None:
    df = load_vehicles()
    q = query.strip().upper()
    for _, row in df.iterrows():
        if row["vehicle_id"].upper() == q or row["class"].upper() == q:
            return row.to_dict()
    # substring on long_name
    for _, row in df.iterrows():
        if q in str(row["long_name"]).upper():
            return row.to_dict()
    return None


def _segment_intersects_zone(a: dict, b: dict, zone: dict) -> bool:
    """Cheap bbox intersection: does any of the segment's lat/lon lie in
    the zone bbox? (Good enough for the demo overlay — we sample 6 points
    along the segment.)
    """
    for t in [0.0, 0.2, 0.4, 0.6, 0.8, 1.0]:
        plat = a["lat"] + (b["lat"] - a["lat"]) * t
        plon = a["lon"] + (b["lon"] - a["lon"]) * t
        if (zone["lat_min"] <= plat <= zone["lat_max"]
                and zone["lon_min"] <= plon <= zone["lon_max"]):
            return True
    return False


# Severity weights for risk scoring
THREAT_WEIGHT = {"HIGH": 0.5, "MEDIUM": 0.3, "LOW": 0.05}
# A modifier: "IED_CLEARED" actually *reduces* risk (it's a cleared corridor)
THREAT_TYPE_MOD = {"IED_CLEARED": -0.4, "UAS": +0.0, "SNIPER": +0.0}


# ---------------------------------------------------------------------------
# TOOL: list_squad_positions
# ---------------------------------------------------------------------------
def list_squad_positions(
    priority: str | None = None,
    terrain: str | None = None,
    min_demand_lb: int | None = None,
    callsign: str | None = None,
    limit: int = 20,
) -> dict[str, Any]:
    """Return squad nodes (with demand) matching filters."""
    squads = load_squads()
    out = []
    for s in squads:
        if priority and s["priority"].upper() != priority.upper():
            continue
        if terrain and s["terrain"].lower() != terrain.lower():
            continue
        if min_demand_lb and s["demand_total_lb"] < int(min_demand_lb):
            continue
        if callsign and callsign.upper() not in s["callsign"]:
            continue
        out.append(s)
    out = out[: int(limit)]
    return {
        "matched": len(out),
        "filters": {
            "priority": priority, "terrain": terrain,
            "min_demand_lb": min_demand_lb, "callsign": callsign,
        },
        "squads": out,
        "total_demand_lb": sum(s["demand_total_lb"] for s in out),
    }


# ---------------------------------------------------------------------------
# TOOL: compute_route
# ---------------------------------------------------------------------------
def compute_route(
    depot: str | None = None,
    stops: list[str] | None = None,
    vehicle: str = "MTVR",
    terrain: str = "mixed",
) -> dict[str, Any]:
    """Compute a depot -> stops -> depot route for a given vehicle.
    Returns ordered legs with distance, time, fuel.
    """
    if not stops:
        return {"error": "Must provide at least one stop callsign."}
    depot_obj = _resolve_depot(depot)
    veh = _resolve_vehicle(vehicle)
    if veh is None:
        return {"error": f"Unknown vehicle class: {vehicle}"}

    resolved_stops = []
    for s in stops:
        sq = _resolve_squad(s)
        if sq is None:
            return {"error": f"Unknown squad: {s}"}
        resolved_stops.append(sq)

    # Greedy nearest-neighbor ordering for the demo (squads → depot return)
    path = [depot_obj]
    remaining = list(resolved_stops)
    cur = depot_obj
    while remaining:
        nxt = min(remaining, key=lambda x: _haversine_km(cur, x))
        path.append(nxt)
        remaining.remove(nxt)
        cur = nxt
    path.append(depot_obj)  # return-to-depot

    legs: list[dict] = []
    total_km = 0.0
    total_hr = 0.0
    total_gal = 0.0

    # Effective speed depends on terrain
    cruise = float(veh["cruise_kph"])
    offroad = float(veh["offroad_kph"])
    burn = float(veh["fuel_gal_hr"])
    terrain_speed = {
        "open":     cruise,
        "broken":   offroad,
        "wadi":     offroad * 0.85,
        "urban":    cruise * 0.7,
        "mixed":    (cruise + offroad) / 2,
    }
    for a, b in zip(path[:-1], path[1:]):
        leg_terrain = b.get("terrain", "mixed")
        speed = terrain_speed.get(leg_terrain, terrain_speed["mixed"])
        d_km = _haversine_km(a, b)
        # add 15% for terrain wiggle / tactical pauses
        d_km *= 1.15
        hr = d_km / max(speed, 1)
        gal = hr * burn
        legs.append({
            "from": a.get("callsign") or a.get("id"),
            "to":   b.get("callsign") or b.get("id"),
            "from_lat": a["lat"], "from_lon": a["lon"],
            "to_lat":   b["lat"], "to_lon":   b["lon"],
            "terrain":  leg_terrain,
            "distance_km": round(d_km, 2),
            "time_hr":     round(hr, 2),
            "fuel_gal":    round(gal, 2),
        })
        total_km += d_km
        total_hr += hr
        total_gal += gal

    return {
        "depot":   depot_obj["id"],
        "vehicle": veh["vehicle_id"],
        "vehicle_class": veh["class"],
        "vehicle_capacity_lb": int(veh["capacity_lb"]),
        "stops_count": len(resolved_stops),
        "stops_order": [p.get("callsign") or p.get("id") for p in path[1:-1]],
        "leg_count":   len(legs),
        "total_distance_km": round(total_km, 2),
        "total_time_hr":     round(total_hr, 2),
        "total_fuel_gal":    round(total_gal, 2),
        "legs": legs,
    }


# ---------------------------------------------------------------------------
# TOOL: check_threat_overlay
# ---------------------------------------------------------------------------
def check_threat_overlay(route: dict[str, Any]) -> dict[str, Any]:
    """Given a route (output of compute_route), find which threat zones
    intersect each leg + return an aggregate risk score (0-1)."""
    if not isinstance(route, dict) or "legs" not in route:
        return {"error": "route is missing 'legs' (call compute_route first)."}
    zones = load_threat_zones()
    findings = []
    risk_acc = 0.0
    for i, leg in enumerate(route["legs"]):
        a = {"lat": leg["from_lat"], "lon": leg["from_lon"]}
        b = {"lat": leg["to_lat"],   "lon": leg["to_lon"]}
        leg_hits = []
        leg_risk = 0.0
        for z in zones:
            if _segment_intersects_zone(a, b, z):
                w = THREAT_WEIGHT.get(z["severity"], 0.2)
                w += THREAT_TYPE_MOD.get(z["type"], 0.0)
                w = max(w, 0.0)
                leg_hits.append({
                    "zone_id": z["id"], "name": z["name"],
                    "type": z["type"], "severity": z["severity"],
                    "window_local": z["window_local"],
                    "guidance": z["guidance"],
                })
                leg_risk += w
        findings.append({
            "leg_index": i,
            "from": leg["from"], "to": leg["to"],
            "zone_hits": leg_hits,
            "leg_risk": round(min(leg_risk, 1.0), 2),
        })
        risk_acc += leg_risk
    overall = min(risk_acc / max(len(route["legs"]), 1), 1.0)
    # Surface highest-severity zones touched
    touched = {f["zone_hits"][0]["zone_id"] for f in findings if f["zone_hits"]}
    return {
        "route_distance_km": route.get("total_distance_km"),
        "leg_count": len(route["legs"]),
        "zones_touched": sorted(touched),
        "leg_findings": findings,
        "overall_risk_0_1": round(overall, 2),
    }


# ---------------------------------------------------------------------------
# TOOL: compare_options
# ---------------------------------------------------------------------------
def compare_options(
    plans: list[dict] | None = None,
    objective: str = "lowest_threat",
) -> dict[str, Any]:
    """Rank up to 4 candidate plans. Each plan is:
       {label, vehicle, stops:[callsigns]} OR a precomputed
       {label, route, threat} pair.

    If `plans` is empty, build a sensible default 3-option comparison:
       - MTVR full convoy (all 8)
       - JLTV armored fast push (priority + urgent only)
       - UGV unmanned last-mile (URGENT + PRIORITY only)
    """
    objective = (objective or "balanced").lower()
    squads = load_squads()
    all_callsigns = [s["callsign"] for s in squads]
    urgent = [s["callsign"] for s in squads if s["priority"] == "URGENT"]
    priority_high = [s["callsign"] for s in squads
                     if s["priority"] in ("URGENT", "PRIORITY")]

    if not plans:
        plans = [
            {"label": "MTVR Bulk Convoy (all 8 squads)",
             "vehicle": "MTVR", "stops": all_callsigns},
            {"label": "JLTV Fast Armored Push (urgent+priority)",
             "vehicle": "JLTV", "stops": priority_high},
            {"label": "UGV Unmanned Last-Mile (urgent only)",
             "vehicle": "UGV",  "stops": urgent or all_callsigns[:3]},
        ]

    enriched: list[dict] = []
    for p in plans:
        if "route" in p and "threat" in p:
            route = p["route"]
            threat = p["threat"]
        else:
            route = compute_route(
                depot=p.get("depot"),
                stops=p.get("stops") or [],
                vehicle=p.get("vehicle", "MTVR"),
                terrain=p.get("terrain", "mixed"),
            )
            if "error" in route:
                continue
            threat = check_threat_overlay(route)
        enriched.append({
            "label": p.get("label", f"{p.get('vehicle','?')}-plan"),
            "vehicle": route.get("vehicle_class") or p.get("vehicle"),
            "stops_count": route.get("stops_count"),
            "total_distance_km": route.get("total_distance_km"),
            "total_time_hr":     route.get("total_time_hr"),
            "total_fuel_gal":    route.get("total_fuel_gal"),
            "overall_risk_0_1":  threat.get("overall_risk_0_1"),
            "zones_touched":     threat.get("zones_touched"),
            "route":  route,
            "threat": threat,
        })

    if not enriched:
        return {"error": "No feasible plans could be built."}

    # Normalize for ranking (lower is better for time, fuel, risk)
    min_t  = min(e["total_time_hr"]    for e in enriched) or 0.1
    min_f  = min(e["total_fuel_gal"]   for e in enriched) or 0.1
    min_r  = min(e["overall_risk_0_1"] for e in enriched) or 0.01

    weights = {
        "lowest_threat":  (0.15, 0.15, 0.70),
        "fastest":        (0.70, 0.15, 0.15),
        "lowest_fuel":    (0.15, 0.70, 0.15),
        "balanced":       (0.34, 0.33, 0.33),
    }.get(objective, (0.34, 0.33, 0.33))

    for e in enriched:
        t_norm = min_t / max(e["total_time_hr"], 0.1)
        f_norm = min_f / max(e["total_fuel_gal"], 0.1)
        r_norm = min_r / max(e["overall_risk_0_1"], 0.01)
        e["score"] = round(
            weights[0] * t_norm + weights[1] * f_norm + weights[2] * r_norm, 3,
        )

    enriched.sort(key=lambda x: x["score"], reverse=True)
    enriched = enriched[:4]
    enriched[0]["recommended"] = True

    return {
        "objective": objective,
        "plan_count": len(enriched),
        "options": enriched,
    }


# ---------------------------------------------------------------------------
# Tool schemas (OpenAI function-calling spec)
# ---------------------------------------------------------------------------
TOOL_SCHEMAS: list[dict] = [
    {
        "type": "function",
        "function": {
            "name": "list_squad_positions",
            "description": (
                "List dispersed squad positions across the AOI with their "
                "Class I/V/VIII demand, water requirement, terrain, and "
                "priority. Use to scope which squads need resupply before "
                "planning a route."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "priority": {"type": "string",
                                 "enum": ["ROUTINE", "PRIORITY", "URGENT"]},
                    "terrain":  {"type": "string",
                                 "enum": ["open", "broken", "urban", "wadi"]},
                    "min_demand_lb": {"type": "integer", "minimum": 0},
                    "callsign":      {"type": "string",
                                      "description": "alpha..hotel"},
                    "limit":         {"type": "integer", "default": 20},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "compute_route",
            "description": (
                "Compute a depot → stops → depot route for a given vehicle "
                "class. Uses greedy nearest-neighbor ordering. Returns ordered "
                "legs with distance (km), time (hr), and fuel burn (gal)."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "depot":  {"type": "string",
                               "description": "Depot id (default FOB-RAVEN)."},
                    "stops":  {"type": "array",
                               "items": {"type": "string"},
                               "description": "Squad callsigns to visit."},
                    "vehicle": {"type": "string",
                                "enum": ["MTVR", "JLTV", "ARV", "UGV"],
                                "default": "MTVR"},
                    "terrain": {"type": "string",
                                "enum": ["open", "broken", "urban", "wadi", "mixed"],
                                "default": "mixed"},
                },
                "required": ["stops"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "check_threat_overlay",
            "description": (
                "Given a route (from compute_route), check which named threat "
                "zones (UAS, sniper, IED-cleared corridor) intersect each leg. "
                "Returns per-leg findings + an overall risk score (0-1)."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "route": {"type": "object",
                              "description": "Full output of compute_route "
                                             "(must contain 'legs')."},
                },
                "required": ["route"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "compare_options",
            "description": (
                "Rank candidate plans by the operator's objective "
                "('lowest_threat', 'fastest', 'lowest_fuel', 'balanced'). "
                "If `plans` is empty, builds 3 default options "
                "(MTVR bulk / JLTV fast / UGV unmanned)."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "plans": {
                        "type": "array",
                        "items": {"type": "object"},
                        "description": (
                            "Each plan: {label, vehicle, stops:[callsigns]} "
                            "— or pass empty/null to use defaults."
                        ),
                    },
                    "objective": {
                        "type": "string",
                        "enum": ["lowest_threat", "fastest",
                                 "lowest_fuel", "balanced"],
                        "default": "lowest_threat",
                    },
                },
            },
        },
    },
]

TOOL_REGISTRY = {
    "list_squad_positions": list_squad_positions,
    "compute_route":        compute_route,
    "check_threat_overlay": check_threat_overlay,
    "compare_options":      compare_options,
}
