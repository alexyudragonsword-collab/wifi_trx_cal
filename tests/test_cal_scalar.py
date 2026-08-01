"""M2 tests: scalar calibrations converge on randomized impairments."""
import numpy as np
import pytest

from wifitrx.cal.lpf_corner import calibrate_lpf_corner_rx, calibrate_lpf_corner_tx
from wifitrx.cal.rx_dc import calibrate_rx_dc
from wifitrx.cal.tx_lo_leak import (
    calibrate_tx_lo_leak_envdet, calibrate_tx_lo_leak_loopback,
)
from wifitrx.cal.tx_power import calibrate_tx_power
from wifitrx.chain import LoopbackPath, RxChain, RxParams, TxChain, TxParams
from wifitrx.impairments.analog_filter import TunableLPF
from wifitrx.impairments.converters import ADCParams, DACParams
from wifitrx.impairments.iq_imbalance import FreqDepIQImbalance
from wifitrx.impairments.phase_noise import LOModel
from wifitrx.waveform import OFDMConfig, generate_ofdm
from wifitrx.waveform.preamble import apply_cfo, build_frame, estimate_cfo

FS = 320e6


def _tx_params(**kw):
    d = dict(bandwidth_hz=160e6, dac=DACParams(enabled=False),
             lpf=TunableLPF(fc_nominal_hz=90e6, enabled=False),
             iq=FreqDepIQImbalance(enabled=False), lo_leak_dbm=None,
             lo=LOModel(enabled=False), pa_enabled=False)
    d.update(kw)
    return TxParams(**d)


def _rx_params(**kw):
    d = dict(bandwidth_hz=160e6, nonlin_enabled=False,
             iq=FreqDepIQImbalance(enabled=False), dc_offset=(),
             lpf=TunableLPF(fc_nominal_hz=90e6, enabled=False),
             adc=ADCParams(enabled=False), lo=LOModel(enabled=False))
    d.update(kw)
    return RxParams(**d)


@pytest.mark.parametrize("seed", range(6))
def test_rx_lpf_corner_cal(seed):
    rng = np.random.default_rng(seed)
    rc_err = float(rng.uniform(-0.2, 0.2))
    rx = RxChain(_rx_params(lpf=TunableLPF(fc_nominal_hz=90e6, rc_error=rc_err)), FS)
    res = calibrate_lpf_corner_rx(rx)
    assert res.passed, res.metrics_after


@pytest.mark.parametrize("seed", range(3))
def test_tx_lpf_corner_cal(seed):
    rng = np.random.default_rng(100 + seed)
    rc_err = float(rng.uniform(-0.2, 0.2))
    tx = TxChain(_tx_params(lpf=TunableLPF(fc_nominal_hz=90e6, rc_error=rc_err),
                            lo_leak_dbm=-28.0, pa_enabled=True,
                            dac=DACParams(enabled=True)), FS)
    res = calibrate_lpf_corner_tx(tx)
    assert res.passed, res.metrics_after


@pytest.mark.parametrize("seed", range(6))
def test_rx_dc_cal(seed):
    rng = np.random.default_rng(seed)
    rxp = _rx_params().randomize(rng)
    rxp = rxp.__class__(**{**rxp.__dict__,
                           "iq": FreqDepIQImbalance(enabled=False),
                           "lpf": TunableLPF(enabled=False)})
    rx = RxChain(rxp, FS)
    res = calibrate_rx_dc(rx)
    assert res.passed, res.metrics_after
    for k, v in res.metrics_after.items():
        assert v < -50.0, (k, v)


@pytest.mark.parametrize("seed", range(6))
def test_tx_lo_leak_envdet(seed):
    rng = np.random.default_rng(seed)
    leak = float(rng.uniform(-32.0, -22.0))
    ph = float(rng.uniform(0.0, 360.0))
    tx = TxChain(_tx_params(lo_leak_dbm=leak, lo_leak_phase_deg=ph,
                            dac=DACParams(enabled=True), pa_enabled=True), FS)
    res = calibrate_tx_lo_leak_envdet(tx)
    assert res.metrics_after["lo_leak_dbc"] < -40.0, res.metrics_after
    assert res.metrics_after["lo_leak_dbc"] < res.metrics_before["lo_leak_dbc"] - 10


def test_tx_lo_leak_loopback_refines():
    tx = TxChain(_tx_params(lo_leak_dbm=-26.0, lo_leak_phase_deg=120.0,
                            dac=DACParams(enabled=True)), FS)
    rx = RxChain(_rx_params(), FS)
    rx.noise_enabled = False
    rx.agc(-20.0)
    path = LoopbackPath(atten_db=40.0, delay_ns=0.0, rx_lo_offset_hz=4.8e6)
    res = calibrate_tx_lo_leak_loopback(tx, rx, path)
    assert res.metrics_after["lo_leak_dbc"] < -45.0, res.metrics_after
    # a second pass starts at the already-calibrated level: it must skip
    # (near the measurement floor the iteration only walks on noise),
    # keep the programmed dc_pre and spend no captures
    dc_before = tx.dc_pre
    res2 = calibrate_tx_lo_leak_loopback(tx, rx, path)
    assert "skipped" in res2.notes, res2.notes
    assert tx.dc_pre == dc_before
    assert not res2.cost
    assert res2.passed


def test_tx_power_cal():
    cfg = OFDMConfig(bandwidth_hz=80e6, qam_order=256, n_symbols=4, oversampling=2)
    wf = generate_ofdm(cfg)
    tx = TxChain(_tx_params(pa_enabled=True, dac=DACParams(enabled=True)),
                 cfg.sample_rate_hz)
    x = wf.x * 0.15
    res = calibrate_tx_power(tx, x, target_dbm=15.0)
    assert res.passed, res.metrics_after
    assert abs(res.metrics_after["error_db"]) < 0.5


def test_cfo_estimator():
    cfg = OFDMConfig(bandwidth_hz=80e6, qam_order=64, n_symbols=2, oversampling=2)
    frame = build_frame(cfg)
    fs = cfg.sample_rate_hz
    cfo_true = 31e3
    rx = apply_cfo(frame.x, cfo_true, fs)
    est = estimate_cfo(rx, frame, fs)
    assert abs(est - cfo_true) < 0.01 * abs(cfo_true), est
