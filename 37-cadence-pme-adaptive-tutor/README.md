# CADENCE — Adaptive PME Tutor for Marines

**Codename:** CADENCE  ·  **Port:** 3037  ·  **Wave 2 / app 37**

Student-facing 1:1 companion to LEARN (instructor-facing). A Marine taking a
PME or PMOS course logs in, CADENCE reads their actual `.docx` submission +
last 10 forum posts + the published rubric, then writes a **personalized
7-day Adaptive Study Plan** — doctrine-cite homework, rubric-aligned writing
tips, and a Privacy-Act-and-DoDI-1322.35 audit footer; full audit chain in
`data/audit_logs/`.

## Pitch

> *One-size-fits-all PME isn't working.* The Marine taking the course needs
> a tutor who has read every one of their forum posts and every assignment
> they've turned in. CADENCE does that for every Marine in the schoolhouse,
> on-prem, behind the SCIF wall.

## Records governance

CADENCE assessments are **Military Education Records**.

- **Privacy Act of 1974 (5 U.S.C. § 552a)** — system-of-records authority;
  PII handled in-environment only.
- **DoDI 1322.35 "Military Education Records"** — DoD-wide military
  education records policy.
- **NOT FERPA.** FERPA (20 U.S.C. § 1232g) governs K-12 / civilian higher
  education and **does not apply** to active-duty military training. CADENCE
  never claims FERPA compliance.

## Demo courses & T&R / PME authority

| Course | School | T&R / PME authority | Sample event codes |
|---|---|---|---|
| Logistics Principles Paper (`log_principles_paper`) | MAGTF Logistics Officers Course | **NAVMC 3500.58 — Logistics Training & Readiness Manual** | LOG-DIST-2001, LOG-PLAN-2003, LOG-SUS-3001 |
| Sergeants Course (Resident, SNCO Academy) (`sergeants_course`) | Staff NCO Academy, MCB Quantico VA | **MCO 1553.4B (PME Framework) and DoDI 1322.35 "Military Education"** — anchored to NAVMC 3500.18 Infantry T&R for tactical events | INF-MAN-1001, INF-OPS-2001, INF-PAT-2002 |
| MOS 0411 Sustainment Pipeline (`mos_0411_sustainment`) | Marine Corps Logistics Operations Group | **NAVMC 3500.58 — Logistics Training & Readiness Manual** | LOG-MAINT-1001, LOG-MAINT-2003, LOG-DIST-2001 |

Note: the legacy "Squad Leader Distance Learning" PME has been folded into
the resident **Sergeants Course** (E-5) and **Corporals Course** (E-4)
pathways. SQDL is not framed as a current standalone NCO PME requirement.

## Hero AI move — three-stage adaptive tutoring

1. **Stage 1 — ingest.** Marine selects a course; we read their submission
   `.docx` (via `python-docx`) + their last 10 forum posts.
2. **Stage 2 — `chat_json` analysis.** Returns the structured-output schema
   (knowledge gaps, doctrine to review, writing competency 0-5, critical
   thinking indicators, 3 tailored study questions, peer learning
   suggestions, estimated competency alignment %), with the course's
   T&R event codes available for citation.
3. **Stage 3 — hero `chat`.** A Kamiwaza-deployed model writes the 1-page
   Adaptive Study Plan with daily learning targets for the next 7 days,
   referencing the course's NAVMC 3500-series T&R Manual / MCO 1553.4B
   PME framework events. Wall-clock-capped at 35s with a deterministic
   baseline fallback so the demo never spinner-locks (per AGENT_BRIEF_V2
   §B). Cache-first via `data/cached_briefs.json`.

## Run

```bash
cd apps/37-cadence
pip install -r requirements.txt
python data/generate.py    # writes courses.json, students.json, doctrine_index.json,
                           # cached_briefs.json, assignments/*.docx, submissions/*.docx,
                           # rubrics/*.xlsx
streamlit run src/app.py \
  --server.port 3037 \
  --server.headless true \
  --server.runOnSave false \
  --server.fileWatcherType none \
  --browser.gatherUsageStats false
```

Then open http://localhost:3037.

## Real-data plug-in

CADENCE is a hackathon prototype; it ships with synthetic Marines but plugs
into BOTH NEW LOGCOM-portal datasets:

1. **LMS Course data sets** — real USMC `.mbz` Moodle 4.5+ exports
   (anonymized users, course logs, discussions, structure).
   `data/lms_exports/` ships two **synthetic** `.mbz` files
   (`log_principles_paper.mbz`, `sergeants_course.mbz`) — each is a real
   `.tar.gz` containing `moodle_backup.xml`, `course/course.xml`, an
   activities forum stub, `files.xml`, and a `README_SYNTHETIC.txt`. They
   demonstrate the schema end-to-end. To regenerate, run
   `python data/lms_exports/_make_demo_mbz.py`. Drop real `.mbz` files
   in this directory at deployment time and set `REAL_LMS_EXPORT_DIR`.
2. **Student Written Assignment Examples** — PDF assignments + xlsx rubric
   + docx instructions + sample submissions.
   Drop the bundle in `data/student_artifacts/`. Set `REAL_STUDENT_ARTIFACTS_DIR`.

See `data/load_real.py` for the full schema mapping. The "Logistics
Principles Paper" demo course directly mirrors the second dataset's shape.

## File map

```
apps/37-cadence/
├── README.md                        # this file
├── PRD.md                           # spec + scoring tie-back
├── demo-script.md                   # narrator script for the 90s video
├── demo-script.json                 # cue timeline (emitted by Playwright)
├── data/
│   ├── generate.py                  # synth + precompute_briefs() + baseline fns
│   ├── load_real.py                 # real-data ingestion stubs
│   ├── courses.json                 # courses + tr_manual + tr_event_codes
│   ├── students.json
│   ├── doctrine_index.json          # 30 keyed-by-citation entries
│   ├── cached_briefs.json           # 3 student-course combos pre-analyzed
│   ├── assignments/*.docx
│   ├── submissions/*.docx
│   ├── rubrics/*.xlsx
│   ├── lms_exports/                 # synthetic .mbz files + _make_demo_mbz.py
│   ├── student_artifacts/           # drop real bundle here
│   └── audit_logs/cadence_audit.jsonl
├── src/
│   ├── app.py                       # Streamlit (3037)
│   ├── agent.py                     # 3-stage cache-first pipeline
│   ├── audit.py                     # SHA-256 chain
│   └── extract.py                   # python-docx + openpyxl readers
├── tests/record-demo.spec.ts        # Playwright recorder
├── playwright.config.ts
├── videos/cadence-demo.mp4          # captioned 90s demo
├── requirements.txt
├── .env.example
└── STATUS.txt
```

## How it differs from LEARN (sibling app 32)

| Axis | LEARN (instructor-facing) | **CADENCE (student-facing)** |
|---|---|---|
| Audience | Instructor / cognitive-development cell | The individual Marine |
| Output | Cohort competency map + Instructor's Brief | 1:1 Adaptive Study Plan |
| Data shape | 18-student cohort, 200 posts, 100 submissions | 1 Marine, their .docx, their 10 posts |
| Hero brief | "Who needs intervention?" | "What do **I** read tomorrow?" |
| Compliance pitch | Privacy Act of 1974 + DoDI 1322.35 audit-grade competency calls | Privacy Act of 1974 + DoDI 1322.35 personal Military Education Records |

Both share the SHA-256 audit-chain pattern (`src/audit.py`) and the
cache-first hero LLM pattern.

## Powered by Kamiwaza

Tagline: *From Context to Action.*

Compliance posture: IL5/IL6 ready · NIPR/SIPR/JWICS deployable · 100% data
containment — student data never leaves the accredited environment. Records
governance: **Privacy Act of 1974 (5 U.S.C. § 552a) and DoDI 1322.35
"Military Education Records"** — NOT FERPA.
