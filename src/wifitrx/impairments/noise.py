"""Thermal noise injection in dBm units.

The RX chain injects noise ONCE at its input, using the cascaded noise
figure of the currently selected gain state (Friis handled at the parameter
level in ``link.budget``), which avoids double counting per-stage noise.
"""
from __future__ import annotations

import numpy as np

from ..units import KT_DBM_HZ, dbm_to_mw


def noise_at_density(n: int, fs: float, density_dbm_hz: float,
                     rng: np.random.Generator) -> np.ndarray:
    """Complex AWGN of a given power density [dBm/Hz] over the full
    simulation bandwidth fs (later shaped by the channel filter).

    Absolute density rather than a noise figure: the analog baseband is
    specified by its own noise voltage, not by an NF against a source
    it does not have (see impairments/baseband.py).
    """
    p_mw = dbm_to_mw(density_dbm_hz) * fs
    sigma = np.sqrt(p_mw / 2.0)
    return sigma * (rng.standard_normal(n) + 1j * rng.standard_normal(n))


def thermal_noise(n: int, fs: float, nf_db: float,
                  rng: np.random.Generator) -> np.ndarray:
    """Complex AWGN of density kT + NF [dBm/Hz]."""
    return noise_at_density(n, fs, KT_DBM_HZ + nf_db, rng)


def awgn_snr(x: np.ndarray, snr_db: float, rng: np.random.Generator) -> np.ndarray:
    """Add complex AWGN at a given SNR relative to the mean power of x."""
    p_sig = np.mean(np.abs(x) ** 2)
    p_n = p_sig / 10.0 ** (snr_db / 10.0)
    sigma = np.sqrt(p_n / 2.0)
    return x + sigma * (rng.standard_normal(x.size) + 1j * rng.standard_normal(x.size))
