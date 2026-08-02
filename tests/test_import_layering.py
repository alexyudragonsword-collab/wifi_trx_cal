"""The package layering, enforced by parsing every import in src/wifitrx.

ALLOWED is the complete adjacency table: package (or top-level module) ->
the wifitrx packages it may import from, with the reason each edge exists.
An import that is not in the table fails this test — adding a new edge is
allowed, but it has to be added *here*, with a reason, so layering decay
becomes a reviewed decision instead of an accident.

(Idea ported from a sibling project's test_import_layering.py, where the
table caught dependency creep that otherwise only shows up as an import
cycle months later.)
"""
from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src" / "wifitrx"

# unit/dsp are leaf utility modules; impairments sits on them; chains
# compose impairments + PA; cal drives chains and reads metrics; handoff /
# link / report consume cal results.  No package may import upward.
ALLOWED = {
    "units": set(),            # leaf: dB/power conversions only
    "dsp": set(),              # leaf: filters/resampling only
    "provenance": set(),       # leaf: git/run stamping for artifacts
    "waveform": {"units"},     # OFDM/preamble generation
    "metrics": {"waveform"},   # EVM/PSD need OFDM demod
    "pa": {"units"},           # PA models are self-contained
    "dpd": {"pa"},             # predistorter trains against PA models
    "impairments": {"dsp", "units", "waveform"},
    "circuit_import": {"impairments"},  # CSV -> impairment objects
    "chain": {"dsp", "impairments", "pa", "units"},
    "cal": {"chain", "dpd", "metrics", "pa", "provenance", "units",
            "waveform"},
    # link studies (temp hold, sensitivity) measure EVM/leak via metrics
    "link": {"cal", "chain", "impairments", "metrics", "units", "waveform"},
    "handoff": {"cal", "chain", "metrics", "provenance", "units",
                "waveform"},
    "deploy": {"chain"},       # fixed-point export of programmed state
    # report reads link.spur_planning.lock_time_s for the power-on budget
    "report": {"cal", "link", "metrics", "provenance"},
    "plotting": {"metrics"},
    "__init__": set(),         # top-level package init re-exports nothing
}


def _top_pkg(rel: Path) -> str:
    return rel.parts[0] if len(rel.parts) > 1 else rel.stem


def _edges() -> set[tuple[str, str]]:
    edges = set()
    for p in sorted(SRC.rglob("*.py")):
        rel = p.relative_to(SRC)
        src_pkg = _top_pkg(rel)
        for node in ast.walk(ast.parse(p.read_text())):
            if isinstance(node, ast.ImportFrom):
                if node.level > 0:
                    base = list(rel.parts[:-1])
                    up = node.level - 1
                    base = base[: len(base) - up] if up else base
                    target = base + (node.module or "").split(".")
                    if target and target[0]:
                        edges.add((src_pkg, target[0]))
                elif node.module and node.module.split(".")[0] == "wifitrx":
                    parts = node.module.split(".")
                    if len(parts) > 1:
                        edges.add((src_pkg, parts[1]))
            elif isinstance(node, ast.Import):
                for a in node.names:
                    if a.name.startswith("wifitrx."):
                        edges.add((src_pkg, a.name.split(".")[1]))
    return {(s, t) for s, t in edges if s != t}


def test_every_import_edge_is_declared():
    edges = _edges()
    # premise: the parser actually sees the package, so an empty scan
    # cannot pass vacuously
    assert len(edges) >= 10, f"import scan looks broken: {sorted(edges)}"
    undeclared = {(s, t) for s, t in edges
                  if s not in ALLOWED or t not in ALLOWED[s]}
    assert not undeclared, (
        f"undeclared import edges {sorted(undeclared)}: add each to ALLOWED "
        f"in {__file__} with a reason, or remove the import")


def test_every_package_is_declared():
    pkgs = {_top_pkg(p.relative_to(SRC)) for p in SRC.rglob("*.py")}
    missing = pkgs - set(ALLOWED)
    assert not missing, f"new packages must be added to ALLOWED: {missing}"


def test_allowed_table_is_acyclic():
    # the table itself must describe a DAG, otherwise "no upward imports"
    # is meaningless
    table = {k: set(v) & set(ALLOWED) for k, v in ALLOWED.items()}
    remaining = dict(table)
    while remaining:
        leaves = [k for k, v in remaining.items() if not v]
        assert leaves, f"cycle among {sorted(remaining)}"
        for leaf in leaves:
            remaining.pop(leaf)
            for v in remaining.values():
                v.discard(leaf)


# ---------------------------------------------------------------- reach
# Modules nobody imports are a different decay class from a bad edge:
# they still parse, still look maintained, and their docstrings keep
# making claims.  cal/loops.py sat here for the project's whole life
# asserting "convergence time constants asserted x3 in tests" — true of
# the sibling repo it was vendored from, false here.  A module that no
# test, example or tool can reach is either dead or untested; both need
# a decision, not silence.
UNREACHED_OK = {
    "wifitrx.plotting",         # figure helpers for notebook/ad-hoc use
    "wifitrx.handoff.__main__",  # CLI entry: exercised as a subprocess
}

ENTRY_DIRS = ("tests", "examples", "tools", "app")


def _module_name(p: Path) -> str:
    rel = p.relative_to(SRC).with_suffix("")
    # note the parens: the top-level __init__ must become "wifitrx", not
    # "wifitrx.__init__"
    return ("wifitrx." + ".".join(rel.parts)).replace(".__init__", "")


def _wifitrx_imports(path: Path, pkg: str) -> set[str]:
    out: set[str] = set()
    for n in ast.walk(ast.parse(path.read_text())):
        if isinstance(n, ast.ImportFrom):
            base = n.module or ""
            if n.level:                      # relative import
                parts = pkg.split(".")
                stem = ".".join(parts[:len(parts) - n.level + 1])
                base = f"{stem}.{base}" if base else stem
            if base.startswith("wifitrx"):
                out.add(base)
                out.update(f"{base}.{a.name}" for a in n.names)
        elif isinstance(n, ast.Import):
            out.update(a.name for a in n.names if a.name.startswith("wifitrx"))
    return out


def test_every_module_is_reachable_from_an_entry_point():
    mods = {_module_name(p): p for p in SRC.rglob("*.py")
            if "__pycache__" not in str(p)}
    graph = {m: _wifitrx_imports(p, m if p.name == "__init__.py"
                                 else m.rsplit(".", 1)[0])
             for m, p in mods.items()}
    queue = []
    for d in ENTRY_DIRS:
        for p in (ROOT / d).rglob("*.py"):
            if "__pycache__" not in str(p):
                queue.extend(_wifitrx_imports(p, "entry"))
    assert len(queue) >= 20, "import scan looks broken"
    seen: set[str] = set()
    while queue:
        m = queue.pop()
        if m in seen:
            continue
        seen.add(m)
        queue.extend(graph.get(m, ()))
    # importing wifitrx.cal.sequence executes wifitrx/cal/__init__.py, so
    # a package counts as reached once any of its submodules is
    for m in list(seen):
        parts = m.split(".")
        seen.update(".".join(parts[:i]) for i in range(1, len(parts)))
    unreached = {m for m in mods if m not in seen} - UNREACHED_OK
    assert not unreached, (
        f"no test, example or tool reaches {sorted(unreached)}: give each a "
        f"caller, a test, or delete it — or excuse it in UNREACHED_OK with a "
        f"reason")
