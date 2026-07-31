"""N5 tests: every workbench analysis spec runs headless; window builds
offscreen."""
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "app"))

from specs import ALL_ANALYSES  # noqa: E402

FAST_PARAMS = {
    "full_cal": {"bw_mhz": 80, "qam": 256, "seed": 5, "with_dpd": False},
    "full_cal_steps": {"bw_mhz": 80, "qam": 256, "seed": 5,
                       "with_dpd": False},
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

    app = QApplication.instance() or QApplication([])
    win = app_main.MainWindow()
    # form rebuilds for every registered analysis without crashing
    for i in range(win.combo.count()):
        win.combo.setCurrentIndex(i)
        assert win.widgets
    win.close()
