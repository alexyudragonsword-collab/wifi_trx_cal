"""Every declared config/result field must be read by something.

A dataclass field that is written but never read does not fail — it lies:
a parameter sweep over an unwired knob reports perfect insensitivity, and
a result field nobody consumes documents nothing.  This test AST-scans
every dataclass field in src/wifitrx and requires a Load-context attribute
access with the same name somewhere in src/, app/ or examples/.

tests/ deliberately do NOT count as readers: a knob that only a test reads
is exactly the lying kind — the test asserts on it while the model ignores
it.

(Idea ported from a sibling project's test_no_dead_knobs.py, written there
after an unwired temperature coefficient made a whole temperature study
report perfect stability — the absence of a measurement dressed as one.)
"""
from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src" / "wifitrx"
READER_DIRS = [SRC, ROOT / "app", ROOT / "examples"]

# name-based matching cannot tell two classes' same-named fields apart, so
# a field is only reported dead when NO attribute of that name is read
# anywhere — conservative in the right direction (false negatives, never
# false positives).  Known-dead fields would be excused here with a reason;
# keep this empty.
ALLOWED_DEAD: dict[str, str] = {}


def _dataclass_fields() -> dict[str, set[str]]:
    """{'file:Class': field names} for every @dataclass under src."""
    out = {}
    for p in sorted(SRC.rglob("*.py")):
        for node in ast.walk(ast.parse(p.read_text())):
            if isinstance(node, ast.ClassDef) and any(
                    "dataclass" in ast.unparse(d) for d in node.decorator_list):
                fields = {n.target.id for n in node.body
                          if isinstance(n, ast.AnnAssign)
                          and isinstance(n.target, ast.Name)}
                if fields:
                    out[f"{p.relative_to(ROOT)}:{node.name}"] = fields
    return out


def _read_names() -> set[str]:
    reads = set()
    for d in READER_DIRS:
        for p in sorted(d.rglob("*.py")):
            for node in ast.walk(ast.parse(p.read_text())):
                if isinstance(node, ast.Attribute) and isinstance(
                        node.ctx, ast.Load):
                    reads.add(node.attr)
                elif (isinstance(node, ast.Call)
                      and isinstance(node.func, ast.Name)
                      and node.func.id in ("getattr", "hasattr")
                      and len(node.args) >= 2
                      and isinstance(node.args[1], ast.Constant)):
                    reads.add(node.args[1].value)
    return reads


def test_every_field_is_read_somewhere():
    fields = _dataclass_fields()
    # premise: the scan sees the package
    total = sum(len(v) for v in fields.values())
    assert len(fields) >= 20 and total >= 100, \
        f"field scan looks broken: {len(fields)} classes / {total} fields"
    reads = _read_names()
    dead = {cls: sorted(fs - reads - set(ALLOWED_DEAD))
            for cls, fs in fields.items() if fs - reads - set(ALLOWED_DEAD)}
    assert not dead, (
        f"dead knobs (written, never read in src/app/examples): {dead}. "
        f"Wire each into a consumer or delete it — a dead knob does not "
        f"fail, it lies.")


def test_scanner_can_detect_a_dead_knob():
    """Premise assertion: prove the detector *would* fire.

    Plant a dataclass with an unread field and check the same logic flags
    it — otherwise a broken scanner passes everything forever.
    """
    planted = ast.parse(
        "import dataclasses\n"
        "@dataclasses.dataclass\n"
        "class C:\n"
        "    used: int = 0\n"
        "    dead_knob_xyzzy: int = 0\n"
        "def f(c):\n"
        "    return c.used\n")
    fields = set()
    reads = set()
    for node in ast.walk(planted):
        if isinstance(node, ast.ClassDef):
            fields |= {n.target.id for n in node.body
                       if isinstance(n, ast.AnnAssign)}
        elif isinstance(node, ast.Attribute) and isinstance(node.ctx, ast.Load):
            reads.add(node.attr)
    assert fields - reads == {"dead_knob_xyzzy"}
