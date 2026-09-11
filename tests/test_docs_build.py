"""The tutorial/devguide builder: fast content invariants + slow build.

Fast tier runs on every push with no calibration runs: it validates the
content trees (bilingual completeness, unique anchors, parsable math,
declared {key} fields) in milliseconds.  The full build is the slow tier.
"""
from __future__ import annotations

import re
import string
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools" / "tutorial"))

from model import Diagram, Doc, F, Fig, walk_texts  # noqa: E402


def _docs() -> list[Doc]:
    from content.devguide import DOC as dev
    from content.tutorial import DOC as tut
    return [tut, dev]


_ANCHOR = re.compile(r"^[a-z0-9][a-z0-9-]*$")
_MATH = re.compile(r"\$([^$]+)\$")


def _sections(doc):
    for ch in doc.chapters:
        for sec in ch.sections:
            yield sec


def test_content_model_valid():
    for doc in _docs():
        ids = [ch.id for ch in doc.chapters]
        ids += [s.id for s in _sections(doc)]
        for ch in doc.chapters:
            for sec in ch.sections:
                for item in sec.body:
                    if isinstance(item, (Fig, Diagram)):
                        ids.append(item.id)
        assert len(ids) == len(set(ids)), f"{doc.id}: duplicate ids"
        assert all(_ANCHOR.match(i) for i in ids), \
            [i for i in ids if not _ANCHOR.match(i)]
        # premise: the trees are non-trivial
        assert len(ids) >= (30 if doc.id == "tutorial" else 8), doc.id
        for sec, t in walk_texts(doc):
            assert t.zh.strip() and t.en.strip(), \
                f"{doc.id}/{sec.id if sec else '?'}: missing a language"
            for s in (t.zh, t.en):
                assert s.count("$") % 2 == 0, f"unbalanced $: {s[:60]}"


def test_value_keys_declared():
    fmt = string.Formatter()
    for doc in _docs():
        for sec, t in walk_texts(doc):
            if sec is None:
                continue
            for s in (t.zh, t.en):
                # strip math first, exactly as the renderer does
                plain = _MATH.sub("", s)
                fields = {f for _, f, _, _ in fmt.parse(plain) if f}
                assert fields <= set(sec.value_keys), (
                    f"{doc.id}/{sec.id}: fields {fields - set(sec.value_keys)}"
                    " not declared in value_keys")
            if sec.value_keys:
                assert sec.values is not None, f"{doc.id}/{sec.id}"


def test_formulas_parse():
    from matplotlib.font_manager import FontProperties
    from matplotlib.mathtext import MathTextParser
    parser = MathTextParser("path")
    seen = set()
    for doc in _docs():
        frags = []
        for ch in doc.chapters:
            for sec in ch.sections:
                for item in sec.body:
                    if isinstance(item, F):
                        frags.append((sec.id, item.latex))
        for sec, t in walk_texts(doc):
            for s in (t.zh, t.en):
                for m in _MATH.finditer(s):
                    frags.append((sec.id if sec else "?", m.group(1)))
        for where, latex in frags:
            if latex in seen:
                continue
            seen.add(latex)
            try:
                parser.parse(f"${latex}$", dpi=72,
                             prop=FontProperties(size=12))
            except Exception as exc:
                raise AssertionError(
                    f"{doc.id}/{where}: mathtext rejects {latex!r}: {exc}")
    assert len(seen) >= 15  # premise: formulas actually exist


def test_static_diagram_svg_wellformed():
    for doc in _docs():
        for ch in doc.chapters:
            for sec in ch.sections:
                for item in sec.body:
                    if isinstance(item, Diagram) and item.svg is not None:
                        ET.fromstring(item.svg)
                    if isinstance(item, Diagram):
                        assert (item.svg is None) != (item.build is None)


def test_layering_table_source_importable():
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "lay", ROOT / "tests" / "test_import_layering.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert len(mod.ALLOWED) >= 10


def test_schematics_render():
    """The schemdraw diagrams stay renderable (no cal runs needed)."""
    import schematics
    for name in ("architecture", "envdet_path", "loopback_offset",
                 "ila_loop"):
        svg = getattr(schematics, name)(None)
        assert svg.startswith("<svg") and len(svg) > 2000, name
        ET.fromstring(svg)


# ------------------------------------------------------------- slow tier
@pytest.mark.slow
def test_full_build(tmp_path):
    sys.path.insert(0, str(ROOT / "tools"))
    import build_docs
    build_docs.main(["--out", str(tmp_path)])

    for doc in _docs():
        out = (tmp_path / f"{doc.id}.html").read_text(encoding="utf-8")
        assert len(out) < 8e6, f"{doc.id}: too large"
        # every figure/diagram id landed
        for ch in doc.chapters:
            for sec in ch.sections:
                assert f'id="{sec.id}"' in out, sec.id
                for item in sec.body:
                    if isinstance(item, (Fig, Diagram)):
                        assert f'id="{item.id}"' in out, item.id
        # (no leftover-{field} scan here: escaped {{key}} legitimately
        # renders as a literal, and a genuinely missed field already
        # raises at build time via the strict format_map)
        # offline: no external fetches
        assert not re.search(r'(src|href)="https?://', out), doc.id
        # provenance footer present
        assert "generated from commit" in out
    tut = (tmp_path / "tutorial.html").read_text(encoding="utf-8")
    assert tut.count("data:image/png") >= 15


# ------------------------------------- the staleness checker's own logic
# The nightly compares the committed HTML against a rebuild.  Its
# normaliser used to strip only the timestamp out of the provenance
# footer, leaving the commit id — which the committed file can never
# match, because a file cannot carry the id of the commit containing it.
# That guard was red on every nightly run for three weeks and hid the
# schematic check behind it (CHANGELOG 0.7.26).  These pin the two
# properties it needs: provenance alone is not staleness, real content
# is, and a footer that stops matching is an error rather than a pass.
def _staleness():
    sys.path.insert(0, str(ROOT / "tools"))
    import docs_staleness
    return docs_staleness


_FOOT = ('<footer>generated from commit <code>{sha}</code>{dirty} · '
         '{when} · numpy 2.4.6 · rebuild: <code>x</code></footer></main>')


def _page(body, sha, dirty="", when="2026-09-11T00:00:00+00:00"):
    return f"<main><p>{body}</p>" + _FOOT.format(sha=sha, dirty=dirty, when=when)


def test_provenance_difference_alone_is_not_staleness():
    ds = _staleness()
    committed = _page("same words", "0beb9d4", dirty=" (dirty)")
    rebuilt = _page("same words", "a698f3b", when="2026-09-12T01:02:03+00:00")
    assert committed != rebuilt                       # premise: raw text differs
    assert ds.strip_provenance(committed) == ds.strip_provenance(rebuilt)


def test_a_content_difference_is_staleness():
    ds = _staleness()
    a = _page("nine analyses", "0beb9d4")
    b = _page("ten analyses", "0beb9d4")
    assert ds.strip_provenance(a) != ds.strip_provenance(b)


def test_a_footer_that_stopped_matching_is_an_error_not_a_pass():
    ds = _staleness()
    with pytest.raises(ValueError):
        ds.strip_provenance("<main><p>body</p><footer>built somewhere</footer>")
    with pytest.raises(ValueError):      # two footers is equally wrong
        ds.strip_provenance(_page("body", "a") + _FOOT.format(
            sha="b", dirty="", when="2026-09-11T00:00:00+00:00"))
