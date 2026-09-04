"""Per-symbol common phase error (CPE) removal for EVM measurement.

Modems track the common phase rotation of each OFDM symbol from pilot
tones; EVM against the standard is therefore measured after CPE removal.

Two estimators live here.  ``correct_cpe`` is a genie: it fits the
rotation on every subcarrier against the ideal reference, so its own
estimation noise is negligible and what it leaves behind is the ICI
floor of the phase noise itself.  ``correct_cpe_pilots`` is the modem's
form — N_p known pilots only — and carries the pilot estimator's noise
onto every data subcarrier as a common-mode error.  The gap between the
two is a mechanism, not a bug; the phase-noise/CPE study measures it.
"""
from __future__ import annotations

import numpy as np


def correct_cpe(rx_symbols: np.ndarray, ref_symbols: np.ndarray) -> np.ndarray:
    """Rotate each OFDM symbol by its LS common phase vs the reference."""
    rx = np.asarray(rx_symbols, dtype=complex)
    ref = np.asarray(ref_symbols, dtype=complex)
    out = rx.copy()
    for i in range(rx.shape[0]):
        acc = np.vdot(rx[i], ref[i])
        if abs(acc) > 0:
            out[i] = rx[i] * (acc / abs(acc))
    return out


def correct_cpe_pilots(rx_symbols: np.ndarray, pilot_cols: np.ndarray,
                       pilots: np.ndarray) -> np.ndarray:
    """Rotate each OFDM symbol by the LS common phase of its pilots only.

    ``pilot_cols`` index the pilot tones along the n_active axis and
    ``pilots`` (n_symbols, n_pilots) are their known values — the same
    inputs the tracking loop reads.  Same arithmetic as ``correct_cpe``
    restricted to the pilot set, so the two differ only by how many
    tones the estimate averages over.
    """
    rx = np.asarray(rx_symbols, dtype=complex)
    pil = np.asarray(pilots, dtype=complex)
    cols = np.asarray(pilot_cols, dtype=int)
    out = rx.copy()
    for i in range(rx.shape[0]):
        acc = np.vdot(rx[i, cols], pil[i])
        if abs(acc) > 0:
            out[i] = rx[i] * (acc / abs(acc))
    return out
