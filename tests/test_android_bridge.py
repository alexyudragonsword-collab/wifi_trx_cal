"""Contract tests for the Android bridge (android/app/src/main/python).

The bridge is plain Python — everything except the Kotlin/WebView shell is
verifiable on the desktop, so its JSON contract is pinned here: the same
guarantee test_gui_specs gives the Qt shell, for the Android one.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent
                       / "android" / "app" / "src" / "main" / "python"))

import bridge  # noqa: E402


def test_list_specs_mirrors_registry():
    out = json.loads(bridge.list_specs())
    assert out["ok"], out.get("error")
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "app"))
    from specs import ALL_ANALYSES
    assert [s["key"] for s in out["specs"]] == [s.key for s in ALL_ANALYSES]
    for s in out["specs"]:
        for p in s["params"]:
            assert p["kind"] in ("float", "int", "bool", "choice")
            json.dumps(p["default"])   # defaults must be JSON-clean


def test_run_returns_svg_pages_and_metrics():
    # spur planner: fastest registry entry with a real figure
    out = json.loads(bridge.run("spur_planner",
                                json.dumps({"bw_mhz": 320, "band": "6g"})))
    assert out["ok"], out.get("error")
    assert out["metrics"]
    assert out["pages"] and out["pages"][0]["svg"].lstrip().startswith("<?xml")
    assert out["has_cal_state"] is False


def test_run_bad_key_reports_instead_of_raising():
    out = json.loads(bridge.run("nope", "{}"))
    assert out["ok"] is False and "error" in out


def test_inspect_roundtrip(tmp_path):
    # a structurally-valid empty doc: inspector must answer, not crash
    doc = {"format": "wifitrx-cal-state-v1"}
    out = json.loads(bridge.inspect_cal_state(json.dumps(doc)))
    assert out["ok"], out.get("error")
    assert isinstance(out["findings"], list) and out["text"]


def test_reference_data_has_diagrams_and_tables():
    out = json.loads(bridge.reference_data())
    assert out["ok"], out.get("error")
    kinds = {"svg" if "svg" in e else "table" for e in out["entries"]}
    assert kinds == {"svg", "table"}
    for e in out["entries"]:
        if "svg" in e:
            assert e["svg"].lstrip().startswith(("<?xml", "<svg"))
        else:
            assert e["columns"] and json.dumps(e["rows"])


# Names verified to exist in the versions the Chaquopy Android wheel
# repository ships: numpy 1.19.5 and scipy 1.4.1.  A call outside these
# sets fails the guard below on the desktop instead of as an
# AttributeError on a phone — which is how correlation_lags (scipy 1.5)
# and np.trapezoid (numpy 2.0) each reached a user once.
SCIPY_1_4_1 = {
    "signal.butter", "signal.cheby1", "signal.correlate",
    "signal.freqz", "signal.lfilter", "signal.oaconvolve",
    "signal.sosfilt", "signal.sosfreqz", "signal.welch",
    "interpolate.CubicSpline",
}
NUMPY_1_19_5 = {
    "abs", "all", "allclose", "angle", "append", "arange", "argmax",
    "argmin", "argsort", "array", "asarray", "atleast_1d", "average",
    "bool_", "ceil", "clip", "complex128", "concatenate", "conj",
    "convolve", "cos", "count_nonzero", "cumsum", "deg2rad", "degrees",
    "diff", "digitize", "divmod", "dot", "empty", "empty_like", "exp",
    "eye", "fft", "fill_diagonal", "floating", "floor", "full",
    "gradient", "hanning", "imag", "inf", "insert", "int64", "integer",
    "interp", "iscomplexobj", "isfinite", "linalg", "linspace", "load",
    "log", "log10", "log2", "logspace", "max", "maximum", "mean",
    "median", "min", "minimum", "nan", "ndarray", "nonzero", "ones",
    "ones_like", "outer", "pad", "pi", "polyfit", "random", "ravel",
    "real", "roll", "round", "savez", "savez_compressed", "searchsorted",
    "sin", "sinc", "sort", "sqrt", "stack", "sum", "tile", "trace",
    "trapz", "unique", "unwrap", "var", "vdot", "vstack", "where",
    "zeros", "zeros_like",
}


def _shipped_sources() -> list[Path]:
    """Every Python file that travels into the APK."""
    root = Path(__file__).resolve().parent.parent
    files = list((root / "src" / "wifitrx").rglob("*.py"))
    files += [root / "app" / "specs.py", root / "app" / "reference.py",
              root / "app" / "inspector_data.py",
              root / "android" / "app" / "src" / "main" / "python"
              / "bridge.py"]
    return [f for f in files if f.exists()]


def test_scipy_surface_stays_within_the_android_wheel():
    """Every scipy symbol the shipped tree calls exists in scipy 1.4.1.

    To extend: confirm the symbol in the 1.4.1 reference docs, then add
    it to SCIPY_1_4_1 — the point is that adding it is a decision.
    """
    import re
    used = set()
    for f in _shipped_sources():
        for line in f.read_text(encoding="utf-8").splitlines():
            code = line.split("#", 1)[0]
            for m in re.finditer(r"\bsig\.([A-Za-z_]\w*)", code):
                used.add(f"signal.{m.group(1)}")
            for m in re.finditer(
                    r"from scipy\.(\w+) import ([\w, ]+)", code):
                for name in m.group(2).split(","):
                    used.add(f"{m.group(1)}.{name.strip()}")
    assert used, "scanner found nothing — pattern rot, fix the test"
    assert used <= SCIPY_1_4_1, (
        "scipy calls not verified against the Android wheel (1.4.1): "
        f"{sorted(used - SCIPY_1_4_1)}")


def test_numpy_surface_stays_within_the_android_wheel():
    """Same guard for numpy 1.19.5.

    The desktop runs numpy 2.x, so a 2.0-only spelling looks perfectly
    fine here and dies on the phone: np.trapezoid (renamed from trapz in
    2.0) broke the Reference tab exactly that way.  Where the two numpy
    generations disagree, bind the name once
    (``getattr(np, "new", None) or np.old``) rather than test versions at
    each call site.
    """
    import re
    used = set()
    for f in _shipped_sources():
        for line in f.read_text(encoding="utf-8").splitlines():
            code = line.split("#", 1)[0]
            used.update(re.findall(r"\bnp\.([A-Za-z_]\w*)", code))
    assert used, "scanner found nothing — pattern rot, fix the test"
    assert used <= NUMPY_1_19_5, (
        "numpy calls not verified against the Android wheel (1.19.5): "
        f"{sorted(used - NUMPY_1_19_5)}")


def test_inspector_sections_match_the_desktop_page(tmp_path):
    """Both inspectors render inspector_data.inspector_sections, so the
    Android one cannot silently show less than the Qt page again."""
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "app"))
    from inspector_data import inspector_sections

    doc = {"format": "wifitrx-cal-state-v1",
           "provenance": {"tool": "test"},
           "results": [{"name": "s", "passed": True,
                        "metrics_after": {"m": 1.0}}],
           "residuals": {"values": {"k": 1.0},
                         "specification": {"k": {"unit": "dB"}}}}
    out = json.loads(bridge.inspect_cal_state(json.dumps(doc)))
    assert out["ok"], out.get("error")
    assert out["sections"] == inspector_sections(doc)
    assert {s["title"] for s in out["sections"]} == {
        s["title"] for s in inspector_sections(doc)}
    assert len(out["sections"]) == 3      # steps, residuals, provenance


def test_reference_assets_are_staged_for_the_apk():
    """The Reference tab reads assets/schematics/*.svg off the filesystem;
    Chaquopy only ships what a source dir carries.  A build that drops the
    staging task would put a FileNotFoundError on the phone, so the wiring
    is asserted here rather than discovered on a device."""
    gradle = (Path(__file__).resolve().parent.parent / "android" / "app"
              / "build.gradle").read_text(encoding="utf-8")
    assert "stageAssets" in gradle and "build/python-assets" in gradle
    assert '"../../assets"' in gradle
