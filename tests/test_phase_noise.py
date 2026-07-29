"""M0 smoke tests: vendored phase-noise synthesis and jitter metrics."""
import numpy as np

from wifitrx.impairments import (
    LeesonOscillator, TabulatedPhase, synth_from_psd,
    integrate_pn, ipn_dbc, sphi_from_ldbc, ldbc_from_sphi,
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
