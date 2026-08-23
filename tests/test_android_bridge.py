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
