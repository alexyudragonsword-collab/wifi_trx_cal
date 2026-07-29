"""Standalone cal-state inspector: stdlib-only, checks against embedded spec.

This file deliberately imports NOTHING from wifitrx or third-party
packages (enforced by tests/test_inspector.py): the consumer of a
cal-state JSON is a comm engineer who does not have this library, so the
inspector must be copyable next to the JSON and runnable with bare
Python:  ``python inspect.py cal_state.json``.

Every check runs against the ``spec`` embedded in each result — the spec
in force when the part was calibrated — never against this library's
current tables: checking a six-month-old file against today's table
reports library drift, not file error.

Findings are derived from the data, not hard-coded per step: any result
carrying a spec is re-checked, any step recording ``passed: false`` or a
railed trim is reported, whatever its name.
"""
from __future__ import annotations

import json
import sys

FORMAT = "wifitrx-cal-state-v1"

# severity ordering for the exit code: any "error" -> exit 1
SEVERITIES = ("error", "warning", "info")


def _worst(value, sense: str):
    """Scalar metric value to check: for arrays, the worst element."""
    if isinstance(value, list):
        vals = [v for v in value if isinstance(v, (int, float))]
        if not vals:
            return None
        return min(vals) if sense == "min" else max(
            abs(v) for v in vals) if sense == "abs_max" else max(vals)
    return value if isinstance(value, (int, float)) else None


def _spec_ok(value, limit, sense: str) -> bool | None:
    v = _worst(value, sense)
    if v is None:
        return None
    if sense == "min":
        return v >= limit
    if sense == "max":
        return v <= limit
    if sense == "abs_max":
        return abs(v) <= limit
    return None


def inspect_cal_state(doc: dict) -> list[dict]:
    """Derive findings from a loaded cal-state document.

    Returns [{"severity": "error"|"warning"|"info", "step": str,
    "message": str}, ...]; empty list means nothing to report.
    """
    findings = []

    def add(severity, step, message):
        findings.append({"severity": severity, "step": step,
                         "message": message})

    if doc.get("format") != FORMAT:
        add("error", "-", f"format tag {doc.get('format')!r} != {FORMAT!r}; "
            "this inspector may not understand the file")
    for key in ("tx", "rx"):
        if not isinstance(doc.get(key), dict):
            add("error", "-", f"missing correction state {key!r}: the file "
                "cannot program a chip")

    prov = doc.get("provenance")
    if not prov:
        add("info", "-", "no provenance record: cannot tell which code "
            "version produced these numbers")
    elif prov.get("git_dirty"):
        add("warning", "-", "produced from a dirty working tree "
            f"(commit {prov.get('git_commit', '?')}): numbers may not be "
            "reproducible from the commit alone")

    expiry = doc.get("expiry")
    if expiry and "hold_min_c" in expiry:
        add("info", "-", "corrections valid for "
            f"{expiry.get('hold_min_c')}..{expiry.get('hold_max_c')} degC "
            f"(calibrated at {expiry.get('calibrated_at_c')} degC); outside "
            "this range recalibrate or rely on tracking loops")
    elif expiry is None:
        add("info", "-", "no expiry metadata: the file does not state the "
            "conditions under which these corrections stay valid")

    results = doc.get("results") or []
    if not results:
        add("info", "-", "no per-step results recorded: corrections can be "
            "loaded but nothing here says they were verified")

    for r in results:
        name = r.get("name", "?")
        spec = r.get("spec") or {}
        passed = r.get("passed")
        if passed is False:
            add("error", name, "recorded as failed at calibration time")
        if r.get("saturated"):
            add("warning", name, "met spec with a railed trim code: no "
                "margin left for temperature or ageing")
        if spec:
            metric = spec.get("metric")
            value = (r.get("metrics_after") or {}).get(metric)
            ok = _spec_ok(value, spec.get("limit"), spec.get("sense", ""))
            if ok is None:
                add("warning", name, f"spec names metric {metric!r} but "
                    "metrics_after has no checkable value for it")
            elif not ok:
                add("error", name, f"{metric}={value} violates the embedded "
                    f"spec ({spec.get('sense')} {spec.get('limit')})")
            elif passed is False:
                add("warning", name, f"{metric} meets the embedded spec but "
                    "the step recorded passed=false: the step's own pass "
                    "criterion is stricter than the embedded spec")
        elif passed is not None:
            add("info", name, "no embedded spec: pass/fail cannot be "
                "re-derived from the file alone")
    return findings


def format_findings(findings: list[dict]) -> str:
    if not findings:
        return "OK: no findings."
    order = {s: i for i, s in enumerate(SEVERITIES)}
    lines = []
    for f in sorted(findings, key=lambda f: order.get(f["severity"], 9)):
        lines.append(f"[{f['severity'].upper():7s}] {f['step']}: "
                     f"{f['message']}")
    n_err = sum(f["severity"] == "error" for f in findings)
    lines.append(f"-- {len(findings)} finding(s), {n_err} error(s)")
    return "\n".join(lines)


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) != 1:
        print("usage: python inspect.py cal_state.json", file=sys.stderr)
        return 2
    with open(argv[0], encoding="utf-8") as fh:
        doc = json.load(fh)
    findings = inspect_cal_state(doc)
    print(format_findings(findings))
    return 1 if any(f["severity"] == "error" for f in findings) else 0


if __name__ == "__main__":
    sys.exit(main())
