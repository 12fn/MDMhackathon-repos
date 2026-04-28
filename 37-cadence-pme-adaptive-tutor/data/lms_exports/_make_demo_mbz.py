"""Generate synthetic Moodle 4.5 .mbz backup files for the CADENCE demo
courses.

A Moodle .mbz file is a gzipped tar archive (.tar.gz) containing at minimum:
  - moodle_backup.xml          (top-level backup metadata)
  - course/course.xml          (course metadata)
  - activities/                (activity-level dumps; we stub a forum)
  - files.xml                  (file manifest, empty here)

Run:
    python apps/37-cadence/data/lms_exports/_make_demo_mbz.py

This is for demonstration of the end-to-end .mbz schema only — real exports
should be dropped here per data/load_real.py and the README.
"""
from __future__ import annotations

import io
import json
import tarfile
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
APP_ROOT = HERE.parent.parent
COURSES_JSON = APP_ROOT / "data" / "courses.json"


def _moodle_backup_xml(course_id: str, course_name: str, code: str,
                        tr_manual: str, tr_codes: list[str]) -> str:
    now = int(datetime.now(timezone.utc).timestamp())
    tr_codes_str = ",".join(tr_codes)
    # Minimal Moodle 4.5 backup descriptor — enough for a parser to identify
    # the course, version, and a single forum activity.
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<moodle_backup>
  <information>
    <name>{course_id}.mbz</name>
    <moodle_version>2024100100</moodle_version>
    <moodle_release>4.5</moodle_release>
    <backup_version>2024100100</backup_version>
    <backup_release>4.5</backup_release>
    <backup_date>{now}</backup_date>
    <mnet_remoteusers>0</mnet_remoteusers>
    <original_wwwroot>https://lms.usmc.mil.synthetic</original_wwwroot>
    <original_site_identifier_hash>cadence-synth-001</original_site_identifier_hash>
    <original_course_id>{abs(hash(course_id)) % 10000}</original_course_id>
    <original_course_format>topics</original_course_format>
    <original_course_fullname>{course_name}</original_course_fullname>
    <original_course_shortname>{code}</original_course_shortname>
    <original_course_startdate>{now}</original_course_startdate>
    <details>
      <detail backup_id="cadence-synth-{course_id}">
        <type>course</type>
        <format>moodle2</format>
        <interactive>0</interactive>
        <mode>10</mode>
        <execution>1</execution>
      </detail>
    </details>
    <contents>
      <course>
        <courseid>{abs(hash(course_id)) % 10000}</courseid>
        <title>{course_name}</title>
        <directory>course</directory>
      </course>
      <activities>
        <activity>
          <moduleid>1</moduleid>
          <sectionid>1</sectionid>
          <modulename>forum</modulename>
          <title>Discussion forum (synthetic)</title>
          <directory>activities/forum_1</directory>
        </activity>
      </activities>
      <settings>
        <setting>
          <level>root</level>
          <name>tr_manual</name>
          <value>{tr_manual}</value>
        </setting>
        <setting>
          <level>root</level>
          <name>tr_event_codes</name>
          <value>{tr_codes_str}</value>
        </setting>
        <setting>
          <level>root</level>
          <name>records_governance</name>
          <value>Privacy Act of 1974 (5 U.S.C. 552a) and DoDI 1322.35 Military Education Records</value>
        </setting>
      </settings>
    </contents>
  </information>
</moodle_backup>
"""


def _course_xml(course_id: str, course_name: str, code: str) -> str:
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<course id="{abs(hash(course_id)) % 10000}" contextid="1">
  <shortname>{code}</shortname>
  <fullname>{course_name}</fullname>
  <idnumber>{course_id}</idnumber>
  <summary>Synthetic CADENCE demo course (.mbz schema sample).</summary>
  <format>topics</format>
  <visible>1</visible>
  <lang>en</lang>
</course>
"""


def _forum_xml() -> str:
    return """<?xml version="1.0" encoding="UTF-8"?>
<activity id="1" moduleid="1" modulename="forum" contextid="1">
  <forum id="1">
    <name>Discussion forum (synthetic)</name>
    <intro>Synthetic discussion forum for CADENCE schema demonstration.</intro>
    <type>general</type>
    <discussions>
      <discussion id="1">
        <name>Welcome — synthetic discussion</name>
        <userid>0</userid>
        <posts>
          <post id="1">
            <userid>0</userid>
            <subject>Welcome</subject>
            <message>Synthetic post; no PII. See data/load_real.py for the real-data plug-in path.</message>
          </post>
        </posts>
      </discussion>
    </discussions>
  </forum>
</activity>
"""


def _files_xml() -> str:
    return '<?xml version="1.0" encoding="UTF-8"?>\n<files></files>\n'


def build_one(course: dict) -> Path:
    cid = course["id"]
    out = HERE / f"{cid}.mbz"
    members = {
        "moodle_backup.xml": _moodle_backup_xml(
            cid, course["name"], course["code"],
            course.get("tr_manual", ""),
            course.get("tr_event_codes", []),
        ),
        "course/course.xml": _course_xml(cid, course["name"], course["code"]),
        "activities/forum_1/forum.xml": _forum_xml(),
        "files.xml": _files_xml(),
        "README_SYNTHETIC.txt": (
            "This is a SYNTHETIC Moodle 4.5 .mbz file produced by\n"
            "apps/37-cadence/data/lms_exports/_make_demo_mbz.py for schema\n"
            "demonstration. It contains no PII. Real .mbz exports go here at\n"
            "deployment time per data/load_real.py.\n\n"
            f"Course: {course['name']} ({course['code']})\n"
            f"T&R / PME authority: {course.get('tr_manual','')}\n"
            f"T&R event codes: {', '.join(course.get('tr_event_codes', []))}\n"
            "Records governance: Privacy Act of 1974 (5 U.S.C. § 552a) and "
            "DoDI 1322.35 \"Military Education Records\".\n"
        ),
    }
    with tarfile.open(out, "w:gz") as tar:
        for name, body in members.items():
            data = body.encode("utf-8")
            info = tarfile.TarInfo(name=name)
            info.size = len(data)
            info.mtime = int(datetime.now(timezone.utc).timestamp())
            tar.addfile(info, io.BytesIO(data))
    return out


def main() -> None:
    courses = json.loads(COURSES_JSON.read_text())["courses"]
    # Generate two demo .mbz files (one Logistics, one Sergeants Course)
    targets = [c for c in courses if c["id"] in
               ("log_principles_paper", "sergeants_course")]
    for c in targets:
        out = build_one(c)
        print(f"  wrote {out.relative_to(APP_ROOT.parent.parent)}  ({out.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
