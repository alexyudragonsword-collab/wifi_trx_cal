"""Widely-linear correction FIR design from per-frequency image estimates.

Given the measured image ratio rho(f_k) on a set of calibration frequencies,
build the complex correction FIR w2 whose response approximates
W2(f) = -rho(f) across the signal band (frequency-sampling design with
linear interpolation between measurement points, edge-hold inside the band,
tapered to zero well outside it).
"""
from __future__ import annotations

import numpy as np


def design_w2_fir(freqs_hz: np.ndarray, rho: np.ndarray, fs: float,
                  n_taps: int = 31, band_hz: float | None = None) -> np.ndarray:
    """Complex FIR with center-tap group-delay reference.

    freqs_hz : measurement frequencies (any order, both signs).
    rho      : measured G2/G1-type image ratios at those frequencies; the
               FIR realizes W2 = -rho.
    band_hz  : one-sided band edge outside which the response tapers to 0
               (default: 1.1x the outermost measurement frequency).
    """
    freqs = np.asarray(freqs_hz, dtype=float)
    rho = np.asarray(rho, dtype=complex)
    order = np.argsort(freqs)
    freqs, rho = freqs[order], rho[order]
    if band_hz is None:
        band_hz = 1.1 * float(np.max(np.abs(freqs)))

    # dense target grid across the FULL Nyquist range: leaving any region
    # unconstrained lets the LS solution ring there and amplify conj-path
    # noise; the target rolls off to zero beyond the band via the taper
    n_grid = 1024
    f_grid = np.linspace(-fs / 2, fs / 2, n_grid, endpoint=False)
    w2 = np.interp(f_grid, freqs, rho.real, left=rho.real[0], right=rho.real[-1]) \
        + 1j * np.interp(f_grid, freqs, rho.imag, left=rho.imag[0], right=rho.imag[-1])
    taper = np.clip((1.5 * band_hz - np.abs(f_grid)) / (0.5 * band_hz), 0.0, 1.0)
    target = -w2 * taper

    # ridge-regularized least-squares fit of the center-referenced FIR
    m = n_taps + 1 - n_taps % 2  # odd
    n0 = (m - 1) / 2.0
    w = 2 * np.pi * f_grid / fs
    e = np.exp(-1j * np.outer(w, np.arange(m) - n0))
    a = e.conj().T @ e + 1e-9 * n_grid * np.eye(m)
    b = e.conj().T @ target
    return np.linalg.solve(a, b)


def fir_response(taps: np.ndarray, f_hz: np.ndarray, fs: float) -> np.ndarray:
    """Center-tap-referenced frequency response (matches convolve mode='same')."""
    taps = np.atleast_1d(taps)
    n0 = (taps.size - 1) / 2.0
    w = 2 * np.pi * np.asarray(f_hz, dtype=float) / fs
    k = np.arange(taps.size)
    return np.sum(taps[None, :] * np.exp(-1j * np.outer(w, k - n0)), axis=1)


def center_pad(taps: np.ndarray, n: int) -> np.ndarray:
    """Zero-pad ``taps`` to length ``n`` about its centre tap.

    Iterative IQ calibration composes corrections first-order as
    ``w2_total ~= w2_old + w2_new``, and the two designs need not have
    the same length; the centre tap is the group-delay reference
    (equivalent to ``np.convolve(mode="same")``), so padding has to stay
    symmetric about it.
    """
    return np.pad(taps, ((n - taps.size) // 2, (n - taps.size + 1) // 2))
