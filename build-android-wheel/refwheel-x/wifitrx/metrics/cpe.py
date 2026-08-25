"""Per-symbol common phase error (CPE) removal for EVM measurement.

Modems track the common phase rotation of each OFDM symbol from pilot
tones; EVM against the standard is therefore measured after CPE removal.
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
