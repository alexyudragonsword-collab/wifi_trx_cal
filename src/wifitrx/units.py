"""Power/amplitude unit conventions used across the whole chain.

Convention
----------
Complex baseband samples carry units of sqrt(mW): the mean signal power in
dBm is ``power_dbm(x) = 10*log10(mean(|x|^2))``.  Digital-domain samples
(DAC input, ADC output) are full-scale normalized (|I|, |Q| <= 1); the DAC
and ADC blocks own the conversion using their ``fullscale_dbm`` parameter,
defined as the mean power of a full-scale CW tone (|x| = 1 in digital
units maps to a tone of ``fullscale_dbm``).
"""
from __future__ import annotations

import numpy as np

KT_DBM_HZ = -173.975  # thermal noise density at 290 K [dBm/Hz]


def dbm_to_mw(p_dbm) -> np.ndarray | float:
    return 10.0 ** (np.asarray(p_dbm, dtype=float) / 10.0)


def mw_to_dbm(p_mw) -> np.ndarray | float:
    return 10.0 * np.log10(np.maximum(np.asarray(p_mw, dtype=float), 1e-300))


def db_to_lin(g_db) -> np.ndarray | float:
    """Power ratio from dB."""
    return 10.0 ** (np.asarray(g_db, dtype=float) / 10.0)


def db_to_amp(g_db) -> np.ndarray | float:
    """Amplitude ratio from dB."""
    return 10.0 ** (np.asarray(g_db, dtype=float) / 20.0)


def power_dbm(x: np.ndarray) -> float:
    """Mean power of a sqrt(mW)-scaled complex baseband signal, in dBm."""
    return float(mw_to_dbm(np.mean(np.abs(np.asarray(x)) ** 2)))


def peak_dbm(x: np.ndarray) -> float:
    """Peak envelope power in dBm."""
    return float(mw_to_dbm(np.max(np.abs(np.asarray(x)) ** 2)))


def scale_to_dbm(x: np.ndarray, target_dbm: float) -> np.ndarray:
    """Rescale x so that its mean power equals target_dbm."""
    p = np.mean(np.abs(x) ** 2)
    if p <= 0:
        return x
    return x * np.sqrt(dbm_to_mw(target_dbm) / p)


def papr_db(x: np.ndarray) -> float:
    p = np.abs(x) ** 2
    return float(10.0 * np.log10(np.max(p) / np.mean(p)))
