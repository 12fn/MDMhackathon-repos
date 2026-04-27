"""VITALS synthetic data generator.

Produces a hub-and-spoke blood / blood-product logistics dataset for a
contested USINDOPACOM Distributed Maritime Operations (DMO) scenario.

  data/hub.json             - 1 regional medical depot (Apra, Guam)
  data/spokes.json          - 12 distributed Marine units (afloat + expeditionary)
  data/inventory.json       - blood-component inventory rows for hub + each spoke
  data/routes.json          - hub <-> spoke route status, lift availability
  data/casualty_assumptions.json
                            - planned / projected casualty load per spoke
  data/vendors.json         - approved buy-on-market commercial / host-nation vendors
  data/cached_briefs.json   - pre-computed hero Commander's Decision Briefs

All synthetic but plausible. Stand-in for the LOGCOM portal datasets
'Medical Supply Inventory' and 'Medical Supply Network Data Model'.

Seeded with random.Random(1776) for reproducibility.
"""
from __future__ import annotations

import json
import random
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent
REPO_ROOT = ROOT.parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


# ---- Hub --------------------------------------------------------------------

HUB = {
    "id": "APRA-MED",
    "name": "Apra Regional Medical Depot",
    "kind": "hub",
    "country": "Guam (US)",
    "lat": 13.443,
    "lon": 144.660,
    "cold_chain_units": 14,    # walk-in cold-chain refrigerators
    "cold_chain_health": 0.92, # 0..1 fraction operating nominally
    "lab_reagent_days": 21,    # days of donor-screening reagents on hand
    "dry_ice_kg": 4800,
    "max_daily_throughput_units": 1800,
}


# 12 spokes — distributed Marine units (afloat + expeditionary med sites)
# WestPac focus, INDOPACOM AOR.
# 'kind' in {'afloat-l-class','afloat-cvn','expeditionary-shore','rotc-frwd','marine-corps-air'}
SPOKES: list[dict] = [
    {"id": "LHA-6",   "name": "USS America (LHA-6) Role 2E",     "kind": "afloat-l-class",     "country": "WestPac",          "lat": 17.84, "lon": 142.10, "personnel": 2400, "fridges": 3, "fridge_health": 0.95},
    {"id": "LHD-1",   "name": "USS Wasp (LHD-1) Role 2E",         "kind": "afloat-l-class",     "country": "WestPac",          "lat": 22.10, "lon": 134.50, "personnel": 2300, "fridges": 3, "fridge_health": 0.78},
    {"id": "LPD-29",  "name": "USS Richard McCool (LPD-29) BAS",  "kind": "afloat-l-class",     "country": "WestPac",          "lat": 19.70, "lon": 138.20, "personnel": 700,  "fridges": 2, "fridge_health": 0.88},
    {"id": "MEU-31",  "name": "31st MEU Surgical Co (Okinawa)",   "kind": "expeditionary-shore","country": "Okinawa (JPN)",   "lat": 26.355, "lon": 127.768,"personnel": 2200, "fridges": 4, "fridge_health": 0.82},
    {"id": "MEU-13",  "name": "13th MEU FRSS (Subic Fwd)",        "kind": "expeditionary-shore","country": "Philippines",     "lat": 14.795, "lon": 120.282,"personnel": 2100, "fridges": 3, "fridge_health": 0.71},
    {"id": "EABO-PA", "name": "EABO Site PALAU (3rd MLR FRSS)",   "kind": "rotc-frwd",          "country": "Palau",           "lat": 7.367,  "lon": 134.544,"personnel": 380,  "fridges": 1, "fridge_health": 0.65},
    {"id": "EABO-TI", "name": "EABO Site TINIAN (3rd MLR FRSS)",  "kind": "rotc-frwd",          "country": "CNMI (US)",       "lat": 14.998, "lon": 145.620,"personnel": 420,  "fridges": 1, "fridge_health": 0.83},
    {"id": "EABO-IT", "name": "EABO Site ITBAYAT (4th MLR FRSS)", "kind": "rotc-frwd",          "country": "Philippines",     "lat": 20.770, "lon": 121.840,"personnel": 290,  "fridges": 1, "fridge_health": 0.59},
    {"id": "EABO-IS", "name": "EABO Site ISHIGAKI (12th MLR)",    "kind": "rotc-frwd",          "country": "Ryukyus (JPN)",   "lat": 24.345, "lon": 124.156,"personnel": 340,  "fridges": 1, "fridge_health": 0.74},
    {"id": "MCAS-IW", "name": "MCAS Iwakuni Med Clinic",          "kind": "marine-corps-air",   "country": "Honshu (JPN)",    "lat": 34.144, "lon": 132.235,"personnel": 1700, "fridges": 4, "fridge_health": 0.91},
    {"id": "ROLE3-OK","name": "USNH Okinawa Role 3",              "kind": "expeditionary-shore","country": "Okinawa (JPN)",   "lat": 26.243, "lon": 127.732,"personnel": 3500, "fridges": 6, "fridge_health": 0.90},
    {"id": "CVN-71",  "name": "USS Theodore Roosevelt (CVN-71) Med", "kind": "afloat-cvn",      "country": "WestPac",         "lat": 16.20, "lon": 140.85, "personnel": 5000, "fridges": 5, "fridge_health": 0.86},
]


# ---- Routes (hub <-> each spoke) -------------------------------------------

def _build_routes(rng: random.Random) -> list[dict]:
    """Build hub<->spoke routes with mode, distance, status, lift availability."""
    routes = []
    for s in SPOKES:
        # crude NM distance for narrative purposes
        d_lat = (s["lat"] - HUB["lat"]) * 60
        d_lon = (s["lon"] - HUB["lon"]) * 60 * 0.97
        nm = round((d_lat * d_lat + d_lon * d_lon) ** 0.5, 0)
        if s["kind"].startswith("afloat") or s["kind"] in ("rotc-frwd",):
            mode = "rotary+vertrep" if nm < 600 else "fixed-wing+rotary"
        elif s["kind"] == "marine-corps-air":
            mode = "fixed-wing"
        else:
            mode = "fixed-wing"
        # lift availability + cold-chain transit risk
        lift = rng.choice(["GREEN", "GREEN", "AMBER", "AMBER", "RED"])
        cold_chain_transit_risk = round(rng.uniform(0.05, 0.45), 2)
        leg_h = round(nm / rng.uniform(180, 320), 1)
        routes.append({
            "spoke_id": s["id"],
            "mode": mode,
            "distance_nm": nm,
            "leg_hours": leg_h,
            "lift_status": lift,
            "cold_chain_transit_risk": cold_chain_transit_risk,
            "last_resupply_h_ago": rng.randint(6, 96),
        })
    return routes


# ---- Inventory (blood components) ------------------------------------------
#
# We track three primary blood products carried at the BSI / Role-2E:
#   PRBC   - Packed red blood cells (35-day shelf life refrigerated)
#   PLASMA - Fresh frozen plasma   (1-year frozen / 5-day thawed)
#   PLT    - Platelets             (5-7 day shelf life, room-temp w/ agitation)
# Plus LTOWB (low-titer O whole blood) at select sites.

PRODUCTS = ["PRBC", "PLASMA", "PLT", "LTOWB"]


def _hub_inventory(rng: random.Random) -> list[dict]:
    rows = []
    base = datetime.now(timezone.utc).replace(microsecond=0)
    spec = {"PRBC": (1100, 35), "PLASMA": (820, 365), "PLT": (140, 6), "LTOWB": (260, 21)}
    for prod, (units, shelf_d) in spec.items():
        units = units + rng.randint(-80, 80)
        # mixed expiration distribution
        exp = base + timedelta(days=rng.randint(2, max(3, shelf_d - 3)))
        rows.append({
            "site_id": HUB["id"],
            "product": prod,
            "units": units,
            "expires_iso": exp.isoformat(),
            "cold_chain_status": "GREEN",
        })
    return rows


def _spoke_inventory(rng: random.Random) -> list[dict]:
    """For each spoke + product, generate units, expiration, cold-chain status,
    daily consumption rate, days_of_supply.

    Days-of-supply is the headline number: small spokes with tight cold-chain
    will show <=3 days early — they drive the cascade story in the hero brief.
    """
    rows = []
    base = datetime.now(timezone.utc).replace(microsecond=0)
    for s in SPOKES:
        # Per-spoke daily consumption rate (units/day) — proxy for casualty intake.
        # Large amphib + CVN consume more; EABO sites consume less but are fragile.
        if s["kind"] == "afloat-cvn":
            scale = 14.0
        elif s["kind"] == "afloat-l-class":
            scale = 9.5
        elif s["kind"] == "expeditionary-shore":
            scale = 7.0
        elif s["kind"] == "marine-corps-air":
            scale = 4.5
        else:  # rotc-frwd EABO
            scale = 2.4
        for prod in PRODUCTS:
            # not every spoke holds every product
            if prod == "LTOWB" and s["kind"] not in ("rotc-frwd", "afloat-l-class", "afloat-cvn"):
                continue
            base_units = {
                "PRBC": int(scale * rng.uniform(2.0, 3.5)),
                "PLASMA": int(scale * rng.uniform(1.5, 2.6)),
                "PLT": int(scale * rng.uniform(0.9, 1.6)),
                "LTOWB": int(scale * rng.uniform(1.0, 2.0)),
            }[prod]
            units = max(1, base_units + rng.randint(-3, 3))
            shelf = {"PRBC": 35, "PLASMA": 365, "PLT": 6, "LTOWB": 21}[prod]
            # Spoke fridges in worse health -> shorter effective expiration window
            health = s["fridge_health"]
            shelf_eff = max(1, int(shelf * health))
            exp = base + timedelta(days=rng.randint(1, max(2, shelf_eff)))
            # Cold-chain status keyed off fridge_health
            if health < 0.65:
                cc = "RED"
            elif health < 0.80:
                cc = "AMBER"
            else:
                cc = "GREEN"
            # Daily consumption rate per product (units/day)
            cons = {
                "PRBC": round(scale * rng.uniform(0.8, 1.4), 1),
                "PLASMA": round(scale * rng.uniform(0.5, 0.9), 1),
                "PLT": round(scale * rng.uniform(0.4, 0.7), 1),
                "LTOWB": round(scale * rng.uniform(0.6, 1.1), 1),
            }[prod]
            dos = round(units / cons, 1) if cons > 0 else 99.0
            rows.append({
                "site_id": s["id"],
                "product": prod,
                "units": units,
                "expires_iso": exp.isoformat(),
                "cold_chain_status": cc,
                "daily_consumption": cons,
                "days_of_supply": dos,
            })
    return rows


# ---- Casualty assumptions per spoke ----------------------------------------
def _casualty_assumptions(rng: random.Random) -> list[dict]:
    out = []
    for s in SPOKES:
        # planning factor: WIA per 1000 personnel per 24h in DMO contested
        if s["kind"].startswith("afloat") or s["kind"] == "expeditionary-shore":
            wia_rate = round(rng.uniform(0.6, 1.4), 2)
        elif s["kind"] == "rotc-frwd":  # EABO sites — higher exposure
            wia_rate = round(rng.uniform(1.6, 3.4), 2)
        else:
            wia_rate = round(rng.uniform(0.3, 0.7), 2)
        wia_24h = round(s["personnel"] / 1000.0 * wia_rate, 1)
        # blood product demand factor: ~3 PRBC / serious WIA
        prbc_demand_24h = round(wia_24h * 3.1, 1)
        out.append({
            "spoke_id": s["id"],
            "wia_per_1k_24h": wia_rate,
            "projected_wia_24h": wia_24h,
            "projected_prbc_demand_24h": prbc_demand_24h,
            "casualty_planning_factor_source": "USMC HSS planning factor (DMO, contested)",
        })
    return out


# ---- Approved buy-on-market vendor list ------------------------------------
VENDORS: list[dict] = [
    {"id": "V-DRYICE-01",  "name": "Pacific Cold Chain Logistics (Guam)",
     "country": "Guam (US)", "supplies": ["dry_ice", "gel_packs", "cold-chain-couriers"],
     "lead_time_h": 6,  "trust": "HIGH",
     "contract_vehicle": "GSA Schedule 51V",
     "notes": "Pre-negotiated 24x7 dispatch from Apra; approved by NAVMED Logistics."},
    {"id": "V-REAGENT-02", "name": "Roche Diagnostics APAC (HCMC)",
     "country": "Vietnam", "supplies": ["lab_reagents", "donor-screening-kits"],
     "lead_time_h": 36, "trust": "HIGH",
     "contract_vehicle": "DLA Troop Support BPA",
     "notes": "Host-nation procurement vehicle in place; air-lift to APRA via PACAF."},
    {"id": "V-LIFT-03",    "name": "Berry Aviation (Contracted Cargo)",
     "country": "USA",    "supplies": ["fixed-wing-lift", "rotary-lift"],
     "lead_time_h": 12, "trust": "HIGH",
     "contract_vehicle": "AMC TRANSCOM CRAF Stage I",
     "notes": "Surge contract aviation for inter-island med resupply."},
    {"id": "V-DONOR-04",   "name": "JSDF Self-Defense Med Supply (Okinawa)",
     "country": "Japan",  "supplies": ["LTOWB", "donor-network", "PRBC"],
     "lead_time_h": 18, "trust": "MODERATE",
     "contract_vehicle": "ACSA cross-servicing",
     "notes": "ACSA (Acquisition & Cross-Servicing Agreement) blood swap, JSDF Naha."},
    {"id": "V-COURIER-05", "name": "FedEx Express Critical (Manila)",
     "country": "Philippines", "supplies": ["cold-chain-couriers", "validated-shippers"],
     "lead_time_h": 8,  "trust": "MODERATE",
     "contract_vehicle": "Open-market spot",
     "notes": "Cleared for class VIIIa shipment; SLA 8h Manila->WestPac spokes."},
    {"id": "V-FRIDGE-06",  "name": "Helmer Scientific (Field Refrigeration)",
     "country": "USA",    "supplies": ["field-refrigerators", "spares"],
     "lead_time_h": 72, "trust": "HIGH",
     "contract_vehicle": "DLA Troop Support direct",
     "notes": "Air-droppable Pelican-style cold boxes; 72h DLOA."},
]


# ---- Hero LLM brief precompute (cache-first) -------------------------------

# We pre-bake the hero Commander's Decision Brief into data/cached_briefs.json
# so that the Streamlit demo never blocks on the live LLM call. The 'live'
# regenerate button still re-runs in real time (under timeout) for judges who
# want to see the call happen.

DEFAULT_SCENARIOS = [
    {"id": "baseline",
     "label": "Baseline (current posture)",
     "constraint": "Hub at full lift availability; cold-chain stable at all spokes."},
    {"id": "airlift_loss",
     "label": "Hub airlift loss (typhoon CPA <48h)",
     "constraint": "All hub fixed-wing lift suspended for 48h. Rotary-only resupply to L-class amphibs only."},
    {"id": "cold_chain_breach",
     "label": "Cold-chain breach at EABO sites",
     "constraint": "Two EABO refrigeration units fail. Lab-reagent shipment delayed 36h. PLT inventory at risk."},
    {"id": "mass_cas_event",
     "label": "Mass-cas event at LHD-1",
     "constraint": "Surface action group engagement: projected WIA at LHD-1 doubles for 24h."},
]


def _baseline_brief(hub: dict, spokes: list[dict], inv: list[dict],
                    casualties: list[dict], routes: list[dict],
                    vendors: list[dict], scenario: dict) -> str:
    """Deterministic Commander's Decision Brief fallback (used if LLM hero
    call times out / errors). Same schema as the LLM-generated brief.
    Rendered in markdown so Streamlit picks up headings."""
    by_spoke_inv: dict[str, list[dict]] = {}
    for r in inv:
        by_spoke_inv.setdefault(r["site_id"], []).append(r)

    # Apply scenario constraint synthetically: if cold_chain_breach, push EABO
    # cold-chain to RED. If airlift_loss, mark all routes degraded. If mass_cas,
    # double LHD-1 consumption. Baseline = unchanged.
    ranked = []
    for s in spokes:
        rows = by_spoke_inv.get(s["id"], [])
        # Use minimum days-of-supply across the products held at this spoke
        prbc_rows = [r for r in rows if r["product"] == "PRBC"]
        if not prbc_rows:
            continue
        dos = min(r["days_of_supply"] for r in rows)
        cc = min((r["cold_chain_status"] for r in rows),
                 key=lambda c: ["RED", "AMBER", "GREEN"].index(c))
        # scenario overrides
        if scenario["id"] == "airlift_loss":
            dos = max(0.5, dos - 1.5)
        if scenario["id"] == "cold_chain_breach" and s["kind"] == "rotc-frwd":
            cc = "RED"
            dos = max(0.5, dos - 1.0)
        if scenario["id"] == "mass_cas_event" and s["id"] == "LHD-1":
            dos = max(0.5, dos / 2.0)
        # Viability index 0..10, higher = more viable
        viability = max(0.0, min(10.0, dos * 1.2 + (3.0 if cc == "GREEN" else 1.0 if cc == "AMBER" else 0.0)))
        # confidence
        conf = "HIGH" if dos < 2.5 or cc == "RED" else ("MODERATE" if dos < 5 else "LOW")
        ranked.append({
            "node_id": s["id"],
            "name": s["name"],
            "days_of_supply": round(dos, 1),
            "viability_index": round(viability, 1),
            "cold_chain": cc,
            "confidence": conf,
            "top_constraint": (
                "Cold-chain breach (refrigeration RED)" if cc == "RED"
                else "Days-of-supply <2" if dos < 2 else
                "Days-of-supply <5 + airlift degraded" if dos < 5 else
                "Within sustainment window"
            ),
        })

    ranked.sort(key=lambda r: (r["viability_index"], r["days_of_supply"]))
    top3 = ranked[:3]

    bluf_lines = [
        f"**BLUF:** Under scenario *{scenario['label']}*, "
        f"{sum(1 for r in ranked if r['viability_index'] < 5.0)} of 12 spoke nodes fall below the "
        f"viability threshold within 72 hours. Highest-risk spokes: "
        f"**{top3[0]['name']}**, **{top3[1]['name']}**, **{top3[2]['name']}**. "
        f"Recommend immediate rotary VERTREP push from APRA hub plus contingency cold-chain "
        f"sourcing via approved buy-on-market vendors."
    ]

    top3_lines = []
    for r in top3:
        top3_lines.append(
            f"- **{r['name']}** ({r['node_id']}) — viability **{r['viability_index']:.1f}/10**, "
            f"days-of-supply **{r['days_of_supply']:.1f}**, cold-chain **{r['cold_chain']}**. "
            f"Top constraint: *{r['top_constraint']}* (confidence {r['confidence']})."
        )

    cascades = [
        "- **Cold-chain loss** at EABO refrigeration nodes propagates to PRBC + PLT condemnation within 8h; "
        "lab reagent shortage extends donor-screening turnaround from 3h to 11h.",
        "- **Transport delay** on hub fixed-wing lift forces switch to rotary VERTREP for L-class amphibs only — "
        "EABO sites starve first; projected stockout window 36-72h ahead of plan.",
        "- **Lab-reagent shortage** at hub blocks emergency-release LTOWB titration; back-stop is JSDF ACSA "
        "donor-network pull from V-DONOR-04 (Naha) under 18h lead time.",
    ]

    actions = [
        "1. **APRA hub:** Immediately spin up rotary VERTREP cycle to LHD-1, EABO-PA, EABO-IT — "
        "pre-stage 60 PRBC + 30 PLASMA units in validated shippers (V-DRYICE-01 dry-ice surge).",
        "2. **Buy-on-market:** Activate **V-DRYICE-01** (Pacific Cold Chain, 6h lead) for 800 kg dry-ice surge; "
        "pre-coordinate **V-COURIER-05** (FedEx Express Critical, 8h lead) for Manila->EABO leg.",
        "3. **Cross-service:** Execute **V-DONOR-04** ACSA pull from JSDF Naha for 40 LTOWB units — "
        "fastest path to restoring LTOWB at EABO-IS / EABO-IT.",
        "4. **Field refrigeration:** Initiate **V-FRIDGE-06** DLA Troop Support order for 4 air-droppable "
        "Helmer cold boxes — 72h DLOA supports steady-state recovery.",
        "5. **Risk acceptance:** Recommend Commander accept reduced PLT posture at EABO-IT for 36h "
        "until first restock cycle completes; brief next +24h.",
    ]

    return (
        f"# COMMANDER'S DECISION BRIEF — DHA RESCUE\n"
        f"**Scenario:** {scenario['label']}\n"
        f"**Constraint:** {scenario['constraint']}\n"
        f"**Originator:** VITALS — Joint Blood Logistics Decision Cell\n"
        f"**DTG:** {datetime.now(timezone.utc).strftime('%d%H%MZ %b %Y').upper()}\n"
        f"**Classification:** UNCLASSIFIED // FOR OFFICIAL USE\n\n"
        + "\n".join(bluf_lines) + "\n\n"
        f"## Top 3 Spoke Nodes at Risk\n" + "\n".join(top3_lines) + "\n\n"
        f"## Secondary-Effect Cascades\n" + "\n".join(cascades) + "\n\n"
        f"## Recommended Mitigation Actions\n" + "\n".join(actions) + "\n\n"
        f"## Posture\n"
        f"Running on a Kamiwaza-deployed hero model behind `KAMIWAZA_BASE_URL`. "
        f"Air-gapped, IL5/IL6 ready. Inventory + network model never leave the accredited environment.\n"
    )


def _precompute_briefs(hub, spokes, inventory, casualties, routes, vendors) -> dict:
    """Try the live LLM hero call; on any error fall back to deterministic
    baseline. Always returns a complete brief per scenario."""
    briefs = {}
    try:
        # Lazy import — generation should still work in CI / no-network builds
        from shared.kamiwaza_client import chat
        llm_ok = True
    except Exception:
        llm_ok = False

    def _spoke_table(scn_id: str) -> str:
        # Compact JSON-ish summary of spoke posture for the LLM
        by_inv: dict[str, list[dict]] = {}
        for r in inventory:
            by_inv.setdefault(r["site_id"], []).append(r)
        rows = []
        for s in spokes:
            inv_rows = by_inv.get(s["id"], [])
            if not inv_rows:
                continue
            min_dos = min(r.get("days_of_supply", 99) for r in inv_rows)
            cc = min((r["cold_chain_status"] for r in inv_rows),
                     key=lambda c: ["RED", "AMBER", "GREEN"].index(c))
            cas = next((c for c in casualties if c["spoke_id"] == s["id"]), {})
            rt = next((r for r in routes if r["spoke_id"] == s["id"]), {})
            rows.append({
                "id": s["id"], "name": s["name"], "kind": s["kind"],
                "min_dos": min_dos, "cold_chain": cc,
                "lift": rt.get("lift_status"),
                "wia_24h": cas.get("projected_wia_24h"),
                "prbc_demand_24h": cas.get("projected_prbc_demand_24h"),
            })
        return json.dumps(rows, indent=2)

    SYS = (
        "You are VITALS, the Joint Blood Logistics Decision-Support agent for "
        "USMC LOGCOM and the Defense Health Agency, supporting USINDOPACOM "
        "Distributed Maritime Operations.\n\n"
        "Compose a polished one-page COMMANDER'S DECISION BRIEF in markdown "
        "with these EXACT sections in order:\n"
        "  - A bold one-line **BLUF:** at the top\n"
        "  - ## Top 3 Spoke Nodes at Risk  (bullet list)\n"
        "  - ## Secondary-Effect Cascades  (bullet list)\n"
        "  - ## Recommended Mitigation Actions  (numbered list, 3-5 items)\n"
        "  - ## Posture  (one-paragraph on-prem story)\n\n"
        "Constraints:\n"
        "  - Cite specific spoke names + days-of-supply numbers from the data.\n"
        "  - Each mitigation action MUST name a specific approved vendor by id "
        "(e.g. V-DRYICE-01, V-COURIER-05) when sourcing on the commercial / "
        "host-nation market. Use the contract vehicle field verbatim.\n"
        "  - Mention cold-chain loss, transport delays, and lab-reagent shortage "
        "as the three secondary cascades.\n"
        "  - Total length <= 500 words.\n"
        "  - Classification line: UNCLASSIFIED // FOR OFFICIAL USE."
    )

    for scn in DEFAULT_SCENARIOS:
        brief = None
        if llm_ok:
            try:
                user = (
                    f"SCENARIO: {scn['label']}\n"
                    f"CONSTRAINT: {scn['constraint']}\n\n"
                    f"HUB: {json.dumps(hub, indent=2)}\n\n"
                    f"SPOKES (12) — current posture under scenario:\n"
                    f"{_spoke_table(scn['id'])}\n\n"
                    f"APPROVED BUY-ON-MARKET VENDORS:\n"
                    f"{json.dumps(vendors, indent=2)}\n\n"
                    f"Compose the Commander's Decision Brief now."
                )
                # use hero model name; the shared client's fallback chain protects us
                brief = chat(
                    [{"role": "system", "content": SYS},
                     {"role": "user", "content": user}],
                    model="gpt-5.4",
                    temperature=0.4,
                )
            except Exception as e:
                print(f"  ! LLM hero call failed for scenario {scn['id']}: {e}")
                brief = None
        if not brief or "BLUF" not in brief:
            brief = _baseline_brief(hub, spokes, inventory, casualties, routes, vendors, scn)
        briefs[scn["id"]] = {
            "label": scn["label"],
            "constraint": scn["constraint"],
            "brief": brief,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "source": "llm" if (llm_ok and "BLUF" in brief and len(brief) > 600) else "baseline",
        }
    return briefs


# ---- main -------------------------------------------------------------------

def _generate_data() -> dict:
    rng = random.Random(1776)
    routes = _build_routes(rng)
    inventory = _hub_inventory(rng) + _spoke_inventory(rng)
    casualties = _casualty_assumptions(rng)

    (ROOT / "hub.json").write_text(json.dumps(HUB, indent=2))
    (ROOT / "spokes.json").write_text(json.dumps(SPOKES, indent=2))
    (ROOT / "inventory.json").write_text(json.dumps(inventory, indent=2))
    (ROOT / "routes.json").write_text(json.dumps(routes, indent=2))
    (ROOT / "casualty_assumptions.json").write_text(json.dumps(casualties, indent=2))
    (ROOT / "vendors.json").write_text(json.dumps(VENDORS, indent=2))
    print(f"Wrote 1 hub, {len(SPOKES)} spokes, {len(inventory)} inventory rows, "
          f"{len(routes)} routes, {len(casualties)} casualty rows, {len(VENDORS)} vendors.")
    return {
        "hub": HUB, "spokes": SPOKES, "inventory": inventory, "routes": routes,
        "casualties": casualties, "vendors": VENDORS,
    }


def main() -> None:
    bundle = _generate_data()
    print("Pre-computing hero briefs (cache-first)...")
    briefs = _precompute_briefs(
        bundle["hub"], bundle["spokes"], bundle["inventory"],
        bundle["casualties"], bundle["routes"], bundle["vendors"],
    )
    (ROOT / "cached_briefs.json").write_text(json.dumps(briefs, indent=2))
    print(f"Wrote {len(briefs)} cached briefs -> data/cached_briefs.json")


if __name__ == "__main__":
    main()
