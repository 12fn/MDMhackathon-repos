"""Signal-processing helpers: FFT, envelope analysis, spectrogram, characteristic-band peaks."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.signal import hilbert, spectrogram


@dataclass
class CharFreqs:
    bpfo: float
    bpfi: float
    bsf: float
    ftf: float
    f_shaft: float


def characteristic_freqs(f_shaft: float = 1772.0 / 60.0) -> CharFreqs:
    """SKF 6205-2RS JEM geometry (CWRU drive-end canonical)."""
    n_balls, ball_d, pitch_d = 9, 0.3126, 1.537
    ratio = ball_d / pitch_d
    return CharFreqs(
        bpfo=(n_balls / 2.0) * f_shaft * (1 - ratio),
        bpfi=(n_balls / 2.0) * f_shaft * (1 + ratio),
        bsf=(pitch_d / (2 * ball_d)) * f_shaft * (1 - ratio ** 2),
        ftf=(f_shaft / 2.0) * (1 - ratio),
        f_shaft=f_shaft,
    )


def fft_mag(sig: np.ndarray, fs: int) -> tuple[np.ndarray, np.ndarray]:
    n = len(sig)
    s = sig - sig.mean()
    spec = np.fft.rfft(s * np.hanning(n))
    mag = np.abs(spec) / n * 2.0
    freqs = np.fft.rfftfreq(n, d=1.0 / fs)
    return freqs, mag


def envelope_spectrum(sig: np.ndarray, fs: int) -> tuple[np.ndarray, np.ndarray]:
    """Hilbert envelope, then FFT — classical bearing-fault demodulation."""
    s = sig - sig.mean()
    env = np.abs(hilbert(s))
    env = env - env.mean()
    n = len(env)
    spec = np.fft.rfft(env * np.hanning(n))
    mag = np.abs(spec) / n * 2.0
    freqs = np.fft.rfftfreq(n, d=1.0 / fs)
    return freqs, mag


def band_energy(freqs: np.ndarray, mag: np.ndarray, center: float, bw: float = 5.0) -> float:
    """Sum of magnitudes within +/- bw Hz of center freq."""
    mask = (freqs >= center - bw) & (freqs <= center + bw)
    if not mask.any():
        return 0.0
    return float(mag[mask].sum())


def spectrogram_image(sig: np.ndarray, fs: int) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Return (frequencies, times, Sxx) for plotting."""
    f, t, Sxx = spectrogram(sig, fs=fs, nperseg=256, noverlap=192, scaling="spectrum")
    Sxx = 10 * np.log10(Sxx + 1e-12)
    return f, t, Sxx


def hand_crafted_features(sig: np.ndarray, fs: int) -> np.ndarray:
    """Statistical + frequency-domain feature vector for the classifier."""
    s = sig.astype(np.float64)
    rms = float(np.sqrt(np.mean(s ** 2)))
    peak = float(np.max(np.abs(s)))
    crest = peak / (rms + 1e-9)
    mean = float(np.mean(s))
    std = float(np.std(s))
    skew = float(np.mean(((s - mean) / (std + 1e-9)) ** 3))
    kurt = float(np.mean(((s - mean) / (std + 1e-9)) ** 4))
    p2p = float(np.ptp(s))
    impulse_factor = peak / (np.mean(np.abs(s)) + 1e-9)
    shape_factor = rms / (np.mean(np.abs(s)) + 1e-9)
    margin_factor = peak / (np.mean(np.sqrt(np.abs(s))) + 1e-9) ** 2

    # Envelope-spectrum band energies at characteristic freqs
    cf = characteristic_freqs()
    f_env, m_env = envelope_spectrum(s, fs)
    e_bpfo = band_energy(f_env, m_env, cf.bpfo, bw=4)
    e_bpfi = band_energy(f_env, m_env, cf.bpfi, bw=4)
    e_bsf = band_energy(f_env, m_env, cf.bsf, bw=4)
    e_ftf = band_energy(f_env, m_env, cf.ftf, bw=2)

    # Sidebands at shaft rate around BPFI (inner-race signature)
    e_bpfi_sb_lo = band_energy(f_env, m_env, cf.bpfi - cf.f_shaft, bw=3)
    e_bpfi_sb_hi = band_energy(f_env, m_env, cf.bpfi + cf.f_shaft, bw=3)

    # Raw-spectrum total energy in mid + high band
    f_raw, m_raw = fft_mag(s, fs)
    e_low = float(m_raw[(f_raw < 200)].sum())
    e_mid = float(m_raw[(f_raw >= 200) & (f_raw < 2000)].sum())
    e_high = float(m_raw[f_raw >= 2000].sum())

    return np.array(
        [
            rms, peak, crest, std, skew, kurt, p2p,
            impulse_factor, shape_factor, margin_factor,
            e_bpfo, e_bpfi, e_bsf, e_ftf,
            e_bpfi_sb_lo, e_bpfi_sb_hi,
            e_low, e_mid, e_high,
        ],
        dtype=np.float32,
    )
