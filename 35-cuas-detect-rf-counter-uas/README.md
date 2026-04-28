# CUAS-DETECT — Counter-UAS RF Detection for Installation Force Protection

> Spectrogram in. Watch-officer engagement recommendation out. In seconds.

CUAS-DETECT is agent #35 of the Modern Day Marine 2026 LOGCOM AI Forum
Hackathon portfolio. It pivots two new IEEE DataPort drone-RF datasets into
the LOGCOM **Installation Incident Response** category: Marine bases face
increasing UAS threats (recon drones, weaponized hobbyist quads, swarms) and
the OOD has 30 seconds to make a non-kinetic vs. kinetic call. CUAS-DETECT
classifies an inbound UAS by its RF signature and emits a watch-officer-grade
engagement brief.

## Hero AI move — multi-stage classifier + multimodal LLM intent assessment

1. **Operator picks an RF capture** — six sample spectrograms ship in
   `sample_spectra/` (DJI Mavic, Parrot Anafi, custom commercial fixed-wing,
   COTS hobbyist quad, multi-emitter swarm, ambient/no-signal). Operators
   can also drop their own spectrogram PNG.
2. **Heuristic feature extraction** (`numpy` on the spectrogram array) emits
   peak frequency bins, hopping-pattern signature, modulation hints, and a
   deterministic baseline classifier guess.
3. **Multimodal vision call** (`gpt-4o`-class) ingests the spectrogram PNG +
   heuristic JSON sidecar and returns structured CUAS JSON:
   `uas_class`, `confidence`, `controller_signature_match`, `inferred_intent`,
   `estimated_range_km`, `recommended_action`, `rationale`, and an
   `EOC_callout_text` suitable for a watch-officer SMS alert.
4. **Hero engagement-brief LLM** (cache-first, 35-second watchdog,
   deterministic fallback) writes a five-bullet **CUAS Engagement
   Recommendation** for the OOD with engagement options graded against ROE.

Every LLM call is wrapped in a `ThreadPoolExecutor` watchdog with a
deterministic fallback so the UI never freezes.

## Run

```bash
# from repo root, with .env populated
pip install -r apps/35-cuas-detect/requirements.txt
python apps/35-cuas-detect/data/generate.py    # synthesize spectra + cached briefs
streamlit run apps/35-cuas-detect/src/app.py \
  --server.port 3035 --server.headless true \
  --server.runOnSave false --server.fileWatcherType none \
  --browser.gatherUsageStats false
```

Open <http://localhost:3035>.

## Stack

- **Streamlit** (3035, mono) — single page, dark Kamiwaza theme
- **scipy** + numpy — spectrogram synthesis + heuristic feature extraction
- **Plotly** — frequency × time spectrogram heatmap
- **shared.kamiwaza_client** — multi-provider OpenAI-compatible LLM
  (Kamiwaza on-prem / OpenAI / OpenRouter / Anthropic). Vision lives on the
  OpenAI-compat path; the shared client auto-detects from env.

## Data shape (synthetic)

| File | Purpose |
|---|---|
| `sample_spectra/*.png` + `*.npy` | 6 procedurally-generated spectrograms (PIL) |
| `data/rf_id_db.csv` | 30 known controller fingerprints |
| `data/engagement_options.json` | 8 ROE-graded engagement options |
| `data/cached_briefs.json` | 6 pre-computed CUAS engagement briefs |
| `data/spectra_manifest.json` | Index file the app iterates |

Seed = `1776` for reproducibility.

## Real-data plug-in

`data/load_real.py` documents how to swap synthetic for the two new IEEE
DataPort datasets:

1. **Drone Recognition based on RF Spectrogram** (DroneRF-B Spectra) —
   <https://ieee-dataport.org/> (search "DroneRF-B Spectra"). Drop `.png` +
   matching `.npy` tiles into `data/spectra/` and set `REAL_DATA_PATH`.
2. **Drone RF Identification dataset** (DroneRC RF Signal) —
   <https://ieee-dataport.org/> (search "DroneRC RF Signal"). Drop the
   controller-fingerprint CSV at `data/dronerc.csv` (or set `REAL_RC_CSV`).

The same multi-stage classifier runs unchanged — only the ingestion path
changes.

## Provider note

This app needs a **vision-capable** model for the multimodal classifier
stage. OpenAI (`gpt-4o`) / Kamiwaza-deployed multimodal models / Anthropic
(via the shared client) all work. OpenRouter / custom OK if the configured
model is vision-capable. If the vision call times out the watchdog returns a
deterministic baseline JSON so the demo never blocks.

## Safety / claims

The engagement options catalog is annotated with realistic ROE classes and
authority requirements (per general DoDD 3000.09 / 10 USC 130i / FCC NTIA
spectrum coordination posture). It deliberately **does not** name specific
deployed USMC EW / SHORAD systems and **does not** claim any vendor system is
operationally fielded. The "Recommended COA" is advisory — the OOD always
makes the call.

## Powered by Kamiwaza

Set `KAMIWAZA_BASE_URL` → 100% on-prem inference. Zero code change. IL5/IL6
ready. NIPR/SIPR/JWICS. Air-gapped + DDIL deployment supported.
