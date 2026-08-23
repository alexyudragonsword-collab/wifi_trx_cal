"""Cal-state inspector page: the file, read as its recipient reads it.

This page decides nothing: every verdict, severity and finding text comes
from ``wifitrx.handoff.inspect.inspect_cal_state`` — the same derivations
the CLI and the standalone script produce — and the step table lays out
the JSON's own content.  ``tests/test_gui_inspector.py`` asserts no
verdict wording or threshold appears in this file, so a fix in the
inspector is automatically a fix here too.

A file that does not parse is rendered as a finding rather than raised:
"cannot be read" is the recipient's actual situation, and the reason is
the answer they need.
"""
from __future__ import annotations

import json
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QFileDialog, QHBoxLayout, QLabel,
                               QPushButton, QScrollArea, QTableWidget,
                               QTableWidgetItem, QVBoxLayout, QWidget)

from inspector_data import fmt as _fmt, inspector_sections
from wifitrx.handoff.inspector import inspect_cal_state

# severity -> colour, by role; which finding gets which severity is the
# inspector's call, never this page's
SEVERITY_COLOURS = {"error": "#a11111", "warning": "#a5560b",
                    "info": "#666666"}




def findings_view(findings: list[dict]) -> QWidget:
    box = QWidget()
    layout = QVBoxLayout(box)
    layout.setContentsMargins(0, 0, 0, 0)
    if not findings:
        layout.addWidget(QLabel("Nothing to report."))
        return box
    for f in findings:
        colour = SEVERITY_COLOURS.get(f.get("severity", ""), "#666666")
        label = QLabel(f"<b>{f.get('step', '-')}</b> — {f.get('message', '')}")
        label.setWordWrap(True)
        label.setStyleSheet(f"color:{colour}; border-left:3px solid {colour};"
                            "padding-left:8px;")
        layout.addWidget(label)
    return box


def fixed_table(rows: list[dict], columns: list[str]) -> QTableWidget:
    """A read-only table whose height fits its content.

    A QTableWidget in a vertical layout otherwise expands to whatever
    space is going spare, so a three-row table sits in a screenful of
    empty grid with the next section pushed off the page.
    """
    view = QTableWidget(len(rows), len(columns))
    view.setHorizontalHeaderLabels(columns)
    view.verticalHeader().setVisible(False)
    view.setAlternatingRowColors(True)
    for r, row in enumerate(rows):
        for c, key in enumerate(columns):
            item = QTableWidgetItem(_fmt(row.get(key, "")))
            # No zero-arg flag constructions here: under Nuitka
            # compilation QTableWidget.EditTriggers() raises
            # "EnumType.__call__() missing 1 required positional
            # argument" while working interpreted (proven by a compiled
            # A/B probe) — it aborted this function mid-render and left
            # the Windows exe showing findings but no tables.
            item.setTextAlignment(Qt.AlignmentFlag.AlignRight
                                  | Qt.AlignmentFlag.AlignVCenter)
            item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            view.setItem(r, c, item)
    view.resizeColumnsToContents()
    view.resizeRowsToContents()
    height = view.horizontalHeader().height() + 2 * view.frameWidth()
    for r in range(view.rowCount()):
        height += view.rowHeight(r)
    view.setFixedHeight(height + 2)
    return view


def section(title: str, body: QWidget) -> QWidget:
    box = QWidget()
    layout = QVBoxLayout(box)
    layout.setContentsMargins(0, 8, 0, 0)
    head = QLabel(title)
    head.setStyleSheet("color:#666; font-weight:bold;")
    layout.addWidget(head)
    layout.addWidget(body)
    return box




class InspectorPage(QWidget):
    """Pick a cal_state.json, then read the verdict on it."""

    # step records of the file just opened, for whoever else can use
    # them; one-way, so this page still consumes nothing from anyone
    loaded = Signal(object, object)

    def __init__(self) -> None:
        super().__init__()
        outer = QVBoxLayout(self)
        bar = QHBoxLayout()
        self.open_btn = QPushButton("Open cal_state.json…")
        self.open_btn.clicked.connect(self._choose)
        self.path_label = QLabel("No file chosen yet.")
        self.path_label.setStyleSheet("color:#666;")
        bar.addWidget(self.open_btn)
        bar.addWidget(self.path_label, 1)
        outer.addLayout(bar)

        self.body = QWidget()
        self.body_layout = QVBoxLayout(self.body)
        area = QScrollArea()
        area.setWidgetResizable(True)
        area.setWidget(self.body)
        outer.addWidget(area, 1)

    def _choose(self) -> None:  # pragma: no cover - native dialog
        chosen, _ = QFileDialog.getOpenFileName(
            self, "Choose a cal-state JSON", "", "JSON files (*.json)")
        if chosen:
            self.load(Path(chosen))

    def load(self, path: Path) -> None:
        self.path_label.setText(str(path))
        self._clear()
        try:
            doc = json.loads(Path(path).read_text(encoding="utf-8"))
            self._render(doc)
            # the file's step records are also what the reference tab's
            # acceptance and capture-cost columns are made of
            self.loaded.emit(doc.get("results") or [], doc.get("fs_hz"))
        except Exception:
            # ANY failure renders as a finding: in a windowed exe there is
            # no console, so a swallowed traceback would just look like a
            # half-drawn page ("displays wrong") with nothing to report
            import html
            import traceback
            self._clear()
            tb = html.escape(traceback.format_exc())
            self.body_layout.addWidget(findings_view([{
                "severity": "error", "step": Path(path).name,
                "message": f"failed to render this file:<br>"
                           f"<pre style='font-size:11px'>{tb}</pre>"}]))
            self.body_layout.addStretch(1)

    def _clear(self) -> None:
        while self.body_layout.count():
            item = self.body_layout.takeAt(0)
            if item.widget() is not None:
                item.widget().deleteLater()

    def _render(self, doc: dict) -> None:
        add = self.body_layout.addWidget
        add(section("Findings", findings_view(inspect_cal_state(doc))))
        # Every table below comes from inspector_data.inspector_sections,
        # the same layout the Android front-end renders — a section added
        # for one front-end therefore appears in both.
        for sec in inspector_sections(doc):
            add(section(sec["title"],
                        fixed_table(sec["rows"], sec["columns"])))
        self.body_layout.addStretch(1)
