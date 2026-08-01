"""RX DC-offset calibration: per-AGC-state analog trim + digital table.

With the antenna terminated (no input), each LNA gain state's composite DC
(LO self-mixing + baseband offsets, gain-state dependent) is measured at
the ADC output in two stages:

1. COARSE (analog): the reading is referred back to the baseband node
   (divide by the VGA gain, ADC full-scale re-applied) and programmed
   into the per-state analog trim DAC.  This stage is what protects the
   VGA/ADC headroom: at sensitivity levels the VGA rails at +40 dB and
   an uncorrected analog DC would clip the ADC outright — a digital
   subtraction cannot undo that (backlog B4).
2. FINE (digital): the post-trim residual (trim-DAC quantization plus
   estimation error) is averaged again and stored in the digital
   subtraction table.

Thermal noise sets the averaging length: the residual scales as
sigma/sqrt(N).
"""
from __future__ import annotations

import numpy as np

from ..chain.rx import RxChain
from ..metrics.irr import dc_dbfs
from .base import CalResult


def calibrate_rx_dc(rx: RxChain, n: int = 1 << 14, seed: int = 0) -> CalResult:
    p = rx.params
    rng = np.random.default_rng(seed)
    before, mid, after = {}, {}, {}
    tbl_ana, tbl_post = {}, {}
    saved_idx, saved_vga = rx.lna_idx, rx.vga_db
    rx.dc_ana = {}
    rx.dc_post = {}
    a_fs = p.adc.a_fs
    # defined measurement condition: a moderate VGA where even the
    # worst-case RAW analog DC cannot clip the ADC (the whole point of
    # the coarse stage is that at high VGA it would) — and both
    # corrections are stored node-referred, so they remain valid at
    # whatever VGA the runtime AGC lands on
    rx.vga_db = 20.0
    vga_lin = 10.0 ** (rx.vga_db / 20.0)

    for idx in range(len(p.lna_states)):
        rx.lna_idx = idx
        x = rx(np.zeros(n, dtype=complex), rng=rng)
        before[idx] = dc_dbfs(x)
        # coarse: refer the digital reading to the analog baseband node
        # (undo ADC full-scale and VGA gain; LPF DC gain is ~1) and
        # program the trim DAC — the hardware realizes it quantized
        tbl_ana[idx] = complex(np.mean(x)) * a_fs / vga_lin
        rx.dc_ana[idx] = tbl_ana[idx]
        x2 = rx(np.zeros(n, dtype=complex), rng=rng)
        mid[idx] = dc_dbfs(x2)
        # fine: node-referred residual for the VGA-scaled digital trim
        dc = complex(np.mean(x2)) * a_fs / vga_lin
        tbl_post[idx] = dc
        rx.dc_post[idx] = dc
        x3 = rx(np.zeros(n, dtype=complex), rng=rng)
        after[idx] = dc_dbfs(x3)

    rx.lna_idx, rx.vga_db = saved_idx, saved_vga
    worst_after = max(after.values())
    return CalResult(
        name="rx_dc_offset",
        estimated={f"state{idx}": tbl_post[idx] for idx in tbl_post},
        corrections={
            "dc_ana": {str(k): [v.real, v.imag] for k, v in tbl_ana.items()},
            "dc_post": {str(k): [v.real, v.imag] for k, v in tbl_post.items()},
        },
        metrics_before={f"dc_dbfs_state{k}": v for k, v in before.items()},
        metrics_after={"worst_dc_dbfs": worst_after,
                       "worst_dc_dbfs_after_analog": max(mid.values()),
                       **{f"dc_dbfs_state{k}": v for k, v in after.items()}},
        passed=worst_after < -50.0,
        spec={"metric": "worst_dc_dbfs", "limit": -50.0, "sense": "max"},
        cost={"captures": 3 * len(p.lna_states),
              "samples": 3 * len(p.lna_states) * n},
    )
