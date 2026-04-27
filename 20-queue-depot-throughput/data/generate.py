"""QUEUE synthetic data generator.

Produces:
  data/backlog.csv             - ~80 inducted-or-pending end items with priority + est labor hours
  data/depot_capacity.json     - 3 depots (Albany / Barstow / Blount Island) with bay/shift/skill capacity
  data/parts_availability.csv  - per-NSN on-hand + ETA
  data/cached_briefs.json      - pre-computed hero LLM briefs for 3 scenarios

Seeded with random.Random(1776) for reproducibility.
Real-data swap: replace this module with ingest of GCSS-MC depot extracts.
"""
from __future__ import annotations

import csv
import json
import random
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
REPO_ROOT = ROOT.parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


# ---- Master reference data --------------------------------------------------

DEPOTS = [
    {
        "id": "ALB",
        "name": "MCLB Albany",
        "location": "Albany, GA",
        "bays": 14,
        "shifts_per_day": 2,
        "skills": {
            "hydraulics": 18,
            "powertrain": 22,
            "armor": 14,
            "avionics": 6,
            "weapons": 10,
        },
        "specialty": ["MTVR", "LAV", "M1A1"],
    },
    {
        "id": "BAR",
        "name": "MCLB Barstow",
        "location": "Barstow, CA",
        "bays": 12,
        "shifts_per_day": 2,
        "skills": {
            "hydraulics": 14,
            "powertrain": 18,
            "armor": 16,
            "avionics": 4,
            "weapons": 12,
        },
        "specialty": ["AAV", "LAV", "MTVR"],
    },
    {
        "id": "BIC",
        "name": "Blount Island Command",
        "location": "Jacksonville, FL",
        "bays": 10,
        "shifts_per_day": 3,
        "skills": {
            "hydraulics": 12,
            "powertrain": 14,
            "armor": 8,
            "avionics": 16,
            "weapons": 6,
        },
        "specialty": ["MV-22", "AAV"],
    },
]

# End-item families. labor_lo/hi are estimated direct labor hours per induction.
END_ITEMS = [
    # tag, family, labor_lo, labor_hi, primary_skills (heaviest first)
    ("MTVR",  "Medium Tactical Vehicle Replacement",     220, 460,  ["powertrain", "hydraulics"]),
    ("AAV",   "Assault Amphibious Vehicle",              640, 1100, ["armor", "powertrain", "hydraulics"]),
    ("LAV",   "Light Armored Vehicle",                   480, 820,  ["powertrain", "armor", "weapons"]),
    ("MV-22", "MV-22B Osprey",                           1900, 3400, ["avionics", "powertrain", "hydraulics"]),
    ("M1A1",  "M1A1 Abrams Tank",                        2200, 3800, ["armor", "powertrain", "weapons"]),
]

# Priority codes (USMC-style FAD/Force Activity Designator-ish): 1 highest.
PRIORITY_BANDS = [
    (1, "FD-1 / IPL-A — combat-essential"),
    (2, "FD-2 / IPL-B — mission-critical"),
    (3, "FD-3 / Standard — sustainment"),
    (4, "FD-4 / Backlog — recoverable"),
]

# A small pool of NSNs that reflect the kinds of long-pole parts that actually
# bottleneck depot induction (hydraulic seals, transfer cases, prop blades).
PARTS = [
    # nsn, nomenclature, used_by, is_long_pole
    ("4730-01-441-2298", "Hydraulic seal kit, lift assy",          ["MTVR", "AAV", "LAV", "M1A1"], True),
    ("2520-01-562-9981", "Transfer case, ratio 1.85",              ["MTVR", "LAV"],                True),
    ("1680-01-651-2244", "Prop rotor blade, MV-22 (composite)",    ["MV-22"],                       True),
    ("1730-01-498-7102", "Hydraulic actuator, ramp assy",          ["AAV", "M1A1"],                 True),
    ("2920-01-588-4471", "Starter, 24V high-torque",               ["MTVR", "LAV", "AAV"],          False),
    ("5340-01-122-4419", "Bracket, armor liner",                   ["LAV", "M1A1", "AAV"],          False),
    ("4710-01-440-9921", "Hose, hydraulic high-pressure 1.25in",   ["MTVR", "AAV", "LAV", "M1A1"], False),
    ("3110-01-617-8013", "Bearing, prop hub MV-22",                ["MV-22"],                       True),
    ("2540-01-572-3041", "Seat, armored crew (driver)",            ["LAV", "AAV", "MTVR"],          False),
    ("6130-01-651-1182", "Power distribution unit, vehicle",       ["MTVR", "LAV", "AAV", "M1A1"], False),
    ("1240-01-602-7715", "Optical sight assembly, M1A1",           ["M1A1"],                        True),
    ("2935-01-510-9923", "Fuel control, MV-22 engine",             ["MV-22"],                       True),
    ("5305-01-118-4422", "Bolt, armor track shoe",                 ["AAV", "M1A1"],                 False),
    ("2920-01-518-9912", "Alternator, 28V 300A",                   ["MTVR", "LAV", "AAV", "M1A1"], False),
    ("1660-01-560-2218", "Environmental control unit, crew cab",   ["MV-22", "AAV", "M1A1"],        False),
]


# ---- Scenario seeds ---------------------------------------------------------

SCENARIOS = [
    {
        "id": "baseline",
        "label": "Baseline — current posture",
        "description": "Steady-state induction at MCLB Albany / Barstow / Blount Island. Backlog as inherited, parts on-hand at policy levels, single-shift normal posture.",
        "workforce_mult": 1.0,
        "release_held_parts": False,
        "priority_bias": "balanced",
    },
    {
        "id": "surge",
        "label": "Surge — Force Design 2030 push",
        "description": "MARFORPAC Stand-In Forces backlog draw-down: workforce surged 1.4x via overtime + reservist augmentation; held-parts pool released; priority weights tilt toward FD-1/FD-2.",
        "workforce_mult": 1.4,
        "release_held_parts": True,
        "priority_bias": "fd1_first",
    },
    {
        "id": "parts_constrained",
        "label": "Parts-constrained — long-pole NSN slip",
        "description": "Three long-pole NSNs (hydraulic seals, MV-22 prop blade, transfer case) slip 30 days. Workforce normal. Tests parts cascading effects.",
        "workforce_mult": 1.0,
        "release_held_parts": False,
        "priority_bias": "balanced",
        "parts_slip": True,
    },
]


# ---- Generators -------------------------------------------------------------

def _today() -> datetime:
    return datetime(2026, 4, 27, 8, 0, 0, tzinfo=timezone.utc)


def generate_backlog(rng: random.Random, n: int = 80) -> list[dict]:
    """Create ~80 backlog rows mixing all five end-item families."""
    rows = []
    today = _today()
    # weighted family distribution (more wheeled vehicles, fewer aircraft/tanks)
    weights = {"MTVR": 24, "AAV": 18, "LAV": 16, "MV-22": 12, "M1A1": 10}
    families = []
    for f, w in weights.items():
        families.extend([f] * w)
    rng.shuffle(families)

    for i in range(n):
        family = families[i % len(families)]
        spec = next(s for s in END_ITEMS if s[0] == family)
        _, family_long, lo, hi, skills = spec
        labor_hrs = rng.randint(lo, hi)
        # Priority: weighted skew toward FD-3 sustainment with some FD-1/2.
        priority = rng.choices([1, 2, 3, 4], weights=[15, 25, 45, 15])[0]
        # Induction (received) date: spread across last 90 days.
        induct_date = today - timedelta(days=rng.randint(0, 90))
        # Each item needs 1-3 long-pole parts from the family pool.
        eligible = [p for p in PARTS if family in p[2]]
        rng.shuffle(eligible)
        required_parts = [p[0] for p in eligible[:rng.randint(1, 3)]]
        # Assigned depot biased by depot specialty list, with some overflow.
        candidate_depots = [d["id"] for d in DEPOTS if family in d["specialty"]]
        if not candidate_depots:
            candidate_depots = [d["id"] for d in DEPOTS]
        # 80% specialty, 20% overflow to any depot
        if rng.random() < 0.8:
            depot = rng.choice(candidate_depots)
        else:
            depot = rng.choice([d["id"] for d in DEPOTS])
        # Status: PENDING (not yet started) vs INDUCTED (in work).
        status = rng.choices(["PENDING", "INDUCTED"], weights=[70, 30])[0]
        bumper = f"{family[:3].upper()}-{1000 + i}"
        rows.append({
            "bumper_no": bumper,
            "family": family,
            "family_long": family_long,
            "depot": depot,
            "priority": priority,
            "priority_label": next(p[1] for p in PRIORITY_BANDS if p[0] == priority),
            "labor_hours_est": labor_hrs,
            "skills_needed": ",".join(skills),
            "required_parts_nsn": ",".join(required_parts),
            "induct_date": induct_date.strftime("%Y-%m-%d"),
            "status": status,
        })
    # Sort: priority asc (1 first), then induct_date asc (older first)
    rows.sort(key=lambda r: (r["priority"], r["induct_date"]))
    return rows


def generate_parts_availability(rng: random.Random) -> list[dict]:
    """Per-NSN on-hand stock + ETA for items not on hand."""
    today = _today()
    out = []
    for nsn, name, used_by, is_long_pole in PARTS:
        # Long-pole NSNs frequently zero on hand with multi-week ETA.
        if is_long_pole:
            on_hand = rng.choices([0, 0, 0, 1, 2, 4], weights=[30, 25, 15, 12, 10, 8])[0]
            eta_days = rng.choices([7, 14, 21, 28, 45, 60], weights=[10, 18, 22, 22, 16, 12])[0]
        else:
            on_hand = rng.randint(8, 60)
            eta_days = rng.choices([0, 3, 7, 14], weights=[55, 25, 12, 8])[0]
        eta_date = (today + timedelta(days=eta_days)).strftime("%Y-%m-%d") if eta_days else ""
        unit_cost = rng.choice([
            450, 1200, 3400, 7800, 12500, 28000, 64000, 110000, 230000
        ])
        out.append({
            "nsn": nsn,
            "nomenclature": name,
            "used_by": ",".join(used_by),
            "on_hand": on_hand,
            "eta_days": eta_days,
            "eta_date": eta_date,
            "long_pole": "Y" if is_long_pole else "N",
            "unit_cost_usd": unit_cost,
            "source": rng.choice(["DLA Land", "DLA Aviation", "OEM (Oshkosh)", "OEM (BAE)", "OEM (Bell-Boeing)"]),
        })
    return out


# ---- Cached briefs (hero LLM pre-compute) ----------------------------------

def _scenario_prompt(scenario: dict, backlog: list[dict], capacity_summary: str,
                     parts_summary: str, top_bottleneck: str) -> list[dict]:
    system = (
        "You are QUEUE, a USMC depot maintenance scheduling analyst supporting "
        "MARCORLOGCOM. You produce concise operator-grade decision briefs for "
        "the depot industrial-base directorate (MCLB Albany, MCLB Barstow, "
        "Blount Island Command).\n\n"
        "OUTPUT FORMAT (markdown):\n"
        "Open with **BLUF** (one bold paragraph, 2-3 sentences) naming the "
        "single biggest bottleneck and the projected throughput uplift if "
        "operators take the recommended actions over the next 30 days.\n\n"
        "Then EXACTLY these sections, in order:\n"
        "  ## NAMED BOTTLENECK\n"
        "  ## PARTS AVAILABILITY — CASCADING EFFECTS\n"
        "  ## TOP 5 ACTIONS (NEXT 30 DAYS)\n"
        "  ## ALTERNATIVE INDUCTION SEQUENCES\n"
        "  ## CLASSIFICATION\n\n"
        "In NAMED BOTTLENECK: name the specific resource (e.g. \"Bay 4 hydraulic "
        "lift availability — MCLB Albany\" or \"Hydraulic seal kit NSN "
        "4730-01-441-2298 — DLA Land 28-day ETA\"). Quantify with numbers.\n"
        "In PARTS section: list 3-5 long-pole NSNs and their downstream effect on "
        "MTVR / AAV / LAV / MV-22 / M1A1 induction throughput.\n"
        "In ACTIONS: numbered 1-5, each one sentence, each tied to a specific "
        "depot or NSN, with a quantified throughput-uplift estimate.\n"
        "In ALTERNATIVE SEQUENCES: 2-3 candidate re-sequencing options, each "
        "with the trade-off (e.g. \"Pull MV-22 inductions forward at BIC; defer "
        "two LAV inductions at BAR — net +N units / 30 days\").\n"
        "Close CLASSIFICATION with: UNCLASSIFIED // FOR OFFICIAL USE.\n\n"
        "Keep total output under ~480 words. Be specific. Use real depot codes "
        "(ALB / BAR / BIC) and real end-item families."
    )
    backlog_summary = (
        f"BACKLOG: {len(backlog)} end items inducted-or-pending across 3 depots.\n"
        f"By family: " + ", ".join(
            f"{fam}={sum(1 for b in backlog if b['family']==fam)}"
            for fam in ["MTVR", "AAV", "LAV", "MV-22", "M1A1"]
        )
        + ".\n"
        f"By priority: " + ", ".join(
            f"FD-{p}={sum(1 for b in backlog if b['priority']==p)}"
            for p in [1, 2, 3, 4]
        ) + "."
    )
    user = (
        f"SCENARIO: {scenario['label']}\n"
        f"Description: {scenario['description']}\n"
        f"Workforce multiplier: {scenario['workforce_mult']}x\n"
        f"Release held parts: {scenario['release_held_parts']}\n\n"
        f"{backlog_summary}\n\n"
        f"DEPOT CAPACITY SUMMARY:\n{capacity_summary}\n\n"
        f"PARTS AVAILABILITY SUMMARY:\n{parts_summary}\n\n"
        f"DETERMINISTIC OPTIMIZER OUTPUT (top bottleneck):\n{top_bottleneck}\n\n"
        f"Compose the Depot Throughput Optimization Brief now."
    )
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]


def _capacity_summary(depots: list[dict]) -> str:
    lines = []
    for d in depots:
        skills = ", ".join(f"{k}={v}" for k, v in d["skills"].items())
        lines.append(
            f"- {d['name']} ({d['id']}): {d['bays']} bays x {d['shifts_per_day']} shifts; "
            f"specialty={','.join(d['specialty'])}; skills={skills}"
        )
    return "\n".join(lines)


def _parts_summary(parts: list[dict]) -> str:
    lines = []
    for p in parts:
        if p["long_pole"] != "Y":
            continue
        lines.append(
            f"- NSN {p['nsn']} ({p['nomenclature']}): on_hand={p['on_hand']}, "
            f"ETA={p['eta_days']}d ({p['source']}), used_by={p['used_by']}"
        )
    return "\n".join(lines)


def _deterministic_brief(scenario: dict, top_bottleneck: str) -> str:
    """Fallback brief shape used when LLM is unreachable. Same headers."""
    return (
        f"**BLUF.** Scenario *{scenario['label']}*: the single biggest constraint on "
        f"30-day depot throughput is **{top_bottleneck}**. With the recommended "
        f"actions below, projected uplift over the next 30 days is "
        f"**+{int(8 + scenario['workforce_mult']*6)}%** across MCLB Albany, MCLB "
        f"Barstow, and Blount Island Command.\n\n"
        f"## NAMED BOTTLENECK\n"
        f"{top_bottleneck}. This resource gates the heaviest-labor inductions "
        f"(M1A1, MV-22) and cascades into the FD-1/FD-2 priority backlog.\n\n"
        f"## PARTS AVAILABILITY — CASCADING EFFECTS\n"
        f"- NSN 4730-01-441-2298 (Hydraulic seal kit) — 0 on hand, 28d ETA via DLA Land. Gates MTVR / AAV / LAV / M1A1 inductions across all 3 depots.\n"
        f"- NSN 1680-01-651-2244 (MV-22 prop rotor blade composite) — 0 on hand, 45d ETA. Gates Blount Island MV-22 throughput.\n"
        f"- NSN 1730-01-498-7102 (Hydraulic actuator, ramp assy) — 1 on hand, 21d ETA. Gates AAV / M1A1 induction at MCLB Barstow.\n"
        f"- NSN 1240-01-602-7715 (M1A1 optical sight assy) — 0 on hand, 60d ETA. Gates M1A1 induction at MCLB Albany.\n\n"
        f"## TOP 5 ACTIONS (NEXT 30 DAYS)\n"
        f"1. Expedite hydraulic seal kit NSN 4730-01-441-2298 via DLA Land emergency requisition — projected +6% MTVR/AAV throughput at ALB and BAR.\n"
        f"2. Cross-deck two MV-22 prop rotor blades from organizational stock to BIC — projected +3 MV-22 inductions completed in window.\n"
        f"3. Reallocate two hydraulics technicians from BAR to ALB on second shift — projected +4% LAV throughput at ALB.\n"
        f"4. Defer 5 FD-3 LAV inductions at BAR by 14 days; pull 3 FD-1 MTVR inductions forward — net +5 priority units in window.\n"
        f"5. Place a held-parts release request on M1A1 optical sight NSN 1240-01-602-7715 to unblock 4 M1A1 inductions queued at ALB.\n\n"
        f"## ALTERNATIVE INDUCTION SEQUENCES\n"
        f"- **Sequence A — Priority-pure:** Strict FD-1/FD-2 first across all depots. +12% priority-weighted throughput, but bay-utilization drops to 78%.\n"
        f"- **Sequence B — Bay-utilization max:** Fill bays by labor-fit regardless of FD code. +18% raw throughput, but FD-3/FD-4 backlog ages.\n"
        f"- **Sequence C — Parts-aware (recommended):** Schedule each induction window to its required-parts ETA. +14% throughput, FD-1 inducted on time, no idle bays.\n\n"
        f"## CLASSIFICATION\n"
        f"UNCLASSIFIED // FOR OFFICIAL USE.\n"
    )


def precompute_briefs(backlog: list[dict], depots: list[dict],
                      parts: list[dict]) -> dict:
    """Generate the 3 cached scenario briefs.

    Tries the live LLM (cap 35s per call). On any failure, falls back to a
    deterministic brief with the same shape so the demo never hangs.
    """
    try:
        from shared.kamiwaza_client import chat
        have_llm = True
    except Exception:
        have_llm = False

    cap_sum = _capacity_summary(depots)
    parts_sum = _parts_summary(parts)
    out = {}
    for scenario in SCENARIOS:
        # Determine the canonical bottleneck per scenario
        if scenario.get("parts_slip"):
            top_bn = ("Hydraulic seal kit NSN 4730-01-441-2298 — 0 on hand, "
                      "28d ETA from DLA Land")
        elif scenario["workforce_mult"] >= 1.3:
            top_bn = "Bay 4 hydraulic lift availability — MCLB Albany"
        else:
            top_bn = ("Hydraulic seal kit NSN 4730-01-441-2298 — 0 on hand, "
                      "28d ETA from DLA Land")
        text = None
        if have_llm:
            try:
                import concurrent.futures
                msgs = _scenario_prompt(scenario, backlog, cap_sum, parts_sum, top_bn)
                with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
                    text = ex.submit(
                        lambda: chat(msgs, model="gpt-5.4", temperature=0.45)
                    ).result(timeout=35.0)
                if not text or "BLUF" not in text:
                    text = None
            except Exception:
                text = None
        if not text:
            text = _deterministic_brief(scenario, top_bn)
        out[scenario["id"]] = {
            "label": scenario["label"],
            "description": scenario["description"],
            "workforce_mult": scenario["workforce_mult"],
            "release_held_parts": scenario["release_held_parts"],
            "top_bottleneck": top_bn,
            "brief": text,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "source": "gpt-5.4" if (have_llm and text and "BLUF" in text and "1." in text) else "deterministic",
        }
    return out


# ---- main -------------------------------------------------------------------

def main(*, do_briefs: bool = True) -> None:
    rng = random.Random(1776)
    backlog = generate_backlog(rng, n=80)
    parts = generate_parts_availability(rng)

    # Write CSVs
    backlog_path = ROOT / "backlog.csv"
    with backlog_path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(backlog[0].keys()))
        w.writeheader()
        w.writerows(backlog)

    parts_path = ROOT / "parts_availability.csv"
    with parts_path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(parts[0].keys()))
        w.writeheader()
        w.writerows(parts)

    # Depot capacity
    (ROOT / "depot_capacity.json").write_text(json.dumps(DEPOTS, indent=2))

    # Scenarios manifest
    (ROOT / "scenarios.json").write_text(json.dumps(SCENARIOS, indent=2))

    print(f"Wrote {len(backlog)} backlog rows, {len(parts)} parts rows, "
          f"{len(DEPOTS)} depots.")
    print(f"  -> {ROOT}")

    if do_briefs:
        briefs = precompute_briefs(backlog, DEPOTS, parts)
        (ROOT / "cached_briefs.json").write_text(json.dumps(briefs, indent=2))
        print(f"Wrote {len(briefs)} cached briefs.")


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--no-briefs", action="store_true",
                   help="Skip pre-computing cached briefs (LLM-free).")
    args = p.parse_args()
    main(do_briefs=not args.no_briefs)
