# LEARN — Learning Intelligence Dashboard (LID)

> *From Context to Action.* — Cognitive-development analytics for USMC PME / PMOS / Schoolhouses, on-prem, audit-traceable.

**Codename:** LEARN  ·  **Port:** 3032  ·  **Stack:** Streamlit (mono)

## Pitch
Marine training pipelines — Infantry Officer Course (IOC, NAVMC 3500.18 Infantry T&R), PMOS pipelines (e.g. 0411 Logistics under NAVMC 3500.58, SIGINT 26xx under NAVMC 3500.44), and resident PME courses such as the **Sergeants Course** at the SNCO Academy MCB Quantico (E-5 SGTs) — distinct from the **Squad Leader Course** taught at SOI under NAVMC 3500.18 — generate huge volumes of learning artifacts (discussion forums, written assignments, training logs, AAR). Instructors and the cognitive-development chain have no scalable way to answer: **to what extent is learning actually occurring?** LEARN reads every post and every submission and produces structured competency evidence anchored to the relevant NAVMC 3500-series T&R Manual (or the MCO 1553.4B / DoDI 1322.35 PME framework for resident PME), plus a class-level Instructor's Competency Brief — with a SHA-256-chained audit log so every assessment is replayable. Records governance: **Privacy Act of 1974 (5 U.S.C. § 552a)** and **DoDI 1322.35 'Military Education Records'** — NOT FERPA (FERPA is K-12 / civilian higher-ed; Marines under active military training are governed by the Privacy Act + DoDI 1322.35).

## LOGCOM use case (verbatim)
> Learning Intelligence Dashboard (LID) — AI analyzes learning artifacts (discussion forums, assignments, training logs, AAR) to produce structured competency evidence aligned with USMC training standards. Answers: To what extent is learning occurring? Are Marines demonstrating required competencies? Are instructors providing effective training? Audit trails for transparency.

## T&R Manual anchoring (per cohort)
Every cohort the dashboard ships with is anchored to its specific governing T&R Manual or PME framework so the brief can name the exact event-set its competency calls map to:

| Cohort | Schoolhouse | Governing T&R / PME framework |
|---|---|---|
| IOC Bravo 26-1 (`ioc_b261`) | IOC, TBS / The Basic School, MCB Quantico VA | **NAVMC 3500.18 — Infantry Training & Readiness Manual** (events e.g. INF-MAN-1001, INF-OPS-2001, INF-PAT-2002) |
| PMOS 0411 Maintenance Mgmt 26-04 (`pmos_0411_log`) | MCCSSS, Camp Johnson NC | **NAVMC 3500.58 — Logistics Training & Readiness Manual** (events e.g. LOG-MAINT-1001, LOG-MAINT-2003, LOG-DIST-2001) |
| Sergeants Course 2-26 (`sgts_course`) | **SNCO Academy, MCB Quantico VA** (resident PME, E-5 SGTs) | **MCO 1553.4B (PME Framework) and DoDI 1322.35 'Military Education'** — Sergeants Course is **distinct** from the Squad Leader Course (which is taught at SOI under the Infantry T&R, NAVMC 3500.18). Do not conflate. |

A SIGINT pipeline cohort would map to **NAVMC 3500.44 — Signals Intelligence T&R Manual**.

## Records governance
Every assessment LEARN writes is a Military Education Record. Governance:
- **Privacy Act of 1974 (5 U.S.C. § 552a)** — system-of-records authority; PII handled in-environment only.
- **DoDI 1322.35 'Military Education Records'** — DoD-wide military education records policy.

FERPA does not apply: FERPA covers K-12 / civilian higher-ed students, not active-duty Marines under military training.

## Hero AI move (cache-first, three-stage agent)

1. **Per-student `chat_json`** — every student's forum posts + assignment submissions get scored against the 4-axis competency rubric (critical_thinking, communication, doctrinal_knowledge, problem_solving), with cognitive depth on Bloom's taxonomy, growth indicators, remediation recommendations, intervention flag, and confidence — strict structured-output JSON, audit-grade.

2. **Cohort `chat_json`** — roll-up: course health (GREEN/AMBER/RED), instructor-effectiveness signal, assignment-effectiveness ranking.

3. **Hero `chat`** ("gpt-5.4", 35s wall-clock cap) — narrative *Instructor's Competency Brief* (5-paragraph format: cohort competency map → top performers → intervention list → assignment effectiveness → recommended curriculum adjustments). Cache-first; baseline-deterministic fallback if the hero call doesn't land in time.

Every assessment append-only logged to `audit_logs/learn_audit.jsonl` with a SHA-256 chain.

## Run it (local dev)

```bash
# from repo root, with .venv activated
cd apps/32-learn
python data/generate.py            # synth course + 200 posts + cached briefs
streamlit run src/app.py \
  --server.port 3032 \
  --server.headless true \
  --server.runOnSave false \
  --server.fileWatcherType none \
  --browser.gatherUsageStats false
# open http://localhost:3032
```

## Demo it
Click **GENERATE INSTRUCTORS BRIEF** in the top-left. The cohort heatmap is already populated from the deterministic baseline; clicking GENERATE fires the live three-stage agent (cache-first, so the Brief returns instantly on repeat plays).

Drill into any student via the **Student** picker. Inspect the SHA-256 audit chain at the bottom of the page.

## Real-data swap

`data/load_real.py` documents the Moodle SQL/CSV export schema (mdl_user / mdl_assign / mdl_assign_submission / mdl_forum_posts) and the LEARN-shape JSON the app expects.

```bash
# Once you have a Moodle export massaged into LEARN-shape JSON:
export REAL_DATA_PATH=/path/to/moodle_export.json
streamlit run src/app.py --server.port 3032 ...
```

## Files

```
apps/32-learn/
├── README.md
├── PRD.md
├── data/
│   ├── generate.py             # rerunnable synth (seed=1776) + precompute_briefs()
│   ├── load_real.py            # Moodle ingest stub
│   ├── course.json             # course meta + 18 students + 6 assignments + 30 threads
│   ├── forum_posts.jsonl       # 200 synthetic posts of varied cognitive depth
│   ├── assignments.jsonl       # ~100 submissions
│   └── cached_briefs.json      # 3 pre-computed cohort scenarios (cache-first)
├── src/
│   ├── app.py                  # Streamlit (port 3032)
│   ├── agent.py                # 3-stage cache-first pipeline + audit chain
│   └── heatmap.py              # Plotly cohort heatmap + assignment bars
├── audit_logs/
│   └── learn_audit.jsonl       # SHA-256-chained append-only log
├── tests/record-demo.spec.ts   # Playwright recorder
├── playwright.config.ts
├── package.json
├── demo-script.md              # narrator script
├── demo-script.json            # cue timeline emitted by Playwright
├── videos/learn-demo.mp4       # final captioned demo (≤90s)
├── requirements.txt
├── .env.example
└── STATUS.txt                  # building | testing | recording | done
```

## Scoring tie-back

- **Mission Impact (30%)** — verbatim LOGCOM-published Learning Intelligence Dashboard use case.
- **Technical Innovation (25%)** — three-stage agentic pipeline (per-student JSON → cohort JSON → hero narrative), cache-first with deterministic fallback under wall-clock timeout.
- **Usability & Design (20%)** — Kamiwaza dark theme, Plotly cohort heatmap as the hero visual, 3-click drill-down, captioned 90s demo.
- **Security & Sustainability (15%)** — On-prem via Kamiwaza Stack (`KAMIWAZA_BASE_URL` flips provider). Military Education Records governance under the **Privacy Act of 1974 (5 U.S.C. § 552a)** and **DoDI 1322.35 'Military Education Records'** (NOT FERPA — FERPA does not apply to active-duty military training): nothing leaves the accredited environment. Append-only chained audit log.
- **Team Collaboration (10%)** — Modular agent / app / heatmap split, README documents reproducible synth (seed 1776), real-data swap recipe in `data/load_real.py`.

---

**Powered by Kamiwaza.**  IL5/IL6 ready · NIPR/SIPR/JWICS deployable · DDIL-tolerant.
