"""wifitrx workbench: PySide6 GUI over the declarative analysis registry.

Run with:  python app/main.py
The form, worker invocation and result views are generated from
``app/specs.py``; analyses run in a worker thread and never touch pyplot
(plain Figure + FigureCanvasQTAgg).
"""
from __future__ import annotations

import sys
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

try:
    from PySide6.QtCore import QThread, Signal
    from PySide6.QtWidgets import (QApplication, QCheckBox, QComboBox,
                                   QDoubleSpinBox, QFormLayout, QHBoxLayout,
                                   QLabel, QMainWindow, QPlainTextEdit,
                                   QPushButton, QSpinBox, QSplitter,
                                   QTableWidget, QTableWidgetItem, QTabWidget,
                                   QVBoxLayout, QWidget)
except ImportError as exc:  # pragma: no cover - environment-dependent
    raise ImportError(
        "the workbench needs PySide6, which is an optional extra:\n"
        "    pip install 'wifitrx[gui]'\n"
        "the library, CLI and the stdlib-only cal-state inspector all work "
        "without it") from exc

from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg

from inspector_page import InspectorPage
from specs import ALL_ANALYSES, AnalysisResult, AnalysisSpec, ParamSpec


class Worker(QThread):
    done = Signal(object)
    failed = Signal(str)

    def __init__(self, spec: AnalysisSpec, params: dict):
        super().__init__()
        self.spec = spec
        self.params = params

    def run(self) -> None:
        try:
            self.done.emit(self.spec.run(self.params))
        except Exception:
            self.failed.emit(traceback.format_exc())


def _widget_for(p: ParamSpec):
    if p.kind == "bool":
        w = QCheckBox()
        w.setChecked(bool(p.default))
        w.value = w.isChecked
        return w
    if p.kind == "choice":
        w = QComboBox()
        for c in p.choices:
            w.addItem(str(c), c)
        w.setCurrentIndex(list(p.choices).index(p.default))
        w.value = w.currentData
        return w
    if p.kind == "int":
        w = QSpinBox()
        w.setRange(int(p.minimum or 0), int(p.maximum or 1_000_000))
        w.setValue(int(p.default))
        w.value = w.value if False else w.cleanText  # placeholder
        w.value = lambda w=w: int(w.text())
        return w
    w = QDoubleSpinBox()
    w.setRange(float(p.minimum if p.minimum is not None else -1e12),
               float(p.maximum if p.maximum is not None else 1e12))
    w.setDecimals(3)
    w.setValue(float(p.default))
    w.value = lambda w=w: float(w.cleanText().replace(",", ""))
    return w


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("wifitrx workbench")
        self.resize(1100, 700)
        self.worker: Worker | None = None

        left = QWidget()
        lv = QVBoxLayout(left)
        self.combo = QComboBox()
        for spec in ALL_ANALYSES:
            self.combo.addItem(spec.title, spec)
        self.combo.currentIndexChanged.connect(self._rebuild_form)
        lv.addWidget(self.combo)
        self.desc = QLabel()
        self.desc.setWordWrap(True)
        lv.addWidget(self.desc)
        self.form_holder = QWidget()
        lv.addWidget(self.form_holder)
        self.run_btn = QPushButton("Run")
        self.run_btn.clicked.connect(self._run)
        lv.addWidget(self.run_btn)
        self.status = QLabel("")
        lv.addWidget(self.status)
        lv.addStretch(1)

        right = QWidget()
        rv = QVBoxLayout(right)
        self.table = QTableWidget(0, 2)
        self.table.setHorizontalHeaderLabels(["metric", "value"])
        rv.addWidget(self.table, 1)
        self.text = QPlainTextEdit()
        self.text.setReadOnly(True)
        self.text.setMaximumHeight(120)
        rv.addWidget(self.text)
        self.canvas_holder = QVBoxLayout()
        rv.addLayout(self.canvas_holder, 3)
        self.canvas: FigureCanvasQTAgg | None = None

        split = QSplitter()
        split.addWidget(left)
        split.addWidget(right)
        split.setSizes([320, 780])

        # two audiences, one window: a developer runs analyses, a cal-state
        # recipient opens a JSON and reads the verdict — neither should
        # scroll past the other's page
        self.tabs = QTabWidget()
        self.tabs.addTab(split, "Analyses")
        self.inspector = InspectorPage()
        self.tabs.addTab(self.inspector, "Cal-state inspector")
        self.setCentralWidget(self.tabs)
        self._rebuild_form()

    # ------------------------------------------------------------ form
    def _rebuild_form(self) -> None:
        spec: AnalysisSpec = self.combo.currentData()
        self.desc.setText(spec.description)
        # one persistent QFormLayout, cleared and refilled per analysis —
        # widget replacement + deferred deletion leaves stale rows visible
        if self.form_holder.layout() is None:
            self.form_holder.setLayout(QFormLayout())
        form: QFormLayout = self.form_holder.layout()
        while form.rowCount():
            form.removeRow(0)
        self.widgets = {}
        for p in spec.params:
            w = _widget_for(p)
            if p.tooltip:
                w.setToolTip(p.tooltip)
            self.widgets[p.name] = w
            form.addRow(p.label, w)

    # ------------------------------------------------------------ run
    def _run(self) -> None:
        spec: AnalysisSpec = self.combo.currentData()
        params = {name: w.value() for name, w in self.widgets.items()}
        self.run_btn.setEnabled(False)
        self.status.setText("running…")
        self.worker = Worker(spec, params)
        self.worker.done.connect(self._on_done)
        self.worker.failed.connect(self._on_failed)
        self.worker.start()

    def _on_done(self, result: AnalysisResult) -> None:
        self.run_btn.setEnabled(True)
        self.status.setText("done")
        self.table.setRowCount(0)
        for k, v in result.metrics.items():
            row = self.table.rowCount()
            self.table.insertRow(row)
            self.table.setItem(row, 0, QTableWidgetItem(str(k)))
            val = f"{v:.2f}" if isinstance(v, float) else str(v)
            self.table.setItem(row, 1, QTableWidgetItem(val))
        self.text.setPlainText(result.text)
        if self.canvas is not None:
            self.canvas_holder.removeWidget(self.canvas)
            self.canvas.deleteLater()
            self.canvas = None
        if result.figure is not None:
            self.canvas = FigureCanvasQTAgg(result.figure)
            self.canvas_holder.addWidget(self.canvas)

    def _on_failed(self, tb: str) -> None:
        self.run_btn.setEnabled(True)
        self.status.setText("failed")
        self.text.setPlainText(tb)


def main() -> None:
    app = QApplication(sys.argv)
    win = MainWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
