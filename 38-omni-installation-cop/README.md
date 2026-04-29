# OMNI — Cross-Domain Installation Common Operating Picture

> One operator screen. Six fused feeds. Three LOGCOM use cases at once:
> **I-COP Aggregator** + **ERMP** + **Browser-AI Governance**.

OMNI is the mega-app of the LOGCOM MDM 2026 Phase 2 wave. It pulls six
disparate installation streams onto a single dark-themed dashboard for the
watch officer at the MCB Camp Pendleton Installation EOC, finds anomalies
that span 2+ domains in the same time window, generates a Commander's I-COP
Brief on demand, and maintains a SHA-256 hash-chained who-saw-what audit
log of every persona switch and brief view.

## Hero AI move

A **two-stage cross-domain pipeline**:

1. **Cross-domain correlator** (`chat_json`, structured-output JSON mode,
   18s watchdog) consumes the last 24 hours of fused events from six
   streams and emits anomalies that are corroborated across MULTIPLE
   DOMAINS. Each anomaly carries a `domains_crossed` count, the
   contributing streams, an explainability trace, and a confidence.
2. **Commander's I-COP Brief** (hero `chat`, "gpt-5.4" model, 35s
   timeout, cache-first) writes a one-page brief — BLUF, top 3 cross-
   domain anomalies, predictive risk for next 12h, recommended pre-
   positioning per CCDR. Pre-computed at synth time into
   `data/cached_briefs.json` so the demo never sits idle.

Both calls are wrapped in `concurrent.futures.ThreadPoolExecutor` with
wall-clock timeouts and fall back to deterministic functions on any
failure or timeout.

## Role-aware ABAC

The dashboard reshapes itself per persona (CO / G-1 / G-2 / G-3 / G-4 /
S-6). Stream chips for unauthorized streams render as
**REDACTED — INSUFFICIENT CLEARANCE**, not invisible — so the persona
sees that the stream exists, just not its contents. Anomaly cards scrub
unauthorized contributing-stream pills and label them red.

ABAC enforcement happens inside `src/abac.py` and is applied by both the
FastAPI endpoints (`/api/streams/{persona_id}`,
`/api/timeline/{persona_id}`, `/api/correlate/{persona_id}`,
`/api/brief` with persona check) and the Streamlit UI layer.

## SHA-256 hash-chained audit (Browser-AI Governance tie-in)

Every persona switch, dashboard view, stream view, anomaly view, and
brief view appends a chained record to `audit_logs/omni_audit.jsonl`.
Pattern lifted from `apps/30-guardian`. The Audit tab includes a
"Verify chain integrity" button that walks the file end-to-end.

## Datasets (synthetic stand-ins for 6 real feeds)

| Dataset | Real source | Synth file |
|---|---|---|
| HIFLD critical infrastructure | hifld-geoplatform.opendata.arcgis.com | `data/installations.json` (embedded) |
| NASA Earthdata weather | earthdata.nasa.gov (MERRA-2) | `data/weather.json` |
| NASA FIRMS thermal | firms.modaps.eosdis.nasa.gov | `data/firms.json` |
| GCSS-MC maintenance | SIPR/GCSS-MC export | `data/maintenance.json` |
| IEEE WiFi/BT RF fingerprinting | IEEE-DataPort | `data/rf_events.json` |
| Drone RF detections | DroneRF dataset / DJI Aeroscope log | `data/drone_rf_events.json` |

Plus the synthesized installation-services streams: gate, utility,
EMS/CAD, mass-notification — patterned after DBIDS / DPW SCADA / CAD /
AtHoc + Giant Voice.

Real-data plug-in: see `data/load_real.py`. Each loader documents its
expected schema and the env var that points at the real data path.

## Run

```bash
cd apps/38-omni
pip install -r requirements.txt
python data/generate.py     # 12 JSON files + cached briefs (seed=1776)

# Backend
python -m uvicorn src.api:app --host 0.0.0.0 --port 8038 &

# Frontend
streamlit run src/app.py \
  --server.port 3038 --server.headless true \
  --server.runOnSave false --server.fileWatcherType none \
  --browser.gatherUsageStats false

open http://localhost:3038
```

## Demo arc

1. Cold open / mission frame.
2. Live ingest — six streaming feeds, 600 fused events.
3. Cross-domain correlator finds the planted anomalies.
4. Switch personas (CO → G-2 → G-4) showing different views + REDACTED.
5. Commander's Brief streams in.
6. Audit tab — hash-chained who-saw-what, verify-button passes.
7. Closer — `KAMIWAZA_BASE_URL` env-var = on-prem in one swap.

Captioned video (~90s): `videos/omni-demo.mp4`.

## On-prem

Set `KAMIWAZA_BASE_URL` (and optionally `KAMIWAZA_API_KEY`) in `.env`
and every LLM call routes through your accredited endpoint. The shared
client (`shared/kamiwaza_client.py`) is multi-provider — Kamiwaza,
OpenAI, OpenRouter, Anthropic, or any OpenAI-compatible endpoint.

Air-gapped, IL5/IL6 ready. Built on the Kamiwaza Stack.
