"""Synthetic last-mile expeditionary delivery dataset for CARGO.

Generates:
  - depots.json       — 1 forward depot (austere, dirt LZ)
  - squads.json       — 8 dispersed squad positions (alpha..hotel) across a
                        ~30 km AOI with per-squad demand profile
                        (Class I rations, Class V ammo, Class VIII med, water)
  - vehicles.csv      — 4 vehicle classes (MTVR / JLTV / EFV-replacement /
                        autonomous resupply UGV) with capacity, fuel burn,
                        cruise speed, off-road factor
  - threat_zones.json — 3 named risk windows (UAS observed, sniper sector,
                        IED-cleared corridor)
  - cached_briefs.json — 2 pre-computed scenario briefs (cache-first demo)

Reproducible: random.Random(1776). Frame: "An expeditionary unit pushes
supplies from a forward depot to dispersed squad-level positions across
30 km of austere terrain in 48 hours."

Real-world dataset stand-in: Last Mile Delivery (LaDe) by Cainiao /
Alibaba — public last-mile delivery dataset.
See data/load_real.py for the swap recipe.
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from shared.synth import seeded, write_csv, write_json  # noqa: E402

OUT = Path(__file__).parent

# ---------------------------------------------------------------------------
# Forward depot — austere LZ at the AO origin
# ---------------------------------------------------------------------------
DEPOT = {
    "id": "FOB-RAVEN",
    "name": "FOB Raven (Forward Depot)",
    "type": "austere",
    "lat": 33.4150,
    "lon": 43.7000,
    "elev_m": 240,
    "lz_grade": "dirt",
    "fuel_capacity_gal": 3200,
    "notes": "Class I + Class V on-hand; no hardstand; UAS overwatch x1.",
}

# ---------------------------------------------------------------------------
# 8 squad positions across ~30 km AOI (NATO phonetic alpha..hotel)
# Each squad has a demand profile in lb (Class I food, Class V ammo,
# Class VIII med) + water gallons.
# ---------------------------------------------------------------------------
SQUADS_RAW = [
    # callsign, lat,     lon,     terrain,     personnel, priority
    ("ALPHA",   33.5100, 43.7200, "open",      13, "ROUTINE"),
    ("BRAVO",   33.4900, 43.8350, "broken",    11, "PRIORITY"),
    ("CHARLIE", 33.4400, 43.8800, "urban",     12, "ROUTINE"),
    ("DELTA",   33.3700, 43.8200, "wadi",       9, "URGENT"),
    ("ECHO",    33.3300, 43.7400, "broken",    13, "PRIORITY"),
    ("FOXTROT", 33.3450, 43.6300, "open",      11, "ROUTINE"),
    ("GOLF",    33.4100, 43.5750, "urban",     14, "URGENT"),
    ("HOTEL",   33.4900, 43.6200, "broken",    10, "PRIORITY"),
]


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R_km = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * R_km * math.asin(math.sqrt(a))


def build_squads(rng) -> list[dict]:
    out = []
    # Per-squad scaling — tied to personnel + priority
    pri_weight = {"ROUTINE": 1.0, "PRIORITY": 1.25, "URGENT": 1.55}
    for callsign, lat, lon, terrain, pax, pri in SQUADS_RAW:
        scale = pri_weight[pri] * (pax / 12.0)
        # Class I (rations): ~6 lb/Marine/day (3 MREs)
        cls_i = round(pax * 6.0 * 2 * scale * rng.uniform(0.95, 1.10))
        # Class V (ammo) lb (rounds-equivalent already aggregated)
        cls_v = round(pax * 90.0 * scale * rng.uniform(0.85, 1.20))
        # Class VIII (med) lb
        cls_viii = round(pax * 4.0 * scale * rng.uniform(0.90, 1.15))
        # Water gallons (1.5 gal/Marine/day, 2 days)
        water_gal = round(pax * 1.5 * 2 * scale * rng.uniform(0.95, 1.05), 1)
        # Distance from depot (great-circle, line-of-sight km)
        dist_km = round(_haversine_km(DEPOT["lat"], DEPOT["lon"], lat, lon), 2)
        out.append({
            "id": callsign,
            "callsign": callsign,
            "lat": lat,
            "lon": lon,
            "terrain": terrain,
            "personnel": pax,
            "priority": pri,
            "demand_class_i_lb": cls_i,
            "demand_class_v_lb": cls_v,
            "demand_class_viii_lb": cls_viii,
            "demand_water_gal": water_gal,
            "demand_total_lb": cls_i + cls_v + cls_viii + int(water_gal * 8.34),
            "dist_from_depot_km": dist_km,
        })
    return out


# ---------------------------------------------------------------------------
# 4 vehicle classes. Capacity in lb, fuel burn in gal/hr at cruise,
# cruise km/h on open road. Off-road factor multiplies time on broken/wadi.
# ---------------------------------------------------------------------------
VEHICLES = [
    {
        "vehicle_id": "MTVR-01",
        "class": "MTVR",
        "long_name": "MTVR (Medium Tactical Vehicle Replacement)",
        "capacity_lb": 14000,
        "cruise_kph": 65,
        "offroad_kph": 32,
        "fuel_gal_hr": 6.5,
        "crew": 3,
        "armor": "MEDIUM",
        "off_road_factor": 1.4,
        "signature": "HIGH",
        "notes": "Workhorse 7-ton; CL I/V bulk hauler.",
    },
    {
        "vehicle_id": "JLTV-04",
        "class": "JLTV",
        "long_name": "JLTV (Joint Light Tactical Vehicle)",
        "capacity_lb": 5100,
        "cruise_kph": 90,
        "offroad_kph": 55,
        "fuel_gal_hr": 4.5,
        "crew": 4,
        "armor": "HEAVY",
        "off_road_factor": 1.15,
        "signature": "MEDIUM",
        "notes": "Fast, armored, low-volume but high-survivability.",
    },
    {
        "vehicle_id": "ARV-02",
        "class": "ARV",
        "long_name": "ARV-L (EFV-replacement, amphibious recon)",
        "capacity_lb": 4200,
        "cruise_kph": 72,
        "offroad_kph": 60,
        "fuel_gal_hr": 7.2,
        "crew": 3,
        "armor": "HEAVY",
        "off_road_factor": 1.05,
        "signature": "HIGH",
        "notes": "Amphibious / recon; tolerates wadi crossings.",
    },
    {
        "vehicle_id": "UGV-07",
        "class": "UGV",
        "long_name": "Autonomous Resupply UGV (Squad Multipurpose Equipment Transport)",
        "capacity_lb": 1000,
        "cruise_kph": 18,
        "offroad_kph": 12,
        "fuel_gal_hr": 0.8,
        "crew": 0,
        "armor": "NONE",
        "off_road_factor": 1.6,
        "signature": "LOW",
        "notes": "Unmanned; ideal for last-tactical-mile push to forward squads.",
    },
]

# ---------------------------------------------------------------------------
# 3 named threat zones over the AOI (lat/lon bbox + window time + type)
# ---------------------------------------------------------------------------
THREAT_ZONES = [
    {
        "id": "TZ-01",
        "name": "UAS Observed Sector (Northeast)",
        "type": "UAS",
        "severity": "HIGH",
        "lat_min": 33.45, "lat_max": 33.55,
        "lon_min": 43.78, "lon_max": 43.88,
        "window_local": "0500-0800",
        "guidance": "Avoid daylight crossings; small-quad ISR loitering.",
    },
    {
        "id": "TZ-02",
        "name": "Sniper Sector (Charlie cordon)",
        "type": "SNIPER",
        "severity": "MEDIUM",
        "lat_min": 33.42, "lat_max": 33.48,
        "lon_min": 43.85, "lon_max": 43.92,
        "window_local": "ALL_DAY",
        "guidance": "Hardened armor + speed; no halts inside box.",
    },
    {
        "id": "TZ-03",
        "name": "IED-cleared Corridor (Route IRON)",
        "type": "IED_CLEARED",
        "severity": "LOW",
        "lat_min": 33.36, "lat_max": 33.42,
        "lon_min": 43.55, "lon_max": 43.78,
        "window_local": "ALL_DAY",
        "guidance": "Route swept 0400 today; safe transit corridor "
                    "between depot and Foxtrot/Golf/Hotel.",
    },
]


# ---------------------------------------------------------------------------
# Hero scenarios — these get pre-computed against the LLM at generate-time.
# ---------------------------------------------------------------------------
SCENARIOS = [
    {
        "id": "DEFAULT",
        "title": "Push Class I + V to all squads, lowest threat exposure (T-48h)",
        "prompt": (
            "Push 8,000 lb of Class I and 2,400 rounds-equivalent (Class V) "
            "from FOB Raven to alpha through hotel squads by 0600 tomorrow, "
            "lowest threat exposure. Use the tools to plan."
        ),
    },
    {
        "id": "URGENT_DELTA",
        "title": "URGENT casevac+resupply to Delta squad (T-6h)",
        "prompt": (
            "URGENT: Delta squad at the wadi position needs a 600 lb medical "
            "(Class VIII) push and 900 lb of water inside 6 hours. Threat: "
            "UAS sector active 0500-0800. Recommend a vehicle and route."
        ),
    },
]


def build_data():
    rng = seeded(1776)
    squads = build_squads(rng)
    write_json(OUT / "depots.json", [DEPOT])
    write_json(OUT / "squads.json", squads)
    write_csv(OUT / "vehicles.csv", VEHICLES)
    write_json(OUT / "threat_zones.json", THREAT_ZONES)
    print(f"Wrote 1 depot           -> {OUT/'depots.json'}")
    print(f"Wrote {len(squads)} squads          -> {OUT/'squads.json'}")
    print(f"Wrote {len(VEHICLES)} vehicles        -> {OUT/'vehicles.csv'}")
    print(f"Wrote {len(THREAT_ZONES)} threat zones    -> {OUT/'threat_zones.json'}")


# ---------------------------------------------------------------------------
# Cache-first hero LLM precompute (called at the bottom of __main__)
# ---------------------------------------------------------------------------
def _precompute_briefs():
    """Render the hero brief for each scenario and cache to disk so the
    Streamlit demo path never spins on the LLM. The live "Regenerate" button
    in the UI bypasses cache.
    """
    cache_path = OUT / "cached_briefs.json"
    try:
        # Lazy import — keeps generate.py runnable in a fresh venv (without
        # OPENAI_API_KEY set) for a data-only refresh.
        APP_ROOT = Path(__file__).resolve().parents[1]
        if str(APP_ROOT) not in sys.path:
            sys.path.insert(0, str(APP_ROOT))
        from src.agent import run as agent_run  # type: ignore
    except Exception as e:  # noqa: BLE001
        print(f"[cache] skipping hero precompute (agent import failed: {e})")
        # Write deterministic fallback briefs so the UI always has something.
        cache = {
            s["id"]: {
                "title": s["title"],
                "prompt": s["prompt"],
                "final": _baseline_brief(s["prompt"]),
                "trace": [],
                "cached_from": "fallback",
            }
            for s in SCENARIOS
        }
        write_json(cache_path, cache)
        return

    cache = {}
    for s in SCENARIOS:
        print(f"[cache] precomputing scenario {s['id']!r} ...")
        try:
            out = agent_run(s["prompt"])
            cache[s["id"]] = {
                "title": s["title"],
                "prompt": s["prompt"],
                "final": out.get("final", ""),
                "trace": out.get("trace", []),
                "cached_from": "live_llm",
            }
        except Exception as e:  # noqa: BLE001
            print(f"[cache] live LLM failed for {s['id']}: {e} — using baseline")
            cache[s["id"]] = {
                "title": s["title"],
                "prompt": s["prompt"],
                "final": _baseline_brief(s["prompt"]),
                "trace": [],
                "cached_from": "baseline_fallback",
            }
    write_json(cache_path, cache)
    print(f"[cache] wrote {len(cache)} briefs -> {cache_path}")


def _baseline_brief(prompt: str) -> str:
    """Deterministic hand-written fallback so the UI is never empty."""
    return (
        "**LAST-MILE PUSH BRIEF — CARGO**\n\n"
        "Recommended convoy composition: 2x MTVR (bulk Class I/V) escorted by "
        "1x JLTV (overwatch), with 2x UGV-07 detached for the last-tactical-mile "
        "push to Delta and Echo (broken/wadi terrain).\n\n"
        "Timing: depart FOB Raven 0330L. Transit Route IRON (IED-cleared "
        "corridor) for the southern leg (Foxtrot, Golf, Hotel). Hold Charlie "
        "delivery until after 0800L to clear the UAS observation window over "
        "TZ-01.\n\n"
        "Threat windows: TZ-01 (UAS, NE) active 0500–0800; TZ-02 (sniper, "
        "Charlie cordon) all-day — JLTV speeds the cross at >75 km/h with no "
        "halts; TZ-03 cleared this morning, prefer for southern stops.\n\n"
        "Risk mitigation: unmanned (UGV) push to highest-exposure positions; "
        "armored (JLTV) escort; UAS-window deconfliction on Charlie; redundant "
        "fuel/water on MTVR-01.\n\n"
        "ETA full push complete: T+5.5 h. Fuel burn estimate: ~38 gal across "
        "the convoy. All 8 squads resupplied inside the 48-hour window."
    )


if __name__ == "__main__":
    build_data()
    _precompute_briefs()
