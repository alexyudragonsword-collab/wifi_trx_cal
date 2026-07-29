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


def sensitivity_dbm(nf_db: float, bw_hz: float, snr_req_db: float,
                    impl_loss_db: float = 0.0) -> float:
    return KT_DBM_HZ + 10.0 * np.log10(bw_hz) + nf_db + snr_req_db + impl_loss_db
