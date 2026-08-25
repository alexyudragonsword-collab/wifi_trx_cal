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


# Official 8-state ladder (system-team table, 2026-08; history in
# docs/backlog_zh.md A3).  6 dB gain steps sample the analog
# gain/NF/IIP3 trade-off finely enough that RX EVM rides the balanced
# envelope with ~1.5 dB ripple; hand-over thresholds sit at the
# noise-vs-IM3 balance points t_i = (2*IIP3_i + NF_{i+1} - 89)/3
# (320 MHz anchored).  State 7 is the LNA-bypass/attenuator state: it
# extends strong-signal coverage and restores ADC headroom at extreme
# inputs.
DEFAULT_LNA_STATES = (
    LNAState(gain_db=37.0, nf_db=3.5, iip3_dbm=-20.0, max_input_dbm=-40.7),
    LNAState(gain_db=31.0, nf_db=6.0, iip3_dbm=-14.0, max_input_dbm=-36.0),
    LNAState(gain_db=25.0, nf_db=10.0, iip3_dbm=-9.0, max_input_dbm=-30.3),
    LNAState(gain_db=19.0, nf_db=16.0, iip3_dbm=-4.0, max_input_dbm=-25.3),
    LNAState(gain_db=13.0, nf_db=22.0, iip3_dbm=0.0, max_input_dbm=-21.0),
    LNAState(gain_db=7.0, nf_db=26.0, iip3_dbm=6.0, max_input_dbm=-17.0),
    LNAState(gain_db=1.0, nf_db=30.0, iip3_dbm=8.0, max_input_dbm=-13.0),
    LNAState(gain_db=-5.0, nf_db=34.0, iip3_dbm=12.0, max_input_dbm=10.0),
)

# Calibration-mode gain state: loopback observation captures pin this
# state (real cal firmware does the same) instead of walking the normal
# ladder — the 320 MHz observation level (~-21 dBm at the 34 dB cal
# coupler) would otherwise land in a high-NF state that buries the
# observation.  The NF-22 state (index 4 of the 8-state ladder) jointly
# optimizes thermal SNR vs mixer IM3 at that level.
CAL_OBSERVATION_STATE = 4


def rebalance_thresholds(states: tuple[LNAState, ...],
                         bandwidth_hz: float = 320e6,
                         effective: dict | None = None
                         ) -> tuple[LNAState, ...]:
    """Re-solve every hand-over threshold at its noise-vs-IM3 balance
    point, t_i = (2*IIP3_i + NF_{i+1} + (-174 + 10log10(BW))) / 3 —
    staying in state i costs 2 dB/dB of IM3 while entering state i+1
    costs 1 dB/dB of thermal SNR, and the balance point equalizes the
    two.  The last state's ceiling is kept.  Anchored at 320 MHz by the
    same convention as the official table; use this after any NF/IIP3
    what-if transform (e.g. the GUI's RX high-performance knob) so the
    thresholds track the modified ladder.

    ``effective`` optionally supplies ``{"nf_db": [...], "iip3_dbm":
    [...]}`` per state — the cascade values including an enabled
    baseband stage, computed by ``link.budget`` (this package may not
    import ``link``).  Without it the state's own numbers are used, as
    before."""
    from math import log10
    const = -174.0 + 10.0 * log10(bandwidth_hz)
    nfs = (effective or {}).get("nf_db") or [s.nf_db for s in states]
    ip3s = (effective or {}).get("iip3_dbm") or [s.iip3_dbm for s in states]
    out = []
    for i, s in enumerate(states):
        if i == len(states) - 1:
            out.append(s)
            continue
        t = (2.0 * ip3s[i] + nfs[i + 1] + const) / 3.0
        out.append(LNAState(gain_db=s.gain_db, nf_db=s.nf_db,
                            iip3_dbm=s.iip3_dbm,
                            max_input_dbm=round(t, 1)))
    return tuple(out)


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
