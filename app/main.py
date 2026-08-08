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
                                   QDoubleSpinBox, QFormLayout,
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
from PySide6.QtGui import QIcon

from inspector_page import InspectorPage
from reference_page import ReferencePage
from specs import ALL_ANALYSES, AnalysisResult, AnalysisSpec, ParamSpec


def _icon_path() -> str:
    """assets/icon.png, whether running from source or a frozen exe.

    PyInstaller onefile extracts bundled data under sys._MEIPASS; Nuitka
    onefile keeps data files relative to the extracted __file__ layout.
    """
    base = Path(getattr(sys, "_MEIPASS",
                        Path(__file__).resolve().parent.parent))
    return str(base / "assets" / "icon.png")


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
        # enabled after a run that produced cal-state material; saving
        # also loads the file into the inspector tab — the only way a
        # frozen exe can produce and then inspect the deliverable
        self.save_btn = QPushButton("Save cal-state JSON…")
        self.save_btn.setEnabled(False)
        self.save_btn.clicked.connect(self._save_cal_state)
        lv.addWidget(self.save_btn)
        self.status = QLabel("")
        lv.addWidget(self.status)
        lv.addStretch(1)
        self._cal_state: dict | None = None

        right = QWidget()
        rv = QVBoxLayout(right)
        self.table = QTableWidget(0, 2)
        self.table.setHorizontalHeaderLabels(["metric", "value"])
        rv.addWidget(self.table, 1)
        self.text = QPlainTextEdit()
        self.text.setReadOnly(True)
        self.text.setMaximumHeight(120)
        rv.addWidget(self.text)
        # page selector for multi-figure results (step-through mode);
        # hidden while a result has a single figure
        self.page_combo = QComboBox()
        self.page_combo.setVisible(False)
        self.page_combo.currentIndexChanged.connect(self._show_page)
        rv.addWidget(self.page_combo)
        self.canvas_holder = QVBoxLayout()
        rv.addLayout(self.canvas_holder, 3)
        self.canvas: FigureCanvasQTAgg | None = None
        self._pages: list = []

        split = QSplitter()
        split.addWidget(left)
        split.addWidget(right)
        split.setSizes([320, 780])

        # two audiences, one window: a developer runs analyses, a cal-state
        # recipient opens a JSON and reads the verdict — neither should
        # scroll past the other's page.  Both need the same reference
        # material (what runs before what, and why), which used to live
        # only in the built tutorial.
        self.tabs = QTabWidget()
        self.tabs.addTab(split, "Analyses")
        self.inspector = InspectorPage()
        self.tabs.addTab(self.inspector, "Cal-state inspector")
        self.reference = ReferencePage()
        self.tabs.addTab(self.reference, "Reference")
        self.inspector.loaded.connect(self.reference.set_run_results)
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
        self._cal_state = result.cal_state
        self.save_btn.setEnabled(result.cal_state is not None)
        if result.cal_state:
            # the reference tab's acceptance-spec and capture-cost columns
            # are this session's measurements, not stored constants
            self.reference.set_run_results(result.cal_state.get("results"),
                                           result.cal_state.get("fs_hz"))
        self.table.setRowCount(0)
        for k, v in result.metrics.items():
            row = self.table.rowCount()
            self.table.insertRow(row)
            self.table.setItem(row, 0, QTableWidgetItem(str(k)))
            val = f"{v:.2f}" if isinstance(v, float) else str(v)
            self.table.setItem(row, 1, QTableWidgetItem(val))
        self.text.setPlainText(result.text)
        self._pages = list(result.figures) or (
            [("figure", result.figure)] if result.figure is not None else [])
        self.page_combo.blockSignals(True)
        self.page_combo.clear()
        for title, _ in self._pages:
            self.page_combo.addItem(title)
        self.page_combo.setVisible(len(self._pages) > 1)
        last = len(self._pages) - 1     # step-through: land on the summary
        self.page_combo.setCurrentIndex(max(last, 0))
        self.page_combo.blockSignals(False)
        self._show_page(last)

    def _show_page(self, idx: int) -> None:
        if self.canvas is not None:
            self.canvas_holder.removeWidget(self.canvas)
            self.canvas.deleteLater()
            self.canvas = None
        if 0 <= idx < len(self._pages):
            self.canvas = FigureCanvasQTAgg(self._pages[idx][1])
            self.canvas_holder.addWidget(self.canvas)

    def _on_failed(self, tb: str) -> None:
        self.run_btn.setEnabled(True)
        self.status.setText("failed")
        self.text.setPlainText(tb)

    def _save_cal_state(self, path=None) -> None:
        """Serialize the last run's correction state and open it in the
        inspector tab.  ``path`` is settable for tests; interactively a
        save dialog asks."""
        if self._cal_state is None:
            return
        if not path:  # pragma: no cover - native dialog
            from PySide6.QtWidgets import QFileDialog
            path, _ = QFileDialog.getSaveFileName(
                self, "Save cal-state JSON", "cal_state.json",
                "JSON files (*.json)")
            if not path:
                return
        from wifitrx.cal.base import save_cal_state
        save_cal_state(path, self._cal_state["tx_state"],
                       self._cal_state["rx_state"],
                       self._cal_state["results"],
                       fs_hz=self._cal_state.get("fs_hz"),
                       conditions=self._cal_state.get("conditions"))
        self.status.setText(f"saved {path}")
        self.inspector.load(Path(path))
        self.tabs.setCurrentWidget(self.inspector)


def main() -> None:
    app = QApplication(sys.argv)
    icon = QIcon(_icon_path())
    if not icon.isNull():
        app.setWindowIcon(icon)
    win = MainWindow()
    win.show()

    # frozen-build diagnostics: a windowed exe has no console, so these
    # env hooks let a build be exercised without interaction —
    #   WIFITRX_INSPECT=<json>  auto-load into the inspector tab
    #   WIFITRX_TAB=reference   open a named tab (the reference diagrams
    #                           are the only feature that needs the Qt SVG
    #                           plugin, so a screenshot of that tab is what
    #                           proves the plugin got bundled)
    #   WIFITRX_SHOT=<png>      screenshot the window ~2 s later and exit
    import os
    inspect_file = os.environ.get("WIFITRX_INSPECT")
    if inspect_file:
        win.tabs.setCurrentWidget(win.inspector)
        win.inspector.load(Path(inspect_file))
    tab = os.environ.get("WIFITRX_TAB", "").lower()
    if tab:
        for i in range(win.tabs.count()):
            if win.tabs.tabText(i).lower().startswith(tab):
                win.tabs.setCurrentIndex(i)
                break
    shot = os.environ.get("WIFITRX_SHOT")
    if shot:
        from PySide6.QtCore import QTimer

        def _grab() -> None:
            win.resize(1400, 900)
            win.grab().save(shot)
            app.quit()

        QTimer.singleShot(2000, _grab)
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
