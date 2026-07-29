"""The standalone cal-state inspector and its standalone-ness.

The inspector's whole value is that a consumer WITHOUT this library can
run it against a cal_state.json; these tests enforce both the behaviour
(findings derived from embedded spec, tampering detected) and the
constraint (stdlib-only imports, checked by AST).
"""
from __future__ import annotations

import ast
import json
import subprocess
import sys
from pathlib import Path

from wifitrx.handoff.inspect import inspect_cal_state

INSPECT_PY = (Path(__file__).resolve().parent.parent / "src" / "wifitrx"
              / "handoff" / "inspect.py")

STDLIB_OK = {"json", "sys", "__future__"}


def _doc(**overrides):
    """A minimal healthy cal-state document."""
    doc = {
        "format": "wifitrx-cal-state-v1",
        "tx": {"dc_pre": [0.0, 0.0]},
        "rx": {"dc_post": {}},
        "provenance": {"git_commit": "abc", "git_dirty": False},
        "results": [
            {"name": "tx_iq", "passed": True, "saturated": None,
             "spec": {"metric": "irr_min_db", "limit": 50.0, "sense": "min"},
             "metrics_before": {"irr_min_db": 28.0},
             "metrics_after": {"irr_min_db": 55.0}},
            {"name": "tx_lo_leak_loopback", "passed": True, "saturated": False,
             "spec": {"metric": "lo_leak_dbc", "limit": -40.0, "sense": "max"},
             "metrics_before": {"lo_leak_dbc": -25.0},
             "metrics_after": {"lo_leak_dbc": -55.0}},
        ],
    }
    doc.update(overrides)
    return doc


def test_inspector_imports_stdlib_only():
    """Premise of the whole design: inspect.py must run without wifitrx."""
    mods = set()
    for node in ast.walk(ast.parse(INSPECT_PY.read_text())):
        if isinstance(node, ast.Import):
            mods |= {a.name.split(".")[0] for a in node.names}
        elif isinstance(node, ast.ImportFrom):
            assert node.level == 0, "no relative imports in inspect.py"
            mods.add((node.module or "").split(".")[0])
    assert mods <= STDLIB_OK, f"non-stdlib imports crept in: {mods - STDLIB_OK}"


def test_healthy_document_is_clean():
    assert inspect_cal_state(_doc()) == []


def test_tampered_metric_violates_embedded_spec():
    doc = _doc()
    doc["results"][0]["metrics_after"]["irr_min_db"] = 43.0  # below 50 spec
    f = inspect_cal_state(doc)
    assert any(x["severity"] == "error" and x["step"] == "tx_iq"
               and "violates" in x["message"] for x in f), f


def test_spec_checked_from_file_not_library():
    # a consumer's file calibrated to an older, looser spec must be judged
    # by THAT spec: 46 dB passes a 45 dB embedded limit even though the
    # library's current tx_iq threshold is 50 dB
    doc = _doc()
    doc["results"][0]["spec"]["limit"] = 45.0
    doc["results"][0]["metrics_after"]["irr_min_db"] = 46.0
    assert inspect_cal_state(doc) == []


def test_failed_step_and_railed_trim_are_reported():
    doc = _doc()
    doc["results"][0]["passed"] = False
    doc["results"][0]["metrics_after"]["irr_min_db"] = 43.0
    doc["results"][1]["saturated"] = True
    f = inspect_cal_state(doc)
    sev = {(x["step"], x["severity"]) for x in f}
    assert ("tx_iq", "error") in sev
    assert ("tx_lo_leak_loopback", "warning") in sev


def test_dirty_provenance_is_flagged():
    doc = _doc()
    doc["provenance"]["git_dirty"] = True
    f = inspect_cal_state(doc)
    assert any("dirty" in x["message"] for x in f)


def test_wrong_format_tag_is_an_error():
    f = inspect_cal_state(_doc(format="something-else"))
    assert any(x["severity"] == "error" for x in f)


def test_runs_standalone_as_a_script(tmp_path):
    """Copy inspect.py + JSON to a bare directory and run with -I
    (isolated: no site-packages, no cwd on sys.path) — the consumer's
    environment."""
    (tmp_path / "inspect.py").write_text(INSPECT_PY.read_text())
    good = tmp_path / "good.json"
    good.write_text(json.dumps(_doc()))
    bad_doc = _doc()
    bad_doc["results"][0]["metrics_after"]["irr_min_db"] = 10.0
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps(bad_doc))

    r = subprocess.run([sys.executable, "-I", "inspect.py", "good.json"],
                       cwd=tmp_path, capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
    r = subprocess.run([sys.executable, "-I", "inspect.py", "bad.json"],
                       cwd=tmp_path, capture_output=True, text=True)
    assert r.returncode == 1 and "violates" in r.stdout, r.stdout + r.stderr
