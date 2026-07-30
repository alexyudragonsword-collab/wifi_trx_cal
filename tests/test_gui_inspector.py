"""The GUI inspector page renders verdicts it did not compute.

Behavior: a real cal-state file renders findings and the step table; a
file that does not parse is reported as a finding, not raised.

Guard: the page contains no verdict wording and no threshold — those
belong to ``wifitrx.handoff.inspector`` and must reach the page as data.
The guard strips docstrings first, and a self-check proves the stripper
does not hide real code.
"""
from __future__ import annotations

import ast
import json
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "app"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

APP = Path(__file__).resolve().parent.parent / "app"


def _doc():
    return {
        "format": "wifitrx-cal-state-v1",
        "tx": {"dc_pre": [0.0, 0.0]},
        "rx": {"dc_post": {}},
        "provenance": {"git_commit": "abc", "git_dirty": False},
        "expiry": {"calibrated_at_c": 25.0, "hold_min_c": -10.0,
                   "hold_max_c": 55.0},
        "results": [
            {"name": "tx_iq", "passed": True, "saturated": None,
             "spec": {"metric": "irr_min_db", "limit": 50.0, "sense": "min"},
             "metrics_before": {"irr_min_db": 28.0},
             "metrics_after": {"irr_min_db": 43.0}},   # violates its spec
            {"name": "rx_iip2", "passed": True, "saturated": True,
             "spec": {}, "metrics_before": {"iip2_dbm": 48.0},
             "metrics_after": {"iip2_dbm": 71.0}},
        ],
    }


@pytest.fixture(scope="module")
def qapp():
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


def _labels(page):
    from PySide6.QtWidgets import QLabel
    return [w.text() for w in page.findChildren(QLabel)]


def test_renders_findings_and_steps(qapp, tmp_path):
    from inspector_page import InspectorPage
    from PySide6.QtWidgets import QTableWidget

    p = tmp_path / "cal_state.json"
    p.write_text(json.dumps(_doc()))
    page = InspectorPage()
    page.load(p)
    text = " ".join(_labels(page))
    # the inspector's spec-violation verdict reached the page as data
    assert "violates" in text
    # and the step table lays out every recorded step
    tables = page.findChildren(QTableWidget)
    step_table = next(t for t in tables if t.columnCount() == 7)
    assert step_table.rowCount() == 2
    assert step_table.item(1, 5).text() == "RAILED"


def test_unparseable_file_is_a_finding_not_an_exception(qapp, tmp_path):
    from inspector_page import InspectorPage
    bad = tmp_path / "junk.json"
    bad.write_text("{this is not json")
    page = InspectorPage()
    page.load(bad)   # must not raise
    assert any("junk.json" in t for t in _labels(page))


def test_missing_file_is_a_finding_not_an_exception(qapp, tmp_path):
    from inspector_page import InspectorPage
    page = InspectorPage()
    page.load(tmp_path / "absent.json")
    assert any("absent.json" in t for t in _labels(page))


def test_run_save_inspect_roundtrip(qapp, tmp_path):
    """The frozen-exe user journey: run a calibration in the Analyses tab,
    save the cal-state JSON, and the inspector tab renders the report —
    the exe has no examples/ or CLI, so this is the only produce path."""
    from main import MainWindow
    from specs import ALL_ANALYSES

    win = MainWindow()
    spec = next(s for s in ALL_ANALYSES if s.key == "full_cal")
    result = spec.run({"bw_mhz": 80, "qam": 256, "seed": 5,
                       "with_dpd": False})
    assert result.cal_state is not None
    win._on_done(result)
    assert win.save_btn.isEnabled()

    out = tmp_path / "cal_state.json"
    win._save_cal_state(str(out))
    assert out.exists()
    # the inspector tab took over and rendered the per-step table
    assert win.tabs.currentWidget() is win.inspector
    from PySide6.QtWidgets import QTableWidget
    tables = win.inspector.findChildren(QTableWidget)
    step_table = next(t for t in tables if t.columnCount() == 7)
    assert step_table.rowCount() >= 10


# ------------------------------------------------- the decides-nothing guard
def _stripped_source() -> str:
    tree = ast.parse((APP / "inspector_page.py").read_text())
    for node in ast.walk(tree):
        if (isinstance(node, ast.Expr)
                and isinstance(node.value, ast.Constant)
                and isinstance(node.value.value, str)):
            node.value.value = ""
    return ast.unparse(tree)


def test_the_page_decides_no_verdict_and_no_threshold():
    src = _stripped_source()
    # finding texts and spec logic live in wifitrx.handoff.inspect; if any
    # of these appear here, the page has started restating the contract
    for token in ("violates", "railed trim", "dirty working tree",
                  "no expiry metadata", "abs_max", "-38", "50.0"):
        assert token not in src, (
            f"{token!r} appears in inspector_page.py; verdicts and "
            "thresholds belong to wifitrx.handoff.inspector and must reach "
            "the page as data")
    # ...and the page really does source its verdicts from the inspector
    assert "inspect_cal_state" in src


def test_the_stripper_does_not_hide_real_code():
    src = _stripped_source()
    assert "InspectorPage" in src and "findings_view" in src
    assert len(src) > 2000, len(src)
