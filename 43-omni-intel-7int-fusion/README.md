# OMNI-INTEL -- All-Source Intelligence Fusion

**Codename:** OMNI-INTEL
**Port:** 3043 (Streamlit mono)
**Use case:** USMC LOGCOM CDAO -- G-2 daily intelligence brief at scale, multi-source fusion
**Tier:** A -- all-source intel fusion
**Mission frame:** MARADMIN 131/26 -- Stand-In-Forces ISR for contested logistics

## Pitch

A G-2 staff in WestPac runs seven separate INT pipelines (AIS, ASAM, IMINT,
MASINT, SIGINT-RF, SIGINT-WiFi/BT, GEOINT-FIRMS) and nothing fuses until the
Wednesday morning brief. OMNI-INTEL normalizes all seven into a single
observation envelope, runs a cross-source spatial-temporal correlator, asks
a Kamiwaza-deployed model to classify each fusion cluster (`chat_json`), and
composes a SIPR-style **Daily All-Source Intelligence Brief (ASIB)** with BLUF,
observed activity by source-type, fused-source highlights, named threats,
CCIR-aligned collection recommendations, confidence statement, and the CCDR
distribution line.

## Hero AI move

1. **Per-source ingest** -- 7 native streams parsed into the common envelope
   `{source_type, observation_id, dtg, lat, lon, raw_signature, confidence}`.
2. **Cross-source correlator** -- finds clusters where >=2 INT disciplines
   observe the same target/area inside `(time_window_min, space_radius_km)`.
   Per-source confidence weights (HIT-UAV thermal 1.00, WiFi/BT 0.50) drive a
   `weighted_score`. Edges carry an explainability trace ("AIS GAP [14:05] +
   HITUAV vessel_wake [14:13] within 1.4 km / 13 min").
3. **Per-cluster classification** -- `chat_json` labels each cluster
   {combat, commercial, industrial, wildfire, ambient, ambiguous} with
   rationale + ISR-asset recommendation. Heuristic fallback always wired.
4. **Hero ASIB composer** -- `gpt-5.4` with 35s watchdog + deterministic
   baseline. Cache-first via `data/cached_briefs.json` (3 scenarios).

## Run

```bash
cd apps/43-omni-intel
pip install -r requirements.txt
python data/generate.py            # synthesizes 16k+ observations + 3 cached briefs
streamlit run src/app.py \
  --server.port 3043 \
  --server.headless true \
  --server.runOnSave false \
  --server.fileWatcherType none \
  --browser.gatherUsageStats false
```

## Real-data plug-in

`data/load_real.py` documents the swap recipe for **all 7 sources** (env vars,
native schema, field mapping). Sources without env vars stay synthetic, so
partial-real operation works:

| INT discipline | Source                        | Env var              |
|----------------|-------------------------------|----------------------|
| GEOINT         | AIS Aug 2024 (NOAA)           | `REAL_AIS_PATH`      |
| OSINT          | NGA ASAM Pirate Attacks       | `REAL_ASAM_PATH`     |
| IMINT          | Military Object Detection v3  | `REAL_MILOBJ_PATH`   |
| MASINT         | HIT-UAV Thermal               | `REAL_HITUAV_PATH`   |
| SIGINT         | DroneRF Spectrogram           | `REAL_DRONERF_PATH`  |
| SIGINT         | IEEE WiFi/BT RF Fingerprinting| `REAL_WIFIBT_PATH`   |
| GEOINT         | NASA FIRMS Ukraine            | `REAL_FIRMS_PATH`    |

## Ultra-technical features

- **7-source schema-normalization layer** -- `data/generate.py` per-source
  emitters all return the same envelope.
- **Cross-source correlation algorithm with explainability** -- union-find
  over time-windowed cross-source spatial edges; each cluster carries the
  per-edge reason chain.
- **Per-source confidence weighting** -- `SOURCE_WEIGHTS` in `src/fusion.py`.
- **Live "fusion trace" sidebar** -- shows which observations linked, when,
  and at what range -- driven directly off the correlator's edge log.
- **Hash-chained audit log** -- `audit_logs/fusion_chain.jsonl` SHA-256-chains
  every cluster decision for SIGINT/HUMINT auditability per ICD 501.
- **KAMIWAZA env-var beat** -- `KAMIWAZA_BASE_URL` keeps multi-INT fusion in
  the JWICS-equivalent enclave (sidebar + footer).

## Stack

- Streamlit on port 3043 -- single page, 5 tabs (Fusion Map, Cluster Inspector,
  Per-Source Tabs, Daily ASIB, Audit Chain).
- Folium dark-tile map (CartoDB dark_matter) showing all 7 sources colour-coded
  + fusion-cluster overlay sized by `weighted_score`.
- Plotly per-source activity timeline (30-min buckets, area chart).
- Tabbed UI per source so analysts can drill straight into the raw stream.
- `shared.kamiwaza_client.chat_json` for cluster labels, `chat()` (`gpt-5.4`)
  for the hero ASIB.

## Demo arc (90s)

1. Cold open -- title card.
2. Mission frame -- MARADMIN 131/26, the seven-stovepipe G-2 pain.
3. Live ingest -- all 7 streams on the dark map.
4. Hero AI moment -- the cross-source correlator surfaces 5 fusion clusters
   matching the planted ground-truth anchors. Click cluster F-001; the live
   fusion trace sidebar explains *why* the AI decided AIS + HIT-UAV + DroneRF
   + ASAM are the same target.
5. Operator workflow -- one click streams the cached SIPR-format ASIB.
6. On-prem story -- `KAMIWAZA_BASE_URL` + audit-chain integrity check.
7. Closer.

## Files

```
apps/43-omni-intel/
├── README.md              -- this file
├── PRD.md                 -- spec + scoring tie-back
├── data/
│   ├── generate.py        -- 7-source synth + cached_briefs precompute
│   ├── load_real.py       -- 7-source real-data swap stubs
│   ├── all_observations.json
│   ├── ais.json / asam.json / milobj.json / hituav.json / dronerf.json
│   │   wifibt.json / firms.json
│   ├── platform_library.json
│   ├── planted_fusions.json   -- 5 multi-source ground-truth anchors
│   └── cached_briefs.json     -- 3 pre-computed ASIB scenarios
├── src/
│   ├── app.py              -- Streamlit on 3043
│   ├── fusion.py           -- cross-source correlator + classifier
│   ├── brief.py            -- hero ASIB composer (35s watchdog, cache-first)
│   └── audit.py            -- SHA-256 hash-chained audit log
├── audit_logs/
│   └── fusion_chain.jsonl  -- runtime-appended; verifies on app start
├── tests/record-demo.spec.ts
├── playwright.config.ts
├── package.json / requirements.txt / .env.example
├── demo-script.md / demo-script.json
├── videos/omni-intel-demo.mp4
└── STATUS.txt
```

## Doctrine cited

BLUF, EEFI, CCIR, IPOE, CIM, MIDB, MASINT, SIGINT, IMINT, HUMINT, OSINT, GEOINT,
ICD 501 (audit). MARADMIN 131/26 (Stand-In Forces / contested logistics).

Powered by Kamiwaza.
