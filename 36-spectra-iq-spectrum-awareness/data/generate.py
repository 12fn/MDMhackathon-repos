"""SPECTRA — synthetic I/Q capture generator.

Real dataset reference (would plug in via data/load_real.py):
  NIST Wi-Fi & Bluetooth I/Q RF Recordings (2.4 / 5 GHz)
  https://data.nist.gov/od/id/mds2-2731
  900 one-second I/Q captures at 30 MS/s with SigMF-compatible CSV metadata.

Generates 6 representative one-second complex64 I/Q files at 8 MS/s (downsampled
from the real 30 MS/s footprint to keep the repo lean — the metadata CSV still
documents the canonical NIST 30 MS/s rate so the schema matches). Each capture
is one of the canonical FOB scenarios:

  - wifi_idle_24            : OFDM-like beacon spaced ~102.4 ms (nominal)
  - wifi_busy_bt_mix        : OFDM + bursty GFSK (nominal)
  - bt_le_beacon_storm      : 8 GFSK BLE advertisers in burst pattern (suspicious-pattern)
  - unauth_433_emitter      : OOK pulse train at non-WiFi/BT band (unauthorized-band)
  - jamming_sweep           : wideband chirp (active-jamming)
  - ambient_noise           : Gaussian noise floor only (nominal)

Outputs:
  data/captures/<scenario>.npy           complex64 I/Q array, 1 sec @ 8 MS/s
  data/captures_metadata.csv             SigMF-compatible per-capture metadata
  data/vendor_protocol_map.json          (modulation, protocol) -> device-class map
  data/cached_briefs.json                pre-computed hero briefs (cache-first)
"""
from __future__ import annotations

import csv
import json
import math
import os
import random
import sys
from pathlib import Path

import numpy as np

OUT_DIR = Path(__file__).parent
CAP_DIR = OUT_DIR / "captures"
SEED = 1776

# Synthesis sample rate (Hz). Real NIST captures are 30 MS/s; we synth at
# 2 MS/s to keep .npy files ~16 MB each at 1 second of complex64. The
# metadata CSV still documents the canonical NIST 30 MS/s rate so the
# real-data plug-in path matches.
SYN_FS = 2_000_000
DUR_SEC = 1.0
N_SAMPLES = int(SYN_FS * DUR_SEC)

# Canonical NIST sample rate (cited in the metadata CSV)
NIST_FS = 30_000_000

SCENARIOS: list[dict] = [
    {
        "scenario_id": "wifi_idle_24",
        "label": "Wi-Fi 2.4 GHz · idle AP beacon",
        "center_freq_GHz": 2.437,
        "bw_MHz": 20.0,
        "gain_dB": 30,
        "hardware": "USRP-X300/UBX160/VERT2450",
        "noise_floor_dBm": -96,
        "calibration": "factory",
        "expected_anomaly": "nominal",
    },
    {
        "scenario_id": "wifi_busy_bt_mix",
        "label": "Wi-Fi 2.4 GHz busy + BT-LE traffic",
        "center_freq_GHz": 2.450,
        "bw_MHz": 80.0,
        "gain_dB": 28,
        "hardware": "USRP-X300/UBX160/VERT2450",
        "noise_floor_dBm": -94,
        "calibration": "factory",
        "expected_anomaly": "nominal",
    },
    {
        "scenario_id": "bt_le_beacon_storm",
        "label": "Bluetooth LE beacon storm (8 advertisers)",
        "center_freq_GHz": 2.420,
        "bw_MHz": 2.0,
        "gain_dB": 36,
        "hardware": "USRP-X300/UBX160/VERT2450",
        "noise_floor_dBm": -97,
        "calibration": "factory",
        "expected_anomaly": "suspicious-pattern",
    },
    {
        "scenario_id": "unauth_433_emitter",
        "label": "Unauthorized 433 MHz OOK emitter",
        "center_freq_GHz": 0.43392,
        "bw_MHz": 0.5,
        "gain_dB": 40,
        "hardware": "USRP-X300/UBX160/VERT2450",
        "noise_floor_dBm": -98,
        "calibration": "factory",
        "expected_anomaly": "unauthorized-band",
    },
    {
        "scenario_id": "jamming_sweep",
        "label": "Wideband chirp jammer · 2.4 GHz",
        "center_freq_GHz": 2.450,
        "bw_MHz": 80.0,
        "gain_dB": 22,
        "hardware": "USRP-X300/UBX160/VERT2450",
        "noise_floor_dBm": -82,
        "calibration": "factory",
        "expected_anomaly": "active-jamming",
    },
    {
        "scenario_id": "ambient_noise",
        "label": "Ambient noise floor · 5 GHz quiet channel",
        "center_freq_GHz": 5.180,
        "bw_MHz": 20.0,
        "gain_dB": 30,
        "hardware": "USRP-X300/UBX160/VERT2450",
        "noise_floor_dBm": -99,
        "calibration": "factory",
        "expected_anomaly": "nominal",
    },
]


# ─────────────────────────────────────────────────────────────────────────────
# Signal-synthesis primitives
# ─────────────────────────────────────────────────────────────────────────────
def _noise_floor(rng: np.random.Generator, n: int, sigma: float = 0.025) -> np.ndarray:
    """Complex AWGN (thermal + sensor) at a low level."""
    return (rng.normal(0, sigma, n) + 1j * rng.normal(0, sigma, n)).astype(np.complex64)


def _ofdm_burst(rng: np.random.Generator, n_samp: int, *,
                fs: float, sub_offset_hz: float, n_subcarriers: int = 32,
                spacing_hz: float = 20_000.0,
                amplitude: float = 0.55) -> np.ndarray:
    """Approximate OFDM-like burst: sum of n_subcarriers QAM-like complex tones
    centered at sub_offset_hz, modulated as a burst envelope. (Scaled-down
    spacing for our 2 MS/s synth — visually the same OFDM-comb shape.)"""
    t = np.arange(n_samp) / fs
    sig = np.zeros(n_samp, dtype=np.complex64)
    for k in range(-n_subcarriers // 2, n_subcarriers // 2):
        if k == 0:
            continue
        f = sub_offset_hz + k * spacing_hz
        # random QAM-ish phase per subcarrier
        phi = float(rng.uniform(0, 2 * np.pi))
        amp = amplitude / np.sqrt(n_subcarriers)
        sig += (amp * np.exp(1j * (2 * np.pi * f * t + phi))).astype(np.complex64)
    return sig


def _gfsk_burst(rng: np.random.Generator, n_samp: int, *,
                fs: float, center_offset_hz: float, dev_hz: float = 250_000.0,
                amplitude: float = 0.6) -> np.ndarray:
    """Tiny GFSK-style burst: random bits frequency-shifting a carrier."""
    bit_rate = 1_000_000  # 1 Mbps BLE
    samples_per_bit = max(2, int(fs / bit_rate))
    n_bits = max(2, n_samp // samples_per_bit)
    bits = rng.integers(0, 2, n_bits) * 2 - 1  # ±1
    # Smooth via gaussian filter (BT=0.5 approx) — convolve with small kernel
    ksize = 5
    kernel = np.exp(-0.5 * ((np.arange(ksize) - ksize // 2) / 1.5) ** 2)
    kernel /= kernel.sum()
    bits_smooth = np.convolve(bits.astype(float), kernel, mode="same")
    # Repeat each bit
    inst_freq = np.repeat(bits_smooth, samples_per_bit)[:n_samp]
    # Pad if short
    if len(inst_freq) < n_samp:
        inst_freq = np.pad(inst_freq, (0, n_samp - len(inst_freq)))
    phase = 2 * np.pi * np.cumsum(center_offset_hz + dev_hz * inst_freq) / fs
    return (amplitude * np.exp(1j * phase)).astype(np.complex64)


def _ook_pulse_train(rng: np.random.Generator, n_samp: int, *,
                      fs: float, pulse_rate_hz: float = 50.0,
                      pulse_width_s: float = 0.0008,
                      offset_hz: float = 0.0,
                      amplitude: float = 0.65) -> np.ndarray:
    """OOK / ASK pulse train — typical of 433 MHz remotes / drop sensors."""
    t = np.arange(n_samp) / fs
    sig = np.zeros(n_samp, dtype=np.complex64)
    period = int(fs / pulse_rate_hz)
    width = int(fs * pulse_width_s)
    pos = int(rng.integers(0, period))
    while pos + width < n_samp:
        # ~15% jitter in pulse position (real sensors aren't perfect)
        jitter = int(rng.normal(0, period * 0.05))
        a = max(0, pos + jitter)
        b = min(n_samp, a + width)
        sig[a:b] = amplitude * np.exp(1j * 2 * np.pi * offset_hz * t[a:b])
        pos += period
    return sig


def _chirp(n_samp: int, *, fs: float, f0: float, f1: float,
           amplitude: float = 0.85) -> np.ndarray:
    """Linear FM chirp from f0 to f1 across the capture (jammer signature)."""
    t = np.arange(n_samp) / fs
    inst_phase = 2 * np.pi * (f0 * t + 0.5 * (f1 - f0) / DUR_SEC * t * t)
    return (amplitude * np.exp(1j * inst_phase)).astype(np.complex64)


def _periodic_burst_envelope(n_samp: int, *, fs: float, period_s: float,
                              on_time_s: float) -> np.ndarray:
    """0/1 envelope. period_s is the gap between burst starts; on_time_s is the
    on-time per burst."""
    period = int(fs * period_s)
    on = int(fs * on_time_s)
    env = np.zeros(n_samp, dtype=np.float32)
    pos = 0
    while pos + on < n_samp:
        env[pos:pos + on] = 1.0
        pos += period
    return env


# ─────────────────────────────────────────────────────────────────────────────
# Per-scenario synthesis
# ─────────────────────────────────────────────────────────────────────────────
def synth_capture(scenario_id: str, rng: np.random.Generator) -> np.ndarray:
    """Generate a 1-second complex64 I/Q array for the given scenario."""
    fs = float(SYN_FS)
    n = N_SAMPLES
    sig = _noise_floor(rng, n, sigma=0.03)

    if scenario_id == "wifi_idle_24":
        # ~10 beacon frames per second at 102.4 ms spacing, each ~250 us
        env = _periodic_burst_envelope(n, fs=fs, period_s=0.1024, on_time_s=0.00025)
        ofdm = _ofdm_burst(rng, n, fs=fs, sub_offset_hz=+200_000.0,
                            n_subcarriers=32, spacing_hz=15_000.0,
                            amplitude=0.65)
        sig = sig + (ofdm * env).astype(np.complex64)

    elif scenario_id == "wifi_busy_bt_mix":
        # Heavy WiFi: 60 short bursts/sec, each ~500us, plus BT GFSK chatter
        env_w = _periodic_burst_envelope(n, fs=fs, period_s=0.0167,
                                          on_time_s=0.0005)
        ofdm = _ofdm_burst(rng, n, fs=fs, sub_offset_hz=-300_000.0,
                            n_subcarriers=32, spacing_hz=18_000.0,
                            amplitude=0.55)
        sig = sig + (ofdm * env_w).astype(np.complex64)
        # 25 BT-LE bursts mixed in, lower amplitude, on opposite side
        env_b = _periodic_burst_envelope(n, fs=fs, period_s=0.04,
                                          on_time_s=0.00018)
        gfsk = _gfsk_burst(rng, n, fs=fs, center_offset_hz=+450_000.0,
                            dev_hz=120_000.0, amplitude=0.45)
        sig = sig + (gfsk * env_b).astype(np.complex64)

    elif scenario_id == "bt_le_beacon_storm":
        # 8 advertisers each emitting ~10 advertisements / sec — that's 80
        # bursts/sec, at slightly different center offsets. Looks like a storm.
        for adv in range(8):
            offset = float(rng.uniform(-300_000, 300_000))
            phase = float(rng.uniform(0, 0.02))
            env = _periodic_burst_envelope(n, fs=fs, period_s=0.1,
                                            on_time_s=0.00018)
            # phase-shift by re-rolling start
            shift = int(phase * fs)
            env = np.roll(env, shift)
            gfsk = _gfsk_burst(rng, n, fs=fs, center_offset_hz=offset,
                                dev_hz=120_000.0, amplitude=0.40)
            sig = sig + (gfsk * env).astype(np.complex64)

    elif scenario_id == "unauth_433_emitter":
        # OOK pulse train, ~25 pulses/sec, 1 ms wide. Off-band for any
        # WiFi/BT band — by definition unauthorized in the 2.4 GHz survey.
        train = _ook_pulse_train(rng, n, fs=fs, pulse_rate_hz=25.0,
                                  pulse_width_s=0.001, offset_hz=+30_000.0,
                                  amplitude=0.7)
        sig = sig + train

    elif scenario_id == "jamming_sweep":
        # Continuous wideband linear chirp covering most of the baseband,
        # plus a constant CW pedestal — classic spectrum hog. With a 2 MS/s
        # synth, we span -800 kHz to +800 kHz.
        chirp = _chirp(n, fs=fs, f0=-800_000.0, f1=+800_000.0,
                        amplitude=0.85)
        sig = sig + chirp
        # add a constant CW pedestal too
        t = np.arange(n) / fs
        cw = 0.25 * np.exp(1j * 2 * np.pi * 100_000.0 * t).astype(np.complex64)
        sig = sig + cw

    elif scenario_id == "ambient_noise":
        # Already only noise floor. Slightly bump sigma for variety.
        sig = _noise_floor(rng, n, sigma=0.045)
        # add a single faint distant carrier to make it non-degenerate
        t = np.arange(n) / fs
        faint = 0.02 * np.exp(1j * 2 * np.pi * -350_000.0 * t).astype(np.complex64)
        sig = sig + faint

    else:
        raise ValueError(f"Unknown scenario: {scenario_id}")

    # Final amplitude normalization to roughly [-1, 1] complex
    peak = max(0.001, float(np.max(np.abs(sig))))
    if peak > 1.4:
        sig = (sig / peak * 1.2).astype(np.complex64)
    return sig.astype(np.complex64)


# ─────────────────────────────────────────────────────────────────────────────
# Vendor / protocol map
# ─────────────────────────────────────────────────────────────────────────────
VENDOR_PROTOCOL_MAP = {
    "OFDM": {
        "WiFi-2.4":   ["wifi-AP", "phone", "iot-sensor"],
        "WiFi-5":     ["wifi-AP", "phone"],
        "proprietary":["unknown-emitter"],
        "unknown":    ["unknown-emitter"],
    },
    "FSK": {
        "BT-Classic": ["phone", "wearable"],
        "proprietary":["iot-sensor"],
        "unknown":    ["unknown-emitter"],
    },
    "GFSK": {
        "BT-Classic": ["phone", "wearable"],
        "BT-LE":      ["bt-beacon", "wearable", "iot-sensor"],
        "Zigbee":     ["iot-sensor"],
        "unknown":    ["unknown-emitter"],
    },
    "DSSS": {
        "WiFi-2.4":   ["wifi-AP"],
        "Zigbee":     ["iot-sensor"],
        "unknown":    ["unknown-emitter"],
    },
    "OOK": {
        "proprietary":["unknown-emitter", "iot-sensor"],
        "unknown":    ["unknown-emitter"],
    },
    "Chirp": {
        "proprietary":["unknown-emitter"],
        "unknown":    ["unknown-emitter"],
    },
    "unknown": {
        "unknown":    ["unknown-emitter"],
    },
}


# ─────────────────────────────────────────────────────────────────────────────
# Pre-computed brief scenarios (cache-first)
# ─────────────────────────────────────────────────────────────────────────────
SCENARIO_HINTS = {
    "wifi_idle_24": {
        "modulation_class": "OFDM",
        "protocol_inferred": "WiFi-2.4",
        "estimated_burst_count": 10,
        "duty_cycle_estimate_pct": 0.25,
        "signal_strength_band": "medium",
        "device_class_hypothesis": "wifi-AP",
        "anomaly_flag": "nominal",
        "confidence": 0.88,
    },
    "wifi_busy_bt_mix": {
        "modulation_class": "OFDM",
        "protocol_inferred": "WiFi-2.4",
        "estimated_burst_count": 60,
        "duty_cycle_estimate_pct": 3.0,
        "signal_strength_band": "strong",
        "device_class_hypothesis": "wifi-AP",
        "anomaly_flag": "nominal",
        "confidence": 0.81,
    },
    "bt_le_beacon_storm": {
        "modulation_class": "GFSK",
        "protocol_inferred": "BT-LE",
        "estimated_burst_count": 78,
        "duty_cycle_estimate_pct": 1.4,
        "signal_strength_band": "medium",
        "device_class_hypothesis": "bt-beacon",
        "anomaly_flag": "suspicious-pattern",
        "confidence": 0.79,
    },
    "unauth_433_emitter": {
        "modulation_class": "OOK",
        "protocol_inferred": "proprietary",
        "estimated_burst_count": 25,
        "duty_cycle_estimate_pct": 2.5,
        "signal_strength_band": "strong",
        "device_class_hypothesis": "unknown-emitter",
        "anomaly_flag": "unauthorized-band",
        "confidence": 0.86,
    },
    "jamming_sweep": {
        "modulation_class": "Chirp",
        "protocol_inferred": "unknown",
        "estimated_burst_count": 1,
        "duty_cycle_estimate_pct": 100.0,
        "signal_strength_band": "strong",
        "device_class_hypothesis": "unknown-emitter",
        "anomaly_flag": "active-jamming",
        "confidence": 0.92,
    },
    "ambient_noise": {
        "modulation_class": "unknown",
        "protocol_inferred": "unknown",
        "estimated_burst_count": 0,
        "duty_cycle_estimate_pct": 0.0,
        "signal_strength_band": "edge",
        "device_class_hypothesis": "unknown-emitter",
        "anomaly_flag": "nominal",
        "confidence": 0.67,
    },
}


def _build_brief_payload(sc: dict) -> dict:
    hint = SCENARIO_HINTS[sc["scenario_id"]]
    return {
        "site": "FOB Spectrum Manager · Marine Installation perimeter",
        "capture": sc["scenario_id"],
        "label": sc["label"],
        "metadata": {
            "center_freq_GHz": sc["center_freq_GHz"],
            "bw_MHz": sc["bw_MHz"],
            "sample_rate_MSPS": NIST_FS / 1_000_000.0,
            "gain_dB": sc["gain_dB"],
            "hardware": sc["hardware"],
            "noise_floor_dBm": sc["noise_floor_dBm"],
            "calibration": sc["calibration"],
        },
        "classifier_json": hint,
    }


SYSTEM_BRIEF = (
    "You are SPECTRA — a USMC FOB Spectrum Manager / Force Protection RF "
    "analyst. Produce a SIPR-format 'RF Spectrum Awareness Brief' from the "
    "single I/Q snapshot summary provided. Sections in this exact order, "
    "each marked (U) and one short paragraph each:\n\n"
    "(U) BLUF\n"
    "(U) Capture Header & Bandwidth\n"
    "(U) Top Emitters Identified\n"
    "(U) Anomalies / Unauthorized Activity\n"
    "(U) Recommended Spectrum Manager Actions\n"
    "(U) Confidence\n\n"
    "Use only the data provided. Reference the center frequency, bandwidth, "
    "and the classifier's anomaly_flag verbatim. Total length under ~280 "
    "words. Lead BLUF in two sentences. End with explicit confidence "
    "(LOW/MED/HIGH) plus one-line justification."
)


def _fallback_brief(payload: dict) -> str:
    md = payload["metadata"]
    cj = payload["classifier_json"]
    return (
        f"(U) BLUF\n"
        f"SPECTRA single-snapshot capture {payload['capture']} "
        f"({payload['label']}) classified by the multimodal model as "
        f"{cj['modulation_class']} / {cj['protocol_inferred']}. Anomaly "
        f"flag: {cj['anomaly_flag']}; recommend the actions below before "
        f"the next sweep.\n\n"
        f"(U) Capture Header & Bandwidth\n"
        f"Center {md['center_freq_GHz']} GHz, BW {md['bw_MHz']} MHz, "
        f"sample rate {md['sample_rate_MSPS']:.1f} MS/s, gain "
        f"{md['gain_dB']} dB on {md['hardware']}. Noise floor "
        f"{md['noise_floor_dBm']} dBm; calibration: {md['calibration']}.\n\n"
        f"(U) Top Emitters Identified\n"
        f"Inferred device class: {cj['device_class_hypothesis']}. Estimated "
        f"{cj['estimated_burst_count']} bursts in the 1-second window with a "
        f"duty cycle of ~{cj['duty_cycle_estimate_pct']:.1f}% at "
        f"{cj['signal_strength_band']} strength.\n\n"
        f"(U) Anomalies / Unauthorized Activity\n"
        f"Classifier flag: {cj['anomaly_flag']}. "
        + (
            "No further action beyond routine logging."
            if cj["anomaly_flag"] == "nominal"
            else "Recommend immediate operator escalation per below."
        )
        + "\n\n"
        f"(U) Recommended Spectrum Manager Actions\n"
        f"1) Cross-reference inferred protocol against the FOB authorized "
        f"emitter list. 2) Re-cap on the same center frequency in 5 minutes "
        f"to confirm persistence. 3) If anomaly_flag != nominal, push to "
        f"GHOST for pattern-of-life correlation against the perimeter scan.\n\n"
        f"(U) Confidence\n"
        f"MED — single-snapshot evidence; recommend a 3-capture corroboration "
        f"window before any kinetic action. (Deterministic fallback brief.)"
    )


def _precompute_briefs() -> None:
    """Cache-first hero call. Pre-compute the spectrum-awareness brief for all
    six scenarios so the demo never sits on a spinner."""
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))
    try:
        from shared.kamiwaza_client import chat  # noqa: WPS433
    except Exception as e:  # noqa: BLE001
        print(f"[precompute] shared client unavailable, writing fallbacks: {e}")
        chat = None  # type: ignore[assignment]

    cached: dict[str, str] = {}
    for sc in SCENARIOS:
        payload = _build_brief_payload(sc)
        user = (
            f"Capture: {payload['capture']} ({payload['label']})\n"
            f"Site: {payload['site']}\n"
            f"Metadata (SigMF-compatible):\n"
            + json.dumps(payload["metadata"], indent=2)
            + "\n\nMultimodal classifier JSON output for this capture:\n"
            + json.dumps(payload["classifier_json"], indent=2)
            + "\n\nWrite the RF Spectrum Awareness Brief now."
        )
        text = ""
        if chat is not None:
            for hero_model in ("gpt-5.4", "gpt-5.4-mini", None):
                try:
                    print(f"[precompute] generating brief: {payload['capture']} "
                            f"(model={hero_model or 'chain-default'}) ...")
                    text = chat(
                        [
                            {"role": "system", "content": SYSTEM_BRIEF},
                            {"role": "user", "content": user},
                        ],
                        model=hero_model,
                        temperature=0.4,
                    )
                    if text and text.strip():
                        break
                except Exception as e:  # noqa: BLE001
                    print(f"[precompute] {hero_model} failed for "
                            f"{payload['capture']}: {e}")
                    continue
        if not text:
            print(f"[precompute] using deterministic fallback for {payload['capture']}")
            text = _fallback_brief(payload)
        cached[payload["capture"]] = text

    out = OUT_DIR / "cached_briefs.json"
    out.write_text(json.dumps(cached, indent=2))
    print(f"[precompute] wrote {out}")


# ─────────────────────────────────────────────────────────────────────────────
# Main entry — synthesize captures + metadata + vendor map
# ─────────────────────────────────────────────────────────────────────────────
def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    CAP_DIR.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(SEED)

    # 1. Synthesize captures
    print(f"Synthesizing {len(SCENARIOS)} I/Q captures @ {SYN_FS/1e6:.1f} MS/s, "
            f"{DUR_SEC}s each ({N_SAMPLES} samples, complex64) ...")
    for sc in SCENARIOS:
        iq = synth_capture(sc["scenario_id"], rng)
        path = CAP_DIR / f"{sc['scenario_id']}.npy"
        np.save(path, iq)
        rms = float(np.sqrt(np.mean(np.abs(iq) ** 2)))
        print(f"  wrote {path.name}  ({iq.nbytes/1e6:.1f} MB, RMS={rms:.3f}, "
                f"flag={sc['expected_anomaly']})")

    # 2. Metadata CSV (SigMF-compatible field names)
    md_path = OUT_DIR / "captures_metadata.csv"
    with md_path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=[
            "scenario_id", "label", "filename", "synth_sample_rate_MSPS",
            "nist_sample_rate_MSPS", "center_freq_GHz", "bw_MHz", "gain_dB",
            "hardware", "noise_floor_dBm", "calibration", "expected_anomaly",
        ])
        w.writeheader()
        for sc in SCENARIOS:
            w.writerow({
                "scenario_id":             sc["scenario_id"],
                "label":                   sc["label"],
                "filename":                f"captures/{sc['scenario_id']}.npy",
                "synth_sample_rate_MSPS":  SYN_FS / 1_000_000.0,
                "nist_sample_rate_MSPS":   NIST_FS / 1_000_000.0,
                "center_freq_GHz":         sc["center_freq_GHz"],
                "bw_MHz":                  sc["bw_MHz"],
                "gain_dB":                 sc["gain_dB"],
                "hardware":                sc["hardware"],
                "noise_floor_dBm":         sc["noise_floor_dBm"],
                "calibration":             sc["calibration"],
                "expected_anomaly":        sc["expected_anomaly"],
            })
    print(f"Wrote {md_path}")

    # 3. Vendor / protocol map (20+ entries)
    vmap_path = OUT_DIR / "vendor_protocol_map.json"
    vmap_path.write_text(json.dumps(VENDOR_PROTOCOL_MAP, indent=2))
    print(f"Wrote {vmap_path}")

    print("Synthesis complete.")


if __name__ == "__main__":
    main()
    if os.getenv("SKIP_PRECOMPUTE") != "1":
        _precompute_briefs()
