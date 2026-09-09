"""The two EVM views (0.7.18): isolation vs modem form, and the pieces
they stand on — the pilot-slope CFO regression, channel-estimate
smoothing, and the envelope bound on the programmed DPD."""
import numpy as np
import pytest

from wifitrx.cal.sequence import rx_snapshot
from wifitrx.cal.tracking import pilot_cfo_hz
from wifitrx.chain import RxChain, RxParams
from wifitrx.dpd import BoundedDPD
from wifitrx.impairments.analog_filter import TunableLPF
from wifitrx.impairments.converters import ADCParams
from wifitrx.impairments.iq_imbalance import FreqDepIQImbalance
from wifitrx.impairments.phase_noise import LOModel
from wifitrx.waveform import OFDMConfig, demodulate_ofdm
from wifitrx.waveform.pilots import generate_ofdm_with_pilots, pilot_sequence
from wifitrx.waveform.preamble import apply_cfo, smooth_channel_estimate


def _noise_only_rx(bw: float) -> RxChain:
    p = RxParams(bandwidth_hz=bw, lpf=TunableLPF(enabled=False),
                 iq=FreqDepIQImbalance(enabled=False),
                 lo=LOModel(enabled=False), adc=ADCParams(enabled=False))
    p.im2.enabled = False
    return RxChain(p, bw * 4)


@pytest.mark.parametrize("bw, n_p", [(80e6, 16), (320e6, 64)])
def test_modem_form_sits_above_the_isolation_view_by_the_two_estimator_terms(bw, n_p):
    """Thermal noise only, raw LTF estimate (no smoothing): the modem
    form reads 10 log(1 + rho/2) + 10 log(1 + 1/(2 N_p)) above the
    isolation view — the frozen LTF-pair error (rho = 1, two repeats
    averaged) and the pilot CPE's own noise, minus the isolation view's
    own N_active term.  Measured 1.90 vs 1.89 dB at 80 MHz, 1.78 vs
    1.79 at 320 MHz.  Smoothing the estimate over the default 9 tones
    divides the frozen noise by 9 and the penalty drops accordingly."""
    cfg = OFDMConfig(bandwidth_hz=bw, qam_order=1024, n_symbols=6, oversampling=4)
    rx = _noise_only_rx(bw)
    raw = np.array([[s["evm_db"], s["evm_modem_db"]] for s in
                    (rx_snapshot(rx, cfg, -60.0, seed=k, ce_smooth_tones=1)
                     for k in range(3))])
    assert raw.shape[0] == 3 and int(rx_snapshot(rx, cfg, -60.0)["n_pilots"]) == n_p
    theory = (10 * np.log10(1.5) + 10 * np.log10(1 + 1 / (2 * n_p))
              - 10 * np.log10(1 + 1 / (2 * cfg.n_active)))
    assert (raw[:, 1] - raw[:, 0]).mean() == pytest.approx(theory, abs=0.15)
    smoothed = rx_snapshot(rx, cfg, -60.0, seed=0)
    assert smoothed["ce_smooth_tones"] == 9
    penalty_9 = smoothed["evm_modem_db"] - smoothed["evm_db"]
    theory_9 = (10 * np.log10(1 + 0.5 / 9) + 10 * np.log10(1 + 1 / (2 * n_p))
                - 10 * np.log10(1 + 1 / (2 * cfg.n_active)))
    assert 0.0 < penalty_9 < theory - 0.5
    assert penalty_9 == pytest.approx(theory_9, abs=0.2)


def test_channel_estimate_smoothing_keeps_a_smooth_channel_and_averages_noise():
    """Unit gain across the band survives any width; white noise on top
    of it shrinks by the width (variance / n); n <= 1 is the identity."""
    rng = np.random.default_rng(0)
    n = 484
    h = np.ones(n, dtype=complex)
    noise = (rng.standard_normal(n) + 1j * rng.standard_normal(n)) * 0.1
    assert np.array_equal(smooth_channel_estimate(h + noise, 1), h + noise)
    for width in (3, 9, 17):
        out = smooth_channel_estimate(h + noise, width)
        assert np.allclose(np.abs(out).mean(), 1.0, atol=0.02)
        ratio = np.var(out - h) / np.var(noise)
        assert ratio == pytest.approx(1 / width, rel=0.25), (width, ratio)


def test_pilot_slope_regression_reads_an_injected_cfo():
    """The one CFO regression the tracker, the study and the modem view
    share: a residual offset well inside the pilots' unambiguous range
    is read back to within 2 % on a clean frame."""
    cfg = OFDMConfig(bandwidth_hz=80e6, qam_order=256, n_symbols=12, oversampling=4)
    wf, cols = generate_ofdm_with_pilots(cfg)
    pilots = pilot_sequence(cfg.n_symbols, cols.size)
    fs = cfg.sample_rate_hz
    for cfo in (250.0, -3000.0, 12000.0):
        y = apply_cfo(wf.x, cfo, fs)
        est = pilot_cfo_hz(demodulate_ofdm(y, wf), cols, pilots, cfg, fs)
        assert est == pytest.approx(cfo, rel=0.02, abs=5.0), (cfo, est)


def test_bounded_dpd_holds_the_edge_gain_outside_the_training_envelope():
    """Inside the envelope the wrapper is the model; outside it the
    correction gain is the model's at the edge (the LUT behaviour), not
    the polynomial's extrapolation — a cubic that expands 1.2x at the
    edge must expand 1.2x, not 1.2x times the cube of the overshoot."""
    def cubic(x):
        return x * (1.0 + 0.2 * np.abs(x) ** 2)     # gain 1.2 at |x| = 1
    dpd = BoundedDPD(cubic, x_max=1.0)
    inside = np.array([0.3 + 0.1j, -0.9j, 0.5])
    assert np.allclose(dpd(inside), cubic(inside))
    outside = np.array([2.0, -3.0 * np.exp(0.7j)])
    got = dpd(outside)
    assert np.allclose(got, outside * 1.2)
    # the polynomial would have expanded them 1.8x and 2.8x
    assert np.all(np.abs(cubic(outside)) > 1.4 * np.abs(got))
    assert dpd.x_max == 1.0
