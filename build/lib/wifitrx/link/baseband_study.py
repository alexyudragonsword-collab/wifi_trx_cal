"""What the explicit baseband stage changes, measured.

Two sweeps, one per effect the lumped per-state NF/IIP3 could not show
(backlog B5):

- :func:`vga_swing_study` holds the antenna power and walks the VGA away
  from the setting the AGC would choose.  With the baseband stage off
  this is flat by construction — the model has nothing that depends on
  the VGA; with it on, the post-VGA noise refers back through less gain
  and the input-referred NF rises.

- :func:`backoff_study` walks ``adc_backoff_db`` at a fixed antenna
  power.  Because the AGC servos the VGA *output* to a fixed level, the
  baseband's output-referred compression is the one impairment a gain
  state cannot escape: the only lever is backing further off the ADC
  full scale, at the cost of ADC quantization noise.  The minimum of
  that trade-off is the number this study exists to find.
"""
from __future__ import annotations

from dataclasses import replace

import numpy as np

from .budget import adc_equivalent_stage, effective_nf_db
from .sensitivity import measured_rx_evm_db


def vga_swing_study(rx, p_in_dbm: float = -60.0,
                    offsets_db=(-20.0, -10.0, 0.0, 10.0)) -> list[dict]:
    """Input-referred NF as the VGA is forced off its nominal landing."""
    p = rx.params
    rx.agc(p_in_dbm)
    state, nominal = p.lna_states[rx.lna_idx], rx.vga_db
    adc = adc_equivalent_stage(p.adc.bits, p.adc.fullscale_dbm,
                               p.adc_backoff_db, fs_hz=rx.fs,
                               bw_hz=p.bandwidth_hz)
    rows = []
    for off in offsets_db:
        vga = float(np.clip(nominal + off, -10.0, 40.0))
        rows.append({
            "vga_db": vga,
            "offset_db": vga - nominal,
            "nf_db": effective_nf_db(state, p.baseband, vga, adc),
        })
    rx.vga_db = nominal
    return rows


def backoff_study(rx, cfg, p_in_dbm: float = -40.0,
                  backoffs_db=(6.0, 9.0, 12.0, 15.0, 18.0),
                  seed: int = 0) -> list[dict]:
    """RX EVM against ADC backoff — the compression/quantization trade."""
    p = rx.params
    saved = p.adc_backoff_db
    rows = []
    for b in backoffs_db:
        p.adc_backoff_db = float(b)
        rows.append({"backoff_db": float(b),
                     "evm_db": measured_rx_evm_db(rx, cfg, p_in_dbm,
                                                  seed=seed)})
    p.adc_backoff_db = saved
    return rows


def compression_penalty_db(rx, cfg, p_in_dbm: float, seed: int = 0) -> float:
    """EVM cost of the baseband ceiling alone at one antenna power.

    Measured, not derived: the same chain with the stage's compression
    removed but its noise kept, so the difference is the ceiling.
    """
    p = rx.params
    with_bb = measured_rx_evm_db(rx, cfg, p_in_dbm, seed=seed)
    saved = p.baseband
    p.baseband = replace(saved, out_swing_vpp=1e6)   # ceiling out of reach
    without = measured_rx_evm_db(rx, cfg, p_in_dbm, seed=seed)
    p.baseband = saved
    return float(with_bb - without)
