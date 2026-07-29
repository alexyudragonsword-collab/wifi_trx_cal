"""LaTeX -> tight inline SVG via matplotlib mathtext.  Memoized.

Offline by construction: ``svg.fonttype = "path"`` turns every glyph
into path outlines, so the committed HTML needs no fonts; the SVG
timestamp is stripped so rebuilds don't churn the diff.

mathtext limitations (author accordingly):
- supported: \\frac, \\sqrt, sub/superscripts, Greek, \\sum \\int,
  \\hat \\bar \\overline, \\mathrm \\mathbf \\mathcal, \\left( \\right),
  \\langle \\rangle, |...|.
- NOT supported: \\le (use \\leq), \\tfrac (use \\frac), amsmath environments (align/cases/matrix) — author
  multi-line derivations as consecutive F items; \\text{} — use
  \\mathrm{}; \\operatorname; \\boldsymbol.
"""
from __future__ import annotations

import io
import re

import matplotlib

matplotlib.use("Agg")
import matplotlib as mpl  # noqa: E402
from matplotlib.figure import Figure  # noqa: E402
from matplotlib.font_manager import FontProperties  # noqa: E402
from matplotlib.mathtext import MathTextParser  # noqa: E402

mpl.rcParams["svg.fonttype"] = "path"

_PARSER = MathTextParser("path")
_memo: dict[tuple[str, int], str] = {}
_SVG_TAG = re.compile(r"<svg\b")


def latex_to_svg(latex: str, fontsize: int = 12) -> str:
    """Render ``latex`` (without $ delimiters) to an inline <svg> string."""
    key = (latex, fontsize)
    if key in _memo:
        return _memo[key]
    src = f"${latex}$"
    try:
        w, h, depth = _PARSER.parse(
            src, dpi=72, prop=FontProperties(size=fontsize))[:3]
    except Exception as exc:
        raise ValueError(f"mathtext cannot parse {latex!r}: {exc}") from exc

    fig = Figure()
    fig.text(0, 0, src, fontsize=fontsize)
    buf = io.BytesIO()
    fig.savefig(buf, format="svg", bbox_inches="tight", pad_inches=0.02,
                transparent=True, metadata={"Date": None})
    svg = buf.getvalue().decode()
    svg = svg[svg.index("<svg"):]
    # matplotlib embeds the source latex as an XML comment; drop it (it
    # would read as an unresolved {field} to the build checks, and it is
    # dead weight in the committed HTML)
    svg = re.sub(r"<!--.*?-->", "", svg, flags=re.S)
    # baseline alignment: shift down by the descent fraction so inline
    # math sits on the text baseline instead of floating
    align = f"vertical-align:-{float(depth) / max(float(h), 1.0):.2f}em"
    svg = _SVG_TAG.sub(f'<svg class="math" style="{align}"', svg, count=1)
    _memo[key] = svg
    return svg


_INLINE = re.compile(r"\$([^$]+)\$")


def substitute_inline(text: str, fontsize: int = 12) -> str:
    """Replace every ``$...$`` in ``text`` with rendered SVG.

    Must run BEFORE format_map so LaTeX braces never collide with
    ``{key}`` fields.
    """
    if text.count("$") % 2:
        raise ValueError(f"unbalanced $ in: {text[:80]!r}")
    return _INLINE.sub(
        lambda m: latex_to_svg(m.group(1), fontsize), text)
