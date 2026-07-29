"""Content model: bilingual data classes the renderer walks.

Authoring conventions inside ``T`` strings (the only two — this is not a
markup language):

- ``$...$`` becomes an inline math SVG (language-neutral, rendered once).
- ``{key}`` is a format field filled from the enclosing Section's
  ``values(ctx)`` result — the ONLY way a computed number reaches prose;
  hand-typed numbers in running text are reserved for spec constants that
  are quoted with their source.  Literal braces must be doubled.

Strings are trusted HTML fragments: ``<code>``, ``<em>``, ``<a href=#>``
are fine.  Math substitution happens before ``format_map`` so LaTeX
braces never need doubling.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable


@dataclass(frozen=True)
class T:
    """One bilingual fragment: zh and en authored side by side."""

    zh: str
    en: str


@dataclass(frozen=True)
class F:
    """A display formula (block-level)."""

    latex: str
    fontsize: int = 14


@dataclass(frozen=True)
class Fig:
    """A build-time matplotlib figure, embedded as base64 PNG."""

    id: str
    build: Callable  # (RunContext) -> matplotlib Figure
    caption: T | None = None


@dataclass(frozen=True)
class Diagram:
    """An inline SVG block: hand-authored literal or built (schemdraw…)."""

    id: str
    svg: str | None = None
    build: Callable | None = None  # (RunContext) -> svg string
    caption: T | None = None


@dataclass(frozen=True)
class Table:
    header: tuple
    rows: tuple | None = None                 # static rows of str
    rows_from: Callable | None = None         # (RunContext) -> list[list[str]]
    caption: T | None = None


@dataclass(frozen=True)
class Code:
    """A literal code block (not bilingual)."""

    text: str
    lang: str = "python"


@dataclass(frozen=True)
class Section:
    id: str          # unique anchor within the Doc
    title: T
    body: tuple = ()
    level: int = 2   # h2; subsections use 3
    # computed numbers for {key} fields in this section's T strings;
    # value_keys is the declared contract so the fast test can validate
    # fields without running anything expensive
    values: Callable | None = None            # (RunContext) -> dict[str, str]
    value_keys: tuple = ()


@dataclass(frozen=True)
class Chapter:
    id: str
    title: T
    sections: tuple


@dataclass(frozen=True)
class Doc:
    id: str          # "tutorial" | "devguide"
    title: T
    subtitle: T
    chapters: tuple


def walk_texts(doc: Doc):
    """Yield (section, T) for every bilingual fragment in the doc."""
    for ch in doc.chapters:
        yield None, ch.title
        for sec in ch.sections:
            yield sec, sec.title
            for item in sec.body:
                if isinstance(item, T):
                    yield sec, item
                elif isinstance(item, (Fig, Diagram, Table)) and item.caption:
                    yield sec, item.caption
                if isinstance(item, Table):
                    for h in item.header:
                        yield sec, h


def walk_items(doc: Doc, kind):
    for ch in doc.chapters:
        for sec in ch.sections:
            for item in sec.body:
                if isinstance(item, kind):
                    yield sec, item
