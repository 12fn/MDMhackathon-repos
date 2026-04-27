# GHOST — RF Pattern of Life Survey

**Agent #21 · MDM 2026 LOGCOM AI Forum Hackathon**

> *AI Inside Your Security Boundary.*

GHOST collapses an RF scan (Wi-Fi + Bluetooth) into a one-screen
**pattern-of-life survey**: heatmap, clusters, time-bucket activity, and
a SIPR-format AI brief covering BLUF, target/location, device counts,
suspicious signatures, and recommended ISR follow-ups.

## LOGCOM use case (verbatim)

> "Given an RF dataset and/or scan (Wifi, Bluetooth), create full analytics
> based on the data. This would include pattern of life, heatmaps,
> target/location survey."

## Hero AI move — triple

1. **Pattern-of-life clustering** — DBSCAN over `(lat, lon, scaled_time)`.
   Renders as a Folium dark-tile heatmap with neon cluster centroids.
2. **Per-cluster classifier (`chat_json`)** — each cluster gets a
   structured-output JSON tag: `cluster_type`, `inferred_device_type`,
   `confidence`, `time_of_day_pattern`, plus a one-line rationale.
3. **Hero `chat` ("gpt-5.4", 35-second watchdog)** — drafts the
   "RF Pattern of Life Survey" narrative. **Cache-first**:
   `data/cached_briefs.json` ships pre-computed for two scenarios so the
   demo never blocks on a spinner. Live regenerate is one click.

## Run

```bash
# from repo root
pip install -r apps/21-ghost/requirements.txt
python apps/21-ghost/data/generate.py            # synth + cache hero briefs
streamlit run apps/21-ghost/src/app.py \
  --server.port 3021 \
  --server.headless true \
  --server.runOnSave false \
  --server.fileWatcherType none \
  --browser.gatherUsageStats false
```

Open <http://localhost:3021>.

## Data

`data/generate.py` (seed=1776) synthesizes ~5,000 Wi-Fi probes + BT
advertisements over a 24-hour scan of the Camp Pendleton main-gate
perimeter. Planted patterns:

- **device_dwell** — gate-shack, nightly persistent
- **gathering** — chow hall, 1100-1300 spike
- **mobile_transit** — phones along main road, 0700-0900 + 1700-1900 rush
- **fixed_infra** — Cisco/Ruckus/Aruba APs in office buildings
- **fixed_infra (IoT)** — motor pool sensors / vehicle telemetry
- **device_dwell (beacons)** — vehicle park BT beacons
- **ephemeral** — perimeter fence Unknown / Espressif (suspicious)

Schema: `event_id, timestamp, hour, lat, lon, signal_type (WiFi|BT), mac,
oui, vendor, rssi, channel, pattern`.

`data/vendor_oui.csv` ships a 30-row OUI → vendor lookup with realistic
prefixes (Apple, Samsung, Cisco, Ruckus, Estimote, Espressif, etc.).

## Real-data plug-in

`data/load_real.py` documents how to plug in the **IEEE Real-world
Commercial Wi-Fi and Bluetooth Dataset for RF Fingerprinting** (IEEE
DataPort) at the same schema. Set `REAL_DATA_PATH=/path/to/file.csv`
and re-run; no app code change.

## Files

```
apps/21-ghost/
├── README.md
├── PRD.md
├── requirements.txt
├── .env.example
├── STATUS.txt
├── data/
│   ├── generate.py
│   ├── load_real.py
│   ├── rf_events.csv          (5,000 synthetic events, generated)
│   ├── rf_events_sample.json
│   ├── vendor_oui.csv
│   └── cached_briefs.json     (cache-first hero briefs · 2 scenarios)
├── src/
│   ├── app.py                 (Streamlit, port 3021)
│   └── agent.py               (chat_json classifier + hero chat survey)
├── tests/
│   └── record-demo.spec.ts
├── playwright.config.ts
├── burn_captions.py
├── demo-script.md
├── demo-script.json           (emitted by Playwright)
└── videos/ghost-demo.mp4      (final captioned video)
```

## Stack

Streamlit (port 3021) · Folium dark CartoDB tiles · Plotly stacked-bar
histogram · scikit-learn DBSCAN · `shared.kamiwaza_client` (multi-provider).

Powered by Kamiwaza.
