"""M3 tests: frequency-dependent IQ calibrations."""
import numpy as np
import pytest

from wifitrx.cal.group_delay import estimate_gd_mismatch_ps
from wifitrx.cal.rx_iq import (
    calibrate_rx_iq, estimate_rx_iq_from_frame, measure_rx_irr,
)
from wifitrx.cal.tx_iq import (
    calibrate_tx_iq, calibrate_tx_iq_envdet, measure_tx_rho,
)
from wifitrx.cal.wl_fir import design_w2_fir, fir_response
from wifitrx.chain import LoopbackPath, RxChain, RxParams, TxChain, TxParams
from wifitrx.impairments.analog_filter import TunableLPF
from wifitrx.impairments.converters import ADCParams, DACParams
from wifitrx.impairments.iq_imbalance import FreqDepIQImbalance
from wifitrx.impairments.phase_noise import LOModel
from wifitrx.waveform import OFDMConfig, generate_ofdm

FS = 320e6
BW = 160e6


def _rand_iq(rng):
    return FreqDepIQImbalance(
        gain_db=float(rng.uniform(-0.5, 0.5)),
        phase_deg=float(rng.uniform(-3.0, 3.0)),
        gd_mismatch_ps=float(rng.uniform(-300.0, 300.0)),
        rail_ripple_db=float(rng.uniform(0.1, 0.4)),
        rail_gd_ripple_ns=float(rng.uniform(0.05, 0.15)),
    )


def _tx(iq=None, **kw):
    d = dict(bandwidth_hz=BW, dac=DACParams(enabled=False),
             lpf=TunableLPF(fc_nominal_hz=90e6, enabled=False),
             iq=iq or FreqDepIQImbalance(enabled=False), lo_leak_dbm=None,
             lo=LOModel(enabled=False), pa_enabled=False)
    d.update(kw)
    return TxChain(TxParams(**d), FS)


def _rx(iq=None, **kw):
    d = dict(bandwidth_hz=BW, nonlin_enabled=False,
             iq=iq or FreqDepIQImbalance(enabled=False), dc_offset=(),
             lpf=TunableLPF(fc_nominal_hz=90e6, enabled=False),
             adc=ADCParams(enabled=False), lo=LOModel(enabled=False))
    d.update(kw)
    rx = RxChain(RxParams(**d), FS)
    rx.noise_enabled = False
    rx.agc(-30.0)
    return rx


class TestW2FirDesign:
    def test_fir_hits_targets(self):
        rng = np.random.default_rng(0)
        freqs = np.linspace(-70e6, 70e6, 16)
        rho = 0.01 * (rng.standard_normal(16) + 1j * rng.standard_normal(16))
        # smooth targets: low-order polynomial in f
        rho = 0.02 * (freqs / 70e6) * 1j + 0.005 + 0.002j
        taps = design_w2_fir(freqs, rho, FS, n_taps=31)
        resp = fir_response(taps, freqs, FS)
        err = np.max(np.abs(resp - (-rho)))
        assert err < 5e-4, err


@pytest.mark.parametrize("seed", range(4))
def test_tx_iq_cal(seed):
    rng = np.random.default_rng(seed)
    tx = _tx(iq=_rand_iq(rng))
    rx = _rx()
    path = LoopbackPath(atten_db=30.0, delay_ns=6.0, rx_lo_offset_hz=5.1e6)
    res = calibrate_tx_iq(tx, rx, path)
    assert res.metrics_before["irr_min_db"] < 45.0
    assert res.metrics_after["irr_min_db"] > 50.0, res.metrics_after


@pytest.mark.parametrize("seed", range(2))
def test_tx_iq_cal_not_polluted_by_rx_image(seed):
    """TX estimate must match TX-only ground truth even with a bad RX."""
    rng = np.random.default_rng(30 + seed)
    tx = _tx(iq=_rand_iq(rng))
    rx = _rx(iq=_rand_iq(np.random.default_rng(99 - seed)))  # bad RX too
    path = LoopbackPath(atten_db=30.0, delay_ns=6.0, rx_lo_offset_hz=5.1e6)
    rho_f, rho_v = measure_tx_rho(tx, rx, path)
    g1, g2 = tx.params.iq.g1g2(rho_f, FS)
    rho_true = g2 / g1
    assert np.max(np.abs(rho_v - rho_true)) < 0.15 * np.max(np.abs(rho_true))


@pytest.mark.parametrize("seed", range(2))
def test_tx_iq_envdet_fallback(seed):
    rng = np.random.default_rng(50 + seed)
    tx = _tx(iq=_rand_iq(rng), pa_enabled=True, dac=DACParams(enabled=True))
    res = calibrate_tx_iq_envdet(tx)
    assert res.metrics_after["irr_min_db"] > 45.0, res.metrics_after
    assert res.metrics_after["irr_min_db"] > res.metrics_before["irr_min_db"] + 10


@pytest.mark.parametrize("seed", range(4))
def test_rx_iq_cal(seed):
    rng = np.random.default_rng(seed)
    tx = _tx()                       # clean TX (post TX-cal situation)
    rx = _rx(iq=_rand_iq(rng))
    res = calibrate_rx_iq(tx, rx)
    assert res.metrics_before["irr_min_db"] < 45.0
    assert res.metrics_after["irr_min_db"] > 50.0, res.metrics_after


def test_rx_iq_frame_estimator():
    rng = np.random.default_rng(2)
    rx = _rx(iq=_rand_iq(rng))
    cfg = OFDMConfig(bandwidth_hz=BW, qam_order=64, n_symbols=6, oversampling=2)
    wf = generate_ofdm(cfg)
    cap = rx(wf.x * 0.01, rng=np.random.default_rng(0))
    freqs, w2_req = estimate_rx_iq_from_frame(cap, wf)
    rx.w2 = design_w2_fir(freqs, w2_req, FS, n_taps=31, band_hz=0.55 * BW)
    _, irr_after = measure_rx_irr(rx)
    assert float(np.min(irr_after)) > 48.0, irr_after


def test_gd_estimate_from_rho():
    gd_ps = 240.0
    iq = FreqDepIQImbalance(gd_mismatch_ps=gd_ps)
    f = np.linspace(-70e6, 70e6, 24)
    g1, g2 = iq.g1g2(f, FS)
    est = estimate_gd_mismatch_ps(f, g2 / g1)
    assert abs(est - gd_ps) < 25.0, est
