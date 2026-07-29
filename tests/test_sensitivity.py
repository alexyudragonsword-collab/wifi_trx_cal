"""Sensitivity cross-check: behavioral model vs analytic Friis budget.

Two independent paths to the same number (the sibling-project methodology:
an independent second implementation beats a golden number).  The RX here
is impairment-clean with LO phase noise off, so the comparison isolates
the noise/units/EVM plumbing — the chain the analytic budget also models.
"""
from __future__ import annotations

import numpy as np
import pytest

from wifitrx.chain import RxChain, RxParams
from wifitrx.link.sensitivity import measured_rx_evm_db, sensitivity_study
from wifitrx.link.spur_planning import FracNConfig, lock_time_s
from wifitrx.waveform import OFDMConfig

BW = 20e6
CFG = OFDMConfig(bandwidth_hz=BW, qam_order=64, n_symbols=4, oversampling=2)


def _clean_rx() -> RxChain:
    p = RxParams(bandwidth_hz=BW)
    p.lo.enabled = False          # isolate thermal noise from PN floor
    p.lpf.fc_nominal_hz = BW / 2 * 1.3
    rx = RxChain(p, CFG.sample_rate_hz)
    return rx


def test_evm_tracks_input_power_db_for_db():
    # noise-limited region: 6 dB more signal = 6 dB better EVM
    rx = _clean_rx()
    e1 = measured_rx_evm_db(rx, CFG, -80.0, seed=1)
    e2 = measured_rx_evm_db(rx, CFG, -74.0, seed=1)
    assert e2 - e1 == pytest.approx(-6.0, abs=1.0)


@pytest.mark.parametrize("idx", [0, 5, 9])
def test_measured_sensitivity_matches_friis(idx):
    rx = _clean_rx()
    rows = sensitivity_study(rx, CFG, [idx], seed=2)
    r = rows[0]
    # the two independent paths must agree; tolerance covers occupied-BW
    # vs nominal-BW and per-tone-EQ noise enhancement
    assert abs(r["delta_db"]) < 1.5, r


def test_sensitivity_ordering_across_mcs():
    rx = _clean_rx()
    rows = sensitivity_study(rx, CFG, [0, 5, 9], seed=2)
    meas = [r["measured_dbm"] for r in rows]
    assert meas == sorted(meas), rows  # higher MCS = worse sensitivity


def test_pll_lock_time_is_plausible_and_scales():
    cfg = FracNConfig()
    t = lock_time_s(cfg)
    assert 5e-6 < t < 200e-6      # WiFi-class synthesizer: tens of us
    # narrower loop locks slower
    slow = lock_time_s(FracNConfig(loop_bw_hz=cfg.loop_bw_hz / 4))
    assert slow == pytest.approx(4 * t)
    # already-on-frequency step needs no time
    assert lock_time_s(cfg, freq_step_hz=0.0) == 0.0
