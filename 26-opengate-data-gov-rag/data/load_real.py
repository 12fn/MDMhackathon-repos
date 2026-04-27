"""Real-data ingestion stub for OPENGATE.

To plug in the live data.gov catalog, implement load_real() to query the CKAN
package_search endpoint and emit the same shape as data/generate.py produces.

  Endpoint:   https://catalog.data.gov/api/3/action/package_search
  Auth:       none required (public)
  Pagination: rows= up to 1000 per request; start= offset for paging
  Total:      300,000+ packages across every federal agency

Required output fields (match generate.py exactly so src/rag.py needs no edit):
  - dataset_id            (str)   stable CKAN package id
  - title                 (str)
  - abstract              (str)   CKAN `notes` field
  - agency                (str)   short name (NOAA, NASA, FEMA, ...)
  - agency_full           (str)   long name (organization.title in CKAN)
  - sub_office            (str)   organization.name or first author
  - tags                  (list[str])
  - last_updated          (str)   ISO date (CKAN `metadata_modified`)
  - format                (str)   primary resource format (NetCDF, CSV, ...)
  - license               (str)   CKAN `license_title`
  - record_count_estimate (int)   best-effort: count rows in primary CSV, else 0
  - refresh_cadence       (str)   CKAN `frequency` extra, else "unknown"
  - url                   (str)   `https://catalog.data.gov/dataset/{name}`
  - topic_seed            (str)   first tag, used for synth-style topic hint
  - region_seed           (str)   spatial extent if present, else "global"

Then run:
  REAL_DATA_PATH=$(pwd)/datasets_real.json python data/generate.py --embed --briefs-only

This rebuilds embeddings.npy and cached_briefs.json against the live catalog.
"""
from __future__ import annotations

import json
import os
from datetime import date
from pathlib import Path

CKAN_BASE = "https://catalog.data.gov/api/3/action/package_search"


def _to_short_agency(org_name: str) -> str:
    """Map CKAN organization name to a short agency code OPENGATE uses."""
    org_name = (org_name or "").lower()
    matches = {
        "noaa": "NOAA", "nasa": "NASA", "fema": "FEMA",
        "transportation": "DOT", "defense": "DOD", "agriculture": "USDA",
        "geological": "USGS", "energy-information": "EIA",
        "homeland": "DHS", "state-gov": "State", "usaid": "USAID",
        "census": "Census", "epa": "EPA", "veterans": "VA", "labor": "BLS",
    }
    for k, v in matches.items():
        if k in org_name:
            return v
    return (org_name.split("-")[0] or "OTHER").upper()[:6]


def _normalize_package(pkg: dict) -> dict:
    org = pkg.get("organization") or {}
    resources = pkg.get("resources") or []
    tags = [t.get("name", "") for t in (pkg.get("tags") or [])]
    extras = {e.get("key"): e.get("value") for e in (pkg.get("extras") or [])}
    primary_fmt = next(
        (r.get("format", "").upper() for r in resources if r.get("format")),
        "UNKNOWN",
    )
    return {
        "dataset_id": pkg.get("id") or pkg.get("name", "DG-UNKNOWN"),
        "title": pkg.get("title", ""),
        "abstract": pkg.get("notes", "") or "",
        "agency": _to_short_agency(org.get("name", "")),
        "agency_full": org.get("title", "") or pkg.get("author", ""),
        "sub_office": pkg.get("author") or org.get("name", ""),
        "tags": tags,
        "last_updated": (pkg.get("metadata_modified") or date.today().isoformat())[:10],
        "format": primary_fmt,
        "license": pkg.get("license_title", "U.S. Government Work (Public Domain)"),
        "record_count_estimate": 0,
        "refresh_cadence": extras.get("frequency", "unknown"),
        "url": f"https://catalog.data.gov/dataset/{pkg.get('name', '')}",
        "topic_seed": tags[0] if tags else "general",
        "region_seed": extras.get("spatial_text", "global"),
    }


def load_real(limit: int = 200, query: str = "*:*") -> list[dict]:
    """Pull `limit` packages from the live CKAN endpoint.

    Args:
        limit: total packages to ingest (CKAN caps `rows` at 1000 per call).
        query: CKAN Solr query; default is everything.

    Returns: list of dicts in the shape data/generate.py emits.

    Set REAL_DATA_PATH to write the result to disk; otherwise returned in-memory.
    """
    try:
        import requests  # type: ignore
    except ImportError as e:
        raise NotImplementedError(
            "requests not installed. `pip install requests` to enable live "
            "data.gov ingestion via load_real()."
        ) from e

    rows: list[dict] = []
    page_size = min(limit, 1000)
    start = 0
    while len(rows) < limit:
        params = {"q": query, "rows": page_size, "start": start}
        resp = requests.get(CKAN_BASE, params=params, timeout=30)
        resp.raise_for_status()
        results = (resp.json().get("result") or {}).get("results") or []
        if not results:
            break
        rows.extend(_normalize_package(p) for p in results)
        start += page_size
        if len(results) < page_size:
            break
    rows = rows[:limit]

    out_path = os.getenv("REAL_DATA_PATH")
    if out_path:
        Path(out_path).write_text(json.dumps(rows, indent=2))
        print(f"Wrote {len(rows)} real datasets -> {out_path}")
    return rows


if __name__ == "__main__":
    out = load_real(limit=int(os.getenv("LIMIT", "200")))
    print(f"Pulled {len(out)} packages from {CKAN_BASE}")
