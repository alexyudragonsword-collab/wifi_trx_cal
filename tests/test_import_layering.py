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

SRC = Path(__file__).resolve().parent.parent / "src" / "wifitrx"

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
