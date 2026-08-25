# Cascade math adapted from receiver_link_budget:modules/{nf,ip3}_calculator.py
# (Friis referred to the input; simplified to the wifitrx chain stages).
# See PROVENANCE.md.
"""RX cascade link budget: NF, IIP3, sensitivity."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from ..units import KT_DBM_HZ


@dataclass(frozen=True)
class Stage:
    name: str
    gain_db: float
    nf_db: float
    iip3_dbm: float | None = None


def cascade_nf_db(stages: list[Stage]) -> float:
    """Friis noise figure of the cascade, referred to the first input."""
    f_tot = 0.0
    g_acc = 1.0
    for i, st in enumerate(stages):
        f = 10.0 ** (st.nf_db / 10.0)
        if i == 0:
            f_tot = f
        else:
            f_tot += (f - 1.0) / g_acc
        g_acc *= 10.0 ** (st.gain_db / 10.0)
    return float(10.0 * np.log10(f_tot))


def cascade_iip3_dbm(stages: list[Stage]) -> float:
    """Input-referred IP3 of the cascade (inverse-power sum)."""
    inv = 0.0
    g_acc_db = 0.0
    for st in stages:
        if st.iip3_dbm is not None:
            iip3_at_input = st.iip3_dbm - g_acc_db
            inv += 10.0 ** (-iip3_at_input / 10.0)
        g_acc_db += st.gain_db
    if inv <= 0.0:
        return float("inf")
    return float(-10.0 * np.log10(inv))


def adc_equivalent_stage(bits: int, fullscale_dbm: float, backoff_db: float,
                         fs_hz: float, bw_hz: float) -> Stage:
    """ADC quantization noise as an equivalent NF stage at the ADC input.

    Quantization noise power (complex, both rails): 2 * q^2/12 spread over
    fs; in-band share bw/fs.  NF is referred to the thermal floor at the
    ADC input for a signal at (fullscale - backoff).
    """
    q_dbfs = -(6.02 * bits + 1.76) + 10.0 * np.log10(bw_hz / (fs_hz / 2.0))
    p_noise_dbm = fullscale_dbm + q_dbfs
    thermal_dbm = KT_DBM_HZ + 10.0 * np.log10(bw_hz)
    nf = max(p_noise_dbm - thermal_dbm, 0.0)
    return Stage("adc", gain_db=0.0, nf_db=nf, iip3_dbm=None)


def baseband_equivalent_stage(baseband, vga_db: float = 0.0) -> Stage:
    """The analog baseband's noise and ceiling as one cascade stage.

    Same trick as :func:`adc_equivalent_stage`: the block is specified by
    an absolute noise voltage density and an output swing, not by a noise
    figure and an input IP3, so convert both to what a stage sitting at
    the baseband node would need.

    Both numbers are expressed **at that stage's own input** — the
    cascade functions refer them onward by the accumulated gain, so
    pre-referring here would divide by the RF gain twice.  The IP3 term
    does carry the VGA gain that follows it, because the compression is
    an output ceiling: more VGA gain means less input room.
    """
    excess = 10.0 ** ((baseband.psd_dbm_hz() - KT_DBM_HZ) / 10.0)
    return Stage("baseband", gain_db=0.0,
                 nf_db=float(10.0 * np.log10(1.0 + excess)),
                 iip3_dbm=baseband.oip3_dbm() - vga_db)


def rx_stages(state, baseband=None, vga_db: float = 0.0,
              adc: Stage | None = None) -> list[Stage]:
    """RF front-end state (+ optional baseband, VGA and ADC) as a cascade.

    The VGA is a gain-only stage: its own noise and compression belong to
    the baseband block that contains it.
    """
    stages = [Stage("rf", gain_db=state.gain_db, nf_db=state.nf_db,
                    iip3_dbm=state.iip3_dbm)]
    if baseband is not None and baseband.enabled:
        stages.append(baseband_equivalent_stage(baseband, vga_db))
    stages.append(Stage("vga", gain_db=vga_db, nf_db=0.0))
    if adc is not None:
        stages.append(adc)
    return stages


def effective_nf_db(state, baseband=None, vga_db: float = 0.0,
                    adc: Stage | None = None) -> float:
    """Input-referred NF of the state, including the baseband stage."""
    return cascade_nf_db(rx_stages(state, baseband, vga_db, adc))


def effective_iip3_dbm(state, baseband=None, vga_db: float = 0.0) -> float:
    """Input-referred IIP3 of the state, including the baseband stage.

    Note the baseband term moves with the VGA setting, which is the
    whole point: its compression is an output ceiling, so a higher VGA
    gain refers to a lower input power.
    """
    return cascade_iip3_dbm(rx_stages(state, baseband, vga_db))


def deembed_states(states, baseband):
    """Split the cascaded NF totals into the RF-only ladder they imply.

    The delivered ``lna_states`` table is the *cascade*: NF referred to
    the antenna with the baseband contribution already inside.  Enabling
    the baseband stage therefore needs the RF-only figure, or the same
    noise is counted twice.

    Only NF is de-embedded.  The table's IIP3 column describes the RF
    front end ("LNA + mixer folded together") and never contained an
    output-referred baseband ceiling — the two live at different nodes,
    and combining them is what :func:`effective_iip3_dbm` is for.

    Raises when a state's stated total is smaller than the baseband
    contribution alone: not a rounding error but a contradiction between
    the ladder and the baseband specification, and which of the two is
    wrong is a question for the circuit team.
    """
    from ..chain.agc import LNAState

    bb = baseband_equivalent_stage(baseband)
    f_bb = 10.0 ** (bb.nf_db / 10.0) - 1.0          # excess noise factor
    out = []
    for i, st in enumerate(states):
        g_rf = 10.0 ** (st.gain_db / 10.0)
        f_tot = 10.0 ** (st.nf_db / 10.0)
        share = f_bb / g_rf                          # referred to the antenna
        if share >= f_tot - 1.0:
            raise ValueError(
                f"state {i}: the baseband stage alone contributes "
                f"{10 * np.log10(1 + share):.1f} dB of noise figure referred "
                f"to the antenna, but the table states {st.nf_db:.1f} dB for "
                f"the whole cascade — the ladder and "
                f"impairments/baseband.py disagree")
        out.append(LNAState(gain_db=st.gain_db,
                            nf_db=float(10.0 * np.log10(f_tot - share)),
                            iip3_dbm=st.iip3_dbm,
                            max_input_dbm=st.max_input_dbm))
    return tuple(out)


def sensitivity_dbm(nf_db: float, bw_hz: float, snr_req_db: float,
                    impl_loss_db: float = 0.0) -> float:
    return KT_DBM_HZ + 10.0 * np.log10(bw_hz) + nf_db + snr_req_db + impl_loss_db
