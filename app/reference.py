# Declarative reference-content registry, same shape as specs.py: the
# page renders whatever is listed here and decides nothing itself.
"""Reference material for the workbench: block diagrams and the tables
that describe the calibration sequence and the impairment model.

Same content as the tutorial's chapters 3/5, and derived from the same
places, so the two cannot disagree:

- block diagrams come from ``assets/schematics/*.svg``, rendered from
  ``tools/tutorial/schematics.py`` by ``tools/build_assets.py`` (the GUI
  must not import schemdraw — it is a build-time extra, absent from the
  Windows exe);
- the sequence, its dependency graph and the edge reasons come from
  ``wifitrx.cal.reference``, i.e. from ``cal/deps.py``;
- the impairment and AGC tables come from the parameter dataclasses.

Two views need numbers that only exist once a calibration has run (each
step's acceptance spec, and the capture cost).  Those take the results
of the session's last run and read as an em dash before there is one —
nothing here is a stored constant.
"""
from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

DASH = "—"


@dataclass(frozen=True)
class RefEntry:
    key: str
    group: str
    title: str
    # exactly one of these: svg() -> SVG text, or table(results) ->
    # (columns, rows).  ``results`` is the last run's CalResult list, or
    # None when no calibration has run in this session.
    svg: Callable[[], str] | None = None
    table: Callable[[object], tuple] | None = None
    note: str = ""


def asset_path(name: str) -> Path:
    """assets/<name>, whether running from source or a frozen exe
    (same resolution as main.py's window icon)."""
    base = Path(getattr(sys, "_MEIPASS",
                        Path(__file__).resolve().parent.parent))
    return base / "assets" / name


def _schematic(name: str) -> Callable[[], str]:
    def build() -> str:
        return asset_path(f"schematics/{name}.svg").read_text()
    return build


# ------------------------------------------------------------- tables
def _specs_by_name(results) -> dict:
    """step name -> its acceptance spec, from a finished run."""
    out = {}
    for r in results or ():
        name = r["name"] if isinstance(r, dict) else r.name
        spec = r.get("spec") if isinstance(r, dict) else r.spec
        if spec:
            out[name] = spec
    return out


def _dependency_graph() -> str:
    from wifitrx.cal.reference import dependency_graph_svg
    return dependency_graph_svg()


def order_table(results):
    from wifitrx.cal.reference import calibration_order

    cols = ["#", "step", "prerequisites", "acceptance spec"]
    rows = [[str(r["n"]), r["step"], r["requires"], r["spec"]]
            for r in calibration_order(specs_by_name=_specs_by_name(results))]
    return cols, rows


def edge_table(results):
    from wifitrx.cal.reference import dependency_edges

    cols = ["#", "edge", "physical reason"]
    return cols, [[str(r["n"]), r["edge"], r["reason"]]
                  for r in dependency_edges()]


def budget_table(results):
    from wifitrx.cal.reference import capture_cost_rows

    cols = ["step", "captures", "samples"]
    rows = [[r["step"], r["captures"], r["samples"]]
            for r in capture_cost_rows(results or ())]
    return cols, rows


def agc_table(results):
    from wifitrx.chain.agc import CAL_OBSERVATION_STATE, DEFAULT_LNA_STATES

    cols = ["state", "gain [dB]", "NF [dB]", "IIP3 [dBm]",
            "hand-over above [dBm]", "boundary IM3 [dBc]"]
    rows = []
    for i, st in enumerate(DEFAULT_LNA_STATES):
        pinned = "  (cal observation)" if i == CAL_OBSERVATION_STATE else ""
        rows.append([f"{i}{pinned}", f"{st.gain_db:g}", f"{st.nf_db:g}",
                     f"{st.iip3_dbm:g}", f"{st.max_input_dbm:g}",
                     f"{2 * (st.iip3_dbm - st.max_input_dbm):.0f}"])
    return cols, rows


def _flatten(prefix, value, out):
    if isinstance(value, dict):
        for k, v in value.items():
            _flatten(f"{prefix}.{k}" if prefix else k, v, out)
    elif isinstance(value, (tuple, list)):
        for i, v in enumerate(value):
            _flatten(f"{prefix}[{i}]", v, out)
    else:
        out[prefix] = value


def _scalar(v):
    """The magnitude to tabulate, or None for a non-numeric field."""
    if isinstance(v, bool):
        return None
    if isinstance(v, complex):
        return abs(v)
    return float(v) if isinstance(v, (int, float)) else None


def _impairment_rows(params_cls, n_seeds: int = 64):
    """Every knob ``randomize()`` actually varies, with its spread.

    The spread is measured, not documented: randomize() is the process
    sampler the Monte-Carlo studies use, so min…max over N seeds is the
    real corner range.  Parameter names carry their own unit; complex
    entries (per-state DC offsets) are tabulated as magnitudes.  Fixed
    configuration (LO frequency, tempcos, tuning codes) is deliberately
    absent — it does not vary with the process draw.
    """
    import numpy as np

    default = {}
    _flatten("", params_cls().injected(), default)
    samples: dict[str, list] = {}
    for seed in range(n_seeds):
        flat = {}
        _flatten("", params_cls(seed=seed).randomize(
            np.random.default_rng(seed)).injected(), flat)
        for k, v in flat.items():
            s = _scalar(v)
            if s is not None:
                samples.setdefault(k, []).append(s)

    rows = []
    for key, vals in samples.items():
        if max(vals) == min(vals):
            continue                      # not a process knob
        d = _scalar(default.get(key))
        rows.append([key, DASH if d is None else f"{d:.4g}",
                     f"{min(vals):.4g} … {max(vals):.4g}"])
    return rows


def tx_impairment_table(results):
    from wifitrx.chain import TxParams
    return (["parameter", "default", "randomize() spread"],
            _impairment_rows(TxParams))


def rx_impairment_table(results):
    from wifitrx.chain import RxParams
    return (["parameter", "default", "randomize() spread"],
            _impairment_rows(RxParams))


# ------------------------------------------------------------ registry
DIAGRAMS = "Block diagrams"
CALIBRATION = "Calibration reference"
MODEL = "Model parameters"

ALL_REFERENCE: tuple[RefEntry, ...] = (
    RefEntry("arch", DIAGRAMS, "Transceiver architecture",
             svg=_schematic("architecture"),
             note="Direct-conversion IQ transceiver: RX row on top, TX row "
                  "below out of the DBB, shared LO generation between them, "
                  "and the two observation paths (Pdet, switched loopback "
                  "attenuator) off the coupler."),
    RefEntry("envdet", DIAGRAMS, "Envelope-detector observation path",
             svg=_schematic("envdet_path"),
             note="The RX-independent square-law path used by the TX LO-leak "
                  "coarse cal and the TX LPF corner cal."),
    RefEntry("loopback", DIAGRAMS, "Loopback with RX-LO offset",
             svg=_schematic("loopback_offset"),
             note="Offsetting the RX LO by df moves the TX carrier leak off "
                  "DC, separating it from the receiver's own DC in the FFT."),
    RefEntry("ila", DIAGRAMS, "DPD indirect learning",
             svg=_schematic("ila_loop"),
             note="The postinverse is fitted on captured PA output and then "
                  "copied into the predistorter."),
    RefEntry("order", CALIBRATION, "Calibration sequence",
             table=order_table,
             note="Steps with no prerequisites are not ordered among "
                  "themselves. The acceptance column fills in after a "
                  "calibration analysis runs in this session."),
    RefEntry("depgraph", CALIBRATION, "Ordering constraints",
             svg=_dependency_graph,
             note="Columns run left to right; steps inside a column have no "
                  "dependency on each other. The number on a line indexes "
                  "the reason table."),
    RefEntry("edges", CALIBRATION, "Why the order is what it is",
             table=edge_table,
             note="A mis-ordered calibration does not fail — it converges on "
                  "the wrong answer. Each edge carries the physical reason "
                  "declared in cal/deps.py."),
    RefEntry("budget", CALIBRATION, "Capture cost",
             table=budget_table,
             note="Capture count and sample count per step, from this "
                  "session's last calibration run (time = samples / fs, DSP "
                  "excluded). Run a calibration analysis to populate."),
    RefEntry("agc", MODEL, "RX gain-state ladder",
             table=agc_table,
             note="Boundary IM3 is 2*(IIP3 - hand-over level): the "
                  "third-order penalty at the top of each state's window."),
    RefEntry("tx_params", MODEL, "TX impairment parameters",
             table=tx_impairment_table,
             note="Default value and the spread randomize() produces over 64 "
                  "process seeds."),
    RefEntry("rx_params", MODEL, "RX impairment parameters",
             table=rx_impairment_table,
             note="Default value and the spread randomize() produces over 64 "
                  "process seeds."),
)
