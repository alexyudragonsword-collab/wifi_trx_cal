"""Cal-state inspector content, laid out as data (no toolkit imports).

Both front-ends — the Qt page (``inspector_page.py``) and the Android
bridge — render exactly the sections this module returns, so the two
cannot drift apart.  They did drift once: the Android inspector showed
only the findings while the Qt page also had the step, residual and
provenance tables, which is why the layout now lives here instead of
inside a widget method.

Like the page it feeds, this module decides nothing: every verdict comes
from ``wifitrx.handoff.inspector`` and every table lays out the file's
own content.  ``tests/test_gui_inspector.py`` enforces that on this file
too.
"""
from __future__ import annotations


def fmt(v) -> str:
    if isinstance(v, float):
        return f"{v:.4g}"
    if isinstance(v, (list, tuple)):
        return ", ".join(fmt(x) for x in v[:6]) + ("…" if len(v) > 6 else "")
    if isinstance(v, dict):
        return ", ".join(f"{k}={fmt(x)}" for k, x in v.items())
    return str(v)


def step_rows(doc: dict) -> list[dict]:
    """One row per recorded step — the JSON's content, laid out."""
    rows = []
    for r in doc.get("results") or []:
        before = r.get("metrics_before") or {}
        after = r.get("metrics_after") or {}
        key = next(iter(after), next(iter(before), "-"))
        rows.append({
            "step": r.get("name", "?"),
            "metric": key,
            "before": before.get(key, "—"),
            "after": after.get(key, "—"),
            "passed": {True: "yes", False: "NO", None: "—"}[r.get("passed")],
            "saturated": {True: "RAILED", False: "no",
                          None: "—"}[r.get("saturated")],
            "spec": fmt(r["spec"]) if r.get("spec") else "—",
        })
    return rows


def residual_rows(doc: dict) -> list[dict]:
    """Each shipped residual beside its own specification."""
    res = doc.get("residuals") or {}
    values, spec = res.get("values") or {}, res.get("specification") or {}
    return [{"key": k, "value": fmt(values[k]),
             "unit": (spec.get(k) or {}).get("unit", ""),
             "better": (spec.get(k) or {}).get("better", ""),
             "role": (spec.get(k) or {}).get("role", ""),
             "apply": (spec.get(k) or {}).get("apply", "")}
            for k in sorted(values)]


def provenance_rows(doc: dict) -> list[dict]:
    return [{"key": k, "value": fmt(v)}
            for k, v in sorted((doc.get("provenance") or {}).items())]


def inspector_sections(doc: dict) -> list[dict]:
    """``[{title, columns, rows}, ...]`` — the tables, in display order.

    Empty sections are dropped: a file without residuals should show no
    residual table rather than an empty one.
    """
    built = (
        ("Calibration steps (from the file)",
         ["step", "metric", "before", "after", "passed", "saturated",
          "spec"], step_rows(doc)),
        ("Residuals (each with its shipped specification)",
         ["key", "value", "unit", "better", "role", "apply"],
         residual_rows(doc)),
        ("Provenance", ["key", "value"], provenance_rows(doc)),
    )
    return [{"title": t, "columns": c, "rows": r} for t, c, r in built if r]
