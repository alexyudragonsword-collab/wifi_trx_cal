"""Reference page: the tutorial's block diagrams and calibration tables,
without leaving the workbench.

Like the inspector page, this one decides nothing — it lays out whatever
``reference.ALL_REFERENCE`` provides, and every entry there is derived
from ``wifitrx`` or from a committed asset.  Two entries need numbers
that only exist after a calibration has run; ``set_run_results`` feeds
them from the session's own run rather than from a stored constant.
"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QByteArray, Qt
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtSvgWidgets import QSvgWidget
from PySide6.QtWidgets import (QFileDialog, QHBoxLayout, QLabel, QListWidget,
                               QListWidgetItem, QPushButton, QScrollArea,
                               QVBoxLayout, QWidget)

from inspector_page import fixed_table
from reference import ALL_REFERENCE

MAX_COL_WIDTH = 620      # keep one long prose column from filling the screen


def _table(columns: list[str], rows: list[list[str]]) -> QWidget:
    """A read-only table for list-of-lists rows.

    Reuses the inspector's height-fitting builder (a table in a vertical
    layout otherwise eats all the spare space), then left-aligns the
    text, caps the widest column and puts the untruncated cell in the
    tooltip — the edge-reason column is a sentence, not a number.
    """
    if not rows:
        label = QLabel("No data yet.")
        label.setStyleSheet("color:#666;")
        return label
    view = fixed_table([dict(zip(columns, r)) for r in rows], columns)
    for r in range(view.rowCount()):
        for c in range(view.columnCount()):
            item = view.item(r, c)
            if item is None:
                continue
            item.setTextAlignment(Qt.AlignmentFlag.AlignLeft
                                  | Qt.AlignmentFlag.AlignVCenter)
            item.setToolTip(item.text())
    for c in range(view.columnCount()):
        if view.columnWidth(c) > MAX_COL_WIDTH:
            view.setColumnWidth(c, MAX_COL_WIDTH)
    return view


class _Svg(QSvgWidget):
    """An SVG that keeps its aspect ratio and fits the page width."""

    def __init__(self, svg: str):
        super().__init__()
        self._data = QByteArray(svg.encode())
        self.load(self._data)
        size = QSvgRenderer(self._data).defaultSize()
        self._aspect = (size.height() / size.width()) if size.width() else 0.5
        self._natural_width = max(size.width(), 1)
        self.setMinimumHeight(80)

    def fit(self, width: int, height: int) -> None:
        """Scale to the page, bounded by both axes.

        Width alone is not enough: the architecture diagram is wide and
        tall, and a width-fitted copy runs off the bottom of the page.
        """
        w = min(width, height / self._aspect if self._aspect else width)
        w = max(min(w, self._natural_width * 2), 200)
        self.setFixedSize(int(w), int(w * self._aspect))

    def svg_text(self) -> str:
        return bytes(self._data).decode()


class ReferencePage(QWidget):
    def __init__(self):
        super().__init__()
        self._results = None            # last run's CalResult list, if any
        self._fs_hz = None              # …and the rate it was captured at
        self._entry = None
        self._svg: _Svg | None = None

        self.list = QListWidget()
        self.list.setMaximumWidth(260)
        group = None
        for entry in ALL_REFERENCE:
            if entry.group != group:
                group = entry.group
                head = QListWidgetItem(group)
                head.setFlags(Qt.ItemFlag.NoItemFlags)
                head.setForeground(Qt.GlobalColor.gray)
                self.list.addItem(head)
            item = QListWidgetItem("   " + entry.title)
            item.setData(Qt.ItemDataRole.UserRole, entry.key)
            self.list.addItem(item)
        self.list.currentItemChanged.connect(self._on_pick)

        self.save_btn = QPushButton("Save SVG…")
        self.save_btn.clicked.connect(self._save_svg)
        self.save_btn.setVisible(False)

        self.body = QWidget()
        self.body_layout = QVBoxLayout(self.body)
        area = QScrollArea()
        area.setWidgetResizable(True)
        area.setWidget(self.body)
        self._area = area

        right = QVBoxLayout()
        right.addWidget(self.save_btn, alignment=Qt.AlignmentFlag.AlignRight)
        right.addWidget(area)
        layout = QHBoxLayout(self)
        layout.addWidget(self.list)
        layout.addLayout(right, 1)

        for i in range(self.list.count()):
            if self.list.item(i).data(Qt.ItemDataRole.UserRole):
                self.list.setCurrentRow(i)
                break

    # ------------------------------------------------------------ data
    def set_run_results(self, results, fs_hz=None) -> None:
        """Feed the acceptance-spec and capture-cost columns from a run."""
        self._results = results
        self._fs_hz = fs_hz
        self._render()

    def _viewport(self) -> tuple[int, int]:
        """Space a diagram may occupy: the page minus title and note."""
        vp = self._area.viewport()
        return vp.width() - 30, vp.height() - 80

    # ----------------------------------------------------------- render
    def _on_pick(self, item, _prev=None) -> None:
        key = item.data(Qt.ItemDataRole.UserRole) if item else None
        self._entry = next((e for e in ALL_REFERENCE if e.key == key), None)
        self._render()

    def _clear(self) -> None:
        while self.body_layout.count():
            w = self.body_layout.takeAt(0).widget()
            if w is not None:
                # unparent before the deferred delete: deleteLater alone
                # leaves the widget a visible child of the body until the
                # event loop gets round to it, so entries pile up on top
                # of each other while switching
                w.setParent(None)
                w.deleteLater()
        self._svg = None

    def _render(self) -> None:
        self._clear()
        entry = self._entry
        if entry is None:
            return
        title = QLabel(f"<b>{entry.title}</b>")
        self.body_layout.addWidget(title)
        try:
            if entry.svg is not None:
                self._svg = _Svg(entry.svg())
                self._svg.fit(*self._viewport())
                self.body_layout.addWidget(self._svg)
            else:
                columns, rows = entry.table(self._results,
                                            self._fs_hz)
                self.body_layout.addWidget(_table(columns, rows))
        except Exception as exc:        # a missing asset must not kill the tab
            bad = QLabel(f"cannot render this entry: {exc}")
            bad.setWordWrap(True)
            bad.setStyleSheet("color:#a11111;")
            self.body_layout.addWidget(bad)
        if entry.note:
            note = QLabel(entry.note)
            note.setWordWrap(True)
            note.setStyleSheet("color:#666;")
            self.body_layout.addWidget(note)
        self.body_layout.addStretch(1)
        self.save_btn.setVisible(entry.svg is not None)

    def resizeEvent(self, event):        # keep the diagram fitted
        super().resizeEvent(event)
        if self._svg is not None:
            self._svg.fit(*self._viewport())

    def _save_svg(self) -> None:
        if self._svg is None or self._entry is None:
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Save diagram", f"{self._entry.key}.svg", "SVG (*.svg)")
        if path:
            Path(path).write_text(self._svg.svg_text())
