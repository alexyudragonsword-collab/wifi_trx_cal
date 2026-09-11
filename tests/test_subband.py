"""Narrow sub-bands: the model's pilot set, the sub-band plan builder,
and whether an impairment cares where in the band the slice sits.

The physics assertions are shapes and orderings, not remembered dB:
phase noise must be flat with offset because it is common-mode, the IQ
image must hurt a centred slice and not an off-centre one because the
image lands outside the occupied set, and a low-pass must get worse
toward the edge because that is where it attenuates.
"""
import numpy as np
import pytest

from wifitrx.link import subband_study as ss
from wifitrx.waveform import OFDMConfig
from wifitrx.waveform import tone_plan as tp
from wifitrx.waveform.pilots import (model_pilot_positions, pilot_positions,
                                     standard_pilot_tones)

HE = 78.125e3


def test_the_default_still_refuses_to_invent_a_pilot_set():
    """A punctured plan has a different pilot set in the standard.  Not
    having that table is a reason to raise, not to guess."""
    cut = tp.punctured(tp.standard(80e6, HE, HE), 80e6, HE, (1,))
    cfg = OFDMConfig(bandwidth_hz=80e6, n_symbols=2, tone_plan=cut)
    with pytest.raises(ValueError, match="does not carry every standard pilot"):
        pilot_positions(cfg)
    assert cfg.pilot_set == "standard"


def test_model_pilots_keep_the_count_and_are_evenly_spaced():
    for bw in (40e6, 80e6, 160e6, 320e6):
        cfg = OFDMConfig(bandwidth_hz=bw, n_symbols=2, tone_plan="standard",
                         pilot_set="model")
        cols = pilot_positions(cfg)
        assert cols.size == standard_pilot_tones(cfg).size, bw
        gaps = np.diff(cols)
        assert gaps.max() - gaps.min() <= 1, (bw, gaps.min(), gaps.max())


def test_model_pilots_are_mirror_symmetric_on_a_symmetric_plan():
    """Built symmetric rather than argued symmetric: the first version
    placed every rank from one formula and claimed the symmetry followed
    by identity, which it did not — the exact ranks sum to n where
    mirror columns must sum to n-1."""
    for bw in (40e6, 160e6):
        for plan in (None, "standard"):
            cfg = OFDMConfig(bandwidth_hz=bw, n_symbols=2, tone_plan=plan,
                             pilot_set="model")
            assert cfg.plan().mirror_ok()
            t = cfg.active_tone_indices()[pilot_positions(cfg)]
            assert np.array_equal(t, -t[::-1]), (bw, plan)


def test_model_pilots_refuse_a_plan_too_small_to_hold_them():
    cfg = OFDMConfig(bandwidth_hz=80e6, n_symbols=2,
                     tone_plan=tp.subband(80e6, HE, 8, 100), pilot_set="model")
    with pytest.raises(ValueError, match="fewer than"):
        model_pilot_positions(cfg)


def test_subband_builder_skips_dc_and_refuses_to_leave_the_channel():
    centred = tp.subband(80e6, HE, 106, 0)
    assert centred.n_active == 105            # DC removed from the span
    assert 0 not in centred.indices
    assert len(centred.segments()) == 2       # a hole where DC was
    off = tp.subband(80e6, HE, 106, 200)
    assert off.n_active == 106 and len(off.segments()) == 1
    with pytest.raises(ValueError, match="leaves the"):
        tp.subband(80e6, HE, 106, 500)
    with pytest.raises(ValueError):
        tp.subband(80e6, HE, 1, 100)


def test_isolating_an_unknown_impairment_raises():
    with pytest.raises(ValueError, match="unknown impairment"):
        ss.study_receiver(80e6, "gremlins")


@pytest.mark.slow
def test_phase_noise_is_flat_with_the_slice_offset():
    """It is common to every tone, so where the slice sits cannot
    matter.  A curve that tilted would mean the isolation leaked."""
    sw = ss.centre_sweep(80e6, 106, [0, 160, 320, 460], -40.0,
                         impairments=("phase noise",))
    pn = sw["evm_db"]["phase noise"]
    assert np.ptp(pn) < 1.0, pn


@pytest.mark.slow
def test_the_iq_image_hurts_a_centred_slice_and_spares_an_offset_one():
    """IQ imbalance folds +f onto -f.  A slice centred on DC contains
    its own mirror, so the image lands on live tones; an off-centre
    slice has empty spectrum at its mirror and barely notices.  Measured
    at 80 MHz / 106 tones / -40 dBm: 13.5 dB."""
    sw = ss.centre_sweep(80e6, 106, [0, 240], -40.0, impairments=("iq",))
    iq = sw["evm_db"]["iq"]
    assert iq[0] > iq[1] + 6.0, iq


@pytest.mark.slow
def test_the_low_pass_gets_worse_toward_the_band_edge():
    """Per-tone equalisation removes a static response exactly, so what
    is left is the noise enhanced on the tones the filter attenuated —
    monotone toward the corner."""
    sw = ss.centre_sweep(80e6, 106, [80, 240, 400, 460], -40.0,
                         impairments=("lpf",))
    lp = sw["evm_db"]["lpf"]
    assert np.all(np.diff(lp) > -0.05), lp       # monotone, up to noise
    assert lp[-1] > lp[0] + 2.0, lp


@pytest.mark.slow
def test_the_best_slice_placement_is_neither_dc_nor_the_edge():
    """The two localised impairments pull in opposite directions, so the
    combined curve has an interior optimum — the result a link team
    would actually use."""
    centres = [0, 80, 240, 400, 460]
    sw = ss.centre_sweep(80e6, 106, centres, -40.0, impairments=("all",))
    a = sw["evm_db"]["all"]
    best = int(np.argmin(a))
    assert 0 < best < len(centres) - 1, (centres, a)
