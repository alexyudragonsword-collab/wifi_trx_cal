"""Assert every compiled module exports the init symbol CPython asks for.

A cross-compiled extension module can be well-formed, correctly named,
correctly tagged, present in the wheel and present in the APK, and still
fail to import on the device because the one symbol the import system
looks up — ``PyInit_<leaf>`` — was never exported.  Nothing on the build
side notices: the compiler succeeds, the wheel assembles, and
``inspect_apk.py --native`` sees a .so exactly where it wants one.

That is not hypothetical.  ``-fvisibility=hidden`` hides the init
function on any target whose ``PyMODINIT_FUNC`` carries no visibility
attribute of its own — CPython 3.8, which is what Chaquopy ships for
Android.  A host build (3.9+) exports it, so the failure appears only on
the device, as "dynamic module does not define module export function".

So the export is checked here, against the artefact that will ship, with
the NDK's own nm.  Cheap, and it fails at the wheel rather than twenty
minutes later inside an emulator.

Usage:  check_wheel_exports.py <nm-binary> <wheel> [wheel ...]
"""
from __future__ import annotations

import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path


def exported(nm: str, so: Path) -> set[str]:
    """The dynamic symbols the shared object actually defines."""
    out = subprocess.run([nm, "-D", "--defined-only", str(so)],
                         capture_output=True, text=True, check=True).stdout
    return {line.split()[-1] for line in out.splitlines() if line.split()}


def check_wheel(nm: str, wheel: Path) -> list[str]:
    problems: list[str] = []
    with tempfile.TemporaryDirectory() as tmp:
        with zipfile.ZipFile(wheel) as z:
            z.extractall(tmp)
        sos = sorted(Path(tmp).rglob("*.so"))
        if not sos:
            return [f"{wheel.name}: no compiled modules at all"]
        for so in sos:
            # CPython looks up PyInit_<last dotted component>, so the file
            # stem is the name to expect no matter how deep the package is
            want = f"PyInit_{so.stem}"
            syms = exported(nm, so)
            rel = so.relative_to(tmp)
            if want in syms:
                print(f"  ok  {rel}: {want}")
            else:
                inits = sorted(s for s in syms if s.startswith("PyInit"))
                problems.append(f"{wheel.name}: {rel} does not export {want} "
                                f"(exports: {inits or 'no PyInit symbol'})")
    return problems


def main(argv: list[str]) -> int | str:
    if len(argv) < 3:
        return "usage: check_wheel_exports.py <nm-binary> <wheel> [wheel ...]"
    nm, wheels = argv[1], [Path(p) for p in argv[2:]]
    problems: list[str] = []
    for wheel in wheels:
        print(f"--- {wheel} ---")
        problems += check_wheel(nm, wheel)
    for line in problems:
        print("FAIL:", line)
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
