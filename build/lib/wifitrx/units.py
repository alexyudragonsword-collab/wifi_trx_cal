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

# The sqrt(mW) convention implies one reference impedance for the whole
# chain; name it rather than leaving it implicit, because the analog
# baseband is specified in volts (noise density in V/sqrt(Hz), swing in
# Vpp) and those numbers only convert to dBm against a stated impedance.
R_REF_OHM = 50.0


def v_sqrthz_to_dbm_hz(e_n, r_ohm: float = R_REF_OHM) -> np.ndarray | float:
    """Voltage noise density [V/sqrt(Hz)] -> power density [dBm/Hz].

    P = e_n^2 / R  [W/Hz], times 1000 for mW.  Check value: 10 nV/sqrt(Hz)
    at 50 ohm is -147.0 dBm/Hz (27 dB above kT, as a 50-ohm-referred
    baseband block should be).
    """
    e_n = np.asarray(e_n, dtype=float)
    return mw_to_dbm(1000.0 * e_n ** 2 / r_ohm)


def dbm_hz_to_v_sqrthz(p_dbm_hz, r_ohm: float = R_REF_OHM) -> np.ndarray | float:
    """Inverse of :func:`v_sqrthz_to_dbm_hz`."""
    return np.sqrt(dbm_to_mw(p_dbm_hz) / 1000.0 * r_ohm)


def vpp_to_dbm(v_pp, r_ohm: float = R_REF_OHM) -> np.ndarray | float:
    """Sine-wave peak-to-peak swing [V] -> mean power [dBm].

    An output swing is how a baseband amplifier's compression point is
    quoted.  Check value: 1.0 Vpp at 50 ohm is +3.98 dBm.
    """
    v_rms = np.asarray(v_pp, dtype=float) / (2.0 * np.sqrt(2.0))
    return mw_to_dbm(1000.0 * v_rms ** 2 / r_ohm)


def dbm_to_vpp(p_dbm, r_ohm: float = R_REF_OHM) -> np.ndarray | float:
    """Inverse of :func:`vpp_to_dbm`."""
    v_rms = np.sqrt(dbm_to_mw(p_dbm) / 1000.0 * r_ohm)
    return 2.0 * np.sqrt(2.0) * v_rms


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
