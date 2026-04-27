"""Real-data ingestion stub for LEARN — Learning Intelligence Dashboard (LID).

To plug in a real Moodle course export, implement load_real() to read from a
Moodle SQL/CSV export (or the Moodle Web Services REST API) and emit the same
shape as data/generate.py produces.

Required Moodle tables / columns (mapped to LEARN shape):

  Source: mdl_user                       -> students[].name, students[].rank, students[].edipi
    - id          -> student_id (prefix 'S')
    - firstname / lastname -> name
    - profile_field_rank   -> rank (Marine rank)
    - idnumber             -> edipi (or synthetic surrogate)

  Source: mdl_course + mdl_course_categories -> course
    - fullname    -> course.name
    - shortname   -> course.code

  Source: mdl_assign                     -> assignments[]
    - id, name, intro -> id, name, rubric (parse rubric tag from intro/grade outcome)

  Source: mdl_assign_submission + mdl_assignsubmission_onlinetext + mdl_assign_grades
    -> submissions[]
    - userid                -> student_id
    - assignment            -> assignment_id
    - onlinetext            -> excerpt (first ~500 chars, redacted PII)
    - grade                 -> grade
    - timemodified > duedate -> late (bool)
    - timemodified          -> submitted_at

  Source: mdl_forum_discussions + mdl_forum_posts -> forum_threads, forum_posts
    - subject               -> thread name
    - userid                -> student_id
    - message               -> body (HTML-stripped)
    - created               -> ts
    - depth label is computed locally (LLM step 1) — not in Moodle

PII handling (FERPA-equivalent for training records):
  - Replace real names with rank+last for display
  - Redact any email/phone/SSN-shaped strings before emitting
  - DO NOT emit raw EDIPI or SSN; surrogate-hash them

Then point src/app.py at the real data via env:
    REAL_DATA_PATH=/path/to/moodle_export.json   (LEARN-shape JSON)
    REAL_DATA_SQLITE=/path/to/moodle.sqlite      (raw Moodle DB; we'll dispatch on extension)

Author: LEARN team
"""
from __future__ import annotations

import json
import os
from pathlib import Path


def load_real() -> dict:
    """Return a LEARN-shape dict matching data/generate.generate(0) output."""
    path = os.getenv("REAL_DATA_PATH")
    sqlite_path = os.getenv("REAL_DATA_SQLITE")
    if not path and not sqlite_path:
        raise NotImplementedError(
            "Neither REAL_DATA_PATH nor REAL_DATA_SQLITE set. "
            "See module docstring for required Moodle schema mapping."
        )
    if path:
        p = Path(path)
        if not p.exists():
            raise FileNotFoundError(f"REAL_DATA_PATH does not exist: {p}")
        return json.loads(p.read_text())
    raise NotImplementedError(
        "SQLite Moodle ingest not yet implemented. Export to JSON via the "
        "Moodle 'mod_assign_get_submissions' + 'mod_forum_get_forum_discussions_paginated' "
        "Web Services calls and stitch into the LEARN shape, then set REAL_DATA_PATH."
    )
