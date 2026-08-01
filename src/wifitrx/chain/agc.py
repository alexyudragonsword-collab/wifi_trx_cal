# AGC gain-selection logic adapted from
# receiver_link_budget:modules/agc_sweep.py (threshold-based RF state select +
# IF gain landing on a reference level), Qt-free.  See PROVENANCE.md.
"""RX AGC: LNA gain-state selection and VGA gain computation."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class LNAState:
    """One RF front-end gain state (LNA + mixer folded together)."""

    gain_db: float
    nf_db: float
    iip3_dbm: float
    max_input_dbm: float   # switch to the next (lower-gain) state above this


# Circuit-team ladder (2026-08 unified revision; see docs/backlog_zh.md
# history).  Hand-over thresholds derive from the boundary-IM3 rule
# 2*(IIP3 - max_input) >= 54 dBc (RX floor + 10 dB); state 3, being the
# last state, is IM3-limited above -19 dBm by its +8 dBm IIP3.
DEFAULT_LNA_STATES = (
    LNAState(gain_db=37.0, nf_db=3.5, iip3_dbm=-20.0, max_input_dbm=-47.0),
    LNAState(gain_db=25.0, nf_db=10.0, iip3_dbm=-9.0, max_input_dbm=-36.0),
    LNAState(gain_db=13.0, nf_db=22.0, iip3_dbm=0.0, max_input_dbm=-27.0),
    LNAState(gain_db=1.0, nf_db=30.0, iip3_dbm=8.0, max_input_dbm=10.0),
)

# Calibration-mode gain state: loopback observation captures pin this
# state (real cal firmware does the same) instead of walking the normal
# ladder — with the revised thresholds the 320 MHz observation level
# (~-21 dBm at the 34 dB cal coupler) would otherwise land in state 3,
# whose NF 30 buries the observation.  State 2 jointly optimizes thermal
# SNR vs mixer IM3 at that level.
CAL_OBSERVATION_STATE = 2


def select_lna_state(states: tuple[LNAState, ...], p_in_dbm: float) -> int:
    """First (highest-gain) state whose max input the signal stays below."""
    for i, st in enumerate(states):
        if p_in_dbm <= st.max_input_dbm:
            return i
    return len(states) - 1


def vga_gain_db(p_in_dbm: float, lna_gain_db: float,
                adc_target_dbm: float, vga_min_db: float = -10.0,
                vga_max_db: float = 40.0, step_db: float = 0.5) -> float:
    """VGA gain landing the mean signal power on the ADC reference level."""
    g = adc_target_dbm - (p_in_dbm + lna_gain_db)
    g = np.clip(g, vga_min_db, vga_max_db)
    return float(np.round(g / step_db) * step_db)
