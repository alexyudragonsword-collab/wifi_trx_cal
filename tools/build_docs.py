"""Build the bilingual tutorial/devguide HTML pages.

    python tools/build_docs.py [--out docs/] [--only tutorial|devguide]
    [--cache PATH]

--cache pickles the expensive RunContext products so prose iteration
doesn't re-run calibrations; never use it for the committed build.
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE / "tutorial"))
sys.path.insert(0, str(ROOT / "src"))


def main(argv=None) -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, default=ROOT / "docs")
    ap.add_argument("--only", choices=("tutorial", "devguide"), default=None)
    ap.add_argument("--cache", type=Path, default=None)
    args = ap.parse_args(argv)

    from render import render_doc
    from runs import RunContext
    from wifitrx.provenance import provenance

    ctx = RunContext(cache=args.cache)
    prov = provenance()
    args.out.mkdir(parents=True, exist_ok=True)

    docs = []
    if args.only in (None, "tutorial"):
        from content.tutorial import DOC as tutorial_doc
        docs.append(tutorial_doc)
    if args.only in (None, "devguide"):
        from content.devguide import DOC as devguide_doc
        docs.append(devguide_doc)

    for doc in docs:
        t0 = time.perf_counter()
        html = render_doc(doc, ctx, prov,
                          rebuild_cmd="python tools/build_docs.py")
        path = args.out / f"{doc.id}.html"
        path.write_text(html, encoding="utf-8")
        print(f"{path}  {len(html) / 1e6:.2f} MB  "
              f"({time.perf_counter() - t0:.1f} s)")


if __name__ == "__main__":
    main()
