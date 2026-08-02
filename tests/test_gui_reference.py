"""The Reference tab shows derived material, not transcribed material.

Behavior: every registry entry builds (SVGs parse, tables have rows),
the page renders each one offscreen, and the two run-dependent tables
fill in once results are handed over.

Guard: ``app/reference.py`` hand-types no step name and no threshold —
the sequence, its constraints and the acceptance specs must arrive from
``wifitrx.cal.reference``, so that a change in ``cal/deps.py`` reaches
the GUI and the tutorial together.  A second guard keeps the committed
schematic assets in step with their generator.
"""
from __future__ import annotations

import ast
import os
import re
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "app"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from wifitrx.cal.reference import (calibration_order, dependency_edges,
                                   dependency_graph_svg)


def _entries():
    import reference
    return reference.ALL_REFERENCE


def test_every_entry_builds():
    for entry in _entries():
        assert (entry.svg is None) != (entry.table is None), entry.key
        if entry.svg is not None:
            svg = entry.svg()
            ET.fromstring(svg)
            assert len(svg) > 2000, entry.key
        else:
            columns, rows = entry.table(None)
            assert columns
            for row in rows:
                assert len(row) == len(columns), (entry.key, row)


def test_run_dependent_tables_start_empty_and_fill():
    import reference

    _, rows = reference.budget_table(None)
    assert rows == []                      # no run yet: nothing to show
    _, order = reference.order_table(None)
    assert {r[3] for r in order} == {reference.DASH}

    results = [{"name": "tx_iq", "cost": {"captures": 4, "samples": 131072},
                "spec": {"metric": "irr_min_db", "limit": 50.0,
                         "sense": "min"}}]
    _, rows = reference.budget_table(results)
    assert rows[0][0] == "tx_iq" and rows[-1][0] == "total"
    _, order = reference.order_table(results)
    spec_cell = next(r[3] for r in order if r[1] == "tx_iq")
    assert "irr_min_db" in spec_cell and "50" in spec_cell


def test_dependency_graph_draws_its_arrowheads():
    """Explicit polygons, not <defs><marker>: marker support is recent
    in Qt's SVG Tiny renderer and the GUI advertises PySide6 >= 6.6."""
    svg = dependency_graph_svg()
    assert "<marker" not in svg
    assert svg.count("<polygon") == len(dependency_edges())


def test_graph_badges_index_the_reason_table():
    edges = dependency_edges()
    assert [e["n"] for e in edges] == list(range(1, len(edges) + 1))
    svg = dependency_graph_svg()
    for e in edges:                        # every badge number is drawn
        assert f">{e['n']}</text>" in svg
    steps = {r["step"] for r in calibration_order()}
    for e in edges:
        req, name = e["edge"].split(" → ")
        assert req in steps and name in steps


def test_page_renders_every_entry():
    pytest.importorskip("PySide6")
    try:
        from PySide6.QtWidgets import QApplication
    except ImportError as exc:            # missing GL libs on a bare runner
        pytest.skip(str(exc))
    from PySide6.QtCore import Qt

    app = QApplication.instance() or QApplication([])
    from reference_page import ReferencePage

    page = ReferencePage()
    page.resize(1000, 700)
    seen = 0
    for i in range(page.list.count()):
        item = page.list.item(i)
        if not item.data(Qt.ItemDataRole.UserRole):
            continue                       # group header
        page.list.setCurrentRow(i)
        assert page._entry is not None
        seen += 1
    assert seen == len(_entries())
    del app


def test_mainwindow_has_the_reference_tab():
    pytest.importorskip("PySide6")
    try:
        from PySide6.QtWidgets import QApplication
    except ImportError as exc:
        pytest.skip(str(exc))
    app = QApplication.instance() or QApplication([])
    import main

    win = main.MainWindow()
    titles = [win.tabs.tabText(i) for i in range(win.tabs.count())]
    assert "Reference" in titles
    del app


def _stripped_source(path: Path) -> str:
    """Module source with docstrings blanked (prose may say anything)."""
    tree = ast.parse(path.read_text())
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef,
                             ast.AsyncFunctionDef)):
            if (node.body and isinstance(node.body[0], ast.Expr)
                    and isinstance(node.body[0].value, ast.Constant)
                    and isinstance(node.body[0].value.value, str)):
                node.body[0].value.value = ""
    return ast.unparse(tree)


def test_the_registry_transcribes_no_step_and_no_threshold():
    src = _stripped_source(ROOT / "app" / "reference.py")
    for step in (r["step"] for r in calibration_order()):
        assert step not in src, (
            f"{step!r} is hand-typed in app/reference.py; the sequence must "
            "come from wifitrx.cal.reference so cal/deps.py stays the only "
            "source")
    # reading a result's ``spec`` field is data passing; *rendering* an
    # acceptance clause is a judgement, and it belongs to
    # cal.reference.format_spec
    for token in ("≥", "≤"):
        assert token not in src, (
            f"{token!r} in app/reference.py: acceptance clauses are formatted "
            "by wifitrx.cal.reference, not here")
    assert "calibration_order" in src and "dependency_edges" in src


def test_committed_schematic_assets_match_their_generator():
    pytest.importorskip("schemdraw")
    out = subprocess.run(
        [sys.executable, str(ROOT / "tools" / "build_assets.py"), "--check"],
        capture_output=True, text=True, cwd=ROOT,
        env={**os.environ, "MPLBACKEND": "Agg"})
    assert out.returncode == 0, out.stdout + out.stderr


def test_assets_render_in_qt_without_warnings():
    """The diagrams reach the GUI through Qt's SVG renderer, which is a
    different parser from a browser's: it rejects a glyph definition
    with no path data (matplotlib emits the space glyph that way), and
    every <use> of it then resolves to nothing.  Nothing visible is lost
    for a space, but the same defect in a real glyph would be silent, so
    assert the shape of the file and that it paints."""
    pytest.importorskip("PySide6")
    try:
        from PySide6.QtGui import QColor, QGuiApplication, QImage, QPainter
        from PySide6.QtSvg import QSvgRenderer
    except ImportError as exc:
        pytest.skip(str(exc))
    from PySide6.QtCore import QByteArray

    app = QGuiApplication.instance() or QGuiApplication([])
    paths = sorted((ROOT / "assets" / "schematics").glob("*.svg"))
    assert len(paths) == 4
    for path in paths:
        svg = path.read_text()
        assert not re.search(r'<path id="[^"]+"(?![^>]*\sd=)', svg), (
            f"{path.name} has a glyph definition with no path data")
        renderer = QSvgRenderer(QByteArray(svg.encode()))
        assert renderer.isValid(), path.name
        size = renderer.defaultSize()
        img = QImage(size.width(), size.height(), QImage.Format.Format_RGB32)
        img.fill(QColor("white"))
        painter = QPainter(img)
        renderer.render(painter)
        painter.end()
        ink = sum(1 for y in range(0, size.height(), 3)
                  for x in range(0, size.width(), 3)
                  if img.pixelColor(x, y) != QColor("white"))
        assert ink > 200, (path.name, ink)      # not a blank page
    del app


def test_a_loaded_cal_state_fills_the_budget_table(tmp_path):
    """Opening a delivered bundle populates the reference tables too —
    the file carries each step's cost, so the capture budget is readable
    without re-running the calibration."""
    pytest.importorskip("PySide6")
    try:
        from PySide6.QtWidgets import QApplication
    except ImportError as exc:
        pytest.skip(str(exc))
    import json

    app = QApplication.instance() or QApplication([])
    import main

    doc = {"format": "wifitrx-cal-state-v1", "tx": {}, "rx": {},
           "results": [{"name": "tx_iq", "passed": True, "saturated": None,
                        "spec": {"metric": "irr_min_db", "limit": 50.0,
                                 "sense": "min"},
                        "cost": {"captures": 4, "samples": 131072},
                        "metrics_before": {"irr_min_db": 28.0},
                        "metrics_after": {"irr_min_db": 55.0}}]}
    path = tmp_path / "cal_state.json"
    path.write_text(json.dumps(doc))

    win = main.MainWindow()
    win.inspector.load(path)                 # emits loaded -> reference
    from reference import budget_table, order_table

    assert win.reference._results, "the inspector did not hand the file over"
    _, budget = budget_table(win.reference._results)
    assert [r[0] for r in budget] == ["tx_iq", "total"]
    _, order = order_table(win.reference._results)
    assert "irr_min_db" in next(r[3] for r in order if r[1] == "tx_iq")
    del app
