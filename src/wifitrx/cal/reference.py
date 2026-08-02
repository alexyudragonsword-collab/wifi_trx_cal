"""Reference views of the calibration sequence, derived from the code.

The tutorial chapter 5 and the GUI's Reference tab both show the same
three things: the ordered step list, the ordering-constraint graph and
the physical reason behind every edge.  They are derived here, once, so
the two presentations cannot drift from each other or from
``cal/deps.py``.

Everything in this module is pure data or plain string building: no
matplotlib, no Qt, no calibration run.  The one thing that cannot be
derived without running is each step's acceptance spec (a ``CalResult``
field), so ``calibration_order`` takes it as an optional argument.
"""
from __future__ import annotations

from .deps import STEP_REQUIRES, planned_steps

# sense semantics are defined in cal/base.py: "min" -> value >= limit,
# "max" -> value <= limit, "abs_max" -> |value| <= limit
_SPEC_FMT = {"min": "{m} ≥ {l:g}", "max": "{m} ≤ {l:g}",
             "abs_max": "|{m}| ≤ {l:g}"}
_DASH = "—"


def step_order(profile: str = "factory") -> list[str]:
    """The planned step names, in execution order."""
    # function-local: the profile table is the only thing needed from
    # sequence, and importing it at module scope would drag chain / pa /
    # dpd / metrics in behind a dict lookup
    from .sequence import PROFILES
    return planned_steps(PROFILES[profile], with_iip2=True, with_dpd=True)


def format_spec(spec: dict | None) -> str:
    """``{"metric","limit","sense"}`` -> a readable acceptance clause."""
    fmt = _SPEC_FMT.get((spec or {}).get("sense"))
    return _DASH if not fmt else fmt.format(m=spec["metric"], l=spec["limit"])


def calibration_order(profile: str = "factory",
                      specs_by_name: dict | None = None) -> list[dict]:
    """One row per step: execution index, name, prerequisites, spec.

    ``specs_by_name`` maps step name -> the ``spec`` dict a CalResult
    reported; without it the spec column reads as an em dash (the
    acceptance criteria only exist once a calibration has run).
    """
    rows = []
    for i, name in enumerate(step_order(profile), 1):
        rows.append({
            "n": i,
            "step": name,
            "requires": ", ".join(STEP_REQUIRES.get(name, {})) or _DASH,
            "spec": format_spec((specs_by_name or {}).get(name)),
        })
    return rows


def dependency_edges(profile: str = "factory") -> list[dict]:
    """Every ordering edge with the reason deps.py carries.

    The walk order defines the edge numbering, and
    ``dependency_graph_svg`` walks identically — the badge on a line in
    the figure is this list's ``n``.  Keep the two in lockstep.
    """
    order = step_order(profile)
    known = set(order)
    rows = []
    for name in order:
        for req, reason in STEP_REQUIRES.get(name, {}).items():
            if req in known:
                rows.append({"n": len(rows) + 1,
                             "edge": f"{req} → {name}", "reason": reason})
    return rows


def capture_cost_rows(results) -> list[dict]:
    """Per-step capture cost from a finished run, plus a total row.

    ``results`` is the CalResult list a sequence run returns, or the
    step records a cal-state file carries (``summary`` serializes
    ``cost``, so a delivered bundle reports its own test cost).  Steps
    that spend no captures are omitted, as in the tutorial's table.
    """
    rows, cap_tot, samp_tot = [], 0, 0
    for r in results:
        cost = (r.get("cost") if isinstance(r, dict) else r.cost) or {}
        if not cost:
            continue
        name = r["name"] if isinstance(r, dict) else r.name
        captures, samples = cost.get("captures", 0), cost.get("samples", 0)
        cap_tot, samp_tot = cap_tot + captures, samp_tot + samples
        rows.append({"step": name, "captures": f"{captures:,}",
                     "samples": f"{samples:,}"})
    if rows:
        rows.append({"step": "total", "captures": f"{cap_tot:,}",
                     "samples": f"{samp_tot:,}"})
    return rows


# ------------------------------------------------------------- the graph
_BW, _BH, _HGAP, _VGAP = 158, 32, 130, 20
_TOP = 34                                  # column-header band
_PER_ROW = 4                               # free-step band, boxes per row


def _arrowhead(x: float, y: float) -> str:
    """A left-pointing-into-the-box arrowhead as an explicit polygon.

    A <defs><marker> would be shorter and Qt 6.11 draws it correctly,
    but marker support is recent in Qt's SVG Tiny renderer and the GUI
    advertises PySide6 >= 6.6; an arrowless dependency graph reads as an
    undirected one, so this figure does not rely on it.
    """
    return (f'<polygon points="{x} {y},{x - 8} {y - 4},{x - 8} {y + 4}" '
            f'fill="#445"/>')


def dependency_graph_svg(profile: str = "factory") -> str:
    """Layered SVG of STEP_REQUIRES.

    Layout rules that keep it readable: Kahn depth -> column (a header
    names the stage), the steps that take part in no ordering constraint
    get their own band at the bottom instead of padding the columns,
    edges route orthogonally through one gutter lane each (no crossing
    curves), and every edge carries a numbered badge indexing
    ``dependency_edges``.  Reasons also stay as <title> tooltips, which
    browsers show on hover.
    """
    order = step_order(profile)

    dependents = {r for n in order for r in STEP_REQUIRES.get(n, {})}
    constrained = [n for n in order
                   if STEP_REQUIRES.get(n) or n in dependents]
    free = [n for n in order if n not in constrained]

    level: dict[str, int] = {}
    for name in order:
        level[name] = 1 + max(
            (level.get(r, 0) for r in STEP_REQUIRES.get(name, {})), default=0)
    cols: dict[int, list[str]] = {}
    for name in constrained:
        cols.setdefault(level[name], []).append(name)

    n_col = max(cols)
    rows_max = max(len(v) for v in cols.values())
    pos: dict[str, tuple[float, float]] = {}
    for lv, names in sorted(cols.items()):
        x = 12 + (lv - 1) * (_BW + _HGAP)
        for i, name in enumerate(names):
            pos[name] = (x, _TOP + i * (_BH + _VGAP))
    band_y = _TOP + rows_max * (_BH + _VGAP) + 30
    for i, name in enumerate(free):
        pos[name] = (12 + (i % _PER_ROW) * (_BW + 16),
                     band_y + 22 + (i // _PER_ROW) * (_BH + 10))

    width = max(n_col * (_BW + _HGAP) + 12, _PER_ROW * (_BW + 16) + 12)
    height = band_y + 22 + ((len(free) - 1) // _PER_ROW + 1) * (_BH + 10) + 12

    p = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} '
         f'{height}" width="{width}" height="{height}" '
         f'style="max-width:100%;height:auto;font-family:sans-serif">']

    for lv in sorted(cols):
        x = 12 + (lv - 1) * (_BW + _HGAP)
        p.append(f'<text x="{x + _BW / 2}" y="20" text-anchor="middle" '
                 f'font-size="11" fill="#667">stage {lv}</text>')
        if lv > 1:                       # dashed separator between stages
            gx = x - _HGAP / 2
            p.append(f'<line x1="{gx}" y1="26" x2="{gx}" y2="{band_y - 12}" '
                     f'stroke="#ccd" stroke-dasharray="3 4"/>')
    p.append(f'<line x1="12" y1="{band_y}" x2="{width - 12}" y2="{band_y}" '
             f'stroke="#ccd" stroke-dasharray="3 4"/>')
    p.append(f'<text x="12" y="{band_y + 16}" font-size="11" fill="#667">'
             f'no ordering constraint (any order)</text>')

    lanes: dict[int, int] = {}
    idx = 0
    for name in order:
        for req, reason in STEP_REQUIRES.get(name, {}).items():
            if req not in pos or name not in pos:
                continue
            idx += 1
            x1, y1 = pos[req]
            x2, y2 = pos[name]
            gcol = level[name]
            lanes[gcol] = lanes.get(gcol, 0) + 1
            gx = x2 - _HGAP + 30 + (lanes[gcol] - 1) * 16     # lane offset
            sx, sy = x1 + _BW, y1 + _BH / 2
            ex, ey = x2, y2 + _BH / 2
            straight = abs(sy - ey) <= 1
            d = (f"M{sx} {sy} H{ex}" if straight
                 else f"M{sx} {sy} H{gx} V{ey} H{ex}")
            # badge on the clear part of the run: mid-gutter for a
            # dog-leg; a straight edge's midpoint would land on the other
            # edges' gutter lanes, so sit it right after the source box
            bx, by = (sx + 16, sy) if straight else (gx, (sy + ey) / 2)
            p.append(f'<path d="{d}" fill="none" stroke="#7a8598" '
                     f'stroke-width="1.4">'
                     f"<title>{req} → {name}: {reason}</title></path>")
            p.append(_arrowhead(ex, ey))
            p.append(f'<circle cx="{bx}" cy="{by}" r="7.5" '
                     f'fill="#fff" stroke="#7a8598" stroke-width="1"/>'
                     f'<text x="{bx}" y="{by + 3.5}" '
                     f'text-anchor="middle" font-size="9" fill="#445">'
                     f'{idx}</text>')

    rank = {n: i for i, n in enumerate(order, 1)}
    for name, (x, y) in pos.items():
        dashed = ' stroke-dasharray="4 3"' if name in free else ""
        p.append(
            f'<rect x="{x}" y="{y}" width="{_BW}" height="{_BH}" rx="6" '
            f'fill="#eef3f8" stroke="#0b5fa5"{dashed}/>'
            f'<text x="{x + _BW / 2}" y="{y + _BH / 2 + 4}" '
            f'text-anchor="middle" font-size="11">'
            f'{rank[name]}. {name}</text>')
    p.append("</svg>")
    return "".join(p)
