"""Is a committed generated HTML doc still what the builder produces?

The nightly lane rebuilds `docs/tutorial.html` and `docs/devguide.html`
and compares them against the committed copies, because nothing else
notices when the shipped HTML falls behind the code it is generated
from.  The comparison has to ignore the provenance footer the builder
stamps, and the check that did this normalised only the timestamp
inside it.

That could never pass.  The footer names the commit the build ran at,
and **a file cannot carry the id of the commit that contains it**: what
is committed was built at the parent, with the tree dirty (the docs are
rebuilt and committed in one go), while a rebuild at HEAD stamps HEAD.
So the comparison reported a difference on every run, for every commit
— and because the step exits non-zero, the schematic check behind it
never executed either.

The whole footer is therefore dropped before comparing: commit id,
dirty flag, build time and numpy version are build circumstance, not
content.  Anything else that differs is genuine staleness.

Used by `scripts/ci_nightly.sh`; `strip_provenance` is pinned by
`tests/test_docs_build.py`.
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

#: the element `tools/tutorial/render.py` appends to every document
PROVENANCE = re.compile(r"<footer>generated from commit .*?</footer>", re.S)

DOCS = ("docs/tutorial.html", "docs/devguide.html")


def strip_provenance(html: str) -> str:
    """The document without its provenance footer.  Raises when the
    footer is not there: a normaliser that silently matches nothing
    would make every comparison pass on the wrong text."""
    stripped, n = PROVENANCE.subn("", html)
    if n != 1:
        raise ValueError(
            f"expected exactly one provenance footer, found {n} — "
            "render.py's footer changed and this checker did not")
    return stripped


def committed(name: str) -> str:
    return subprocess.run(["git", "show", f"HEAD:{name}"], check=True,
                          capture_output=True, text=True).stdout


def main(names: tuple[str, ...] = DOCS) -> int:
    for name in names:
        rebuilt = Path(name).read_text(encoding="utf-8")
        # the rebuilt file must carry a footer; the committed one is
        # only required to match once the footer is out of the way
        new = strip_provenance(rebuilt)
        old = strip_provenance(committed(name))
        if old != new:
            print(f"{name} is stale: rebuild with "
                  "python tools/build_docs.py --out docs/", file=sys.stderr)
            return 1
    print("committed docs are current")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
