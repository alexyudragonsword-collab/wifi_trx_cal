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


DEFAULT_LNA_STATES = (
    LNAState(gain_db=36.0, nf_db=4.5, iip3_dbm=-12.0, max_input_dbm=-42.0),
    LNAState(gain_db=24.0, nf_db=6.5, iip3_dbm=-2.0, max_input_dbm=-30.0),
    LNAState(gain_db=12.0, nf_db=10.0, iip3_dbm=6.0, max_input_dbm=-18.0),
    LNAState(gain_db=0.0, nf_db=16.0, iip3_dbm=14.0, max_input_dbm=10.0),
)


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
