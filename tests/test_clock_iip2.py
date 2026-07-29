"""N2 tests: clock error modeling, pilot tracking loop, RX IIP2 cal."""
import numpy as np
import pytest

from wifitrx.cal.rx_iip2 import calibrate_rx_iip2
from wifitrx.cal.tracking import ClockTracker
from wifitrx.chain import LoopbackPath, RxChain, RxParams, TxChain, TxParams
from wifitrx.impairments.analog_filter import TunableLPF
from wifitrx.impairments.clock import ClockError
from wifitrx.impairments.converters import ADCParams, DACParams
from wifitrx.impairments.iq_imbalance import FreqDepIQImbalance
from wifitrx.impairments.nonlinear import Im2Params
from wifitrx.impairments.phase_noise import LOModel
from wifitrx.metrics import evm
from wifitrx.metrics.cpe import correct_cpe
from wifitrx.waveform import OFDMConfig, generate_ofdm
from wifitrx.waveform.pilots import generate_ofdm_with_pilots, pilot_positions

FS = 320e6
BW = 80e6


def _clean_rx(**kw):
    d = dict(bandwidth_hz=BW, nonlin_enabled=False,
             iq=FreqDepIQImbalance(enabled=False), dc_offset=(),
             lpf=TunableLPF(enabled=False), adc=ADCParams(enabled=False),
             lo=LOModel(enabled=False))
    d.update(kw)
    rx = RxChain(RxParams(**d), FS)
    rx.noise_enabled = False
    rx.vga_db = 0.0
    return rx


class TestClockError:
    def test_correlated_cfo_sco(self):
        ck = ClockError(ppm=20.0)
        assert np.isclose(ck.cfo_hz(6e9), -120e3)

    def test_disabled_identity(self):
        ck = ClockError(ppm=20.0, enabled=False)
        x = np.exp(2j * np.pi * 5e6 * np.arange(1024) / FS)
        np.testing.assert_allclose(ck.apply(x, FS, 6e9), x)

    def test_sco_shifts_late_samples(self):
        ck = ClockError(ppm=50.0)
        n = 1 << 15
        x = np.exp(2j * np.pi * 10e6 * np.arange(n) / FS)
        y = ck.apply_sco(x, FS)
        # accumulated timing error at the end: n * ppm ~ 1.6 samples
        ph_end = np.angle(y[-100] * np.conj(x[-100]))
        assert abs(ph_end) > 0.1


class TestPilotTracking:
    def test_tracker_converges_and_recovers_evm(self):
        cfg = OFDMConfig(bandwidth_hz=BW, qam_order=256, n_symbols=8,
                         oversampling=4)
        fs = cfg.sample_rate_hz
        wf, cols = generate_ofdm_with_pilots(cfg)
        # 5 ppm -> 30 kHz CFO: inside the pilot loop's pull-in range
        # (coarse acquisition beyond that is the preamble estimator's job)
        ppm_true = 5.0
        rx = _clean_rx(clock=ClockError(ppm=ppm_true),
                       lo=LOModel(enabled=False))
        rx.params.lo.freq_hz = 6.0e9

        tracker = ClockTracker(fs=fs, f_carrier_hz=6.0e9)
        rng = np.random.default_rng(0)
        evms = []
        for frame in range(6):
            cap = rx(wf.x * 0.01, rng=rng)
            syms = tracker.process_frame(cap, wf, cols)
            syms = correct_cpe(syms, wf.tx_symbols)
            evms.append(evm(syms, wf.tx_symbols, equalize="per_tone").db)
        est_ppm = -tracker.cfo_hz / 6.0e9 * 1e6
        assert abs(est_ppm - ppm_true) < 0.05 * ppm_true, est_ppm
        assert abs(tracker.sco_ppm - ppm_true) < 0.05 * ppm_true
        # converged EVM good enough for high MCS; the remaining floor is
        # ICI from the residual CFO estimate (physics, not a bug)
        assert evms[-1] < -35.0, evms
        assert evms[-1] < evms[0] - 10.0, evms


class TestIip2Cal:
    @pytest.mark.parametrize("seed", range(4))
    def test_trim_search_converges(self, seed):
        rng = np.random.default_rng(seed)
        im2 = Im2Params(trim_best=int(rng.integers(30, 226)),
                        phase_deg=float(rng.uniform(0, 360)), enabled=True)
        txp = TxParams(bandwidth_hz=BW, dac=DACParams(enabled=True),
                       lpf=TunableLPF(enabled=False),
                       iq=FreqDepIQImbalance(enabled=False), lo_leak_dbm=None,
                       lo=LOModel(enabled=False), pa_enabled=True)
        tx = TxChain(txp, FS)
        rx = _clean_rx(im2=im2)
        res = calibrate_rx_iip2(tx, rx)
        assert res.passed, res.metrics_after
        assert abs(res.estimated["trim_code"] - im2.trim_best) <= 3
        assert res.metrics_after["iip2_dbm"] > 68.0
