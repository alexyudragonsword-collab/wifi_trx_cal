"""M0 smoke tests: vendored phase-noise synthesis and jitter metrics."""
import numpy as np
import pytest

from wifitrx.impairments import (
    LeesonOscillator, TabulatedPhase, TypeIIPllPhase, synth_from_psd,
    integrate_pn, ipn_dbc, sphi_from_ldbc, ldbc_from_sphi,
    cpe_partition, ici_weight,
)


def test_ldbc_sphi_roundtrip():
    l_in = -100.0
    assert np.isclose(ldbc_from_sphi(sphi_from_ldbc(l_in)), l_in)


def test_synth_matches_target_psd():
    # Flat -120 dBc/Hz phase-noise floor: variance = S_phi * fs / 2.
    fs = 100e6
    n = 1 << 18
    s0 = float(sphi_from_ldbc(-120.0))
    rng = np.random.default_rng(0)
    phi = synth_from_psd(lambda f: np.full_like(f, s0), fs, n, rng)
    var_expected = s0 * fs / 2.0
    assert np.isclose(np.var(phi), var_expected, rtol=0.05)


def test_leeson_from_spot():
    osc = LeesonOscillator.from_spot("vco", l_dbchz=-110.0, f_offset=1e6)
    # Spot reproduces itself on the 1/f^2 asymptote (floor is ~60 dB below).
    assert np.isclose(ldbc_from_sphi(osc.psd(np.array([1e6])))[0], -110.0, atol=0.1)
    # 20 dB/dec slope
    l_10m = ldbc_from_sphi(osc.psd(np.array([1e7])))[0]
    assert np.isclose(l_10m, -130.0, atol=0.5)


def test_tabulated_ipn():
    # WiFi-like closed-loop profile: plateau -95 dBc/Hz to 100 kHz, then rolloff.
    prof = TabulatedPhase("lo", f_pts=(1e4, 1e5, 1e6, 1e7),
                          l_dbc_pts=(-95.0, -95.0, -115.0, -135.0))
    f = np.logspace(4, 7, 400)
    ipn = ipn_dbc(f, prof.psd(f), f1=1e4, f2=1e7)
    # Rough analytic estimate: plateau contributes ~ -95 + 10log10(9e4) ~ -45.5 dBc
    assert -50.0 < ipn < -40.0
    p = integrate_pn(f, prof.psd(f), 1e4, 1e7)
    rms_deg = np.degrees(np.sqrt(p))
    assert 0.1 < rms_deg < 2.0


# ------------------------------------------------ CPE / ICI partition
def test_cpe_partition_of_a_flat_psd_is_the_sinc_integral():
    """A white phase PSD splits by the analytic identity
    int_0^inf sinc^2(f T) df = 1/(2T): the CPE-removable power of S0 over
    a wide band is S0/(2T) and the -3 dB hand-over sits at 0.443/T."""
    t_fft = 12.8e-6
    s0 = 1e-9
    part = cpe_partition(lambda f: np.full(np.shape(f), s0), t_fft,
                         f1=10.0, f2=100e6)
    assert part["cpe_rad2"] == pytest.approx(s0 / (2 * t_fft), rel=0.02)
    assert part["f_3db_hz"] == pytest.approx(0.443 / t_fft)
    assert part["total_rad2"] == pytest.approx(s0 * (100e6 - 10.0), rel=1e-3)
    assert part["ici_rad2"] + part["cpe_rad2"] == pytest.approx(
        part["total_rad2"])
    # the weight itself: nothing survives at DC, everything far out, and
    # exactly half at the quoted -3 dB point
    assert ici_weight(np.array([0.0]), t_fft)[0] == pytest.approx(0.0)
    assert ici_weight(np.array([1e7]), t_fft)[0] == pytest.approx(1.0, abs=1e-3)
    assert ici_weight(np.array([0.443 / t_fft]), t_fft)[0] == pytest.approx(
        0.5, abs=0.01)


def test_wifi7_symbol_leaves_cpe_four_times_less_to_remove():
    """The shipped LO profile under the 12.8 us 11ax/be symbol vs the
    3.2 us legacy symbol: the CPE-removable band shrinks 4x (35 -> 138
    kHz hand-over), so CPE tracking takes out ~6.5 % of this profile's
    phase power instead of ~28 % — measured 6.6 % / 28.7 % at 80 MHz."""
    from wifitrx.impairments.phase_noise import DEFAULT_WIFI7_LO_PROFILE
    ax = cpe_partition(DEFAULT_WIFI7_LO_PROFILE.psd, 12.8e-6, 3e3, 160e6)
    ac = cpe_partition(DEFAULT_WIFI7_LO_PROFILE.psd, 3.2e-6, 3e3, 160e6)
    assert ac["f_3db_hz"] == pytest.approx(4 * ax["f_3db_hz"])
    assert 0.04 < ax["tracked_fraction"] < 0.10
    assert ac["tracked_fraction"] > 3 * ax["tracked_fraction"]


def test_typeii_pll_loop_bandwidth_is_the_minus_3db_point():
    """With the VCO and floor off, the profile is |H|^2 times the plateau:
    exactly the plateau in-band, exactly half at loop_bw_hz, and falling
    20 dB/dec far above it (the type-II zero at 2 zeta wn leaves a
    first-order roll-off — this is why real loops add poles; a -40
    dB/dec expectation here was the first draft's mistake, not the
    model's).  With the plateau off it is |1-H|^2 times the VCO: the
    VCO 1/f^2 line far out; in-band |1-H|^2 rises as f^4, so the
    suppressed VCO contribution climbs 20 dB/dec towards the loop."""
    plateau = float(sphi_from_ldbc(-100.0))
    for zeta in (0.7, 1.0, 1.5):
        pll = TypeIIPllPhase("pll", loop_bw_hz=200e3, zeta=zeta,
                             plateau=plateau)
        f = np.array([1e3, 200e3, 2e7, 2e8])
        s = pll.psd(f)
        assert s[0] == pytest.approx(plateau, rel=1e-3)
        assert s[1] == pytest.approx(plateau / 2, rel=1e-6), zeta
        assert 10 * np.log10(s[2] / plateau) < -40.0
        assert 10 * np.log10(s[2] / s[3]) == pytest.approx(20.0, abs=0.2)
    vco = TypeIIPllPhase.from_spot("pll", 200e3, plateau_dbchz=-300.0,
                                   vco_dbchz_at_1mhz=-116.0,
                                   floor_dbchz=-300.0)
    assert ldbc_from_sphi(vco.psd(np.array([1e7])))[0] == pytest.approx(
        -136.0, abs=0.05)
    in_band = ldbc_from_sphi(vco.psd(np.array([1e3, 1e4])))
    assert in_band[1] - in_band[0] == pytest.approx(20.0, abs=0.3)
    assert in_band[0] < -128.0        # measured -132.2 dBc/Hz at 1 kHz
