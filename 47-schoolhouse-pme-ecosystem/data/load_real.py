"""Real-data ingestion stub for SCHOOLHOUSE.

Documents the swap recipe for each of the four datasets the synthetic
data is shaped against. Until configured, src/app.py reads the files
produced by data/generate.py.

────────────────────────────────────────────────────────────────────────────
DATASET 1 — Moodle .mbz course exports
────────────────────────────────────────────────────────────────────────────
Source: a Moodle .mbz export of a USMC PME / PMOS course (e.g. Sergeants
Course, MOS 0411 Pipeline). Moodle is the LMS in use across many CDET /
MarineNet-adjacent learning programs.

A .mbz is a gzipped tar of XML files. The two we read:
  - course/course.xml             course metadata + structure
  - users.xml                      enrolled-user roster
  - activities/forum_*/posts.xml   forum threads + posts
  - activities/assign_*/grades.xml submission grades + feedback

Required emit shape (matches data/courses.json + data/forum_posts.jsonl):
  course = {
    "course_id": str, "name": str, "code": str, "tr_manual": str,
    "instructor": str, "students": [{student_id, name, rank, edipi_synth,
    profile}], "assignment": {id, title, type, rubric_xlsx, rubric_criteria}
  }

Then point src/app.py at it via env: REAL_MBZ_PATH=/path/to/export.mbz

────────────────────────────────────────────────────────────────────────────
DATASET 2 — Student Written Assignment Examples
────────────────────────────────────────────────────────────────────────────
Source: instructor-provided .docx + .xlsx rubric pairs from the Logistics
Principles Paper Course / Sergeants Course / 0411 Pipeline.

Shape on disk:
  REAL_ASSIGNMENTS_PATH/
    <course_id>/
      assignment.docx
      rubric.xlsx
      submissions/<student_id>.docx

Required: assignment.docx text + rubric criteria (criterion_id, label, weight,
0-5 anchors). Rubric .xlsx schema: columns [criterion_id, label, weight,
score_0_anchor, score_1_anchor, ..., score_5_anchor].

────────────────────────────────────────────────────────────────────────────
DATASET 3 — Xperience-10M egocentric
────────────────────────────────────────────────────────────────────────────
Source: Xperience-10M — large-scale egocentric multimodal dataset of
human experience for embodied AI / robot learning / world models.

Shape on disk:
  REAL_X10M_PATH/
    scenarios.json                (same schema as data/scenes_meta.json)
    frames/<scene_id>.png         one egocentric still per scenario

────────────────────────────────────────────────────────────────────────────
DATASET 4 — Military Object Detection (visual ID training corpus)
────────────────────────────────────────────────────────────────────────────
Source: Military Object Detection Dataset — labeled foreign and US
platform imagery (MBT, IFV, helicopter, fighter, UCAV, ship classes).

Shape on disk:
  REAL_MOD_PATH/
    images/<id>.jpg
    labels.csv  columns: id, image, ground_truth, country, type, key_features

Then point src/app.py at it via env:
  REAL_MBZ_PATH         (Moodle .mbz LMS export)
  REAL_ASSIGNMENTS_PATH (per-course assignment + rubric directory)
  REAL_X10M_PATH        (Xperience-10M curated subset)
  REAL_MOD_PATH         (Military Object Detection corpus)
"""
from __future__ import annotations

import os
from pathlib import Path


def load_real_lms() -> list[dict]:
    """Parse a Moodle .mbz export into the SCHOOLHOUSE course shape."""
    path = os.getenv("REAL_MBZ_PATH")
    if not path:
        raise NotImplementedError(
            "REAL_MBZ_PATH not set. See module docstring for required schema. "
            "Until configured, src/app.py reads data/courses.json (synthetic)."
        )
    # Real impl would: tar -xzf $REAL_MBZ_PATH; parse course.xml, users.xml,
    # forum_*/posts.xml, assign_*/grades.xml; emit the SCHOOLHOUSE course shape.
    raise NotImplementedError("Moodle .mbz parser stubbed — see docstring.")


def load_real_assignments() -> dict:
    path = os.getenv("REAL_ASSIGNMENTS_PATH")
    if not path:
        raise NotImplementedError(
            "REAL_ASSIGNMENTS_PATH not set. See module docstring."
        )
    raise NotImplementedError(".docx + .xlsx rubric ingester stubbed.")


def load_real_egocentric() -> list[dict]:
    path = os.getenv("REAL_X10M_PATH")
    if not path:
        raise NotImplementedError(
            "REAL_X10M_PATH not set. See module docstring."
        )
    import json
    root = Path(path)
    scenarios = json.loads((root / "scenarios.json").read_text())
    missing = [s["id"] for s in scenarios
               if not (root / "frames" / f"{s['id']}.png").exists()]
    if missing:
        raise FileNotFoundError(f"Missing frames for scenarios: {missing}")
    return scenarios


def load_real_visual_id() -> list[dict]:
    path = os.getenv("REAL_MOD_PATH")
    if not path:
        raise NotImplementedError(
            "REAL_MOD_PATH not set. See module docstring."
        )
    import csv
    root = Path(path)
    out: list[dict] = []
    with (root / "labels.csv").open() as f:
        for row in csv.DictReader(f):
            out.append({
                "id": row["id"],
                "image": row["image"],
                "ground_truth": row["ground_truth"],
                "country": row["country"],
                "type": row["type"],
                "key_features": row["key_features"],
            })
    return out
