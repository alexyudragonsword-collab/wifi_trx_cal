"""Calibration result/state containers.

Every calibration follows the inject-truth -> estimate -> correct -> verify
pattern (adc_toolbox app/tiadc_model.py): the estimator returns a
``CalResult`` carrying the estimated parameters, the applied correction,
a convergence trace and before/after metrics; the programmed correction
state of both chains serializes to JSON for the comm-engineer handoff.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class CalResult:
    name: str
    estimated: dict = field(default_factory=dict)
    corrections: dict = field(default_factory=dict)
    trace: list = field(default_factory=list)
    metrics_before: dict = field(default_factory=dict)
    metrics_after: dict = field(default_factory=dict)
    passed: bool | None = None
    # Independent fact from ``passed``: a trim/tuning code landed on its
    # range limit.  Met-spec-with-a-railed-trim is a *margin* problem —
    # failing it would reject a good part, ignoring it hides that there is
    # no range left for temperature or ageing.
    saturated: bool | None = None
    # Acceptance spec in force when this step ran, e.g.
    # {"metric": "irr_db", "limit": 50.0, "sense": "min"} (sense: "min"
    # value >= limit, "max" value <= limit, "abs_max" |value| <= limit).
    # Travels with the result so an external consumer checks the bundle
    # against the spec it was calibrated to, not a later library's table.
    spec: dict = field(default_factory=dict)
    notes: str = ""
    # capture cost: {"captures": n, "samples": total_samples} — the raw
    # material for the calibration time budget (time = samples / fs)
    cost: dict = field(default_factory=dict)
    # bulky raw data for report figures (waveforms, symbol arrays);
    # deliberately NOT serialized by summary()
    artifacts: dict = field(default_factory=dict)

    def capture_time_s(self, fs: float) -> float:
        return float(self.cost.get("samples", 0)) / fs if fs > 0 else 0.0

    def summary(self) -> dict:
        return {
            "name": self.name,
            "estimated": _jsonable(self.estimated),
            "corrections": _jsonable(self.corrections),
            "metrics_before": _jsonable(self.metrics_before),
            "metrics_after": _jsonable(self.metrics_after),
            "passed": None if self.passed is None else bool(self.passed),
            "saturated": None if self.saturated is None
                         else bool(self.saturated),
            "spec": _jsonable(self.spec),
            # what the step cost to measure: the recipient is a
            # production-test audience, and a bundle that states what it
            # measured but not what the measurement cost cannot be
            # budgeted against a tester's time
            "cost": _jsonable(self.cost),
            "notes": self.notes,
        }


def _jsonable(obj: Any) -> Any:
    import numpy as np
    if isinstance(obj, dict):
        return {k: _jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_jsonable(v) for v in obj]
    if isinstance(obj, complex):
        return {"re": obj.real, "im": obj.imag}
    if isinstance(obj, np.ndarray):
        if np.iscomplexobj(obj):
            return {"re": obj.real.tolist(), "im": obj.imag.tolist()}
        return obj.tolist()
    if isinstance(obj, (np.floating, np.integer, np.bool_)):
        return obj.item()
    return obj


def save_cal_state(path: str | Path, tx_state: dict, rx_state: dict,
                   results: list[CalResult] | None = None,
                   expiry: dict | None = None,
                   fs_hz: float | None = None,
                   conditions: dict | None = None) -> None:
    """Persist the full correction state (and optional result summaries).

    ``expiry``: validity metadata for the corrections (e.g. the measured
    temperature hold range from ``link.temp_study``) — corrections are not
    forever, and the file should say so.

    ``fs_hz``: the sample rate the steps were captured at.  Each step
    reports its cost in samples; without the rate the recipient cannot
    turn that into tester time, which is the only unit it is useful in.

    ``conditions``: everything a consumer needs to reproduce the
    measurement context from the file alone — bandwidth/QAM/symbol
    count/seed of the scoring waveform, and the chain constants some
    ``apply`` recipes convert through (``adc_backoff_db``).  Without the
    waveform recipe the replay harness cannot regenerate the stimulus,
    so the residuals cannot be checked against the file's own EVM.

    When ``results`` are given, the file also carries a flat
    ``residuals`` block: each specced ``step.metric`` beside its own
    specification (unit / meaning / better / apply / role), so the
    number and the instruction for consuming it cannot travel apart.
    """
    from ..provenance import provenance
    from .residuals import extract_residuals
    summaries = [r.summary() for r in (results or [])]
    doc = {
        "format": "wifitrx-cal-state-v1",
        "tx": tx_state,
        "rx": rx_state,
        "results": summaries,
        "provenance": provenance(),
    }
    if summaries:
        doc["residuals"] = extract_residuals(summaries)
    if fs_hz:
        doc["fs_hz"] = float(fs_hz)
    if conditions:
        doc["conditions"] = _jsonable(conditions)
    if expiry:
        doc["expiry"] = _jsonable(expiry)
    Path(path).write_text(json.dumps(doc, indent=2))
    readme = Path(path).with_name("README.md")
    readme.write_text(cal_state_readme(doc))


def cal_state_readme(doc: dict) -> str:
    """The state file's own README, rendered from the file it sits beside.

    Generated rather than written, so it cannot drift from the JSON — a
    hand-written handoff note that disagrees with the data next to it is
    worse than no note.  Everything here is derived from ``doc``; adding
    prose that is not in the file would recreate the drift this exists
    to remove.
    """
    cond = doc.get("conditions") or {}
    results = doc.get("results") or []
    res = doc.get("residuals") or {}
    values = res.get("values") or {}
    spec = res.get("specification") or {}
    prov = doc.get("provenance") or {}

    lines = [
        "# wifitrx calibration state: handoff",
        "",
        "This directory's `cal_state.json` is the deliverable: every "
        "digital correction plus the analog tuning codes, the per-step "
        "verdicts against the acceptance specs in force when they ran, "
        "and the residual figures a link simulation consumes.",
        "",
    ]
    ident = [f"format `{doc.get('format')}`"]
    if cond.get("bandwidth_hz"):
        ident.append(f"{cond['bandwidth_hz'] / 1e6:g} MHz")
    if cond.get("qam_order"):
        ident.append(f"{cond['qam_order']}-QAM")
    if doc.get("fs_hz"):
        ident.append(f"fs {doc['fs_hz'] / 1e6:g} MS/s")
    if prov.get("version"):
        ident.append(f"wifitrx {prov['version']}")
    lines += [" · ".join(ident), ""]

    lines += [
        "## How to consume it",
        "",
        "```bash",
        "python -m wifitrx.handoff inspect cal_state.json   # verdicts, "
        "stdlib-only",
        "python -m wifitrx.handoff replay  cal_state.json   # residuals "
        "applied literally vs the file's own EVM",
        "```",
        "",
        "To restore this exact part in the model:",
        "",
        "```python",
        "from wifitrx.cal.base import load_cal_state",
        "tx_state, rx_state = load_cal_state('cal_state.json')",
        "tx.load_correction_state(tx_state)",
        "rx.load_correction_state(rx_state)",
        "# analog tuning codes travel with the params: rerun the two",
        "# cheap corner searches (see wifitrx.handoff.runner)",
        "```",
        "",
    ]

    if cond:
        lines += [
            "## Measurement conditions",
            "",
            "Everything below changes the numbers; a consumer who cannot "
            "state these cannot reproduce them.",
            "",
        ]
        lines += [f"* `{k}` = {v}" for k, v in sorted(cond.items())]
        lines.append("")

    if results:
        lines += [
            "## Steps",
            "",
            "| # | step | passed | trim railed | spec |",
            "|---|---|---|---|---|",
        ]
        for i, r in enumerate(results, 1):
            s = r.get("spec") or {}
            spec_txt = (f"{s.get('metric')} {s.get('sense', '')} "
                        f"{s.get('limit')}" if s else "—")
            lines.append(
                f"| {i} | `{r.get('name')}` | "
                f"{_verdict(r.get('passed'))} | "
                f"{_verdict(r.get('saturated'))} | {spec_txt} |")
        lines.append("")

    if values:
        lines += [
            "## Residuals",
            "",
            "Each figure ships with its own specification in the JSON "
            "(`residuals.specification`): unit, meaning, whether larger "
            "or smaller is better, and **the recipe for injecting it "
            "into a link simulation** (`apply`). Read that rather than "
            "inferring from the names — an image-rejection figure "
            "applied as a gain imbalance does not give the same "
            "constellation as the same dB applied as a quadrature "
            "error. `role` says how each key is meant to be consumed: "
            "`impairment` entries are injectable, `figure` and "
            "`condition` entries are context, `total` entries are "
            "measured wholes and must never be re-injected.",
            "",
            "| key | value | unit | better | role |",
            "|---|---|---|---|---|",
        ]
        for key in sorted(values):
            entry = spec.get(key, {})
            lines.append(
                f"| `{key}` | {_fmt(values[key])} | "
                f"{entry.get('unit', '')} | {entry.get('better', '')} | "
                f"{entry.get('role', '')} |")
        lines.append("")
        dups = res.get("duplicates") or []
        if dups:
            lines += ["Pairs describing one physical quantity measured "
                      "two ways — apply at most one of each:", ""]
            lines += [f"* `{a}` / `{b}` (keep the second)"
                      for a, b in dups]
            lines.append("")

    if doc.get("expiry"):
        lines += [
            "## Validity",
            "",
            "Corrections are not forever. The `expiry` block records "
            "the measured hold window and the minimal recalibration "
            "plan:",
            "",
        ]
        lines += [f"* `{k}` = {v}"
                  for k, v in sorted(doc["expiry"].items())]
        lines.append("")

    return "\n".join(lines) + "\n"


def _verdict(flag) -> str:
    return "—" if flag is None else ("yes" if flag else "no")


def _fmt(value) -> str:
    if isinstance(value, float):
        return f"{value:.4g}"
    if isinstance(value, list):
        return f"[{len(value)} entries]"
    return str(value)


def load_cal_state(path: str | Path) -> tuple[dict, dict]:
    doc = json.loads(Path(path).read_text())
    if doc.get("format") != "wifitrx-cal-state-v1":
        raise ValueError("unknown cal-state format")
    return doc["tx"], doc["rx"]
