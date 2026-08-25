"""Assert what the instrumented run actually did, and say why it failed.

Two jobs need this and a green build says neither: a test that never
executes, or is skipped, leaves the run successful and the guard
imaginary.  So the count is asserted here rather than read out of gradle
output by a person.

It also prints each failure's message.  The reason is unglamorous: the
log API truncates by size, so gradle's own report of *why* a test failed
sits in a middle section that a tail cannot reach, and the run-log
download host is outside some network policies.  Evidence that cannot be
retrieved is not evidence, so the summary goes at the end where a tail
always lands.

Usage:  check_ondevice_results.py <results-dir> <expected-count> [label]
"""
from __future__ import annotations

import glob
import os
import sys
import xml.etree.ElementTree as ET

MAX_FAILURE_LINES = 20


def collect(results_dir: str) -> tuple[int, int, int, list, list]:
    files = sorted(glob.glob(os.path.join(results_dir, "**", "*.xml"),
                             recursive=True))
    total = failed = skipped = 0
    names: list[str] = []
    failures: list[tuple[str, str]] = []
    for path in files:
        suite = ET.parse(path).getroot()
        total += int(suite.get("tests", 0))
        failed += int(suite.get("failures", 0)) + int(suite.get("errors", 0))
        skipped += int(suite.get("skipped", 0))
        for case in suite.iter("testcase"):
            name = f"{case.get('classname')}.{case.get('name')}"
            names.append(name)
            for bad in list(case.iter("failure")) + list(case.iter("error")):
                failures.append((name, (bad.text or bad.get("message") or
                                        "(no message)")))
    return total, failed, skipped, names, failures


def main(argv: list[str]) -> int:
    if len(argv) < 3:
        return "usage: check_ondevice_results.py <dir> <expected> [label]"
    results_dir, expected = argv[1], int(argv[2])
    label = argv[3] if len(argv) > 3 else "on-device"

    if not glob.glob(os.path.join(results_dir, "**", "*.xml"), recursive=True):
        return f"{label}: no instrumented test results were written at all"
    total, failed, skipped, names, failures = collect(results_dir)

    print(f"{label} tests: {total} run, {failed} failed, {skipped} skipped")
    for name in sorted(names):
        print("  -", name)
    for name, text in failures:
        print(f"\n--- {name} ---")
        lines = [ln for ln in text.strip().splitlines() if ln.strip()]
        for line in lines[:MAX_FAILURE_LINES]:
            print("   ", line)
        if len(lines) > MAX_FAILURE_LINES:
            print(f"    ... {len(lines) - MAX_FAILURE_LINES} more lines")

    # Exact, not a floor: ">= n" still passes when a test is added while an
    # existing one quietly stops running.  One AVD, so the sum is the count.
    if total != expected:
        return (f"{label}: expected exactly {expected} tests, ran {total} — "
                "update this number when adding one")
    if failed or skipped:
        return f"{label}: tests failed or were skipped"
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
