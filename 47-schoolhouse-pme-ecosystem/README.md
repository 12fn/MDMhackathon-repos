# SCHOOLHOUSE — Marine Schoolhouse-in-a-Box

> _PME today is three disconnected systems and a tired NCO. SCHOOLHOUSE folds them into one role-aware UI — on-prem, behind the wire._

**Tier A** entry · **port 3047** (Streamlit mono) · MDM 2026 LOGCOM AI Forum Hackathon.

## Pitch

A USMC schoolhouse-in-a-box. Four drill types in one app, three role-aware UI views, on-prem multimodal LLM. Same on-prem stack scores all four drills, surfaces the cohort heatmap, and writes a one-page Schoolhouse Intelligence Brief reshaped per role.

## Hero AI move (full PME ecosystem)

1. **Egocentric tactical decision drills** — Marine sees a first-person scene (Xperience-10M egocentric still — doorway breach, vehicle checkpoint, casualty triage, comms shop FPCON-Charlie alert), types what they would do; multimodal LLM scores against doctrine (MCWP 3-35.3, MCRP 3-33.1A, TCCC, MCWP 3-11.2, MCWP 3-17.2, MCO 3302.1F) and writes coaching feedback with a specific NAVMC 3500.18 / 3500.58 T&R event code mapping.

2. **Visual ID drills** — Marine drops an image of a foreign or US platform (Military Object Detection corpus); a vision-language model identifies it and writes the analyst-style numbered reasoning with releasability call (the SENTINEL pattern).

3. **Written assignment grading** — Marine submits a logistics-principles paper; `chat_json` grades against a published rubric.xlsx with narrative feedback per criterion plus a 0-5 writing-competency score, anchored to the governing T&R Manual.

4. **Instructor cohort dashboard** — instructor view aggregates the cohort: who's struggling, which assignments are landing, instructor effectiveness signal — same Plotly heatmap pattern as LEARN.

5. **PA Training audience sim** — Marine drafts a unit-internal PA message; 5 audience personas (junior Marine, NCO, officer, civilian spouse, retired vet) react in parallel with trust delta + interpretation + predicted action.

6. **Role-aware AI tutor** — switch persona (student / instructor / school CO) → the entire brief reshapes: student gets adaptive study plan; instructor gets cohort intervention list; CO gets schoolhouse health dashboard.

7. **Hero `chat` ("gpt-5.4", 35s, cache-first)** writes a one-page Schoolhouse Intelligence Brief — BLUF, top performer, students at risk, curriculum effectiveness, recommended instructor moves, cohort competency map; cited against NAVMC 3500-series T&R Manual + MCO 1553.4B PME.

## Datasets (4)

All synthetic for the hackathon — every dataset cites its real-world source so judges know it would plug in unchanged. Real-data swap recipes are documented in `data/load_real.py`.

| # | Synthetic | Real source | Swap-in env var |
|---|---|---|---|
| 1 | `data/courses.json` | Moodle .mbz course exports (CDET / MarineNet) | `REAL_MBZ_PATH` |
| 2 | `SAMPLE_DRAFT` + `rubric_criteria` per course | Student Written Assignment Examples (.docx + .xlsx) | `REAL_ASSIGNMENTS_PATH` |
| 3 | `data/scenes/*.png` + `data/scenes_meta.json` | Xperience-10M egocentric multimodal | `REAL_X10M_PATH` |
| 4 | `data/visual_id/*.png` + `data/visual_id_meta.json` | Military Object Detection Dataset | `REAL_MOD_PATH` |

## Run

```bash
# from the repo root, ensure .env has OPENAI_API_KEY (or KAMIWAZA_BASE_URL etc)
cd apps/47-schoolhouse
pip install -r requirements.txt

# regenerate synthetic data + cached briefs
python data/generate.py

# launch (port 3047)
streamlit run src/app.py \
  --server.port 3047 \
  --server.headless true \
  --server.runOnSave false \
  --server.fileWatcherType none \
  --browser.gatherUsageStats false
```

## Demo arc (90 s)

| Time | Beat |
|---|---|
| 0–5 s | Cold open: "PME today is three disconnected systems and a tired NCO." |
| 5–15 s | Mission frame: 4 LOGCOM datasets + 3 use cases — folded into one app. |
| 15–25 s | Switch to **student** persona → run egocentric drill (Vehicle Checkpoint). |
| 25–40 s | Switch to **Visual ID** drill → drop T-72B3, get analyst-style numbered reasoning. |
| 40–55 s | Switch to **Written assignment** drill → grade against rubric.xlsx. |
| 55–65 s | Switch to **instructor** persona → cohort heatmap + Schoolhouse Intelligence Brief. |
| 65–75 s | Switch to **school CO** persona → same data reshapes to a CO health dashboard. |
| 75–85 s | KAMIWAZA env-var beat: "PME data stays inside the SCIF." |
| 85–90 s | Closer: "Built on the Kamiwaza Stack." |

## Records governance

Privacy Act of 1974 (5 U.S.C. § 552a) and DoDI 1322.35 'Military Education Records' — **NOT FERPA** (FERPA is K-12 / higher-ed; Marines under active military training are governed by the Privacy Act + DoDI 1322.35). Every drill / brief / persona panel append-only logged to `data/audit_logs/schoolhouse_audit.jsonl` with a SHA-256 chain.

## Real cites

- **NAVMC 3500.18** — Infantry T&R Manual
- **NAVMC 3500.58** — Logistics T&R Manual
- **MCO 1553.4B** — Marine Corps PME Framework
- **DoDI 1322.35** — Military Education
- **Privacy Act of 1974** (5 U.S.C. § 552a)
- TECOM, CDET, MCLOG (cited by name; no current contract claimed)

## Powered by Kamiwaza
