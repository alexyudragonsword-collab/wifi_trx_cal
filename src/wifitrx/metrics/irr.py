"""Measured image-rejection and LO-leakage metrics from captures."""
from __future__ import annotations

import numpy as np


def tone_image_irr_db(y: np.ndarray, f_tone_hz: float, fs: float) -> float:
    """IRR of a single-tone capture: direct bin over image bin [dB]."""
    n = y.size
    spec = np.fft.fft(y) / n
    k = int(round(f_tone_hz * n / fs)) % n
    direct = np.abs(spec[k])
    image = np.abs(spec[-k % n])
    return float(20.0 * np.log10(max(direct, 1e-300) / max(image, 1e-300)))


def comb_irr_db(y: np.ndarray, freqs_hz: np.ndarray, fs: float) -> np.ndarray:
    """Per-tone IRR for a one-sided multitone capture."""
    return np.array([tone_image_irr_db(y, f, fs) for f in np.atleast_1d(freqs_hz)])


def lo_leak_dbc(y: np.ndarray, fs: float, avg_bins: int = 1) -> float:
    """DC-bin power relative to total signal power [dBc].

    ``avg_bins``: half-width of extra bins around DC to include (leakage
    smeared by phase noise).
    """
    n = y.size
    spec = np.abs(np.fft.fft(y)) ** 2 / n ** 2
    idx = list(range(-avg_bins, avg_bins + 1))
    p_dc = float(np.sum(spec[np.array(idx) % n]))
    p_tot = float(np.mean(np.abs(y) ** 2))
    if p_tot <= p_dc:
        return 0.0
    return 10.0 * np.log10(max(p_dc, 1e-300) / (p_tot - p_dc))


def dc_dbfs(x: np.ndarray) -> float:
    """Mean DC power of a digital capture relative to full scale (=1)."""
    dc = np.mean(x)
    return float(20.0 * np.log10(max(abs(dc), 1e-300)))
