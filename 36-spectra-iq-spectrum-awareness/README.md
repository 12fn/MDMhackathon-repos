# SPECTRA — Marine FOB / Installation Spectrum Awareness

> AI Inside Your Security Boundary.

Agent #36 of the MDM 2026 LOGCOM AI Forum Hackathon portfolio.

SPECTRA ingests a single one-second I/Q capture, renders an STFT spectrogram,
and runs a multimodal vision-language model over the image + SigMF metadata
header to classify the protocol, modulation, device class, and anomaly state.
A second hero call drafts a SIPR-format **RF Spectrum Awareness Brief** for
the FOB Spectrum Manager.

This is the **raw I/Q sister** of GHOST (#21). Where GHOST builds pattern of
life from processed Wi-Fi + Bluetooth scan tables, SPECTRA answers the
single-snapshot question — *"I just heard something. What is it, is it ours,
and what do I do?"*

## Run

```bash
cd apps/36-spectra
pip install -r requirements.txt
# (optional) regenerate synthetic captures + cache the hero briefs
python data/generate.py
# launch
streamlit run src/app.py \
  --server.port 3036 --server.headless true \
  --server.runOnSave false --server.fileWatcherType none \
  --browser.gatherUsageStats false
# open http://localhost:3036
```

The shared `kamiwaza_client` auto-detects your provider (Kamiwaza / OpenAI /
OpenRouter / Anthropic / any OpenAI-compatible endpoint). Set
`KAMIWAZA_BASE_URL` and your code goes 100% on-prem with zero edits.

## Hero AI move

Three-stage pipeline:

1. **DSP.** numpy complex64 1-sec capture at 30 MS/s → `scipy.signal.stft` →
   128×128 dB-scale spectrogram → Plotly heatmap.
2. **Vision-language classifier.** `gpt-4o` multimodal ingests the spectrogram
   image + SigMF-format metadata header → returns strict JSON:

```json
{
  "modulation_class": "OFDM | FSK | GFSK | DSSS | unknown",
  "protocol_inferred": "WiFi-2.4 | WiFi-5 | BT-Classic | BT-LE | LoRa | Zigbee | proprietary | unknown",
  "estimated_burst_count": 12,
  "duty_cycle_estimate_pct": 38.4,
  "signal_strength_band": "strong | medium | weak | edge",
  "device_class_hypothesis": "phone | wearable | iot-sensor | wifi-AP | bt-beacon | unknown-emitter",
  "anomaly_flag": "nominal | unauthorized-band | suspicious-pattern | active-jamming",
  "confidence": 0.83
}
```

3. **Hero brief.** `chat` (`gpt-5.4`, 35 s watchdog, cache-first) writes the
   RF Spectrum Awareness Brief — BLUF, top emitters, anomalies flagged,
   recommended Spectrum Manager actions.

Both calls run through the shared multi-provider client. Both have a wall-clock
watchdog and a deterministic fallback so the demo never blocks on a spinner.
Brief outputs for the six canonical scenarios are pre-cached in
`data/cached_briefs.json` for the demo path.

## Real-data plug-in

The NIST **Wi-Fi & Bluetooth I/Q RF Recordings (2.4 / 5 GHz)** corpus
publishes 900 one-second I/Q captures at 30 MS/s with SigMF-compatible CSV
metadata (center frequency, bandwidth, sample rate, gain, hardware,
calibration, noise floor).

URL: https://data.nist.gov/od/id/mds2-2731

To plug in:

1. Drop the NIST `.npy` (or `.sigmf-data` re-saved as complex64 .npy) files
   into `data/captures/`.
2. Append rows to `data/captures_metadata.csv` with the same column names
   (already SigMF-compatible).
3. Set `REAL_DATA_PATH=$(pwd)/data/captures` and `streamlit run`.

`data/load_real.py` documents the column contract.

## Files

```
apps/36-spectra/
├── README.md
├── PRD.md
├── STATUS.txt
├── requirements.txt
├── package.json
├── playwright.config.ts
├── .env.example
├── demo-script.md
├── demo-script.json                # emitted by the recorder
├── data/
│   ├── generate.py                 # synth captures + precompute briefs
│   ├── load_real.py                # NIST plug-in stub
│   ├── captures_metadata.csv       # SigMF-style metadata table
│   ├── vendor_protocol_map.json    # 20 (modulation, protocol) → device-class mappings
│   ├── cached_briefs.json          # 6 pre-computed hero briefs
│   └── captures/                   # 6 .npy complex64 I/Q files
├── src/
│   ├── app.py                      # Streamlit single-page on :3036
│   ├── signal_proc.py              # STFT, PSD, spectrogram image, header pretty-print
│   └── agent.py                    # vision-language classifier + hero brief, both with watchdog
├── tests/
│   └── record-demo.spec.ts         # Playwright walkthrough → demo-script.json
└── videos/
    └── spectra-demo.mp4            # final captioned video
```

## Powered by Kamiwaza
