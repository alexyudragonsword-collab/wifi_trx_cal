"""N3 tests: blockers, reciprocal mixing, AGC desense, frac-N spur planning."""
import numpy as np

from wifitrx.impairments.blocker import Blocker, reciprocal_mixing_noise_dbm
from wifitrx.impairments.phase_noise import (DEFAULT_WIFI7_LO_PROFILE, LOModel,
                                             ldbc_from_sphi)
from wifitrx.chain import RxChain, RxParams
from wifitrx.impairments.analog_filter import TunableLPF
from wifitrx.impairments.converters import ADCParams
from wifitrx.impairments.iq_imbalance import FreqDepIQImbalance
from wifitrx.link.spur_planning import (FracNConfig, channel_spur_table,
                                        frac_of, lo_with_frac_spurs,
                                        predict_spurs)
from wifitrx.units import dbm_to_mw, power_dbm

FS = 640e6
BW = 160e6


def _rx(**kw):
    d = dict(bandwidth_hz=BW, nonlin_enabled=False,
             iq=FreqDepIQImbalance(enabled=False), dc_offset=(),
             lpf=TunableLPF(enabled=False), adc=ADCParams(enabled=False),
             lo=LOModel(enabled=False))
    d.update(kw)
    rx = RxChain(RxParams(**d), FS)
    rx.noise_enabled = False
    rx.vga_db = 0.0
    return rx


class TestBlocker:
    def test_blocker_power_and_offset(self):
        b = Blocker(offset_hz=200e6, power_dbm=-25.0, kind="cw")
        x = b.signal(1 << 14, FS)
        assert np.isclose(power_dbm(x), -25.0, atol=0.05)
        spec = np.abs(np.fft.fft(x)) ** 2
        k = int(round(200e6 * x.size / FS))
        assert np.argmax(spec) == k

    def test_ofdm_blocker_bandwidth(self):
        b = Blocker(offset_hz=150e6, power_dbm=-30.0, kind="ofdm", bw_hz=20e6)
        x = b.signal(1 << 15, FS)
        assert np.isclose(power_dbm(x), -30.0, atol=0.3)

    def test_reciprocal_mixing_level(self):
        """LO skirt on a strong CW blocker matches the analytic level."""
        offset = 200e6
        p_b = -20.0
        rx = _rx(lo=LOModel(enabled=True))
        n = 1 << 17
        blk = Blocker(offset_hz=offset, power_dbm=p_b, kind="cw")
        cap = rx(blk.signal(n, FS), rng=np.random.default_rng(0))
        # in-band noise density measured well away from the blocker
        spec = np.abs(np.fft.fft(cap)) ** 2 / n ** 2
        band = (np.arange(n) * FS / n)
        sel = (band > 5e6) & (band < 40e6)   # wanted-band region
        p_meas_dbm = 10 * np.log10(np.sum(spec[sel]))
        gain_db = rx.params.lna_states[rx.lna_idx].gain_db
        # analytic: blocker power x L(offset) over the measured bandwidth
        l_dbchz = float(ldbc_from_sphi(
            DEFAULT_WIFI7_LO_PROFILE.psd(np.array([offset])))[0])
        p_pred_dbm = reciprocal_mixing_noise_dbm(p_b + gain_db, l_dbchz, 35e6)
        assert abs(p_meas_dbm - p_pred_dbm) < 2.0, (p_meas_dbm, p_pred_dbm)


class TestAgcDesense:
    def test_blocker_forces_gain_backoff(self):
        rx = _rx()
        p_sig = -70.0
        rx.agc(p_sig)
        idx_clean = rx.lna_idx
        # AGC keys on total power: signal + strong blocker
        p_tot = 10 * np.log10(dbm_to_mw(p_sig) + dbm_to_mw(-30.0))
        rx.agc(p_tot)
        assert rx.lna_idx > idx_clean  # backed off -> desense (higher NF)


class TestSpurPlanning:
    def test_offsets_follow_frac_arithmetic(self):
        cfg = FracNConfig()
        f_lo = 5985e6
        frac = frac_of(f_lo, cfg)
        spurs = predict_spurs(f_lo, cfg)
        for f_off in spurs:
            nus = [(k * frac) % 1.0 for k in range(1, 7)]
            ok = any(np.isclose(f_off, min(nu, 1 - nu) * cfg.fref_hz,
                                rtol=1e-6) for nu in nus)
            assert ok, f_off

    def test_near_integer_channel_is_dirty(self):
        cfg = FracNConfig()
        # engineered near-integer channel: frac ~ 200 Hz/fref
        f_lo = (np.floor(cfg.vco_mult * 5980e6 / cfg.fref_hz) * cfg.fref_hz
                + 20e3) / cfg.vco_mult
        spurs = predict_spurs(f_lo, cfg, fmin=1e2)
        assert spurs, "near-integer channel must show low-offset spurs"
        f_min = min(spurs)
        assert f_min < 1e6
        assert spurs[f_min] > -80.0  # inside loop BW, strong

    def test_channel_table_flags_some_dirty(self):
        rows = channel_spur_table(320e6, bands=("6g",))
        assert len(rows) == 59
        dirty = [r for r in rows if r["dirty"]]
        clean = [r for r in rows if not r["dirty"]]
        assert dirty and clean  # both classes exist across the band

    def test_lo_with_spurs_injects(self):
        lo = lo_with_frac_spurs(5985e6)
        assert lo.freq_hz == 5985e6
        assert len(lo.spur_offsets_hz) == len(lo.spur_dbc)
