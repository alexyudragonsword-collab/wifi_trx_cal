"""Contract tests for the Android bridge (android/app/src/main/python).

The bridge is plain Python — everything except the Kotlin/WebView shell is
verifiable on the desktop, so its JSON contract is pinned here: the same
guarantee test_gui_specs gives the Qt shell, for the Android one.
"""
import json
import math
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


def test_self_check_is_the_one_golden_comparison():
    """The in-app self-check and the emulator GoldenTest call this same
    function, so a phone and CI can never adjudicate by different rules.
    On the desktop it compares the golden values against the machine that
    produced them — every delta must be exactly zero, which is what makes
    this a test of the comparison logic rather than of the physics."""
    out = json.loads(bridge.self_check())
    assert out["ok"], out.get("error")
    assert out["passed"], out["cases"]
    assert out["tolerance_abs_db"] == 0.05 and out["tolerance_rel"] == 1e-3
    assert {c["key"] for c in out["cases"]} == {
        "full_cal", "rx_evm_sweep", "spur_planner"}
    for case in out["cases"]:
        assert case["rows"], case["key"]
        for row in case["rows"]:
            assert row["verdict"] == "ok", (case["key"], row)
            if row["delta"] != "—":
                assert float(row["delta"]) == 0.0, (case["key"], row)
    # the platform block is the point of the feature: it must name what ran
    assert out["platform"]["numpy"] and out["platform"]["android_abi"]


def test_golden_values_ship_inside_the_apk():
    """Self-check on a phone needs the golden file in the Chaquopy source
    dir, not only in the test APK's assets."""
    p = (Path(__file__).resolve().parent.parent / "android" / "app" / "src"
         / "main" / "python" / "golden.json")
    assert p.exists(), "golden.json must sit beside bridge.py to ship"
    assert json.loads(p.read_text(encoding="utf-8"))


def test_reference_source_follows_run_and_inspect():
    """Both paths that produce step records feed the Reference tables, as
    on the desktop (main.py wires a finished run AND inspector.loaded to
    the same set_run_results slot).  Only the run path existed here, so a
    recipient opening a delivered file saw empty acceptance and
    capture-cost tables — the exact case the Android app is for."""
    doc = {"format": "wifitrx-cal-state-v1", "fs_hz": 160e6,
           "results": [{"name": "lpf_corner",
                        "cost": {"captures": 3, "samples": 3072}}]}
    before = json.loads(bridge.reference_version())["version"]
    out = json.loads(bridge.inspect_cal_state(json.dumps(doc)))
    assert out["ok"], out.get("error")

    ref = json.loads(bridge.reference_data())
    assert ref["ok"], ref.get("error")
    budget = next(e for e in ref["entries"] if e["key"] == "budget")
    names = [r[0] for r in budget["rows"]]
    assert "lpf_corner" in names and "total" in names, budget["rows"]
    # the version must move, or the UI's cached page would never reload
    assert ref["version"] > before

    # a document the inspector cannot read must not rewrite those tables:
    # the desktop emits `loaded` only after rendering succeeded
    stable = json.loads(bridge.reference_version())["version"]
    bad = json.loads(bridge.inspect_cal_state('{"results": [{"spec": "x"}]}'))
    assert bad["ok"] is False
    assert json.loads(bridge.reference_version())["version"] == stable


def test_every_native_call_the_ui_makes_exists_in_the_bridge():
    """The WebView reaches Python through hand-written Kotlin shims, so a
    renamed bridge function fails as a runtime error on the device and
    nowhere else.  Pin the three-layer chain here instead."""
    import re
    root = Path(__file__).resolve().parent.parent / "android" / "app" / "src"
    js = (root / "main" / "assets" / "ui" / "app.js").read_text(
        encoding="utf-8")
    kt = (root / "main" / "java" / "com" / "wifitrx" / "workbench"
          / "MainActivity.kt").read_text(encoding="utf-8")

    used = set(re.findall(r"native\.([A-Za-z_]\w*)\(", js))
    declared = set(re.findall(r"fun ([A-Za-z_]\w*)\(", kt))
    assert used <= declared, f"UI calls undeclared Native.*: {used - declared}"

    # and every callAttr target must be a real bridge function
    for name in re.findall(r'callAttr\(\s*"([a-z_]+)"', kt):
        assert hasattr(bridge, name), f"MainActivity calls bridge.{name}()"

    # third leg: the callbacks the shell pushes back into the page.  A
    # result that lands on a handler the UI never defined is swallowed by
    # the WebView with no error anywhere — same class of silent break as
    # the two directions above.
    for name in set(re.findall(r'emit\(\s*"ui\.(\w+)"', kt)) | set(
            re.findall(r'"ui\.(\w+)"', kt)):
        assert f"{name}(" in js, f"MainActivity emits ui.{name}(), UI has no such handler"


def test_figure_export_offers_a_format_the_phone_can_open():
    """Android has no SVG decoder anywhere in the platform, so an SVG-only
    export ships a file the receiving phone cannot open (0.7.1 did exactly
    that).  PNG must stay the primary export on both figure surfaces."""
    root = Path(__file__).resolve().parent.parent / "android" / "app" / "src"
    ui = root / "main" / "assets" / "ui"
    js = (ui / "app.js").read_text(encoding="utf-8")
    html = (ui / "index.html").read_text(encoding="utf-8")

    assert 'id="a-export"' in html and 'id="a-export-svg"' in html, \
        "the result figure must offer both PNG and SVG export"
    assert ">Export PNG<" in html, "PNG must be the button reached first"
    for el in ("a-export", "a-export-svg"):
        assert f'$("{el}").onclick' in js, f"{el} is not wired up"
    assert "native.saveBinary(" in js, "PNG never reaches the shell"
    # both figure surfaces (result pages and Reference diagrams) go
    # through the one export helper, so neither can regress alone
    assert js.count("exportFigure(") >= 3

    # the saved figure must be the SVG the bridge produced, never the DOM
    # copy: showPage() sizes that one in px and strips its height
    # attribute, which leaves the exported file with no intrinsic size
    assert "outerHTML" not in js, \
        "export must use the pristine page.svg, not the mutated DOM node"


def test_shipped_diagrams_can_be_rasterized_on_device():
    """The PNG export draws each SVG into a WebView canvas.  That works
    only while the diagrams are self-contained: an external reference
    would fail to load offline (no INTERNET permission) and a cross-origin
    one taints the canvas, so toDataURL throws instead of exporting."""
    import re
    from reference import ALL_REFERENCE
    checked = 0
    for entry in ALL_REFERENCE:
        if entry.svg is None:
            continue
        svg = entry.svg()
        checked += 1
        for attr in re.findall(r'(?:xlink:)?href\s*=\s*"([^"]*)"', svg):
            assert attr.startswith("#"), \
                f"{entry.key}: external reference {attr!r} breaks rasterizing"
        assert "<image" not in svg, f"{entry.key}: embedded raster image"
        assert "url(http" not in svg, f"{entry.key}: external url() reference"
    assert checked, "no diagrams were checked"


def _spur_page():
    """One real result page, cheap enough for a unit test (~0.3 s)."""
    out = json.loads(bridge.run("spur_planner",
                                json.dumps({"bw_mhz": 320, "band": "6g"})))
    assert out["ok"], out.get("error")
    return out["pages"][0]


def test_pages_carry_axes_metadata_for_the_coordinate_readout():
    """The figure travels as an SVG, which says nothing about the data
    limits.  Without this metadata the Android toolbar cannot report data
    coordinates at all — the readout would silently show nothing."""
    page = _spur_page()
    assert page["axes"], "no axes metadata reached the UI"
    for a in page["axes"]:
        assert set(a) >= {"x0", "y0", "x1", "y1", "xlim", "ylim",
                          "xscale", "yscale", "xlabel", "ylabel"}
        assert 0.0 <= a["x0"] < a["x1"] <= 1.0, a
        assert 0.0 <= a["y0"] < a["y1"] <= 1.0, a
        for lim in (a["xlim"], a["ylim"]):
            assert len(lim) == 2 and all(math.isfinite(v) for v in lim)
            assert lim[0] != lim[1]
        # JSON-safe: numpy scalars would survive json.dumps as strings
        assert all(isinstance(v, float) for v in a["xlim"] + a["ylim"])


def test_axes_rectangle_matches_where_the_frame_actually_lands():
    """Independent check of the readout's frame of reference: render the
    same figure and find the axes spines in the pixels.  A wrong or
    stale rectangle (read before layout, or measured in the wrong
    direction) puts every reported coordinate off by that much."""
    import io

    import numpy as np
    from matplotlib.backends.backend_agg import FigureCanvasAgg
    from PIL import Image

    from specs import ALL_ANALYSES
    spec = next(s for s in ALL_ANALYSES if s.key == "spur_planner")
    fig = spec.run({"bw_mhz": 320, "band": "6g"}).figure
    reported = bridge._axes_meta(fig)[0]        # _svg draws; so does print_png

    buf = io.BytesIO()
    FigureCanvasAgg(fig).print_png(buf)
    im = np.asarray(Image.open(io.BytesIO(buf.getvalue())).convert("L"))
    h, w = im.shape
    dark = im < 128
    cols = np.where(dark.sum(axis=0) > 0.35 * h)[0]   # the vertical spines
    rows = np.where(dark.sum(axis=1) > 0.35 * w)[0]   # the horizontal ones
    assert cols.size and rows.size, "no axes frame found in the render"
    measured = {"x0": cols.min() / w, "x1": cols.max() / w,
                # figure fractions count y from the bottom, pixels from the top
                "y0": 1 - rows.max() / h, "y1": 1 - rows.min() / h}
    for key, value in measured.items():
        assert abs(value - reported[key]) < 0.01, \
            f"{key}: reported {reported[key]:.4f}, frame at {value:.4f}"


def test_the_figure_toolbar_offers_what_the_desktop_toolbar_does():
    """Qt gets Home/Back/Forward/Pan/Zoom and the coordinate readout from
    matplotlib's own NavigationToolbar2QT; on Android the WebView has to
    supply them, so they can regress independently."""
    root = Path(__file__).resolve().parent.parent / "android" / "app" / "src"
    ui = root / "main" / "assets" / "ui"
    js = (ui / "app.js").read_text(encoding="utf-8")
    html = (ui / "index.html").read_text(encoding="utf-8")

    for el in ("a-reset", "a-back", "a-fwd", "a-pan", "a-zoom", "fig-coord"):
        assert f'id="{el}"' in html, f"{el} missing from the toolbar"
    for el in ("a-reset", "a-back", "a-fwd", "a-pan", "a-zoom"):
        assert f'$("{el}").onclick' in js, f"{el} is not wired up"
    # the readout needs the metadata above; keep the consumer honest
    assert "dataAtPoint" in js and "page.axes" in js


def _strict(payload, what):
    """Parse the way the WebView does: JSON.parse has no NaN or Infinity,
    and Python's json writes those tokens happily.  One masked sample was
    enough to make the browser discard a whole page of data."""
    def reject(token):
        raise AssertionError(f"{what} contains the non-JSON token {token!r}")
    return json.loads(payload, parse_constant=reject)


def test_every_bridge_payload_is_strict_json():
    """Whatever a payload carries, it has to survive JSON.parse — the one
    consumer on the far side of the bridge."""
    _strict(bridge.list_specs(), "list_specs")
    _strict(bridge.reference_data(), "reference_data")
    run = _strict(bridge.run("rx_evm_sweep", json.dumps(
        {"bw_mhz": 20, "qam": 256, "std": "11ax/be", "rx_hp": False,
         "agc_rebw": False, "baseband": False, "bb_noise_nv": 5,
         "seed": 5})), "run")
    assert run["ok"], run.get("error")
    for i in range(len(run["pages"])):
        _strict(bridge.page_series(i), f"page_series({i})")
    _strict(bridge.inspect_cal_state('{"format":"wifitrx-cal-state-v1"}'),
            "inspect_cal_state")


def test_masked_samples_reach_the_cursor_as_null():
    """The isolation-floor masking leaves NaN in the swept curves — real
    data meaning "not attributable".  It has to travel as null: a cursor
    must not snap to it, and the token must not break the parse."""
    out = json.loads(bridge.run("rx_evm_sweep", json.dumps(
        {"bw_mhz": 20, "qam": 256, "std": "11ax/be", "rx_hp": False,
         "agc_rebw": False, "baseband": False, "bb_noise_nv": 5,
         "seed": 5})))
    assert out["ok"], out.get("error")
    page = _strict(bridge.page_series(0), "page_series")
    masked = [v for s in page["series"] for v in s.get("y", ()) if v is None]
    assert masked, "no masked sample survived to the payload"
    for s in page["series"]:
        for v in s.get("x", ()) + s.get("y", ()):
            assert v is None or isinstance(v, float)


def test_page_series_ships_data_and_not_guide_lines():
    """Guide lines carry a blended transform, not transData: an AGC
    hand-over mark or an MCS threshold is not a measurement, and a cursor
    that snapped to one would report it as if it were."""
    params = {"bw_mhz": 80, "qam": 256, "seed": 5, "with_dpd": False,
              "std": "11ax/be", "rx_hp": False, "baseband": False,
              "agc_rebw": False, "bb_noise_nv": 5}
    out = json.loads(bridge.run("full_cal", json.dumps(params)))
    assert out["ok"], out.get("error")
    page = _strict(bridge.page_series(0), "page_series")
    by_axes = {}
    for s in page["series"]:
        by_axes.setdefault(s["axes"], []).append(s)

    # the RX-EVM axes plots two swept curves and one operating point, and
    # carries eight guides on top of them
    mixed = [s for a in by_axes.values() for s in a
             if any(x["name"] == "uncalibrated" for x in a)]
    assert len(mixed) == 3, [s["name"] for s in mixed]

    # constellation scatters are declared, not silently dropped
    clouds = [s for s in page["series"] if not s.get("snap")]
    assert clouds, "the scatter clouds should still be listed"
    for s in clouds:
        assert s["why"] and s["points"] > 0 and "x" not in s

    # and the bars a cursor can sit on are grouped by their container
    bars = [s["name"] for s in page["series"] if s["kind"] == "bar"]
    assert bars == ["before", "after"], bars


def test_page_series_is_bounded_and_refuses_unknown_pages():
    params = {"bw_mhz": 80, "qam": 256, "seed": 5, "with_dpd": False,
              "std": "11ax/be", "rx_hp": False, "baseband": False,
              "agc_rebw": False, "bb_noise_nv": 5}
    json.loads(bridge.run("full_cal", json.dumps(params)))
    page = _strict(bridge.page_series(0), "page_series")
    assert page["points"] <= bridge.PAGE_POINT_BUDGET
    bad = json.loads(bridge.page_series(99))
    assert bad["ok"] is False and "error" in bad


def test_the_phone_only_traps_stay_fixed():
    """Five things that are invisible on a desktop and only bite on a
    phone.  Each is cheap to keep and expensive to rediscover."""
    root = Path(__file__).resolve().parent.parent / "android" / "app" / "src"
    kt = (root / "main" / "java" / "com" / "wifitrx" / "workbench"
          / "MainActivity.kt").read_text(encoding="utf-8")
    ui = root / "main" / "assets" / "ui"
    html = (ui / "index.html").read_text(encoding="utf-8")
    js = (ui / "app.js").read_text(encoding="utf-8")

    # 1. matplotlib builds a font cache on first import; a read-only config
    # dir turns that into a crash on the first calculation
    for var in ("MPLCONFIGDIR", "XDG_CACHE_HOME"):
        assert f'Os.setenv("{var}"' in kt, f"{var} is not pinned"
    # match the call, not the word: the comment above it says
    # "Python.start()" too, and searching for prose finds that first
    assert kt.index("MPLCONFIGDIR") < kt.index("Python.start(AndroidPlatform"), \
        "the cache directories must be set before Python starts"

    # 2. an author `display` beats the UA's [hidden] { display:none }, so a
    # toggled element stays on screen — invisible content that still exists
    assert "#fig svg { display:block; }" in html
    assert "#fig-cursors[hidden] { display:none; }" in html

    # 3. notches and gesture bars
    assert "viewport-fit=cover" in html
    assert "safe-area-inset-bottom" in html and "safe-area-inset-top" in html

    # 4. the first bridge call pays the whole import; without a loading
    # state an empty form sits there looking hung
    assert "starting Python" in js
    assert js.index("starting Python") < js.index("init();"), \
        "the loading state must be shown before the blocking first call"

    # 5. bbox_inches silently changes a figure's extent, so the axes
    # rectangles the cursor and the readout are computed from would
    # describe a different image than the one on screen
    repo = Path(__file__).resolve().parent.parent
    for folder in ("src", "app", "android"):
        for path in (repo / folder).rglob("*.py"):
            assert "bbox_inches" not in path.read_text(encoding="utf-8"), \
                f"{path} uses bbox_inches; the axes metadata would drift"


def test_the_compiled_flavour_cannot_ship_source():
    """The compiled variant's whole point is that wifitrx travels as .so.

    A Chaquopy source dir takes import precedence over site-packages, so
    leaving the repo's src/ in that flavour's source set would shadow every
    compiled module and produce an interpreted APK that looks compiled —
    and nothing in the build log would say so.
    """
    root = Path(__file__).resolve().parent.parent / "android"
    gradle = (root / "app" / "build.gradle").read_text(encoding="utf-8")
    tools = root / "tools"

    assert 'productFlavors' in gradle and "compiled {" in gradle
    # wifitrx as source belongs to the interpreted flavour alone
    src_line = [ln for ln in gradle.splitlines() if '"../../src"' in ln]
    assert len(src_line) == 1, src_line
    interpreted = gradle.index("interpreted {\n            srcDirs")
    assert gradle.index('"../../src"') > interpreted, \
        "the repo's src/ must sit in the interpreted flavour's source set"
    # and the wheels must resolve by tag, never by path
    assert '--find-links' in gradle and 'install "wifitrx"' in gradle

    # the vendored builder, with the change this tree depends on
    wheel_tool = (tools / "android_wheel.py").read_text(encoding="utf-8")
    # match the argument as it appears in the call, not the words: the
    # vendoring note at the top of that file explains the flag in prose,
    # and searching for the phrase finds the explanation, not the flag
    assert '"-X", "annotation_typing=False"' in wheel_tool, \
        "without it, np.float64 fails the `float` annotations this tree " \
        "writes descriptively (metrics/ccdf.py is the shortest example)"
    assert (tools / "inspect_apk.py").exists()

    workflow = (Path(__file__).resolve().parent.parent / ".github"
                / "workflows" / "android.yml").read_text(encoding="utf-8")
    # 3.3.0 crashes on imaginary literals, and this tree is complex baseband
    assert 'pip install "cython<3.3"' in workflow
    # both artefacts asserted, in the two directions that distinguish them
    assert "--native" in workflow and "--pure" in workflow
