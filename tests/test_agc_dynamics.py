"""AGC settling dynamics (impairments/agc_dynamics, chain/rx, the STF and
link/agc_dynamics_study): every check is against a closed form or an
invariant, not a remembered number."""
from dataclasses import replace

import numpy as np
import pytest

from wifitrx.chain import RxChain
from wifitrx.impairments.agc_dynamics import AgcDynamics
from wifitrx.link import agc_dynamics_study as st
from wifitrx.waveform import OFDMConfig
from wifitrx.waveform.pilots import generate_ofdm_with_pilots
from wifitrx.waveform.preamble import (STF_PERIOD_S, build_frame, channel_estimate,
                                       estimate_cfo)

BW = 40e6


def _cfg(n_symbols=4):
    return OFDMConfig(bandwidth_hz=BW, qam_order=256, n_symbols=n_symbols,
                      oversampling=4)


def test_envelopes_are_piecewise_then_exponential():
    """Before the attack: start gain / VGA / DC exactly; after it the
    LNA gain steps, the VGA and DC decay to their targets with their
    own time constants — e^-1 at one tau, e^-3 at three."""
    dyn = AgcDynamics(enabled=True, attack_s=1e-6, vga_tau_s=0.5e-6, dc_tau_s=2e-6)
    fs = 160e6
    n = int(20e-6 * fs)
    n_att, gain, vga, dc = dyn.envelopes(n, fs, 10.0, 2.0, 40.0, 4.0,
                                         0.02 + 0.01j, 0.005 - 0.002j)
    assert n_att == 160
    assert np.all(gain[:n_att] == 10.0) and np.all(gain[n_att:] == 2.0)
    assert vga[0] == 40.0 and dc[0] == 0.02 + 0.01j
    k1 = n_att + int(round(0.5e-6 * fs))
    assert vga[k1] == pytest.approx(4.0 + 36.0 * np.exp(-1.0), rel=1e-3)
    k3 = n_att + int(round(6e-6 * fs))
    assert dc[k3] == pytest.approx((0.005 - 0.002j) + (0.015 + 0.012j) * np.exp(-3.0),
                                   rel=1e-3)
    assert vga[-1] == pytest.approx(4.0, abs=1e-6)


def test_disabled_dynamics_leave_the_chain_bit_identical():
    """The default is off, and off must be the chain as it was: same
    samples, not merely the same EVM."""
    cfg = _cfg()
    rxp = st.study_receiver(BW, seed=1)
    wf, _ = generate_ofdm_with_pilots(cfg)
    x = wf.x * 1e-2
    outs = []
    for dyn in (AgcDynamics(enabled=False), AgcDynamics(enabled=False, attack_s=5e-6)):
        rx = RxChain(replace(rxp, agc_dynamics=dyn), cfg.sample_rate_hz)
        rx.agc(-40.0)
        outs.append(rx(x, rng=np.random.default_rng(0)))
    assert np.array_equal(outs[0], outs[1])


def test_stf_is_transparent_to_the_estimators_and_at_data_power():
    """Ten 0.8 us periods make the 8 us L-STF; the estimators index
    from the LTF and read exactly what they read without it, and the
    STF carries the data part's average power (what the AGC settles on)."""
    cfg = _cfg()
    wf, _ = generate_ofdm_with_pilots(cfg)
    f0 = build_frame(cfg, data=wf)
    f1 = build_frame(cfg, data=wf, stf_periods=10)
    fs = cfg.sample_rate_hz
    assert f1.stf_len == int(round(10 * STF_PERIOD_S * fs))
    assert f1.preamble_len == f0.preamble_len + f1.stf_len
    assert estimate_cfo(f1.x, f1, fs) == pytest.approx(0.0, abs=1e-6)
    assert np.allclose(channel_estimate(f1.x, f1), channel_estimate(f0.x, f0))
    p_stf = np.mean(np.abs(f1.x[:f1.stf_len]) ** 2)
    assert p_stf == pytest.approx(np.mean(np.abs(wf.x) ** 2), rel=0.05)
    # periodic: the second period repeats the first
    period = int(round(STF_PERIOD_S * fs))
    assert np.allclose(f1.x[:period], f1.x[period:2 * period])


def test_attack_delay_is_free_until_the_ltf_and_a_cliff_inside_it():
    """The STF is discarded, so an AGC that finishes anywhere before the
    LTF costs nothing (within the noise realization); a switch under the
    LTF is frozen into the channel estimate and the packet is lost."""
    cfg = _cfg(n_symbols=6)
    rxp = st.study_receiver(BW, seed=0)
    gi2_s = 2 * cfg.cp_len * cfg.oversampling / cfg.sample_rate_hz
    ltf_start = st.STF_S + gi2_s
    attacks = np.array([0.8e-6, 4.0e-6, st.STF_S, ltf_start - 0.2e-6,
                        ltf_start + 2.0e-6])
    sw = st.sweep(rxp, cfg, -30.0, AgcDynamics(enabled=True), "attack_s", attacks)
    settled = sw["settled"]["evm_modem_db"]
    assert sw["rows"][0]["states_crossed"] >= 2       # a real ladder walk
    assert np.all(np.abs(sw["evm_modem_db"][:4] - settled) < 0.2)
    assert sw["evm_modem_db"][4] > settled + 15.0
    assert st.budget(attacks, sw["evm_modem_db"], settled) == pytest.approx(
        ltf_start - 0.2e-6)


def test_vga_settling_budget_is_a_fraction_of_the_gi2():
    """Decision at the STF's end: the VGA has the 1.6 us GI2 to settle
    before the LTF.  The cost is monotone in the time constant and the
    0.5 dB budget sits between GI2/8 and GI2/2 (measured 0.4 < tau_b <
    0.8 us at 40 MHz, -30 dBm) — a 39 dB VGA swing needs several time
    constants inside the GI2.  Symbol by symbol the penalty is flat:
    the error is in the frozen channel estimate, not in the data."""
    cfg = _cfg(n_symbols=6)
    rxp = st.study_receiver(BW, seed=0)
    gi2_s = 2 * cfg.cp_len * cfg.oversampling / cfg.sample_rate_hz
    taus = np.array([0.1, 0.2, 0.4, 0.8, 1.6]) * 1e-6
    late = AgcDynamics(enabled=True, attack_s=st.STF_S)
    sw = st.sweep(rxp, cfg, -30.0, late, "vga_tau_s", taus)
    settled = sw["settled"]["evm_modem_db"]
    assert np.all(np.diff(sw["evm_modem_db"]) >= -0.05)   # monotone (noise)
    b = st.budget(taus, sw["evm_modem_db"], settled)
    assert gi2_s / 8 <= b <= gi2_s / 2, (b, gi2_s)
    assert sw["evm_modem_db"][-1] > settled + 10.0
    ps = sw["per_symbol_db"][-1]
    assert ps.max() - ps.min() < 1.0


def test_budget_stops_at_the_first_excursion():
    t = np.array([1.0, 2.0, 3.0, 4.0])
    assert st.budget(t, np.array([0.0, 0.2, 1.0, 0.1]), 0.0) == 2.0
    assert np.isnan(st.budget(t, np.array([1.0, 0.0, 0.0, 0.0]), 0.0))
    assert st.budget(t, np.zeros(4), 0.0) == 4.0
