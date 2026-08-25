"""Array-gain validation of the MIMO alignment + decoupling calibrations.

Equal-weight beamforming toward broadside: all chains transmit the same
tone; the far-field sum of the antenna-port outputs should show the ideal
coherent array gain 20*log10(N) over a single chain.  LO-distribution
skew (phase/delay) and inter-chain coupling both eat into it; the
comparison un-aligned -> aligned -> aligned+decoupled quantifies what
each calibration buys.
"""
from __future__ import annotations

import numpy as np

from ..chain.mimo import MimoTrx
from ..waveform.stimuli import single_tone


def array_gain_db(mimo: MimoTrx, f_probe: float = 23e6, n: int = 1 << 13,
                  amp: float = 0.05) -> float:
    """Far-field coherent gain of equal-weight transmission vs chain 0."""
    n_ch = mimo.params.n_chains
    tone = single_tone(f_probe, mimo.fs, n, amp=amp)

    x_single = np.zeros((n_ch, n), dtype=complex)
    x_single[0] = tone
    p_single = np.mean(np.abs(np.sum(mimo.tx_all(x_single), axis=0)) ** 2)

    x_all = np.tile(tone, (n_ch, 1))
    p_all = np.mean(np.abs(np.sum(mimo.tx_all(x_all), axis=0)) ** 2)
    return float(10 * np.log10(p_all / p_single))


def beamforming_study(mimo_factory, path=None) -> dict:
    """Array gain for un-aligned / aligned / aligned+decoupled setups.

    ``mimo_factory()`` must return a freshly impaired MimoTrx each call.
    """
    from ..cal.mimo_align import calibrate_mimo_align, calibrate_mimo_decouple

    out = {}
    mimo = mimo_factory()
    n_ch = mimo.params.n_chains
    out["ideal_db"] = float(20 * np.log10(n_ch))
    out["unaligned_db"] = array_gain_db(mimo)

    mimo = mimo_factory()
    calibrate_mimo_align(mimo, path)
    out["aligned_db"] = array_gain_db(mimo)

    mimo = mimo_factory()
    calibrate_mimo_align(mimo, path)
    calibrate_mimo_decouple(mimo, path)
    out["aligned_decoupled_db"] = array_gain_db(mimo)
    return out
