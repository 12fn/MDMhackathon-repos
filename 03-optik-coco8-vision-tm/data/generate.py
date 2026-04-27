"""OPTIK synthetic data generator.

Produces a runnable demo corpus so the app works out-of-the-box. Everything
written here is replaceable — see "Swap to real data" below.

Outputs:
  data/tm_snippets.json  — 30 fake but realistically-formatted TM snippets
  data/tm_index.npz      — embedding matrix for cosine RAG (with --embed)
  sample_images/*.jpg    — 5 COCO8 demo photos (Ultralytics) + 1 placeholder

Run:
  python data/generate.py
  python data/generate.py --embed   # also build embedding index (needs an
                                    # OpenAI-compat provider — see DEPLOY.md)

Reproducible: seeded with random.Random(1776).

──────────────────────────────────────────────────────────────────────────────
Swap to real data (Bucket B — see ../../DATA_INGESTION.md)
──────────────────────────────────────────────────────────────────────────────
This is one of the five image-input templates in the "Bucket B" tier — the
compute pipeline (vision call, embedding, cosine search, narrator) is data-
agnostic. Swapping the demo data takes ~10 minutes:

  1. Drop maintainer field photos into ./sample_images/ (or data/samples/) —
     any .jpg / .png. The Gradio Examples panel auto-lists them at startup.

  2. Replace data/tm_snippets.json with real TM excerpts. Keep the same field
     schema used by make_snippet() below: id, tm, vehicle, section, component,
     primary_nsn, gasket_nsn, seal_nsn, echelon, class, fluid, failure,
     figure, keywords, text. Only `text` is consumed by the LLM narrator;
     the other fields drive the citation panel + GCSS-MC parts JSON.

  3. Re-run `python data/generate.py --embed` to rebuild the embedding index
     against the new corpus. (The app also rebuilds at startup if the .npz is
     missing — see src/rag.py::TMIndex.load_or_build.)

See ../../DATA_INGESTION.md for the full Bucket B walkthrough.
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
# TM snippet synthesizer
# ---------------------------------------------------------------------------

# Real TM number prefixes (publicly known on USMC supply lists). Snippet text is synthetic.
TM_VEHICLES = [
    ("MTVR (Medium Tactical Vehicle Replacement) MK23/MK25", "TM 11240A-OR/B"),
    ("MTVR Wrecker MK36",                                     "TM 11240A-23&P/3"),
    ("LVSR (Logistics Vehicle System Replacement) MK31",      "TM 11035A-OR/A"),
    ("HMMWV M1151A1",                                         "TM 9-2320-387-23"),
    ("JLTV M1278 Heavy Gun Carrier",                          "TM 9-2320-447-23"),
    ("AAV7A1 Assault Amphibious Vehicle",                     "TM 09674A-23&P"),
    ("ACV Personnel (Amphibious Combat Vehicle)",             "TM 09704A-OR/A"),
    ("MEP-803A 10kW Generator Set",                           "TM 9-6115-642-24"),
    ("M870A3 Semitrailer (40-ton lowbed)",                    "TM 9-2330-381-14&P"),
    ("M1101 1.25-ton Trailer",                                "TM 9-2330-392-14&P"),
]

COMPONENTS = [
    # (component, NSN base, torque ft-lb range, fluid, common failure)
    ("central tire inflation system (CTIS) valve",  "2540-01", (32, 38),  "MIL-PRF-46170 hydraulic fluid", "seal seepage at hose collar"),
    ("kingpin upper bushing",                       "2530-01", (180, 220),"MIL-PRF-2105E 80W-90 GO",       "ovalized bore from missed lube"),
    ("transfer-case input shaft seal",              "2520-01", (45, 55),  "MIL-PRF-2105E 75W-90",          "Class III leak at output flange"),
    ("turbocharger oil supply line",                "2950-01", (18, 22),  "MIL-PRF-2104J 15W-40",          "chafing against bracket — replace clamp P/N 5340-01"),
    ("alternator drive belt (serpentine)",          "3030-01", (None, None),"n/a",                         "glazing + 8% length elongation — replace at 250 hr"),
    ("engine coolant thermostat housing",           "2930-01", (22, 28),  "MIL-A-46153 ELC coolant",       "weep at gasket from over-torque"),
    ("transmission oil cooler line (return)",       "4720-01", (35, 42),  "Dexron VI ATF",                 "vibration fatigue at compression sleeve"),
    ("steering gear sector shaft seal",             "2530-01", (140, 160),"MIL-PRF-46170",                 "Class III leak — bring vehicle to NMC"),
    ("fuel-water separator drain plug",             "2910-01", (8, 10),   "F-24 fuel",                     "stripped threads — install heli-coil P/N 5340-01"),
    ("brake caliper guide pin",                     "2530-01", (32, 38),  "DOT-5 silicone brake fluid",    "frozen pin from corrosion"),
    ("axle differential breather valve",            "2520-01", (12, 15),  "n/a",                           "clogged — water ingress to housing"),
    ("ECM (Engine Control Module) connector J3",    "5998-01", (None, None),"n/a",                         "green-pin corrosion — clean per MIL-DTL-83488"),
    ("rear suspension torque rod end",              "2510-01", (180, 220),"MIL-PRF-10924 grease",          "play exceeds 0.030 in — replace pair"),
    ("hydraulic winch motor",                       "3950-01", (60, 75),  "MIL-PRF-46170",                 "no rotation under load — internal vane wear"),
    ("MEP-803A engine fuel injector",               "2910-01", (35, 40),  "F-24 fuel",                     "spray pattern out of spec — replace as a set of 3"),
    ("AAV bilge pump impeller",                     "4320-01", (None, None),"n/a",                         "fouled impeller — replace and verify Y-valve alignment"),
    ("amphibious seal kit, hatch coaming",          "2540-01", (None, None),"silicone grease MIL-S-8660",  "cracked durometer — annual replacement"),
    ("driver's night vision sight (AN/VAS-5)",      "5855-01", (None, None),"n/a",                         "dim image — boresight per TM"),
    ("intervehicular cable (NATO slave)",           "6150-01", (None, None),"n/a",                         "outer jacket abrasion — replace if conductors visible"),
    ("crewman's helmet ICS cable",                  "5995-01", (None, None),"n/a",                         "intermittent — flex-test connectors"),
]

FIGURES = [
    "Figure 4-7. CTIS valve assembly, exploded view (item 3 is the gasket).",
    "Figure 6-2. Kingpin assembly with upper/lower bushing locations.",
    "Figure 8-14. Transfer-case input/output shaft seal arrangement.",
    "Figure 12-3. Turbocharger lubrication circuit schematic.",
    "Figure 3-1. Serpentine belt routing — 7-rib, MTVR caterpillar engine.",
    "Figure 5-9. Coolant thermostat housing torque sequence (1-3-2-4 cross pattern).",
    "Figure 9-22. Transmission cooler line layout, return side.",
    "Figure 7-4. Steering gear assembly cutaway.",
    "Figure 10-1. Fuel/water separator with manual drain.",
    "Figure 11-8. Brake caliper guide pin removal.",
]

SECTIONS = [
    "Section 4.7.3 — CTIS Maintenance",
    "Section 6.2.1 — Kingpin Inspection",
    "Section 8.14.2 — Transfer Case",
    "Section 12.3.4 — Turbocharger Service",
    "Section 3.1.5 — Drive Belts",
    "Section 5.9.2 — Cooling System",
    "Section 9.22.1 — Transmission Cooling",
    "Section 7.4.6 — Steering Gear",
    "Section 10.1.3 — Fuel System",
    "Section 11.8.2 — Brake Service",
]

INSPECTION_LEVELS = ["Operator (Crew)", "Field Maintainer (3rd echelon)", "Sustainment (5th echelon depot)"]
CLASSES = ["Class I (no action)", "Class II (monitor at next PMCS)", "Class III (corrective action required)"]


def _nsn(rng: random.Random, base: str) -> str:
    """Build a NIIN-correct-shape NSN: NNNN-CC-NNN-NNNN."""
    return f"{base}-{rng.randrange(100, 999)}-{rng.randrange(1000, 9999)}"


def _torque_str(rng: random.Random, lo: int | None, hi: int | None) -> str:
    if lo is None:
        return "_no torque (visual/wear inspection only)_"
    val = rng.randint(lo, hi)
    nm = round(val * 1.3558, 1)
    return f"**{val} ft-lb ({nm} N-m)**"


def make_snippet(rng: random.Random, idx: int) -> dict:
    vehicle, tm = rng.choice(TM_VEHICLES)
    comp, nsn_base, torque, fluid, failure = rng.choice(COMPONENTS)
    fig = rng.choice(FIGURES)
    sec = rng.choice(SECTIONS)
    level = rng.choice(INSPECTION_LEVELS)
    klass = rng.choice(CLASSES)

    primary_nsn = _nsn(rng, nsn_base)
    gasket_nsn  = _nsn(rng, "5330-01")
    seal_nsn    = _nsn(rng, "5330-01")

    body = f"""# {tm} — {vehicle}
## {sec}

**Component:** {comp}
**Echelon:** {level}
**Discrepancy class:** {klass}
**Primary part NSN:** `{primary_nsn}`
**Associated seal kit NSN:** `{seal_nsn}`
**Gasket NSN:** `{gasket_nsn}`
**Torque spec:** {_torque_str(rng, *torque)}
**Lubricant / fluid:** {fluid}

### Failure indication
{failure.capitalize()}.

### Procedure
1. Park on level ground; set parking brake; chock wheels per OPER manual.
2. Disconnect NATO slave cable; lock-out / tag-out.
3. Reference {fig} for orientation.
4. Remove {comp}; inspect bore, mating face, and adjacent harness for collateral damage.
5. Install replacement P/N `{primary_nsn}`. Replace gasket `{gasket_nsn}` — single-use item.
6. Torque to spec ({_torque_str(rng, *torque)}). Final torque after a 5-minute settle.
7. Refill / top off with {fluid}. Bleed system per Section 12.4.
8. Operational check: 10 minutes idle + road test per PMCS Table 2-1 sequence 14a.

### Verification
- No visible leak at 1.5x operating pressure for 60 seconds.
- Connector resistance < 0.1 ohm to chassis ground.
- Record PM action in GCSS-MC EM record under SLEP code {rng.choice(['SLEP-A1','SLEP-B2','SLEP-C3'])}.

> _alt-text figure description_: {fig}
"""

    keywords = [comp.lower(), vehicle.split(" ")[0].lower(), "torque", "leak", "seal", "gasket", "nsn"]

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
        "keywords": keywords,
        "text": body.strip(),
    }


def write_snippets(out: Path, n: int = 30) -> list[dict]:
    rng = random.Random(SEED)
    snippets = [make_snippet(rng, i + 1) for i in range(n)]
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
    ap.add_argument("--n-snippets", type=int, default=30)
    args = ap.parse_args()

    print("OPTIK data generator")
    print(f"  data dir:    {DATA_DIR}")
    print(f"  samples dir: {SAMPLES_DIR}")

    print("[1/3] writing TM snippets...")
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
