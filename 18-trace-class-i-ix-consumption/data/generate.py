"""TRACE — synthetic data generator for the LogTRACE Class I-IX consumption estimator.

Produces:
  data/doctrine_rates.json    - per-class planning consumption rates
                                (lbs/Marine/day, gal/vehicle/day, etc.) keyed by
                                (climate, opscale).
  data/gcssmc_depots.csv      - 8 synthetic GCSS-MC depots with on-hand inventory
                                per supply class.
  data/scenarios.json         - 3 pre-baked unit-composition scenarios used by
                                cached_briefs.json.
  data/cached_briefs.json     - hero LLM outputs (full Class I-IX consumption
                                estimate + sustainment brief) for each scenario.
                                Cache-first pattern — keeps the demo snappy.

Real-data swap: replace this with ingest of MCWP 4-11 / MCRP 3-40D consumption
planning rate tables and live GCSS-MC depot inventory pulls. See data/load_real.py.

Seeded with random.Random(1776) for reproducibility.
"""
from __future__ import annotations

import json
import os
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
APP_ROOT = ROOT.parent
REPO_ROOT = ROOT.parents[2]
for p in (str(REPO_ROOT), str(APP_ROOT)):
    if p not in sys.path:
        sys.path.insert(0, p)


# ---------------------------------------------------------------------------
# Doctrine consumption planning rates
# ---------------------------------------------------------------------------
# Synthetic stand-in for MCWP 4-11 / MCRP 3-40D consumption planning rates.
# Rates are per-Marine-per-day unless noted. Values vary by climate and opscale
# so the planner UI shows non-trivial spread when you toggle inputs.
#
# Rate units (declared up front so the LLM and the UI can label them):
#   I    : lbs/Marine/day      (subsistence — MREs, UGRs, fresh fruit)
#   II   : lbs/Marine/day      (clothing & individual equipment)
#   III  : gal/Marine/day      (POL — fuel, bulk equiv across vehicles + gen)
#   IV   : lbs/Marine/day      (construction & barrier materials)
#   V    : lbs/Marine/day      (ammunition basic load expenditure)
#   VI   : lbs/Marine/day      (personal demand items — sundries pack)
#   VII  : ea/100Marines/30day (major end items attrition — vehicles/radios)
#   VIII : lbs/Marine/day      (medical supplies)
#   IX   : lbs/Marine/day      (repair parts)
#
# Variance band % is "+/- this much" and the LLM is told to report it.
DOCTRINE_RATES: dict = {
    "rate_units": {
        "I":    "lbs/Marine/day",
        "II":   "lbs/Marine/day",
        "III":  "gal/Marine/day",
        "IV":   "lbs/Marine/day",
        "V":    "lbs/Marine/day",
        "VI":   "lbs/Marine/day",
        "VII":  "ea/100Marines/30day",
        "VIII": "lbs/Marine/day",
        "IX":   "lbs/Marine/day",
    },
    "class_names": {
        "I":    "Subsistence (MREs / UGRs / fresh)",
        "II":   "Clothing & individual equipment",
        "III":  "POL — fuel & lubricants",
        "IV":   "Construction & barrier materials",
        "V":    "Ammunition",
        "VI":   "Personal demand items (sundries)",
        "VII":  "Major end items",
        "VIII": "Medical supplies",
        "IX":   "Repair parts",
    },
    # rates[climate][opscale][class] = (rate, variance_pct)
    "rates": {
        "temperate": {
            "low":    {"I": (4.5, 5),  "II": (0.5, 8),  "III": (1.8, 12), "IV": (1.0, 15), "V":  (2.0, 20), "VI": (0.4, 6),  "VII": (1.2, 25), "VIII": (0.4, 10), "IX": (1.6, 12)},
            "medium": {"I": (4.8, 5),  "II": (0.6, 8),  "III": (3.2, 12), "IV": (1.6, 15), "V":  (8.0, 20), "VI": (0.4, 6),  "VII": (1.8, 25), "VIII": (0.6, 10), "IX": (2.4, 12)},
            "high":   {"I": (5.0, 6),  "II": (0.7, 9),  "III": (5.4, 14), "IV": (2.4, 18), "V": (18.0, 22), "VI": (0.4, 6),  "VII": (2.8, 28), "VIII": (1.0, 12), "IX": (4.0, 15)},
        },
        "tropical": {
            "low":    {"I": (5.0, 5),  "II": (0.7, 8),  "III": (2.0, 12), "IV": (1.1, 15), "V":  (2.2, 20), "VI": (0.6, 6),  "VII": (1.4, 25), "VIII": (0.5, 10), "IX": (1.8, 12)},
            "medium": {"I": (5.4, 5),  "II": (0.8, 8),  "III": (3.6, 12), "IV": (1.8, 15), "V":  (8.8, 20), "VI": (0.6, 6),  "VII": (2.0, 25), "VIII": (0.8, 10), "IX": (2.8, 12)},
            "high":   {"I": (5.6, 6),  "II": (0.9, 9),  "III": (6.0, 14), "IV": (2.6, 18), "V": (19.8, 22), "VI": (0.6, 6),  "VII": (3.2, 28), "VIII": (1.2, 12), "IX": (4.4, 15)},
        },
        "arid": {
            "low":    {"I": (4.8, 5),  "II": (0.6, 8),  "III": (2.2, 12), "IV": (0.9, 15), "V":  (2.0, 20), "VI": (0.5, 6),  "VII": (1.3, 25), "VIII": (0.4, 10), "IX": (1.7, 12)},
            "medium": {"I": (5.2, 5),  "II": (0.7, 8),  "III": (3.8, 12), "IV": (1.4, 15), "V":  (8.4, 20), "VI": (0.5, 6),  "VII": (1.9, 25), "VIII": (0.7, 10), "IX": (2.6, 12)},
            "high":   {"I": (5.4, 6),  "II": (0.8, 9),  "III": (6.4, 14), "IV": (2.2, 18), "V": (19.0, 22), "VI": (0.5, 6),  "VII": (3.0, 28), "VIII": (1.1, 12), "IX": (4.2, 15)},
        },
        "cold_weather": {
            "low":    {"I": (5.6, 5),  "II": (1.1, 8),  "III": (2.8, 12), "IV": (1.2, 15), "V":  (2.2, 20), "VI": (0.5, 6),  "VII": (1.5, 25), "VIII": (0.5, 10), "IX": (2.0, 12)},
            "medium": {"I": (6.0, 5),  "II": (1.3, 8),  "III": (4.6, 12), "IV": (1.9, 15), "V":  (9.0, 20), "VI": (0.5, 6),  "VII": (2.2, 25), "VIII": (0.8, 10), "IX": (3.0, 12)},
            "high":   {"I": (6.2, 6),  "II": (1.5, 9),  "III": (7.2, 14), "IV": (2.8, 18), "V": (20.5, 22), "VI": (0.5, 6),  "VII": (3.4, 28), "VIII": (1.3, 12), "IX": (4.6, 15)},
        },
        "expeditionary_austere": {
            "low":    {"I": (5.2, 6),  "II": (0.8, 9),  "III": (3.0, 14), "IV": (1.4, 18), "V":  (3.0, 22), "VI": (0.5, 8),  "VII": (1.6, 28), "VIII": (0.6, 12), "IX": (2.2, 15)},
            "medium": {"I": (5.6, 6),  "II": (1.0, 9),  "III": (4.4, 14), "IV": (2.2, 18), "V": (10.0, 22), "VI": (0.5, 8),  "VII": (2.4, 28), "VIII": (0.9, 12), "IX": (3.2, 15)},
            "high":   {"I": (5.8, 7),  "II": (1.2, 10), "III": (7.0, 16), "IV": (3.0, 20), "V": (22.0, 25), "VI": (0.5, 8),  "VII": (3.6, 30), "VIII": (1.4, 14), "IX": (4.8, 18)},
        },
    },
}


# ---------------------------------------------------------------------------
# GCSS-MC synthetic depot inventory
# ---------------------------------------------------------------------------
# 8 plausible MARFORLOGCOM nodes. On-hand inventory is per supply class in the
# units appropriate for that class. Marine Depot Maintenance + MCLB locations
# real, inventory numbers synthetic.
DEPOTS: list[dict] = [
    {
        "depot_id": "MCLB-ALB",
        "name": "MCLB Albany",
        "location": "Albany, GA",
        "lat": 31.546,
        "lon": -84.064,
        "role": "Eastern CONUS source-of-supply / depot maintenance",
        "inventory": {
            "I":   {"on_hand": 720000, "unit": "lbs"},
            "II":  {"on_hand":  95000, "unit": "lbs"},
            "III": {"on_hand": 180000, "unit": "gal"},
            "IV":  {"on_hand": 150000, "unit": "lbs"},
            "V":   {"on_hand": 880000, "unit": "lbs"},
            "VI":  {"on_hand":  42000, "unit": "lbs"},
            "VII": {"on_hand":    240, "unit": "ea"},
            "VIII":{"on_hand":  62000, "unit": "lbs"},
            "IX":  {"on_hand": 320000, "unit": "lbs"},
        },
    },
    {
        "depot_id": "MCLB-BAR",
        "name": "MCLB Barstow",
        "location": "Barstow, CA",
        "lat": 34.892,
        "lon": -117.017,
        "role": "Western CONUS source-of-supply / depot maintenance",
        "inventory": {
            "I":   {"on_hand": 640000, "unit": "lbs"},
            "II":  {"on_hand":  88000, "unit": "lbs"},
            "III": {"on_hand": 220000, "unit": "gal"},
            "IV":  {"on_hand": 140000, "unit": "lbs"},
            "V":   {"on_hand": 760000, "unit": "lbs"},
            "VI":  {"on_hand":  38000, "unit": "lbs"},
            "VII": {"on_hand":    210, "unit": "ea"},
            "VIII":{"on_hand":  54000, "unit": "lbs"},
            "IX":  {"on_hand": 290000, "unit": "lbs"},
        },
    },
    {
        "depot_id": "BICMD",
        "name": "Blount Island Command",
        "location": "Jacksonville, FL",
        "lat": 30.405,
        "lon": -81.516,
        "role": "MPF maintenance + afloat pre-positioning hub",
        "inventory": {
            "I":   {"on_hand": 410000, "unit": "lbs"},
            "II":  {"on_hand":  72000, "unit": "lbs"},
            "III": {"on_hand": 480000, "unit": "gal"},
            "IV":  {"on_hand": 200000, "unit": "lbs"},
            "V":   {"on_hand": 920000, "unit": "lbs"},
            "VI":  {"on_hand":  31000, "unit": "lbs"},
            "VII": {"on_hand":    320, "unit": "ea"},
            "VIII":{"on_hand":  44000, "unit": "lbs"},
            "IX":  {"on_hand": 360000, "unit": "lbs"},
        },
    },
    {
        "depot_id": "MCRD-SD",
        "name": "MCRD San Diego SSP",
        "location": "San Diego, CA",
        "lat": 32.737,
        "lon": -117.198,
        "role": "Western recruit-depot supply support point",
        "inventory": {
            "I":   {"on_hand": 220000, "unit": "lbs"},
            "II":  {"on_hand":  56000, "unit": "lbs"},
            "III": {"on_hand":  48000, "unit": "gal"},
            "IV":  {"on_hand":  22000, "unit": "lbs"},
            "V":   {"on_hand":  32000, "unit": "lbs"},
            "VI":  {"on_hand":  18000, "unit": "lbs"},
            "VII": {"on_hand":     46, "unit": "ea"},
            "VIII":{"on_hand":  22000, "unit": "lbs"},
            "IX":  {"on_hand":  46000, "unit": "lbs"},
        },
    },
    {
        "depot_id": "CPEN-SMU",
        "name": "Camp Pendleton SMU",
        "location": "Camp Pendleton, CA",
        "lat": 33.385,
        "lon": -117.567,
        "role": "I MEF supply management unit",
        "inventory": {
            "I":   {"on_hand": 510000, "unit": "lbs"},
            "II":  {"on_hand":  78000, "unit": "lbs"},
            "III": {"on_hand": 160000, "unit": "gal"},
            "IV":  {"on_hand":  92000, "unit": "lbs"},
            "V":   {"on_hand": 540000, "unit": "lbs"},
            "VI":  {"on_hand":  29000, "unit": "lbs"},
            "VII": {"on_hand":    138, "unit": "ea"},
            "VIII":{"on_hand":  38000, "unit": "lbs"},
            "IX":  {"on_hand": 210000, "unit": "lbs"},
        },
    },
    {
        "depot_id": "CLEJ-SMU",
        "name": "Camp Lejeune SMU",
        "location": "Camp Lejeune, NC",
        "lat": 34.685,
        "lon": -77.337,
        "role": "II MEF supply management unit",
        "inventory": {
            "I":   {"on_hand": 540000, "unit": "lbs"},
            "II":  {"on_hand":  82000, "unit": "lbs"},
            "III": {"on_hand": 145000, "unit": "gal"},
            "IV":  {"on_hand":  88000, "unit": "lbs"},
            "V":   {"on_hand": 510000, "unit": "lbs"},
            "VI":  {"on_hand":  31000, "unit": "lbs"},
            "VII": {"on_hand":    146, "unit": "ea"},
            "VIII":{"on_hand":  41000, "unit": "lbs"},
            "IX":  {"on_hand": 232000, "unit": "lbs"},
        },
    },
    {
        "depot_id": "OKI-SMU",
        "name": "MCB Camp Butler SMU (Okinawa)",
        "location": "Okinawa, JPN",
        "lat": 26.298,
        "lon": 127.756,
        "role": "III MEF / forward-deployed Pacific support",
        "inventory": {
            "I":   {"on_hand": 360000, "unit": "lbs"},
            "II":  {"on_hand":  62000, "unit": "lbs"},
            "III": {"on_hand": 110000, "unit": "gal"},
            "IV":  {"on_hand":  64000, "unit": "lbs"},
            "V":   {"on_hand": 380000, "unit": "lbs"},
            "VI":  {"on_hand":  22000, "unit": "lbs"},
            "VII": {"on_hand":     94, "unit": "ea"},
            "VIII":{"on_hand":  29000, "unit": "lbs"},
            "IX":  {"on_hand": 168000, "unit": "lbs"},
        },
    },
    {
        "depot_id": "MEUMPS",
        "name": "MPSRON-3 (afloat, Guam)",
        "location": "Apra Harbor, Guam",
        "lat": 13.443,
        "lon": 144.660,
        "role": "Maritime Pre-positioning Squadron 3 — afloat reach",
        "inventory": {
            "I":   {"on_hand": 290000, "unit": "lbs"},
            "II":  {"on_hand":  48000, "unit": "lbs"},
            "III": {"on_hand": 380000, "unit": "gal"},
            "IV":  {"on_hand": 130000, "unit": "lbs"},
            "V":   {"on_hand": 720000, "unit": "lbs"},
            "VI":  {"on_hand":  20000, "unit": "lbs"},
            "VII": {"on_hand":    180, "unit": "ea"},
            "VIII":{"on_hand":  31000, "unit": "lbs"},
            "IX":  {"on_hand": 240000, "unit": "lbs"},
        },
    },
]


# ---------------------------------------------------------------------------
# Pre-baked scenarios for cached_briefs.json
# ---------------------------------------------------------------------------
SCENARIOS: list[dict] = [
    {
        "id": "meu_soc_30d_tropical_high",
        "label": "MEU(SOC), 2,200 personnel, 30 days, expeditionary austere, tropical high-tempo",
        "unit_type": "MEU(SOC)",
        "personnel": 2200,
        "days": 30,
        "climate": "tropical",
        "opscale": "high",
        "supply_basis": "expeditionary_austere",
    },
    {
        "id": "rct_15d_temperate_medium",
        "label": "RCT, 4,800 personnel, 15 days, temperate, medium tempo",
        "unit_type": "Regimental Combat Team (RCT)",
        "personnel": 4800,
        "days": 15,
        "climate": "temperate",
        "opscale": "medium",
        "supply_basis": "temperate",
    },
    {
        "id": "magtf_60d_arid_high",
        "label": "MAGTF (reinforced), 7,500 personnel, 60 days, arid, high tempo",
        "unit_type": "MAGTF (reinforced)",
        "personnel": 7500,
        "days": 60,
        "climate": "arid",
        "opscale": "high",
        "supply_basis": "arid",
    },
]


# ---------------------------------------------------------------------------
# Deterministic baseline estimator (no LLM dependency).
# ---------------------------------------------------------------------------
def baseline_estimate(scenario: dict, *, doctrine: dict | None = None) -> dict:
    """Compute a fully deterministic Class I-IX consumption estimate.

    Used as the no-LLM fallback so the UI is never blank/spinning.
    Output schema matches the LLM hero call.
    """
    doctrine = doctrine or DOCTRINE_RATES
    climate = scenario["supply_basis"]
    opscale = scenario["opscale"]
    personnel = int(scenario["personnel"])
    days = int(scenario["days"])
    rates = doctrine["rates"][climate][opscale]
    units = doctrine["rate_units"]
    names = doctrine["class_names"]

    classes = []
    for cls in ["I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX"]:
        rate, var_pct = rates[cls]
        unit = units[cls]
        # Class VII is per-100-Marines per 30-day window; everything else per-Marine per-day.
        if cls == "VII":
            daily = rate * (personnel / 100.0) / 30.0
            total = daily * days
            unit_for_total = "ea"
            unit_for_daily = "ea/day"
        else:
            daily = rate * personnel
            total = daily * days
            unit_for_total = unit.split("/")[0]
            unit_for_daily = unit.replace("Marine/", "")  # e.g. "lbs/day"
        classes.append({
            "class": cls,
            "name": names[cls],
            "daily_consumption": round(daily, 1),
            "daily_unit": unit_for_daily,
            "total_30day_or_window": round(total, 1),
            "total_unit": unit_for_total,
            "variance_band_pct": var_pct,
            "rate_basis": f"{rate} {unit}",
            "_source": "baseline",
        })

    # Pre-position sourcing: pick top-3 depots per class by on-hand.
    sourcing = []
    for c in classes:
        cls = c["class"]
        ranked = sorted(DEPOTS, key=lambda d: -d["inventory"][cls]["on_hand"])[:3]
        sources = [
            {
                "depot_id": d["depot_id"],
                "name": d["name"],
                "on_hand": d["inventory"][cls]["on_hand"],
                "unit": d["inventory"][cls]["unit"],
                "covers_pct": min(100.0,
                                  round(100.0 * d["inventory"][cls]["on_hand"]
                                        / max(c["total_30day_or_window"], 1.0), 1)),
            }
            for d in ranked
        ]
        sourcing.append({"class": cls, "sources": sources})

    return {
        "scenario_id": scenario["id"],
        "scenario_label": scenario["label"],
        "personnel": personnel,
        "days": days,
        "climate": scenario["climate"],
        "opscale": opscale,
        "classes": classes,
        "sourcing": sourcing,
        "_source": "baseline",
    }


def baseline_brief(scenario: dict, estimate: dict) -> str:
    """Deterministic OPORD-shaped 1-page Sustainment Estimate Brief.

    Used when the narrator LLM call times out / no cache.
    """
    classes = estimate["classes"]
    cls_by_id = {c["class"]: c for c in classes}
    sourcing_by_id = {s["class"]: s for s in estimate["sourcing"]}

    def line(cls: str) -> str:
        c = cls_by_id[cls]
        top_source = sourcing_by_id[cls]["sources"][0]
        return (f"- **Class {cls} — {c['name']}**: ~{c['total_30day_or_window']:,.0f} "
                f"{c['total_unit']} over {scenario['days']} days "
                f"(±{c['variance_band_pct']}%); primary source **{top_source['name']}** "
                f"({top_source['on_hand']:,} {top_source['unit']} on hand).")

    return (
        f"**SUSTAINMENT ESTIMATE — {scenario['label'].upper()}**\n\n"
        f"## PARA 1 — SITUATION\n"
        f"{scenario['unit_type']} (~{scenario['personnel']:,} personnel) projected for "
        f"{scenario['days']}-day operation in **{scenario['climate']}** environment at "
        f"**{scenario['opscale']}** opscale. Doctrine basis: synthetic stand-in for MCWP 4-11 "
        f"/ MCRP 3-40D consumption planning rates (supply basis: "
        f"`{scenario['supply_basis']}`).\n\n"
        f"## PARA 2 — MISSION\n"
        f"Source, marry, and deliver Class I-IX requirements to the supported MAGTF such that "
        f"≥30 days of authorized supply (DOS) are on the ground or afloat NLT C+0.\n\n"
        f"## PARA 3 — CONSUMPTION ESTIMATE (Class I-IX)\n"
        + "\n".join(line(cls) for cls in ["I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX"])
        + "\n\n"
        f"## PARA 4 — RISKS & CONTINGENCY\n"
        f"- **Class III (POL):** highest variance under high-tempo / hot climate — "
        f"plan +15% contingency reserve and pre-coordinate barge-delivered F-76 fallback.\n"
        f"- **Class V (ammunition):** 22-25% variance band; pre-position basic-load + 1 "
        f"resupply at the nearest MPSRON-3 site.\n"
        f"- **Class IX (repair parts):** demand spikes track maintenance hours; cross-deck "
        f"from MCLB Albany if deployed-MAGTF demand exceeds forecast at C+15.\n"
        f"- **Class VIII (medical):** scale Role-2 capability to climate (heat-cas vs cold-cas).\n\n"
        f"## PARA 5 — SOURCES & SIGNAL\n"
        f"Primary CONUS sources: MCLB Albany / Barstow. Forward sources: MCB Camp Butler "
        f"(Okinawa SMU) and MPSRON-3 (afloat, Guam). Deterministic baseline produced from "
        f"synthetic GCSS-MC depot inventory; the AI engine refines variance and risk callouts "
        f"on demand. Classification: **UNCLASSIFIED // FOR OFFICIAL USE**.\n"
    )


# ---------------------------------------------------------------------------
# Hero LLM precompute — cache-first pattern.
# ---------------------------------------------------------------------------
def _precompute_briefs(*, force: bool = False) -> None:
    """Run the full hero pipeline for each scenario and cache to disk.

    The Streamlit app reads from cache on startup; the live call only fires when
    the user clicks "Regenerate". This keeps the demo recording snappy.
    """
    out_path = ROOT / "cached_briefs.json"
    if out_path.exists() and not force:
        try:
            existing = json.loads(out_path.read_text())
            if all(s["id"] in existing for s in SCENARIOS):
                print(f"[generate] cached_briefs.json already populated ({len(existing)} scenarios). "
                      "Pass --force to rebuild.")
                return
        except Exception:
            pass

    cached: dict = {}
    # Always start from the baseline so cache is non-empty even without a key.
    for sc in SCENARIOS:
        est = baseline_estimate(sc)
        brief_md = baseline_brief(sc, est)
        cached[sc["id"]] = {
            "scenario": sc,
            "estimate": est,
            "brief": brief_md,
            "source": "baseline",
        }

    # Layer the LLM hero call on top, if we have a key.
    try:
        from shared.kamiwaza_client import chat, chat_json  # noqa: WPS433
        have_llm = True
    except Exception as e:
        print(f"[generate] shared client unavailable ({e}); writing baseline-only cache.")
        have_llm = False

    if have_llm and (os.getenv("OPENAI_API_KEY") or os.getenv("KAMIWAZA_BASE_URL")
                     or os.getenv("OPENROUTER_API_KEY") or os.getenv("ANTHROPIC_API_KEY")
                     or os.getenv("LLM_API_KEY")):
        from src.agent import run_hero_pipeline  # local import to avoid cycle  # noqa: WPS433
        for sc in SCENARIOS:
            try:
                print(f"[generate] hero pipeline for {sc['id']} ...")
                hot = run_hero_pipeline(sc, hero=True, use_cache=False)
                cached[sc["id"]] = {
                    "scenario": sc,
                    "estimate": hot["estimate"],
                    "brief": hot["brief"],
                    "source": hot.get("source", "llm"),
                }
            except Exception as e:  # noqa: BLE001
                print(f"[generate]   {sc['id']} hero call failed ({e}); keeping baseline.")
                continue
    else:
        print("[generate] no LLM key in env — cached_briefs.json contains baseline only.")

    out_path.write_text(json.dumps(cached, indent=2))
    print(f"[generate] wrote {out_path} ({len(cached)} scenarios)")


# ---------------------------------------------------------------------------
# Top-level main
# ---------------------------------------------------------------------------
def _write_depots_csv() -> None:
    import csv
    classes = ["I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX"]
    fields = ["depot_id", "name", "location", "lat", "lon", "role"]
    for c in classes:
        fields.extend([f"on_hand_{c}", f"unit_{c}"])
    with (ROOT / "gcssmc_depots.csv").open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(fields)
        for d in DEPOTS:
            row = [d["depot_id"], d["name"], d["location"], d["lat"], d["lon"], d["role"]]
            for c in classes:
                row.extend([d["inventory"][c]["on_hand"], d["inventory"][c]["unit"]])
            w.writerow(row)


def main(*, force: bool = False) -> None:
    rng = random.Random(1776)  # noqa: F841 — reserved for future jitter
    (ROOT / "doctrine_rates.json").write_text(json.dumps(DOCTRINE_RATES, indent=2))
    (ROOT / "depots.json").write_text(json.dumps(DEPOTS, indent=2))
    (ROOT / "scenarios.json").write_text(json.dumps(SCENARIOS, indent=2))
    _write_depots_csv()
    print(f"[generate] wrote doctrine_rates.json, depots.json, scenarios.json, gcssmc_depots.csv")
    _precompute_briefs(force=force)


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true", help="Force rebuild cached_briefs.json")
    args = ap.parse_args()
    main(force=args.force)
