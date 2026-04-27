"""OPENGATE — Synthetic data.gov-shape federal-dataset catalog generator.

Real dataset reference (would plug in via data/load_real.py):
  data.gov public CKAN API — 300,000+ federal datasets across every agency.
  https://catalog.data.gov/api/3/action/package_search

We synthesize 200 plausible federal-dataset records, seeded for reproducibility.
Each record carries the CKAN-style fields a Marine analyst doing OSINT or
contested-logistics prep cares about:

  dataset_id, title, abstract, agency, sub_office, tags (list[str]),
  last_updated (ISO date), format (CSV / JSON / GeoTIFF / NetCDF / API / SHP),
  license, record_count_estimate, refresh_cadence,
  url (synthetic catalog.data.gov path)

Two-pass generation:
  pass 1 (`python data/generate.py`)         — emit datasets.json
  pass 2 (`python data/generate.py --embed`) — embed every abstract,
                                                cache embeddings.npy + ids.json,
                                                pre-compute cached_briefs.json
"""
from __future__ import annotations

import argparse
import json
import random
import sys
from datetime import date, timedelta
from pathlib import Path

OUT_DIR = Path(__file__).parent
SEED = 1776
N_RECORDS = 200

# Make repo importable for shared/
ROOT = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(ROOT))


# Federal agency profiles — each carries plausible sub-offices, topic palette,
# typical formats, and a refresh-cadence weight.
AGENCIES = [
    {
        "name": "NOAA",
        "full": "National Oceanic and Atmospheric Administration",
        "sub_offices": ["NCEI", "NWS", "NESDIS", "NMFS", "OAR", "NOS"],
        "topics": [
            "sea-surface temperature", "tropical cyclone tracks", "wave height",
            "ocean salinity", "Pacific basin bathymetry", "coastal radar",
            "tidal residuals", "coral reef bleaching", "harmful algal bloom",
            "buoy observations", "climatology normals", "sea ice extent",
            "tsunami arrival times", "storm surge runup",
        ],
        "formats": ["NetCDF", "GeoTIFF", "CSV", "API"],
        "weight": 0.16,
    },
    {
        "name": "NASA",
        "full": "National Aeronautics and Space Administration",
        "sub_offices": ["JPL", "GSFC", "Earthdata", "LARC", "Ames"],
        "topics": [
            "soil moisture (SMAP)", "MODIS Aqua imagery", "MODIS Terra imagery",
            "land-surface temperature", "GPM precipitation", "ICESat-2 elevation",
            "GRACE-FO water mass anomaly", "Landsat 9 surface reflectance",
            "atmospheric aerosol optical depth", "vegetation NDVI",
            "cloud-top pressure", "fire radiative power",
        ],
        "formats": ["HDF5", "NetCDF", "GeoTIFF", "API"],
        "weight": 0.13,
    },
    {
        "name": "FEMA",
        "full": "Federal Emergency Management Agency",
        "sub_offices": ["NFIP", "Region IX", "Region X", "OPPA", "RAPT"],
        "topics": [
            "flood insurance claims", "disaster declarations",
            "emergency shelter capacity", "individual assistance grants",
            "public assistance projects", "national risk index",
            "hazard mitigation projects", "preparedness drills attendance",
            "search-and-rescue task force readiness",
        ],
        "formats": ["CSV", "SHP", "GeoJSON", "API"],
        "weight": 0.08,
    },
    {
        "name": "DOT",
        "full": "Department of Transportation",
        "sub_offices": ["BTS", "MARAD", "FAA", "FHWA", "FMCSA"],
        "topics": [
            "port performance freight statistics",
            "container throughput by U.S. port",
            "truck border-crossing volumes",
            "general aviation flight tracks",
            "commercial driver hours-of-service violations",
            "airport delay causal factors", "rail-grade crossing inventory",
            "intermodal terminal locations",
            "Jones Act vessel registry", "ferry boat census",
        ],
        "formats": ["CSV", "API", "SHP", "GeoJSON"],
        "weight": 0.10,
    },
    {
        "name": "DOD",
        "full": "Department of Defense (public-release)",
        "sub_offices": ["DLA", "DCSA", "DMDC", "USTRANSCOM (PR)", "DARPA-PR"],
        "topics": [
            "DLA aviation parts catalog (public release)",
            "defense personnel and procurement statistics",
            "base realignment property dispositions",
            "research and engineering topical funding",
            "defense logistics agency vendor index",
            "DoD energy consumption by installation",
            "selected acquisition reports (public)",
            "DoD contracts above threshold",
        ],
        "formats": ["CSV", "JSON", "API", "PDF"],
        "weight": 0.09,
    },
    {
        "name": "USDA",
        "full": "Department of Agriculture",
        "sub_offices": ["NASS", "ERS", "FSIS", "FAS", "ARS"],
        "topics": [
            "global agricultural production estimates",
            "crop yield forecasts by district",
            "livestock disease surveillance",
            "agricultural export volumes by partner country",
            "food-price index components",
            "grain stocks survey",
        ],
        "formats": ["CSV", "API", "JSON"],
        "weight": 0.05,
    },
    {
        "name": "USGS",
        "full": "United States Geological Survey",
        "sub_offices": ["EROS", "ESA", "Volcano Hazards", "Earthquake Hazards"],
        "topics": [
            "real-time earthquake catalog",
            "global volcanism program activity",
            "national elevation dataset (3DEP)",
            "groundwater monitoring wells",
            "national hydrography dataset (NHD)",
            "landslide susceptibility",
            "critical mineral commodity statistics",
        ],
        "formats": ["GeoTIFF", "SHP", "CSV", "API"],
        "weight": 0.07,
    },
    {
        "name": "EIA",
        "full": "Energy Information Administration",
        "sub_offices": ["Petroleum", "Natural Gas", "Electricity", "International"],
        "topics": [
            "weekly petroleum stocks",
            "global refined product trade flows",
            "LNG export terminal utilization",
            "electricity grid hourly demand by balancing authority",
            "international energy outlook scenarios",
            "strategic petroleum reserve drawdowns",
        ],
        "formats": ["CSV", "API", "JSON"],
        "weight": 0.05,
    },
    {
        "name": "DHS",
        "full": "Department of Homeland Security",
        "sub_offices": ["CBP", "TSA", "USCG", "CISA"],
        "topics": [
            "U.S. Coast Guard search-and-rescue cases",
            "port-of-entry pedestrian and vehicle wait times",
            "TSA passenger throughput by airport",
            "CISA known exploited vulnerabilities catalog",
            "national infrastructure protection plan sectors",
            "Coast Guard cutter deployment summaries",
        ],
        "formats": ["CSV", "JSON", "API"],
        "weight": 0.07,
    },
    {
        "name": "State",
        "full": "Department of State",
        "sub_offices": ["Bureau of Population, Refugees, and Migration",
                        "Bureau of Consular Affairs",
                        "Bureau of Political-Military Affairs"],
        "topics": [
            "travel advisory level by country",
            "refugee admissions by region",
            "foreign military sales notifications",
            "country reports on terrorism",
            "treaties in force",
        ],
        "formats": ["CSV", "JSON", "PDF"],
        "weight": 0.04,
    },
    {
        "name": "USAID",
        "full": "United States Agency for International Development",
        "sub_offices": ["BHA", "Bureau for Africa", "Bureau for Asia"],
        "topics": [
            "humanitarian assistance obligations",
            "food security early warning network (FEWS NET) classifications",
            "country development cooperation strategies",
            "disaster response funding allocations",
        ],
        "formats": ["CSV", "API", "JSON"],
        "weight": 0.04,
    },
    {
        "name": "Census",
        "full": "U.S. Census Bureau",
        "sub_offices": ["Geography Division", "International Trade",
                        "Population Division"],
        "topics": [
            "American Community Survey (ACS) tract estimates",
            "international trade in goods by HS code",
            "TIGER/Line shapefiles",
            "international population pyramids by country",
            "metropolitan statistical area boundaries",
        ],
        "formats": ["CSV", "API", "SHP", "GeoJSON"],
        "weight": 0.04,
    },
    {
        "name": "EPA",
        "full": "Environmental Protection Agency",
        "sub_offices": ["OAQPS", "Office of Water", "OECA"],
        "topics": [
            "air quality system (AQS) hourly observations",
            "toxic release inventory (TRI)",
            "drinking water enforcement actions",
            "greenhouse gas reporting program facilities",
        ],
        "formats": ["CSV", "API", "JSON"],
        "weight": 0.03,
    },
    {
        "name": "VA",
        "full": "Department of Veterans Affairs",
        "sub_offices": ["VHA", "VBA"],
        "topics": [
            "VA medical center facility locations",
            "veteran suicide prevention metrics by state",
            "compensation and pension claims processing times",
            "post-9/11 GI Bill enrollment",
        ],
        "formats": ["CSV", "JSON"],
        "weight": 0.02,
    },
    {
        "name": "BLS",
        "full": "Bureau of Labor Statistics",
        "sub_offices": ["LAUS", "QCEW", "OEWS"],
        "topics": [
            "occupational employment and wage statistics",
            "consumer price index components",
            "producer price index by industry",
            "local area unemployment statistics",
        ],
        "formats": ["CSV", "API", "JSON"],
        "weight": 0.03,
    },
]

REFRESH_CADENCES = ["realtime", "hourly", "daily", "weekly", "monthly",
                    "quarterly", "annually", "as-collected"]

LICENSES = ["U.S. Government Work (Public Domain)",
            "CC BY 4.0",
            "Open Data Commons Public Domain Dedication and License (PDDL)",
            "Creative Commons CC0"]

REGION_KEYWORDS = [
    "Indo-Pacific", "South China Sea", "Pacific basin", "Western Pacific",
    "Indian Ocean", "Arctic", "Mediterranean", "Caribbean", "Atlantic basin",
    "CONUS", "Alaska", "Hawaii", "Guam and Marianas", "Philippines",
    "Korean Peninsula", "Japan archipelago", "Taiwan Strait",
    "Bering Sea", "Strait of Hormuz", "Gulf of Aden", "Red Sea",
    "Bab-el-Mandeb", "Strait of Malacca", "Cape of Good Hope",
    "global", "regional", "CONUS-wide",
]

OPS_TAGS = [
    "logistics", "maritime", "weather", "infrastructure", "intelligence-prep",
    "humanitarian-assistance", "disaster-response", "force-protection",
    "supply-chain", "energy", "transportation", "geospatial", "demographics",
    "economic-indicators", "force-readiness", "freight", "ports",
    "airfields", "rail", "pipeline", "PNT-alternatives", "communications",
    "cyber-threat", "OSINT", "ISR-cuing",
]


def _weighted_choice(rng: random.Random, items: list[tuple]) -> object:
    total = sum(w for _, w in items)
    r = rng.uniform(0, total)
    upto = 0.0
    for item, w in items:
        upto += w
        if upto >= r:
            return item
    return items[-1][0]


def _pick_agency(rng: random.Random) -> dict:
    return _weighted_choice(rng, [(a, a["weight"]) for a in AGENCIES])


def _make_dataset(idx: int, rng: random.Random, used_titles: set) -> dict:
    agency = _pick_agency(rng)
    sub = rng.choice(agency["sub_offices"])
    topic = rng.choice(agency["topics"])
    region = rng.choice(REGION_KEYWORDS)

    # Title patterns — vary so they read naturally
    patterns = [
        f"{agency['name']} {topic.title()} — {region}",
        f"{topic.title()} ({agency['name']}/{sub})",
        f"{region} {topic.title()} — {agency['name']} {sub}",
        f"{agency['name']} {sub}: {topic.title()}",
    ]
    for _ in range(10):
        title = rng.choice(patterns)
        if title not in used_titles:
            break
    else:
        title = f"{agency['name']} {sub} {topic.title()} — record {idx}"
    used_titles.add(title)

    fmt = rng.choice(agency["formats"])
    cadence = rng.choice(REFRESH_CADENCES)
    license_ = rng.choice(LICENSES)

    # Last updated — bias recent, with a long tail going back several years
    days_ago = int(rng.triangular(1, 1825, 90))
    last_updated = (date.today() - timedelta(days=days_ago)).isoformat()

    record_count = rng.choice([
        rng.randint(50, 5_000),
        rng.randint(5_000, 100_000),
        rng.randint(100_000, 5_000_000),
        rng.randint(5_000_000, 250_000_000),
    ])

    # Tag set — region + topic-keyword tokens + ops tags
    topic_tokens = [t for t in topic.lower().replace("(", " ").replace(")", " ")
                                            .replace(",", " ").split() if len(t) > 3]
    base_tags = list({*topic_tokens[:3]})
    base_tags.append(region.lower().replace(" ", "-"))
    base_tags.extend(rng.sample(OPS_TAGS, k=rng.randint(2, 4)))
    tags = sorted(set(base_tags))[:8]

    abstract_intros = [
        f"This dataset, maintained by {agency['full']} ({agency['name']}/{sub}),",
        f"Published by {agency['name']}'s {sub} office, this collection",
        f"The {agency['name']} {sub} program publishes this dataset, which",
        f"Maintained by {agency['full']}, this {fmt}-format dataset",
    ]
    middles = [
        f"covers {topic} across the {region} area of operations.",
        f"provides {cadence} observations of {topic} for the {region} region.",
        f"captures {topic} with {region.lower()} coverage.",
        f"records {topic} pertinent to the {region} theater.",
    ]
    operational_hints = [
        "Useful for OSINT prep, contested-logistics modeling, and HA/DR cell setup.",
        "Frequently cited in MARFORPAC and INDOPACOM analytic products.",
        "Recommended for force-projection planning and route-feasibility studies.",
        "Supports campaign analysis, intelligence preparation of the operational environment, and stand-in force employment.",
        "Source data for many DoD-published assessments of regional infrastructure.",
        "Underpins joint planning timelines for distributed maritime operations.",
        "Cited in published BTS, USTRANSCOM, and MARAD freight studies.",
    ]
    coverage_lines = [
        f"Approximately {record_count:,} records.",
        f"Refresh cadence: {cadence}; latest update {last_updated}.",
        f"Format: {fmt}; license: {license_}.",
    ]
    abstract = " ".join([
        rng.choice(abstract_intros),
        rng.choice(middles),
        rng.choice(operational_hints),
        rng.choice(coverage_lines),
    ])

    dataset_id = f"DG-{agency['name'].lower()}-{idx:04d}"
    url = f"https://catalog.data.gov/dataset/{dataset_id.lower()}"

    return {
        "dataset_id": dataset_id,
        "title": title,
        "abstract": abstract,
        "agency": agency["name"],
        "agency_full": agency["full"],
        "sub_office": sub,
        "tags": tags,
        "last_updated": last_updated,
        "format": fmt,
        "license": license_,
        "record_count_estimate": record_count,
        "refresh_cadence": cadence,
        "url": url,
        "topic_seed": topic,
        "region_seed": region,
    }


def generate(n: int = N_RECORDS, seed: int = SEED) -> list[dict]:
    rng = random.Random(seed)
    used: set = set()
    return [_make_dataset(i + 1, rng, used) for i in range(n)]


def write_datasets() -> list[dict]:
    rows = generate()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    json_path = OUT_DIR / "datasets.json"
    json_path.write_text(json.dumps(rows, indent=2))
    print(f"Wrote {len(rows)} datasets -> {json_path}")

    # Distribution print
    from collections import Counter
    by_agency = Counter(r["agency"] for r in rows)
    print("\nAgency distribution:")
    for k, v in by_agency.most_common():
        print(f"  {k:8s} {v:3d}")
    return rows


# ─────────────────────────────────────────────────────────────────────────────
# Embedding cache + brief precompute
# ─────────────────────────────────────────────────────────────────────────────

CANONICAL_QUERIES = [
    {
        "id": "indo_pacific_ports",
        "label": "Indo-Pacific port congestion + contested logistics",
        "prompt": (
            "I need datasets relevant to Pacific port congestion and contested "
            "logistics in the Indo-Pacific. Specifically: container throughput, "
            "vessel call timing, host-nation infrastructure, and weather "
            "climatology that would slow MPF offload windows."
        ),
    },
    {
        "id": "haadr_typhoon",
        "label": "Typhoon-corridor humanitarian-assistance & disaster-response",
        "prompt": (
            "Pull datasets supporting a humanitarian-assistance and "
            "disaster-response cell standing up in the Western Pacific typhoon "
            "corridor. We need population, shelter capacity, prior disaster "
            "claims, real-time storm tracks, and search-and-rescue history."
        ),
    },
    {
        "id": "pnt_alt",
        "label": "GPS-denied / alternative-PNT environmental references",
        "prompt": (
            "Find federal datasets that could anchor an alternative-PNT or "
            "GPS-denied navigation feasibility study. Magnetic-field, "
            "high-resolution elevation, hydrography, and any signals-of-"
            "opportunity catalogs would all be candidates."
        ),
    },
]


def _embed_cache(rows: list[dict]) -> None:
    """Embed every dataset abstract; cache embeddings.npy + ids.json."""
    import numpy as np
    from shared.kamiwaza_client import embed  # noqa: WPS433

    abstracts = [
        f"{r['title']}. {r['abstract']} Tags: {', '.join(r['tags'])}."
        for r in rows
    ]
    ids = [r["dataset_id"] for r in rows]

    print(f"\nEmbedding {len(abstracts)} dataset abstracts...")
    batch = 64
    vecs: list[list[float]] = []
    for i in range(0, len(abstracts), batch):
        chunk = abstracts[i : i + batch]
        vecs.extend(embed(chunk))
        print(f"  embedded {min(i + batch, len(abstracts))}/{len(abstracts)}")

    import numpy as _np  # explicit local alias
    mat = _np.array(vecs, dtype=_np.float32)
    norms = _np.linalg.norm(mat, axis=1, keepdims=True) + 1e-12
    mat = mat / norms

    _np.save(OUT_DIR / "embeddings.npy", mat)
    (OUT_DIR / "embedding_ids.json").write_text(json.dumps(ids))
    print(f"Wrote embeddings -> {OUT_DIR / 'embeddings.npy'} shape={mat.shape}")


def _precompute_briefs(rows: list[dict]) -> None:
    """Run the full RAG pipeline against canonical queries; cache outputs."""
    import sys as _sys
    _sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
    from rag import retrieve, comparison_json, hero_brief  # noqa: WPS433

    briefs = {}
    for q in CANONICAL_QUERIES:
        print(f"\nPre-computing brief: {q['id']}")
        try:
            result = retrieve(q["prompt"], k=8)
            comp = comparison_json(q["prompt"], result["ranked"])
            brief_text = hero_brief(q["prompt"], result["ranked"], comp,
                                    use_hero_model=False)  # mini for cache speed
            briefs[q["id"]] = {
                "label": q["label"],
                "prompt": q["prompt"],
                "filters": result["filters"],
                "ranked_ids": [r["dataset_id"] for r in result["ranked"]],
                "comparison": comp,
                "brief": brief_text,
            }
        except Exception as e:  # noqa: BLE001
            print(f"  brief {q['id']} failed: {e}")
            briefs[q["id"]] = {
                "label": q["label"],
                "prompt": q["prompt"],
                "error": str(e),
            }

    (OUT_DIR / "cached_briefs.json").write_text(json.dumps(briefs, indent=2))
    print(f"\nWrote {len(briefs)} cached briefs -> {OUT_DIR / 'cached_briefs.json'}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--embed", action="store_true",
                        help="Also embed every abstract + precompute briefs.")
    parser.add_argument("--briefs-only", action="store_true",
                        help="Skip data + embedding regen; only precompute briefs.")
    args = parser.parse_args()

    if args.briefs_only:
        rows = json.loads((OUT_DIR / "datasets.json").read_text())
    else:
        rows = write_datasets()
        if args.embed:
            _embed_cache(rows)

    if args.embed or args.briefs_only:
        _precompute_briefs(rows)


if __name__ == "__main__":
    main()
