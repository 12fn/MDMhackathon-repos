# LEARN — Learning Intelligence Dashboard (LID)

> *From Context to Action.* — Cognitive-development analytics for USMC PME / PMOS / Schoolhouses, on-prem, audit-traceable.

**Codename:** LEARN  ·  **Port:** 3032  ·  **Stack:** Streamlit (mono)

## Pitch
Marine training pipelines (Infantry Officer Course, PMOS pipelines, PME like Squad Leader School) generate huge volumes of learning artifacts — discussion forums, written assignments, training logs, AAR — but instructors and the cognitive-development chain have no scalable way to answer: **to what extent is learning actually occurring?** LEARN reads every post and every submission and produces structured competency evidence aligned to USMC training standards, plus a class-level Instructor's Competency Brief — with a SHA-256-chained audit log so every assessment is replayable.

## LOGCOM use case (verbatim)
> Learning Intelligence Dashboard (LID) — AI analyzes learning artifacts (discussion forums, assignments, training logs, AAR) to produce structured competency evidence aligned with USMC training standards. Answers: To what extent is learning occurring? Are Marines demonstrating required competencies? Are instructors providing effective training? Audit trails for transparency.

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
- **Security & Sustainability (15%)** — On-prem via Kamiwaza Stack (`KAMIWAZA_BASE_URL` flips provider). FERPA-equivalent for training records: nothing leaves the accredited environment. Append-only chained audit log.
- **Team Collaboration (10%)** — Modular agent / app / heatmap split, README documents reproducible synth (seed 1776), real-data swap recipe in `data/load_real.py`.

---

**Powered by Kamiwaza.**  IL5/IL6 ready · NIPR/SIPR/JWICS deployable · DDIL-tolerant.
