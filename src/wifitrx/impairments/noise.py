"""Thermal noise injection in dBm units.

The RX chain injects noise ONCE at its input, using the cascaded noise
figure of the currently selected gain state (Friis handled at the parameter
level in ``link.budget``), which avoids double counting per-stage noise.
"""
from __future__ import annotations

import numpy as np

from ..units import KT_DBM_HZ, dbm_to_mw


def thermal_noise(n: int, fs: float, nf_db: float,
                  rng: np.random.Generator) -> np.ndarray:
    """Complex AWGN of density kT + NF [dBm/Hz] over the full simulation
    bandwidth fs (later shaped by the channel filter)."""
    density_dbm_hz = KT_DBM_HZ + nf_db
    p_mw = dbm_to_mw(density_dbm_hz) * fs
    sigma = np.sqrt(p_mw / 2.0)
    return sigma * (rng.standard_normal(n) + 1j * rng.standard_normal(n))


def awgn_snr(x: np.ndarray, snr_db: float, rng: np.random.Generator) -> np.ndarray:
    """Add complex AWGN at a given SNR relative to the mean power of x."""
    p_sig = np.mean(np.abs(x) ** 2)
    p_n = p_sig / 10.0 ** (snr_db / 10.0)
    sigma = np.sqrt(p_n / 2.0)
    return x + sigma * (rng.standard_normal(x.size) + 1j * rng.standard_normal(x.size))
