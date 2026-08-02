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
                 "std": "11ax/be", "rx_hp": False, "baseband": False},
    "full_cal_steps": {"bw_mhz": 80, "qam": 256, "seed": 5,
                       "with_dpd": False, "std": "11ax/be",
                       "rx_hp": False, "baseband": False},
    "rx_evm_sweep": {"bw_mhz": 80, "qam": 256, "seed": 5,
                     "std": "11ax/be", "rx_hp": False, "baseband": False},
    "drift_tracking": {"bw_mhz": 80, "n_states": 3},
    "blocker_desense": {"bw_mhz": 160, "offset_mhz": 200.0,
                        "p_sig_dbm": -60.0},
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
