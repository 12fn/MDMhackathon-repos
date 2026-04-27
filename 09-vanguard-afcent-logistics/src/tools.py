# VANGUARD — TMR automation with tool-calling agent loop
# Part of the MDM 2026 Hackathon Templates (https://github.com/12fn/MDMhackathon-repos)
# MIT licensed. Built on GAI (Government Acquisitions, Inc.) + Kamiwaza (https://www.kamiwaza.ai/).
"""VANGUARD tool implementations.

Each function is exposed to the LLM via OpenAI tool-calling. Tools are PURE —
they read from the in-memory pandas DataFrames and the routing graph and
return JSON-serializable dicts. The agent loop in `agent.py` dispatches
calls here based on the model's `tool_calls`.
"""
from __future__ import annotations

import heapq
import json
import math
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

import pandas as pd

DATA_DIR = Path(__file__).resolve().parents[1] / "data"

# ---------------------------------------------------------------------------
# Cached data loaders
# ---------------------------------------------------------------------------


@lru_cache(maxsize=1)
def load_bases() -> pd.DataFrame:
    return pd.read_csv(DATA_DIR / "bases.csv")


@lru_cache(maxsize=1)
def load_assets() -> pd.DataFrame:
    return pd.read_csv(DATA_DIR / "assets.csv")


@lru_cache(maxsize=1)
def load_graph() -> dict:
    return json.loads((DATA_DIR / "graph.json").read_text())


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

# Average JP-8 / DF-2 / marine bunker fuel cost approximations ($/lb)
FUEL_COST_PER_LB = {"air": 4.10, "sea": 0.95, "road": 1.55}

# Risk weights (dimensionless 0–1) factored into option scoring
MODE_RISK = {"air": 0.10, "road": 0.40, "sea": 0.20}

# Throughput overhead per leg (port handling, ramp, refuel) in hours
LEG_OVERHEAD_HR = {"air": 1.5, "sea": 12.0, "road": 2.0}


def _resolve_base_code(base_query: str) -> str | None:
    """Match user input against base code, name, or country (case-insensitive)."""
    if not base_query:
        return None
    bases = load_bases()
    q = base_query.strip().lower()
    for col in ("code", "name"):
        m = bases[bases[col].str.lower() == q]
        if not m.empty:
            return m.iloc[0]["code"]
    # substring on name
    m = bases[bases["name"].str.lower().str.contains(q, na=False)]
    if not m.empty:
        return m.iloc[0]["code"]
    # substring on country
    m = bases[bases["country"].str.lower().str.contains(q, na=False)]
    if not m.empty:
        return m.iloc[0]["code"]
    # substring on code
    m = bases[bases["code"].str.lower().str.contains(q, na=False)]
    if not m.empty:
        return m.iloc[0]["code"]
    return None


def _haversine_nm(a: dict, b: dict) -> float:
    R = 3440.065
    p1, p2 = math.radians(a["lat"]), math.radians(b["lat"])
    dp = math.radians(b["lat"] - a["lat"])
    dl = math.radians(b["lon"] - a["lon"])
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * R * math.asin(math.sqrt(h))


# ---------------------------------------------------------------------------
# TOOL: list_assets
# ---------------------------------------------------------------------------

def list_assets(
    theater: str | None = None,
    mode: str | None = None,
    near_base: str | None = None,
    min_pallets: int | None = None,
    readiness: str | None = None,
    limit: int = 25,
) -> dict[str, Any]:
    """Return matching transport assets."""
    df = load_assets().copy()
    if theater:
        df = df[df["theater"].str.upper() == theater.upper()]
    if mode:
        df = df[df["mode"].str.lower() == mode.lower()]
    if readiness:
        df = df[df["readiness"].str.upper() == readiness.upper()]
    if min_pallets:
        df = df[df["cap_pallets"] >= int(min_pallets)]
    if near_base:
        code = _resolve_base_code(near_base)
        if code:
            df = df[df["current_base"] == code]
    total = len(df)
    rows = df.head(int(limit)).to_dict(orient="records")
    return {
        "matched": total,
        "returned": len(rows),
        "filters": {
            "theater": theater, "mode": mode, "near_base": near_base,
            "min_pallets": min_pallets, "readiness": readiness,
        },
        "assets": rows,
    }


# ---------------------------------------------------------------------------
# TOOL: compute_route
# ---------------------------------------------------------------------------

def _shortest_path(origin: str, dest: str, allowed_modes: set[str]) -> list[dict]:
    """Dijkstra shortest path on filtered graph. Returns list of edge dicts."""
    g = load_graph()
    if origin not in g["adj"] or dest not in g["adj"]:
        return []
    dist = {origin: 0.0}
    prev: dict[str, tuple[str, dict]] = {}
    pq: list[tuple[float, str]] = [(0.0, origin)]
    while pq:
        d, u = heapq.heappop(pq)
        if u == dest:
            break
        if d > dist.get(u, float("inf")):
            continue
        for edge in g["adj"].get(u, []):
            if edge["mode"] not in allowed_modes:
                continue
            v = edge["to"]
            nd = d + edge["distance_nm"]
            if nd < dist.get(v, float("inf")):
                dist[v] = nd
                prev[v] = (u, edge)
                heapq.heappush(pq, (nd, v))
    if dest not in prev and origin != dest:
        return []
    legs: list[dict] = []
    cur = dest
    while cur != origin:
        if cur not in prev:
            return []
        u, edge = prev[cur]
        legs.append({"from": u, "to": edge["to"], "mode": edge["mode"],
                     "distance_nm": edge["distance_nm"]})
        cur = u
    legs.reverse()
    return legs


def compute_route(
    origin: str,
    destination: str,
    mode: str = "any",
    pallets: int = 0,
) -> dict[str, Any]:
    """Compute shortest feasible route between two bases for the given mode."""
    o_code = _resolve_base_code(origin)
    d_code = _resolve_base_code(destination)
    if not o_code or not d_code:
        return {"error": f"Could not resolve bases (origin={origin}, destination={destination})"}
    if o_code == d_code:
        return {"error": "Origin and destination are the same base."}

    bases = {b["code"]: b for b in load_bases().to_dict(orient="records")}

    mode_sets: dict[str, set[str]] = {
        "air":   {"air"},
        "sea":   {"sea"},
        "land":  {"road"},
        "road":  {"road"},
        "any":   {"air", "sea", "road"},
        "intermodal": {"air", "sea", "road"},
    }
    allowed = mode_sets.get(mode.lower(), {"air", "sea", "road"})

    legs = _shortest_path(o_code, d_code, allowed)
    if not legs:
        # try fallback to all modes
        legs = _shortest_path(o_code, d_code, {"air", "sea", "road"})
        if not legs:
            return {"error": f"No route found between {o_code} and {d_code}."}

    enriched = []
    total_nm = 0.0
    for leg in legs:
        a, b = bases[leg["from"]], bases[leg["to"]]
        leg_out = {
            **leg,
            "from_name": a["name"], "to_name": b["name"],
            "from_lat": a["lat"], "from_lon": a["lon"],
            "to_lat": b["lat"], "to_lon": b["lon"],
        }
        enriched.append(leg_out)
        total_nm += leg["distance_nm"]

    modes_used = sorted({leg["mode"] for leg in legs})
    return {
        "origin": o_code, "destination": d_code,
        "origin_name": bases[o_code]["name"],
        "destination_name": bases[d_code]["name"],
        "mode_requested": mode,
        "modes_used": modes_used,
        "leg_count": len(legs),
        "total_distance_nm": round(total_nm, 1),
        "legs": enriched,
        "pallets": pallets,
    }


# ---------------------------------------------------------------------------
# TOOL: check_feasibility
# ---------------------------------------------------------------------------

def check_feasibility(
    asset_class: str,
    pallets: int,
    deadline_hours: float,
    route: dict[str, Any],
) -> dict[str, Any]:
    """Validate one asset class against pallet count + deadline on a given route."""
    if "legs" not in route or not route["legs"]:
        return {"error": "Route has no legs."}
    assets = load_assets()
    matches = assets[assets["class"].str.lower() == asset_class.lower()]
    if matches.empty:
        # fuzzy substring
        matches = assets[assets["class"].str.lower().str.contains(
            asset_class.lower().split()[0], na=False)]
    if matches.empty:
        return {"error": f"Unknown asset class: {asset_class}"}
    proto = matches.iloc[0]
    cap = int(proto["cap_pallets"])
    cruise = float(proto["cruise_kn"])
    burn_lb_hr = float(proto["fuel_lb_hr"])
    mode_for_class = str(proto["mode"])

    # Filter route legs to those compatible with this asset's mode (air assets fly air legs etc.)
    compatible_legs = [l for l in route["legs"] if
                       (mode_for_class == "land" and l["mode"] == "road") or
                       (mode_for_class != "land" and l["mode"] == mode_for_class)]
    intermodal = len(compatible_legs) != len(route["legs"])

    sorties = math.ceil(pallets / cap) if cap else 999
    total_nm = sum(l["distance_nm"] for l in route["legs"])
    flight_hours = total_nm / cruise if cruise else 0.0
    overhead_hr = sum(LEG_OVERHEAD_HR.get(l["mode"], 2.0) for l in route["legs"])
    # serial sorties model: each sortie repeats the route
    total_hours = sorties * (flight_hours + overhead_hr)
    feasible_time = total_hours <= deadline_hours

    fuel_lb = sorties * flight_hours * burn_lb_hr
    avg_cost_per_lb = sum(FUEL_COST_PER_LB.get(l["mode"], 1.5)
                          for l in route["legs"]) / max(1, len(route["legs"]))
    fuel_cost_usd = fuel_lb * avg_cost_per_lb

    risk = sum(MODE_RISK.get(l["mode"], 0.3) for l in route["legs"]) / len(route["legs"])
    return {
        "asset_class": str(proto["class"]),
        "asset_mode": mode_for_class,
        "cap_pallets_per_sortie": cap,
        "sorties_required": sorties,
        "intermodal_route": intermodal,
        "single_leg_hours": round(flight_hours, 2),
        "overhead_hours": round(overhead_hr, 2),
        "total_hours": round(total_hours, 2),
        "deadline_hours": deadline_hours,
        "feasible_time": feasible_time,
        "fuel_lb": round(fuel_lb, 0),
        "fuel_cost_usd": round(fuel_cost_usd, 0),
        "risk_score_0_1": round(risk, 2),
    }


# ---------------------------------------------------------------------------
# TOOL: compare_options
# ---------------------------------------------------------------------------

def compare_options(
    origin: str,
    destination: str,
    pallets: int,
    deadline_hours: float,
    objective: str = "balanced",
) -> dict[str, Any]:
    """Build 3 candidate options (air, intermodal, sea/land) and rank them."""
    options: list[dict] = []
    candidates = [
        ("Air-Direct (C-17)",   "air",  "C-17 Globemaster III"),
        ("Tactical Air (C-130J)", "air", "C-130J Super Hercules"),
        ("Sealift (T-AKE)",     "sea",  "T-AKE Lewis-class Dry Cargo"),
        ("Ground Convoy (M1083)", "land", "M1083 MTV Convoy (8x)"),
    ]
    seen_signatures = set()
    for label, mode, klass in candidates:
        route = compute_route(origin, destination, mode=mode, pallets=pallets)
        if "error" in route:
            continue
        feas = check_feasibility(klass, pallets, deadline_hours, route)
        if "error" in feas:
            continue
        sig = (label, route["total_distance_nm"], feas["sorties_required"])
        if sig in seen_signatures:
            continue
        seen_signatures.add(sig)
        options.append({
            "label": label,
            "asset_class": klass,
            "mode_family": mode,
            "route": {"origin": route["origin"], "destination": route["destination"],
                      "total_distance_nm": route["total_distance_nm"],
                      "leg_count": route["leg_count"],
                      "modes_used": route["modes_used"],
                      "legs": route["legs"]},
            "feasibility": feas,
        })

    # Score each option
    obj = objective.lower()
    for o in options[:3] if False else options:
        f = o["feasibility"]
        time_score = 1.0 if f["feasible_time"] else 0.4
        # normalize against best
        o["raw"] = {
            "hours": f["total_hours"],
            "fuel_usd": f["fuel_cost_usd"],
            "risk": f["risk_score_0_1"],
            "time_ok": f["feasible_time"],
        }
        _ = time_score  # keep linter quiet
    if not options:
        return {"error": "No feasible options could be computed."}

    min_hours = min(o["raw"]["hours"] for o in options) or 1
    min_cost = min(o["raw"]["fuel_usd"] for o in options) or 1
    min_risk = min(o["raw"]["risk"] for o in options) or 0.01

    # weighting
    w = {
        "fastest":  (0.70, 0.10, 0.20),
        "cheapest": (0.10, 0.70, 0.20),
        "safest":   (0.15, 0.15, 0.70),
        "balanced": (0.40, 0.30, 0.30),
        "lowest fuel burn": (0.15, 0.65, 0.20),
        "lowest_fuel": (0.15, 0.65, 0.20),
    }.get(obj, (0.40, 0.30, 0.30))

    for o in options:
        r = o["raw"]
        # lower-is-better → invert ratio
        time_norm = min_hours / max(r["hours"], 0.1)
        cost_norm = min_cost / max(r["fuel_usd"], 1)
        risk_norm = min_risk / max(r["risk"], 0.01)
        score = w[0] * time_norm + w[1] * cost_norm + w[2] * risk_norm
        # Penalize infeasible-time options
        if not r["time_ok"]:
            score *= 0.5
        o["score"] = round(score, 3)

    options.sort(key=lambda x: x["score"], reverse=True)
    options = options[:3]
    if options:
        options[0]["recommended"] = True

    return {
        "origin": origin, "destination": destination,
        "pallets": pallets, "deadline_hours": deadline_hours,
        "objective": objective,
        "options": options,
    }


# ---------------------------------------------------------------------------
# Tool schema for OpenAI function-calling
# ---------------------------------------------------------------------------

TOOL_SCHEMAS: list[dict] = [
    {
        "type": "function",
        "function": {
            "name": "list_assets",
            "description": (
                "List USMC/joint transport assets matching filters. Use to discover "
                "what aircraft, ships, or convoys are available in a theater or "
                "near a base before planning a route."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "theater": {"type": "string", "description": "e.g. CENTCOM"},
                    "mode": {"type": "string", "enum": ["air", "sea", "land"]},
                    "near_base": {"type": "string",
                                  "description": "Base code or name (e.g. ARIFJAN, Al Udeid)"},
                    "min_pallets": {"type": "integer", "minimum": 1},
                    "readiness": {"type": "string", "enum": ["FMC", "PMC", "NMC"]},
                    "limit": {"type": "integer", "default": 25, "maximum": 200},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "compute_route",
            "description": (
                "Compute the shortest feasible routing graph path between two bases "
                "for a given mode (air, sea, land, intermodal/any). Returns ordered legs."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "origin": {"type": "string", "description": "Base code or name"},
                    "destination": {"type": "string", "description": "Base code or name"},
                    "mode": {"type": "string",
                             "enum": ["air", "sea", "land", "road", "any", "intermodal"],
                             "default": "any"},
                    "pallets": {"type": "integer", "minimum": 0, "default": 0},
                },
                "required": ["origin", "destination"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "check_feasibility",
            "description": (
                "Given a route (from compute_route) and an asset class, compute "
                "sorties required, total time, fuel burn, fuel cost, and risk."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "asset_class": {"type": "string",
                                    "description": "e.g. 'C-17 Globemaster III'"},
                    "pallets": {"type": "integer", "minimum": 1},
                    "deadline_hours": {"type": "number", "minimum": 1},
                    "route": {"type": "object",
                              "description": "Output of compute_route (must contain 'legs')."},
                },
                "required": ["asset_class", "pallets", "deadline_hours", "route"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "compare_options",
            "description": (
                "Build a 3-option comparison (air / intermodal / sea or ground) for a TMR. "
                "Ranks by the user's objective ('fastest', 'cheapest', 'lowest fuel burn', "
                "'safest', 'balanced'). Returns options with score + recommended flag."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "origin": {"type": "string"},
                    "destination": {"type": "string"},
                    "pallets": {"type": "integer", "minimum": 1},
                    "deadline_hours": {"type": "number", "minimum": 1},
                    "objective": {"type": "string",
                                  "enum": ["fastest", "cheapest", "safest", "balanced",
                                          "lowest fuel burn"],
                                  "default": "balanced"},
                },
                "required": ["origin", "destination", "pallets", "deadline_hours"],
            },
        },
    },
]


TOOL_REGISTRY = {
    "list_assets": list_assets,
    "compute_route": compute_route,
    "check_feasibility": check_feasibility,
    "compare_options": compare_options,
}
