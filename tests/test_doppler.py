"""A time-varying channel: Clarke's spectrum, the tilt it puts across a
packet, and why the textbook closed form does not predict the EVM.

Checks are closed forms and invariants.  The one measured contrast that
is asserted numerically carries the configuration it was taken at.
"""
import numpy as np
import pytest

from wifitrx.link import channel as ch
from wifitrx.link import channel_study as cs
from wifitrx.waveform import OFDMConfig

BW = 40e6
FS = BW * 4


def _cfg(n_symbols=6):
    return OFDMConfig(bandwidth_hz=BW, qam_order=256, n_symbols=n_symbols,
                      oversampling=4)


def test_zero_doppler_is_the_block_fading_path_bit_for_bit():
    """Every reading before 0.7.33 was taken with a frozen realisation;
    the default must reproduce it exactly, not approximately."""
    x = np.random.default_rng(0).standard_normal(4096) + 0j
    a, ta = ch.TDLChannel(rms_delay_ns=50.0).apply(
        x, FS, np.random.default_rng(1))
    b, tb = ch.TDLChannel(rms_delay_ns=50.0, doppler_hz=0.0).apply(
        x, FS, np.random.default_rng(1))
    assert np.array_equal(a, b) and np.array_equal(ta, tb)


def test_a_moving_channel_still_carries_unit_power():
    """Normalisation must not depend on whether the taps move."""
    c = ch.TDLChannel(rms_delay_ns=50.0, doppler_hz=500.0)
    rng = np.random.default_rng(0)
    p = np.mean([abs(c.tap_process(64, FS, 0.25, rng)[0]) ** 2
                 for _ in range(4000)])
    assert p == pytest.approx(0.25, rel=0.08)


@pytest.mark.slow
def test_the_tap_autocorrelation_follows_j0():
    """The closed form that makes this generator usable at all: Clarke's
    spectrum gives J0(2 pi f_D tau).  Checked at a Doppler large enough
    for the window to span several lobes, since the statistic depends
    only on the product f_D * tau."""
    from scipy.special import j0
    n, fd = 20000, 20e3
    c = ch.TDLChannel(rms_delay_ns=50.0, doppler_hz=fd, n_sinusoids=16)
    rng = np.random.default_rng(3)
    lags = np.array([0, 1000, 2500, 5000, 8000, 12000])
    acc = np.zeros(lags.size, dtype=complex)
    for _ in range(300):
        g = c.tap_process(n, FS, 1.0, rng)
        for i, lag in enumerate(lags):
            acc[i] += np.vdot(g[:n - lag], g[lag:]) / (n - lag)
    r = (acc / acc[0]).real
    want = j0(2 * np.pi * fd * lags / FS)
    assert np.abs(r - want).max() < 0.05, np.c_[r, want]


def test_the_closed_form_is_the_channels_motion_not_an_evm_bound():
    """2[1 - J0] at tau = 0 is zero motion, and it grows toward 2 (3 dB)
    as the channel decorrelates.  Pinning the shape here; that it does
    *not* bound the EVM is the slow test below."""
    assert cs.frozen_estimate_change_db(0.0, 1e-3) < -100.0
    far = cs.frozen_estimate_change_db(1e4, 1e-3)     # f_D t = 10, J0 ~ 0
    assert far == pytest.approx(10 * np.log10(2.0), abs=0.6)
    a = cs.frozen_estimate_change_db(100.0, 1e-4)
    b = cs.frozen_estimate_change_db(200.0, 1e-4)
    assert b > a                                       # faster is worse


@pytest.mark.slow
def test_a_frozen_estimate_tilts_the_packet_only_when_the_channel_moves():
    """The signature.  With the channel still, the LTF estimate is right
    for every symbol and the per-symbol EVM is flat (which is what the
    AGC study measured).  With it moving, the estimate goes stale and the
    packet tilts."""
    cfg = _cfg(n_symbols=8)
    still = [cs.doppler_readings(cfg, ch.TDLChannel(rms_delay_ns=50.0), 30.0,
                                 9, s)["per_symbol_db"] for s in range(8)]
    moving = [cs.doppler_readings(cfg, ch.TDLChannel(rms_delay_ns=50.0,
                                                     doppler_hz=670.0), 30.0,
                                  9, s)["per_symbol_db"] for s in range(8)]
    flat = np.median(np.array(still), axis=0)
    tilt = np.median(np.array(moving), axis=0)
    assert abs(flat[-1] - flat[0]) < 1.0, flat
    assert tilt[-1] - tilt[0] > 5.0, tilt


@pytest.mark.slow
def test_the_doppler_contribution_is_worse_than_the_flat_weighted_form():
    """Isolation: the Doppler term is the total minus the still-channel
    floor in power, and it comes out several dB worse than
    2[1 - J0(2 pi f_D T)].  Same cause as the divergent power-mean —
    equalising with a stale estimate divides the channel's change by
    |h|^2, so the deep fades, where the estimate is worst, also carry the
    largest divisor.  Measured at 40 MHz / 50 ns / 30 dB: 3 to 12 dB."""
    cfg = _cfg(n_symbols=8)
    t_p = 9 * cs.symbol_time_s(cfg)
    def total(fd):
        return cs.median_db([cs.doppler_readings(
            cfg, ch.TDLChannel(rms_delay_ns=50.0, doppler_hz=fd), 30.0, 9, s
        )["evm_modem_db"] for s in range(8)])
    floor = 10 ** (total(0.0) / 10.0)
    for fd in (170.0, 670.0):
        contribution = 10 * np.log10(max(10 ** (total(fd) / 10.0) - floor, 1e-12))
        flat = cs.frozen_estimate_change_db(fd, t_p)
        assert contribution > flat + 1.5, (fd, contribution, flat)


@pytest.mark.slow
def test_evm_worsens_monotonically_with_doppler():
    cfg = _cfg(n_symbols=8)
    vals = [cs.median_db([cs.doppler_readings(
        cfg, ch.TDLChannel(rms_delay_ns=50.0, doppler_hz=fd), 30.0, 9, s
    )["evm_modem_db"] for s in range(8)]) for fd in (0.0, 170.0, 670.0)]
    assert vals[0] < vals[1] < vals[2], vals


def test_the_bessel_helper_matches_scipy():
    """The docstring claims the periodic mean is spectrally accurate;
    measure it rather than assert it.  scipy is fine here — tests are
    not shipped, and the Android allowlist only governs what is."""
    from scipy.special import j0
    x = np.concatenate([np.linspace(0.0, 3.0, 40), np.linspace(3.0, 120.0, 160)])
    err = max(abs(cs.bessel_j0(float(v)) - j0(v)) for v in x)
    assert err < 1e-12, err


def test_the_bessel_helper_keeps_the_renamed_numpy_name_out():
    """np.trapz became np.trapezoid in numpy 2.0 and the phone runs
    1.19.5; that rename has broken this repository once already.  The
    helper must not reach for either spelling.

    Checked against the compiled name table, not the source text: a
    first version read ``inspect.getsource`` and went red on the
    docstring, which *discusses* both names.  Matching prose instead of
    the line that does the work is the exact failure this repository has
    hit four times (AGENTS.md, verification section)."""
    names = set(cs.bessel_j0.__code__.co_names)
    assert "trapz" not in names and "trapezoid" not in names, names
    assert "mean" in names, names        # premise: this is the real body
