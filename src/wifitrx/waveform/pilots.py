"""802.11be-style pilot tone placement and insertion.

Pilot signed tone indices per bandwidth (11be data-and-pilot allocations;
the 320 MHz set follows the duplicated-160 MHz pattern).  Data OFDM from the
vendored generator fills all active tones; ``insert_pilots`` overwrites the
pilot positions with a known BPSK sequence so preamble-less tracking
(residual CFO/SCO, common phase error) is possible.
"""
from __future__ import annotations

import numpy as np

from .ofdm import OFDMConfig, OFDMWaveform, generate_ofdm

PILOT_TONES = {
    20e6: (-21, -7, 7, 21),
    40e6: (-53, -25, -11, 11, 25, 53),
    80e6: (-103, -75, -39, -11, 11, 39, 75, 103),
    160e6: (-231, -203, -167, -139, -117, -89, -53, -25,
            25, 53, 89, 117, 139, 167, 203, 231),
    320e6: (-487, -459, -423, -395, -373, -345, -309, -281,
            -231, -203, -167, -139, -117, -89, -53, -25,
            25, 53, 89, 117, 139, 167, 203, 231,
            281, 309, 345, 373, 395, 423, 459, 487),
}


def pilot_positions(config: OFDMConfig) -> np.ndarray:
    """Column indices (into the n_active axis) of the pilot tones."""
    tones = config.active_tone_indices()
    pilots = PILOT_TONES.get(config.bandwidth_hz)
    if pilots is None:
        # fallback: 8 evenly spaced tones
        idx = np.linspace(0, tones.size - 1, 10, dtype=int)[1:-1]
        return idx
    pos = []
    for p in pilots:
        hits = np.nonzero(tones == p)[0]
        if hits.size:
            pos.append(hits[0])
    return np.asarray(pos, dtype=int)


def pilot_sequence(n_symbols: int, n_pilots: int, seed: int = 42) -> np.ndarray:
    """Known BPSK pilot values, (n_symbols, n_pilots)."""
    rng = np.random.default_rng(seed)
    return (2.0 * rng.integers(0, 2, size=(n_symbols, n_pilots)) - 1.0).astype(complex)


def generate_ofdm_with_pilots(config: OFDMConfig,
                              pilot_seed: int = 42) -> tuple[OFDMWaveform, np.ndarray]:
    """Data OFDM with pilot positions overwritten by known BPSK.

    Returns (waveform, pilot_cols).
    """
    base = generate_ofdm(config)
    cols = pilot_positions(config)
    symbols = base.tx_symbols.copy()
    symbols[:, cols] = pilot_sequence(config.n_symbols, cols.size, pilot_seed)
    wf = generate_ofdm(config, symbols=symbols)
    return wf, cols
