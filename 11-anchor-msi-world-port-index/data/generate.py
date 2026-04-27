"""ANCHOR — Synthetic World Port Index dataset generator (Bucket C stand-in).

This script emits a 250-port synthetic corpus seeded for reproducibility so
the template runs end-to-end with no external dependencies. Each record
carries the WPI-style fields an MPF / Blount Island Command planner cares
about:

  port_id, name, country, region, lat, lon, harbor_type,
  max_draft_m, max_loa_m, channel_depth_m, berths,
  anchorage_capacity, cranes, roro_capable,
  bunker_available, repair_capability,
  political_risk, hostnation_status, weather_risk,
  notes, profile

REAL DATA (Bucket C — requires custom loader code):
  NGA MSI World Port Index (WPI), Pub 150 — 3,700+ ports, refreshed quarterly.
  https://msi.nga.mil/Publications/WPI

  WPI ships as an ESRI shapefile bundle. To plug in the real data, write a
  loader (e.g. with geopandas) that:
    1. Reads the shapefile and iterates features.
    2. Maps WPI attributes to this schema (berth depth, channel depth,
       crane count, fuel/bunker availability, RoRo capability,
       host-nation posture proxy).
    3. Writes data/ports.json in the same record shape.
  Then rebuild the embedding cache:
      python -c "from src.rag import build_embeddings; build_embeddings(force=True)"
  No changes required in src/rag.py or src/app.py.
"""
from __future__ import annotations

import json
import math
import random
from pathlib import Path
import sys

OUT_DIR = Path(__file__).parent
SEED = 1776
N_RECORDS = 250

# Make repo importable for shared/
ROOT = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(ROOT))

# Region anchor points: name, lat, lon, lat-spread, lon-spread, weight, country pool, hn_status pool
REGIONS = [
    {
        "name": "Western Pacific",
        "lat": 15.0, "lon": 135.0,
        "spread_lat": 18.0, "spread_lon": 22.0,
        "weight": 0.34,
        "countries": [
            ("Japan", "ALLY"), ("Republic of Korea", "ALLY"),
            ("Philippines", "PARTNER"), ("Guam (US)", "US_TERRITORY"),
            ("Northern Mariana Is. (US)", "US_TERRITORY"),
            ("Palau", "PARTNER"), ("Federated States of Micronesia", "PARTNER"),
            ("Marshall Islands", "PARTNER"), ("Taiwan", "PARTNER"),
            ("Vietnam", "NEUTRAL"), ("Indonesia", "NEUTRAL"),
            ("Malaysia", "NEUTRAL"), ("Singapore", "PARTNER"),
            ("Brunei", "PARTNER"), ("Thailand", "ALLY"),
        ],
    },
    {
        "name": "Indian Ocean",
        "lat": -5.0, "lon": 75.0,
        "spread_lat": 22.0, "spread_lon": 28.0,
        "weight": 0.28,
        "countries": [
            ("Diego Garcia (UK/US)", "US_TERRITORY"), ("India", "PARTNER"),
            ("Sri Lanka", "PARTNER"), ("Maldives", "NEUTRAL"),
            ("Oman", "PARTNER"), ("UAE", "PARTNER"),
            ("Bahrain", "ALLY"), ("Djibouti", "PARTNER"),
            ("Kenya", "PARTNER"), ("Tanzania", "NEUTRAL"),
            ("Mozambique", "NEUTRAL"), ("South Africa", "PARTNER"),
            ("Australia", "ALLY"), ("Indonesia", "NEUTRAL"),
            ("Mauritius", "PARTNER"), ("Madagascar", "NEUTRAL"),
            ("Seychelles", "PARTNER"), ("Pakistan", "DENIED"),
        ],
    },
    {
        "name": "Mediterranean",
        "lat": 38.0, "lon": 18.0,
        "spread_lat": 6.0, "spread_lon": 22.0,
        "weight": 0.22,
        "countries": [
            ("Italy", "ALLY"), ("Spain", "ALLY"),
            ("Greece", "ALLY"), ("Türkiye", "ALLY"),
            ("Cyprus", "PARTNER"), ("Malta", "PARTNER"),
            ("France", "ALLY"), ("Croatia", "ALLY"),
            ("Israel", "ALLY"), ("Egypt", "PARTNER"),
            ("Tunisia", "NEUTRAL"), ("Morocco", "PARTNER"),
            ("Albania", "ALLY"), ("Lebanon", "DENIED"),
            ("Libya", "DENIED"), ("Syria", "DENIED"),
        ],
    },
    {
        "name": "South Pacific / Oceania",
        "lat": -18.0, "lon": 165.0,
        "spread_lat": 16.0, "spread_lon": 28.0,
        "weight": 0.10,
        "countries": [
            ("Australia", "ALLY"), ("New Zealand", "ALLY"),
            ("Papua New Guinea", "PARTNER"), ("Fiji", "PARTNER"),
            ("Solomon Islands", "PARTNER"), ("Vanuatu", "PARTNER"),
            ("New Caledonia (FR)", "ALLY"), ("Samoa", "PARTNER"),
            ("Tonga", "PARTNER"), ("Cook Islands", "PARTNER"),
        ],
    },
    {
        "name": "Eastern Pacific / Americas",
        "lat": 8.0, "lon": -100.0,
        "spread_lat": 28.0, "spread_lon": 18.0,
        "weight": 0.06,
        "countries": [
            ("Mexico", "PARTNER"), ("Panama", "PARTNER"),
            ("Costa Rica", "PARTNER"), ("Colombia", "PARTNER"),
            ("Ecuador", "PARTNER"), ("Peru", "PARTNER"),
            ("Chile", "ALLY"), ("Hawaii (US)", "US_TERRITORY"),
        ],
    },
]

HARBOR_TYPES = [
    ("Coastal Natural", 0.30),
    ("Coastal Breakwater", 0.20),
    ("Coastal Tide Gate", 0.05),
    ("River Natural", 0.15),
    ("River Basin", 0.05),
    ("Lake or Canal", 0.03),
    ("Open Roadstead", 0.10),
    ("Typhoon Harbor", 0.06),
    ("Manmade Harbor", 0.06),
]

REPAIR_LEVELS = ["None", "Limited", "Moderate", "Major", "Full Drydock"]

NAME_PREFIXES = [
    "Port of", "Naval Base", "Terminal", "Harbor",
    "Pier", "Anchorage at", "Wharf at",
]

# Seed name fragments — kept generic so we never accidentally collide with a real installation
NAME_ROOTS_PER_REGION = {
    "Western Pacific": [
        "Subic", "Bataan", "Cebu", "Davao", "Manila North", "Cagayan",
        "Naha South", "Yokosuka East", "Sasebo Outer", "Iwakuni", "Kobe South",
        "Busan East", "Pohang", "Ulsan North", "Inchon", "Pusan",
        "Apra", "Tinian", "Saipan", "Rota", "Koror", "Yap",
        "Kaohsiung", "Keelung", "Hualien",
        "Cam Ranh", "Da Nang", "Haiphong",
        "Belawan", "Surabaya", "Makassar", "Tanjung",
        "Penang", "Kota Kinabalu", "Sandakan", "Labuan",
        "Singapore West", "Tuas", "Sembawang",
        "Muara", "Bandar",
        "Laem Chabang", "Sattahip", "Ranong",
    ],
    "Indian Ocean": [
        "Diego Outer", "Diego Lagoon", "Kochi", "Vizag", "Chennai",
        "Mumbai South", "Mangalore", "Tuticorin", "Paradip", "Kolkata",
        "Colombo", "Trincomalee", "Hambantota",
        "Male", "Hulhumale",
        "Salalah", "Duqm", "Sohar",
        "Jebel Ali", "Khalifa", "Fujairah", "Khor Fakkan",
        "Manama", "Sitra",
        "Doraleh", "Tadjoura",
        "Mombasa", "Lamu",
        "Dar es Salaam", "Tanga",
        "Beira", "Maputo", "Nacala",
        "Durban", "Cape Town", "Coega", "Ngqura", "Saldanha",
        "Fremantle", "Darwin", "Broome", "Geraldton",
        "Bali", "Lombok",
        "Port Louis",
        "Tamatave", "Diego Suarez",
        "Victoria", "Praslin",
        "Karachi", "Gwadar",
    ],
    "Mediterranean": [
        "Naples", "Gaeta", "Augusta", "Taranto", "Cagliari", "Livorno",
        "Rota", "Algeciras", "Cartagena", "Valencia", "Barcelona",
        "Piraeus", "Souda", "Crete West", "Thessaloniki", "Patras",
        "Aksaz", "Iskenderun", "Mersin", "Izmir", "Antalya",
        "Limassol", "Larnaca",
        "Marsaxlokk", "Valletta",
        "Toulon", "Marseille", "Sète",
        "Split", "Pula", "Rijeka",
        "Haifa", "Ashdod",
        "Alexandria", "Port Said", "Damietta",
        "Bizerte", "La Goulette",
        "Tangier", "Casablanca",
        "Durrës", "Vlorë",
        "Beirut",
        "Tripoli (LY)", "Benghazi",
        "Latakia", "Tartus",
    ],
    "South Pacific / Oceania": [
        "Brisbane", "Townsville", "Cairns", "Gladstone",
        "Auckland", "Wellington", "Lyttelton",
        "Port Moresby", "Lae",
        "Suva", "Lautoka",
        "Honiara",
        "Port Vila",
        "Nouméa",
        "Apia",
        "Nuku'alofa",
        "Avarua",
    ],
    "Eastern Pacific / Americas": [
        "Manzanillo", "Lazaro Cardenas", "Ensenada",
        "Balboa", "Colón",
        "Puerto Caldera",
        "Buenaventura",
        "Guayaquil", "Manta",
        "Callao", "Chimbote",
        "San Antonio", "Valparaíso",
        "Pearl Harbor East", "Hilo", "Kahului",
    ],
}


def _weighted_choice(rng: random.Random, items: list[tuple]) -> tuple:
    total = sum(w for _, w in items)
    r = rng.uniform(0, total)
    upto = 0.0
    for item, w in items:
        upto += w
        if upto >= r:
            return item
    return items[-1][0]


def _pick_region(rng: random.Random) -> dict:
    return _weighted_choice(rng, [(r, r["weight"]) for r in REGIONS])


def _hn_baseline_risk(hn_status: str, rng: random.Random) -> float:
    """Political risk score 0-10 keyed off host-nation posture."""
    base = {
        "US_TERRITORY": 0.5,
        "ALLY": 1.5,
        "PARTNER": 3.5,
        "NEUTRAL": 5.5,
        "DENIED": 8.5,
    }[hn_status]
    return round(min(10.0, max(0.0, base + rng.uniform(-1.0, 1.5))), 1)


def _weather_risk_for_region(region_name: str, rng: random.Random) -> float:
    """Weather climatology risk score 0-10. Typhoon belt > Mediterranean."""
    base = {
        "Western Pacific": 6.0,
        "Indian Ocean": 4.5,
        "Mediterranean": 2.5,
        "South Pacific / Oceania": 5.5,
        "Eastern Pacific / Americas": 4.0,
    }.get(region_name, 4.0)
    return round(min(10.0, max(0.0, base + rng.uniform(-1.5, 2.0))), 1)


def _make_port(idx: int, rng: random.Random, used_names: set) -> dict:
    region = _pick_region(rng)
    country, hn_status = rng.choice(region["countries"])

    # Name selection — never repeat
    roots = NAME_ROOTS_PER_REGION[region["name"]]
    for _ in range(20):
        root = rng.choice(roots)
        prefix = rng.choice(NAME_PREFIXES)
        candidate = f"{prefix} {root}"
        if candidate not in used_names:
            break
    else:
        candidate = f"{prefix} {root} {idx}"
    used_names.add(candidate)

    # Coordinates — gaussian around region centroid
    lat = round(region["lat"] + rng.gauss(0, region["spread_lat"] / 3.0), 4)
    lon = round(region["lon"] + rng.gauss(0, region["spread_lon"] / 3.0), 4)
    lat = max(-66.0, min(66.0, lat))
    lon = ((lon + 180) % 360) - 180

    # Physical capacity — correlated cluster: bigger ports have everything bigger
    size_tier = rng.choices(["small", "medium", "large", "deep_water"],
                            weights=[0.30, 0.35, 0.25, 0.10])[0]
    if size_tier == "small":
        max_draft_m = round(rng.uniform(3.5, 8.0), 1)
        max_loa_m = round(rng.uniform(80, 180), 0)
        channel_depth_m = round(max_draft_m + rng.uniform(0.3, 1.5), 1)
        berths = rng.randint(2, 8)
        anchorage = rng.randint(2, 12)
        cranes = rng.randint(0, 4)
    elif size_tier == "medium":
        max_draft_m = round(rng.uniform(8.0, 12.0), 1)
        max_loa_m = round(rng.uniform(180, 260), 0)
        channel_depth_m = round(max_draft_m + rng.uniform(0.5, 2.0), 1)
        berths = rng.randint(6, 18)
        anchorage = rng.randint(8, 30)
        cranes = rng.randint(2, 10)
    elif size_tier == "large":
        max_draft_m = round(rng.uniform(12.0, 16.0), 1)
        max_loa_m = round(rng.uniform(260, 350), 0)
        channel_depth_m = round(max_draft_m + rng.uniform(0.8, 2.5), 1)
        berths = rng.randint(14, 32)
        anchorage = rng.randint(20, 60)
        cranes = rng.randint(8, 22)
    else:  # deep_water
        max_draft_m = round(rng.uniform(16.0, 22.0), 1)
        max_loa_m = round(rng.uniform(330, 420), 0)
        channel_depth_m = round(max_draft_m + rng.uniform(1.0, 3.0), 1)
        berths = rng.randint(20, 60)
        anchorage = rng.randint(30, 120)
        cranes = rng.randint(14, 40)

    harbor_type = _weighted_choice(rng, HARBOR_TYPES)

    # Capability flags — bigger + ally-aligned ports likelier to have RoRo + bunker
    ally_bias = {"US_TERRITORY": 0.4, "ALLY": 0.3, "PARTNER": 0.15, "NEUTRAL": 0.0, "DENIED": -0.2}[hn_status]
    size_bias = {"small": -0.2, "medium": 0.0, "large": 0.25, "deep_water": 0.4}[size_tier]
    roro_p = 0.45 + ally_bias + size_bias
    bunker_p = 0.55 + ally_bias + size_bias * 0.7
    roro_capable = rng.random() < max(0.05, min(0.95, roro_p))
    bunker_available = rng.random() < max(0.05, min(0.97, bunker_p))

    # Repair capability — biased by size
    repair_weights = {
        "small": [0.50, 0.35, 0.10, 0.04, 0.01],
        "medium": [0.18, 0.45, 0.25, 0.10, 0.02],
        "large": [0.05, 0.25, 0.35, 0.25, 0.10],
        "deep_water": [0.02, 0.10, 0.28, 0.35, 0.25],
    }[size_tier]
    repair_capability = rng.choices(REPAIR_LEVELS, weights=repair_weights)[0]

    political_risk = _hn_baseline_risk(hn_status, rng)
    weather_risk = _weather_risk_for_region(region["name"], rng)

    # Notes — short, plausible operational footnote
    note_pool = [
        f"Pilotage compulsory above {round(max_loa_m * 0.4)}m LOA.",
        f"Tidal range {round(rng.uniform(0.5, 4.5), 1)}m; berthing window applies.",
        f"VTS coverage active 24/7 within {rng.randint(8, 30)}nm.",
        f"Diplomatic clearance required for grey hulls (NLT {rng.choice([7, 14, 21, 30])} days notice).",
        f"Bunker grades available: {rng.choice(['HFO380, MGO', 'VLSFO, MGO', 'MGO only', 'HFO, VLSFO, MGO, LNG'])}.",
        f"RoRo ramp angle: {rng.uniform(6, 14):.1f}° at MLW.",
        f"Container yard capacity ~{rng.randint(2, 60)*1000} TEU.",
        f"Heavy lift crane peak SWL: {rng.randint(40, 800)} t.",
        f"Recent dredging program completed {rng.randint(2018, 2025)}; channel re-surveyed.",
        f"Partnered with {rng.choice(['MSC', 'CMA CGM', 'Maersk', 'COSCO', 'ONE', 'Evergreen'])} for liner calls.",
    ]
    notes = " ".join(rng.sample(note_pool, k=rng.randint(2, 3)))

    # Profile string — concatenated for embedding-based RAG
    profile = (
        f"{candidate} ({country}, {region['name']}). "
        f"Harbor type: {harbor_type}. "
        f"Max draft {max_draft_m}m, max LOA {max_loa_m}m, channel depth {channel_depth_m}m. "
        f"{berths} berths, {anchorage} anchorage slots, {cranes} cranes. "
        f"RoRo: {'yes' if roro_capable else 'no'}. "
        f"Bunker: {'yes' if bunker_available else 'no'}. "
        f"Repair capability: {repair_capability}. "
        f"Host-nation status: {hn_status} (political risk {political_risk}/10). "
        f"Climatology risk {weather_risk}/10. "
        f"{notes}"
    )

    return {
        "port_id": f"WPI-{idx:04d}",
        "name": candidate,
        "country": country,
        "region": region["name"],
        "lat": lat,
        "lon": lon,
        "harbor_type": harbor_type,
        "max_draft_m": max_draft_m,
        "max_loa_m": max_loa_m,
        "channel_depth_m": channel_depth_m,
        "berths": berths,
        "anchorage_capacity": anchorage,
        "cranes": cranes,
        "roro_capable": roro_capable,
        "bunker_available": bunker_available,
        "repair_capability": repair_capability,
        "political_risk": political_risk,
        "hostnation_status": hn_status,
        "weather_risk": weather_risk,
        "size_tier": size_tier,
        "notes": notes,
        "profile": profile,
    }


def generate(n: int = N_RECORDS, seed: int = SEED) -> list[dict]:
    rng = random.Random(seed)
    used = set()
    return [_make_port(i + 1, rng, used) for i in range(n)]


def main() -> None:
    rows = generate()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    json_path = OUT_DIR / "ports.json"
    json_path.write_text(json.dumps(rows, indent=2))
    print(f"Wrote {len(rows)} ports → {json_path}")

    # Parquet (optional — only if pyarrow/pandas present)
    try:
        import pandas as pd  # noqa: WPS433
        df = pd.DataFrame(rows)
        parquet_path = OUT_DIR / "ports.parquet"
        df.to_parquet(parquet_path, index=False)
        print(f"Wrote {len(rows)} ports → {parquet_path}")
    except ImportError:
        print("(pandas/pyarrow not installed — skipping parquet)")

    # Quick distribution print
    from collections import Counter
    region_dist = Counter(r["region"] for r in rows)
    hn_dist = Counter(r["hostnation_status"] for r in rows)
    print("\nRegion distribution:")
    for k, v in region_dist.most_common():
        print(f"  {k:30s} {v:3d}")
    print("\nHost-nation distribution:")
    for k, v in hn_dist.most_common():
        print(f"  {k:15s} {v:3d}")


if __name__ == "__main__":
    main()
