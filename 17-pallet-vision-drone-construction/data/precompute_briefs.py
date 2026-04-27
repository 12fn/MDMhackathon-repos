"""Pre-compute hero outputs for the 6 sample images.

Cache-first pattern: the Streamlit app reads from data/cached_briefs.json on
startup so the demo recording never sits on a spinner. The user can still
click "Regenerate" to fire a fresh live call (with watchdog).

Run after `python data/generate.py`:

    cd apps/17-pallet-vision
    python data/precompute_briefs.py
"""
from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent
APP_ROOT = ROOT.parent
sys.path.insert(0, str(APP_ROOT))

from src.vision import quantify, loadmaster_brief  # noqa: E402


def _read_platform_specs() -> str:
    csv_path = ROOT / "platform_specs.csv"
    with csv_path.open() as f:
        rows = list(csv.DictReader(f))
    lines = []
    for r in rows:
        lines.append(
            f"- {r['platform']} ({r['category']}): {r['pallets_463l']} 463L pallets, "
            f"max {r['max_payload_kg']} kg, cube {r['internal_cube_m3']} m^3. "
            f"{r['notes']}"
        )
    return "\n".join(lines)


def main() -> None:
    manifest_path = ROOT / "sample_manifest.json"
    if not manifest_path.exists():
        raise SystemExit("Run data/generate.py first.")
    manifest = json.loads(manifest_path.read_text())
    platform_specs_text = _read_platform_specs()

    cache: dict = {}
    for entry in manifest:
        img_path = APP_ROOT / entry["local_path"]
        print(f"[{entry['id']}] {img_path.name} — quantify…")
        with Image.open(img_path) as img:
            quant = quantify(img, scene_hint=entry["scene_type"], timeout=45.0)
        print(f"          → loadmaster brief…")
        brief_md = loadmaster_brief(quant, platform_specs_text, timeout=35.0)
        cache[entry["id"]] = {
            "quant": quant,
            "brief_md": brief_md,
            "scene_type": entry["scene_type"],
            "title": entry["title"],
        }

    out = ROOT / "cached_briefs.json"
    out.write_text(json.dumps(cache, indent=2))
    print(f"wrote {out} ({len(cache)} entries)")


if __name__ == "__main__":
    main()
