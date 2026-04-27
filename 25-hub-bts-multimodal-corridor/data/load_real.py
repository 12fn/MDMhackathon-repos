"""Real-data ingestion stub for HUB.

To plug in real Bureau of Transportation Statistics (BTS) NTAD shapefiles,
implement load_real() to read from the official BTS distribution and emit
the same shape as data/generate.py produces.

Required source layers (BTS — National Transportation Atlas Database):

  • NTAD :: North American Roads (line)
      https://geodata.bts.gov/datasets/usdot::north-american-roads
      → mode="road", clearance from `MIN_VERT_CLEAR`, weight from `WEIGHT_LMT`

  • NTAD :: North American Rail Lines (line)
      https://geodata.bts.gov/datasets/usdot::north-american-rail-lines
      → mode="rail", clearance plate (A-K), capacity from `CARS_PER_DAY`

  • NTAD :: Navigable Waterway Network Lines (line)
      https://geodata.bts.gov/datasets/usdot::navigable-waterway-network-lines
      → mode="waterway", channel depth from `CTRL_DEPTH`

  • NTAD :: Air Carrier Statistics (T-100 Segment) (table)
      https://www.transtats.bts.gov/Tables.asp?DB_ID=110
      → mode="air", capacity from monthly tons hauled

  • NTAD :: Strategic Highway Network (STRAHNET) overlay
      https://geodata.bts.gov/datasets/usdot::defense-strategic-highway-network

Required emitted fields per edge (matches data/generate.py):
  - a, b              : node ids matching nodes.json
  - mode              : "road" | "rail" | "waterway" | "air"
  - miles             : leg length
  - capacity_tpd      : design daily throughput (short-tons)
  - clearance_in      : minimum vertical clearance for the leg
  - weight_limit_lbs  : minimum weight class for the leg (gross)
  - bottleneck_named  : human-readable named choke point ("" if clean)

Then point src/app.py at it via env: REAL_DATA_PATH=/path/to/ntad-export-dir
"""
from __future__ import annotations

import os
from pathlib import Path


def load_real() -> dict:
    path = os.getenv("REAL_DATA_PATH")
    if not path:
        raise NotImplementedError(
            "REAL_DATA_PATH not set. Point it at a directory containing "
            "extracted BTS NTAD shapefiles. See module docstring for the "
            "required schema and the BTS source layer URLs."
        )
    base = Path(path)
    if not base.exists():
        raise FileNotFoundError(f"REAL_DATA_PATH does not exist: {path}")

    raise NotImplementedError(
        f"Real BTS NTAD ingest not yet wired. Drop shapefiles into {path} "
        f"and implement the geopandas → nodes/edges projection here. The "
        f"output schema must match data/generate.py exactly."
    )
