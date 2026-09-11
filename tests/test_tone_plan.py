"""Tone plans: the standard's real occupancy, puncturing, and every
place that used to assume the active tones were one contiguous block.

The load-bearing property is that the default changes nothing: the
frozen cal-state fixture, the golden and every number measured before
0.7.31 were taken on the contiguous block, and `tone_plan=None` must
still produce it bit for bit.
"""
import numpy as np
import pytest

from wifitrx.waveform import OFDMConfig, generate_ofdm
from wifitrx.waveform import tone_plan as tp
from wifitrx.waveform.pilots import pilot_positions, standard_pilot_tones
from wifitrx.waveform.preamble import smooth_channel_estimate

HE = 78.125e3


def test_the_default_is_the_historical_block_bit_for_bit():
    """The whole change rests on this."""
    for bw in (20e6, 40e6, 160e6, 320e6):
        cfg = OFDMConfig(bandwidth_hz=bw, n_symbols=2)
        half = cfg.n_active // 2
        want = np.concatenate([np.arange(-half, 0), np.arange(1, half + 1)])
        assert np.array_equal(cfg.active_tone_indices(), want), bw
    a = generate_ofdm(OFDMConfig(bandwidth_hz=40e6, n_symbols=3, seed=7))
    b = generate_ofdm(OFDMConfig(bandwidth_hz=40e6, n_symbols=3, seed=7,
                                 tone_plan=None))
    assert np.array_equal(a.x, b.x)


def test_a_standard_plan_repositions_tones_without_changing_the_count():
    """Same n_active, so every sqrt(n_active) power normalisation and
    every symbol shape is untouched; what moves is where the tones sit."""
    for bw in (20e6, 40e6, 80e6, 160e6, 320e6):
        block = OFDMConfig(bandwidth_hz=bw, n_symbols=2)
        std = OFDMConfig(bandwidth_hz=bw, n_symbols=2, tone_plan="standard")
        assert std.n_active == block.n_active, bw
        assert std.plan().mirror_ok()
        assert not np.array_equal(std.active_tone_indices(),
                                  block.active_tone_indices()), bw
        # the real plan reaches further out, because it skips tones inside
        assert std.active_tone_indices().max() > block.active_tone_indices().max()


def test_the_standard_plan_has_real_holes_and_the_block_has_one():
    """160/320 MHz carry inter-segment nulls; the block never does."""
    block = OFDMConfig(bandwidth_hz=160e6, n_symbols=2).plan()
    std = OFDMConfig(bandwidth_hz=160e6, n_symbols=2, tone_plan="standard").plan()
    assert block.is_contiguous and len(block.segments()) == 2
    assert not std.is_contiguous and len(std.segments()) == 4
    assert sum(s.size for s in std.segments()) == std.n_active


def test_pilots_land_exactly_on_the_standard_tones_with_a_real_plan():
    """The rank map of 0.7.17 exists only because the block has no holes.
    With the plan it becomes an identity, and the SCO lever arm is the
    standard's exactly — measured: the rank map is off by up to 2 tones
    at 40 MHz and 16 at 160 MHz."""
    for bw, rank_err in ((40e6, 2), (160e6, 16)):
        std = OFDMConfig(bandwidth_hz=bw, n_symbols=2, tone_plan="standard")
        cols = pilot_positions(std)
        assert np.array_equal(std.active_tone_indices()[cols],
                              standard_pilot_tones(std))
        block = OFDMConfig(bandwidth_hz=bw, n_symbols=2)
        got = block.active_tone_indices()[pilot_positions(block)]
        assert np.abs(got - standard_pilot_tones(block)).max() == rank_err, bw


def test_the_direct_pilot_lookup_is_what_makes_a_non_standard_plan_report():
    """A first version of the test above did not discriminate, and a
    mutation caught it: on the *standard* plan the model's active set IS
    the standard's occupied set, so rank-mapping and direct lookup agree
    exactly and disabling the direct branch changed nothing.  What the
    direct branch uniquely buys is a plan that is neither — a punctured
    one names the pilot tones it lost, where the rank map could only
    report a count mismatch."""
    base = tp.standard(320e6, HE, HE)
    cfg = OFDMConfig(bandwidth_hz=320e6, n_symbols=2,
                     tone_plan=tp.punctured(base, 320e6, HE, (3,)))
    with pytest.raises(ValueError, match="does not carry every standard pilot"):
        pilot_positions(cfg)


def test_smoothing_inside_a_segment_equals_the_old_behaviour():
    """No segments, or one segment covering everything, must reproduce
    the plain moving average — otherwise the default path moved."""
    h = np.exp(1j * np.linspace(0, 3, 200)) * np.linspace(0.5, 1.5, 200)
    plain = smooth_channel_estimate(h, 9)
    one = smooth_channel_estimate(h, 9, [np.arange(200)])
    assert np.allclose(plain, one)
    assert np.array_equal(smooth_channel_estimate(h, 1), h)


def test_smoothing_across_a_null_is_wrong_and_segments_fix_it():
    """The silent one.  A window straddling a gap averages across a
    discontinuity: nothing changes shape, nothing becomes NaN, the
    estimate is just wrong near every hole.  Measured on a 30 ns
    deterministic response at 160 MHz, worst-tone error -16.5 dB
    unsegmented against -30.6 dB segmented."""
    cfg = OFDMConfig(bandwidth_hz=160e6, n_symbols=2, tone_plan="standard")
    plan = cfg.plan()
    idx = plan.indices
    h = np.exp(-2j * np.pi * idx * cfg.subcarrier_spacing_hz * 30e-9)
    naive = smooth_channel_estimate(h, 9)
    seg = smooth_channel_estimate(h, 9, plan.segments())
    e_naive = np.abs(naive - h).max()
    e_seg = np.abs(seg - h).max()
    assert e_seg < e_naive / 3.0, (e_seg, e_naive)
    # and it is local: only tones within a window of a hole differ
    assert 0 < (np.abs(naive - seg) > 1e-9).sum() <= 4 * 9


def test_puncturing_removes_whole_subchannels_and_breaks_the_mirror():
    base = tp.standard(320e6, HE, HE)
    cut = tp.punctured(base, 320e6, HE, (3,))
    assert cut.n_active < base.n_active
    assert cut.n_active / base.n_active == pytest.approx(1 - 1 / 16, abs=0.02)
    assert not cut.mirror_ok()          # asymmetric by construction
    with pytest.raises(ValueError):
        tp.punctured(base, 320e6, HE, (16,))
    with pytest.raises(ValueError):
        tp.punctured(base, 20e6, HE, (0,))


def test_rx_iq_refuses_an_asymmetric_plan_instead_of_dropping_tones():
    """It fits the image correction on mirror pairs, and unmatched tones
    used to be skipped with a bare ``continue``: a quietly smaller fit
    set and a quietly worse correction.  Called for real with a punctured
    plan rather than grepped for — a guard that reads the source would
    pass on the name alone."""
    from wifitrx.cal.rx_iq import estimate_rx_iq_from_frame
    base = tp.standard(80e6, HE, HE)
    cut = tp.punctured(base, 80e6, HE, (1,))
    assert not cut.mirror_ok()
    cfg = OFDMConfig(bandwidth_hz=80e6, qam_order=64, n_symbols=2,
                     oversampling=4, tone_plan=cut, seed=1)
    wf = generate_ofdm(cfg)
    with pytest.raises(ValueError, match="symmetric about DC"):
        estimate_rx_iq_from_frame(wf.x, wf)
    # and the symmetric plan it is meant to run on still works
    sym = OFDMConfig(bandwidth_hz=80e6, qam_order=64, n_symbols=2,
                     oversampling=4, tone_plan="standard", seed=1)
    wsym = generate_ofdm(sym)
    estimate_rx_iq_from_frame(wsym.x, wsym)


def test_a_plan_must_be_sorted_unique_and_skip_dc():
    with pytest.raises(ValueError):
        tp.TonePlan(np.array([-2, 0, 2]))
    with pytest.raises(ValueError):
        tp.TonePlan(np.array([2, 1]))
    with pytest.raises(ValueError):
        tp.TonePlan(np.array([1, 1]))
    with pytest.raises(ValueError):
        tp.TonePlan(np.array([], dtype=int))


def test_an_unknown_plan_name_or_bandwidth_raises_rather_than_guessing():
    with pytest.raises(ValueError, match="unknown tone_plan"):
        OFDMConfig(bandwidth_hz=40e6, n_symbols=2, tone_plan="he").plan()
    with pytest.raises(ValueError, match="no 11ax/be tone plan"):
        OFDMConfig(bandwidth_hz=60e6, n_symbols=2,
                   tone_plan="standard").plan()
    with pytest.raises(ValueError, match="no legacy"):
        OFDMConfig(bandwidth_hz=320e6, n_symbols=2, subcarrier_spacing_hz=312.5e3,
                   tone_plan="standard").plan()


def test_a_waveform_on_a_standard_plan_round_trips():
    """Generation and demodulation must agree on the same tone set."""
    from wifitrx.waveform import demodulate_ofdm
    cfg = OFDMConfig(bandwidth_hz=40e6, qam_order=256, n_symbols=4,
                     oversampling=4, tone_plan="standard", seed=3)
    wf = generate_ofdm(cfg)
    got = demodulate_ofdm(wf.x, wf)
    assert got.shape == wf.tx_symbols.shape
    err = np.abs(got - wf.tx_symbols).max() / np.abs(wf.tx_symbols).mean()
    assert err < 1e-9, err
