"""STRIDER synthetic data generator — GOOSE-style off-road terrain swatches.

Produces:
  data/vehicle_specs.csv  -- ground-clearance / fording / max-grade / tire spec
                             for 6 ground-fleet vehicle classes (LAV-25, JLTV,
                             MTVR, ALPV-1, ATT-EV, UGV mule). Edit this file
                             (or hand-author the CSV) to plug in your own fleet.

  sample_images/*.jpg     -- 6 deterministic procedurally-generated terrain
                             swatches (mud, sand, rock, vegetation, water-
                             crossing, gravel-road) so the demo runs offline.

Real-data swap (Bucket B)
-------------------------
The vision call returns the same structured terrain JSON regardless of source.
To swap in real frames:

  1. Drop GOOSE-style or arbitrary terrain JPG / PNG files into
     `sample_images/` (or `data/terrain/`) — restart the app and they appear
     in the dropdown.
  2. GOOSE itself: https://goose-dataset.de — 50 GB labelled off-road semantic
     segmentation, free academic. Any forward-rover dashcam, ISR capture, or
     phone photo also works.

Reproducible with random.Random(1776).
"""
from __future__ import annotations

import csv
import random
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
IMG = ROOT / "sample_images"
DATA.mkdir(parents=True, exist_ok=True)
IMG.mkdir(parents=True, exist_ok=True)

RNG = random.Random(1776)

# ---------------------------------------------------------------------------
# Vehicle spec table
# ---------------------------------------------------------------------------
# Cleared figures from public manufacturer / TM data + a couple of "future"
# entries (autonomous tow tractor, ALPV) consistent with USMC modernization
# briefings. All synthetic-but-plausible.
VEHICLES = [
    {
        "vehicle_id": "LAV-25",
        "class": "Light Armored Vehicle",
        "weight_kg": 12700,
        "ground_clearance_in": 19.7,
        "fording_depth_in": 60.0,         # amphibious
        "max_grade_pct": 70,
        "max_side_slope_pct": 30,
        "tire_or_track": "8x8 wheeled",
        "powertrain": "diesel",
        "autonomy_level": "manned",
    },
    {
        "vehicle_id": "JLTV",
        "class": "Joint Light Tactical Vehicle (M1278)",
        "weight_kg": 6577,
        "ground_clearance_in": 18.0,
        "fording_depth_in": 60.0,
        "max_grade_pct": 60,
        "max_side_slope_pct": 40,
        "tire_or_track": "4x4 wheeled, run-flat",
        "powertrain": "diesel",
        "autonomy_level": "manned",
    },
    {
        "vehicle_id": "MTVR-MK23",
        "class": "Medium Tactical Vehicle Replacement",
        "weight_kg": 17690,
        "ground_clearance_in": 17.0,
        "fording_depth_in": 60.0,
        "max_grade_pct": 60,
        "max_side_slope_pct": 30,
        "tire_or_track": "6x6 wheeled, CTIS",
        "powertrain": "diesel",
        "autonomy_level": "manned",
    },
    {
        "vehicle_id": "ALPV-1",
        "class": "Autonomous Low-Profile Vehicle (Force Design 2030)",
        "weight_kg": 1100,
        "ground_clearance_in": 11.0,
        "fording_depth_in": 24.0,
        "max_grade_pct": 45,
        "max_side_slope_pct": 25,
        "tire_or_track": "4x4 wheeled, all-terrain",
        "powertrain": "hybrid-electric",
        "autonomy_level": "autonomous (SAE L4)",
    },
    {
        "vehicle_id": "ATT-EV",
        "class": "Autonomous Electric Tow Tractor (MDMC Albany pilot, STEER Tech)",
        "weight_kg": 2400,
        "ground_clearance_in": 6.5,
        "fording_depth_in": 8.0,
        "max_grade_pct": 18,
        "max_side_slope_pct": 12,
        "tire_or_track": "4x4 pneumatic, depot-grade",
        "powertrain": "battery-electric",
        "autonomy_level": "autonomous (SAE L4, geofenced)",
    },
    {
        "vehicle_id": "UGV-MULE",
        "class": "Unmanned Ground Vehicle (squad mule)",
        "weight_kg": 540,
        "ground_clearance_in": 13.0,
        "fording_depth_in": 18.0,
        "max_grade_pct": 50,
        "max_side_slope_pct": 30,
        "tire_or_track": "tracked rubber",
        "powertrain": "hybrid-electric",
        "autonomy_level": "autonomous (SAE L3 follow-me)",
    },
]


def write_vehicles() -> None:
    out = DATA / "vehicle_specs.csv"
    with out.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(VEHICLES[0].keys()))
        w.writeheader()
        for v in VEHICLES:
            w.writerow(v)
    print(f"wrote {out} ({len(VEHICLES)} rows)")


# ---------------------------------------------------------------------------
# Procedural terrain swatches
# ---------------------------------------------------------------------------
W, H = 768, 512


def _noise(base: tuple[int, int, int], jitter: int = 25) -> tuple[int, int, int]:
    return tuple(max(0, min(255, c + RNG.randint(-jitter, jitter))) for c in base)


def _grain(img: Image.Image, n: int, palette: list[tuple[int, int, int]], radius: int = 2) -> None:
    d = ImageDraw.Draw(img)
    for _ in range(n):
        x = RNG.randint(0, W - 1)
        y = RNG.randint(0, H - 1)
        c = _noise(RNG.choice(palette), 18)
        r = RNG.randint(1, radius)
        d.ellipse((x - r, y - r, x + r, y + r), fill=c)


def _label(img: Image.Image, text: str) -> None:
    d = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 22)
    except Exception:
        font = ImageFont.load_default()
    pad = 12
    bbox = d.textbbox((0, 0), text, font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    d.rectangle((pad - 6, pad - 6, pad + tw + 10, pad + th + 10), fill=(0, 0, 0, 200))
    d.text((pad, pad), text, fill=(0, 255, 167), font=font)


def make_mud() -> Image.Image:
    img = Image.new("RGB", (W, H), (60, 42, 28))
    _grain(img, 12000, [(70, 48, 30), (45, 30, 18), (90, 65, 40), (30, 20, 12)], radius=3)
    img = img.filter(ImageFilter.GaussianBlur(1.2))
    # specular wet patches
    d = ImageDraw.Draw(img, "RGBA")
    for _ in range(40):
        x, y = RNG.randint(0, W), RNG.randint(0, H)
        r = RNG.randint(20, 60)
        d.ellipse((x, y, x + r, y + r * 0.4), fill=(120, 90, 70, 90))
    _label(img, "MUD / WET CLAY")
    return img


def make_sand() -> Image.Image:
    img = Image.new("RGB", (W, H), (210, 180, 130))
    _grain(img, 18000, [(220, 190, 140), (200, 165, 115), (235, 205, 155), (190, 155, 105)], radius=2)
    img = img.filter(ImageFilter.GaussianBlur(0.8))
    # dune ripples
    d = ImageDraw.Draw(img, "RGBA")
    for i in range(0, H, 14):
        d.line([(0, i + RNG.randint(-3, 3)), (W, i + RNG.randint(-3, 3))], fill=(180, 145, 95, 60), width=1)
    _label(img, "SOFT SAND / DUNE")
    return img


def make_rock() -> Image.Image:
    img = Image.new("RGB", (W, H), (110, 105, 100))
    _grain(img, 9000, [(120, 115, 110), (90, 85, 80), (150, 145, 140), (70, 65, 60)], radius=4)
    d = ImageDraw.Draw(img)
    # angular rocks
    for _ in range(45):
        cx, cy = RNG.randint(0, W), RNG.randint(0, H)
        pts = [(cx + RNG.randint(-40, 40), cy + RNG.randint(-30, 30)) for _ in range(6)]
        d.polygon(pts, fill=_noise((100, 95, 90), 30), outline=(50, 50, 50))
    img = img.filter(ImageFilter.GaussianBlur(0.5))
    _label(img, "BROKEN ROCK / SCREE")
    return img


def make_vegetation() -> Image.Image:
    img = Image.new("RGB", (W, H), (50, 80, 40))
    _grain(img, 14000, [(60, 100, 45), (40, 70, 30), (80, 120, 55), (30, 55, 20)], radius=3)
    d = ImageDraw.Draw(img)
    # grass blades
    for _ in range(800):
        x = RNG.randint(0, W)
        y = RNG.randint(H // 3, H)
        h = RNG.randint(8, 26)
        d.line([(x, y), (x + RNG.randint(-3, 3), y - h)], fill=_noise((90, 130, 60), 25), width=1)
    img = img.filter(ImageFilter.GaussianBlur(0.6))
    _label(img, "DENSE VEGETATION")
    return img


def make_water() -> Image.Image:
    img = Image.new("RGB", (W, H), (60, 90, 110))
    # bank
    d = ImageDraw.Draw(img)
    d.rectangle((0, 0, W, int(H * 0.3)), fill=(95, 80, 55))
    _grain(img, 4000, [(110, 95, 70), (75, 60, 40)], radius=3)
    # water
    d.rectangle((0, int(H * 0.3), W, H), fill=(55, 95, 120))
    for _ in range(500):
        x, y = RNG.randint(0, W), RNG.randint(int(H * 0.3), H)
        d.line([(x, y), (x + RNG.randint(8, 30), y + RNG.randint(-1, 1))], fill=(90, 130, 160), width=1)
    img = img.filter(ImageFilter.GaussianBlur(0.8))
    _label(img, "WATER CROSSING (~30 IN EST)")
    return img


def make_gravel_road() -> Image.Image:
    img = Image.new("RGB", (W, H), (130, 125, 115))
    _grain(img, 16000, [(140, 135, 125), (110, 105, 95), (160, 155, 145)], radius=2)
    # tire ruts
    d = ImageDraw.Draw(img, "RGBA")
    for ox in (W // 3, 2 * W // 3):
        d.ellipse((ox - 60, H // 2 - 10, ox + 60, H), fill=(80, 75, 65, 120))
    img = img.filter(ImageFilter.GaussianBlur(0.5))
    _label(img, "GRAVEL TRACK")
    return img


def write_images() -> None:
    factories = {
        "01_mud.jpg": make_mud,
        "02_soft_sand.jpg": make_sand,
        "03_broken_rock.jpg": make_rock,
        "04_dense_vegetation.jpg": make_vegetation,
        "05_water_crossing.jpg": make_water,
        "06_gravel_track.jpg": make_gravel_road,
    }
    for name, fn in factories.items():
        path = IMG / name
        fn().save(path, "JPEG", quality=88)
        print(f"wrote {path}")


def main() -> None:
    write_vehicles()
    write_images()


if __name__ == "__main__":
    main()
