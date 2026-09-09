"""The version travels in three places — pyproject.toml, the package and
the Android app — and nothing pinned them together: 0.7.6 shipped two
releases in a row under the wrong label before anyone read a wheel
filename out of a CI log (CHANGELOG 0.7.7).  The Android versionCode is
derived from the same string so a phone sees each release as an
upgrade; it had been 1 for fifteen releases.  CHANGELOG's newest entry
must carry the same number, or a release goes out undocumented.
"""
import re
import tomllib
from pathlib import Path

import wifitrx

ROOT = Path(__file__).resolve().parent.parent


def _pyproject_version() -> str:
    return tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]["version"]


def _gradle() -> str:
    return (ROOT / "android" / "app" / "build.gradle").read_text(encoding="utf-8")


def test_package_pyproject_and_apk_agree_on_the_version():
    v = _pyproject_version()
    assert wifitrx.__version__ == v
    m = re.search(r'^def appVersion = "([^"]+)"$', _gradle(), re.M)
    assert m, "build.gradle must declare `def appVersion = \"x.y.z\"`"
    assert m.group(1) == v


def test_apk_version_code_is_derived_from_the_version():
    g = _gradle()
    # the working lines, not the comment: versionName reads the one
    # string, versionCode is computed from it
    assert re.search(r"^\s+versionName appVersion$", g, re.M)
    assert re.search(r"^\s+versionCode semverCode\(appVersion\)$", g, re.M)
    major, minor, patch = (int(x) for x in _pyproject_version().split("."))
    expected = major * 1000000 + minor * 10000 + patch
    assert expected > 1
    # the Groovy formula, read from the file so a rewrite cannot drift
    formula = re.search(r"return p\[0\] \* (\d+) \+ p\[1\] \* (\d+) \+ p\[2\]", g)
    assert formula, "semverCode must keep the MAJOR*1e6 + MINOR*1e4 + PATCH form"
    assert (major * int(formula.group(1)) + minor * int(formula.group(2)) + patch
            == expected)


def test_changelog_leads_with_the_current_version():
    head = re.search(r"^## (\d+\.\d+\.\d+) — \d{4}-\d\d-\d\d$",
                     (ROOT / "CHANGELOG.md").read_text(encoding="utf-8"), re.M)
    assert head, "CHANGELOG.md has no `## x.y.z — date` entry"
    assert head.group(1) == _pyproject_version()
