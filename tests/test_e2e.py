"""End-to-end full-sequence calibration tests."""
import numpy as np
import pytest

from wifitrx.cal.base import load_cal_state, save_cal_state
from wifitrx.cal.sequence import loopback_evm, run_full_cal
from wifitrx.chain import LoopbackPath, RxChain, RxParams, TxChain, TxParams
from wifitrx.waveform import OFDMConfig


def impaired_trx(bw: float, fs: float, seed: int, tx_lpf_ratio: float = 1.12):
    rng = np.random.default_rng(seed)
    txp = TxParams(bandwidth_hz=bw).randomize(rng)
    rxp = RxParams(bandwidth_hz=bw).randomize(rng)
    # LPF corners sized for the signal band
    txp.lpf.fc_nominal_hz = bw / 2 * tx_lpf_ratio
    rxp.lpf.fc_nominal_hz = bw / 2 * 1.12
    tx = TxChain(txp, fs)
    rx = RxChain(rxp, fs)
    return tx, rx


def test_full_sequence_80mhz():
    bw = 80e6
    cfg = OFDMConfig(bandwidth_hz=bw, qam_order=1024, n_symbols=6,
                     oversampling=4)
    fs = cfg.sample_rate_hz
    tx, rx = impaired_trx(bw, fs, seed=5)
    path = LoopbackPath(atten_db=40.0, delay_ns=6.0)
    results = run_full_cal(tx, rx, cfg, path)
    by_name = {r.name: r for r in results}
    final = by_name["final_loopback_evm"]
    assert final.metrics_after["tx_evm_db"] < -38.0, final.metrics_after
    assert final.metrics_after["evm_db"] < -35.0, final.metrics_after
    assert final.metrics_after["evm_db"] < final.metrics_before["evm_db"] - 5.0
    # every individual step healthy
    for r in results:
        assert r.passed in (True, None), (r.name, r.metrics_after, r.notes)


@pytest.mark.slow
def test_full_sequence_320mhz_4096qam():
    bw = 320e6
    # oversampling=4: DPD needs to see the regrowth bandwidth (at
    # oversampling=2 the predistorted spectrum aliases and the TX LPF
    # strips the correction terms)
    cfg = OFDMConfig(bandwidth_hz=bw, qam_order=4096, n_symbols=4,
                     oversampling=4)
    fs = cfg.sample_rate_hz
    # Design insight the model surfaces: at 320 MHz the TX baseband filter
    # must be wider than the channel (here 1.3x BW/2 = 208 MHz) or it strips
    # the DPD pre-correction spectrum and the PA residual floors near -39 dB
    tx, rx = impaired_trx(bw, fs, seed=9, tx_lpf_ratio=1.3)
    path = LoopbackPath(atten_db=40.0, delay_ns=6.0)
    results = run_full_cal(tx, rx, cfg, path, with_dpd=True,
                           final_drive_scale=0.12)
    final = {r.name: r for r in results}["final_loopback_evm"]
    # MCS13 TX EVM requirement at the PA output (802.11be spec point)
    assert final.metrics_after["tx_evm_db"] <= -38.0, final.metrics_after
    # composite TX+RX loopback EVM stays within the model's own budget
    assert final.metrics_after["evm_db"] <= -34.0, final.metrics_after


def test_cal_state_json_roundtrip(tmp_path):
    bw = 80e6
    cfg = OFDMConfig(bandwidth_hz=bw, qam_order=256, n_symbols=4,
                     oversampling=2)
    fs = cfg.sample_rate_hz
    tx, rx = impaired_trx(bw, fs, seed=3)
    path = LoopbackPath(atten_db=40.0, delay_ns=6.0)
    results = run_full_cal(tx, rx, cfg, path, with_dpd=False)
    evm_cal = loopback_evm(tx, rx, path, cfg)

    p = tmp_path / "cal_state.json"
    save_cal_state(p, tx.correction_state(), rx.correction_state(), results,
                   fs_hz=fs)

    # fresh chains with the same impairments, corrections loaded from JSON
    tx2, rx2 = impaired_trx(bw, fs, seed=3)
    tx_state, rx_state = load_cal_state(p)
    tx2.load_correction_state(tx_state)
    rx2.load_correction_state(rx_state)
    # no manual fix-ups allowed here: the JSON alone must restore the full
    # correction state, analog tuning codes included — a consumer only has
    # the file
    assert tx2.params.lpf.rc_code == tx.params.lpf.rc_code
    assert rx2.params.lpf.rc_code == rx.params.lpf.rc_code
    assert rx2.im2_trim_code == rx.im2_trim_code
    evm_loaded = loopback_evm(tx2, rx2, path, cfg)
    assert abs(evm_loaded - evm_cal) < 1.0, (evm_loaded, evm_cal)

    # the bundle also states what the calibration cost to measure: the
    # recipient is a production-test audience budgeting tester time, and
    # the capture counts are not recoverable from anything else in it
    import json
    doc = json.loads(p.read_text())
    spent = {r["name"]: r.get("cost") for r in doc["results"]}
    live = {r.name: r.cost for r in results if r.cost}
    assert live, "no step reported a cost — check the sequence"
    for name, cost in live.items():
        assert spent[name] == cost, (name, spent[name], cost)
    # …and the sample rate those counts are denominated in, without which
    # "samples" cannot be turned into tester time
    assert doc["fs_hz"] == pytest.approx(fs)
