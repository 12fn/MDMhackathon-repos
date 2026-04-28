"""SPECTRA signal-processing helpers.

Pure-numpy + scipy.signal, no LLM. Used by both the live UI render path and
the precompute path:

  - load_iq(npy_path)            -> complex64 1-D array
  - stft_db(iq, fs)              -> (freqs_Hz, times_s, dB) — for Plotly heatmap
  - psd_dbm(iq, fs, noise_floor) -> (freqs_Hz, dBm_per_Hz) — for the side PSD
  - spectrogram_image_png(iq, fs, ...) -> bytes — used as the LLM vision input
  - sigmf_header(meta_row)       -> str — pretty-printed SigMF-style header
  - quick_features(iq, fs)       -> dict — burst count, duty cycle, peak, RMS
"""
from __future__ import annotations

import io
from typing import Any

import numpy as np
from PIL import Image
from scipy.signal import stft, welch


def load_iq(path) -> np.ndarray:
    """Load a complex64 .npy I/Q file. Returns a 1-D complex64 array."""
    arr = np.load(path)
    if arr.dtype not in (np.complex64, np.complex128):
        # Some sources store interleaved float32 I,Q,I,Q,...
        if arr.dtype in (np.float32, np.float64) and arr.size % 2 == 0:
            arr = arr.astype(np.float32).view(np.complex64).reshape(-1)
        else:
            raise ValueError(
                f"Expected complex64 .npy I/Q, got dtype={arr.dtype} "
                f"shape={arr.shape}"
            )
    return arr.astype(np.complex64)


def stft_db(iq: np.ndarray, fs: float, *, nperseg: int = 256,
            noverlap: int = 192) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Short-time Fourier transform → magnitude in dB, fftshift'ed so DC is in
    the middle (matches a real spectrum-analyzer waterfall)."""
    f, t, Zxx = stft(iq, fs=fs, nperseg=nperseg, noverlap=noverlap,
                      return_onesided=False)
    # Center-shift frequencies so f goes from -fs/2 .. +fs/2
    f = np.fft.fftshift(f)
    Zxx = np.fft.fftshift(Zxx, axes=0)
    mag = np.abs(Zxx)
    db = 20.0 * np.log10(mag + 1e-9)
    return f, t, db


def psd_dbm(iq: np.ndarray, fs: float, *, noise_floor_dbm: float = -95.0
            ) -> tuple[np.ndarray, np.ndarray]:
    """Welch PSD with rough calibration to dBm/Hz (anchor the floor to the
    metadata `noise_floor_dBm`). Returns (freqs_Hz_centered, dBm_per_Hz)."""
    f, p = welch(iq, fs=fs, nperseg=1024, return_onesided=False)
    # Center
    order = np.argsort(f)
    f = f[order]
    p = p[order]
    # Convert to dB and rescale so the median ≈ noise_floor_dbm
    p_db = 10.0 * np.log10(p + 1e-12)
    delta = noise_floor_dbm - float(np.median(p_db))
    p_db = p_db + delta
    return f, p_db


def downsample_for_image(db: np.ndarray, *, target_size: int = 128) -> np.ndarray:
    """Downsample a 2-D dB matrix to roughly target_size on its largest axis,
    preserving aspect ratio. Used as the vision input."""
    rows, cols = db.shape
    biggest = max(rows, cols)
    if biggest <= target_size:
        return db
    stride_r = max(1, rows // target_size)
    stride_c = max(1, cols // target_size)
    return db[::stride_r, ::stride_c]


def _norm_to_8bit(db: np.ndarray, *, low_pct: float = 5.0,
                   high_pct: float = 99.0) -> np.ndarray:
    """Robust percentile normalization to uint8 for the vision model."""
    lo = float(np.percentile(db, low_pct))
    hi = float(np.percentile(db, high_pct))
    if hi <= lo:
        hi = lo + 1.0
    norm = (db - lo) / (hi - lo)
    norm = np.clip(norm, 0.0, 1.0)
    return (norm * 255.0).astype(np.uint8)


def _viridis_colormap(uint8: np.ndarray) -> np.ndarray:
    """Cheap viridis-like colormap RGB lookup — no matplotlib dependency."""
    # 6-stop colormap close to viridis
    stops = np.array([
        [68,   1,  84],   # dark purple
        [59,  82, 139],   # blue
        [33, 145, 140],   # teal
        [94, 201,  98],   # green
        [253, 231,  37],  # yellow
        [255, 255, 200],  # near-white highlight
    ], dtype=np.float32)
    n = stops.shape[0]
    pos = uint8.astype(np.float32) / 255.0 * (n - 1)
    lo_idx = np.floor(pos).astype(np.int32)
    hi_idx = np.minimum(lo_idx + 1, n - 1)
    frac = (pos - lo_idx)[..., None]
    rgb = stops[lo_idx] * (1 - frac) + stops[hi_idx] * frac
    return np.clip(rgb, 0, 255).astype(np.uint8)


def spectrogram_image_png(iq: np.ndarray, fs: float, *, max_side: int = 384
                            ) -> bytes:
    """Render a colored PNG of the STFT spectrogram. Used as the multimodal
    LLM input. Larger than the 128x128 numpy view so the model has detail
    to read."""
    _, _, db = stft_db(iq, fs)
    # downsample to roughly target image side (frequency axis usually larger)
    db_small = downsample_for_image(db, target_size=max_side)
    img8 = _norm_to_8bit(db_small)
    # Time axis along x, frequency along y. STFT returns (freq, time).
    rgb = _viridis_colormap(img8)
    img = Image.fromarray(rgb, mode="RGB")
    # If too tall/skinny, resize to a square-ish max_side
    w, h = img.size
    if max(w, h) > max_side:
        scale = max_side / max(w, h)
        img = img.resize((max(32, int(w * scale)), max(32, int(h * scale))),
                          Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, "PNG", optimize=True)
    return buf.getvalue()


def sigmf_header(meta: dict[str, Any]) -> str:
    """Pretty-print the metadata row as a SigMF-style YAML-ish header. This is
    what we drop into the vision-LLM user prompt."""
    return (
        "SigMF-compatible header:\n"
        f"  scenario_id           : {meta.get('scenario_id')}\n"
        f"  label                 : {meta.get('label')}\n"
        f"  center_freq_GHz       : {meta.get('center_freq_GHz')}\n"
        f"  bw_MHz                : {meta.get('bw_MHz')}\n"
        f"  synth_sample_rate_MSPS: {meta.get('synth_sample_rate_MSPS')}\n"
        f"  nist_sample_rate_MSPS : {meta.get('nist_sample_rate_MSPS')}\n"
        f"  gain_dB               : {meta.get('gain_dB')}\n"
        f"  hardware              : {meta.get('hardware')}\n"
        f"  noise_floor_dBm       : {meta.get('noise_floor_dBm')}\n"
        f"  calibration           : {meta.get('calibration')}\n"
    )


def quick_features(iq: np.ndarray, fs: float) -> dict[str, Any]:
    """Cheap deterministic feature set, used for: (a) the side panel KPIs and
    (b) the multimodal LLM prompt so the model has numeric ground truth in
    addition to the spectrogram image. Also feeds the deterministic fallback
    when the vision call times out."""
    if iq.size == 0:
        return {"rms": 0.0, "peak": 0.0, "duty_cycle_pct": 0.0,
                "burst_count": 0, "snr_estimate_dB": 0.0,
                "occupancy_pct": 0.0, "spectral_flatness": 0.0}

    mag = np.abs(iq)
    rms = float(np.sqrt(np.mean(mag ** 2)))
    peak = float(np.max(mag))

    # Burst detection: threshold the envelope at noise_rms * 3, count
    # rising edges, measure on-time
    noise_rms = float(np.median(mag))
    thresh = max(noise_rms * 3.0, 0.05)
    above = mag > thresh
    # rising edges
    edges = np.where(np.diff(above.astype(np.int8)) == 1)[0]
    burst_count = int(len(edges))
    duty_cycle = float(above.mean() * 100.0)

    # Spectral occupancy — fraction of FFT bins above the median
    n_fft = min(len(iq), 4096)
    fft = np.fft.fftshift(np.fft.fft(iq[:n_fft] * np.hanning(n_fft)))
    spec_mag = np.abs(fft)
    spec_db = 20.0 * np.log10(spec_mag + 1e-9)
    occ_thresh = float(np.median(spec_db)) + 6.0
    occupancy_pct = float((spec_db > occ_thresh).mean() * 100.0)

    # Spectral flatness (geometric mean / arithmetic mean of |spec|^2)
    p = (spec_mag ** 2) + 1e-12
    log_mean = float(np.exp(np.mean(np.log(p))))
    arith_mean = float(np.mean(p))
    spectral_flatness = float(log_mean / arith_mean) if arith_mean > 0 else 0.0

    # SNR estimate: peak above noise floor (in dB)
    snr = 20.0 * math_log10_safe(peak / max(noise_rms, 1e-6))

    return {
        "rms": rms,
        "peak": peak,
        "duty_cycle_pct": round(duty_cycle, 2),
        "burst_count": burst_count,
        "snr_estimate_dB": round(snr, 1),
        "occupancy_pct": round(occupancy_pct, 1),
        "spectral_flatness": round(spectral_flatness, 4),
    }


def math_log10_safe(x: float) -> float:
    if x <= 0:
        return -120.0
    return float(np.log10(x))
