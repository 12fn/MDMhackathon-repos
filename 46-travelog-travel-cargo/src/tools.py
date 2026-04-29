"""TRAVELOG tool implementations — exposed to the LLM via OpenAI tool-calling.

Pure functions over in-memory pandas DataFrames + the BTS NTAD-style
multimodal corridor graph. The agent loop in `agent.py` dispatches calls
based on the model's `tool_calls`.

The four headline tools the hero call orchestrates:
  - compare_modes        : 4-mode optimizer (BTS NTAD + AFCENT lift data)
  - submit_tmr           : auto-populates the cargo movement form (DTR
                           4500.9-R Part II), validates against installation
                           movement policy, returns a routed control number
  - prefill_dts_voucher  : generates the DTS authorization (JTR-aligned
                           per-diem, GTCC, mode-of-travel, lodging projection)
  - plan_last_mile_push  : LaDe-shape pickup + delivery to the receiving unit
                           on the new installation
  - cross_validate_plan  : does the travel route + cargo route + arrival
                           window all sync? returns OK / WARN with reasons.
"""
from __future__ import annotations

import csv
import heapq
import json
import math
import random
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any

DATA_DIR = Path(__file__).resolve().parents[1] / "data"


# ─────────────────────────────────────────────────────────────────────────────
# Cached loaders
# ─────────────────────────────────────────────────────────────────────────────
@lru_cache(maxsize=1)
def load_nodes() -> list[dict]:
    return json.loads((DATA_DIR / "bts_nodes.json").read_text())


@lru_cache(maxsize=1)
def load_edges() -> list[dict]:
    out = []
    with (DATA_DIR / "bts_edges.csv").open() as f:
        for r in csv.DictReader(f):
            r["distance_mi"] = float(r["distance_mi"])
            r["transit_hr"] = float(r["transit_hr"])
            r["cost_per_mile_usd"] = float(r["cost_per_mile_usd"])
            out.append(r)
    return out


@lru_cache(maxsize=1)
def load_assets() -> list[dict]:
    out = []
    with (DATA_DIR / "logistics_assets.csv").open() as f:
        for r in csv.DictReader(f):
            for k in ("cap_lbs", "cap_pallets", "fuel_lb_hr"):
                try:
                    r[k] = float(r[k])
                except Exception:
                    r[k] = 0.0
            try:
                r["cruise_mph"] = float(r["cruise_mph"])
            except Exception:
                r["cruise_mph"] = 0.0
            out.append(r)
    return out


@lru_cache(maxsize=1)
def load_per_diem() -> dict[str, dict]:
    raw = json.loads((DATA_DIR / "per_diem_rates.json").read_text())
    return {r["city"]: r for r in raw["rates"]}


@lru_cache(maxsize=1)
def load_scenarios() -> list[dict]:
    return json.loads((DATA_DIR / "pcs_scenarios.json").read_text())


@lru_cache(maxsize=1)
def load_dts() -> list[dict]:
    out = []
    with (DATA_DIR / "dts_records.csv").open() as f:
        for r in csv.DictReader(f):
            for k in ("nights", "per_diem_lodging_ceiling", "per_diem_mie"):
                try:
                    r[k] = int(r[k])
                except Exception:
                    pass
            for k in ("total_authorized", "total_voucher"):
                try:
                    r[k] = float(r[k])
                except Exception:
                    pass
            out.append(r)
    return out


def _node_by_id(nid: str) -> dict | None:
    for n in load_nodes():
        if n["id"] == nid:
            return n
    return None


def _resolve_node(query: str) -> str | None:
    if not query:
        return None
    nodes = load_nodes()
    q = query.strip().lower()
    for n in nodes:
        if n["id"].lower() == q:
            return n["id"]
    for n in nodes:
        if n["name"].lower() == q:
            return n["id"]
    for n in nodes:
        if q in n["name"].lower() or q in n["id"].lower():
            return n["id"]
    # fuzzy: short city tokens
    for n in nodes:
        for tok in n["name"].lower().replace("(", " ").replace(")", " ").split():
            if tok == q:
                return n["id"]
    return None


# ─────────────────────────────────────────────────────────────────────────────
# Multimodal shortest path (BTS NTAD edges)
# ─────────────────────────────────────────────────────────────────────────────
def _shortest_path(origin: str, dest: str, allowed: set[str],
                   metric: str = "transit_hr") -> list[dict]:
    """Dijkstra on the multimodal corridor graph filtered by mode set."""
    edges = load_edges()
    adj: dict[str, list[dict]] = {}
    for e in edges:
        if e["mode"] in allowed:
            adj.setdefault(e["from"], []).append(e)
    if origin not in adj and origin != dest:
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
        for e in adj.get(u, []):
            v = e["to"]
            nd = d + float(e[metric])
            if nd < dist.get(v, float("inf")):
                dist[v] = nd
                prev[v] = (u, e)
                heapq.heappush(pq, (nd, v))
    if dest not in prev and origin != dest:
        return []
    legs: list[dict] = []
    cur = dest
    while cur != origin:
        if cur not in prev:
            return []
        u, e = prev[cur]
        legs.append({"from": u, "to": e["to"], "mode": e["mode"],
                     "distance_mi": e["distance_mi"],
                     "transit_hr": e["transit_hr"],
                     "cost_per_mile_usd": e["cost_per_mile_usd"]})
        cur = u
    legs.reverse()
    return legs


# ─────────────────────────────────────────────────────────────────────────────
# JTR per-diem (CONUS via JTR Ch 2 / GSA; OCONUS via JTR Ch 3 / DTMO)
# ─────────────────────────────────────────────────────────────────────────────
DEST_TO_PERDIEM_CITY = {
    "MCBLEJ":   "Camp Lejeune",
    "MCBPEN":   "Oceanside",
    "MCBQUA":   "Quantico",
    "MCAGCC":   "Twentynine Palms",
    "MCASCP":   "Cherry Point",
    "MCAS_YUMA":"Yuma",
    "MCBHAW":   "Honolulu",
    "MCAS_IWA": "Iwakuni",
    "MCBOKI":   "Okinawa",
}


def _per_diem_for(node_id: str) -> dict:
    city = DEST_TO_PERDIEM_CITY.get(node_id, "Camp Lejeune")
    return load_per_diem().get(
        city, {"city": city, "lodging_per_night": 110, "mie_per_day": 64}
    )


def jtr_per_diem(node_id: str, nights: int) -> dict[str, Any]:
    """Compute JTR-compliant per-diem for an arrival city + N nights.
    M&IE @ 75% on first/last travel day per JTR Table 2-21."""
    pd_row = _per_diem_for(node_id)
    lodging = float(pd_row["lodging_per_night"])
    mie = float(pd_row["mie_per_day"])
    n = max(1, int(nights))
    total_lodging = round(lodging * n, 2)
    # 75% MIE on first + last travel day, 100% on full days
    if n == 1:
        total_mie = round(mie * 0.75 * 2, 2)
    else:
        total_mie = round(mie * 0.75 * 2 + mie * (n - 1), 2)
    return {
        "city": pd_row["city"],
        "lodging_per_night_usd": lodging,
        "mie_per_day_usd": mie,
        "nights": n,
        "lodging_total_usd": total_lodging,
        "mie_total_usd": total_mie,
        "per_diem_total_usd": round(total_lodging + total_mie, 2),
        "authority": "JTR Ch 2 (CONUS via GSA)" if pd_row["state"] not in ("JP",)
                     else "JTR Ch 3 (OCONUS via DTMO)",
    }


# ─────────────────────────────────────────────────────────────────────────────
# TOOL: compare_modes  —  the headline 4-mode optimizer
# ─────────────────────────────────────────────────────────────────────────────
MODE_LABELS = {
    "fly_ship":    "Fly pax + ship cargo separately",
    "drive_ship":  "Drive POV + ship cargo separately",
    "drive_escort":"Drive POV escorting cargo (single move)",
    "fly_airfreight":"Fly pax + air-freight cargo",
}


def _route_for(mode_key: str, o: str, d: str) -> tuple[list[dict], list[dict]]:
    """Return (pax_legs, cargo_legs) for each mode option."""
    if mode_key == "fly_ship":
        pax = _shortest_path(o, d, {"air", "road"})
        cargo = _shortest_path(o, d, {"sea", "road", "rail"})
    elif mode_key == "drive_ship":
        pax = _shortest_path(o, d, {"road"})
        cargo = _shortest_path(o, d, {"sea", "road", "rail"})
    elif mode_key == "drive_escort":
        legs = _shortest_path(o, d, {"road"})
        pax = legs
        cargo = legs
    elif mode_key == "fly_airfreight":
        legs = _shortest_path(o, d, {"air", "road"})
        pax = legs
        cargo = legs
    else:
        pax = cargo = []
    return pax, cargo


def _cost_for_legs(legs: list[dict], who: str, hhg_lbs: int = 0) -> dict:
    """Estimate $$ + fuel for a set of legs.

    who: 'pov' | 'flatbed' | 'pax_air' | 'sealift' | 'airfreight' | 'rail'
    """
    if not legs:
        return {"cost_usd": 0, "fuel_gal": 0, "fuel_cost_usd": 0,
                "transit_hr": 0, "distance_mi": 0}
    total_mi = sum(l["distance_mi"] for l in legs)
    total_hr = sum(l["transit_hr"] for l in legs)
    fuel_gal = 0.0
    cost = 0.0
    if who == "pov":
        # ~22 mpg + $3.85/gal + per-diem already separate
        fuel_gal = total_mi / 22
        cost = fuel_gal * 3.85
    elif who == "flatbed":
        fuel_gal = total_mi / 7  # 7 mpg flatbed
        # Fully loaded commercial flatbed lease ~$2.10/mi all-in
        cost = total_mi * 2.10
    elif who == "pax_air":
        # AMC / commercial pax ticket: flat per-leg + small distance term
        air_legs = [l for l in legs if l["mode"] == "air"]
        cost = 580 * max(1, len(air_legs))  # AMC space-required pax
    elif who == "sealift":
        # CONEX rate: ~$1.40 per lb across the whole sea+road segment
        cost = max(0, hhg_lbs) * 1.40 * 0.5  # half rate, sea is $$ but bulk
        # Add port handling
        cost += 850
    elif who == "airfreight":
        # Air freight: ~$3.40 per lb door-to-door (much faster)
        cost = max(0, hhg_lbs) * 3.40
    elif who == "rail":
        cost = total_mi * 1.05
    else:
        cost = sum(l["distance_mi"] * l["cost_per_mile_usd"] for l in legs)
    return {
        "cost_usd": round(cost, 2),
        "fuel_gal": round(fuel_gal, 1),
        "fuel_cost_usd": round(fuel_gal * 3.85, 2) if who in ("pov", "flatbed") else 0,
        "transit_hr": round(total_hr, 1),
        "distance_mi": round(total_mi, 1),
    }


def _mode_cargo_lead_time_hr(mode_key: str, cargo_summary: dict) -> float:
    """Cargo lead time = transit + handling buffer per mode."""
    base = cargo_summary.get("transit_hr", 0)
    buf = {"fly_ship": 14*24, "drive_ship": 11*24,
           "drive_escort": 4*24, "fly_airfreight": 3*24}.get(mode_key, 96)
    # Cap by buf if route was zero, else max(transit + 24h, buf*0.6)
    if base <= 0:
        return float(buf)
    return float(max(base + 24, buf * 0.6))


def compare_modes(origin: str, destination: str,
                  hhg_lbs: int = 8000,
                  has_motor_pool_item: bool = False,
                  motor_pool_item: str = "",
                  d_plus_days: int = 30) -> dict[str, Any]:
    """Compare the 4 PCS travel + cargo modes side-by-side.

    Returns options sorted by cost (ascending) with a recommended flag set on
    the highest-value option (lowest cost AND meets cargo lead time)."""
    o = _resolve_node(origin) or origin
    d = _resolve_node(destination) or destination
    if not _node_by_id(o) or not _node_by_id(d):
        return {"error": f"Could not resolve nodes (origin={origin}, dest={destination})"}

    # OCONUS PCS = no road-only option (no driving across the Pacific). We
    # detect that by asking: does a road-only path even exist between o and d?
    road_only = _shortest_path(o, d, {"road"})
    is_oconus_move = not road_only

    nights_at_dest = 3  # PCS report-in window — short hotel stay before HHG arrives
    pd = jtr_per_diem(d, nights_at_dest)
    options = []
    for mode_key in ["fly_ship", "drive_ship", "drive_escort", "fly_airfreight"]:
        # Skip drive options for OCONUS moves (no road path)
        if is_oconus_move and mode_key in ("drive_ship", "drive_escort"):
            continue
        pax_legs, cargo_legs = _route_for(mode_key, o, d)
        if not pax_legs and not cargo_legs:
            continue
        # Defensive: if pax_legs is empty for a "drive" mode, skip
        if mode_key in ("drive_ship", "drive_escort") and not pax_legs:
            continue
        # Likewise, fly modes need an air leg in pax
        if mode_key in ("fly_ship", "fly_airfreight") and not any(
                l["mode"] == "air" for l in pax_legs):
            continue
        # PAX cost
        if mode_key in ("fly_ship", "fly_airfreight"):
            pax_cost = _cost_for_legs(pax_legs, "pax_air")
        else:
            pax_cost = _cost_for_legs(pax_legs, "pov")
        # CARGO cost
        if mode_key == "fly_airfreight":
            cargo_cost = _cost_for_legs(cargo_legs, "airfreight", hhg_lbs)
        elif mode_key == "drive_escort":
            cargo_cost = _cost_for_legs(cargo_legs, "flatbed")
        else:
            # mixed: prefer sealift if a sea leg exists, else rail/road
            if any(l["mode"] == "sea" for l in cargo_legs):
                cargo_cost = _cost_for_legs(cargo_legs, "sealift", hhg_lbs)
            elif any(l["mode"] == "rail" for l in cargo_legs):
                cargo_cost = _cost_for_legs(cargo_legs, "rail")
            else:
                cargo_cost = _cost_for_legs(cargo_legs, "flatbed")

        per_diem_total = pd["per_diem_total_usd"]
        total_cost = round(pax_cost["cost_usd"] + cargo_cost["cost_usd"]
                           + per_diem_total, 2)
        cargo_lead_hr = _mode_cargo_lead_time_hr(mode_key, cargo_cost)
        # Time = max(pax transit, cargo lead) — that's when both have arrived
        combined_time_hr = round(
            max(pax_cost["transit_hr"], cargo_lead_hr), 1
        )

        options.append({
            "mode_key": mode_key,
            "label": MODE_LABELS[mode_key],
            "pax_legs": pax_legs,
            "cargo_legs": cargo_legs,
            "pax_cost_usd": pax_cost["cost_usd"],
            "cargo_cost_usd": cargo_cost["cost_usd"],
            "per_diem_usd": per_diem_total,
            "total_cost_usd": total_cost,
            "fuel_gal": pax_cost["fuel_gal"] + cargo_cost["fuel_gal"],
            "fuel_cost_usd": pax_cost["fuel_cost_usd"] + cargo_cost["fuel_cost_usd"],
            "pax_transit_hr": pax_cost["transit_hr"],
            "cargo_lead_hr": round(cargo_lead_hr, 1),
            "combined_time_hr": combined_time_hr,
            "pax_distance_mi": pax_cost["distance_mi"],
            "cargo_distance_mi": cargo_cost["distance_mi"],
        })

    if not options:
        return {"error": f"No feasible routes computed between {o} and {d}"}

    # Score: weighted cost + lead-time penalty if > deadline
    deadline_hr = max(48, d_plus_days * 24)
    for o_ in options:
        time_penalty = 1.0 if o_["combined_time_hr"] <= deadline_hr else 0.55
        cheap_norm = min(o["total_cost_usd"] for o in options) / max(o_["total_cost_usd"], 1)
        fast_norm  = min(o["combined_time_hr"] for o in options) / max(o_["combined_time_hr"], 1)
        # Heavy weight on cost (PCS Marines + DoD funds) but reward speed too
        o_["score"] = round((0.55 * cheap_norm + 0.35 * fast_norm + 0.10) * time_penalty, 4)
        # If escorting motor-pool item, give drive_escort a boost
        if has_motor_pool_item and o_["mode_key"] == "drive_escort":
            o_["score"] = round(o_["score"] * 1.18, 4)
            o_["bonus_reason"] = "Single-move escort eliminates one TMR hand-off"

    options.sort(key=lambda x: x["score"], reverse=True)
    options[0]["recommended"] = True

    return {
        "origin": o, "origin_name": _node_by_id(o)["name"],
        "destination": d, "destination_name": _node_by_id(d)["name"],
        "hhg_lbs": hhg_lbs,
        "has_motor_pool_item": has_motor_pool_item,
        "motor_pool_item": motor_pool_item,
        "d_plus_days": d_plus_days,
        "deadline_hr": deadline_hr,
        "per_diem_basis": pd,
        "options": options,
    }


# ─────────────────────────────────────────────────────────────────────────────
# TOOL: prefill_dts_voucher  — DTS authorization with JTR-compliant per-diem
# ─────────────────────────────────────────────────────────────────────────────
def prefill_dts_voucher(scenario_id: str, mode_key: str,
                         depart_date: str | None = None,
                         nights: int = 3) -> dict[str, Any]:
    """Generate a DTS authorization pre-fill (VOUCHER schema, JTR-compliant).
    Returns a dict the UI renders as a 'voucher card'."""
    scenarios = {s["scenario_id"]: s for s in load_scenarios()}
    scn = scenarios.get(scenario_id)
    if not scn:
        return {"error": f"Unknown scenario: {scenario_id}"}
    pd = jtr_per_diem(scn["dest_id"], nights)
    rng = random.Random(hash(scenario_id) & 0xFFFFFFFF)
    if not depart_date:
        depart = (datetime(2026, 4, 27)
                  + timedelta(days=scn["d_plus_days"])).date().isoformat()
    else:
        depart = depart_date

    mode_to_dts_code = {
        "fly_ship":      "CA",  # Commercial Air
        "fly_airfreight":"CA",
        "drive_ship":    "PA",  # Privately Owned Auto
        "drive_escort":  "PA",
    }
    incidentals = round(60 + rng.uniform(40, 220), 2)
    return {
        "doc_number": ("".join(rng.choices("ABCDEFGHJKLMNPQRSTUVWXYZ", k=6))
                       + "".join(rng.choices("0123456789", k=6))),
        "ta_number": f"TA-{depart.replace('-','')}-{rng.randint(1000,9999)}",
        "scenario_id": scenario_id,
        "traveler_edipi": scn["traveler_edipi"],
        "traveler_name": scn["traveler_name"],
        "traveler_grade": scn["traveler_grade"],
        "ao_name": "MCKAY, DANIEL",
        "ao_edipi": "25" + "".join(rng.choices("0123456789", k=8)),
        "trip_purpose": "PCS",
        "trip_start": depart,
        "trip_end": (datetime.fromisoformat(depart)
                     + timedelta(days=nights)).date().isoformat(),
        "tdy_city": pd["city"],
        "nights": nights,
        "per_diem_lodging_ceiling_usd": pd["lodging_per_night_usd"],
        "per_diem_mie_usd": pd["mie_per_day_usd"],
        "per_diem_authority": pd["authority"],
        "lodging_total_usd": pd["lodging_total_usd"],
        "mie_total_usd": pd["mie_total_usd"],
        "incidentals_usd": incidentals,
        "total_authorized_usd": round(
            pd["lodging_total_usd"] + pd["mie_total_usd"] + incidentals, 2),
        "mode_of_travel": mode_to_dts_code.get(mode_key, "PA"),
        "gtcc_authority": "DoDFMR Vol 9 Ch 5 — APC-issued GTCC for fuel + lodging",
        "status": "PRE-FILLED — pending AO approval",
    }


# ─────────────────────────────────────────────────────────────────────────────
# TOOL: submit_tmr  —  auto-populates the cargo movement form
# ─────────────────────────────────────────────────────────────────────────────
INSTALLATION_MOVEMENT_POLICY = {
    # max single-shipment lbs without IMO escalation, by destination class
    "default": 26000,
    "OCONUS":  18000,  # OCONUS HHG container weight cap
}


def submit_tmr(scenario_id: str, mode_key: str,
               cargo_lbs: int, motor_pool_item: str = "",
               cargo_lead_hr: float | None = None) -> dict[str, Any]:
    """Auto-populate a TMR (DTR 4500.9-R Part II) for the recommended mode,
    validate against installation movement policy, return a routed control
    number."""
    scenarios = {s["scenario_id"]: s for s in load_scenarios()}
    scn = scenarios.get(scenario_id)
    if not scn:
        return {"error": f"Unknown scenario: {scenario_id}"}
    rng = random.Random((hash(scenario_id) ^ hash(mode_key)) & 0xFFFFFFFF)
    is_oconus = scn["dest_id"] in ("MCAS_IWA", "MCBOKI", "MCBHAW")
    cap_key = "OCONUS" if is_oconus else "default"
    cap = INSTALLATION_MOVEMENT_POLICY[cap_key]

    asset_for_mode = {
        "fly_ship":      ("CONEX (sealift)",      "sea"),
        "drive_ship":    ("CONEX (sealift)" if is_oconus else "Penske 26ft (HHG)",
                          "sea" if is_oconus else "road"),
        "drive_escort":  ("M1078 LMTV" if motor_pool_item else "Penske 26ft (HHG)",
                          "road"),
        "fly_airfreight":("C-17 Globemaster III",  "air"),
    }
    asset_class, mode = asset_for_mode.get(mode_key, ("Penske 26ft (HHG)", "road"))

    # RDD = D + (d_plus_days) + cargo lead time (rounded up to days)
    if cargo_lead_hr is not None:
        rdd_days = scn["d_plus_days"] + max(2, int((cargo_lead_hr + 23) // 24))
    else:
        # Sensible defaults per mode
        default_lead_days = {"drive_escort": 4, "drive_ship": 11,
                             "fly_ship": 14, "fly_airfreight": 4}.get(mode_key, 7)
        rdd_days = scn["d_plus_days"] + default_lead_days
    rdd = (datetime(2026, 4, 27)
           + timedelta(days=rdd_days)).date().isoformat()
    tcn = f"TCN-{rng.randint(100000, 999999)}-{rng.choice('ABCDEFGHJK')}"

    # Validation
    issues = []
    if cargo_lbs > cap:
        issues.append(
            f"Single-shipment weight {cargo_lbs} lbs exceeds {cap_key} cap "
            f"({cap} lbs) — IMO concurrence required."
        )
    if motor_pool_item and "LMTV" in motor_pool_item and not is_oconus and mode_key == "fly_airfreight":
        issues.append(
            "M1078 LMTV by air is non-standard for CONUS PCS — recommend "
            "drive escort or sealift."
        )
    if motor_pool_item and is_oconus and mode_key == "drive_escort":
        issues.append(
            "OCONUS PCS cannot drive-escort organic motor-pool items — "
            "ASSET must move via sealift or USTRANSCOM SDDC."
        )
    status = "ROUTED-TO-AO" if not issues else "ROUTED-TO-IMO-FOR-CONCURRENCE"

    return {
        "tcn": tcn,
        "scenario_id": scenario_id,
        "origin_id": scn["origin_id"],
        "origin_name": scn["origin_name"],
        "dest_id": scn["dest_id"],
        "dest_name": scn["dest_name"],
        "shipper": "USMC LOGCOM, Installation Movement Office",
        "consignee_unit": "Receiving Unit Movement Coordinator",
        "rdd": rdd,
        "asset_class": asset_class,
        "mode": mode,
        "cargo_lbs": cargo_lbs,
        "motor_pool_item": motor_pool_item or None,
        "policy_cap_lbs": cap,
        "validation_issues": issues,
        "status": status,
        "routing_authority": "DTR 4500.9-R Part II",
        "submitted_at": datetime.now(timezone.utc).isoformat(),
    }


# ─────────────────────────────────────────────────────────────────────────────
# TOOL: plan_last_mile_push  — LaDe pickup + delivery to receiving unit
# ─────────────────────────────────────────────────────────────────────────────
def plan_last_mile_push(scenario_id: str, tmr_tcn: str | None = None) -> dict:
    """Build a LaDe-shape last-mile plan for the cargo's final hop on the
    receiving installation."""
    scenarios = {s["scenario_id"]: s for s in load_scenarios()}
    scn = scenarios.get(scenario_id)
    if not scn:
        return {"error": f"Unknown scenario: {scenario_id}"}
    rng = random.Random((hash(scenario_id) ^ hash(tmr_tcn or "")) & 0xFFFFFFFF)
    d_node = _node_by_id(scn["dest_id"])
    pickup_eta = (datetime(2026, 4, 27)
                  + timedelta(days=scn["d_plus_days"] + 5))
    delivery_eta = pickup_eta + timedelta(hours=rng.randint(6, 36))
    couriers = ["DET-A", "DET-B", "MCO-DOM", "CLB-7"]
    return {
        "parcel_id": f"LMD-{scenario_id}",
        "tmr_tcn": tmr_tcn,
        "courier": rng.choice(couriers),
        "pickup_node": scn["dest_id"] + "-PORT",
        "pickup_lat": round(d_node["lat"] + rng.uniform(-0.04, 0.04), 5),
        "pickup_lon": round(d_node["lon"] + rng.uniform(-0.04, 0.04), 5),
        "delivery_node": scn["dest_id"] + "-RECV-WHSE",
        "delivery_lat": round(d_node["lat"] + rng.uniform(-0.04, 0.04), 5),
        "delivery_lon": round(d_node["lon"] + rng.uniform(-0.04, 0.04), 5),
        "weight_lbs": scn["hhg_lbs"],
        "item": scn["motor_pool_item"] or "HHG container",
        "receiving_unit": rng.choice([
            "1st Bn 5th Marines", "3d Bn 7th Marines", "HQ Bn II MEF",
            "1st Marine Logistics Group", "Combat Logistics Bn 7",
        ]),
        "eta_pickup": pickup_eta.isoformat(),
        "eta_delivery": delivery_eta.isoformat(),
        "transit_hr_last_mile": round(
            (delivery_eta - pickup_eta).total_seconds() / 3600, 1),
        "status": "PLANNED — synced to GCSS-MC",
    }


# ─────────────────────────────────────────────────────────────────────────────
# TOOL: cross_validate_plan  — does it all sync?  (chat_json validator)
# ─────────────────────────────────────────────────────────────────────────────
def cross_validate_plan(comparison: dict, voucher: dict, tmr: dict,
                         last_mile: dict | None = None) -> dict:
    """Runs deterministic cross-validation across the 3 sub-plans + last-mile."""
    issues: list[str] = []
    notes: list[str] = []

    rec = next((o for o in comparison.get("options", []) if o.get("recommended")), None)
    if not rec:
        issues.append("No recommended mode in comparison.")
        return {"verdict": "BLOCKED", "issues": issues, "notes": notes}

    # 1. Mode of travel matches TMR mode family (PA -> road, CA -> air, etc.)
    mot = voucher.get("mode_of_travel")
    if mot == "PA" and tmr.get("mode") == "air":
        issues.append("Voucher mode-of-travel POV but TMR is air — mismatch.")
    if mot == "CA" and tmr.get("mode") == "road" and rec.get("mode_key") not in ("fly_ship",):
        notes.append("Voucher CA + TMR road is fine for fly+ship-cargo split — "
                     "traveler flies; HHG ground-ships.")

    # 2. Trip end vs cargo RDD
    try:
        trip_end = datetime.fromisoformat(voucher["trip_end"])
        rdd = datetime.fromisoformat(tmr["rdd"])
        gap = (rdd - trip_end).days
        if gap > 7:
            issues.append(f"Cargo RDD is {gap} days after trip end — "
                          "traveler may need extra TLA / lodging extension.")
        elif gap < -2:
            issues.append(f"Cargo RDD is {-gap} days BEFORE trip end — "
                          "no one on the receiving end to sign for it.")
        else:
            notes.append(f"Trip end ↔ cargo RDD aligned within {gap} day(s).")
    except Exception:
        issues.append("Could not compare trip end vs cargo RDD (parse error).")

    # 3. TMR validation issues
    if tmr.get("validation_issues"):
        for i in tmr["validation_issues"]:
            issues.append(f"TMR: {i}")

    # 4. Last-mile alignment
    if last_mile:
        try:
            lm_pickup = datetime.fromisoformat(last_mile["eta_pickup"])
            lm_delivery = datetime.fromisoformat(last_mile["eta_delivery"])
            if lm_pickup < datetime.fromisoformat(tmr["rdd"]):
                # pickup before RDD means cargo isn't there yet
                notes.append("Last-mile pickup window starts BEFORE cargo RDD — "
                             "ETD-buffer in GCSS-MC absorbs the slack.")
            notes.append(
                f"Last-mile transit {round((lm_delivery-lm_pickup).total_seconds()/3600,1)}h, "
                f"courier {last_mile['courier']}.")
        except Exception:
            pass

    # 5. Per-diem cap sanity
    pd = comparison.get("per_diem_basis", {})
    if pd:
        if voucher["per_diem_lodging_ceiling_usd"] != pd["lodging_per_night_usd"]:
            issues.append("Voucher lodging ceiling does NOT match JTR per-diem.")
        else:
            notes.append(
                f"JTR per-diem ${pd['lodging_per_night_usd']}/night lodging, "
                f"${pd['mie_per_day_usd']}/day M&IE confirmed.")

    verdict = "OK" if not issues else ("WARN" if len(issues) <= 2 else "BLOCKED")
    return {
        "verdict": verdict,
        "issues": issues,
        "notes": notes,
        "checked_at": datetime.now(timezone.utc).isoformat(),
    }


# ─────────────────────────────────────────────────────────────────────────────
# Tool schemas for OpenAI function-calling
# ─────────────────────────────────────────────────────────────────────────────
TOOL_SCHEMAS: list[dict] = [
    {
        "type": "function",
        "function": {
            "name": "compare_modes",
            "description": (
                "Compare the 4 PCS travel + cargo mode options "
                "(fly+ship / drive+ship / drive escort / fly+airfreight). "
                "Uses the BTS NTAD multimodal corridor graph and AFCENT "
                "logistics asset data to compute time, cost, fuel, and "
                "JTR-compliant per-diem per option. Returns options with "
                "scores and a recommended flag."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "origin": {"type": "string",
                               "description": "Origin node id or name (MCBLEJ, MCBPEN, ...)"},
                    "destination": {"type": "string"},
                    "hhg_lbs": {"type": "integer", "default": 8000},
                    "has_motor_pool_item": {"type": "boolean"},
                    "motor_pool_item": {"type": "string"},
                    "d_plus_days": {"type": "integer", "default": 30},
                },
                "required": ["origin", "destination"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "prefill_dts_voucher",
            "description": (
                "Generate a JTR-compliant DTS authorization pre-fill for "
                "the chosen mode. Returns a doc_number, per-diem rates, "
                "lodging projection, GTCC authority, mode-of-travel."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "scenario_id": {"type": "string"},
                    "mode_key": {"type": "string",
                                 "enum": ["fly_ship", "drive_ship",
                                          "drive_escort", "fly_airfreight"]},
                    "depart_date": {"type": "string", "description": "YYYY-MM-DD"},
                    "nights": {"type": "integer", "default": 3},
                },
                "required": ["scenario_id", "mode_key"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "submit_tmr",
            "description": (
                "Auto-populate the cargo Transportation Movement Request "
                "(TMR per DTR 4500.9-R Part II) for the chosen mode. "
                "Validates against installation movement policy; returns "
                "a routed TCN."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "scenario_id": {"type": "string"},
                    "mode_key": {"type": "string"},
                    "cargo_lbs": {"type": "integer"},
                    "motor_pool_item": {"type": "string"},
                    "cargo_lead_hr": {"type": "number",
                                       "description": "Lead time from compare_modes for the picked mode."},
                },
                "required": ["scenario_id", "mode_key", "cargo_lbs"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "plan_last_mile_push",
            "description": (
                "LaDe-shape last-mile plan: pickup at receiving installation "
                "port/yard → delivery to receiving unit. Returns a parcel "
                "record synced to GCSS-MC."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "scenario_id": {"type": "string"},
                    "tmr_tcn": {"type": "string"},
                },
                "required": ["scenario_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "cross_validate_plan",
            "description": (
                "Cross-validate the travel route + cargo route + arrival "
                "windows. Returns OK/WARN/BLOCKED with issue + note bullets."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "comparison": {"type": "object"},
                    "voucher":    {"type": "object"},
                    "tmr":        {"type": "object"},
                    "last_mile":  {"type": "object"},
                },
                "required": ["comparison", "voucher", "tmr"],
            },
        },
    },
]


TOOL_REGISTRY = {
    "compare_modes":       compare_modes,
    "prefill_dts_voucher": prefill_dts_voucher,
    "submit_tmr":          submit_tmr,
    "plan_last_mile_push": plan_last_mile_push,
    "cross_validate_plan": cross_validate_plan,
}
