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


def test_scipy_surface_stays_within_the_android_wheel():
    """Every scipy symbol the tree calls, verified against scipy 1.4.1 —
    the newest version the Chaquopy Android wheel repository carries.

    A new scipy call that is not on this list fails HERE, on the desktop,
    instead of as an AttributeError on a phone — which is exactly how
    ``correlation_lags`` (scipy >= 1.5) slipped through and crashed the
    first on-device run.  To extend the list: check the symbol exists in
    scipy 1.4.1 (docs.scipy.org/doc/scipy-1.4.1/reference/), then add it.
    """
    import re
    root = Path(__file__).resolve().parent.parent
    verified = {
        "signal.butter", "signal.cheby1", "signal.correlate",
        "signal.freqz", "signal.lfilter", "signal.oaconvolve",
        "signal.sosfilt", "signal.sosfreqz", "signal.welch",
        "interpolate.CubicSpline",
    }
    used = set()
    files = list((root / "src" / "wifitrx").rglob("*.py"))
    files += [root / "app" / "specs.py",
              root / "android" / "app" / "src" / "main" / "python"
              / "bridge.py"]
    for f in files:
        for line in f.read_text(encoding="utf-8").splitlines():
            code = line.split("#", 1)[0]
            for m in re.finditer(r"\bsig\.([A-Za-z_]\w*)", code):
                used.add(f"signal.{m.group(1)}")
            for m in re.finditer(
                    r"from scipy\.(\w+) import ([\w, ]+)", code):
                for name in m.group(2).split(","):
                    used.add(f"{m.group(1)}.{name.strip()}")
    assert used, "scanner found nothing — pattern rot, fix the test"
    assert used <= verified, (
        "scipy calls not verified against the Android wheel (1.4.1): "
        f"{sorted(used - verified)}")


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
