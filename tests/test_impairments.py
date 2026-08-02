"""M1 tests: impairment blocks against analytic expectations."""
import numpy as np

from wifitrx.impairments.analog_filter import TunableLPF
from wifitrx.impairments.converters import ADCParams, DACParams
from wifitrx.impairments.iq_imbalance import FreqDepIQImbalance
from wifitrx.impairments.nonlinear import MemorylessNonlin
from wifitrx.pa.saleh import SalehPA
from wifitrx.pa.scaled import ScaledPA
from wifitrx.units import dbm_to_mw, power_dbm, scale_to_dbm

FS = 640e6


def _tone(f, n=8192, fs=FS, amp=1.0):
    t = np.arange(n) / fs
    return amp * np.exp(2j * np.pi * f * t)


# --------------------------------------------------------------- ScaledPA
class TestScaledPA:
    def setup_method(self):
        self.pa = ScaledPA(SalehPA(), gain_db=26.0, psat_dbm=28.0, pae_max=0.35)

    def test_saturation_at_psat(self):
        # The AM-AM peak sits at Psat (Saleh rolls off past the peak).
        p_in = np.linspace(-20.0, 20.0, 2000)
        p_out_max = np.max(self.pa.am_am(p_in))
        assert np.isclose(p_out_max, 28.0, atol=0.05)

    def test_small_signal_gain(self):
        p_out = self.pa.am_am(np.array([-40.0]))[0]
        assert np.isclose(p_out, -40.0 + 26.0, atol=0.05)

    def test_p1db_below_psat(self):
        p1 = self.pa.p1db_out_dbm
        assert 20.0 < p1 < 28.0

    def test_pae_at_psat(self):
        assert np.isclose(self.pa.pae(28.0), 0.35, atol=1e-6)

    def test_average_pae_at_backoff(self):
        rng = np.random.default_rng(0)
        x = (rng.standard_normal(4096) + 1j * rng.standard_normal(4096)) / np.sqrt(2)
        x = scale_to_dbm(x, 18.0 - 26.0)  # ~10 dB output backoff
        y = self.pa(x)
        pae = self.pa.average_pae(y)
        assert 0.05 < pae < 0.35


# ------------------------------------------------- FreqDepIQImbalance
class TestIQImbalance:
    def test_disabled_is_identity(self):
        iq = FreqDepIQImbalance(gain_db=0.3, phase_deg=2.0, enabled=False)
        x = _tone(50e6)
        np.testing.assert_allclose(iq.apply(x, FS), x)

    def test_flat_irr_matches_textbook(self):
        # IRR = |(1+g e^{jp}) / (1-g e^{jp})|^2 with g = amplitude ratio.
        iq = FreqDepIQImbalance(gain_db=0.5, phase_deg=2.0)
        f = np.array([50e6])
        irr = iq.irr_db(f, FS)[0]
        g = 10 ** (0.5 / 20)
        phi = np.deg2rad(2.0)
        k = g * np.exp(1j * phi)
        irr_ref = 20 * np.log10(abs(1 + k) / abs(1 - k))
        assert np.isclose(irr, irr_ref, atol=0.3)

    def test_measured_image_matches_analytic(self):
        iq = FreqDepIQImbalance(gain_db=0.4, phase_deg=1.5, gd_mismatch_ps=200.0,
                                rail_ripple_db=0.3, rail_gd_ripple_ns=0.1)
        f0 = 80e6
        n = 8192
        x = _tone(f0, n)
        y = iq.apply(x, FS)
        spec = np.fft.fft(y) / n
        k = int(round(f0 * n / FS))
        direct = np.abs(spec[k])
        image = np.abs(spec[-k])
        irr_meas = 20 * np.log10(direct / image)
        irr_ana = iq.irr_db(np.array([f0]), FS)[0]
        assert np.isclose(irr_meas, irr_ana, atol=1.0)

    def test_gd_mismatch_makes_irr_freq_dependent(self):
        iq = FreqDepIQImbalance(phase_deg=0.5, gd_mismatch_ps=400.0)
        f = np.array([10e6, 150e6])
        irr = iq.irr_db(f, FS)
        assert irr[1] < irr[0] - 3.0  # worse IRR at band edge


# --------------------------------------------------------------- TunableLPF
class TestTunableLPF:
    def test_corner_moves_with_code(self):
        lpf = TunableLPF(fc_nominal_hz=160e6, rc_error=0.15)
        assert lpf.fc_actual_hz > 160e6
        lpf_hi = TunableLPF(fc_nominal_hz=160e6, rc_error=0.15,
                            rc_code=lpf.code_mid + 8)
        assert lpf_hi.fc_actual_hz < lpf.fc_actual_hz

    def test_minus3db_at_corner(self):
        lpf = TunableLPF(fc_nominal_hz=160e6, order=5)
        h = lpf.freq_response(np.array([lpf.fc_actual_hz]), FS)
        assert np.isclose(20 * np.log10(np.abs(h[0])), -3.0, atol=0.3)


# --------------------------------------------------------------- converters
class TestConverters:
    def test_dac_scaling_bypass(self):
        dac = DACParams(fullscale_dbm=4.0, enabled=False)
        x = _tone(50e6, amp=1.0)
        y = dac.apply(x, FS)
        assert np.isclose(power_dbm(y), 4.0, atol=0.01)

    def test_adc_quantization_snr(self):
        adc = ADCParams(bits=11, fullscale_dbm=2.0, jitter_ps_rms=0.0)
        x = _tone(50e6, amp=np.sqrt(dbm_to_mw(2.0)) * 0.9)
        y = adc.apply(x, FS) * adc.a_fs
        err = y - x
        snr = 10 * np.log10(np.mean(np.abs(x) ** 2) / np.mean(np.abs(err) ** 2))
        # ~6.02*11+1.76 per rail; complex tone at 0.9 FS
        assert snr > 60.0

    def test_adc_clips(self):
        adc = ADCParams(bits=11, fullscale_dbm=2.0)
        x = _tone(50e6, amp=np.sqrt(dbm_to_mw(2.0)) * 3.0)
        y = adc.apply(x, FS)
        assert np.max(np.abs(y.real)) <= 1.0


# --------------------------------------------------------------- nonlinear
def test_iip3_definition():
    # Single complex tone at power P: fundamental gain compression
    # y = x (1 - P/iip3): at P = IIP3 - 10 dB, compression ~ 0.9.
    nl = MemorylessNonlin(iip3_dbm=0.0)
    x = _tone(10e6, amp=np.sqrt(dbm_to_mw(-10.0)))
    y = nl.apply(x)
    g = np.abs(np.vdot(x, y) / np.vdot(x, x))
    assert np.isclose(g, 1.0 - 0.1, atol=0.005)
