"""Synthetic NASA FIRMS-shape fire-detection dataset for an AOI, 24 months.

This generator produces fire pixels (lat, lon, datetime, brightness K,
FRP MW, confidence) that are **schema-byte-compatible** with the real NASA
FIRMS VIIRS / MODIS active-fire product. The synthetic file lets the EMBER
pipeline run end-to-end with no network or API key.

To swap in REAL FIRMS data:

  1. Download a country / region archive (JSON or CSV) from
       https://firms.modaps.eosdis.nasa.gov/country/   (or /api/area/)
  2. Drop it at  data/firms_ukraine.json  (or repoint the path in src/app.py).
  3. Required columns: latitude, longitude, brightness, scan, track,
       acq_date, acq_time, satellite, confidence, frp.

The synthesis is biased to five realistic source classes seen in
conflict-zone combustion analysis:

  combat_artillery  -- short, intense, point bursts in contested oblasts
  combat_armor      -- vehicle hits along front-line salients
  industrial        -- repeated point sources at refineries / depots
  wildfire          -- summer agricultural line-fires across the ag belt
  structure         -- single-detection structure fires in towns

Each pixel is independently sampled but cluster_truth is recorded so the
clustering pipeline can be evaluated qualitatively in the demo. Seeded with
random.Random(1776) for reproducibility.
"""
from __future__ import annotations

import json
import math
import random
from datetime import datetime, timedelta, timezone
from pathlib import Path

OUT = Path(__file__).resolve().parent / "firms_ukraine.json"

# Anchor points: (name, lat, lon, oblast, kind)
HOTSPOTS = [
    # Eastern front salients -- dense artillery / armor activity
    ("Bakhmut",           48.595, 38.000, "Donetsk",       "combat_artillery"),
    ("Avdiivka",          48.139, 37.745, "Donetsk",       "combat_artillery"),
    ("Kreminna",          49.046, 38.207, "Luhansk",       "combat_artillery"),
    ("Vuhledar",          47.776, 37.262, "Donetsk",       "combat_armor"),
    ("Kupyansk",          49.708, 37.616, "Kharkiv",       "combat_armor"),
    ("Robotyne",          47.443, 35.832, "Zaporizhzhia",  "combat_artillery"),
    ("Krynky",            46.747, 33.140, "Kherson",       "combat_armor"),
    # Industrial / energy infrastructure
    ("Kremenchuk_refinery", 49.074, 33.443, "Poltava",     "industrial"),
    ("Lysychansk_refinery", 48.910, 38.454, "Luhansk",     "industrial"),
    ("Mariupol_steel",      47.117, 37.677, "Donetsk",     "industrial"),
    ("Zaporizhzhia_steel",  47.840, 35.107, "Zaporizhzhia","industrial"),
    # Agricultural belt -- summer crop / stubble fires
    ("Cherkasy_ag",        49.444, 32.060, "Cherkasy",     "wildfire"),
    ("Kirovohrad_ag",      48.508, 32.262, "Kirovohrad",   "wildfire"),
    ("Mykolaiv_ag",        47.000, 31.700, "Mykolaiv",     "wildfire"),
    ("Odesa_ag",           46.700, 30.730, "Odesa",        "wildfire"),
    ("Vinnytsia_ag",       49.233, 28.470, "Vinnytsia",    "wildfire"),
    # Structure / urban fires
    ("Kharkiv_city",       49.994, 36.231, "Kharkiv",      "structure"),
    ("Kherson_city",       46.635, 32.616, "Kherson",      "structure"),
    ("Kyiv_city",          50.450, 30.523, "Kyiv",         "structure"),
]

OBLAST_BBOXES = {  # rough bounding boxes for fallback random pixels
    "Ukraine": (44.0, 52.4, 22.0, 40.2),
}

START = datetime(2024, 4, 1, 0, 0, 0)
END   = datetime(2026, 4, 1, 0, 0, 0)
TOTAL_DAYS = (END - START).days


def _samp_combat_artillery(rng: random.Random, anchor) -> dict:
    """Tight point burst, very high brightness, very high FRP, short duration."""
    name, lat0, lon0, oblast, _ = anchor
    # tight spatial scatter (~2-3 km)
    lat = lat0 + rng.gauss(0, 0.025)
    lon = lon0 + rng.gauss(0, 0.035)
    bright = rng.gauss(385, 25)             # very hot
    frp = abs(rng.gauss(45, 18))            # high radiative power
    conf = rng.choice(["nominal", "high", "high", "high"])
    return _pixel(lat, lon, bright, frp, conf, oblast, "combat_artillery")


def _samp_combat_armor(rng: random.Random, anchor) -> dict:
    """Vehicle hit: hot, point-like, sometimes a follow-on detection."""
    name, lat0, lon0, oblast, _ = anchor
    lat = lat0 + rng.gauss(0, 0.04)
    lon = lon0 + rng.gauss(0, 0.05)
    bright = rng.gauss(360, 30)
    frp = abs(rng.gauss(28, 12))
    conf = rng.choice(["nominal", "high", "high"])
    return _pixel(lat, lon, bright, frp, conf, oblast, "combat_armor")


def _samp_industrial(rng: random.Random, anchor) -> dict:
    """Industrial: medium-high brightness, very high FRP, persistent location."""
    name, lat0, lon0, oblast, _ = anchor
    lat = lat0 + rng.gauss(0, 0.008)        # very tight (single facility)
    lon = lon0 + rng.gauss(0, 0.010)
    bright = rng.gauss(345, 20)
    frp = abs(rng.gauss(70, 30))            # massive FRP -- big fuel/steel fires
    conf = rng.choice(["high", "high", "high"])
    return _pixel(lat, lon, bright, frp, conf, oblast, "industrial")


def _samp_wildfire(rng: random.Random, anchor) -> dict:
    """Agricultural line-fire: long linear scatter, moderate brightness."""
    name, lat0, lon0, oblast, _ = anchor
    # bias along a heading -- creates a line
    heading = rng.uniform(0, 2 * math.pi)
    dist = rng.gauss(0, 0.15)
    lat = lat0 + dist * math.cos(heading) + rng.gauss(0, 0.02)
    lon = lon0 + dist * math.sin(heading) + rng.gauss(0, 0.02)
    bright = rng.gauss(320, 18)             # cooler than combat
    frp = abs(rng.gauss(12, 6))
    conf = rng.choice(["low", "nominal", "nominal", "high"])
    return _pixel(lat, lon, bright, frp, conf, oblast, "wildfire")


def _samp_structure(rng: random.Random, anchor) -> dict:
    """Single-detection structure fire."""
    name, lat0, lon0, oblast, _ = anchor
    lat = lat0 + rng.gauss(0, 0.05)
    lon = lon0 + rng.gauss(0, 0.06)
    bright = rng.gauss(340, 22)
    frp = abs(rng.gauss(18, 10))
    conf = rng.choice(["nominal", "high", "high"])
    return _pixel(lat, lon, bright, frp, conf, oblast, "structure")


def _pixel(lat, lon, bright, frp, conf, oblast, truth) -> dict:
    return {
        "lat": round(float(lat), 5),
        "lon": round(float(lon), 5),
        "brightness_k": round(float(bright), 1),
        "frp_mw": round(float(frp), 2),
        "confidence": conf,
        "scan_km": round(0.375 + random.random() * 0.05, 3),
        "track_km": round(0.375 + random.random() * 0.05, 3),
        "satellite": random.choice(["VIIRS-NOAA20", "VIIRS-NPP", "MODIS-Aqua", "MODIS-Terra"]),
        "instrument": "VIIRS",
        "version": "2.0NRT",
        "daynight": "D" if random.random() > 0.4 else "N",
        "oblast": oblast,
        "truth_class": truth,  # ground-truth class label (used for demo coloring)
    }


SAMPLERS = {
    "combat_artillery": _samp_combat_artillery,
    "combat_armor":     _samp_combat_armor,
    "industrial":       _samp_industrial,
    "wildfire":         _samp_wildfire,
    "structure":        _samp_structure,
}


def _temporal_weight(class_kind: str, day_of_year: int, year_progress: float, rng: random.Random) -> float:
    """Weight the chance of a sample firing on a given day, by class."""
    if class_kind == "wildfire":
        # peak July-September (DOY 180-260)
        peak = 220
        return math.exp(-((day_of_year - peak) ** 2) / (2 * 35 ** 2))
    if class_kind == "industrial":
        # roughly steady, with episodic spikes
        return 0.4 + (0.6 if rng.random() < 0.05 else 0.0)
    if class_kind in ("combat_artillery", "combat_armor"):
        # heavy throughout, with offensive surges
        # Surge near "summer counter-offensive" window each year
        surge = 1.0 + 0.8 * math.exp(-((day_of_year - 170) ** 2) / (2 * 40 ** 2))
        return 0.7 * surge
    if class_kind == "structure":
        # winter heating fires uptick
        return 0.5 + 0.4 * math.exp(-((day_of_year - 30) ** 2) / (2 * 60 ** 2))
    return 0.3


def generate(n_pixels: int = 5000, seed: int = 1776) -> list[dict]:
    rng = random.Random(seed)
    random.seed(seed)
    pixels: list[dict] = []

    # Pre-bucket hotspots by class for fast pick
    by_kind: dict[str, list] = {}
    for h in HOTSPOTS:
        by_kind.setdefault(h[4], []).append(h)

    # Class mix (roughly): combat_artillery 38%, combat_armor 18%, industrial 9%,
    # wildfire 28%, structure 7%
    class_weights = {
        "combat_artillery": 0.38,
        "combat_armor":     0.18,
        "industrial":       0.09,
        "wildfire":         0.28,
        "structure":        0.07,
    }
    # Resolve cumulative
    classes = list(class_weights.keys())
    cw = [class_weights[c] for c in classes]

    while len(pixels) < n_pixels:
        # choose class
        c = rng.choices(classes, weights=cw, k=1)[0]
        # choose date
        day_offset = rng.randint(0, TOTAL_DAYS - 1)
        ts = START + timedelta(days=day_offset, minutes=rng.randint(0, 1439))
        # gate by temporal weight
        if rng.random() > _temporal_weight(c, ts.timetuple().tm_yday, day_offset / TOTAL_DAYS, rng):
            continue
        anchor = rng.choice(by_kind[c])
        px = SAMPLERS[c](rng, anchor)
        px["acq_datetime"] = ts.isoformat() + "Z"
        # FIRMS schema-like split fields
        px["acq_date"] = ts.strftime("%Y-%m-%d")
        px["acq_time"] = ts.strftime("%H%M")
        pixels.append(px)

    pixels.sort(key=lambda x: x["acq_datetime"])
    return pixels


def main() -> None:
    pixels = generate(5000)
    OUT.write_text(json.dumps({
        "source": "Synthetic NASA FIRMS-format fire pixels (Ukraine, 24mo). "
                  "Plug-in target: NASA FIRMS Ukraine 2-yr archive "
                  "(https://firms.modaps.eosdis.nasa.gov/country/).",
        "generated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S") + "Z",
        "count": len(pixels),
        "schema": ["lat", "lon", "brightness_k", "frp_mw", "confidence",
                   "scan_km", "track_km", "satellite", "instrument", "version",
                   "daynight", "oblast", "truth_class", "acq_datetime",
                   "acq_date", "acq_time"],
        "pixels": pixels,
    }, indent=2))
    counts: dict[str, int] = {}
    for p in pixels:
        counts[p["truth_class"]] = counts.get(p["truth_class"], 0) + 1
    print(f"Wrote {len(pixels)} pixels -> {OUT}")
    for k, v in sorted(counts.items(), key=lambda kv: -kv[1]):
        print(f"  {k:20s} {v}")


if __name__ == "__main__":
    main()
