"""HTML emitter: Doc tree -> one self-contained bilingual page.

Both languages ship in the same file as sibling elements
(``<p class="zh">`` / ``<p class="en">``); CSS hides the inactive one and
an 8-line script flips the ``lang-*`` class on <html>.  No external
assets of any kind — math is inline SVG, figures are base64 PNG.
"""
from __future__ import annotations

import base64
import html
import io
import re

from mathsvg import latex_to_svg
from model import Code, Diagram, Doc, F, Fig, Section, T, Table

_MATH_SPLIT = re.compile(r"\$([^$]+)\$")


def _render_text(text: str, vals: dict) -> str:
    """Format {key} fields and render $...$ math, without collisions.

    The text is split on math segments first: LaTeX braces never meet
    format_map, and the brace-laden SVG that math rendering produces is
    never formatted.
    """
    if text.count("$") % 2:
        raise ValueError(f"unbalanced $ in: {text[:80]!r}")
    parts = _MATH_SPLIT.split(text)
    return "".join(latex_to_svg(p) if i % 2 else p.format_map(vals)
                   for i, p in enumerate(parts))

CSS = """
:root { --ink:#1a1a1a; --accent:#0b5fa5; --muted:#667; --line:#d8dde3; }
* { box-sizing: border-box; }
body { margin:0; color:var(--ink); font:15px/1.65 -apple-system,"Segoe UI",
  Roboto,"Helvetica Neue","PingFang SC","Microsoft YaHei","Noto Sans CJK SC",
  sans-serif; display:grid; grid-template-columns:270px 1fr; }
nav { position:sticky; top:0; max-height:100vh; overflow-y:auto;
  padding:18px 14px; border-right:1px solid var(--line); font-size:13px; }
nav a { display:block; color:var(--ink); text-decoration:none;
  padding:2px 6px; border-radius:4px; }
nav a:hover { background:#eef3f8; }
nav .ch { font-weight:600; margin-top:10px; }
nav .sec { padding-left:16px; color:#445; }
nav .sub { padding-left:30px; color:#667; font-size:12px; }
main { padding:28px 48px 80px; max-width:960px; }
h1 { font-size:26px; border-bottom:2px solid var(--accent); padding-bottom:8px; }
h2 { font-size:20px; margin-top:38px; border-bottom:1px solid var(--line);
  padding-bottom:4px; }
h3 { font-size:17px; margin-top:28px; }
p { margin:9px 0; }
code { background:#f0f2f5; padding:1px 5px; border-radius:4px;
  font-size:13px; font-family:ui-monospace,Consolas,monospace; }
pre { background:#f6f8fa; border:1px solid var(--line); border-radius:6px;
  padding:12px 14px; overflow-x:auto; font-size:13px; line-height:1.5; }
pre code { background:none; padding:0; }
table { border-collapse:collapse; margin:14px 0; font-size:13.5px; }
th,td { border:1px solid var(--line); padding:5px 11px; text-align:left; }
th { background:#f2f5f8; }
figure { margin:18px 0; text-align:center; }
figure img, figure svg { max-width:100%; height:auto; }
figcaption { font-size:13px; color:var(--muted); margin-top:6px; }
.formula { text-align:center; margin:14px 0; }
svg.math { vertical-align:middle; margin:0 1px; }
html.lang-zh .en { display:none; }
html.lang-en .zh { display:none; }
#langbtn { position:fixed; top:14px; right:20px; z-index:9;
  background:var(--accent); color:#fff; border:0; border-radius:6px;
  padding:7px 14px; font-size:13px; cursor:pointer; }
footer { margin-top:60px; padding-top:10px; border-top:1px solid var(--line);
  font-size:12px; color:var(--muted); }
@media print { nav,#langbtn { display:none } body { display:block } }
@media (max-width:900px) { body { display:block }
  nav { position:static; max-height:none; border-right:0;
        border-bottom:1px solid var(--line); } }
"""

JS = """
var b=document.getElementById('langbtn'),r=document.documentElement;
function setl(l){r.className='lang-'+l;
  b.textContent=(l==='zh')?'EN':'\\u4e2d\\u6587';
  try{localStorage.setItem('wifitrx-doc-lang',l)}catch(e){}}
b.onclick=function(){setl(r.className==='lang-zh'?'en':'zh')};
try{setl(localStorage.getItem('wifitrx-doc-lang')||'zh')}catch(e){setl('zh')}
"""


class _Strict(dict):
    def __init__(self, d, where):
        super().__init__(d)
        self.where = where

    def __missing__(self, key):
        raise KeyError(f"section {self.where!r}: no value for {{{key}}}")


def _pair(t: T, vals: _Strict, tag: str = "p", extra: str = "") -> str:
    out = []
    for lang in ("zh", "en"):
        s = _render_text(getattr(t, lang), vals)
        out.append(f'<{tag} class="{lang}{extra}">{s}</{tag}>')
    return "".join(out)


def _values_for(sec: Section, ctx) -> _Strict:
    if sec is None or sec.values is None:
        return _Strict({}, sec.id if sec else "-")
    vals = sec.values(ctx)
    if set(vals) != set(sec.value_keys):
        raise ValueError(
            f"section {sec.id!r}: values() keys {sorted(vals)} != declared "
            f"value_keys {sorted(sec.value_keys)}")
    return _Strict(vals, sec.id)


def _render_item(item, vals: _Strict, ctx) -> str:
    if isinstance(item, T):
        return _pair(item, vals)
    if isinstance(item, F):
        return (f'<div class="formula">'
                f"{latex_to_svg(item.latex, item.fontsize)}</div>")
    if isinstance(item, Code):
        return f"<pre><code>{html.escape(item.text)}</code></pre>"
    if isinstance(item, Fig):
        fig = item.build(ctx)
        buf = io.BytesIO()
        fig.savefig(buf, format="png", dpi=110, bbox_inches="tight")
        import matplotlib.pyplot as plt
        plt.close(fig)
        b64 = base64.b64encode(buf.getvalue()).decode()
        cap = _pair(item.caption, vals, "figcaption") if item.caption else ""
        return (f'<figure id="{item.id}">'
                f'<img src="data:image/png;base64,{b64}" alt="{item.id}">'
                f"{cap}</figure>")
    if isinstance(item, Diagram):
        svg = item.svg if item.svg is not None else item.build(ctx)
        cap = _pair(item.caption, vals, "figcaption") if item.caption else ""
        return f'<figure id="{item.id}">{svg}{cap}</figure>'
    if isinstance(item, Table):
        rows = item.rows if item.rows is not None else item.rows_from(ctx)
        head = "".join(f"<th>{_pair(h, vals, 'span')}</th>"
                       for h in item.header)
        body = "".join(
            "<tr>" + "".join(
                f"<td>{_render_text(str(c), vals)}</td>"
                for c in row) + "</tr>"
            for row in rows)
        cap = _pair(item.caption, vals, "figcaption") if item.caption else ""
        return (f"<figure>{cap}<table><thead><tr>{head}</tr></thead>"
                f"<tbody>{body}</tbody></table></figure>")
    raise TypeError(f"unknown body item {type(item).__name__}")


def _toc(doc: Doc) -> str:
    out = ["<nav>"]
    for ch in doc.chapters:
        out.append(f'<a class="ch" href="#{ch.id}">'
                   f'{_pair(ch.title, _Strict({}, ch.id), "span")}</a>')
        for sec in ch.sections:
            cls = "sec" if sec.level == 2 else "sub"
            out.append(f'<a class="{cls}" href="#{sec.id}">'
                       f'{_pair(sec.title, _Strict({}, sec.id), "span")}</a>')
    out.append("</nav>")
    return "".join(out)


def render_doc(doc: Doc, ctx, provenance: dict, rebuild_cmd: str) -> str:
    parts = [f'<main><h1>{_pair(doc.title, _Strict({}, "title"), "span")}'
             "</h1>",
             _pair(doc.subtitle, _Strict({}, "subtitle"))]
    for ch in doc.chapters:
        parts.append(f'<h1 id="{ch.id}">'
                     f'{_pair(ch.title, _Strict({}, ch.id), "span")}</h1>')
        for sec in ch.sections:
            vals = _values_for(sec, ctx)
            tag = f"h{sec.level}"
            parts.append(f'<{tag} id="{sec.id}">'
                         f'{_pair(sec.title, vals, "span")}</{tag}>')
            for item in sec.body:
                parts.append(_render_item(item, vals, ctx))
    dirty = " (dirty)" if provenance.get("git_dirty") else ""
    parts.append(
        "<footer>generated from commit "
        f"<code>{provenance.get('git_commit') or 'unknown'}</code>{dirty} · "
        f"{provenance.get('generated_utc')} · numpy "
        f"{provenance.get('numpy')} · rebuild: <code>{rebuild_cmd}</code>"
        "</footer></main>")

    zh_title = html.escape(doc.title.zh)
    return ("<!DOCTYPE html>\n"
            f'<html lang="zh" class="lang-zh"><head><meta charset="utf-8">'
            f'<meta name="viewport" content="width=device-width,'
            f'initial-scale=1"><title>{zh_title}</title>'
            f"<style>{CSS}</style></head><body>"
            f'<button id="langbtn">EN</button>'
            f"{_toc(doc)}{''.join(parts)}"
            f"<script>{JS}</script></body></html>")
