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
                   fs_hz: float | None = None) -> None:
    """Persist the full correction state (and optional result summaries).

    ``expiry``: validity metadata for the corrections (e.g. the measured
    temperature hold range from ``link.temp_study``) — corrections are not
    forever, and the file should say so.

    ``fs_hz``: the sample rate the steps were captured at.  Each step
    reports its cost in samples; without the rate the recipient cannot
    turn that into tester time, which is the only unit it is useful in.
    """
    from ..provenance import provenance
    doc = {
        "format": "wifitrx-cal-state-v1",
        "tx": tx_state,
        "rx": rx_state,
        "results": [r.summary() for r in (results or [])],
        "provenance": provenance(),
    }
    if fs_hz:
        doc["fs_hz"] = float(fs_hz)
    if expiry:
        doc["expiry"] = _jsonable(expiry)
    Path(path).write_text(json.dumps(doc, indent=2))


def load_cal_state(path: str | Path) -> tuple[dict, dict]:
    doc = json.loads(Path(path).read_text())
    if doc.get("format") != "wifitrx-cal-state-v1":
        raise ValueError("unknown cal-state format")
    return doc["tx"], doc["rx"]
