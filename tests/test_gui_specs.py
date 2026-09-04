"""N5 tests: every workbench analysis spec runs headless; window builds
offscreen."""
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "app"))

from specs import ALL_ANALYSES  # noqa: E402

FAST_PARAMS = {
    "full_cal": {"bw_mhz": 80, "qam": 256, "seed": 5, "with_dpd": False,
                 "std": "11ax/be", "rx_hp": False, "baseband": False,
                 "agc_rebw": False, "bb_noise_nv": 5},
    "full_cal_steps": {"bw_mhz": 80, "qam": 256, "seed": 5,
                       "with_dpd": False, "std": "11ax/be",
                       "rx_hp": False, "baseband": False,
                       "agc_rebw": False, "bb_noise_nv": 5},
    "rx_evm_sweep": {"bw_mhz": 80, "qam": 256, "seed": 5,
                     "std": "11ax/be", "rx_hp": False, "baseband": False,
                     "agc_rebw": False, "bb_noise_nv": 5},
    "bb_noise_sweep": {"bw_mhz": 80, "qam": 256, "seed": 5,
                       "std": "11ax/be", "agc_rebw": True, "quick": True},
    "drift_tracking": {"bw_mhz": 80, "n_states": 3},
    "blocker_desense": {"bw_mhz": 160, "offset_mhz": 200.0,
                        "p_sig_dbm": -60.0},
    "pn_cpe_study": {"bw_mhz": 80, "std": "11ax/be", "lo_count": "single",
                     "n_frames": 2, "vco_1f3_khz": 0.0, "seed": 0},
    "spur_planner": {"bw_mhz": 320, "band": "6g"},
}


@pytest.mark.parametrize("spec", ALL_ANALYSES, ids=lambda s: s.key)
def test_spec_runs(spec):
    params = FAST_PARAMS[spec.key]
    assert set(p.name for p in spec.params) == set(params), \
        "FAST_PARAMS out of sync with spec params"
    result = spec.run(params)
    assert result.metrics, spec.key
    assert result.figure is not None


def test_legacy_standard_setup():
    """The 11ac/n selector builds the legacy numerology (312.5 kHz
    spacing, long GI, 4x symbols) and rejects bandwidths the legacy
    standards never defined."""
    from specs import _cal_setup

    cfg, tx, rx, path = _cal_setup({"bw_mhz": 40, "qam": 64, "seed": 1,
                                    "std": "11ac/n"})
    assert cfg.subcarrier_spacing_hz == 312.5e3
    assert cfg.fft_size == 128
    assert cfg.n_active == 114          # 11n 40 MHz: 108 data + 6 pilots
    assert cfg.cp_len == 32             # 0.8 us long GI
    assert cfg.n_symbols == 24
    with pytest.raises(ValueError, match="160 MHz"):
        _cal_setup({"bw_mhz": 320, "qam": 64, "seed": 1, "std": "11ac/n"})
    # default remains 11ax
    cfg2, *_ = _cal_setup({"bw_mhz": 20, "qam": 256, "seed": 1})
    assert cfg2.subcarrier_spacing_hz == 78.125e3


def test_rx_hp_rebalances_thresholds():
    """The RX high-performance knob shifts NF/IIP3 AND re-solves every
    hand-over at the balance point t = (2*IIP3_i + NF_{i+1} - 89)/3."""
    from specs import _cal_setup

    from math import log10

    _, _, rx, _ = _cal_setup({"bw_mhz": 80, "qam": 256, "seed": 5,
                              "rx_hp": True})
    st = rx.params.lna_states
    assert st[0].nf_db == 2.5 and st[0].iip3_dbm == -18.0
    const = -174.0 + 10.0 * log10(320e6)   # 320 MHz anchor convention
    for i, s in enumerate(st[:-1]):
        expect = (2 * s.iip3_dbm + st[i + 1].nf_db + const) / 3
        assert s.max_input_dbm == pytest.approx(expect, abs=0.06), i
    assert st[-1].max_input_dbm == 10.0   # last-state ceiling kept


def test_agc_rebw_moves_the_thresholds_to_the_run_bandwidth():
    """The shipped ladder solves the noise-vs-IM3 balance once at
    320 MHz and uses one register set at every bandwidth.  `agc_rebw`
    re-solves at the run's own bandwidth; the balance point moves by a
    third of the bandwidth change, so 20 MHz sits 4 dB below 320 MHz.

    Off, the factory table must come through untouched — a run that
    doesn't ask for the what-if must not silently get it.
    """
    from math import log10

    from specs import _cal_setup
    from wifitrx.chain.agc import DEFAULT_LNA_STATES

    base = {"bw_mhz": 20, "qam": 64, "seed": 5}
    _, _, rx_off, _ = _cal_setup(base)
    assert rx_off.params.lna_states == DEFAULT_LNA_STATES

    _, _, rx_on, _ = _cal_setup({**base, "agc_rebw": True})
    st = rx_on.params.lna_states
    const = -174.0 + 10.0 * log10(20e6)
    for i, s in enumerate(st[:-1]):
        expect = (2 * s.iip3_dbm + st[i + 1].nf_db + const) / 3
        assert s.max_input_dbm == pytest.approx(expect, abs=0.06), i
    assert st[-1].max_input_dbm == 10.0          # last-state ceiling kept

    # The shift is a third of the bandwidth change, not a free
    # parameter.  Check it solved-against-solved: the shipped table is
    # not the bare formula everywhere (state 5 sits 1.4 dB off it), so
    # comparing the factory numbers would measure that hand-adjustment
    # instead of the anchor.
    # Exact shift is 10*log10(320/20)/3 = 4.014 dB; the solver rounds
    # each threshold to 0.1 dB, so a difference of rounded values lands
    # on 4.0 or 4.1.
    from wifitrx.chain.agc import rebalance_thresholds
    at320 = rebalance_thresholds(DEFAULT_LNA_STATES, bandwidth_hz=320e6)
    for a, b in zip(at320[:-1], st[:-1]):
        assert a.max_input_dbm - b.max_input_dbm == pytest.approx(4.014,
                                                                  abs=0.09)


def test_agc_anchor_is_explicit_for_every_ladder_transform():
    """rx_hp and the baseband stage both re-solve thresholds because
    they change the ladder.  Which bandwidth they anchor at must follow
    `agc_rebw` too, not be decided per branch — that inconsistency is
    what this test exists to prevent coming back."""
    from math import log10

    from specs import _cal_setup

    for extra in ({"rx_hp": True}, {"baseband": True}):
        for rebw, anchor in ((False, 320e6), (True, 20e6)):
            _, _, rx, _ = _cal_setup({"bw_mhz": 20, "qam": 64, "seed": 5,
                                      "agc_rebw": rebw, **extra})
            st = rx.params.lna_states
            const = -174.0 + 10.0 * log10(anchor)
            # the effective NF/IIP3 of the baseband branch are not
            # reproduced here; check the anchor through the spacing
            # between the solved thresholds instead, which the constant
            # shifts rigidly
            solved = [s.max_input_dbm for s in st[:-1]]
            ref = [(2 * s.iip3_dbm + st[i + 1].nf_db + const) / 3
                   for i, s in enumerate(st[:-1])]
            offs = [a - b for a, b in zip(solved, ref)]
            assert max(offs) - min(offs) < 1.5, (extra, rebw, offs)


def test_step_through_matches_one_shot():
    """The step-through mode's per-step snapshots are observers: the
    corrections it programs must be bit-identical to the one-shot mode's
    (AGC runtime state is saved/restored around every snapshot — without
    that, mid-sequence snapshots would shift the level the IQ cals see)."""
    from specs import run_full_cal, run_full_cal_steps

    params = FAST_PARAMS["full_cal"]
    one = run_full_cal(dict(params))
    step = run_full_cal_steps(dict(params))
    assert step.figures and len(step.figures) >= 10
    for side in ("tx_state", "rx_state"):
        assert one.cal_state[side] == step.cal_state[side], side
    assert one.metrics["tx_evm_db"] == step.metrics["tx_evm_db"]


def test_mainwindow_offscreen():
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    pytest.importorskip("PySide6")
    try:
        from PySide6.QtWidgets import QApplication
    except ImportError as e:          # missing system GL libs on headless CI
        pytest.skip(f"Qt runtime unavailable: {e}")

    import main as app_main

    app = QApplication.instance() or QApplication([])  # noqa: F841
    # the QApplication must outlive the widgets built below
    win = app_main.MainWindow()
    # form rebuilds for every registered analysis without crashing
    for i in range(win.combo.count()):
        win.combo.setCurrentIndex(i)
        assert win.widgets
    win.close()


def test_bb_noise_knob_sweeps_the_stage_not_the_rf_ladder():
    """The density knob sets the baseband stage; the RF-only front end
    is de-embedded at the fixed 6 nV reference so it stays one part
    across the sweep.  40 nV must therefore (a) not raise — a
    same-density de-embed would — and (b) leave the underlying RF
    ladder identical to the 5 nV run, with only the stage and the
    re-solved thresholds differing."""
    from specs import _cal_setup

    base = {"bw_mhz": 80, "qam": 256, "seed": 5, "baseband": True}
    _, _, rx5, _ = _cal_setup({**base, "bb_noise_nv": 5})
    _, _, rx40, _ = _cal_setup({**base, "bb_noise_nv": 40})

    assert rx5.params.baseband.noise_v_sqrthz == pytest.approx(5e-9)
    assert rx40.params.baseband.noise_v_sqrthz == pytest.approx(40e-9)
    # same RF-only part: gains/NF/IIP3 identical, only the hand-over
    # thresholds move (they are re-solved with the stage's effective
    # figures, which is the study)
    for a, b in zip(rx5.params.lna_states, rx40.params.lna_states):
        assert (a.gain_db, a.nf_db, a.iip3_dbm) == (b.gain_db, b.nf_db,
                                                    b.iip3_dbm)
    t5 = [s.max_input_dbm for s in rx5.params.lna_states[:-1]]
    t40 = [s.max_input_dbm for s in rx40.params.lna_states[:-1]]
    assert any(x != y for x, y in zip(t5, t40))
    # a noisier baseband raises the effective NF, and the balance point
    # t = (2*IIP3 + NF + const)/3 moves a third of that with it —
    # thresholds rise, never fall
    assert all(y >= x for x, y in zip(t5, t40))


def test_pn_study_reads_the_closed_form_and_orders_the_mechanisms():
    """The phase-noise/CPE study is an isolation measurement (phase
    noise only) whose two genie configurations have closed forms:
    config 1 = int S_phi df, config 2 = int S_phi [1 - sinc^2(f T)] df.
    Eight frames at 80 MHz / 11ax read -43.94 / -44.22 dB against
    -43.81 / -44.10 dB closed form (single-frame spread ~0.3 dB rms).
    The mechanisms then stack in one direction: CPE removal can only
    help (config 2 <= 1); the LTF channel estimate freezes its own ICI
    into every symbol (config 3 sits 1.7 dB above 2, no averaging
    across the packet); the 8-pilot CPE adds its estimator noise
    common-mode (config 4 above 3, +0.33 dB measured)."""
    from specs import run_pn_cpe_study

    m = run_pn_cpe_study(dict(FAST_PARAMS["pn_cpe_study"], n_frames=8)).metrics
    assert abs(m["evm_no_cpe_db"] - m["closed_form_total_db"]) < 0.3
    assert abs(m["evm_genie_cpe_db"] - m["closed_form_ici_db"]) < 0.3
    assert m["evm_genie_cpe_db"] <= m["evm_no_cpe_db"]
    assert 1.0 < m["ltf_penalty_db"] < 3.0        # 3 dB = single LTF bound
    assert m["pilot_penalty_db"] > 0.05
    assert m["n_pilots"] == 8
    assert m["f_cpe_3db_khz"] == pytest.approx(34.6, abs=0.1)
    assert 4.0 < m["cpe_tracked_pct"] < 10.0


def test_pilot_cpe_reduces_to_the_genie_when_every_tone_is_a_pilot():
    """Same estimator, different averaging set: with all tones declared
    pilots the two must agree to rounding, and a pure common rotation is
    taken out exactly by the pilot form."""
    import numpy as np
    from wifitrx.metrics.cpe import correct_cpe, correct_cpe_pilots

    rng = np.random.default_rng(3)
    ref = rng.choice([-1.0, 1.0], size=(4, 64)) + 0j
    rot = np.exp(1j * rng.uniform(-1.0, 1.0, size=(4, 1)))
    rx = ref * rot + 0.05 * (rng.standard_normal((4, 64))
                             + 1j * rng.standard_normal((4, 64)))
    cols = np.arange(64)
    assert np.allclose(correct_cpe_pilots(rx, cols, ref), correct_cpe(rx, ref))
    clean = correct_cpe_pilots(ref * rot, np.array([3, 17, 40, 61]),
                               ref[:, [3, 17, 40, 61]])
    assert np.allclose(clean, ref)
