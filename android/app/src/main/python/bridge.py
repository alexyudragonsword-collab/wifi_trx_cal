"""Android bridge: JSON-in/JSON-out facade over the analysis registry.

This is the only Python file written for the Android app.  Everything it
exposes is a thin serialization layer over the same modules the desktop
workbench uses: ``app/specs.py`` (analysis registry), ``app/reference.py``
(reference tables/diagrams), ``wifitrx.handoff.inspector`` (stdlib-only
cal-state verdicts) and ``wifitrx.cal.base.save_cal_state``.

Contract: every public function takes/returns JSON strings only (the
Kotlin side passes them through to the WebView untouched), never raises —
errors come back as ``{"ok": false, "error": ...}`` so a Python traceback
can be shown in the UI instead of killing the process.

Figures are serialized as SVG text so the WebView can pan/zoom them as
vectors — the Android counterpart of the desktop NavigationToolbar.
"""
from __future__ import annotations

import os

os.environ.setdefault("MPLBACKEND", "Agg")  # before any matplotlib import

import io          # noqa: E402
import json        # noqa: E402
import sys         # noqa: E402
import traceback   # noqa: E402
from pathlib import Path  # noqa: E402

# On-device, Chaquopy merges the configured srcDirs (this directory, the
# repo's src/ and app/) onto one sys.path root.  On the desktop (contract
# tests) resolve the repo layout explicitly.
_REPO = Path(__file__).resolve().parents[5]
for _p in (_REPO / "app", _REPO / "src"):
    if _p.is_dir() and str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

_last_cal_state: dict | None = None


def _jsonable(v):
    """Coerce numpy scalars/arrays and Paths into JSON-safe values."""
    import numpy as np
    if isinstance(v, (np.integer,)):
        return int(v)
    if isinstance(v, (np.floating,)):
        return float(v)
    if isinstance(v, np.ndarray):
        return [_jsonable(x) for x in v.tolist()]
    if isinstance(v, dict):
        return {str(k): _jsonable(x) for k, x in v.items()}
    if isinstance(v, (list, tuple)):
        return [_jsonable(x) for x in v]
    if isinstance(v, (str, int, float, bool)) or v is None:
        return v
    return str(v)


def _svg(fig) -> str:
    from matplotlib.backends.backend_svg import FigureCanvasSVG
    buf = io.StringIO()
    FigureCanvasSVG(fig).print_svg(buf)
    return buf.getvalue()


def _fail() -> str:
    return json.dumps({"ok": False, "error": traceback.format_exc()})


def list_specs() -> str:
    """Registry dump: the single source the UI builds its forms from."""
    try:
        from specs import ALL_ANALYSES
        specs = []
        for s in ALL_ANALYSES:
            specs.append({
                "key": s.key, "title": s.title,
                "description": s.description,
                "params": [{
                    "name": p.name, "label": p.label, "kind": p.kind,
                    "default": _jsonable(p.default),
                    "choices": [_jsonable(c) for c in p.choices],
                    "minimum": p.minimum, "maximum": p.maximum,
                    "tooltip": p.tooltip,
                } for p in s.params],
            })
        return json.dumps({"ok": True, "specs": specs})
    except Exception:
        return _fail()


def run(key: str, params_json: str) -> str:
    """Run one analysis; figures come back as per-page SVG text."""
    global _last_cal_state
    try:
        from specs import ALL_ANALYSES
        spec = next(s for s in ALL_ANALYSES if s.key == key)
        params = json.loads(params_json)
        result = spec.run(params)
        pages = list(result.figures) or (
            [("figure", result.figure)] if result.figure is not None else [])
        _last_cal_state = result.cal_state
        return json.dumps({
            "ok": True,
            "metrics": _jsonable(result.metrics),
            "text": result.text,
            "pages": [{"title": t, "svg": _svg(f)} for t, f in pages],
            "has_cal_state": result.cal_state is not None,
        })
    except Exception:
        return _fail()


def save_cal_state(dir_path: str) -> str:
    """Serialize the last run's correction state (README auto-generated
    beside it by save_cal_state, same as the desktop save button)."""
    try:
        if _last_cal_state is None:
            return json.dumps({"ok": False,
                               "error": "no cal-state from the last run"})
        from wifitrx.cal.base import save_cal_state as _save
        out = Path(dir_path) / "cal_state.json"
        _save(str(out), _last_cal_state["tx_state"],
              _last_cal_state["rx_state"], _last_cal_state["results"],
              fs_hz=_last_cal_state.get("fs_hz"),
              conditions=_last_cal_state.get("conditions"))
        readme = out.parent / "README.md"
        return json.dumps({"ok": True, "path": str(out),
                           "readme": str(readme) if readme.exists() else None})
    except Exception:
        return _fail()


def inspect_cal_state(json_text: str) -> str:
    """Inspector verdicts plus the same tables the Qt page renders.

    Sections come from ``inspector_data.inspector_sections`` — shared with
    the desktop page so the two inspectors cannot show different things
    (they did once: this front-end had findings only).
    """
    try:
        from inspector_data import inspector_sections
        from wifitrx.handoff.inspector import (format_findings,
                                               inspect_cal_state as _inspect)
        doc = json.loads(json_text)
        findings = _inspect(doc)
        return json.dumps({"ok": True, "findings": _jsonable(findings),
                           "text": format_findings(findings),
                           "sections": _jsonable(inspector_sections(doc))})
    except Exception:
        return _fail()


def reference_data() -> str:
    """Reference tab payload: shipped SVG diagrams + live-computed tables.

    ``results``/``fs_hz`` from the last run refresh the acceptance and
    capture-cost columns, mirroring the desktop Reference tab.
    """
    try:
        from reference import ALL_REFERENCE
        results = (_last_cal_state or {}).get("results")
        fs_hz = (_last_cal_state or {}).get("fs_hz")
        entries = []
        for e in ALL_REFERENCE:
            item = {"key": e.key, "group": e.group, "title": e.title,
                    "note": e.note}
            if e.svg is not None:
                item["svg"] = e.svg()
            else:
                cols, rows = e.table(results, fs_hz)
                item["columns"] = list(cols)
                item["rows"] = _jsonable([list(r) for r in rows])
            entries.append(item)
        return json.dumps({"ok": True, "entries": entries})
    except Exception:
        return _fail()


# Golden tolerances: Android BLAS/FFT builds differ from the desktop's, so
# bit identity is never the claim.  Shared by the emulator GoldenTest and
# the in-app self-check — one implementation, one pair of numbers.
GOLDEN_ABS_DB = 0.05
GOLDEN_REL = 1.0e-3


def _platform() -> dict:
    """What actually executed the physics — the point of a self-check."""
    import platform
    import numpy
    import scipy
    return {"python": sys.version.split()[0], "numpy": numpy.__version__,
            "scipy": scipy.__version__, "machine": platform.machine(),
            "android_abi": ", ".join(_abis()) or platform.machine()}


def _abis() -> list:
    try:                                        # Chaquopy exposes the ABI
        from java.lang import System            # noqa: F401
        from android.os import Build
        return [str(a) for a in Build.SUPPORTED_ABIS]
    except Exception:
        return []


def self_check() -> str:
    """Replay the desktop-generated golden cases on THIS device.

    The emulator job can only adjudicate the ABI it runs on (x86_64); a
    phone is arm64 with a different OpenBLAS.  Shipping the golden values
    inside the APK lets the device that actually matters answer the
    question — and lets a user re-answer it after any Android, phone or
    wheel change.

    Verdict shape mirrors the CI test exactly because the CI test calls
    this function: a metric passes within GOLDEN_ABS_DB absolute or
    GOLDEN_REL relative, non-numeric values must match exactly.
    """
    try:
        from specs import ALL_ANALYSES
        golden = json.loads(
            (Path(__file__).resolve().parent / "golden.json")
            .read_text(encoding="utf-8"))
        cases, all_passed = [], True
        for case in golden:
            spec = next(s for s in ALL_ANALYSES if s.key == case["key"])
            result = spec.run(dict(case["params"]))
            got = _jsonable(result.metrics)
            pages = len(result.figures) or (result.figure is not None)
            rows, case_ok = [], pages == case["n_pages"]
            for name, want in case["metrics"].items():
                have = got.get(name)
                if isinstance(want, (int, float)) and \
                        isinstance(have, (int, float)):
                    delta = abs(float(have) - float(want))
                    ok = (delta <= GOLDEN_ABS_DB
                          or delta <= GOLDEN_REL * abs(float(want)))
                    shown = f"{delta:.2e}"
                else:
                    ok, shown = str(want) == str(have), "—"
                case_ok = case_ok and ok
                rows.append({"metric": name, "desktop": want,
                             "device": have, "delta": shown,
                             "verdict": "ok" if ok else "FAIL"})
            all_passed = all_passed and case_ok
            cases.append({"key": case["key"], "passed": case_ok,
                          "pages_desktop": case["n_pages"],
                          "pages_device": pages, "rows": rows})
        return json.dumps({"ok": True, "passed": all_passed,
                           "platform": _platform(), "cases": cases,
                           "tolerance_abs_db": GOLDEN_ABS_DB,
                           "tolerance_rel": GOLDEN_REL})
    except Exception:
        return _fail()
