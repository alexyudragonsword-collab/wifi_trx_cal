"""Run provenance: which code, from which state, produced this artifact.

Every generated deliverable (cal-state JSON, report, handoff outputs)
carries this stamp so "which code version produced these numbers" is
answerable from the artifact alone.  ``git_dirty`` is recorded rather
than assumed clean; ``None`` means git was unavailable, which is a
different fact than "clean".
"""
from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


def _git(*args: str) -> str | None:
    try:
        r = subprocess.run(["git", *args], capture_output=True, text=True,
                           cwd=Path(__file__).resolve().parent, timeout=5)
        return r.stdout.strip() if r.returncode == 0 else None
    except (OSError, subprocess.TimeoutExpired):
        return None


def provenance(extra: dict | None = None) -> dict:
    import numpy

    commit = _git("rev-parse", "HEAD")
    status = _git("status", "--porcelain") if commit else None
    doc = {
        "generated_utc": datetime.now(timezone.utc).isoformat(
            timespec="seconds"),
        "git_commit": commit,
        "git_dirty": None if status is None else bool(status),
        "argv": list(sys.argv),
        "python": sys.version.split()[0],
        "numpy": numpy.__version__,
    }
    if extra:
        doc.update(extra)
    return doc


def write_provenance(path: str | Path, extra: dict | None = None) -> Path:
    p = Path(path)
    p.write_text(json.dumps(provenance(extra), indent=2))
    return p
