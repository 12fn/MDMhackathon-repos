"""MARINE-MEDIC synthetic data generator.

Produces a full-medical-pipeline dataset that ties together:
  - Medical Supply Inventory v1 (PRBC/FFP/PLT/LTOWB) — ~200 rows w/ expiration
  - Medical Supply Inventory v2 (broader Class VIII) — ~1000 rows
  - Medical Supply Network Data Model — 1 hub + 12 spokes, route status
  - GCSS-MC Supply & Maintenance — synthetic requisition history + lead times

Use cases served (3):
  - DHA RESCUE — joint blood logistics
  - Inventory Control Management — Class VIII accountability
  - LogTRACE — Class VIII consumption forecasting

Plus 5 casualty scenarios for the triage->demand->requisition cascade.

Seed: random.Random(1776). Run from repo root or `cd apps/44-marine-medic`.
"""
from __future__ import annotations

import json
import random
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
APP_ROOT = ROOT.parent
REPO_ROOT = APP_ROOT.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


# ---- Hub --------------------------------------------------------------------

HUB = {
    "id": "APRA-MED",
    "name": "Apra Regional Medical Depot (BUMED / NMRTC Guam)",
    "kind": "hub",
    "country": "Guam (US)",
    "lat": 13.443,
    "lon": 144.660,
    "cold_chain_units": 14,
    "cold_chain_health": 0.92,
    "lab_reagent_days": 21,
    "dry_ice_kg": 4800,
    "max_daily_throughput_units": 1800,
    "role": "Role 3 / Theater Distribution Node",
    "j4_medlog_cell": "III MEF J-4 MEDLOG",
}


# 12 spokes — distributed Marine units (afloat MEU + expeditionary med sites)
SPOKES: list[dict] = [
    {"id": "LHA-6",   "name": "USS America (LHA-6) Role 2E",      "kind": "afloat-l-class",     "role": "Role 2E", "country": "WestPac",        "lat": 17.84, "lon": 142.10, "personnel": 2400, "fridges": 3, "fridge_health": 0.95},
    {"id": "LHD-1",   "name": "USS Wasp (LHD-1) Role 2E",          "kind": "afloat-l-class",     "role": "Role 2E", "country": "WestPac",        "lat": 22.10, "lon": 134.50, "personnel": 2300, "fridges": 3, "fridge_health": 0.78},
    {"id": "LPD-29",  "name": "USS Richard McCool (LPD-29) BAS",   "kind": "afloat-l-class",     "role": "Role 1", "country": "WestPac",        "lat": 19.70, "lon": 138.20, "personnel": 700,  "fridges": 2, "fridge_health": 0.88},
    {"id": "MEU-31",  "name": "31st MEU FRSS (Okinawa)",           "kind": "expeditionary-shore","role": "Role 2 FRSS", "country": "Okinawa (JPN)",   "lat": 26.355, "lon": 127.768,"personnel": 2200, "fridges": 4, "fridge_health": 0.82},
    {"id": "MEU-13",  "name": "13th MEU FRSS (Subic Fwd)",         "kind": "expeditionary-shore","role": "Role 2 FRSS", "country": "Philippines",     "lat": 14.795, "lon": 120.282,"personnel": 2100, "fridges": 3, "fridge_health": 0.71},
    {"id": "EABO-PA", "name": "EABO PALAU BAS (3rd MLR)",          "kind": "rotc-frwd",          "role": "Role 1 BAS", "country": "Palau",           "lat": 7.367,  "lon": 134.544,"personnel": 380,  "fridges": 1, "fridge_health": 0.65},
    {"id": "EABO-TI", "name": "EABO TINIAN BAS (3rd MLR)",         "kind": "rotc-frwd",          "role": "Role 1 BAS", "country": "CNMI (US)",       "lat": 14.998, "lon": 145.620,"personnel": 420,  "fridges": 1, "fridge_health": 0.83},
    {"id": "EABO-IT", "name": "EABO ITBAYAT BAS (4th MLR)",        "kind": "rotc-frwd",          "role": "Role 1 BAS", "country": "Philippines",     "lat": 20.770, "lon": 121.840,"personnel": 290,  "fridges": 1, "fridge_health": 0.59},
    {"id": "EABO-IS", "name": "EABO ISHIGAKI BAS (12th MLR)",      "kind": "rotc-frwd",          "role": "Role 1 BAS", "country": "Ryukyus (JPN)",   "lat": 24.345, "lon": 124.156,"personnel": 340,  "fridges": 1, "fridge_health": 0.74},
    {"id": "MCAS-IW", "name": "MCAS Iwakuni Med Clinic",           "kind": "marine-corps-air",   "role": "Role 2", "country": "Honshu (JPN)",    "lat": 34.144, "lon": 132.235,"personnel": 1700, "fridges": 4, "fridge_health": 0.91},
    {"id": "ROLE3-OK","name": "USNH Okinawa NMRTC (Role 3)",       "kind": "expeditionary-shore","role": "Role 3 NMRTC", "country": "Okinawa (JPN)",   "lat": 26.243, "lon": 127.732,"personnel": 3500, "fridges": 6, "fridge_health": 0.90},
    {"id": "CVN-71",  "name": "USS Theodore Roosevelt (CVN-71) Med", "kind": "afloat-cvn",      "role": "Role 2", "country": "WestPac",         "lat": 16.20, "lon": 140.85, "personnel": 5000, "fridges": 5, "fridge_health": 0.86},
]


# ---- Routes (hub <-> each spoke) -------------------------------------------

def _build_routes(rng: random.Random) -> list[dict]:
    routes = []
    for s in SPOKES:
        d_lat = (s["lat"] - HUB["lat"]) * 60
        d_lon = (s["lon"] - HUB["lon"]) * 60 * 0.97
        nm = round((d_lat * d_lat + d_lon * d_lon) ** 0.5, 0)
        if s["kind"].startswith("afloat") or s["kind"] == "rotc-frwd":
            mode = "rotary+vertrep" if nm < 600 else "fixed-wing+rotary"
        elif s["kind"] == "marine-corps-air":
            mode = "fixed-wing"
        else:
            mode = "fixed-wing"
        lift = rng.choice(["GREEN", "GREEN", "AMBER", "AMBER", "RED"])
        cct_risk = round(rng.uniform(0.05, 0.45), 2)
        leg_h = round(nm / rng.uniform(180, 320), 1)
        routes.append({
            "spoke_id": s["id"],
            "mode": mode,
            "distance_nm": nm,
            "leg_hours": leg_h,
            "lift_status": lift,
            "cold_chain_transit_risk": cct_risk,
            "last_resupply_h_ago": rng.randint(6, 96),
        })
    return routes


# ---- Inventory v1 — blood components (~200 rows w/ expiration) -------------

PRODUCTS_V1 = ["PRBC", "FFP", "PLASMA", "PLT", "LTOWB"]


def _inventory_v1(rng: random.Random) -> list[dict]:
    """200-row blood-product ledger (PRBC/FFP/PLASMA/PLT/LTOWB)."""
    rows: list[dict] = []
    base = datetime.now(timezone.utc).replace(microsecond=0)
    sites = [HUB["id"], *(s["id"] for s in SPOKES)]
    spec = {"PRBC": (35, 0.9), "FFP": (365, 0.55), "PLASMA": (365, 0.55),
            "PLT": (6, 0.45), "LTOWB": (21, 0.7)}
    n = 0
    while len(rows) < 200:
        site = rng.choice(sites)
        prod = rng.choice(PRODUCTS_V1)
        shelf, cons_rate = spec[prod]
        units = rng.randint(2, 28)
        exp = base + timedelta(days=rng.randint(1, max(2, shelf - 2)))
        # cold-chain
        roll = rng.random()
        cc = "GREEN" if roll < 0.74 else ("AMBER" if roll < 0.93 else "RED")
        cons = round(cons_rate * rng.uniform(0.6, 1.6), 2)
        dos = round(units / max(0.05, cons), 1)
        rows.append({
            "row_id": f"BLD-{n:04d}",
            "site_id": site,
            "product": prod,
            "units": units,
            "lot": f"LOT-{rng.randint(1000, 9999)}",
            "expires_iso": exp.isoformat(),
            "cold_chain_status": cc,
            "daily_consumption": cons,
            "days_of_supply": dos,
            "iso_donor_screened": rng.random() > 0.05,
        })
        n += 1
    return rows


# ---- Inventory v2 — broader Class VIII (~1000 rows) ------------------------

CLASS_VIII_ITEMS = [
    # (NSN-prefix, nomenclature, unit, daily-use-base, sensitivity)
    ("6505-01", "Tranexamic Acid 1g IV (TXA)",                "vial", 1.4, "ROUTINE"),
    ("6505-01", "Ketamine 500mg/10mL inj",                    "vial", 0.6, "CONTROLLED"),
    ("6505-01", "Fentanyl 100mcg lozenge",                    "ea",   1.1, "CONTROLLED"),
    ("6505-01", "Calcium Gluconate 1g IV",                    "vial", 0.9, "ROUTINE"),
    ("6505-01", "Cefazolin 1g IV (antibiotic)",               "vial", 1.6, "ROUTINE"),
    ("6505-01", "Ertapenem 1g IV",                            "vial", 0.4, "ROUTINE"),
    ("6505-01", "Hextend 500mL colloid",                      "bag",  0.7, "ROUTINE"),
    ("6505-01", "Plasma-Lyte 1L IV crystalloid",              "bag",  3.2, "ROUTINE"),
    ("6505-01", "Lactated Ringers 1L IV",                     "bag",  3.6, "ROUTINE"),
    ("6510-01", "Combat Application Tourniquet (CAT-7)",      "ea",   2.1, "ROUTINE"),
    ("6510-01", "Junctional Tourniquet (SAM JTQ)",            "ea",   0.3, "ROUTINE"),
    ("6510-01", "Combat Gauze (QuikClot)",                    "ea",   2.6, "ROUTINE"),
    ("6510-01", "Israeli Emergency Bandage 6\"",              "ea",   2.2, "ROUTINE"),
    ("6510-01", "Chest Seal HALO occlusive",                  "ea",   1.0, "ROUTINE"),
    ("6510-01", "Needle Decompression 14ga 3.25\"",           "ea",   0.4, "ROUTINE"),
    ("6515-01", "Surgical Set, FRSS Damage Control",          "set",  0.18, "SENSITIVE"),
    ("6515-01", "Cricothyroidotomy Kit",                      "set",  0.25, "ROUTINE"),
    ("6515-01", "IO Access Kit (FAST-1 sternal)",             "set",  0.35, "ROUTINE"),
    ("6515-01", "SAM Splint Set (large)",                     "set",  0.9, "ROUTINE"),
    ("6515-01", "Pelvic Binder (SAM)",                        "ea",   0.4, "ROUTINE"),
    ("6515-01", "Burn Sheet, Sterile 60x90",                  "ea",   0.5, "ROUTINE"),
    ("6515-01", "CBRN Atropine/2-PAM Auto-Injector",          "ea",   0.2, "SENSITIVE"),
    ("6515-01", "Naloxone 4mg IN auto-spray",                 "ea",   0.6, "CONTROLLED"),
    ("6505-01", "Vancomycin 1g IV",                           "vial", 0.5, "ROUTINE"),
    ("6505-01", "Sodium Chloride 0.9% 1L",                    "bag",  4.0, "ROUTINE"),
]

LOCATIONS = [
    "APRA-MED", "LHA-6", "LHD-1", "LPD-29", "MEU-31", "MEU-13",
    "EABO-PA", "EABO-TI", "EABO-IT", "EABO-IS", "MCAS-IW", "ROLE3-OK", "CVN-71",
]


def _inventory_v2(rng: random.Random) -> list[dict]:
    """~1000 row broader Class VIII inventory (the v2 dataset stand-in)."""
    rows: list[dict] = []
    base = datetime.now(timezone.utc).replace(microsecond=0)
    n = 0
    while len(rows) < 1000:
        prefix, nomen, unit, daily_base, sens = rng.choice(CLASS_VIII_ITEMS)
        site = rng.choice(LOCATIONS)
        nsn = f"{prefix}-{rng.randint(100, 999)}-{rng.randint(1000, 9999)}"
        qty_on_hand = rng.randint(2, 360)
        qty_required = qty_on_hand + rng.randint(-30, 80)
        shortage = max(0, qty_required - qty_on_hand)
        cond = rng.choices(["A", "B", "C", "F"], weights=[78, 14, 5, 3])[0]
        # Burn rate scaled by site type
        site_scale = 1.0
        if site.startswith("EABO"):
            site_scale = 0.6
        elif site in ("CVN-71", "ROLE3-OK"):
            site_scale = 1.8
        elif site == "APRA-MED":
            site_scale = 2.4
        burn = round(daily_base * site_scale * rng.uniform(0.7, 1.4), 2)
        dos = round(qty_on_hand / max(0.1, burn), 1)
        # expiration applies to drugs/fluids; sets/devices use "calibration_due"
        if "Set" in nomen or "Kit" in nomen or "Tourniquet" in nomen or "Splint" in nomen or "Binder" in nomen or "Sheet" in nomen or "Seal" in nomen or "Gauze" in nomen or "Bandage" in nomen or "Decompression" in nomen:
            exp = base + timedelta(days=rng.randint(60, 1100))
        else:
            exp = base + timedelta(days=rng.randint(20, 540))
        rows.append({
            "item_id": f"CL8-{n:05d}",
            "nsn": nsn,
            "nomenclature": nomen,
            "unit": unit,
            "site_id": site,
            "qty_on_hand": qty_on_hand,
            "qty_required": qty_required,
            "shortage": shortage,
            "condition_code": cond,
            "sensitivity_class": sens,
            "burn_rate_per_day": burn,
            "days_of_supply": dos,
            "expires_iso": exp.isoformat(),
            "lot": f"LOT-{rng.randint(10000, 99999)}",
            "nmc_impacting": (cond == "F" and "Set" in nomen),
        })
        n += 1
    return rows


# ---- Supply Network Data Model (graph) -------------------------------------

def _supply_network(routes: list[dict]) -> dict:
    """Hub-spoke relationships, route status, lift availability — JSON shape
    matches the LOGCOM 'Medical Supply Network Data Model' (synthetic stand-in)."""
    return {
        "as_of": datetime.now(timezone.utc).isoformat(),
        "hub": HUB,
        "spokes": SPOKES,
        "edges": [
            {
                "edge_id": f"EDGE-{i:02d}",
                "source": HUB["id"],
                "target": r["spoke_id"],
                "mode": r["mode"],
                "distance_nm": r["distance_nm"],
                "leg_hours": r["leg_hours"],
                "lift_status": r["lift_status"],
                "cold_chain_transit_risk": r["cold_chain_transit_risk"],
                "last_resupply_h_ago": r["last_resupply_h_ago"],
            }
            for i, r in enumerate(routes)
        ],
    }


# ---- GCSS-MC requisition / maintenance synth -------------------------------

def _gcss_mc_requisitions(rng: random.Random) -> list[dict]:
    """Synthetic GCSS-MC Class VIII requisition + maintenance log."""
    rows = []
    statuses = ["BO", "OPN", "REC", "SHP", "CLS"]  # backorder/open/received/shipped/closed
    priorities = ["01", "03", "06", "09", "12"]    # FAD I-V
    for i in range(180):
        prefix, nomen, unit, _, _ = rng.choice(CLASS_VIII_ITEMS)
        nsn = f"{prefix}-{rng.randint(100, 999)}-{rng.randint(1000, 9999)}"
        site = rng.choice(LOCATIONS)
        qty = rng.randint(1, 60)
        status = rng.choice(statuses)
        priority = rng.choice(priorities)
        lead_h = rng.randint(8, 240)
        rows.append({
            "doc_id": f"DOC-{rng.randint(100000, 999999)}",
            "nsn": nsn,
            "nomenclature": nomen,
            "ric_to": "SMS",
            "ship_to_uic": site,
            "qty": qty,
            "uoi": unit,
            "status": status,
            "priority": priority,
            "submitted_iso": (datetime.now(timezone.utc) - timedelta(hours=rng.randint(2, 600))).isoformat(),
            "lead_time_h_estimate": lead_h,
            "source_depot": rng.choice(["DDJC-Tracy", "DDSP-Mechanicsburg", "DDPM-PugetSound", "APRA-MED"]),
        })
    return rows


# ---- Casualty scenarios (5) ------------------------------------------------

CASUALTY_SCENARIOS = [
    {
        "id": "squad_ambush",
        "label": "Squad ambush — small-arms TIC",
        "frame": "13-Marine squad ambushed at EABO ITBAYAT (Batanes). 9 WIA, mixed extremity GSW + 1 thoracic.",
        "location_id": "EABO-IT",
        "wia_count": 9,
        "injury_mix": {"penetrating_extremity": 5, "penetrating_thoracic": 1, "blast_concussive": 2, "minor": 1},
        "hours_to_evac_estimate": 6,
    },
    {
        "id": "he_blast_mascal",
        "label": "HE blast MASCAL — IDF on FRSS",
        "frame": "Sustained indirect-fire impact on 13th MEU FRSS (Subic Fwd). 22 WIA, blast/poly-trauma heavy.",
        "location_id": "MEU-13",
        "wia_count": 22,
        "injury_mix": {"penetrating_extremity": 6, "penetrating_thoracic": 4, "blast_concussive": 8, "burn_secondary": 3, "minor": 1},
        "hours_to_evac_estimate": 4,
    },
    {
        "id": "burn_mascal",
        "label": "Burn MASCAL — fuel fire aboard LHD-1",
        "frame": "Fuel-cell fire aboard USS Wasp. 14 WIA, predominantly thermal burns >20% TBSA.",
        "location_id": "LHD-1",
        "wia_count": 14,
        "injury_mix": {"burn_major": 6, "burn_minor": 5, "inhalation_injury": 3},
        "hours_to_evac_estimate": 8,
    },
    {
        "id": "cbrn_event",
        "label": "CBRN exposure — chemical agent (suspected GA)",
        "frame": "Suspected nerve-agent exposure during HA/DR support, EABO PALAU. 18 WIA, CBRN protocol in effect.",
        "location_id": "EABO-PA",
        "wia_count": 18,
        "injury_mix": {"chem_nerve_agent": 12, "chem_pulmonary": 4, "minor": 2},
        "hours_to_evac_estimate": 12,
    },
    {
        "id": "mvi_rollover",
        "label": "MVI rollover — convoy MTVR rollover",
        "frame": "Convoy MTVR rollover at MCAS Iwakuni perimeter. 7 WIA, blunt trauma + 1 spine.",
        "location_id": "MCAS-IW",
        "wia_count": 7,
        "injury_mix": {"blunt_polytrauma": 4, "spine_suspected": 1, "blast_concussive": 0, "minor": 2},
        "hours_to_evac_estimate": 3,
    },
]


# ---- TCCC / JTS doctrine reference -----------------------------------------

TRIAGE_DOCTRINE = {
    "categories": [
        {"code": "ROUTINE",          "ttl_h": 24, "color": "#9AD3FF", "description": "Stable; can wait > 4h for surgical care."},
        {"code": "PRIORITY",         "ttl_h": 4,  "color": "#E0B341", "description": "Stable but requires surgical care within 4h."},
        {"code": "URGENT",           "ttl_h": 2,  "color": "#E36F2C", "description": "Life-threatening; needs intervention <= 2h."},
        {"code": "URGENT_SURGICAL", "ttl_h": 1,  "color": "#D8362F", "description": "Needs damage-control surgery <= 1h."},
        {"code": "EXPECTANT",        "ttl_h": 0,  "color": "#888888", "description": "Survival unlikely with available resources; comfort care."},
    ],
    "role_thresholds": {
        "Role 1 BAS":     {"capability": "TCCC stabilization, TXA, tourniquet, blood TQ, casualty evac call",
                            "max_dwell_h": 1},
        "Role 2 FRSS":    {"capability": "Damage control surgery, walking blood bank, 8h holding",
                            "max_dwell_h": 8},
        "Role 2E":        {"capability": "Enhanced surgical, 24-72h holding, ICU lite",
                            "max_dwell_h": 72},
        "Role 3 NMRTC":   {"capability": "Definitive surgical / specialty care, ICU, full lab",
                            "max_dwell_h": 168},
    },
    "class_viii_planning_factors_per_wia": {
        "penetrating_extremity":  {"PRBC": 2, "FFP": 1, "PLT": 0.0, "LTOWB": 0, "TXA_g": 1, "tourniquets": 1, "fluids_L": 1.5, "antibiotic_doses": 1, "splint_set": 1},
        "penetrating_thoracic":   {"PRBC": 6, "FFP": 4, "PLT": 1.0, "LTOWB": 2, "TXA_g": 2, "tourniquets": 0, "fluids_L": 2.5, "antibiotic_doses": 2, "surgical_set": 1},
        "blast_concussive":       {"PRBC": 1, "FFP": 0, "PLT": 0.0, "LTOWB": 0, "TXA_g": 1, "tourniquets": 0, "fluids_L": 1.0, "antibiotic_doses": 0},
        "burn_major":             {"PRBC": 2, "FFP": 2, "PLT": 0.0, "LTOWB": 0, "TXA_g": 0, "tourniquets": 0, "fluids_L": 8.0, "antibiotic_doses": 2, "burn_sheet": 2},
        "burn_minor":             {"PRBC": 0, "FFP": 0, "PLT": 0.0, "LTOWB": 0, "TXA_g": 0, "tourniquets": 0, "fluids_L": 2.0, "antibiotic_doses": 1, "burn_sheet": 1},
        "burn_secondary":         {"PRBC": 1, "FFP": 1, "PLT": 0.0, "LTOWB": 0, "TXA_g": 0, "tourniquets": 0, "fluids_L": 3.0, "antibiotic_doses": 1, "burn_sheet": 1},
        "inhalation_injury":      {"PRBC": 0, "FFP": 0, "PLT": 0.0, "LTOWB": 0, "TXA_g": 0, "tourniquets": 0, "fluids_L": 1.5, "antibiotic_doses": 1},
        "chem_nerve_agent":       {"PRBC": 0, "FFP": 0, "PLT": 0.0, "LTOWB": 0, "TXA_g": 0, "atropine_kits": 3, "fluids_L": 1.0, "antibiotic_doses": 0},
        "chem_pulmonary":         {"PRBC": 0, "FFP": 0, "PLT": 0.0, "LTOWB": 0, "TXA_g": 0, "fluids_L": 1.0, "antibiotic_doses": 1},
        "blunt_polytrauma":       {"PRBC": 4, "FFP": 2, "PLT": 0.5, "LTOWB": 1, "TXA_g": 2, "tourniquets": 0, "fluids_L": 2.0, "antibiotic_doses": 1, "surgical_set": 1, "splint_set": 1},
        "spine_suspected":        {"PRBC": 1, "FFP": 0, "PLT": 0.0, "LTOWB": 0, "TXA_g": 1, "tourniquets": 0, "fluids_L": 1.5, "antibiotic_doses": 0, "splint_set": 1},
        "minor":                  {"PRBC": 0, "FFP": 0, "PLT": 0.0, "LTOWB": 0, "TXA_g": 0, "tourniquets": 0, "fluids_L": 0.5, "antibiotic_doses": 0},
    },
    "triage_assignment_rules": {
        "penetrating_extremity":  "PRIORITY",
        "penetrating_thoracic":   "URGENT_SURGICAL",
        "blast_concussive":       "ROUTINE",
        "burn_major":             "URGENT_SURGICAL",
        "burn_minor":             "PRIORITY",
        "burn_secondary":         "PRIORITY",
        "inhalation_injury":      "URGENT",
        "chem_nerve_agent":       "URGENT",
        "chem_pulmonary":         "PRIORITY",
        "blunt_polytrauma":       "URGENT",
        "spine_suspected":        "PRIORITY",
        "minor":                  "ROUTINE",
    },
    "role_assignment_rules": {
        "ROUTINE":         "Role 1 BAS",
        "PRIORITY":        "Role 2 FRSS",
        "URGENT":          "Role 2E",
        "URGENT_SURGICAL": "Role 3 NMRTC",
        "EXPECTANT":       "Role 1 BAS",
    },
}


# ---- Buy-on-market vendors --------------------------------------------------

VENDORS: list[dict] = [
    {"id": "V-DRYICE-01",  "name": "Pacific Cold Chain Logistics (Guam)",
     "country": "Guam (US)", "supplies": ["dry_ice", "gel_packs", "cold-chain-couriers"],
     "lead_time_h": 6,  "trust": "HIGH", "contract_vehicle": "GSA Schedule 51V",
     "notes": "Pre-negotiated 24x7 dispatch from Apra; approved by NAVMED Logistics."},
    {"id": "V-REAGENT-02", "name": "Roche Diagnostics APAC (HCMC)",
     "country": "Vietnam", "supplies": ["lab_reagents", "donor-screening-kits"],
     "lead_time_h": 36, "trust": "HIGH", "contract_vehicle": "DLA Troop Support BPA",
     "notes": "Host-nation procurement vehicle in place; air-lift to APRA via PACAF."},
    {"id": "V-LIFT-03",    "name": "Berry Aviation (Contracted Cargo)",
     "country": "USA",    "supplies": ["fixed-wing-lift", "rotary-lift"],
     "lead_time_h": 12, "trust": "HIGH", "contract_vehicle": "AMC TRANSCOM CRAF Stage I",
     "notes": "Surge contract aviation for inter-island med resupply."},
    {"id": "V-DONOR-04",   "name": "JSDF Self-Defense Med Supply (Okinawa)",
     "country": "Japan",  "supplies": ["LTOWB", "donor-network", "PRBC"],
     "lead_time_h": 18, "trust": "MODERATE", "contract_vehicle": "ACSA cross-servicing",
     "notes": "ACSA blood swap, JSDF Naha — walking blood bank standby roster."},
    {"id": "V-COURIER-05", "name": "FedEx Express Critical (Manila)",
     "country": "Philippines", "supplies": ["cold-chain-couriers", "validated-shippers"],
     "lead_time_h": 8,  "trust": "MODERATE", "contract_vehicle": "Open-market spot",
     "notes": "Cleared for class VIIIa shipment; SLA 8h Manila->WestPac spokes."},
    {"id": "V-FRIDGE-06",  "name": "Helmer Scientific (Field Refrigeration)",
     "country": "USA",    "supplies": ["field-refrigerators", "spares"],
     "lead_time_h": 72, "trust": "HIGH", "contract_vehicle": "DLA Troop Support direct",
     "notes": "Air-droppable Pelican-style cold boxes; 72h DLOA."},
    {"id": "V-SURG-07",    "name": "Stryker Field Surgical (APAC)",
     "country": "Singapore", "supplies": ["surgical_sets", "damage_control_kits"],
     "lead_time_h": 24, "trust": "HIGH", "contract_vehicle": "DLA Troop Support BPA",
     "notes": "Pre-positioned damage-control surgical sets; SLA 24h to ROLE3-OK."},
]


# ---- Cached briefs (precomputed hero outputs) ------------------------------

def _baseline_brief(scenario: dict, demand: dict, gap: dict) -> str:
    """Deterministic Medical Sustainment Action Brief — fallback when LLM
    times out. Same shape as the live hero brief."""
    top_gap_lines = [
        f"- **{g['item']}**: need {g['need']:.1f} {g['unit']}, on-hand {g['on_hand']:.1f} {g['unit']}, "
        f"shortfall **{g['shortfall']:.1f} {g['unit']}** (24h window)"
        for g in gap.get("top_shortfalls", [])[:5]
    ]
    cas = scenario.get("wia_count", 0)
    loc = scenario.get("location_id", "")
    return (
        f"# MEDICAL SUSTAINMENT ACTION BRIEF\n"
        f"**Scenario:** {scenario.get('label', '')}\n"
        f"**Frame:** {scenario.get('frame', '')}\n"
        f"**DTG:** {datetime.now(timezone.utc).strftime('%d%H%MZ %b %Y').upper()}\n"
        f"**Classification:** UNCLASSIFIED // FOR OFFICIAL USE\n\n"
        f"**BLUF:** {cas} WIA inbound from {loc}. Class VIII demand projects "
        f"**{demand.get('total_prbc_units', 0):.0f} PRBC**, "
        f"**{demand.get('total_ffp_units', 0):.0f} FFP**, "
        f"**{demand.get('total_fluids_L', 0):.0f} L** crystalloid in next 24h. "
        f"Hub-spoke check identifies **{len(gap.get('top_shortfalls', []))}** sustainment gaps; "
        f"recommend immediate APRA-hub vertical replenishment + "
        f"V-DONOR-04 (JSDF Naha) ACSA pull for LTOWB.\n\n"
        f"## Casualty-flow projection (Role 1 -> 2 -> 2E -> 3)\n"
        f"- Role 1 BAS holding: TCCC stabilization, TXA, tourniquets, IV crystalloid push.\n"
        f"- Role 2 FRSS handoff: damage control surgery for URGENT and URGENT_SURGICAL casualties.\n"
        f"- Role 2E afloat (LHA-6 / LHD-1): 24-72h ICU-lite holding for thoracic + burn cohort.\n"
        f"- Role 3 NMRTC (USNH Okinawa): definitive surgical, blood bank, ICU.\n"
        f"- Bottleneck: Role 2 FRSS surgical-set throughput; mitigate via lateral pull from MEU-31.\n\n"
        f"## Class VIII gap (24h)\n"
        + ("\n".join(top_gap_lines) if top_gap_lines else "- No critical shortfalls under current posture.")
        + "\n\n"
        f"## Supplier action plan\n"
        f"1. **V-DRYICE-01** (Pacific Cold Chain, 6h lead) — surge dry-ice 800 kg to APRA-MED for cold-chain regen.\n"
        f"2. **V-DONOR-04** (JSDF Naha ACSA) — pull 40 LTOWB units; activate walking blood bank at MEU-31 / ROLE3-OK.\n"
        f"3. **V-SURG-07** (Stryker Singapore, 24h lead) — pre-stage 4 damage-control surgical sets to Role 3 NMRTC.\n"
        f"4. **V-LIFT-03** (Berry Aviation CRAF Stage I) — surge fixed-wing lift APRA->MEU-13 for 48h.\n\n"
        f"## Regional-hub posture\n"
        f"APRA-MED holding **1,800 units/day** throughput; **21d** lab reagent reserve; "
        f"cold-chain health 0.92. III MEF J-4 MEDLOG informed; NAVMED BUMED confirms ACSA channel ready.\n\n"
        f"## Mortality risk window\n"
        f"If no resupply action taken within **{scenario.get('hours_to_evac_estimate', 6)} hours**, "
        f"expected mortality climbs from baseline ~6% to ~14% across the URGENT_SURGICAL cohort, "
        f"driven by Class VIIIa stockout (PRBC + FFP) at receiving Role 2E node.\n\n"
        f"## Posture\n"
        f"Running on a Kamiwaza-deployed hero model behind `KAMIWAZA_BASE_URL`. "
        f"Casualty data stays in IL5/IL6 enclave — never leaves the accredited environment. "
        f"Hash-chained audit per HIPAA / NDAA Section 1739.\n"
    )


def _projected_demand(scenario: dict) -> dict:
    """Precompute Class VIII demand for this scenario (1/6/12/24h time-phased)."""
    pf = TRIAGE_DOCTRINE["class_viii_planning_factors_per_wia"]
    totals = {"PRBC": 0.0, "FFP": 0.0, "PLT": 0.0, "LTOWB": 0.0,
              "TXA_g": 0.0, "tourniquets": 0.0, "fluids_L": 0.0,
              "antibiotic_doses": 0.0, "surgical_set": 0.0,
              "splint_set": 0.0, "burn_sheet": 0.0, "atropine_kits": 0.0}
    for inj_kind, count in scenario["injury_mix"].items():
        for k, v in pf.get(inj_kind, {}).items():
            totals[k] = totals.get(k, 0.0) + v * count
    # Time-phased (1h, 6h, 12h, 24h cumulative fractions)
    phased = {h: {k: round(v * frac, 2) for k, v in totals.items()}
              for h, frac in [(1, 0.55), (6, 0.78), (12, 0.92), (24, 1.0)]}
    return {
        "total_prbc_units": round(totals.get("PRBC", 0), 1),
        "total_ffp_units":  round(totals.get("FFP", 0), 1),
        "total_plt_units":  round(totals.get("PLT", 0), 1),
        "total_ltowb_units":round(totals.get("LTOWB", 0), 1),
        "total_fluids_L":   round(totals.get("fluids_L", 0), 1),
        "total_txa_g":      round(totals.get("TXA_g", 0), 1),
        "total_tourniquets":round(totals.get("tourniquets", 0), 1),
        "total_antibiotic_doses": round(totals.get("antibiotic_doses", 0), 1),
        "total_surgical_sets":    round(totals.get("surgical_set", 0), 1),
        "total_splint_sets":      round(totals.get("splint_set", 0), 1),
        "total_burn_sheets":      round(totals.get("burn_sheet", 0), 1),
        "total_atropine_kits":    round(totals.get("atropine_kits", 0), 1),
        "time_phased":  phased,
        "totals_raw":   totals,
    }


def _hub_spoke_gap(scenario: dict, demand: dict, inv_v1: list[dict],
                   inv_v2: list[dict]) -> dict:
    """Find shortfalls between projected 24h demand and on-hand at the receiving
    spoke + APRA hub combined."""
    site = scenario["location_id"]
    on_hand = {"PRBC": 0.0, "FFP": 0.0, "PLT": 0.0, "LTOWB": 0.0,
               "tourniquets": 0.0, "fluids_L": 0.0, "antibiotic_doses": 0.0,
               "surgical_set": 0.0, "splint_set": 0.0, "burn_sheet": 0.0,
               "atropine_kits": 0.0, "TXA_g": 0.0}
    # Blood from v1 — count units at receiving spoke + hub
    for r in inv_v1:
        if r["site_id"] in (site, "APRA-MED") and r["product"] in ("PRBC", "FFP", "PLT", "LTOWB"):
            on_hand[r["product"]] += r["units"]
    # Class VIII v2 — buckets by nomenclature contains
    for r in inv_v2:
        if r["site_id"] not in (site, "APRA-MED"):
            continue
        nom = r["nomenclature"].lower()
        qty = r["qty_on_hand"]
        if "tourniquet" in nom:        on_hand["tourniquets"]   += qty
        elif "ringer" in nom or "plasma-lyte" in nom or "sodium chloride" in nom or "hextend" in nom:
            on_hand["fluids_L"]        += qty
        elif "cefazolin" in nom or "ertapenem" in nom or "vancomycin" in nom:
            on_hand["antibiotic_doses"]+= qty
        elif "surgical set" in nom or "damage control" in nom:
            on_hand["surgical_set"]    += qty
        elif "sam splint" in nom or "splint set" in nom:
            on_hand["splint_set"]      += qty
        elif "burn sheet" in nom:      on_hand["burn_sheet"]    += qty
        elif "atropine" in nom or "2-pam" in nom:
            on_hand["atropine_kits"]   += qty
        elif "tranexamic" in nom or "txa" in nom:
            on_hand["TXA_g"]           += qty

    need = {
        "PRBC":    demand["total_prbc_units"],
        "FFP":     demand["total_ffp_units"],
        "PLT":     demand["total_plt_units"],
        "LTOWB":   demand["total_ltowb_units"],
        "fluids_L":demand["total_fluids_L"],
        "TXA_g":   demand["total_txa_g"],
        "tourniquets": demand["total_tourniquets"],
        "antibiotic_doses": demand["total_antibiotic_doses"],
        "surgical_set":     demand["total_surgical_sets"],
        "splint_set":       demand["total_splint_sets"],
        "burn_sheet":       demand["total_burn_sheets"],
        "atropine_kits":    demand["total_atropine_kits"],
    }
    units = {"PRBC": "units", "FFP": "units", "PLT": "units", "LTOWB": "units",
             "fluids_L": "L", "TXA_g": "g", "tourniquets": "ea",
             "antibiotic_doses": "doses", "surgical_set": "sets",
             "splint_set": "sets", "burn_sheet": "ea", "atropine_kits": "kits"}
    shortfalls = []
    for k, v in need.items():
        if v <= 0:
            continue
        oh = on_hand.get(k, 0.0)
        sf = max(0.0, v - oh)
        if sf > 0:
            shortfalls.append({
                "item": k, "need": v, "on_hand": oh,
                "shortfall": sf, "unit": units.get(k, ""),
            })
    shortfalls.sort(key=lambda r: r["shortfall"], reverse=True)
    return {
        "receiving_site": site,
        "on_hand_summary": on_hand,
        "top_shortfalls": shortfalls[:8],
        "total_shortfalls": len(shortfalls),
    }


def _gcss_requisition(scenario: dict, gap: dict) -> dict:
    """Auto-build a GCSS-MC requisition for the top shortfalls."""
    lines = []
    for i, sf in enumerate(gap.get("top_shortfalls", [])[:6]):
        lines.append({
            "doc_id": f"DOC-{900000 + i + scenario.get('wia_count', 0):06d}",
            "nsn_class": f"6505-01-{500 + i:03d}-{1000 + i*7:04d}",
            "nomenclature": sf["item"],
            "qty": int(sf["shortfall"] + 1),
            "uoi": sf["unit"],
            "priority": "01" if sf["item"] in ("PRBC", "FFP", "LTOWB") else "03",
            "ric_to": "SMS",
            "ship_to_uic": gap.get("receiving_site", ""),
            "source_depot": "APRA-MED" if sf["item"] in ("PRBC", "FFP", "PLT", "LTOWB") else "DDJC-Tracy",
            "lead_time_h_estimate": 6 if sf["item"] in ("PRBC", "FFP", "LTOWB") else 24,
            "submitted_iso": datetime.now(timezone.utc).isoformat(),
        })
    return {"scenario_id": scenario["id"], "lines": lines,
            "submitted_iso": datetime.now(timezone.utc).isoformat()}


def _precompute_briefs(inv_v1: list[dict], inv_v2: list[dict]) -> dict:
    """Hero-call brief per scenario; deterministic fallback if no LLM."""
    briefs: dict = {}
    try:
        from shared.kamiwaza_client import chat
        llm_ok = True
    except Exception:
        llm_ok = False

    SYS = (
        "You are MARINE-MEDIC, the Joint Class VIII / Casualty-Flow Decision-"
        "Support agent for USMC LOGCOM, BUMED, and the Defense Health Agency, "
        "supporting USINDOPACOM Distributed Maritime Operations. Use TCCC, JTS, "
        "FRSS / BAS / Role 1-3, LTOWB, walking blood bank, NMRTC, BUMED, "
        "ASCA cross-servicing, J-4 MEDLOG, NAVMED terminology verbatim.\n\n"
        "Compose a polished one-page MEDICAL SUSTAINMENT ACTION BRIEF in markdown "
        "with these EXACT sections, in order:\n"
        "  - **BLUF:** one bold sentence at the top\n"
        "  - ## Casualty-flow projection (Role 1 -> 2 -> 2E -> 3)\n"
        "  - ## Class VIII gap (24h)\n"
        "  - ## Supplier action plan\n"
        "  - ## Regional-hub posture\n"
        "  - ## Mortality risk window\n"
        "  - ## Posture (one paragraph: on-prem Kamiwaza Stack, IL5/IL6 ready, "
        "    casualty data never leaves the accredited environment)\n\n"
        "Cite specific shortfalls (units, liters, doses), specific Roles of care, "
        "and specific approved buy-on-market vendors by id (V-DRYICE-01, "
        "V-REAGENT-02, V-LIFT-03, V-DONOR-04, V-COURIER-05, V-FRIDGE-06, V-SURG-07). "
        "Total length <= 550 words. Classification: UNCLASSIFIED // FOR OFFICIAL USE."
    )

    for scn in CASUALTY_SCENARIOS:
        demand = _projected_demand(scn)
        gap = _hub_spoke_gap(scn, demand, inv_v1, inv_v2)
        req = _gcss_requisition(scn, gap)
        brief = None
        if llm_ok:
            try:
                user = (
                    f"SCENARIO: {scn['label']}\n"
                    f"FRAME: {scn['frame']}\n"
                    f"LOCATION: {scn['location_id']}\n"
                    f"WIA COUNT: {scn['wia_count']}\n"
                    f"INJURY MIX: {json.dumps(scn['injury_mix'], indent=2)}\n"
                    f"PROJECTED 24h CLASS VIII DEMAND:\n{json.dumps(demand, indent=2, default=str)}\n\n"
                    f"HUB-SPOKE GAP ANALYSIS:\n{json.dumps(gap, indent=2, default=str)}\n\n"
                    f"AUTO-BUILT GCSS-MC REQUISITION:\n{json.dumps(req, indent=2)}\n\n"
                    f"APPROVED VENDORS:\n{json.dumps(VENDORS, indent=2)}\n\n"
                    f"Compose the Medical Sustainment Action Brief now."
                )
                brief = chat(
                    [{"role": "system", "content": SYS},
                     {"role": "user", "content": user}],
                    model="gpt-5.4", temperature=0.4,
                )
            except Exception as e:
                print(f"  ! LLM hero call failed for {scn['id']}: {e}")
                brief = None
        if not brief or "BLUF" not in brief:
            brief = _baseline_brief(scn, demand, gap)
        briefs[scn["id"]] = {
            "label": scn["label"],
            "frame": scn["frame"],
            "brief": brief,
            "demand": demand,
            "gap":    gap,
            "requisition": req,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "source": "llm" if (llm_ok and "BLUF" in brief and len(brief) > 600) else "baseline",
        }
    return briefs


# ---- main -------------------------------------------------------------------

def _generate_data() -> dict:
    rng = random.Random(1776)
    routes = _build_routes(rng)
    inv_v1 = _inventory_v1(rng)
    inv_v2 = _inventory_v2(rng)
    network = _supply_network(routes)
    gcss = _gcss_mc_requisitions(rng)

    (ROOT / "hub.json").write_text(json.dumps(HUB, indent=2))
    (ROOT / "spokes.json").write_text(json.dumps(SPOKES, indent=2))
    (ROOT / "routes.json").write_text(json.dumps(routes, indent=2))
    (ROOT / "inventory_v1.json").write_text(json.dumps(inv_v1, indent=2))
    (ROOT / "inventory_v2.json").write_text(json.dumps(inv_v2, indent=2))
    (ROOT / "supply_network.json").write_text(json.dumps(network, indent=2))
    (ROOT / "gcss_mc.json").write_text(json.dumps(gcss, indent=2))
    (ROOT / "casualty_scenarios.json").write_text(json.dumps(CASUALTY_SCENARIOS, indent=2))
    (ROOT / "triage_doctrine.json").write_text(json.dumps(TRIAGE_DOCTRINE, indent=2))
    (ROOT / "vendors.json").write_text(json.dumps(VENDORS, indent=2))

    print(f"Wrote 1 hub, {len(SPOKES)} spokes, {len(routes)} routes, "
          f"{len(inv_v1)} v1 blood rows, {len(inv_v2)} v2 Class VIII rows, "
          f"{len(gcss)} GCSS-MC requisitions, {len(CASUALTY_SCENARIOS)} scenarios, "
          f"{len(VENDORS)} vendors.")
    return {"inv_v1": inv_v1, "inv_v2": inv_v2}


def main() -> None:
    bundle = _generate_data()
    print("Pre-computing hero briefs (cache-first)…")
    briefs = _precompute_briefs(bundle["inv_v1"], bundle["inv_v2"])
    (ROOT / "cached_briefs.json").write_text(json.dumps(briefs, indent=2, default=str))
    print(f"Wrote {len(briefs)} cached briefs -> data/cached_briefs.json")


if __name__ == "__main__":
    main()
