"""STORM-SHIFT — 6-parallel-projection polycrisis engine.

Six deterministic projection functions feed the 6-axis readiness picture.
Each runs in parallel via concurrent.futures.ThreadPoolExecutor; the LLM
narrative call is layered on top via src/agent.py.

Projections (deterministic — never gated on LLM):
  1. flood_damage      — NFIP claim density × storm severity haversine
  2. supply_chain      — FEMA SC Climate + Logistics-CA disruption rollup
  3. inventory_cascade — on-hand stocks ÷ surge demand → red items in N hours
  4. consumption_surge — Class I-IX demand × forced-shelter days × headcount
  5. base_impact       — rolled-up dollar exposure + days-to-MC
  6. fire_secondary    — FIRMS pixels + wind-projected ignition risk score

All six return JSON-serializable dicts. The dashboard reads these directly.
"""
from __future__ import annotations

import concurrent.futures
import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DATA_DIR = Path(__file__).resolve().parents[1] / "data"


# ─────────────────────────────────────────────────────────────────────────────
# Loaders (cache so streamlit re-runs are instant)
# ─────────────────────────────────────────────────────────────────────────────
_CACHE: dict[str, Any] = {}


def _load(name: str) -> Any:
    if name not in _CACHE:
        _CACHE[name] = json.loads((DATA_DIR / name).read_text())
    return _CACHE[name]


def load_installations() -> list[dict]:
    return _load("installations.json")


def load_scenarios() -> list[dict]:
    return _load("scenarios.json")


def load_polycrisis_pairs() -> list[dict]:
    return _load("polycrisis_pairs.json")


def load_nfip() -> list[dict]:
    return _load("nfip_claims.json")


def load_firms() -> list[dict]:
    return _load("firms_pixels.json")


def load_fema_sc() -> list[dict]:
    return _load("fema_sc_climate.json")


def load_logistics() -> list[dict]:
    return _load("logistics_ca.json")


def load_cached_briefs() -> dict:
    return _load("cached_briefs.json")


# ─────────────────────────────────────────────────────────────────────────────
# Math helpers
# ─────────────────────────────────────────────────────────────────────────────

def haversine_mi(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R = 3958.7613
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * R * math.asin(min(1.0, math.sqrt(a)))


def severity_factor(scenario: dict) -> float:
    """Composite severity 0..3+. Cat-4 ≈ 2.6, baseline ≈ 0.05."""
    wind = scenario["wind_kt"] / 100.0
    rain = scenario["rain_in_24h"] / 12.0
    surge = scenario["surge_ft"] / 8.0
    return round(0.4 * wind + 0.35 * rain + 0.25 * surge, 3)


def installation_by_id(inst_id: str) -> dict | None:
    for i in load_installations():
        if i["id"] == inst_id:
            return i
    return None


def scenario_by_id(scn_id: str) -> dict | None:
    for s in load_scenarios():
        if s["id"] == scn_id:
            return s
    return None


# ─────────────────────────────────────────────────────────────────────────────
# 1. Flood damage projection
# ─────────────────────────────────────────────────────────────────────────────

def proj_flood_damage(installation_id: str, scenario_id: str) -> dict:
    """NFIP claim density within 30 mi × storm severity → $ exposure per asset class.

    Returns:
      {
        total_usd, asset_class_breakdown: {housing, wharf, hangars, fuel, c2},
        nfip_claims_in_radius, severity, methodology
      }
    """
    inst = installation_by_id(installation_id)
    scn = scenario_by_id(scenario_id)
    if not inst or not scn:
        return {"error": "unknown installation or scenario"}

    sev = severity_factor(scn)
    nearby = [c for c in load_nfip()
              if haversine_mi(c["latitude"], c["longitude"], inst["lat"], inst["lon"]) <= 30.0]

    # baseline historical $ density at this installation (sum of paid claims, normalized)
    historical_paid = sum(
        c.get("amountPaidOnBuildingClaim", 0) + c.get("amountPaidOnContentsClaim", 0)
        for c in nearby
    )
    # scale: a single Cat-3 today ≈ 1.0x the cumulative 15-year historic paid value
    storm_total = historical_paid * sev * 1.0

    inv = inst["inventory"]
    breakdown = {
        "Family Housing":  storm_total * 0.42 if inv.get("family_housing_units", 0) > 0 else 0.0,
        "Wharf / Marine":  storm_total * 0.22 if inv.get("wharf_meters", 0) > 0 else 0.0,
        "Aircraft Hangars": storm_total * 0.16 if inv.get("aircraft_hangars", 0) > 0 else 0.0,
        "Fuel Storage":    storm_total * 0.10,
        "C2 / IT Nodes":   storm_total * 0.05,
        "Other Facilities": storm_total * 0.05,
    }
    total = sum(breakdown.values())
    return {
        "projection": "flood_damage",
        "total_usd": round(total, 2),
        "asset_class_breakdown": {k: round(v, 2) for k, v in breakdown.items()},
        "nfip_claims_in_radius": len(nearby),
        "severity": sev,
        "methodology": "NFIP paid-claim density (30-mi haversine) × composite severity (wind+rain+surge).",
    }


# ─────────────────────────────────────────────────────────────────────────────
# 2. Supply chain disruption projection
# ─────────────────────────────────────────────────────────────────────────────

def proj_supply_chain(installation_id: str, scenario_id: str) -> dict:
    """FEMA SC Climate Resilience + Logistics-CA → affected suppliers, lead-time surges."""
    inst = installation_by_id(installation_id)
    scn = scenario_by_id(scenario_id)
    if not inst or not scn:
        return {"error": "unknown installation or scenario"}

    sev = severity_factor(scn)
    fema_sc = load_fema_sc()
    # suppliers within 200 mi and matching hazard family
    hazard_map = {
        "hurricane": ["Hurricane", "Cyclone"],
        "tropical_storm": ["Hurricane"],
        "atmospheric_river": ["Atmospheric River", "Riverine Flood"],
        "santa_ana_fire": ["Wildfire", "Heatwave"],
        "baseline": [],
    }
    relevant_hazards = hazard_map.get(scn["kind"], [])
    matched = [
        e for e in fema_sc
        if e["hazard_type"] in relevant_hazards
        and haversine_mi(e["latitude"], e["longitude"], inst["lat"], inst["lon"]) <= 200.0
    ]

    suppliers_affected = sum(e["supplier_count_affected"] for e in matched)
    avg_baseline_lead = (
        sum(e["lead_time_baseline_days"] for e in matched) / max(1, len(matched))
        if matched else 7.0
    )
    avg_disrupted_lead = (
        sum(e["lead_time_disrupted_days"] for e in matched) / max(1, len(matched))
        if matched else 7.0
    )
    surge_factor = round(avg_disrupted_lead / max(1.0, avg_baseline_lead), 2)
    estimated_cost = sum(e["estimated_cost_usd"] for e in matched) * (1.0 + sev * 0.5)

    # Logistics-CA — only relevant for Pendleton + Yuma
    logistics = load_logistics()
    near_logistics = [r for r in logistics
                      if haversine_mi(r["destination_lat"], r["destination_lon"],
                                      inst["lat"], inst["lon"]) <= 200.0]
    delayed = [r for r in near_logistics if r["transit_days_actual"] > r["transit_days_planned"]]

    # Top affected product categories
    by_cat: dict[str, int] = {}
    for e in matched:
        by_cat[e["product_category"]] = by_cat.get(e["product_category"], 0) + e["supplier_count_affected"]
    top_categories = sorted(by_cat.items(), key=lambda kv: -kv[1])[:5]

    return {
        "projection": "supply_chain",
        "suppliers_affected": suppliers_affected,
        "fema_sc_events_matched": len(matched),
        "lead_time_baseline_days": round(avg_baseline_lead, 1),
        "lead_time_disrupted_days": round(avg_disrupted_lead, 1),
        "lead_time_surge_factor": surge_factor,
        "estimated_disruption_cost_usd": round(estimated_cost, 2),
        "logistics_ca_records_in_radius": len(near_logistics),
        "logistics_ca_delayed": len(delayed),
        "top_affected_categories": [{"category": c, "suppliers": n} for c, n in top_categories],
        "methodology": "FEMA SC Climate (200-mi haversine + hazard-family match) joined to Logistics-CA actuals.",
    }


# ─────────────────────────────────────────────────────────────────────────────
# 3. Inventory cascade projection
# ─────────────────────────────────────────────────────────────────────────────

INVENTORY_BURN_RATE = {
    # daily burn per sheltered person (used to compute hours-to-red)
    "class_i_mre_cases": 0.012,            # cases/person/day (3 MRE/person/day, 24/case)
    "class_iii_fuel_gal": 1.5,             # gal generator+vehicle support / person / day in shelter
    "class_v_ammo_short_tons": 0.0001,     # negligible during shelter posture
    "class_viii_plasma_units": 0.004,      # 4 per 1000 sheltered/day
    "class_ix_repair_parts_lines": 0.8,    # lines pulled per person per day during disaster
    "potable_water_gal": 6.0,              # gal/person/day
    "generator_diesel_gal": 1.2,           # gal/person/day under shelter posture
}

INVENTORY_LABEL = {
    "class_i_mre_cases": "Class I — MRE (cases)",
    "class_iii_fuel_gal": "Class III — JP-8 / Fuel (gal)",
    "class_v_ammo_short_tons": "Class V — Ammo (short tons)",
    "class_viii_plasma_units": "Class VIII — Plasma (units)",
    "class_ix_repair_parts_lines": "Class IX — Repair Parts (lines)",
    "potable_water_gal": "Potable Water (gal)",
    "generator_diesel_gal": "Generator Diesel (gal)",
}


def proj_inventory_cascade(installation_id: str, scenario_id: str) -> dict:
    inst = installation_by_id(installation_id)
    scn = scenario_by_id(scenario_id)
    if not inst or not scn:
        return {"error": "unknown installation or scenario"}

    sev = severity_factor(scn)
    headcount = int(inst["personnel"] * scn.get("headcount_factor", 1.0))
    shelter_days = max(1, scn.get("shelter_days", 1))

    rows = []
    red_count = 0
    for cls, on_hand in inst["stocks"].items():
        burn = INVENTORY_BURN_RATE[cls] * headcount * (1.0 + sev * 0.6)
        hours_to_red = (on_hand / max(1.0, burn)) * 24.0  # burn is per-day → convert to hours
        # Required for shelter window
        required = burn * shelter_days
        delta = on_hand - required
        status = "GREEN"
        if delta < 0:
            status = "RED"
            red_count += 1
        elif hours_to_red < (shelter_days * 24 * 1.5):
            status = "AMBER"
        rows.append({
            "class": INVENTORY_LABEL[cls],
            "on_hand": round(on_hand, 1),
            "daily_burn": round(burn, 2),
            "shelter_window_required": round(required, 1),
            "delta": round(delta, 1),
            "hours_to_red": round(hours_to_red, 1),
            "status": status,
        })
    rows.sort(key=lambda r: r["hours_to_red"])

    return {
        "projection": "inventory_cascade",
        "headcount_in_shelter": headcount,
        "shelter_days": shelter_days,
        "items_red": red_count,
        "items_amber": sum(1 for r in rows if r["status"] == "AMBER"),
        "items_green": sum(1 for r in rows if r["status"] == "GREEN"),
        "rows": rows,
        "methodology": "On-hand ÷ (per-person daily burn × headcount × severity) → hours-to-red.",
    }


# ─────────────────────────────────────────────────────────────────────────────
# 4. Consumption surge projection (Class I-IX over 72h)
# ─────────────────────────────────────────────────────────────────────────────

def proj_consumption_surge(installation_id: str, scenario_id: str) -> dict:
    inst = installation_by_id(installation_id)
    scn = scenario_by_id(scenario_id)
    if not inst or not scn:
        return {"error": "unknown installation or scenario"}

    sev = severity_factor(scn)
    headcount = int(inst["personnel"] * scn.get("headcount_factor", 1.0))
    shelter_days = max(1, scn.get("shelter_days", 1))

    classes = []
    for cls, label in INVENTORY_LABEL.items():
        burn = INVENTORY_BURN_RATE[cls] * headcount * (1.0 + sev * 0.6)
        consumed = burn * shelter_days
        classes.append({
            "class": label,
            "daily_consumption": round(burn, 2),
            "total_over_shelter": round(consumed, 1),
            "units": label.split("(")[-1].rstrip(")") if "(" in label else "",
        })

    return {
        "projection": "consumption_surge",
        "headcount": headcount,
        "shelter_days": shelter_days,
        "severity": sev,
        "classes": classes,
        "methodology": "LogTRACE-shape consumption tables × (forced-shelter days) × headcount × severity multiplier.",
    }


# ─────────────────────────────────────────────────────────────────────────────
# 5. Base impact rollup ($ + days-to-MC)
# ─────────────────────────────────────────────────────────────────────────────

def proj_base_impact(flood: dict, supply: dict, inv: dict, consumption: dict,
                     fire: dict | None = None) -> dict:
    flood_usd = flood.get("total_usd", 0.0)
    supply_usd = supply.get("estimated_disruption_cost_usd", 0.0)

    # inventory shortage cost: number of red items × premium replenishment cost (heuristic)
    red_premium = inv.get("items_red", 0) * 12_000_000  # $12M premium per critical class red
    fire_usd = fire.get("estimated_damage_usd", 0.0) if fire else 0.0

    total = flood_usd + supply_usd + red_premium + fire_usd

    # days-to-MC: composite of supply lead-time and red-item count
    base_days = inv.get("shelter_days", 1) * 0.6
    days_to_mc = base_days + (supply.get("lead_time_surge_factor", 1.0) - 1.0) * 1.4 + inv.get("items_red", 0) * 0.7
    if fire and fire.get("ignition_risk_score", 0) > 0.6:
        days_to_mc += 1.5

    return {
        "projection": "base_impact",
        "total_dollar_exposure_usd": round(total, 2),
        "components_usd": {
            "flood_damage": round(flood_usd, 2),
            "supply_chain": round(supply_usd, 2),
            "inventory_red_premium": round(red_premium, 2),
            "fire_secondary": round(fire_usd, 2),
        },
        "days_to_mission_capable": round(days_to_mc, 2),
        "methodology": "Sum of flood + supply + inventory red-premium + fire-secondary; days-to-MC = base + supply surge + red items.",
    }


# ─────────────────────────────────────────────────────────────────────────────
# 6. Fire-secondary risk projection
# ─────────────────────────────────────────────────────────────────────────────

def proj_fire_secondary(installation_id: str, scenario_id: str) -> dict:
    inst = installation_by_id(installation_id)
    scn = scenario_by_id(scenario_id)
    if not inst or not scn:
        return {"error": "unknown installation or scenario"}

    firms = load_firms()
    nearby = [f for f in firms
              if haversine_mi(f["latitude"], f["longitude"], inst["lat"], inst["lon"]) <= 60.0]
    n_pixels = len(nearby)

    # wind-projected score: if wind is offshore (Santa Ana) or post-storm dry, score↑
    base_wind = scn["wind_kt"] / 100.0
    fire_relevant = scn.get("fire_secondary", False)
    base_score = 0.0
    if fire_relevant:
        base_score = min(1.0, 0.25 + base_wind * 0.6 + (n_pixels / 60.0) * 0.4)
    else:
        # still a low background score for any installation w/ FIRMS pixels
        base_score = min(0.3, n_pixels / 200.0)

    avg_frp = (sum(f.get("frp", 0.0) for f in nearby) / max(1, n_pixels)) if nearby else 0.0
    high_conf = sum(1 for f in nearby if f.get("confidence") == "high")

    # damage estimate: $50M per 0.1 of ignition_risk_score for fire-relevant scenarios
    estimated_damage = base_score * 500_000_000 if fire_relevant else 0.0

    # Time-lag: atmospheric river → 10-14 day fire-following lag, Santa Ana → immediate
    if scn["kind"] == "atmospheric_river":
        time_lag_days = 12
        lag_note = "Vegetation regrowth lag — fire risk peaks Day 10-14 post-event."
    elif scn["kind"] == "santa_ana_fire":
        time_lag_days = 0
        lag_note = "Immediate — Santa Ana wind drives ignition concurrent with event."
    else:
        time_lag_days = 0
        lag_note = "Background FIRMS density only; no storm-driven lag."

    return {
        "projection": "fire_secondary",
        "firms_pixels_within_60mi": n_pixels,
        "high_confidence_pixels": high_conf,
        "avg_fire_radiative_power": round(avg_frp, 2),
        "ignition_risk_score": round(base_score, 3),
        "estimated_damage_usd": round(estimated_damage, 2),
        "time_lag_days": time_lag_days,
        "lag_note": lag_note,
        "methodology": "FIRMS thermal anomaly density × scenario wind kt × scenario fire-relevance flag.",
    }


# ─────────────────────────────────────────────────────────────────────────────
# Polycrisis multiplier
# ─────────────────────────────────────────────────────────────────────────────

def polycrisis_multiplier(scenario_ids: list[str]) -> dict:
    """Look up the compounding multiplier for 2+ co-occurring scenarios."""
    pairs = load_polycrisis_pairs()
    matched = []
    for p in pairs:
        if p["a"] in scenario_ids and p["b"] in scenario_ids:
            matched.append(p)
    if not matched:
        return {"multiplier": 1.0, "rationale": None, "matched_pairs": []}
    # Compound: multiplicative across matched pairs (capped at 2.5x)
    m = 1.0
    for p in matched:
        m *= p["multiplier"]
    m = min(m, 2.5)
    return {
        "multiplier": round(m, 3),
        "rationale": " ".join(p["rationale"] for p in matched),
        "matched_pairs": matched,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Run all 6 projections in parallel
# ─────────────────────────────────────────────────────────────────────────────

def run_all_projections(installation_id: str, scenario_id: str,
                        co_scenario_id: str | None = None) -> dict:
    """Fan-out all 6 projections in a thread pool. Returns a single rolled-up dict."""
    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as ex:
        f_flood   = ex.submit(proj_flood_damage,      installation_id, scenario_id)
        f_supply  = ex.submit(proj_supply_chain,      installation_id, scenario_id)
        f_inv     = ex.submit(proj_inventory_cascade, installation_id, scenario_id)
        f_cons    = ex.submit(proj_consumption_surge, installation_id, scenario_id)
        f_fire    = ex.submit(proj_fire_secondary,    installation_id, scenario_id)
        flood   = f_flood.result()
        supply  = f_supply.result()
        inv     = f_inv.result()
        cons    = f_cons.result()
        fire    = f_fire.result()

    # impact rollup depends on the others
    base = proj_base_impact(flood, supply, inv, cons, fire)

    # polycrisis multiplier (if a second scenario picked)
    poly = polycrisis_multiplier([scenario_id] + ([co_scenario_id] if co_scenario_id else []))

    # apply multiplier to total dollar exposure & days-to-MC
    if poly["multiplier"] > 1.0:
        base["total_dollar_exposure_usd"] = round(base["total_dollar_exposure_usd"] * poly["multiplier"], 2)
        base["days_to_mission_capable"] = round(base["days_to_mission_capable"] * (1.0 + (poly["multiplier"] - 1.0) * 0.6), 2)
        base["polycrisis_multiplier_applied"] = poly["multiplier"]

    return {
        "installation_id": installation_id,
        "scenario_id": scenario_id,
        "co_scenario_id": co_scenario_id,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "flood": flood,
        "supply": supply,
        "inventory": inv,
        "consumption": cons,
        "fire": fire,
        "base_impact": base,
        "polycrisis": poly,
    }


if __name__ == "__main__":
    import sys
    inst_id = sys.argv[1] if len(sys.argv) > 1 else "lejeune"
    scn_id  = sys.argv[2] if len(sys.argv) > 2 else "cat3"
    out = run_all_projections(inst_id, scn_id)
    print(json.dumps(out, indent=2))
