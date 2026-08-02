"""Render the signal-chain schematics to committed SVG assets.

    python tools/build_assets.py [--out assets/schematics] [--check]

The GUI's Reference tab shows the same block diagrams as the tutorial,
but it must not import schemdraw (a build-time `[docs]` extra that is
not installed in the Windows exe jobs), so the diagrams ship as assets.

They keep matplotlib's default glyph-outline text (``svg.fonttype =
"path"``): the labels carry ° ² · ÷ – ₀, and the exe runs on machines
whose default sans font is not the one they were laid out in — outlines
render identically everywhere, live ``<text>`` does not.

One fix-up is needed for Qt: matplotlib emits the space glyph as
``<path id="DejaVuSans-3"/>`` with no ``d`` attribute, so Qt's SVG
parser rejects the definition and logs "link ... is undefined" for
every ``<use>`` of it (nothing visible is lost — a space draws nothing —
but the noise hides real warnings).  Giving it an empty path silences
it with byte-identical output.

--check exits non-zero if a regenerated diagram no longer matches the
committed asset structurally (same set of drawn elements), which is what
the test suite runs so the assets cannot go stale.
"""
from __future__ import annotations

import argparse
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE / "tutorial"))
sys.path.insert(0, str(ROOT / "src"))

DIAGRAMS = ("architecture", "envdet_path", "loopback_offset", "ila_loop")


_EMPTY_GLYPH = re.compile(r'<path id="([^"]+)"(?![^>]*\sd=)')


def render(name: str) -> str:
    """The SVG for one diagram, with Qt-parseable glyph definitions."""
    import schematics
    svg = getattr(schematics, name)(None)
    return _EMPTY_GLYPH.sub(r'<path id="\1" d="M 0 0"', svg)


def shape(svg: str) -> tuple:
    """What the diagram draws, tag by tag — the identity we compare.

    Deliberately not a byte comparison: glyph ids and coordinate
    precision wobble between matplotlib versions without the picture
    changing.
    """
    root = ET.fromstring(svg)
    ns = "{http://www.w3.org/2000/svg}"
    counts: dict[str, int] = {}
    for el in root.iter():
        tag = el.tag.replace(ns, "")
        counts[tag] = counts.get(tag, 0) + 1
    texts = {"".join(t.itertext()).strip() for t in root.iter(f"{ns}text")}
    return tuple(sorted(counts.items())), tuple(sorted(texts - {""}))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, default=ROOT / "assets" / "schematics")
    ap.add_argument("--check", action="store_true",
                    help="compare against the committed assets instead of "
                         "writing them")
    args = ap.parse_args(argv)

    args.out.mkdir(parents=True, exist_ok=True)
    stale = []
    for name in DIAGRAMS:
        svg = render(name)
        path = args.out / f"{name}.svg"
        if args.check:
            if not path.exists():
                stale.append(f"{path.name}: missing")
            elif shape(path.read_text()) != shape(svg):
                stale.append(f"{path.name}: drawing differs")
        else:
            path.write_text(svg)
            print(f"{path}  {len(svg) / 1024:.1f} kB  "
                  f"{len(shape(svg)[1])} labels")
    if stale:
        print("stale assets (run tools/build_assets.py):", *stale, sep="\n  ")
        return 1
    if args.check:
        print(f"{len(DIAGRAMS)} schematic assets up to date")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
