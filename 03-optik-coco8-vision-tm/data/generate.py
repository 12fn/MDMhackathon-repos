"""OPTIK synthetic data generator.

Outputs:
  data/tm_snippets.json  — ~30 fake but realistically-formatted TM snippets
  data/tm_index.npz      — embedding matrix for cosine RAG (optional, see embed_index)
  sample_images/*.jpg    — 5 demo images (downloaded from Ultralytics COCO8 + 1 fallback)

Run:
  python data/generate.py
  python data/generate.py --embed   (also build embedding index — needs Kamiwaza endpoint or OPENAI_API_KEY fallback)

Reproducible: seeded with random.Random(1776).

NOTE (2026-04-27 fix): Previously the generator randomly paired
{vehicle, section, component} which produced nonsense like "Cooling System"
on an M1101 trailer or "Drive Belts" filed under a CTIS valve. A maintainer
would reject the corpus in 30 seconds. The generator now iterates a curated
TM_TEMPLATES dict so every snippet is internally consistent: the component
actually belongs on the vehicle and lives in the named section.
"""
from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path

import urllib.request

# Make shared/ importable when run as a script.
ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

DATA_DIR = Path(__file__).resolve().parent
SAMPLES_DIR = DATA_DIR.parent / "sample_images"
SEED = 1776


# ---------------------------------------------------------------------------
# TM snippet synthesizer — CURATED so vehicle / section / component all match.
# ---------------------------------------------------------------------------

# Real TM number prefixes (publicly known on USMC supply lists). Snippet bodies
# are synthetic but plausible — torques, NSN families, and lubricants are drawn
# from the actual TM family for that platform.
#
# Each template is an internally-consistent maintenance task:
#   - section is a section that actually exists on that vehicle's TM
#   - component is a part that lives in that section
#   - figure is roughly themed to the section
#   - torque / fluid / failure all match the component
TM_TEMPLATES: dict[str, dict] = {
    "MTVR MK23": {
        "tm": "TM 11240A-OR/B",
        "snippets": [
            {
                "section": "Section 5.9 — Cooling System",
                "component": "engine coolant thermostat housing",
                "figure": "Figure 5-9. Coolant thermostat housing torque sequence (1-3-2-4 cross pattern).",
                "nsn_base": "2930-01",
                "torque": (22, 28),
                "fluid": "MIL-A-46153 ELC coolant",
                "failure": "weep at gasket from over-torque",
                "pmcs": "Q",
            },
            {
                "section": "Section 3.1 — Drive Belts",
                "component": "alternator drive belt (serpentine, 7-rib)",
                "figure": "Figure 3-1. Serpentine belt routing — 7-rib, MTVR caterpillar engine.",
                "nsn_base": "3030-01",
                "torque": (None, None),
                "fluid": "n/a",
                "failure": "glazing + 8% length elongation — replace at 250 hr",
                "pmcs": "S",
            },
            {
                "section": "Section 12.3 — Turbocharger Service",
                "component": "turbocharger oil supply line",
                "figure": "Figure 12-3. Turbocharger lubrication circuit schematic.",
                "nsn_base": "2950-01",
                "torque": (18, 22),
                "fluid": "MIL-PRF-2104J 15W-40",
                "failure": "chafing against bracket — replace clamp P/N 5340-01",
                "pmcs": "M",
            },
            {
                "section": "Section 8.14 — Transfer Case",
                "component": "transfer-case input shaft seal",
                "figure": "Figure 8-14. Transfer-case input/output shaft seal arrangement.",
                "nsn_base": "2520-01",
                "torque": (45, 55),
                "fluid": "MIL-PRF-2105E 75W-90",
                "failure": "Class III leak at output flange",
                "pmcs": "AN",
            },
            {
                "section": "Section 4.7 — CTIS (Central Tire Inflation System)",
                "component": "CTIS wheel valve",
                "figure": "Figure 4-7. CTIS valve assembly, exploded view (item 3 is the gasket).",
                "nsn_base": "2540-01",
                "torque": (32, 38),
                "fluid": "MIL-PRF-46170 hydraulic fluid",
                "failure": "seal seepage at hose collar",
                "pmcs": "B",
            },
        ],
    },
    "MTVR MK25": {
        "tm": "TM 11240A-OR/B",
        "snippets": [
            {
                "section": "Section 9.22 — Transmission Cooling",
                "component": "transmission oil cooler return line",
                "figure": "Figure 9-22. Transmission cooler line layout, return side.",
                "nsn_base": "4720-01",
                "torque": (35, 42),
                "fluid": "Dexron VI ATF",
                "failure": "vibration fatigue at compression sleeve",
                "pmcs": "M",
            },
            {
                "section": "Section 10.1 — Fuel System",
                "component": "fuel-water separator drain plug",
                "figure": "Figure 10-1. Fuel/water separator with manual drain.",
                "nsn_base": "2910-01",
                "torque": (8, 10),
                "fluid": "F-24 fuel",
                "failure": "stripped threads — install heli-coil P/N 5340-01",
                "pmcs": "B",
            },
            {
                "section": "Section 11.8 — Brake Service",
                "component": "front brake caliper guide pin",
                "figure": "Figure 11-8. Brake caliper guide pin removal.",
                "nsn_base": "2530-01",
                "torque": (32, 38),
                "fluid": "MIL-PRF-10924 grease",
                "failure": "frozen pin from corrosion",
                "pmcs": "Q",
            },
        ],
    },
    "MTVR Wrecker MK36": {
        "tm": "TM 11240A-23&P/3",
        "snippets": [
            {
                "section": "Section 14.2 — Recovery Winch",
                "component": "hydraulic winch motor (35,000 lb recovery winch)",
                "figure": "Figure 14-2. Recovery winch hydraulic motor exploded view.",
                "nsn_base": "3950-01",
                "torque": (60, 75),
                "fluid": "MIL-PRF-46170",
                "failure": "no rotation under load — internal vane wear",
                "pmcs": "S",
            },
            {
                "section": "Section 14.5 — Boom Hydraulics",
                "component": "boom extension hydraulic cylinder rod seal",
                "figure": "Figure 14-5. Boom cylinder seal kit, item 4.",
                "nsn_base": "1730-01",
                "torque": (None, None),
                "fluid": "MIL-PRF-46170",
                "failure": "Class III leak at rod gland — full seal kit replacement",
                "pmcs": "Q",
            },
        ],
    },
    "LVSR MK31": {
        "tm": "TM 11035A-OR/A",
        "snippets": [
            {
                "section": "Section 6.2 — Suspension (Hydropneumatic)",
                "component": "hydropneumatic suspension strut accumulator",
                "figure": "Figure 6-2. LVSR hydropneumatic strut, charge port location.",
                "nsn_base": "2510-01",
                "torque": (180, 220),
                "fluid": "MIL-PRF-46170 + dry nitrogen charge",
                "failure": "loss of nitrogen pre-charge — strut bottoms over road shock",
                "pmcs": "AN",
            },
            {
                "section": "Section 8.4 — Transfer Case",
                "component": "transfer-case input shaft seal",
                "figure": "Figure 8-4. LVSR transfer-case seal arrangement.",
                "nsn_base": "2520-01",
                "torque": (45, 55),
                "fluid": "MIL-PRF-2105E 75W-90",
                "failure": "Class III leak at output flange",
                "pmcs": "AN",
            },
            {
                "section": "Section 4.7 — CTIS (Central Tire Inflation System)",
                "component": "CTIS wheel valve",
                "figure": "Figure 4-7. LVSR CTIS valve, 10-wheel layout.",
                "nsn_base": "2540-01",
                "torque": (32, 38),
                "fluid": "MIL-PRF-46170 hydraulic fluid",
                "failure": "seal seepage at hose collar",
                "pmcs": "B",
            },
        ],
    },
    "HMMWV M1151A1": {
        "tm": "TM 9-2320-387-23",
        "snippets": [
            {
                "section": "Section 7.4 — Steering Gear",
                "component": "steering gear sector shaft seal",
                "figure": "Figure 7-4. Steering gear assembly cutaway.",
                "nsn_base": "2530-01",
                "torque": (140, 160),
                "fluid": "MIL-PRF-46170",
                "failure": "Class III leak — bring vehicle to NMC",
                "pmcs": "M",
            },
            {
                "section": "Section 5.6 — Cooling System",
                "component": "engine coolant fan clutch",
                "figure": "Figure 5-6. HMMWV fan clutch, viscous-drive type.",
                "nsn_base": "2930-01",
                "torque": (22, 28),
                "fluid": "MIL-A-46153 ELC coolant",
                "failure": "no clutch engagement above 200 F — replace assy",
                "pmcs": "Q",
            },
            {
                "section": "Section 9.3 — Drive Train (Geared Hubs)",
                "component": "geared hub output seal",
                "figure": "Figure 9-3. HMMWV geared hub cross-section.",
                "nsn_base": "2520-01",
                "torque": (60, 75),
                "fluid": "MIL-PRF-2105E 80W-90 GO",
                "failure": "Class III leak at hub face — gear oil contaminating brake",
                "pmcs": "S",
            },
            {
                "section": "Section 11.4 — Brake Service",
                "component": "front brake caliper guide pin",
                "figure": "Figure 11-4. HMMWV brake caliper service.",
                "nsn_base": "2530-01",
                "torque": (32, 38),
                "fluid": "MIL-PRF-10924 grease",
                "failure": "frozen pin from corrosion",
                "pmcs": "Q",
            },
        ],
    },
    "JLTV M1278": {
        "tm": "TM 9-2320-447-23",
        "snippets": [
            {
                "section": "Section 6.2 — Independent Suspension",
                "component": "front upper control arm bushing",
                "figure": "Figure 6-2. JLTV upper control arm pivot.",
                "nsn_base": "2510-01",
                "torque": (180, 220),
                "fluid": "MIL-PRF-10924 grease",
                "failure": "play exceeds 0.030 in — replace pair",
                "pmcs": "S",
            },
            {
                "section": "Section 12.4 — Engine Aftercooler",
                "component": "charge-air cooler outlet hose clamp",
                "figure": "Figure 12-4. JLTV CAC plumbing, intake side.",
                "nsn_base": "2950-01",
                "torque": (8, 10),
                "fluid": "n/a",
                "failure": "boost leak under load — torque the t-bolt clamp",
                "pmcs": "M",
            },
            {
                "section": "Section 16.1 — Vehicle Network (J3 ECM)",
                "component": "ECM (Engine Control Module) connector J3",
                "figure": "Figure 16-1. ECM connector pinout, J3 (powertrain).",
                "nsn_base": "5998-01",
                "torque": (None, None),
                "fluid": "n/a",
                "failure": "green-pin corrosion — clean per MIL-DTL-83488",
                "pmcs": "Q",
            },
        ],
    },
    "AAV-7A1": {
        "tm": "TM 09674A-23&P",
        "snippets": [
            {
                "section": "Section 13.2 — Bilge & Water Egress",
                "component": "bilge pump impeller (forward bilge well)",
                "figure": "Figure 13-2. AAV forward bilge pump assembly.",
                "nsn_base": "4320-01",
                "torque": (None, None),
                "fluid": "n/a",
                "failure": "fouled impeller — replace and verify Y-valve alignment",
                "pmcs": "B",
            },
            {
                "section": "Section 13.5 — Hatch & Hull Seals",
                "component": "amphibious seal kit, commander's hatch coaming",
                "figure": "Figure 13-5. Hatch coaming seal cross-section.",
                "nsn_base": "2540-01",
                "torque": (None, None),
                "fluid": "silicone grease MIL-S-8660",
                "failure": "cracked durometer — annual replacement",
                "pmcs": "AN",
            },
            {
                "section": "Section 9.1 — Final Drive",
                "component": "final drive output seal",
                "figure": "Figure 9-1. AAV final drive cross-section.",
                "nsn_base": "2520-01",
                "torque": (140, 160),
                "fluid": "MIL-PRF-2105E 80W-90 GO",
                "failure": "Class III leak — gear oil onto track pad",
                "pmcs": "S",
            },
        ],
    },
    "ACV Personnel": {
        "tm": "TM 09704A-OR/A",
        "snippets": [
            {
                "section": "Section 13.4 — Marine Drive (Waterjet)",
                "component": "waterjet steering nozzle actuator",
                "figure": "Figure 13-4. ACV waterjet steering nozzle hydraulic actuator.",
                "nsn_base": "1905-01",
                "torque": (60, 75),
                "fluid": "MIL-PRF-46170 hydraulic fluid",
                "failure": "sluggish nozzle response — bleed actuator and check for air ingress",
                "pmcs": "Q",
            },
            {
                "section": "Section 5.4 — Cooling System",
                "component": "engine coolant heat exchanger (sea-water raw side)",
                "figure": "Figure 5-4. ACV heat exchanger with raw-water/coolant divider plate.",
                "nsn_base": "2930-01",
                "torque": (22, 28),
                "fluid": "MIL-A-46153 ELC coolant",
                "failure": "raw-water side fouled with marine growth — flush and re-pressure test",
                "pmcs": "S",
            },
            {
                "section": "Section 4.7 — CTIS (Central Tire Inflation System)",
                "component": "CTIS wheel valve (8x8)",
                "figure": "Figure 4-7. ACV CTIS valve, 8-wheel layout.",
                "nsn_base": "2540-01",
                "torque": (32, 38),
                "fluid": "MIL-PRF-46170 hydraulic fluid",
                "failure": "seal seepage at hose collar",
                "pmcs": "B",
            },
            {
                "section": "Section 16.3 — Crew Comms",
                "component": "crewman's helmet ICS cable",
                "figure": "Figure 16-3. ACV intercom cable routing.",
                "nsn_base": "5995-01",
                "torque": (None, None),
                "fluid": "n/a",
                "failure": "intermittent — flex-test connectors",
                "pmcs": "W",
            },
        ],
    },
    "MEP-803A 10kW Generator Set": {
        "tm": "TM 9-6115-642-24",
        "snippets": [
            {
                "section": "Section 4.1 — Fuel Injection",
                "component": "engine fuel injector",
                "figure": "Figure 4-1. MEP-803A injector, 3-cyl Yanmar.",
                "nsn_base": "2910-01",
                "torque": (35, 40),
                "fluid": "F-24 fuel",
                "failure": "spray pattern out of spec — replace as a set of 3",
                "pmcs": "S",
            },
            {
                "section": "Section 5.2 — Cooling System (Air-Cooled)",
                "component": "cooling fan shroud mounting bracket",
                "figure": "Figure 5-2. MEP-803A cooling fan shroud.",
                "nsn_base": "2930-01",
                "torque": (12, 15),
                "fluid": "n/a",
                "failure": "fatigue crack at weld — replace bracket P/N 5340-01",
                "pmcs": "M",
            },
            {
                "section": "Section 6.1 — Generator End",
                "component": "voltage regulator (AVR) module",
                "figure": "Figure 6-1. MEP-803A AVR mounting panel.",
                "nsn_base": "6110-01",
                "torque": (None, None),
                "fluid": "n/a",
                "failure": "voltage hunting under load — replace AVR",
                "pmcs": "AN",
            },
        ],
    },
    "M870A3 Trailer": {
        "tm": "TM 9-2330-381-14&P",
        "snippets": [
            {
                "section": "Section 6.2 — Kingpin",
                "component": "kingpin upper bushing",
                "figure": "Figure 6-2. Kingpin assembly with upper/lower bushing locations.",
                "nsn_base": "2530-01",
                "torque": (180, 220),
                "fluid": "MIL-PRF-2105E 80W-90 GO",
                "failure": "ovalized bore from missed lube",
                "pmcs": "AN",
            },
            {
                "section": "Section 11.2 — Air Brake System",
                "component": "spring brake actuator (rear axle)",
                "figure": "Figure 11-2. M870A3 spring brake actuator.",
                "nsn_base": "2530-01",
                "torque": (140, 160),
                "fluid": "n/a",
                "failure": "leaking diaphragm — emergency brake will not release",
                "pmcs": "Q",
            },
            {
                "section": "Section 8.3 — Wheels & Tires",
                "component": "wheel bearing (outer, lowbed axle)",
                "figure": "Figure 8-3. M870A3 wheel hub & bearing arrangement.",
                "nsn_base": "3110-01",
                "torque": (60, 75),
                "fluid": "MIL-PRF-10924 grease",
                "failure": "grease seal weep — repack and replace seal",
                "pmcs": "S",
            },
        ],
    },
    "M1101 Trailer": {
        "tm": "TM 9-2330-392-14&P",
        "snippets": [
            {
                "section": "Section 8.3 — Wheels & Tires",
                "component": "wheel bearing (outer)",
                "figure": "Figure 8-3. M1101 wheel hub cutaway.",
                "nsn_base": "3110-01",
                "torque": (60, 75),
                "fluid": "MIL-PRF-10924 grease",
                "failure": "grease seal weep — repack and replace seal",
                "pmcs": "S",
            },
            {
                "section": "Section 10.4 — Lighting",
                "component": "tail light lens & gasket",
                "figure": "Figure 10-4. M1101 tail light assembly, blackout & service.",
                "nsn_base": "6220-01",
                "torque": (None, None),
                "fluid": "n/a",
                "failure": "cracked lens — water ingress to socket",
                "pmcs": "B",
            },
            {
                "section": "Section 7.1 — Lunette & Hitch",
                "component": "lunette ring (3-inch tow eye)",
                "figure": "Figure 7-1. M1101 lunette ring & safety chain attach.",
                "nsn_base": "2540-01",
                "torque": (180, 220),
                "fluid": "MIL-PRF-10924 grease",
                "failure": "wear groove > 1/8 in — condemn lunette",
                "pmcs": "M",
            },
            {
                "section": "Section 11.6 — Surge Brake",
                "component": "surge brake actuator master cylinder",
                "figure": "Figure 11-6. M1101 surge brake actuator.",
                "nsn_base": "2530-01",
                "torque": (32, 38),
                "fluid": "DOT-5 silicone brake fluid",
                "failure": "low pedal — bleed system or replace cylinder",
                "pmcs": "Q",
            },
            {
                "section": "Section 6.4 — Frame & Chassis",
                "component": "leaf-spring U-bolt",
                "figure": "Figure 6-4. M1101 leaf-spring U-bolt torque pattern.",
                "nsn_base": "5306-01",
                "torque": (140, 160),
                "fluid": "n/a",
                "failure": "loose U-bolt — re-torque per cross pattern",
                "pmcs": "S",
            },
        ],
    },
}

INSPECTION_LEVELS = ["Operator (Crew)", "Field Maintainer (3rd echelon)", "Sustainment (5th echelon depot)"]
CLASSES = ["Class I (no action)", "Class II (monitor at next PMCS)", "Class III (corrective action required)"]

# Real PMCS interval codes from TM-10 series:
#   B = Before, D = During, A = After, W = Weekly, M = Monthly,
#   Q = Quarterly, S = Semi-annual, AN = Annual.
# (SLEP is the Service Life Extension Program — NOT a PMCS interval.)
PMCS_CODES = ["B", "D", "A", "W", "M", "Q", "S", "AN"]


def _nsn(rng: random.Random, base: str) -> str:
    """Build a NIIN-correct-shape NSN: NNNN-CC-NNN-NNNN."""
    return f"{base}-{rng.randrange(100, 999)}-{rng.randrange(1000, 9999)}"


def _torque_str(rng: random.Random, lo: int | None, hi: int | None) -> str:
    if lo is None:
        return "_no torque (visual / wear inspection only)_"
    val = rng.randint(lo, hi)
    nm = round(val * 1.3558, 1)
    return f"**{val} ft-lb ({nm} N-m)**"


def _flatten_templates() -> list[tuple[str, str, dict]]:
    """Return [(vehicle, tm_number, template_dict), ...] in a stable order."""
    out: list[tuple[str, str, dict]] = []
    for vehicle, block in TM_TEMPLATES.items():
        tm = block["tm"]
        for tmpl in block["snippets"]:
            out.append((vehicle, tm, tmpl))
    return out


def make_snippet(rng: random.Random, idx: int, vehicle: str, tm: str, tmpl: dict) -> dict:
    sec = tmpl["section"]
    comp = tmpl["component"]
    fig = tmpl["figure"]
    nsn_base = tmpl["nsn_base"]
    torque = tmpl["torque"]
    fluid = tmpl["fluid"]
    failure = tmpl["failure"]
    pmcs = tmpl.get("pmcs") or rng.choice(PMCS_CODES)

    level = rng.choice(INSPECTION_LEVELS)
    klass = rng.choice(CLASSES)

    primary_nsn = _nsn(rng, nsn_base)
    gasket_nsn = _nsn(rng, "5330-01")
    seal_nsn = _nsn(rng, "5330-01")

    # Compute the torque string ONCE so step 6 echoes the same value as the header.
    torque_header = _torque_str(rng, *torque)

    body = f"""# {tm} — {vehicle}
## {sec}

**Component:** {comp}
**Echelon:** {level}
**Discrepancy class:** {klass}
**Primary part NSN:** `{primary_nsn}`
**Associated seal kit NSN:** `{seal_nsn}`
**Gasket NSN:** `{gasket_nsn}`
**Torque spec:** {torque_header}
**Lubricant / fluid:** {fluid}
**PMCS interval:** {pmcs}

### Failure indication
{failure.capitalize()}.

### Procedure
1. Park on level ground; set parking brake; chock wheels per OPER manual.
2. Disconnect NATO slave cable; lock-out / tag-out.
3. Reference {fig} for orientation.
4. Remove {comp}; inspect bore, mating face, and adjacent harness for collateral damage.
5. Install replacement P/N `{primary_nsn}`. Replace gasket `{gasket_nsn}` — single-use item.
6. Torque to spec ({torque_header}). Final torque after a 5-minute settle.
7. Refill / top off with {fluid}. Bleed / purge per the section's bleed procedure.
8. Operational check: 10 minutes idle + road test per PMCS Table 2-1 sequence 14a.

### Verification
- No visible leak at 1.5x operating pressure for 60 seconds.
- Connector resistance < 0.1 ohm to chassis ground (where applicable).
- Record PM action in GCSS-MC EM record under PMCS interval **{pmcs}**.

> _alt-text figure description_: {fig}
"""

    keywords = [
        comp.lower(),
        vehicle.split(" ")[0].lower(),
        sec.split("—")[-1].strip().lower(),
        "torque", "leak", "seal", "gasket", "nsn",
    ]

    return {
        "id": f"snip-{idx:02d}",
        "tm": tm,
        "vehicle": vehicle,
        "section": sec,
        "component": comp,
        "primary_nsn": primary_nsn,
        "gasket_nsn": gasket_nsn,
        "seal_nsn": seal_nsn,
        "echelon": level,
        "class": klass,
        "fluid": fluid,
        "failure": failure,
        "figure": fig,
        "pmcs_interval": pmcs,
        "keywords": keywords,
        "text": body.strip(),
    }


def write_snippets(out: Path, n: int | None = None) -> list[dict]:
    """Iterate the curated TM_TEMPLATES dict (does NOT randomly pair anything).

    `n` truncates if provided; default writes every curated template.
    """
    rng = random.Random(SEED)
    flat = _flatten_templates()
    if n is not None:
        flat = flat[:n]
    snippets = [make_snippet(rng, i + 1, v, t, tmpl) for i, (v, t, tmpl) in enumerate(flat)]
    out.write_text(json.dumps(snippets, indent=2))
    return snippets


# ---------------------------------------------------------------------------
# Sample images — fetch from Ultralytics COCO8 (8 license: AGPL-3.0, public)
# ---------------------------------------------------------------------------

# Real COCO8 dataset (Ultralytics, AGPL-3.0, public). The dataset names itself
# "COCO8" — 8 images split 4 train / 4 val. We pull the zip from the Ultralytics
# CDN once and copy the JPGs into sample_images/.
COCO8_ZIP_URL = "https://ultralytics.com/assets/coco8.zip"


def _fetch(url: str, dest: Path, timeout: int = 30) -> bool:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 OPTIK-demo"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            dest.write_bytes(r.read())
        return True
    except Exception as e:  # noqa: BLE001
        print(f"  ! fetch failed for {url}: {e}")
        return False


def _fetch_coco8(samples_dir: Path) -> int:
    """Download + extract COCO8 zip; copy 5 images into samples_dir."""
    import tempfile, zipfile
    if any(samples_dir.glob("0000*.jpg")):
        return len(list(samples_dir.glob("0000*.jpg")))
    with tempfile.TemporaryDirectory() as td:
        zpath = Path(td) / "coco8.zip"
        if not _fetch(COCO8_ZIP_URL, zpath):
            return 0
        with zipfile.ZipFile(zpath) as zf:
            zf.extractall(td)
        copied = 0
        for sub in ("coco8/images/train", "coco8/images/val"):
            for jpg in sorted((Path(td) / sub).glob("*.jpg")):
                dst = samples_dir / jpg.name
                dst.write_bytes(jpg.read_bytes())
                copied += 1
                if copied >= 5:
                    return copied
        return copied


def _make_placeholder(dest: Path, label: str) -> None:
    """Make a Pillow placeholder: dark image with text. Always works offline."""
    from PIL import Image, ImageDraw, ImageFont
    img = Image.new("RGB", (640, 480), (12, 12, 12))
    d = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 22)
    except Exception:
        font = ImageFont.load_default()
    d.rectangle((20, 20, 620, 460), outline=(0, 187, 122), width=2)
    d.text((40, 40),  "OPTIK SAMPLE", fill=(0, 255, 167), font=font)
    d.text((40, 90),  label, fill=(255, 255, 255), font=font)
    d.text((40, 420), "(synthetic placeholder — drag a real image to test)",
           fill=(120, 120, 120), font=font)
    img.save(dest, "JPEG", quality=88)


def write_sample_images() -> list[Path]:
    SAMPLES_DIR.mkdir(parents=True, exist_ok=True)
    n = _fetch_coco8(SAMPLES_DIR)
    print(f"  COCO8 images present: {n}")
    # Always include a known-safe synthetic placeholder so the demo never empties.
    pl = SAMPLES_DIR / "placeholder_valve.jpg"
    if not pl.exists():
        _make_placeholder(pl, "CTIS valve (training image)")
    return sorted(SAMPLES_DIR.glob("*.jpg"))


# ---------------------------------------------------------------------------
# Optional: pre-build embedding index
# ---------------------------------------------------------------------------

def build_index(snippets: list[dict]) -> None:
    try:
        import numpy as np
        from shared.kamiwaza_client import embed
    except Exception as e:  # noqa: BLE001
        print(f"  ! embed step skipped: {e}")
        return
    texts = [f"{s['tm']} {s['component']} {s['failure']} {s['vehicle']}" for s in snippets]
    print(f"  embedding {len(texts)} snippets...")
    vecs = np.array(embed(texts), dtype="float32")
    np.savez_compressed(DATA_DIR / "tm_index.npz", vecs=vecs,
                        ids=np.array([s["id"] for s in snippets]))
    print(f"  wrote {DATA_DIR / 'tm_index.npz'}  shape={vecs.shape}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--embed", action="store_true", help="also build embedding index (needs API key)")
    ap.add_argument("--n-snippets", type=int, default=None,
                    help="truncate to N snippets (default: write every curated template)")
    args = ap.parse_args()

    print("OPTIK data generator")
    print(f"  data dir:    {DATA_DIR}")
    print(f"  samples dir: {SAMPLES_DIR}")

    print("[1/3] writing TM snippets (from curated TM_TEMPLATES)...")
    snippets = write_snippets(DATA_DIR / "tm_snippets.json", n=args.n_snippets)
    print(f"  wrote {len(snippets)} snippets -> data/tm_snippets.json")

    print("[2/3] fetching/synthesizing sample images...")
    imgs = write_sample_images()
    for p in imgs:
        print(f"  {p}")

    if args.embed:
        print("[3/3] building embedding index...")
        build_index(snippets)
    else:
        print("[3/3] skipped (re-run with --embed to build index, or app builds at startup)")

    print("done.")


if __name__ == "__main__":
    main()
