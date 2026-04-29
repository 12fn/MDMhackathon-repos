"""CONTESTED-LOG tools — 6 typed tools fired by the agent loop end-to-end.

Each function is exposed to the LLM via OpenAI tool-calling. Pure tools:
read the synthetic data files and return JSON-serializable dicts.

Tools:
  1. route_conus(origin, poe, weight_class)            -> CONUS rail/road/water leg
  2. check_port_capacity(port_id, pallets)             -> MSI WPI berth check
  3. forecast_pirate_risk(from_port, to_port)          -> pirate KDE overlay
  4. check_supply_chain_disruption(corridor, days)     -> 60-day events feed
  5. compute_last_mile(forward_port, squad_callsigns)  -> LaDe + GCSS-MC
  6. compare_options(origin, dest, pallets, deadline)  -> rank 3 routes
"""
from __future__ import annotations

import heapq
import json
import math
from functools import lru_cache
from pathlib import Path
from typing import Any

import pandas as pd

from .kde import lane_risk, hotspots, basin_lookup_risk

DATA_DIR = Path(__file__).resolve().parents[1] / "data"


# ---------------------------------------------------------------------------
# Cached loaders
# ---------------------------------------------------------------------------
@lru_cache(maxsize=1)
def load_bts_nodes() -> list[dict]:
    return pd.read_csv(DATA_DIR / "bts_nodes.csv").to_dict(orient="records")


@lru_cache(maxsize=1)
def load_bts_edges() -> list[dict]:
    return pd.read_csv(DATA_DIR / "bts_edges.csv").to_dict(orient="records")


@lru_cache(maxsize=1)
def load_ports() -> list[dict]:
    return json.loads((DATA_DIR / "ports.json").read_text())


@lru_cache(maxsize=1)
def load_lanes() -> list[dict]:
    return json.loads((DATA_DIR / "ais_lanes.json").read_text())


@lru_cache(maxsize=1)
def load_squads() -> list[dict]:
    return json.loads((DATA_DIR / "squads.json").read_text())


@lru_cache(maxsize=1)
def load_depot_stocks() -> dict:
    return json.loads((DATA_DIR / "depot_stocks.json").read_text())


@lru_cache(maxsize=1)
def load_disruptions() -> list[dict]:
    return json.loads((DATA_DIR / "sc_disruptions.json").read_text())


def _resolve_node(query: str) -> dict | None:
    if not query:
        return None
    q = query.strip().upper()
    for n in load_bts_nodes():
        if n["id"].upper() == q or q in n["name"].upper():
            return n
    return None


def _resolve_port(query: str) -> dict | None:
    if not query:
        return None
    q = query.strip().upper()
    for p in load_ports():
        if p["id"].upper() == q or q in p["name"].upper():
            return p
    return None


def _haversine_nm(a: dict, b: dict) -> float:
    R = 3440.065
    p1, p2 = math.radians(a["lat"]), math.radians(b["lat"])
    dp = math.radians(b["lat"] - a["lat"])
    dl = math.radians(b["lon"] - a["lon"])
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * R * math.asin(math.sqrt(h))


# ---------------------------------------------------------------------------
# TOOL 1: route_conus  — BTS NTAD rail/road/water leg
# ---------------------------------------------------------------------------
def route_conus(
    origin: str,
    poe: str = "PORT-BMT",
    weight_class: str = "286k",
    min_clearance_in: int = 192,
) -> dict[str, Any]:
    """Compute CONUS leg from origin (depot) to a Port-of-Embarkation node
    via the BTS NTAD multimodal graph. Filters edges by weight_class and
    bridge_clearance_in. Returns ordered legs with mode + distance.
    """
    nodes_by_id = {n["id"]: n for n in load_bts_nodes()}
    o = _resolve_node(origin)
    # Map any port id back to a BTS node by name match
    if poe.startswith("PORT-"):
        # Find the matching BTS port node
        candidate = None
        for n in load_bts_nodes():
            if n["kind"] == "port":
                pn = n["id"]
                if (pn.endswith(poe.split("-")[-1])
                        or poe.split("-")[-1] in pn):
                    candidate = n
                    break
        if not candidate:
            # default to BMT-PORT
            candidate = nodes_by_id.get("BMT-PORT")
        d = candidate
    else:
        d = _resolve_node(poe)
    if not o or not d:
        return {"error": f"Could not resolve origin={origin} poe={poe}"}
    if o["id"] == d["id"]:
        return {"error": "Origin and POE are the same node"}

    # Build adjacency from edges, filtered by clearance + weight class
    adj: dict[str, list[dict]] = {n["id"]: [] for n in load_bts_nodes()}
    for e in load_bts_edges():
        if e["mode"] != "water":
            if int(e["bridge_clearance_in"]) < min_clearance_in:
                continue
            if weight_class == "286k" and e["weight_class"] not in ("286k", "HS-20"):
                continue
        adj[e["from"]].append(e)

    # Dijkstra by transit_hr
    dist = {o["id"]: 0.0}
    prev: dict[str, tuple[str, dict]] = {}
    pq = [(0.0, o["id"])]
    while pq:
        cost, u = heapq.heappop(pq)
        if u == d["id"]:
            break
        if cost > dist.get(u, float("inf")):
            continue
        for e in adj.get(u, []):
            v = e["to"]
            nd = cost + float(e["transit_hr"])
            if nd < dist.get(v, float("inf")):
                dist[v] = nd
                prev[v] = (u, e)
                heapq.heappush(pq, (nd, v))

    if d["id"] not in prev:
        return {"error": f"No CONUS path {o['id']} -> {d['id']} under weight_class={weight_class}"}

    legs: list[dict] = []
    cur = d["id"]
    while cur != o["id"]:
        u, e = prev[cur]
        a, b = nodes_by_id[u], nodes_by_id[e["to"]]
        legs.append({
            "from": u, "to": e["to"],
            "from_name": a["name"], "to_name": b["name"],
            "from_lat": float(a["lat"]), "from_lon": float(a["lon"]),
            "to_lat": float(b["lat"]),   "to_lon": float(b["lon"]),
            "mode": e["mode"], "weight_class": e["weight_class"],
            "bridge_clearance_in": int(e["bridge_clearance_in"]),
            "distance_km": float(e["distance_km"]),
            "transit_hr": float(e["transit_hr"]),
            "capacity_pallets_per_day": int(e["capacity_pallets_per_day"]),
        })
        cur = u
    legs.reverse()

    total_km = sum(l["distance_km"] for l in legs)
    total_hr = sum(l["transit_hr"] for l in legs)
    return {
        "origin": o["id"], "origin_name": o["name"],
        "poe": d["id"], "poe_name": d["name"],
        "weight_class": weight_class,
        "min_clearance_in": min_clearance_in,
        "leg_count": len(legs),
        "total_distance_km": round(total_km, 1),
        "total_transit_hr": round(total_hr, 1),
        "total_transit_days": round(total_hr / 24.0, 2),
        "modes_used": sorted(set(l["mode"] for l in legs)),
        "weight_class_check": "PASS",
        "bridge_clearance_check": "PASS",
        "legs": legs,
    }


# ---------------------------------------------------------------------------
# TOOL 2: check_port_capacity  — MSI WPI throughput & berth/LCAC check
# ---------------------------------------------------------------------------
def check_port_capacity(port_id: str, pallets: int = 200,
                        require_lcac: bool = False) -> dict[str, Any]:
    p = _resolve_port(port_id)
    if not p:
        return {"error": f"Port not found: {port_id}"}
    # 1 TEU ~ 12 pallets approx
    pallets_per_day = int(p["throughput_teu_per_day"]) * 12
    days_to_clear = pallets / max(pallets_per_day, 1)
    # Berth assignment heuristic — pick first available berth
    berth_id = f"B{(hash(p['id']) % p['berths']) + 1:02d}"
    feasible = pallets_per_day >= pallets and (not require_lcac or p["lcac_pad"])
    return {
        "port_id": p["id"], "port_name": p["name"], "country": p["country"],
        "lat": p["lat"], "lon": p["lon"],
        "throughput_teu_per_day": p["throughput_teu_per_day"],
        "pallets_per_day_capacity": pallets_per_day,
        "berths_total": p["berths"],
        "assigned_berth": berth_id,
        "lcac_pad_available": bool(p["lcac_pad"]),
        "lcac_pad_required": bool(require_lcac),
        "pallets_requested": pallets,
        "days_to_clear": round(days_to_clear, 2),
        "feasible": bool(feasible),
        "role": p["role"],
    }


# ---------------------------------------------------------------------------
# TOOL 3: forecast_pirate_risk  — pirate KDE overlay along a sealift segment
# ---------------------------------------------------------------------------
def forecast_pirate_risk(from_port: str, to_port: str) -> dict[str, Any]:
    a = _resolve_port(from_port)
    b = _resolve_port(to_port)
    if not a or not b:
        return {"error": f"Port resolution failed (from={from_port} to={to_port})"}
    # Try to find a matching AIS lane
    matched_lane = None
    for ln in load_lanes():
        if (ln["from_port"] == a["id"] and ln["to_port"] == b["id"]) or \
           (ln["from_port"] == b["id"] and ln["to_port"] == a["id"]):
            matched_lane = ln
            break
    basin = matched_lane["risk_basin"] if matched_lane else ""
    # Compute KDE risk along the great-circle segment, sample 12 pts
    risk = lane_risk(a["lat"], a["lon"], b["lat"], b["lon"], fallback_basin=basin)
    # Surface nearby hotspots (top-2 closest)
    hs = hotspots(top_k=6)
    midlat, midlon = (a["lat"] + b["lat"]) / 2, (a["lon"] + b["lon"]) / 2
    hs_sorted = sorted(hs, key=lambda h: (h["lat"] - midlat) ** 2 + (h["lon"] - midlon) ** 2)
    near = hs_sorted[:2]
    # Transit days from lane or great-circle estimate
    transit_days = float(matched_lane["transit_days"]) if matched_lane else \
        round(_haversine_nm(a, b) / 18.0 / 24.0, 2)
    verdict = "AVOID" if risk > 0.55 else ("CAUTION" if risk > 0.25 else "ACCEPTABLE")
    return {
        "from_port": a["id"], "to_port": b["id"],
        "from_name": a["name"], "to_name": b["name"],
        "from_lat": a["lat"], "from_lon": a["lon"],
        "to_lat": b["lat"], "to_lon": b["lon"],
        "matched_lane": matched_lane["id"] if matched_lane else None,
        "risk_basin": basin or "Open Pacific",
        "kde_risk_0_1": round(risk, 3),
        "verdict": verdict,
        "transit_days": transit_days,
        "nearby_hotspots": near,
    }


# ---------------------------------------------------------------------------
# TOOL 4: check_supply_chain_disruption  — 60-day events feed query
# ---------------------------------------------------------------------------
def check_supply_chain_disruption(corridor_keyword: str = "",
                                  active_only: bool = True,
                                  limit: int = 12) -> dict[str, Any]:
    events = load_disruptions()
    out = []
    kw = corridor_keyword.strip().lower()
    for ev in events:
        if active_only and not ev.get("active"):
            continue
        if kw and kw not in ev["location"].lower() and kw not in ev["narrative"].lower():
            continue
        out.append(ev)
    out = out[: int(limit)]
    severity_count = {"HIGH": 0, "MEDIUM": 0, "LOW": 0}
    for ev in out:
        severity_count[ev.get("severity", "LOW")] = severity_count.get(ev.get("severity"), 0) + 1
    return {
        "corridor_keyword": corridor_keyword, "active_only": active_only,
        "matched": len(out),
        "events": out,
        "severity_count": severity_count,
    }


# ---------------------------------------------------------------------------
# TOOL 5: compute_last_mile  — forward port -> dispersed squads
# ---------------------------------------------------------------------------
def compute_last_mile(forward_port: str = "PORT-GUM",
                      squad_callsigns: list[str] | None = None,
                      mode: str = "air"  # air | ground | ugv
                      ) -> dict[str, Any]:
    fp = _resolve_port(forward_port)
    if not fp:
        return {"error": f"Forward port not found: {forward_port}"}
    squads = load_squads()
    if squad_callsigns:
        cs_set = {c.upper() for c in squad_callsigns}
        squads = [s for s in squads if s["callsign"].upper() in cs_set]
    if not squads:
        return {"error": "No squads matched"}

    # Vehicle profile by mode
    profile = {
        "air":    {"speed_kn": 240, "cap_pallets": 6,  "name": "C-130J Super Hercules"},
        "ground": {"speed_kn": 35,  "cap_pallets": 14, "name": "MTVR Ground Convoy"},
        "ugv":    {"speed_kn": 18,  "cap_pallets": 4,  "name": "Autonomous Resupply UGV"},
    }.get(mode, {"speed_kn": 240, "cap_pallets": 6, "name": "C-130J Super Hercules"})

    # Path: forward port -> nearest-neighbor through squads
    path = [{"id": fp["id"], "name": fp["name"], "lat": fp["lat"], "lon": fp["lon"]}]
    rem = list(squads)
    cur = path[0]
    total_nm = 0.0
    legs = []
    while rem:
        nxt = min(rem, key=lambda x: _haversine_nm(cur, x))
        d_nm = _haversine_nm(cur, nxt)
        total_nm += d_nm
        legs.append({
            "from": cur.get("callsign") or cur["id"],
            "to": nxt["callsign"],
            "from_lat": cur["lat"], "from_lon": cur["lon"],
            "to_lat": nxt["lat"], "to_lon": nxt["lon"],
            "distance_nm": round(d_nm, 1),
            "transit_hr": round(d_nm / profile["speed_kn"], 2),
            "demand_lb": nxt["demand_total_lb"],
            "priority": nxt["priority"],
        })
        rem.remove(nxt)
        cur = nxt

    total_demand = sum(s["demand_total_lb"] for s in squads)
    sorties = math.ceil(len(squads) / max(profile["cap_pallets"] // 2, 1))
    total_hr = sum(l["transit_hr"] for l in legs)
    return {
        "forward_port": fp["id"], "forward_port_name": fp["name"],
        "vehicle": profile["name"], "mode": mode,
        "squads_count": len(squads),
        "total_distance_nm": round(total_nm, 1),
        "total_transit_hr": round(total_hr, 2),
        "sorties_required": sorties,
        "total_demand_lb": int(total_demand),
        "legs": legs,
    }


# ---------------------------------------------------------------------------
# TOOL 6: compare_options  — full end-to-end ranking
# ---------------------------------------------------------------------------
def compare_options(origin: str = "MCLB-ALB",
                    dest_squad: str = "ALPHA",
                    pallets: int = 200,
                    deadline_days: float = 14.0,
                    objective: str = "lowest_pirate_risk") -> dict[str, Any]:
    """Build 3 candidate end-to-end COA options and rank them.

    Each option is a tuple of (CONUS POE, sealift forward port, last-mile mode).
    """
    candidates = [
        {
            "label": "COA-1 Albany→Beaumont→Pearl→Guam→Itbayat",
            "poe": "PORT-BMT",
            "sealift": ["PORT-BMT", "PORT-PHL", "PORT-GUM"],
            "fwd": "PORT-GUM", "last_mode": "air",
        },
        {
            "label": "COA-2 Charleston→Panama→LAX→Guam→Itbayat",
            "poe": "PORT-CHS",
            "sealift": ["PORT-CHS", "PORT-LAX", "PORT-GUM"],
            "fwd": "PORT-GUM", "last_mode": "air",
        },
        {
            "label": "COA-3 Tacoma→Yokosuka→Okinawa→Itbayat",
            "poe": "PORT-TCM",
            "sealift": ["PORT-TCM", "PORT-YOK", "PORT-OKI"],
            "fwd": "PORT-OKI", "last_mode": "air",
        },
    ]

    enriched = []
    for c in candidates:
        # CONUS leg
        conus = route_conus(origin=origin, poe=c["poe"])
        if "error" in conus:
            continue
        # Port capacity at POE
        poe_cap = check_port_capacity(c["poe"], pallets)
        # Sealift legs + cumulative pirate risk
        sealift_segments = []
        risks = []
        sealift_days = 0.0
        for a, b in zip(c["sealift"][:-1], c["sealift"][1:]):
            seg = forecast_pirate_risk(a, b)
            sealift_segments.append(seg)
            if "error" not in seg:
                risks.append(seg["kde_risk_0_1"])
                sealift_days += float(seg["transit_days"])
        # Forward port
        fwd_cap = check_port_capacity(c["fwd"], pallets, require_lcac=True)
        # Last-mile push (all squads)
        last = compute_last_mile(c["fwd"], None, c["last_mode"])
        # Total days
        total_days = round(conus["total_transit_days"] + sealift_days + 1.5, 2)
        avg_risk = round(sum(risks) / len(risks), 3) if risks else 0.0
        feasible = total_days <= deadline_days and poe_cap.get("feasible", False) and fwd_cap.get("feasible", False)
        enriched.append({
            "label": c["label"],
            "poe": c["poe"], "fwd_port": c["fwd"], "last_mode": c["last_mode"],
            "conus_days": conus["total_transit_days"],
            "sealift_days": round(sealift_days, 2),
            "total_days": total_days,
            "deadline_days": deadline_days,
            "feasible_time": total_days <= deadline_days,
            "poe_feasible": poe_cap.get("feasible", False),
            "fwd_feasible": fwd_cap.get("feasible", False),
            "avg_pirate_risk_0_1": avg_risk,
            "feasible": feasible,
            "conus_legs": conus["legs"],
            "sealift_segments": sealift_segments,
            "last_mile_legs": last.get("legs", []) if "error" not in last else [],
            "poe_check": poe_cap, "fwd_check": fwd_cap,
        })

    if not enriched:
        return {"error": "No feasible COAs computed"}

    # Score: lower-is-better on risk + days
    min_d = min(e["total_days"] for e in enriched) or 1.0
    min_r = min(e["avg_pirate_risk_0_1"] for e in enriched) or 0.01
    weights = {
        "lowest_pirate_risk": (0.20, 0.20, 0.60),
        "fastest":            (0.70, 0.15, 0.15),
        "balanced":           (0.34, 0.33, 0.33),
    }.get(objective, (0.20, 0.20, 0.60))
    for e in enriched:
        d_norm = min_d / max(e["total_days"], 0.1)
        f_norm = 1.0 if e["feasible"] else 0.5
        r_norm = min_r / max(e["avg_pirate_risk_0_1"], 0.01)
        e["score"] = round(weights[0] * d_norm + weights[1] * f_norm + weights[2] * r_norm, 3)

    enriched.sort(key=lambda x: x["score"], reverse=True)
    enriched[0]["recommended"] = True
    return {
        "origin": origin, "dest_squad": dest_squad, "pallets": pallets,
        "deadline_days": deadline_days, "objective": objective,
        "options": enriched,
    }


# ---------------------------------------------------------------------------
# Tool schemas (OpenAI function-calling spec)
# ---------------------------------------------------------------------------
TOOL_SCHEMAS: list[dict] = [
    {
        "type": "function",
        "function": {
            "name": "route_conus",
            "description": (
                "Compute CONUS-leg routing from a depot origin to a CONUS "
                "Port-of-Embarkation via the BTS NTAD multimodal graph "
                "(rail/road/water). Filters by weight class and bridge "
                "clearance. Returns ordered legs with mode, distance, transit hours."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "origin": {"type": "string", "description": "BTS node id (e.g. MCLB-ALB)."},
                    "poe":    {"type": "string", "description": "POE node/port id (default PORT-BMT)."},
                    "weight_class": {"type": "string", "enum": ["286k", "HS-20"], "default": "286k"},
                    "min_clearance_in": {"type": "integer", "default": 192},
                },
                "required": ["origin"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "check_port_capacity",
            "description": (
                "Check throughput, berth count, and LCAC pad availability at "
                "a port (MSI WPI shape). Returns days-to-clear for the "
                "requested pallet load + assigned berth + feasibility verdict."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "port_id":      {"type": "string"},
                    "pallets":      {"type": "integer", "default": 200},
                    "require_lcac": {"type": "boolean", "default": False},
                },
                "required": ["port_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "forecast_pirate_risk",
            "description": (
                "Forecast pirate-attack risk along a sealift segment using a "
                "live 2-D Gaussian KDE on 3,000 ASAM-shape historical attacks. "
                "Returns 0-1 risk, named risk basin, transit days, nearby hotspots."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "from_port": {"type": "string"},
                    "to_port":   {"type": "string"},
                },
                "required": ["from_port", "to_port"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "check_supply_chain_disruption",
            "description": (
                "Query the rolling 60-day supply-chain disruption feed for "
                "active corridor events (NOTAMs, strikes, port congestion, "
                "missile threats). Filter by keyword."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "corridor_keyword": {"type": "string"},
                    "active_only": {"type": "boolean", "default": True},
                    "limit": {"type": "integer", "default": 12},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "compute_last_mile",
            "description": (
                "Compute the last-mile push from a forward Pacific port to "
                "dispersed 31st MEU squad positions (LaDe + GCSS-MC fused). "
                "Mode: air (C-130J), ground (MTVR), or ugv (autonomous)."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "forward_port": {"type": "string", "default": "PORT-GUM"},
                    "squad_callsigns": {"type": "array", "items": {"type": "string"}},
                    "mode": {"type": "string", "enum": ["air", "ground", "ugv"], "default": "air"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "compare_options",
            "description": (
                "Build a 3-COA end-to-end comparison "
                "(CONUS leg + sealift + forward port + last-mile) ranked by "
                "objective ('lowest_pirate_risk', 'fastest', 'balanced'). "
                "Returns scored options with feasibility flags + recommended."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "origin":        {"type": "string", "default": "MCLB-ALB"},
                    "dest_squad":    {"type": "string", "default": "ALPHA"},
                    "pallets":       {"type": "integer", "default": 200},
                    "deadline_days": {"type": "number",  "default": 14.0},
                    "objective":     {"type": "string",
                                      "enum": ["lowest_pirate_risk", "fastest", "balanced"],
                                      "default": "lowest_pirate_risk"},
                },
            },
        },
    },
]

TOOL_REGISTRY = {
    "route_conus": route_conus,
    "check_port_capacity": check_port_capacity,
    "forecast_pirate_risk": forecast_pirate_risk,
    "check_supply_chain_disruption": check_supply_chain_disruption,
    "compute_last_mile": compute_last_mile,
    "compare_options": compare_options,
}
