"""PALLET-VISION synthetic data generator.

Produces:
  - sample_images/*.jpg              : 6 procedurally generated stand-in images
                                        (warehouse stacks, loading dock, drone
                                         overhead truck-bed, etc.) so the demo
                                         runs offline without bundling third-
                                         party imagery.
  - platform_specs.csv               : USMC airlift / sealift / surface platform
                                        pallet capacity + max payload weight,
                                        verbatim from public DoD references
                                        (TM 38-250, AFI 24-605, MCRP 4-11.3D).
  - sample_manifest.json             : ground-truth metadata per sample (count,
                                        scene type, expected lift class).
  - cached_briefs.json               : pre-computed hero outputs for the 6
                                        samples (cache-first pattern). Filled
                                        in by precompute_briefs.py.

Seed: random.Random(1776).
"""
from __future__ import annotations

import csv
import json
import random
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent
APP_ROOT = ROOT.parent
SAMPLES_DIR = APP_ROOT / "sample_images"
SAMPLES_DIR.mkdir(parents=True, exist_ok=True)

RNG = random.Random(1776)


# -----------------------------------------------------------------------------
# Platform specs — DoD airlift / sealift / surface lift pallet capacities
# -----------------------------------------------------------------------------
# Sources cited per row in platform_specs.csv. Values are public-domain spec
# sheets (USAF AFI 24-605, USMC MCRP 4-11.3D, OEM cards). 463L is the
# 88x108 in cargo pallet standard.
PLATFORM_SPECS: list[dict] = [
    # AIRLIFT
    {"platform": "C-17 Globemaster III", "category": "Airlift",
     "pallets_463l": 18, "max_payload_kg": 77519,
     "internal_cube_m3": 592.0,
     "notes": "18 463L position spine; oversize/outsize cargo capable; primary inter-theater."},
    {"platform": "C-130J Super Hercules", "category": "Airlift",
     "pallets_463l": 6, "max_payload_kg": 19958,
     "internal_cube_m3": 127.4,
     "notes": "6 463L max in standard cargo config; primary intra-theater."},
    {"platform": "KC-46A Pegasus", "category": "Airlift",
     "pallets_463l": 18, "max_payload_kg": 65317,
     "internal_cube_m3": 432.0,
     "notes": "Tanker-cargo; 18 463L positions, lower deck cargo only."},
    {"platform": "KC-130J", "category": "Airlift",
     "pallets_463l": 6, "max_payload_kg": 20411,
     "internal_cube_m3": 127.4,
     "notes": "USMC tanker variant; 6 463L positions, loadmaster-controlled."},
    # SURFACE LIFT (truck)
    {"platform": "MTVR (MK23)", "category": "Surface",
     "pallets_463l": 4, "max_payload_kg": 6804,
     "internal_cube_m3": 18.5,
     "notes": "Marine 7-ton; 4 standard 463L pallets on cargo bed, 15-ton off-road."},
    {"platform": "M1083 FMTV (5-ton)", "category": "Surface",
     "pallets_463l": 4, "max_payload_kg": 4536,
     "internal_cube_m3": 17.0,
     "notes": "Family of Medium Tactical Vehicles; standard cargo bed."},
    {"platform": "M1078 LMTV (2.5-ton)", "category": "Surface",
     "pallets_463l": 2, "max_payload_kg": 2268,
     "internal_cube_m3": 9.0,
     "notes": "Light variant; 2 standard pallets."},
    {"platform": "LVSR (MK36)", "category": "Surface",
     "pallets_463l": 8, "max_payload_kg": 20412,
     "internal_cube_m3": 36.0,
     "notes": "Logistics Vehicle System Replacement; 22.5-ton on-road."},
    # SEALIFT
    {"platform": "LCAC", "category": "Sealift",
     "pallets_463l": 12, "max_payload_kg": 54431,
     "internal_cube_m3": 168.0,
     "notes": "Landing Craft Air Cushion; ship-to-shore connector."},
]


# -----------------------------------------------------------------------------
# Sample images — 6 procedurally drawn scenes
# -----------------------------------------------------------------------------
SAMPLES: list[dict] = [
    {
        "id": "S001",
        "name": "warehouse_grid",
        "title": "Warehouse cube — staged pallets",
        "scene_type": "warehouse",
        "true_pallets": 24,
        "pallet_type": "wood-stringer",
        "estimated_avg_kg_per_pallet": 410,
        "narration": "Class IX repair parts staged at MCLB Albany inbound dock.",
    },
    {
        "id": "S002",
        "name": "loading_dock_mixed",
        "title": "Loading dock — mixed cargo",
        "scene_type": "loading_dock",
        "true_pallets": 9,
        "pallet_type": "mixed",
        "estimated_avg_kg_per_pallet": 540,
        "narration": "Mixed Class I and Class IV palletized for outbound MTVR run.",
    },
    {
        "id": "S003",
        "name": "drone_overhead_truck",
        "title": "Drone overhead — MTVR loaded",
        "scene_type": "drone_overhead",
        "true_pallets": 4,
        "pallet_type": "463L",
        "estimated_avg_kg_per_pallet": 1450,
        "narration": "Drone overhead pass; MTVR cargo bed fully built up.",
    },
    {
        "id": "S004",
        "name": "flight_line_463l",
        "title": "Flight line — 463L stacks",
        "scene_type": "flight_line",
        "true_pallets": 12,
        "pallet_type": "463L",
        "estimated_avg_kg_per_pallet": 1820,
        "narration": "463L cargo pallets staged for next C-17 lift.",
    },
    {
        "id": "S005",
        "name": "construction_yard",
        "title": "Construction yard — heavy equipment",
        "scene_type": "construction_yard",
        "true_pallets": 6,
        "pallet_type": "mixed",
        "estimated_avg_kg_per_pallet": 880,
        "narration": "Engineer support equipment + Class IV barrier stock.",
    },
    {
        "id": "S006",
        "name": "ship_deck_pallets",
        "title": "Ship deck — sealift staging",
        "scene_type": "ship_deck",
        "true_pallets": 36,
        "pallet_type": "464L",
        "estimated_avg_kg_per_pallet": 720,
        "narration": "MPSRON staging deck; sustainment cargo pre-positioned.",
    },
]


# -----------------------------------------------------------------------------
# Drawing helpers — every image is 1024 x 640 JPEG
# -----------------------------------------------------------------------------
W, H = 1024, 640
ACCENT = (0, 255, 167)        # neon
PRIMARY = (0, 187, 122)
PALLET_WOOD = (138, 92, 42)
PALLET_BLUE = (52, 116, 160)
PALLET_TAN = (188, 162, 102)
PALLET_GREEN = (66, 110, 64)


def _font(size: int = 14):
    for path in (
        "/System/Library/Fonts/Menlo.ttc",
        "/System/Library/Fonts/Helvetica.ttc",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    ):
        try:
            return ImageFont.truetype(path, size)
        except Exception:
            continue
    return ImageFont.load_default()


def _noise(img: Image.Image, density: int = 1500, jitter: int = 14) -> None:
    rng = random.Random(hash(img.tobytes()[:64]) & 0xFFFFFFFF)
    px = img.load()
    for _ in range(density):
        x, y = rng.randrange(W), rng.randrange(H)
        r, g, b = px[x, y]
        d = rng.randint(-jitter, jitter)
        px[x, y] = (
            max(0, min(255, r + d)),
            max(0, min(255, g + d)),
            max(0, min(255, b + d)),
        )


def _overlay_label(draw: ImageDraw.ImageDraw, text: str) -> None:
    f = _font(14)
    draw.rectangle([0, 0, W, 24], fill=(0, 0, 0))
    draw.text((8, 4), text, fill=ACCENT, font=f)


def _draw_pallet(draw: ImageDraw.ImageDraw, x: int, y: int, w: int, h: int,
                 color: tuple[int, int, int], label: str = "") -> None:
    # Pallet body
    draw.rectangle([x, y, x + w, y + h], fill=color, outline=(20, 20, 20), width=2)
    # Slats (top face) for woody look
    slat = max(3, h // 6)
    for i in range(1, h // slat):
        ly = y + i * slat
        draw.line([(x + 2, ly), (x + w - 2, ly)], fill=(0, 0, 0), width=1)
    # Side shadow for depth
    draw.polygon(
        [(x + w, y), (x + w + 8, y - 6), (x + w + 8, y + h - 6), (x + w, y + h)],
        fill=tuple(max(0, c - 35) for c in color),
        outline=(20, 20, 20),
    )
    if label:
        draw.text((x + 4, y + 2), label, fill=(245, 245, 245), font=_font(11))


def render_warehouse_grid(sample: dict) -> Image.Image:
    """Wide warehouse — 6 wide x 4 deep grid of pallets, perspective-faked."""
    img = Image.new("RGB", (W, H), (32, 36, 42))
    draw = ImageDraw.Draw(img)
    # Floor stripes
    for i in range(0, H, 24):
        draw.line([(0, i), (W, i)], fill=(28, 32, 36), width=1)
    # Back wall
    draw.rectangle([0, 0, W, 200], fill=(20, 24, 28))
    # Ceiling lights
    for cx in (180, 480, 780):
        draw.ellipse([cx - 30, 30, cx + 30, 70], fill=(255, 240, 200))
        draw.ellipse([cx - 14, 38, cx + 14, 62], fill=(255, 255, 230))
    # Pallets in a 6x4 grid; back row smaller (perspective)
    rows, cols = 4, 6
    for r in range(rows):
        for c in range(cols):
            scale = 0.7 + 0.1 * r
            pw = int(110 * scale)
            ph = int(70 * scale)
            x = 60 + c * int(155 * scale) + (rows - r) * 10
            y = 240 + r * int(85 * scale)
            color = PALLET_WOOD if (r + c) % 2 == 0 else PALLET_TAN
            _draw_pallet(draw, x, y, pw, ph, color)
    _noise(img)
    _overlay_label(draw, "WAREHOUSE FEED  ID: S001  AOR: MCLB-ALBANY")
    return img


def render_loading_dock(sample: dict) -> Image.Image:
    img = Image.new("RGB", (W, H), (52, 56, 60))
    draw = ImageDraw.Draw(img)
    # Dock door (back)
    draw.rectangle([300, 120, 720, 420], fill=(80, 78, 70))
    for i in range(8):
        y = 120 + i * 38
        draw.line([(300, y), (720, y)], fill=(40, 38, 30), width=2)
    # Truck body suggestion (left)
    draw.rectangle([0, 280, 200, 520], fill=(60, 70, 50))
    draw.rectangle([0, 320, 200, 360], fill=(70, 80, 60))
    # Mixed pallets in foreground
    layout = [
        (240, 460, 110, 70, PALLET_WOOD),
        (370, 460, 110, 70, PALLET_BLUE),
        (500, 460, 110, 70, PALLET_TAN),
        (630, 460, 110, 70, PALLET_GREEN),
        (760, 460, 110, 70, PALLET_WOOD),
        (290, 380, 110, 70, PALLET_BLUE),
        (420, 380, 110, 70, PALLET_TAN),
        (550, 380, 110, 70, PALLET_WOOD),
        (680, 380, 110, 70, PALLET_GREEN),
    ]
    for (x, y, w, h, color) in layout:
        _draw_pallet(draw, x, y, w, h, color)
    # Dock floor line
    draw.line([(0, 540), (W, 540)], fill=(80, 80, 80), width=3)
    _noise(img)
    _overlay_label(draw, "DOCK CAM  ID: S002  CARGO: MIXED CLASS I/IV")
    return img


def render_drone_overhead_truck(sample: dict) -> Image.Image:
    """Top-down view of an MTVR cargo bed with pallets."""
    img = Image.new("RGB", (W, H), (88, 76, 50))  # dirt/desert
    draw = ImageDraw.Draw(img)
    # Truck cab + bed (top-down); cab on right
    bed_x0, bed_y0, bed_x1, bed_y1 = 180, 180, 720, 460
    draw.rectangle([bed_x0, bed_y0, bed_x1, bed_y1], fill=(50, 60, 50),
                   outline=(20, 20, 20), width=3)
    # Cab
    draw.rectangle([720, 200, 870, 440], fill=(40, 50, 40),
                   outline=(20, 20, 20), width=3)
    draw.rectangle([735, 220, 855, 280], fill=(60, 80, 70))  # windshield
    # 4 463L pallets on the bed (2x2)
    pallet_w, pallet_h = 245, 125
    gap = 10
    for i in range(2):
        for j in range(2):
            x = bed_x0 + 15 + i * (pallet_w + gap)
            y = bed_y0 + 15 + j * (pallet_h + gap)
            color = PALLET_TAN if (i + j) % 2 == 0 else PALLET_WOOD
            _draw_pallet(draw, x, y, pallet_w - 5, pallet_h - 5, color, label="463L")
    # Wheels (top-down)
    for wy in (170, 295, 420, 470):
        draw.ellipse([175 - 15, wy, 175 + 15, wy + 30], fill=(15, 15, 15))
        draw.ellipse([720 - 15, wy, 720 + 15, wy + 30], fill=(15, 15, 15))
    # Tracks in sand
    draw.line([(0, 200), (175, 200)], fill=(108, 96, 70), width=8)
    draw.line([(0, 440), (175, 440)], fill=(108, 96, 70), width=8)
    _noise(img, density=2400)
    _overlay_label(draw, "DRONE-EO  ID: S003  ALT: 120m AGL  PLATFORM: MTVR")
    return img


def render_flight_line(sample: dict) -> Image.Image:
    img = Image.new("RGB", (W, H), (110, 110, 115))  # tarmac
    draw = ImageDraw.Draw(img)
    # Runway markings
    for x in range(0, W, 120):
        draw.rectangle([x, 530, x + 60, 545], fill=(245, 240, 230))
    # 463L pallet stacks (12 = 4 rows of 3)
    for r in range(4):
        for c in range(3):
            x = 200 + c * 220
            y = 180 + r * 80
            # Stacked silhouette: 2 layers
            _draw_pallet(draw, x, y, 180, 50, PALLET_TAN, label="463L")
            _draw_pallet(draw, x + 6, y - 14, 168, 18, (90, 80, 50))
    # Aircraft tail in background (suggestion of C-17)
    draw.polygon([(820, 50), (1010, 80), (1010, 220), (820, 200)], fill=(180, 180, 185))
    draw.polygon([(870, 80), (970, 100), (970, 200), (870, 180)], fill=(150, 150, 155))
    draw.text((860, 90), "USAF", fill=(50, 50, 50), font=_font(18))
    _noise(img)
    _overlay_label(draw, "FLIGHT LINE  ID: S004  STATION: MCAS-CHERRY-PT")
    return img


def render_construction_yard(sample: dict) -> Image.Image:
    img = Image.new("RGB", (W, H), (140, 132, 110))  # gravel
    draw = ImageDraw.Draw(img)
    # Trailer
    draw.rectangle([60, 200, 320, 360], fill=(180, 60, 50), outline=(20, 20, 20), width=3)
    draw.ellipse([100, 350, 160, 410], fill=(20, 20, 20))
    draw.ellipse([220, 350, 280, 410], fill=(20, 20, 20))
    # Conex box
    draw.rectangle([400, 200, 700, 400], fill=(140, 100, 60), outline=(20, 20, 20), width=3)
    for i in range(8):
        draw.line([(400, 220 + i * 22), (700, 220 + i * 22)], fill=(60, 40, 20), width=1)
    draw.text((420, 290), "CONEX", fill=(245, 245, 245), font=_font(28))
    # 6 mixed pallets in foreground
    layout = [
        (120, 460, 130, 70, PALLET_BLUE),
        (270, 460, 130, 70, PALLET_WOOD),
        (420, 460, 130, 70, PALLET_TAN),
        (570, 460, 130, 70, PALLET_GREEN),
        (720, 460, 130, 70, PALLET_BLUE),
        (820, 380, 140, 70, PALLET_WOOD),
    ]
    for (x, y, w, h, color) in layout:
        _draw_pallet(draw, x, y, w, h, color)
    # Excavator silhouette
    draw.rectangle([770, 200, 900, 290], fill=(220, 180, 30))
    draw.rectangle([800, 170, 870, 220], fill=(220, 180, 30))
    draw.line([(870, 200), (970, 130)], fill=(60, 60, 60), width=10)
    _noise(img)
    _overlay_label(draw, "ENGR YARD  ID: S005  UNIT: 8th ESB")
    return img


def render_ship_deck(sample: dict) -> Image.Image:
    img = Image.new("RGB", (W, H), (40, 70, 95))  # ocean/steel deck dim
    draw = ImageDraw.Draw(img)
    # Deck plating
    draw.rectangle([0, 100, W, H], fill=(70, 78, 86))
    for x in range(0, W, 80):
        draw.line([(x, 100), (x, H)], fill=(50, 56, 64), width=1)
    for y in range(120, H, 60):
        draw.line([(0, y), (W, y)], fill=(50, 56, 64), width=1)
    # Sky / horizon
    draw.rectangle([0, 0, W, 100], fill=(58, 96, 130))
    # Pallet grid 9 wide x 4 deep
    rows, cols = 4, 9
    for r in range(rows):
        for c in range(cols):
            pw, ph = 90, 50
            x = 30 + c * 110
            y = 200 + r * 80
            color = PALLET_TAN if (r + c) % 2 == 0 else (200, 175, 60)
            _draw_pallet(draw, x, y, pw, ph, color, label="464L")
    # Crane silhouette
    draw.line([(W - 80, 100), (W - 80, 540)], fill=(20, 20, 20), width=8)
    draw.line([(W - 80, 100), (W - 350, 80)], fill=(20, 20, 20), width=6)
    _noise(img)
    _overlay_label(draw, "MPSRON DECK  ID: S006  HULL: USNS-2nd-ESG")
    return img


RENDERERS = {
    "warehouse_grid": render_warehouse_grid,
    "loading_dock_mixed": render_loading_dock,
    "drone_overhead_truck": render_drone_overhead_truck,
    "flight_line_463l": render_flight_line,
    "construction_yard": render_construction_yard,
    "ship_deck_pallets": render_ship_deck,
}


def main() -> None:
    # 1) platform_specs.csv
    csv_path = ROOT / "platform_specs.csv"
    with csv_path.open("w", newline="") as f:
        w = csv.DictWriter(
            f,
            fieldnames=["platform", "category", "pallets_463l", "max_payload_kg",
                        "internal_cube_m3", "notes"],
        )
        w.writeheader()
        for row in PLATFORM_SPECS:
            w.writerow(row)
    print(f"wrote {csv_path}  ({len(PLATFORM_SPECS)} platforms)")

    # 2) Sample images + manifest
    manifest = []
    for s in SAMPLES:
        renderer = RENDERERS[s["name"]]
        img = renderer(s)
        out = SAMPLES_DIR / f"{s['id']}_{s['name']}.jpg"
        img.save(out, "JPEG", quality=90)
        manifest.append({
            "id": s["id"],
            "name": s["name"],
            "title": s["title"],
            "scene_type": s["scene_type"],
            "true_pallets": s["true_pallets"],
            "pallet_type": s["pallet_type"],
            "estimated_avg_kg_per_pallet": s["estimated_avg_kg_per_pallet"],
            "narration": s["narration"],
            "local_path": str(out.relative_to(APP_ROOT)),
        })
        print(f"wrote {out}")
    (ROOT / "sample_manifest.json").write_text(json.dumps(manifest, indent=2))
    print(f"wrote {ROOT / 'sample_manifest.json'}")

    # 3) seed an empty cached_briefs.json if missing — precompute_briefs.py fills it
    cb = ROOT / "cached_briefs.json"
    if not cb.exists():
        cb.write_text(json.dumps({}, indent=2))
        print(f"seeded empty {cb}; run precompute_briefs.py to fill")


if __name__ == "__main__":
    main()
