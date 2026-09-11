"""The propagation channel (link/channel, link/channel_study).

Every check is a closed form, an invariant, or a measured contrast —
never a remembered number.  The one number quoted from a measurement
carries the configuration it was measured at.
"""
import numpy as np
import pytest

from wifitrx.link import channel as ch
from wifitrx.link import channel_study as cs
from wifitrx.waveform import OFDMConfig

BW = 40e6


def _cfg(n_symbols=6):
    return OFDMConfig(bandwidth_hz=BW, qam_order=256, n_symbols=n_symbols,
                      oversampling=4)


def test_flat_and_disabled_leave_the_signal_bit_identical():
    """The default deliverable is conducted mode; a channel that is off
    must be the absence of a channel, not an approximation of one."""
    fs = _cfg().sample_rate_hz
    x = (np.random.default_rng(0).standard_normal(2048)
         + 1j * np.random.default_rng(1).standard_normal(2048))
    for c in (ch.TDLChannel(enabled=False), ch.TDLChannel(rms_delay_ns=0.0)):
        y, taps = c.apply(x, fs, np.random.default_rng(2))
        assert np.array_equal(x, y)
        assert taps.size == 1 and taps[0] == 1.0


def test_tap_power_is_normalised_so_the_channel_does_not_change_snr():
    """E[sum |g|^2] = 1: a realisation reshapes the frequency response
    and leaves the average level alone, or every EVM below would be
    reading a gain error instead of a fade."""
    fs = _cfg().sample_rate_hz
    rng = np.random.default_rng(0)
    for rms in (15.0, 50.0, 150.0):
        c = ch.TDLChannel(rms_delay_ns=rms)
        p = np.mean([np.sum(np.abs(c.realize(fs, rng)) ** 2) for _ in range(3000)])
        assert p == pytest.approx(1.0, abs=0.03), rms


def test_realized_rms_delay_is_recomputed_not_assumed():
    """The sampled, truncated profile is not exactly the continuous
    exponential, so the class reports what the taps actually have.  It
    must land just under the request (truncation removes the far tail)
    and never above it."""
    fs = _cfg().sample_rate_hz
    for rms in (15.0, 50.0, 150.0):
        got = ch.TDLChannel(rms_delay_ns=rms).realized_rms_delay_s(fs) * 1e9
        assert got <= rms
        assert got == pytest.approx(rms, rel=0.07), (rms, got)
    assert ch.TDLChannel(rms_delay_ns=0.0).realized_rms_delay_s(fs) == 0.0


def test_frequency_response_agrees_with_the_dft_of_the_taps():
    """Closed-form cross-check: H(f) = sum_l g_l exp(-j2 pi f tau_l) must
    equal the FFT of the zero-padded tap train at the bin frequencies."""
    fs = _cfg().sample_rate_hz
    c = ch.TDLChannel(rms_delay_ns=50.0)
    taps = c.realize(fs, np.random.default_rng(3))
    n = 4096
    ref = np.fft.fft(taps, n)
    k = np.array([1, 7, 33, 128, 1000])
    got = c.frequency_response(taps, k * fs / n, fs)
    assert np.allclose(got, ref[k], rtol=1e-9, atol=1e-12)


def test_coherence_bandwidth_is_the_stated_definition():
    assert ch.coherence_bandwidth_hz(50e-9) == pytest.approx(1.0 / (2 * np.pi * 50e-9))
    assert np.isinf(ch.coherence_bandwidth_hz(0.0))


def test_snr_parameter_is_the_in_band_snr():
    """A flat channel must read an EVM of -snr_db.  Before the fix the
    parameter was a time-domain SNR and read 10 log10(os_nfft/n_active)
    = 6.26 dB better here, which is enough to mislead a reader."""
    cfg = _cfg()
    flat = ch.TDLChannel(rms_delay_ns=0.0)
    for snr in (25.0, 32.0):
        vals = [cs.packet_readings(cfg, flat, snr, 9, s)["evm_db"]
                for s in range(3)]
        assert cs.median_db(vals) == pytest.approx(-snr, abs=0.4), snr


def test_the_reported_statistic_is_the_median_not_the_power_mean():
    """Zero-forcing through a Rayleigh tone costs 1/|H|^2, whose
    expectation diverges, so the power-domain mean of these EVMs has no
    limit to converge to.  Pin the choice directly: one outlier must not
    move the reported number.  (A power mean of [0, 0, 30] dB is 24.8.)"""
    s = cs.summarize_db([0.0, 0.0, 30.0])
    assert s["median_db"] == 0.0
    assert s["n"] == 3
    assert s["p90_db"] > s["median_db"]


@pytest.mark.slow
def test_the_power_mean_spreads_across_seed_groups_and_the_median_does_not():
    """The measurement behind the choice above, at 50 ns / 30 dB: three
    independent groups of realisations disagree far more in the power
    mean than in the median."""
    cfg = _cfg()
    c = ch.TDLChannel(rms_delay_ns=50.0)
    means, medians = [], []
    for off in range(3):
        v = np.array([cs.packet_readings(cfg, c, 30.0, 9, off * 1000 + s)
                      ["evm_modem_db"] for s in range(24)])
        means.append(10 * np.log10(np.mean(10 ** (v / 10.0))))
        medians.append(float(np.median(v)))
    assert np.ptp(medians) < 1.5, medians
    assert np.ptp(means) > 2.0 * np.ptp(medians), (means, medians)


@pytest.mark.slow
def test_the_nine_tone_smoothing_default_is_a_conducted_mode_choice():
    """0.7.18 picked ``ce_smooth_tones=9`` on a flat chain.  It survives
    a mild channel and does not survive a dispersive one: measured at
    40 MHz / 30 dB in-band SNR, the penalty against the best width on the
    same sweep is under a few tenths of a dB up to 50 ns rms delay and
    several dB at 150 ns, where 9 tones (703 kHz) is a sizeable fraction
    of the 1.06 MHz coherence bandwidth."""
    cfg = _cfg()
    sw = cs.smoothing_sweep(cfg, [0.0, 50.0, 150.0], snr_db=30.0, n_real=12)
    j9 = list(sw["widths"]).index(9)
    penalty = sw["modem_db"][:, j9] - sw["modem_db"].min(axis=1)
    assert penalty[0] < 0.5 and penalty[1] < 0.8, penalty
    assert penalty[2] > 3.0, penalty
    # and the direction: the useful width shrinks as the channel disperses
    assert sw["best_width"][0] >= sw["best_width"][2]
    assert np.isinf(sw["coherence_bw_hz"][0])


@pytest.mark.slow
def test_most_of_the_long_delay_loss_is_the_receiver_not_the_guard_interval():
    """An exponential profile truncated at 6 tau puts 0.25 % of its power
    past the truncation, so crossing the cyclic prefix is a gradual cost,
    not a cliff.  At 150 ns (tail 900 ns, past the 800 ns GI) re-tuning
    the smoothing recovers several dB, which means the fixed 9-tone width
    — not the guard interval — is the larger part of what looked like a
    channel limit."""
    cfg = _cfg()
    c = ch.TDLChannel(rms_delay_ns=150.0)
    assert 6 * 150e-9 > cs.cp_duration_s(cfg)          # premise: past the GI
    at9 = cs.median_db([cs.packet_readings(cfg, c, 30.0, 9, s)["evm_modem_db"]
                        for s in range(12)])
    at3 = cs.median_db([cs.packet_readings(cfg, c, 30.0, 3, s)["evm_modem_db"]
                        for s in range(12)])
    assert at3 < at9 - 3.0, (at3, at9)


def test_cp_duration_is_the_guard_interval():
    """0.8 us for the 11ax 1/16 GI at any bandwidth."""
    assert cs.cp_duration_s(_cfg()) == pytest.approx(0.8e-6, rel=1e-9)
