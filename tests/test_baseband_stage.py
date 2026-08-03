"""The analog baseband stage: what it adds, and what it does not.

B5 asked for three things. Measuring them corrected one of the premises:

- the **noise** the baseband contributes is real and matters most in the
  low-gain states (the referral divides by the RF gain), but it sits
  *before* the VGA, so it cannot make the noise figure depend on the VGA
  setting.  That dependence already existed through the ADC, whose noise
  is post-VGA — the lumped model was not missing it.
- the **compression** is where the VGA dependence actually lives: an
  output ceiling makes the input-referred IP3 fall 1 dB per dB of VGA
  gain, and under a level-servoing AGC it costs the same EVM at any
  antenna power.  Nothing in the lumped per-state IIP3 can express that.

The tests below pin both statements, including the negative one.
"""
from __future__ import annotations

import numpy as np
import pytest

from wifitrx.chain import RxChain, RxParams
from wifitrx.chain.agc import DEFAULT_LNA_STATES
from wifitrx.impairments.baseband import BasebandStage
from wifitrx.link.budget import (adc_equivalent_stage, deembed_states,
                                 effective_iip3_dbm, effective_nf_db)
from wifitrx.units import (dbm_hz_to_v_sqrthz, dbm_to_vpp, v_sqrthz_to_dbm_hz,
                           vpp_to_dbm)
from wifitrx.waveform import OFDMConfig

BW = 160e6


def _cfg():
    return OFDMConfig(bandwidth_hz=BW, qam_order=1024, n_symbols=4,
                      oversampling=4)


def _rx(baseband: BasebandStage | None = None, seed: int = 4):
    """An RX whose ladder matches the baseband stage it is given."""
    bb = baseband or BasebandStage()
    p = RxParams(bandwidth_hz=BW, baseband=bb, seed=seed)
    if bb.enabled:                      # de-embed, or the noise is double
        p = RxParams(bandwidth_hz=BW, baseband=bb, seed=seed,
                     lna_states=deembed_states(p.lna_states, bb))
    p.lpf.fc_nominal_hz = BW / 2 * 1.12
    return RxChain(p, _cfg().sample_rate_hz)


# ------------------------------------------------------------ conversions
def test_voltage_and_swing_conversions_match_hand_calculation():
    """A factor of 1000 or of sqrt(2) here would poison every number
    downstream, so check against values computed by hand."""
    assert float(v_sqrthz_to_dbm_hz(10e-9, 50.0)) == pytest.approx(-147.0,
                                                                   abs=0.02)
    assert float(vpp_to_dbm(1.0, 50.0)) == pytest.approx(3.98, abs=0.02)
    for v in (2e-9, 6e-9, 25e-9):
        assert float(dbm_hz_to_v_sqrthz(v_sqrthz_to_dbm_hz(v))) == \
            pytest.approx(v, rel=1e-9)
    for vpp in (0.4, 1.0, 2.2):
        assert float(dbm_to_vpp(vpp_to_dbm(vpp))) == pytest.approx(vpp,
                                                                   rel=1e-9)


def test_integrated_noise_constructor_round_trips():
    bb = BasebandStage.from_rms_noise(180e-6, bw_hz=BW)
    assert bb.rms_noise_v(BW) == pytest.approx(180e-6, rel=1e-9)


# --------------------------------------------------------------- de-embed
def test_deembed_reproduces_the_stated_cascade():
    """The delivered ladder is the cascade total; splitting it and
    re-cascading must give the same number back, or enabling the stage
    silently degrades every published figure."""
    bb = BasebandStage(enabled=True)
    rf = deembed_states(DEFAULT_LNA_STATES, bb)
    for total, part in zip(DEFAULT_LNA_STATES, rf):
        assert effective_nf_db(part, bb) == pytest.approx(total.nf_db,
                                                          abs=0.001)
        assert part.nf_db < total.nf_db          # the RF part is quieter


def test_baseband_share_grows_toward_the_low_gain_states():
    bb = BasebandStage(enabled=True)
    rf = deembed_states(DEFAULT_LNA_STATES, bb)
    share = [t.nf_db - p.nf_db for t, p in zip(DEFAULT_LNA_STATES, rf)]
    # referred to the antenna the baseband noise divides by the RF gain,
    # so it costs least where the front-end gain is highest
    assert share[0] < 0.2 < share[-1] < 1.5
    # non-decreasing: states 2-4 tie exactly, each trading 6 dB of gain
    # for 6 dB of NF, so the referred share does not move across them
    assert all(b - a > -1e-9 for a, b in zip(share, share[1:])), share


def test_an_impossible_baseband_is_reported_not_absorbed():
    with pytest.raises(ValueError, match="disagree"):
        deembed_states(DEFAULT_LNA_STATES,
                       BasebandStage(noise_v_sqrthz=30e-9, enabled=True))


# ----------------------------------------------------- what it does *not* do
def test_the_noise_figure_does_not_gain_a_vga_dependence():
    """The baseband noise is pre-VGA, so it cannot make NF depend on the
    VGA setting — B5's first premise was wrong.  What VGA dependence
    exists comes from the ADC and predates this stage."""
    p = RxParams(bandwidth_hz=BW)
    adc = adc_equivalent_stage(p.adc.bits, p.adc.fullscale_dbm,
                               p.adc_backoff_db, fs_hz=BW * 4, bw_hz=BW)
    bb = BasebandStage(enabled=True)
    rf = deembed_states(DEFAULT_LNA_STATES, bb)
    for lumped, part in zip(DEFAULT_LNA_STATES, rf):
        for vga in (0.0, 20.0, 40.0):
            assert effective_nf_db(part, bb, vga, adc) == pytest.approx(
                effective_nf_db(lumped, None, vga, adc), abs=0.01)


# ------------------------------------------------------ what it does do
def test_input_referred_ip3_falls_one_db_per_db_of_vga_gain():
    """An output ceiling referred to the input moves with the gain in
    front of it — the signature the lumped per-state IIP3 cannot have."""
    bb = BasebandStage(enabled=True)
    state = deembed_states(DEFAULT_LNA_STATES, bb)[-1]
    ip3 = [effective_iip3_dbm(state, bb, v) for v in (20.0, 30.0, 40.0)]
    assert ip3[1] - ip3[0] == pytest.approx(-10.0, abs=0.5)
    assert ip3[2] - ip3[1] == pytest.approx(-10.0, abs=0.5)
    # …while the lumped model reports the same IIP3 at every VGA setting
    flat = [effective_iip3_dbm(DEFAULT_LNA_STATES[-1], None, v)
            for v in (20.0, 30.0, 40.0)]
    assert max(flat) - min(flat) < 1e-9


def test_the_ceiling_costs_the_same_evm_at_any_antenna_power():
    """The AGC servos the VGA *output* to a fixed level, so an
    output-referred ceiling is the one impairment a gain state cannot
    escape: the penalty at -40 dBm and at -20 dBm is the same."""
    from wifitrx.link.baseband_study import compression_penalty_db

    rx, cfg = _rx(BasebandStage(enabled=True)), _cfg()
    strong = compression_penalty_db(rx, cfg, -20.0)
    mid = compression_penalty_db(rx, cfg, -40.0)
    assert strong > 1.0, strong           # the ceiling is doing something
    assert mid == pytest.approx(strong, abs=0.5)


def test_more_adc_backoff_relieves_the_ceiling():
    """…and the only lever that helps is backing off the ADC, which is
    what prices adc_backoff_db."""
    from wifitrx.link.baseband_study import backoff_study

    rows = backoff_study(_rx(BasebandStage(enabled=True)), _cfg(),
                         p_in_dbm=-40.0, backoffs_db=(6.0, 12.0, 18.0))
    evm = [r["evm_db"] for r in rows]
    assert evm[0] > evm[1] > evm[2]       # more backoff, better EVM


def test_the_global_nonlinearity_switch_also_removes_the_ceiling():
    """``nonlin_enabled`` gates the per-state IM3, and the baseband
    ceiling has to follow it.

    Otherwise a contribution split that turns "the nonlinearity" off
    leaves the ceiling behind and books it as residual — which is
    exactly how it was first measured, with the ceiling showing up in a
    curve labelled PN + ISI + IQ + ADC.
    """
    from dataclasses import replace as _replace

    rng = np.random.default_rng(11)
    x = 0.01 * (rng.standard_normal(4096)      # -40 dBm mean, so the
                + 1j * rng.standard_normal(4096))   # peaks reach the ceiling

    def out(nonlin: bool, swing: float) -> np.ndarray:
        rx = _rx(BasebandStage(enabled=True), seed=7)
        rx.noise_enabled = False           # keep the test about distortion
        rx.params.nonlin_enabled = nonlin
        rx.params.baseband = _replace(rx.params.baseband,
                                      out_swing_vpp=swing)
        rx.agc(-40.0)
        return rx(x, rng=np.random.default_rng(1))

    # switch off: indistinguishable from a chain whose ceiling is out of reach
    assert np.array_equal(out(False, 1.0), out(False, 1e6))
    # switch on: the ceiling still bites, so the test above is not vacuous
    assert not np.array_equal(out(True, 1.0), out(True, 1e6))


# -------------------------------------------------------------- default off
def test_disabled_by_default_and_bit_identical():
    """Every delivered number was measured with the lumped ladder; the
    stage must not move any of them until it is switched on."""
    assert not RxParams().baseband.enabled
    x = np.zeros(4096, dtype=complex)
    out = []
    for _ in range(2):
        rx = _rx(seed=7)
        rx.agc(-50.0)
        out.append(rx(x, rng=np.random.default_rng(1)))
    assert np.array_equal(out[0], out[1])

    rx_on = _rx(BasebandStage(enabled=True), seed=7)
    rx_on.agc(-50.0)
    y = rx_on(x, rng=np.random.default_rng(1))
    assert not np.array_equal(out[0], y)   # …and it does change something
