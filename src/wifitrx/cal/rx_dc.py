"""RX DC-offset calibration: per-AGC-state digital DC table.

With the antenna terminated (no input), each LNA gain state's composite DC
(LO self-mixing + baseband offsets, gain-state dependent) is averaged at the
ADC output and stored in the per-state subtraction table.  Thermal noise
sets the averaging length: the residual scales as sigma/sqrt(N).
"""
from __future__ import annotations

import numpy as np

from ..chain.rx import RxChain
from ..metrics.irr import dc_dbfs
from .base import CalResult


def calibrate_rx_dc(rx: RxChain, n: int = 1 << 14, seed: int = 0) -> CalResult:
    p = rx.params
    rng = np.random.default_rng(seed)
    before, after, table = {}, {}, {}
    saved_idx, saved_vga = rx.lna_idx, rx.vga_db
    rx.dc_post = {}

    for idx in range(len(p.lna_states)):
        rx.lna_idx = idx
        x = rx(np.zeros(n, dtype=complex), rng=rng)
        before[idx] = dc_dbfs(x)
        dc = complex(np.mean(x))
        table[idx] = dc
        rx.dc_post[idx] = dc
        x2 = rx(np.zeros(n, dtype=complex), rng=rng)
        after[idx] = dc_dbfs(x2)

    rx.lna_idx, rx.vga_db = saved_idx, saved_vga
    worst_after = max(after.values())
    return CalResult(
        name="rx_dc_offset",
        estimated={f"state{idx}": table[idx] for idx in table},
        corrections={"dc_post": {str(k): [v.real, v.imag] for k, v in table.items()}},
        metrics_before={f"dc_dbfs_state{k}": v for k, v in before.items()},
        metrics_after={"worst_dc_dbfs": worst_after,
                       **{f"dc_dbfs_state{k}": v for k, v in after.items()}},
        passed=worst_after < -50.0,
        spec={"metric": "worst_dc_dbfs", "limit": -50.0, "sense": "max"},
        cost={"captures": 2 * len(p.lna_states),
              "samples": 2 * len(p.lna_states) * n},
    )
