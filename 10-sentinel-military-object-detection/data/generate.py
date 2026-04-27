"""SENTINEL synthetic reference library + sample tile generator.

Produces:
  - reference_library.csv : 30 known platforms (asset_class, country, type, distinguishing_features)
                            schema-compatible with the real Military Object Detection Dataset.
                            The vision-language model in src/app.py is grounded against this CSV
                            on every PID call — swap the rows for your own asset taxonomy and
                            the system prompt picks up the new library on the next launch.
  - sample_manifest.json  : 8 demo images with stable ground-truth + Wikimedia source URLs
  - sample_images/*.png   : 8 procedurally-rendered stand-in tiles (silhouettes + labels) so
                            the demo runs offline without bundling copyrighted imagery.

Real-imagery swap (Bucket B): drop your own JPG/PNG frames into ../data/imagery/ — the Gradio
UI accepts any image input and the PID pipeline runs unchanged. To use the real Military Object
Detection Dataset (~4 GB), replace the rows in REFERENCE_LIBRARY below with your label hierarchy
and re-run this script; sample_images/ is regenerated each time.

Seed: random.Random(1776).
"""
from __future__ import annotations

import json
import random
from pathlib import Path

import csv
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent
SAMPLES_DIR = ROOT.parent / "sample_images"
SAMPLES_DIR.mkdir(parents=True, exist_ok=True)

RNG = random.Random(1776)


# 30 platforms across armor / rotary / fixed-wing / UAS / naval -----------------
REFERENCE_LIBRARY: list[dict] = [
    # --- Armor (10) ---
    {"asset_class": "M1A2 Abrams", "country_of_origin": "United States", "type": "MBT",
     "distinguishing_features": "Flat angular turret; 120mm M256 smoothbore; CITV optic; M1A2 Trophy APS RWS; seven road wheels per side; gas-turbine exhaust grille on rear deck."},
    {"asset_class": "M2A3 Bradley", "country_of_origin": "United States", "type": "IFV",
     "distinguishing_features": "Twin TOW launcher box on right of turret; 25mm M242 Bushmaster; six road wheels; BUSK-III ERA tiles."},
    {"asset_class": "T-72B3", "country_of_origin": "Russian Federation", "type": "MBT",
     "distinguishing_features": "Round low-profile turret; 125mm 2A46 with bore evacuator mid-barrel; six road wheels per side, no return rollers; Kontakt-5 ERA arrow pattern on glacis."},
    {"asset_class": "T-90M Proryv", "country_of_origin": "Russian Federation", "type": "MBT",
     "distinguishing_features": "Welded turret with Relikt ERA wedges; Sosna-U gunner sight on left of mantlet; soft-kill APS Shtora EOCM boxes either side of main gun."},
    {"asset_class": "T-14 Armata", "country_of_origin": "Russian Federation", "type": "MBT",
     "distinguishing_features": "Unmanned turret; very low silhouette over crew capsule; Afghanit hard-kill APS launcher tubes around turret base; seven road wheels."},
    {"asset_class": "Type 99A", "country_of_origin": "China (PRC)", "type": "MBT",
     "distinguishing_features": "Wedge-shaped turret with composite armor blocks; large laser-dazzler box on turret roof; six road wheels; 125mm smoothbore."},
    {"asset_class": "Leopard 2A7", "country_of_origin": "Germany", "type": "MBT",
     "distinguishing_features": "Boxy angular turret with vertical front face; Rh-120 L/55; seven road wheels; thermal sight box top-right of mantlet."},
    {"asset_class": "Challenger 3", "country_of_origin": "United Kingdom", "type": "MBT",
     "distinguishing_features": "New unmanned-style turret (vs Challenger 2 cast turret); L55A1 smoothbore; Trophy APS panels; seven road wheels."},
    {"asset_class": "BMP-3", "country_of_origin": "Russian Federation", "type": "IFV",
     "distinguishing_features": "100mm 2A70 + coaxial 30mm 2A72 main armament combo; rear engine layout with troop hatches over rear deck."},
    {"asset_class": "ZTQ-15 Type 15", "country_of_origin": "China (PRC)", "type": "Light Tank",
     "distinguishing_features": "Light tank profile; 105mm rifled gun; commander RWS; six small road wheels; intended for plateau / amphibious ops."},

    # --- Rotary (5) ---
    {"asset_class": "AH-64E Apache Guardian", "country_of_origin": "United States", "type": "Attack Helicopter",
     "distinguishing_features": "Tandem cockpit; chin-mounted M230 30mm; nose Longbow millimeter-wave radar dome above main rotor; four-blade main rotor; stub wings with Hellfire rails."},
    {"asset_class": "UH-60M Black Hawk", "country_of_origin": "United States", "type": "Utility Helicopter",
     "distinguishing_features": "Four-blade main rotor; canted tail rotor; large side cabin doors; ESSS stub wings optional."},
    {"asset_class": "Mi-28N Havoc", "country_of_origin": "Russian Federation", "type": "Attack Helicopter",
     "distinguishing_features": "Tandem cockpit; chin 30mm 2A42; mast-mounted radar (Mi-28NM); five-blade main rotor; stub wings with Ataka/Vikhr."},
    {"asset_class": "Ka-52 Alligator", "country_of_origin": "Russian Federation", "type": "Attack Helicopter",
     "distinguishing_features": "Coaxial counter-rotating main rotors (no tail rotor); side-by-side cockpit; ejection seats; chin 2A42 30mm offset to right."},
    {"asset_class": "Z-10 Wuzhi", "country_of_origin": "China (PRC)", "type": "Attack Helicopter",
     "distinguishing_features": "Tandem narrow cockpit; chin 23mm cannon; five-blade main rotor; stub wings with HJ-10 ATGMs; canted exhaust IR suppressors."},

    # --- Fixed wing (5) ---
    {"asset_class": "F-35A Lightning II", "country_of_origin": "United States", "type": "5th-gen Fighter",
     "distinguishing_features": "Single engine; chined nose with EOTS sensor under nose; canted twin tails; internal weapons bays; DAS apertures around airframe."},
    {"asset_class": "F-22 Raptor", "country_of_origin": "United States", "type": "5th-gen Fighter",
     "distinguishing_features": "Twin engines with 2D thrust-vector nozzles; diamond planform wing; canted twin tails; chined nose; large internal bays."},
    {"asset_class": "Su-57 Felon", "country_of_origin": "Russian Federation", "type": "5th-gen Fighter",
     "distinguishing_features": "Twin widely-spaced engines; LEVCONs forward of wing root; all-moving canted twin tails; long tailcone between engines."},
    {"asset_class": "J-20 Mighty Dragon", "country_of_origin": "China (PRC)", "type": "5th-gen Fighter",
     "distinguishing_features": "Canard-delta layout; twin canted tails + ventral fins; chined nose; long fuselage; internal weapons bays."},
    {"asset_class": "Su-34 Fullback", "country_of_origin": "Russian Federation", "type": "Strike Fighter",
     "distinguishing_features": "Side-by-side cockpit ('platypus' nose); twin engines; tandem main gear; large dorsal spine; rear-warning radar tailcone."},

    # --- UAS (7) - the headline 'identify the drone' category ---
    {"asset_class": "MQ-9 Reaper", "country_of_origin": "United States", "type": "MALE UCAV",
     "distinguishing_features": "Long slender fuselage; V-tail with ventral fin; pusher prop; SATCOM bulge above nose; Hellfire/GBU-12 hardpoints under wings; ~20m wingspan."},
    {"asset_class": "MQ-1C Gray Eagle", "country_of_origin": "United States", "type": "MALE UAS",
     "distinguishing_features": "Inverted-V tail (no ventral fin); pusher prop; SATCOM bulge; smaller than Reaper; wing root larger than RQ-7."},
    {"asset_class": "RQ-4 Global Hawk", "country_of_origin": "United States", "type": "HALE ISR",
     "distinguishing_features": "Whale-like SATCOM bulb nose; very long thin straight wings; V-tail; jet engine atop rear fuselage."},
    {"asset_class": "Bayraktar TB2", "country_of_origin": "Turkey", "type": "MALE UCAV",
     "distinguishing_features": "Inverted-V tail; pusher prop; small EO/IR ball under nose; ~12m wingspan; no SATCOM bulge (line-of-sight only)."},
    {"asset_class": "Bayraktar Akinci", "country_of_origin": "Turkey", "type": "HALE UCAV",
     "distinguishing_features": "Twin turboprop tractor engines on wing; inverted-V tail; SATCOM bulge; ~20m wingspan; six hardpoints."},
    {"asset_class": "Shahed-136 / Geran-2", "country_of_origin": "Iran (Russian re-mfg as Geran-2)", "type": "Loitering munition",
     "distinguishing_features": "Delta wing with vertical winglets; pusher prop; ~3.5m wingspan; warhead in nose; launched from rail/canister; triangular planform."},
    {"asset_class": "Wing Loong II", "country_of_origin": "China (PRC)", "type": "MALE UCAV",
     "distinguishing_features": "Conventional V-tail (not inverted); pusher prop; SATCOM bulge; 6 hardpoints; very similar profile to MQ-9 but smaller and V-tail orientation differs."},

    # --- Naval (3) ---
    {"asset_class": "Type 055 Renhai", "country_of_origin": "China (PRC)", "type": "Cruiser",
     "distinguishing_features": "Integrated mast with panel arrays; 112-cell VLS; ~13,000t; long flush forecastle; flat-faced superstructure."},
    {"asset_class": "Arleigh Burke Flight III", "country_of_origin": "United States", "type": "DDG",
     "distinguishing_features": "SPY-6 panel arrays integrated into superstructure; 96-cell Mk-41 VLS; angular RCS-reduced superstructure; single 5-inch Mk-45 forward."},
    {"asset_class": "Ticonderoga CG", "country_of_origin": "United States", "type": "Cruiser",
     "distinguishing_features": "Twin SPY-1 panels on box-shaped superstructure; 122-cell Mk-41 VLS (split fwd/aft); two 5-inch Mk-45; planned retirement."},
]

assert len(REFERENCE_LIBRARY) == 30, f"expected 30 platforms, got {len(REFERENCE_LIBRARY)}"


# 8 demo samples ----------------------------------------------------------------
# Wikimedia URLs are real, free-use imagery for the platforms named. The local
# stand-in tiles are procedurally generated so the demo runs without bundling
# copyrighted bytes; in production these would be the actual frame.
SAMPLES: list[dict] = [
    {"id": "S001", "asset_class": "T-72B3", "country": "Russian Federation",
     "wikimedia_url": "https://commons.wikimedia.org/wiki/File:T-72B3_-_TankBiathlon2013-15.jpg",
     "tile_color": (60, 70, 50), "silhouette": "tank"},
    {"id": "S002", "asset_class": "M1A2 Abrams", "country": "United States",
     "wikimedia_url": "https://commons.wikimedia.org/wiki/File:M1A2_Abrams_in_motion.jpg",
     "tile_color": (90, 90, 70), "silhouette": "tank"},
    {"id": "S003", "asset_class": "MQ-9 Reaper", "country": "United States",
     "wikimedia_url": "https://commons.wikimedia.org/wiki/File:MQ-9_Reaper_in_flight_(2007).jpg",
     "tile_color": (80, 110, 130), "silhouette": "uas"},
    {"id": "S004", "asset_class": "Bayraktar TB2", "country": "Turkey",
     "wikimedia_url": "https://commons.wikimedia.org/wiki/File:Bayraktar_TB2_Runway.jpg",
     "tile_color": (70, 100, 120), "silhouette": "uas"},
    {"id": "S005", "asset_class": "AH-64E Apache Guardian", "country": "United States",
     "wikimedia_url": "https://commons.wikimedia.org/wiki/File:AH-64_Apache_Helicopter.jpg",
     "tile_color": (50, 60, 50), "silhouette": "rotary"},
    {"id": "S006", "asset_class": "Ka-52 Alligator", "country": "Russian Federation",
     "wikimedia_url": "https://commons.wikimedia.org/wiki/File:Russian_Air_Force_Kamov_Ka-52_Beltyukov.jpg",
     "tile_color": (60, 70, 60), "silhouette": "rotary"},
    {"id": "S007", "asset_class": "Su-57 Felon", "country": "Russian Federation",
     "wikimedia_url": "https://commons.wikimedia.org/wiki/File:Sukhoi_T-50_Beltyukov.jpg",
     "tile_color": (90, 100, 110), "silhouette": "fighter"},
    {"id": "S008", "asset_class": "Shahed-136 / Geran-2", "country": "Iran (Russian re-mfg as Geran-2)",
     "wikimedia_url": "https://commons.wikimedia.org/wiki/File:HESA_Shahed_136.png",
     "tile_color": (70, 75, 80), "silhouette": "loitering"},
]


def render_tile(sample: dict) -> Path:
    """Procedurally render a 768x432 stand-in tile.

    Uses a class-specific silhouette so a vision model has *something* to ground
    on, plus the platform name overlaid as a small ID-card hint (mimics a frame
    captured by a sensor with overlaid metadata, which is realistic for ISR
    workstations like Maven / TopBoss).
    """
    W, H = 768, 432
    img = Image.new("RGB", (W, H), sample["tile_color"])
    draw = ImageDraw.Draw(img)

    # Cloudy noise texture for "atmosphere"
    rng = random.Random(hash(sample["id"]) & 0xFFFFFFFF)
    for _ in range(2400):
        x, y = rng.randrange(W), rng.randrange(H)
        c = rng.randint(-20, 20)
        base = sample["tile_color"]
        draw.point((x, y), fill=(
            max(0, min(255, base[0] + c)),
            max(0, min(255, base[1] + c)),
            max(0, min(255, base[2] + c)),
        ))

    # Silhouette
    cx, cy = W // 2, H // 2 + 30
    fg = (20, 22, 18)
    sil = sample["silhouette"]
    if sil == "tank":
        # Hull
        draw.rectangle([cx - 180, cy - 30, cx + 180, cy + 30], fill=fg)
        # Turret
        draw.rectangle([cx - 90, cy - 60, cx + 90, cy - 30], fill=fg)
        # Gun barrel
        draw.rectangle([cx + 60, cy - 50, cx + 230, cy - 42], fill=fg)
        # Tracks
        for i in range(7):
            xc = cx - 165 + i * 55
            draw.ellipse([xc - 18, cy + 18, xc + 18, cy + 54], fill=(35, 35, 30))
    elif sil == "uas":
        # Long thin wing
        draw.rectangle([cx - 280, cy - 6, cx + 280, cy + 6], fill=fg)
        # Fuselage
        draw.rectangle([cx - 50, cy - 22, cx + 80, cy + 22], fill=fg)
        # Pusher prop tail
        draw.polygon([(cx + 80, cy - 22), (cx + 130, cy - 8), (cx + 130, cy + 8), (cx + 80, cy + 22)], fill=fg)
        # Inverted-V tail
        draw.line([(cx + 105, cy), (cx + 150, cy - 38)], fill=fg, width=6)
        draw.line([(cx + 105, cy), (cx + 150, cy + 38)], fill=fg, width=6)
        # SATCOM bulge for Reaper-class
        if "Reaper" in sample["asset_class"]:
            draw.ellipse([cx - 30, cy - 42, cx + 30, cy - 16], fill=fg)
    elif sil == "rotary":
        # Fuselage
        draw.polygon([(cx - 100, cy + 10), (cx + 150, cy), (cx + 150, cy + 25), (cx - 100, cy + 35)], fill=fg)
        # Tail boom
        draw.rectangle([cx + 150, cy + 8, cx + 290, cy + 18], fill=fg)
        # Tail rotor
        draw.rectangle([cx + 285, cy - 10, cx + 295, cy + 38], fill=fg)
        # Main rotor
        draw.rectangle([cx - 180, cy - 8, cx + 100, cy - 2], fill=(15, 15, 12))
        # Coaxial second rotor for Ka-52
        if "Ka-52" in sample["asset_class"]:
            draw.rectangle([cx - 180, cy - 18, cx + 100, cy - 12], fill=(15, 15, 12))
    elif sil == "fighter":
        # Fuselage
        draw.polygon([(cx - 200, cy), (cx + 200, cy - 10), (cx + 220, cy + 10), (cx - 200, cy + 18)], fill=fg)
        # Delta-ish wing
        draw.polygon([(cx - 80, cy + 8), (cx + 70, cy + 8), (cx + 30, cy + 80), (cx - 50, cy + 80)], fill=fg)
        draw.polygon([(cx - 80, cy + 8), (cx + 70, cy + 8), (cx + 30, cy - 70), (cx - 50, cy - 70)], fill=fg)
        # Twin canted tails
        draw.polygon([(cx + 100, cy - 8), (cx + 160, cy - 50), (cx + 175, cy - 50), (cx + 130, cy)], fill=fg)
        draw.polygon([(cx + 100, cy + 14), (cx + 160, cy + 56), (cx + 175, cy + 56), (cx + 130, cy + 6)], fill=fg)
    elif sil == "loitering":
        # Delta wing with winglets
        draw.polygon([(cx - 160, cy + 60), (cx + 140, cy), (cx - 80, cy - 60)], fill=fg)
        draw.line([(cx + 140, cy), (cx + 130, cy - 26)], fill=fg, width=5)
        draw.line([(cx + 140, cy), (cx + 130, cy + 26)], fill=fg, width=5)
        # Pusher prop
        draw.rectangle([cx + 138, cy - 18, cx + 152, cy + 18], fill=(15, 15, 12))

    # Sensor-feed ID overlay (top-left)
    try:
        font = ImageFont.truetype("/System/Library/Fonts/Menlo.ttc", 14)
    except Exception:
        font = ImageFont.load_default()
    overlay = f"SENSOR FEED  ID: {sample['id']}  CLASS-HINT: {sample['asset_class']}"
    draw.rectangle([0, 0, W, 22], fill=(0, 0, 0))
    draw.text((6, 4), overlay, fill=(0, 255, 167), font=font)

    # Crosshair
    draw.line([(cx - 16, cy), (cx + 16, cy)], fill=(0, 255, 167), width=1)
    draw.line([(cx, cy - 16), (cx, cy + 16)], fill=(0, 255, 167), width=1)

    out = SAMPLES_DIR / f"{sample['id']}_{sample['asset_class'].replace(' ', '_').replace('/', '-')}.png"
    img.save(out, "PNG")
    return out


def main() -> None:
    # 1. reference library CSV
    csv_path = ROOT / "reference_library.csv"
    with csv_path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["asset_class", "country_of_origin", "type", "distinguishing_features"])
        w.writeheader()
        for row in REFERENCE_LIBRARY:
            w.writerow(row)
    print(f"Wrote {csv_path}  ({len(REFERENCE_LIBRARY)} platforms)")

    # 2. sample images + manifest
    manifest = []
    for s in SAMPLES:
        path = render_tile(s)
        manifest.append({
            "id": s["id"],
            "asset_class": s["asset_class"],
            "country": s["country"],
            "wikimedia_url": s["wikimedia_url"],
            "local_path": str(path.relative_to(ROOT.parent)),
        })
    (ROOT / "sample_manifest.json").write_text(json.dumps(manifest, indent=2))
    print(f"Wrote {ROOT / 'sample_manifest.json'} and {len(SAMPLES)} sample tiles in {SAMPLES_DIR}")


if __name__ == "__main__":
    main()
