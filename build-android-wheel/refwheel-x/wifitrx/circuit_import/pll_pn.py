# CSV-loading concept from pll_simulator:src/pllsim/fit.py (load_pn_csv),
# self-contained re-implementation.  See PROVENANCE.md.
"""PLL phase-noise table import: measured/simulated L(f) -> TabulatedPhase.

Accepts the CSV shapes that come out of Virtuoso/spectre pnoise exports or
instrument saves: two columns (offset Hz, dBc/Hz), tolerant of comment
lines (#, !, *), header rows, and common column-name variants.
"""
from __future__ import annotations

from pathlib import Path


from ..impairments.phase_noise import TabulatedPhase

_FREQ_NAMES = ("offset_hz", "freq_hz", "frequency", "offset", "foffset")
_LEVEL_NAMES = ("dbchz", "dbc_hz", "l_dbc", "pnoise", "phase_noise",
                "dbc/hz", "l(f)")


def load_pll_pn_csv(path: str | Path, name: str = "imported_lo",
                    min_offset_hz: float = 1.0) -> TabulatedPhase:
    rows: list[tuple[float, float]] = []
    header_freq_col, header_level_col = 0, 1
    for raw in Path(path).read_text().splitlines():
        line = raw.strip()
        if not line or line[0] in "#!*;":
            continue
        parts = [p.strip() for p in line.replace("\t", ",").split(",")
                 if p.strip()]
        if len(parts) < 2:
            continue
        try:
            f, lvl = (float(parts[header_freq_col]),
                      float(parts[header_level_col]))
        except ValueError:
            # header row: try to locate the columns by name
            low = [p.lower().replace(" ", "_") for p in parts]
            for i, nme in enumerate(low):
                if any(k in nme for k in _FREQ_NAMES):
                    header_freq_col = i
                if any(k in nme for k in _LEVEL_NAMES):
                    header_level_col = i
            continue
        if f >= min_offset_hz:
            rows.append((f, lvl))
    if len(rows) < 3:
        raise ValueError(f"{path}: 有效相噪数据点不足({len(rows)} < 3)")
    rows.sort()
    f_pts, l_pts = zip(*rows)
    if any(lvl > 0 or lvl < -200 for lvl in l_pts):
        raise ValueError(f"{path}: dBc/Hz 数值超出合理范围 [-200, 0]")
    return TabulatedPhase(name, f_pts=tuple(f_pts), l_dbc_pts=tuple(l_pts))
