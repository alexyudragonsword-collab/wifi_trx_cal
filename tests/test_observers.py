"""Readers must not move the part.

Measurement/verification functions (EVM snapshots, delay measurement,
metrics) may only *observe* the transceiver: any programmed correction
they leave behind is invisible to the calibration algorithms and shows up
later as an unexplainable state change.  The one declared exception is
AGC (``lna_idx``/``vga_db``) — runtime gain state, not a calibration
correction, and ``loopback_snapshot`` sets it on purpose.

(Idea ported from a sibling project, where two issues hid for many
sessions inside observers that silently perturbed the DUT.)
"""
from __future__ import annotations

import numpy as np
import pytest

from wifitrx.cal.sequence import (loopback_evm, loopback_snapshot,
                                  measure_loopback_delay, tx_evm)
from wifitrx.chain import LoopbackPath, RxChain, RxParams, TxChain, TxParams
from wifitrx.waveform import OFDMConfig

BW = 80e6
CFG = OFDMConfig(bandwidth_hz=BW, qam_order=256, n_symbols=3, oversampling=2)


def _trx():
    rng = np.random.default_rng(7)
    txp = TxParams(bandwidth_hz=BW).randomize(rng)
    rxp = RxParams(bandwidth_hz=BW).randomize(rng)
    txp.lpf.fc_nominal_hz = BW / 2 * 1.12
    rxp.lpf.fc_nominal_hz = BW / 2 * 1.12
    tx, rx = TxChain(txp, CFG.sample_rate_hz), RxChain(rxp, CFG.sample_rate_hz)
    # a non-default programmed state, so "unchanged" is not just "still
    # at defaults" (premise: a reset-to-defaults bug must be caught too)
    tx.dc_pre = 0.01 - 0.02j
    tx.gain_code_db = -3.0
    rx.im2_trim_code = 9
    tx.params.lpf.rc_code = 5
    return tx, rx


def _state(tx: TxChain, rx: RxChain) -> dict:
    # correction_state now includes the analog tuning codes; AGC runtime
    # state (lna_idx, vga_db) is deliberately NOT part of the invariant
    return {"tx": tx.correction_state(), "rx": rx.correction_state()}


READERS = {
    "loopback_snapshot": lambda tx, rx, path: loopback_snapshot(
        tx, rx, path, CFG, drive_scale=0.1),
    "loopback_evm": lambda tx, rx, path: loopback_evm(
        tx, rx, path, CFG, drive_scale=0.1),
    "tx_evm": lambda tx, rx, path: tx_evm(tx, CFG, drive_scale=0.1),
    "measure_loopback_delay": lambda tx, rx, path: measure_loopback_delay(
        tx, rx, path, CFG),
}


@pytest.mark.parametrize("name", sorted(READERS))
def test_reader_does_not_move_the_part(name):
    tx, rx = _trx()
    path = LoopbackPath(atten_db=40.0, delay_ns=6.0)
    before = _state(tx, rx)
    READERS[name](tx, rx, path)
    assert _state(tx, rx) == before, f"{name} reprogrammed the part"


def test_premise_the_invariant_can_fail():
    """Prove the state comparison detects a mutation: a fake 'reader' that
    pokes one trim must trip the same assertion."""
    tx, rx = _trx()
    before = _state(tx, rx)
    rx.im2_trim_code += 1
    assert _state(tx, rx) != before
