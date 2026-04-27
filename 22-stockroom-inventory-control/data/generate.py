"""STOCKROOM synthetic data generator.

Produces:
  data/inventory.xlsx       - 5,000 inventory items mirroring USMC Inventory
                              Control Management workbook columns.
  data/inventory.csv        - same data, CSV mirror for fast diffing.
  data/locations.json       - warehouse zones, vehicle bays, armory rooms.
  data/transactions.jsonl   - append-only audit (seeded with 30 events).
  data/cached_briefs.json   - pre-computed hero "Readiness & Lateral Transfer
                              Brief" for 3 scenarios (cache-first pattern).

Seeded with random.Random(1776) for reproducibility.
Real-data swap: see data/load_real.py — point REAL_DATA_PATH at the LOGCOM
ICM workbook and the same downstream code runs.
"""
from __future__ import annotations

import json
import random
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent
REPO_ROOT = ROOT.parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# ---------------------------------------------------------------------------
# Reference vocab
# ---------------------------------------------------------------------------

LOCATIONS: list[dict] = [
    # Bulk warehouses
    {"id": "WHSE-A1", "kind": "warehouse",  "name": "Warehouse A — Bay 1", "building": "B-1701", "controlled": False},
    {"id": "WHSE-A2", "kind": "warehouse",  "name": "Warehouse A — Bay 2", "building": "B-1701", "controlled": False},
    {"id": "WHSE-B1", "kind": "warehouse",  "name": "Warehouse B — Bay 1", "building": "B-1702", "controlled": False},
    {"id": "WHSE-B2", "kind": "warehouse",  "name": "Warehouse B — Bay 2", "building": "B-1702", "controlled": False},
    # Vehicle bays
    {"id": "VBAY-01", "kind": "vehicle_bay","name": "Motor Pool Bay 01",   "building": "B-2210", "controlled": False},
    {"id": "VBAY-02", "kind": "vehicle_bay","name": "Motor Pool Bay 02",   "building": "B-2210", "controlled": False},
    {"id": "VBAY-03", "kind": "vehicle_bay","name": "TMDE Bay 03",         "building": "B-2212", "controlled": False},
    # Armories — sensitive
    {"id": "ARM-101", "kind": "armory",     "name": "Armory Room 101",     "building": "B-1109", "controlled": True},
    {"id": "ARM-102", "kind": "armory",     "name": "Armory Room 102",     "building": "B-1109", "controlled": True},
    {"id": "ARM-103", "kind": "armory",     "name": "Armory Room 103 (CCI)","building": "B-1109","controlled": True},
    # Comm cage (CCI)
    {"id": "COMSEC-1","kind": "comm_cage",  "name": "COMSEC Cage 1",       "building": "B-1109", "controlled": True},
    # Medical
    {"id": "MED-CAGE","kind": "med_cage",   "name": "Medical Class VIII Cage","building":"B-1402","controlled": True},
    # Fuel/HAZMAT
    {"id": "HAZ-Y1",  "kind": "haz_yard",   "name": "HAZMAT Yard 1",       "building": "B-3301", "controlled": True},
]

# Marines responsible for inventory custody
MARINES = [
    "SSgt Reyes, J.",      "SSgt Whitfield, T.",  "Sgt Alvarado, M.",
    "Sgt Carrillo, R.",    "Sgt Olufsen, K.",     "Sgt Pham, D.",
    "Cpl Boudreau, A.",    "Cpl Diallo, S.",      "Cpl Henderson, B.",
    "Cpl Iwamoto, K.",     "Cpl Kowalski, P.",    "Cpl Marin, L.",
    "GySgt Underwood, R.", "GySgt Yelovich, M.",  "MSgt Quinones, V.",
]

# Sensitivity classes (drives inventory cadence)
SENSITIVITY = [
    ("ROUTINE",   60, 0.70),  # (label, days_between_inventory, weight)
    ("SENSITIVE", 30, 0.18),
    ("CCI",       10, 0.06),  # Controlled Cryptographic Item
    ("ARMS",      10, 0.04),
    ("HAZMAT",    14, 0.02),
]
SENSITIVITY_LABELS = [s[0] for s in SENSITIVITY]
SENSITIVITY_WEIGHTS = [s[2] for s in SENSITIVITY]
SENSITIVITY_CADENCE = {s[0]: s[1] for s in SENSITIVITY}

CATEGORIES = [
    "Class I — Subsistence",
    "Class II — Clothing & Individual Equip",
    "Class III — POL",
    "Class IV — Construction",
    "Class V — Ammunition",
    "Class VI — Personal Demand",
    "Class VII — Major End Items",
    "Class VIII — Medical",
    "Class IX — Repair Parts",
    "Class X — Non-Mil Programs",
]

# Synthetic NSN nomenclature templates per category
NOMENCLATURE = {
    "Class I — Subsistence": [
        "MRE Case, Menu A", "MRE Case, Menu B", "Bottled Water, Pallet",
        "UGR-A Component Pack", "Coffee, Instant, Case",
    ],
    "Class II — Clothing & Individual Equip": [
        "Plate Carrier, Medium", "Helmet ECH, Large", "Cold Weather Parka, Med",
        "Boot, Combat, Size 10R", "Pack, USMC ILBE, OD",
        "Glove, Combat, Black, M", "Shemagh, Tan",
    ],
    "Class III — POL": [
        "JP-8, 55-gal Drum", "MOGAS, 55-gal Drum", "Hydraulic Fluid OE-46",
        "Lubricant, GAA, Tube", "Coolant, Antifreeze, Gal",
    ],
    "Class IV — Construction": [
        "Lumber 2x4x8, Bundle", "Concertina Wire, Roll", "Sandbag, Empty, Bundle",
        "Plywood 4x8, Sheet", "Conex Liner Kit",
    ],
    "Class V — Ammunition": [
        "5.56 Ball M855, 200rd Can", "7.62 Linked M80A1, 100rd",
        "9mm Ball M1152, 50rd Box", "12-ga 00 Buck, Case",
        "M67 Frag, 4-grenade Pack", "M18 Smoke, Violet",
    ],
    "Class VI — Personal Demand": [
        "PX Restock Kit, Bundle", "Hygiene Kit, Field, Case",
    ],
    "Class VII — Major End Items": [
        "AN/PRC-117G Manpack Radio", "AN/PRC-152A Handheld",
        "AN/PVS-14 NVG, Mono", "AN/PEQ-15 IR Aim Light",
        "M27 IAR, Serialized", "M4A1 Carbine, Serialized",
        "M240B MG, Serialized", "M2A1 .50cal, Serialized",
        "JLTV M1278A1 Heavy Gun Carrier", "MTVR MK23 7-ton",
    ],
    "Class VIII — Medical": [
        "CAT Tourniquet, Gen-7", "Combat Gauze Z-Fold",
        "Israeli Bandage 6\"", "TXA, 1g IV, Vial",
        "Decompression Needle, 14ga", "Naloxone HCl, 4mg Nasal",
    ],
    "Class IX — Repair Parts": [
        "JLTV Brake Caliper Assy", "MTVR Air Filter, Element",
        "M240 Barrel Assy, Quick-Change", "PRC-117 Battery BB-2590",
        "Generator MEP-803A Voltage Regulator", "AN/VRC-103 Mount Kit",
        "M-ATV Hub Assembly", "Tire, MTVR, 16R20",
    ],
    "Class X — Non-Mil Programs": [
        "Civil Affairs Handout Kit", "Humanitarian Tarps, Pallet",
    ],
}

# Categories that drive a particular sensitivity class
CATEGORY_SENSITIVITY_BIAS = {
    "Class V — Ammunition":            ("ARMS", 0.85),
    "Class VII — Major End Items":     ("SENSITIVE", 0.90),
    "Class VIII — Medical":            ("SENSITIVE", 0.55),
    "Class III — POL":                 ("HAZMAT", 0.65),
}

# Locations preferred by category
CATEGORY_LOCATION_BIAS = {
    "Class V — Ammunition":            ["ARM-101", "ARM-102"],
    "Class VII — Major End Items":     ["ARM-103", "COMSEC-1", "VBAY-01", "VBAY-02"],
    "Class III — POL":                 ["HAZ-Y1"],
    "Class VIII — Medical":            ["MED-CAGE"],
    "Class IX — Repair Parts":         ["WHSE-A1", "WHSE-A2", "WHSE-B1", "VBAY-03"],
    "Class I — Subsistence":           ["WHSE-A1", "WHSE-A2"],
    "Class II — Clothing & Individual Equip": ["WHSE-B1", "WHSE-B2"],
    "Class IV — Construction":         ["WHSE-B2"],
    "Class VI — Personal Demand":      ["WHSE-B1"],
    "Class X — Non-Mil Programs":      ["WHSE-B2"],
}

CONDITION_CODES = ["A", "A", "A", "A", "B", "B", "C", "F"]  # A=svcbl, F=unsvcbl
CONDITION_WEIGHTS_BY_CAT = {
    # Major end items have more F items (NMC) — drives the readiness brief
    "Class VII — Major End Items": ["A", "A", "A", "B", "B", "C", "F", "F"],
    "Class IX — Repair Parts":     ["A", "A", "B", "B", "F"],
}

# ---------------------------------------------------------------------------
# NSN — synthetic but plausible (4-digit FSC, 9-digit NIIN format)
# ---------------------------------------------------------------------------

def _nsn(rng: random.Random, fsc_pool: list[str]) -> str:
    fsc = rng.choice(fsc_pool)
    niin = "".join(rng.choice("0123456789") for _ in range(9))
    # Format NSN as FSC-NIIN[0:2]-NIIN[2:5]-NIIN[5:9]
    return f"{fsc}-{niin[0:2]}-{niin[2:5]}-{niin[5:9]}"

FSC_BY_CATEGORY = {
    "Class I — Subsistence":           ["8910", "8915", "8970"],
    "Class II — Clothing & Individual Equip": ["8415", "8420", "8430", "8465"],
    "Class III — POL":                 ["9130", "9140", "9150"],
    "Class IV — Construction":         ["5510", "5610", "5660"],
    "Class V — Ammunition":            ["1305", "1310", "1330"],
    "Class VI — Personal Demand":      ["8520", "8530"],
    "Class VII — Major End Items":     ["1005", "5820", "5855", "2320"],
    "Class VIII — Medical":            ["6505", "6510", "6515", "6545"],
    "Class IX — Repair Parts":         ["2530", "2540", "2920", "5945", "6135"],
    "Class X — Non-Mil Programs":      ["8470", "9905"],
}

# ---------------------------------------------------------------------------
# Generators
# ---------------------------------------------------------------------------

BASE_DT = datetime(2026, 4, 27, 12, 0, 0, tzinfo=timezone.utc)


def _last_inventoried(rng: random.Random, sensitivity: str) -> datetime:
    """Date the item was last inventoried — biased so a meaningful slice are
    overdue per the cadence for their sensitivity class."""
    cadence = SENSITIVITY_CADENCE[sensitivity]
    # 70% within cadence, 25% mildly overdue (1.0–2.5x cadence), 5% wildly overdue
    bucket = rng.random()
    if bucket < 0.70:
        days = rng.randint(0, max(1, cadence - 1))
    elif bucket < 0.95:
        days = rng.randint(cadence, int(cadence * 2.5))
    else:
        days = rng.randint(int(cadence * 2.5), int(cadence * 6))
    return BASE_DT - timedelta(days=days, hours=rng.randint(0, 23))


def _last_lateral_transfer(rng: random.Random) -> datetime | None:
    """Date of last lateral transfer (or None for items that have never been
    laterally transferred). Biased so ~30% have None and ~25% are >60 days old."""
    bucket = rng.random()
    if bucket < 0.30:
        return None
    days = int(rng.expovariate(1 / 45))  # mean ~45 days
    days = min(days, 720)
    return BASE_DT - timedelta(days=days, hours=rng.randint(0, 23))


def _generate_inventory(rng: random.Random, n: int = 5000) -> pd.DataFrame:
    rows = []
    # Distribution across categories — Class IX dominates, then II / I / V.
    cat_weights = {
        "Class I — Subsistence":           0.10,
        "Class II — Clothing & Individual Equip": 0.18,
        "Class III — POL":                 0.05,
        "Class IV — Construction":         0.05,
        "Class V — Ammunition":            0.10,
        "Class VI — Personal Demand":      0.03,
        "Class VII — Major End Items":     0.08,
        "Class VIII — Medical":            0.07,
        "Class IX — Repair Parts":         0.31,
        "Class X — Non-Mil Programs":      0.03,
    }
    cats, weights = zip(*cat_weights.items())

    for i in range(1, n + 1):
        cat = rng.choices(cats, weights=weights, k=1)[0]
        nomen = rng.choice(NOMENCLATURE[cat])
        nsn = _nsn(rng, FSC_BY_CATEGORY[cat])
        # Sensitivity — biased per category
        bias = CATEGORY_SENSITIVITY_BIAS.get(cat)
        if bias and rng.random() < bias[1]:
            sens = bias[0]
        else:
            sens = rng.choices(SENSITIVITY_LABELS, weights=SENSITIVITY_WEIGHTS, k=1)[0]
        # Location — biased per category (with an off-bias 15% slip — exactly the
        # kind of misplacement an inventory app should surface)
        pool = CATEGORY_LOCATION_BIAS.get(cat, [l["id"] for l in LOCATIONS])
        if rng.random() < 0.15:
            loc = rng.choice([l["id"] for l in LOCATIONS])
        else:
            loc = rng.choice(pool)
        # Quantity — depends on category
        if cat in ("Class VII — Major End Items",):
            qty = 1  # serialized end items
        elif cat in ("Class V — Ammunition", "Class III — POL"):
            qty = rng.randint(2, 50)
        elif cat in ("Class IX — Repair Parts",):
            qty = rng.randint(1, 25)
        else:
            qty = rng.randint(1, 200)

        unit_of_issue = {
            "Class I — Subsistence":           "CS",
            "Class II — Clothing & Individual Equip": "EA",
            "Class III — POL":                 "DR",
            "Class IV — Construction":         "BD",
            "Class V — Ammunition":            "BX",
            "Class VI — Personal Demand":      "KT",
            "Class VII — Major End Items":     "EA",
            "Class VIII — Medical":            "EA",
            "Class IX — Repair Parts":         "EA",
            "Class X — Non-Mil Programs":      "KT",
        }[cat]

        cond_pool = CONDITION_WEIGHTS_BY_CAT.get(cat, CONDITION_CODES)
        cond = rng.choice(cond_pool)

        # Serial — only major end items + CCI/comms get one
        serial = ""
        if cat == "Class VII — Major End Items" or sens in ("CCI",):
            serial = "USMC-" + "".join(rng.choices("ABCDEFGHJKLMNPQRSTUVWXYZ23456789", k=8))

        marine = rng.choice(MARINES)
        last_inv = _last_inventoried(rng, sens)
        last_lat = _last_lateral_transfer(rng)

        # Required-On-Hand vs On-Hand mismatch — drives shortage detection
        roh = qty + rng.choice([0, 0, 0, 0, 1, 2, -1, -2, 5])
        roh = max(0, roh)
        shortage = max(0, roh - qty)

        rows.append({
            "item_id":               f"ITM-{i:06d}",
            "nsn":                   nsn,
            "nomenclature":          nomen,
            "category":              cat,
            "qty_on_hand":           qty,
            "qty_required":          roh,
            "shortage":              shortage,
            "unit_of_issue":         unit_of_issue,
            "condition_code":        cond,
            "serial_number":         serial,
            "sensitivity_class":     sens,
            "location_id":           loc,
            "responsible_marine":    marine,
            "last_inventoried_date": last_inv.date().isoformat(),
            "last_inventoried_iso":  last_inv.isoformat(),
            "last_lateral_transfer_date": last_lat.date().isoformat() if last_lat else "",
            "days_since_inventory":  (BASE_DT - last_inv).days,
            "days_since_lateral_transfer": (BASE_DT - last_lat).days if last_lat else 9999,
            "inventory_overdue":     (BASE_DT - last_inv).days > SENSITIVITY_CADENCE[sens],
            "nmc_impacting":         (cat in ("Class VII — Major End Items", "Class IX — Repair Parts") and cond == "F"),
        })

    return pd.DataFrame(rows)


def _generate_transactions(rng: random.Random, df: pd.DataFrame, n: int = 30) -> list[dict]:
    """Seed the audit log with 30 historic events."""
    events = []
    for i in range(n):
        item = df.sample(1, random_state=rng.randint(0, 10**9)).iloc[0]
        kind = rng.choice([
            "INVENTORY_COUNT", "LATERAL_TRANSFER", "CONDITION_CHANGE",
            "ISSUE", "RECEIPT", "INVENTORY_COUNT", "INVENTORY_COUNT",
        ])
        ts = (BASE_DT - timedelta(days=rng.randint(0, 60),
                                  hours=rng.randint(0, 23),
                                  minutes=rng.randint(0, 59)))
        actor = rng.choice(MARINES)
        events.append({
            "ts":          ts.isoformat(),
            "kind":        kind,
            "item_id":     item["item_id"],
            "nsn":         item["nsn"],
            "nomenclature":item["nomenclature"],
            "actor":       actor,
            "from_loc":    item["location_id"] if kind == "LATERAL_TRANSFER" else None,
            "to_loc":      rng.choice([l["id"] for l in LOCATIONS])
                            if kind == "LATERAL_TRANSFER" else item["location_id"],
            "delta_qty":   (-rng.randint(1, 3) if kind == "ISSUE"
                            else rng.randint(1, 3) if kind == "RECEIPT"
                            else 0),
            "note":        {
                "INVENTORY_COUNT":  "Cyclic inventory count complete.",
                "LATERAL_TRANSFER": "Lateral transfer per supply NCO direction.",
                "CONDITION_CHANGE":"Condition code reassessed by armorer.",
                "ISSUE":            "Issued to using unit.",
                "RECEIPT":          "Received from supplier.",
            }[kind],
        })
    events.sort(key=lambda e: e["ts"])
    return events


# ---------------------------------------------------------------------------
# Cached briefs (3 scenarios) — pre-computed so the demo never blocks
# ---------------------------------------------------------------------------

SCENARIOS = [
    {
        "id": "routine",
        "title": "Routine — daily supply NCO brief",
        "frame": "It is 0700 Monday. Surface the top issues for the supply NCO's first stand-up.",
    },
    {
        "id": "pre_deploy",
        "title": "Pre-deployment — 30 days out",
        "frame": "Battalion deploys in 30 days. Surface what could keep it from going.",
    },
    {
        "id": "post_ig",
        "title": "Post-IG — corrective action brief",
        "frame": "An IG inspection just finished. Surface every accountability gap they will cite.",
    },
]


HERO_SYSTEM = """You are STOCKROOM, an AI logistics analyst supporting the
USMC supply NCO under the LOGCOM "Inventory Control Management" published
use case.

You will be given a JSON summary of an inventory of ~5,000 items spread
across warehouses, vehicle bays, and armory rooms. Compose a polished
**"Readiness & Lateral Transfer Brief"** in markdown with these EXACT
sections, in order:

  ### BLUF
  ### Items overdue for inventory
  ### NMC-impacting shortages
  ### Sensitive-item & lateral-transfer flags
  ### Recommended actions for the supply NCO

Constraints:
  - BLUF: one bold sentence stating overall accountability posture.
  - "Items overdue for inventory": cite hard numbers for ROUTINE / SENSITIVE /
    CCI / ARMS / HAZMAT cadence misses and name the top three responsible Marines
    by overdue count.
  - "NMC-impacting shortages": list the top 5 Class VII / Class IX items in
    condition code F or with shortage > 0, with NSN, nomenclature, qty, and
    location.
  - "Sensitive-item & lateral-transfer flags": call out items in ARMS, CCI, or
    SENSITIVE classes that have not been laterally transferred in > 60 days,
    or that are in a location not consistent with their category.
  - "Recommended actions": exactly THREE numbered actions, each tied to a
    specific Marine or location, that the supply NCO can execute today.
  - Total length ~350 words. No invented Marines beyond those named in the input.
  - Do NOT mention the underlying AI provider or model name.
"""


def _summarize_inventory(df: pd.DataFrame) -> dict:
    """Compact summary handed to the hero LLM (so prompt stays small)."""
    overdue = df[df["inventory_overdue"]]
    by_sens = overdue.groupby("sensitivity_class").size().to_dict()
    top_marines = (overdue.groupby("responsible_marine").size()
                   .sort_values(ascending=False).head(5).to_dict())
    nmc = df[df["nmc_impacting"]].head(8)[
        ["item_id", "nsn", "nomenclature", "qty_on_hand", "qty_required",
         "shortage", "condition_code", "location_id", "responsible_marine"]
    ].to_dict("records")
    shortage = df[df["shortage"] > 0].sort_values("shortage", ascending=False).head(8)[
        ["item_id", "nsn", "nomenclature", "qty_on_hand", "qty_required",
         "shortage", "category", "location_id", "responsible_marine"]
    ].to_dict("records")
    sensitive_stale = df[
        (df["sensitivity_class"].isin(["ARMS", "CCI", "SENSITIVE"]))
        & (df["days_since_lateral_transfer"] > 60)
    ].head(10)[
        ["item_id", "nsn", "nomenclature", "sensitivity_class",
         "days_since_lateral_transfer", "location_id", "responsible_marine"]
    ].to_dict("records")

    return {
        "as_of":                 BASE_DT.isoformat(),
        "total_items":           int(len(df)),
        "by_category":           df["category"].value_counts().to_dict(),
        "by_sensitivity":        df["sensitivity_class"].value_counts().to_dict(),
        "by_location":           df["location_id"].value_counts().to_dict(),
        "overdue_total":         int(len(overdue)),
        "overdue_by_sensitivity":{k: int(v) for k, v in by_sens.items()},
        "top_marines_overdue":   {k: int(v) for k, v in top_marines.items()},
        "nmc_items":             nmc,
        "shortage_items":        shortage,
        "sensitive_stale_lateral":sensitive_stale,
    }


def _precompute_briefs(df: pd.DataFrame) -> dict[str, str]:
    """Run hero LLM call for each scenario; persist with a deterministic
    fallback if any call fails or returns nothing useful."""
    try:
        from shared.kamiwaza_client import chat
    except Exception as e:
        print(f"[generate] Could not import shared.kamiwaza_client: {e}")
        chat = None

    summary = _summarize_inventory(df)
    out: dict[str, str] = {}
    for sc in SCENARIOS:
        prompt = (
            f"Scenario: {sc['title']}\n"
            f"Frame: {sc['frame']}\n\n"
            f"INVENTORY SUMMARY (JSON):\n{json.dumps(summary, indent=2, default=str)}\n\n"
            "Compose the Readiness & Lateral Transfer Brief now."
        )
        text = ""
        if chat is not None:
            try:
                text = chat(
                    [
                        {"role": "system", "content": HERO_SYSTEM},
                        {"role": "user",   "content": prompt},
                    ],
                    model="gpt-5.4",
                    temperature=0.4,
                )
            except Exception as e:
                print(f"[generate] hero call failed for {sc['id']}: {e}")
                text = ""
        if not text or "BLUF" not in text:
            text = _fallback_brief(sc, summary)
        out[sc["id"]] = text
        print(f"[generate] cached brief for {sc['id']} ({len(text)} chars)")
    return out


def _fallback_brief(scenario: dict, summary: dict) -> str:
    overdue_total = summary["overdue_total"]
    by_sens = summary["overdue_by_sensitivity"]
    top_marines = summary["top_marines_overdue"]
    nmc = summary["nmc_items"][:5]
    shortage = summary["shortage_items"][:5]
    stale = summary["sensitive_stale_lateral"][:5]
    top_marine_lines = [f"- **{m}** — {c} overdue" for m, c in top_marines.items()]
    nmc_lines = [
        f"- **{r['nomenclature']}** ({r['nsn']}) — qty {r['qty_on_hand']}/{r['qty_required']}, "
        f"cond **{r['condition_code']}**, loc {r['location_id']}, custody {r['responsible_marine']}"
        for r in nmc
    ]
    short_lines = [
        f"- **{r['nomenclature']}** ({r['nsn']}) — short **{r['shortage']}** ({r['qty_on_hand']}/{r['qty_required']}), "
        f"loc {r['location_id']}"
        for r in shortage
    ]
    stale_lines = [
        f"- **{r['nomenclature']}** ({r['nsn']}) — class {r['sensitivity_class']}, "
        f"{r['days_since_lateral_transfer']} days since last lateral transfer, "
        f"loc {r['location_id']}, custody {r['responsible_marine']}"
        for r in stale
    ]
    return (
        f"### BLUF\n"
        f"**{scenario['title']} — {overdue_total:,} of {summary['total_items']:,} items "
        f"are outside their inventory cadence; accountability posture is AMBER.**\n\n"
        f"### Items overdue for inventory\n"
        + "\n".join(f"- {k}: **{v}** items overdue" for k, v in by_sens.items())
        + "\n\nTop responsible Marines by overdue count:\n"
        + "\n".join(top_marine_lines) + "\n\n"
        f"### NMC-impacting shortages\n"
        + ("\n".join(nmc_lines) if nmc_lines else "_No NMC-impacting items detected._")
        + "\n\nAdditional shortages worth chasing:\n"
        + ("\n".join(short_lines) if short_lines else "_No quantity shortages._")
        + "\n\n"
        f"### Sensitive-item & lateral-transfer flags\n"
        + ("\n".join(stale_lines) if stale_lines
           else "_No sensitive items beyond the 60-day lateral-transfer threshold._")
        + "\n\n"
        f"### Recommended actions for the supply NCO\n"
        f"1. Direct **{next(iter(top_marines), 'top responsible Marine')}** to "
        f"close out the overdue inventory backlog before EOB; pair with the duty NCO.\n"
        f"2. Pull the top-5 NMC end items for an immediate condition recheck and "
        f"cross-reference with the Class IX shortage list above.\n"
        f"3. Schedule lateral-transfer cycles for the sensitive items above; prioritize "
        f"any in **ARM-101 / ARM-102 / COMSEC-1**.\n"
    )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main(*, with_briefs: bool = True) -> None:
    rng = random.Random(1776)

    print("[generate] inventory.xlsx (5,000 rows)…")
    df = _generate_inventory(rng, n=5000)
    df.to_excel(ROOT / "inventory.xlsx", index=False, engine="openpyxl")
    df.to_csv(ROOT / "inventory.csv", index=False)

    print("[generate] locations.json…")
    (ROOT / "locations.json").write_text(json.dumps(LOCATIONS, indent=2))

    print("[generate] transactions.jsonl (audit log seed)…")
    events = _generate_transactions(rng, df, n=30)
    with open(ROOT / "transactions.jsonl", "w") as f:
        for e in events:
            f.write(json.dumps(e) + "\n")

    if with_briefs:
        print("[generate] precomputing 3 cached hero briefs (cache-first pattern)…")
        briefs = _precompute_briefs(df)
        (ROOT / "cached_briefs.json").write_text(json.dumps(briefs, indent=2))

    print(f"[generate] done. wrote {len(df):,} items to {ROOT}")


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--no-briefs", action="store_true",
                   help="Skip the LLM hero precompute (synth + JSON only).")
    args = p.parse_args()
    main(with_briefs=not args.no_briefs)
