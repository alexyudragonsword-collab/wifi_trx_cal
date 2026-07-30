"""Calibration stimuli: tones, asymmetric multitone combs, DC probes.

All stimuli are digital-domain (full-scale units, |x| <= 1 headroom left to
the caller via ``amp``) and FFT-grid coherent for leakage-free bin readout.
"""
from __future__ import annotations

import numpy as np


def scaled_probe(f_ref_hz: float, bandwidth_hz: float,
                 bw_ref_hz: float = 80e6) -> float:
    """Scale a probe frequency proven at ``bw_ref_hz`` down with bandwidth.

    Calibration stimuli must live inside the channel: a probe frequency
    that was chosen for wide modes (e.g. 23 MHz) sits OUTSIDE a 20 MHz
    channel and beyond its LPF corner, so the measurement runs on a tone
    attenuated by ~25 dB — the IIP2 trim then walks on noise and the AGC
    sweep reads no SNR at all.  Wide modes keep the proven value; narrow
    modes scale it proportionally.
    """
    return f_ref_hz * min(1.0, bandwidth_hz / bw_ref_hz)


def grid_freq(f_target: float, fs: float, n: int) -> float:
    """Snap a frequency onto the length-n FFT grid."""
    return round(f_target * n / fs) * fs / n


def single_tone(f_hz: float, fs: float, n: int, amp: float = 0.5,
                phase: float = 0.0) -> np.ndarray:
    """Complex tone snapped to the FFT grid."""
    f = grid_freq(f_hz, fs, n)
    t = np.arange(n) / fs
    return amp * np.exp(1j * (2 * np.pi * f * t + phase))


def multitone(freqs_hz: np.ndarray, fs: float, n: int, amp_total: float = 0.5,
              seed: int = 0) -> tuple[np.ndarray, np.ndarray]:
    """Multitone comb with random phases (PAPR control), grid-snapped.

    Returns (x, f_actual).  Callers doing image estimation should pass
    one-sided frequencies (all positive or all negative) so every image bin
    is free of direct-tone content.
    """
    rng = np.random.default_rng(seed)
    freqs = np.array([grid_freq(f, fs, n) for f in np.atleast_1d(freqs_hz)])
    if np.unique(np.abs(freqs)).size != freqs.size:
        raise ValueError("tone collision after grid snapping (|f| not unique)")
    t = np.arange(n) / fs
    amp = amp_total / np.sqrt(freqs.size)
    x = np.zeros(n, dtype=complex)
    for f in freqs:
        x += amp * np.exp(1j * (2 * np.pi * f * t + rng.uniform(0, 2 * np.pi)))
    return x, freqs


def iq_cal_comb(bandwidth_hz: float, fs: float, n: int, n_tones: int = 16,
                amp_total: float = 0.4, seed: int = 0,
                sign: int = +1) -> tuple[np.ndarray, np.ndarray]:
    """One-sided comb spanning ~90% of the half-band for IQ-image estimation.

    ``sign=+1`` places tones at positive frequencies (images land at -f),
    ``sign=-1`` mirrors.  Frequencies avoid DC and the band edge.
    """
    f_lo = 0.04 * bandwidth_hz / 2
    f_hi = 0.92 * bandwidth_hz / 2
    freqs = sign * np.linspace(f_lo, f_hi, n_tones)
    return multitone(freqs, fs, n, amp_total=amp_total, seed=seed)


def bin_value(x: np.ndarray, f_hz: float, fs: float) -> complex:
    """Complex amplitude of the FFT bin nearest f_hz (coherent readout)."""
    n = x.size
    k = int(round(f_hz * n / fs)) % n
    return complex(np.fft.fft(x)[k] / n)
