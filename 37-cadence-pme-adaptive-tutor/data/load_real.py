"""Real-data ingestion stub for CADENCE — Adaptive PME Tutor.

CADENCE plugs into TWO real LOGCOM portal datasets (both NEW for the
2026 LOGCOM AI Forum Hackathon):

  1. "LMS Course data sets"
     - Real USMC .mbz Moodle 4.5+ exports (anonymized users, course logs,
       discussions, structure)
     - Drop the .mbz files in: data/lms_exports/
     - Point env: REAL_LMS_EXPORT_DIR=/abs/path/to/.mbz/dir
     - Use the `moodle-mbz-parser` pip package (or unzip + parse the
       moodle_backup.xml + activities/discussion/*.xml manually)

  2. "Student Written Assignment Examples"
     - PDF assignments + xlsx rubric + docx instructions + sample submissions
     - Drop the directory in: data/student_artifacts/
     - Point env: REAL_STUDENT_ARTIFACTS_DIR=/abs/path/to/dir
     - Expected file pattern:
         <course_id>/instructions.docx
         <course_id>/rubric.xlsx
         <course_id>/<student_id>/submission.docx (or .pdf)

Both datasets cited verbatim from the LOGCOM portal.

Required output shape (mirrors data/generate.generate(0)):

    courses.json          {"courses": [{id, name, code, school, ...}, ...]}
    students.json         {"students": [{student_id, name, rank, primary_course_id,
                                          submission_history, forum_posts}, ...]}
    doctrine_index.json   {"<CITATION>": {"title": str, "section_abstracts": dict}}

PII handling (Privacy Act of 1974 (5 U.S.C. § 552a) and DoDI 1322.35
"Military Education Records" — NOT FERPA):
    - Replace real names with rank+last
    - Strip email/phone/SSN-shaped tokens
    - Surrogate-hash any EDIPI before emitting

Author: CADENCE team
"""
from __future__ import annotations

import json
import os
from pathlib import Path


def load_real_lms() -> dict:
    """Read .mbz Moodle exports from REAL_LMS_EXPORT_DIR and emit a CADENCE-
    shape course/student bundle.

    Implementation outline:
        1. For each .mbz under REAL_LMS_EXPORT_DIR, unzip to a tempdir.
        2. Parse moodle_backup.xml → course metadata (id, name, code).
        3. Parse activities/forum_*/discussion.xml → forum_posts (per student).
        4. Parse activities/assign_*/submissions.xml → submission_history.
        5. Anonymize: rank + last only; surrogate-hash any EDIPI / email.

    Returns the same shape as data/generate.generate() emits.
    """
    raw = os.getenv("REAL_LMS_EXPORT_DIR")
    if not raw:
        raise NotImplementedError(
            "REAL_LMS_EXPORT_DIR not set. Drop your .mbz Moodle 4.5+ exports in "
            "data/lms_exports/ and point this env var at it. See module "
            "docstring for the full mapping."
        )
    p = Path(raw)
    if not p.exists():
        raise FileNotFoundError(f"REAL_LMS_EXPORT_DIR does not exist: {p}")
    raise NotImplementedError(
        "Hook up `moodle-mbz-parser` here (pip install moodle-mbz-parser) or "
        "implement the manual unzip + XML parse described in the docstring."
    )


def load_real_student_artifacts() -> dict:
    """Read PDF assignments + xlsx rubrics + docx submissions from
    REAL_STUDENT_ARTIFACTS_DIR and emit per-course assignment + rubric +
    submission text.

    Expected layout under REAL_STUDENT_ARTIFACTS_DIR:
        <course_id>/instructions.docx     (or .pdf)
        <course_id>/rubric.xlsx
        <course_id>/<student_id>/submission.docx
    """
    raw = os.getenv("REAL_STUDENT_ARTIFACTS_DIR")
    if not raw:
        raise NotImplementedError(
            "REAL_STUDENT_ARTIFACTS_DIR not set. Drop the LOGCOM-portal "
            "Student Written Assignment Examples bundle in "
            "data/student_artifacts/ and point this env var at it."
        )
    p = Path(raw)
    if not p.exists():
        raise FileNotFoundError(f"REAL_STUDENT_ARTIFACTS_DIR does not exist: {p}")
    raise NotImplementedError(
        "Implement docx/pdf/xlsx parsing here. The CADENCE app already "
        "knows how to read .docx via python-docx (see src/extract.py). "
        "Use openpyxl for the rubrics, pdfplumber for any PDFs."
    )


def load_real() -> dict:
    """Convenience entry-point — loads BOTH datasets if their env vars are
    set; otherwise falls back to the synthetic generator output."""
    if os.getenv("REAL_LMS_EXPORT_DIR") and os.getenv("REAL_STUDENT_ARTIFACTS_DIR"):
        lms = load_real_lms()
        artifacts = load_real_student_artifacts()
        return {"lms": lms, "artifacts": artifacts}
    raise NotImplementedError(
        "Neither REAL_LMS_EXPORT_DIR nor REAL_STUDENT_ARTIFACTS_DIR set. "
        "Run `python data/generate.py` to use the synthetic dataset."
    )
