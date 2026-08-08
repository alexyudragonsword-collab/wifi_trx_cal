"""B9/B10/B11: the residual spec, the replay cross-check, the README.

The property under test is the one the peer project's harness lost:
**the closure check must be falsifiable**.  Nothing in the closure sum
may be derived from the closure target, so corrupting a shipped number
must break closure — and an honest file must still close.
"""
import json

import numpy as np
import pytest

from wifitrx.cal.base import cal_state_readme, save_cal_state
from wifitrx.cal.residuals import RESIDUAL_SPEC, run_conditions
from wifitrx.cal.sequence import run_full_cal
from wifitrx.chain import LoopbackPath, RxChain, RxParams, TxChain, TxParams
from wifitrx.handoff.inspector import inspect_cal_state
from wifitrx.handoff.replay import replay
from wifitrx.waveform import OFDMConfig

#: cost accounting, not measurements — the one exemption list, mirrored
#: from what CalResult.cost feeds and named here so the anti-drift test
#: below fails loudly when a new metric appears without a spec entry
BOOKKEEPING = {"captures", "samples", "capture_time_ms", "total_captures"}


def _run(bw, qam, with_dpd, seed=3):
    rng = np.random.default_rng(seed)
    txp = TxParams(bandwidth_hz=bw).randomize(rng)
    rxp = RxParams(bandwidth_hz=bw).randomize(rng)
    txp.lpf.fc_nominal_hz = bw / 2 * 1.3
    rxp.lpf.fc_nominal_hz = bw / 2 * 1.12
    cfg = OFDMConfig(bandwidth_hz=bw, qam_order=qam, n_symbols=6,
                     oversampling=4)
    tx = TxChain(txp, cfg.sample_rate_hz)
    rx = RxChain(rxp, cfg.sample_rate_hz)
    results = run_full_cal(tx, rx, cfg, LoopbackPath(atten_db=40.0,
                                                     delay_ns=6.0),
                           with_dpd=with_dpd)
    return cfg, tx, rx, results


@pytest.fixture(scope="module")
def saved_state(tmp_path_factory):
    """One full calibration (with DPD), saved with the current writer."""
    cfg, tx, rx, results = _run(40e6, 256, with_dpd=True)
    out = tmp_path_factory.mktemp("state") / "cal_state.json"
    save_cal_state(out, tx.correction_state(), rx.correction_state(),
                   results, fs_hz=cfg.sample_rate_hz,
                   conditions=run_conditions(cfg, tx, rx, with_dpd=True))
    return out, results


def test_every_measured_metric_has_a_spec_entry(saved_state):
    """Anti-drift guard: a step that starts shipping a new scalar metric
    must give it a specification entry (or consciously extend the
    exemptions here).  This is the check that replaces runtime
    'unspecified' warnings on every file."""
    _, results = saved_state
    for r in results:
        for metric, value in r.metrics_after.items():
            if metric in BOOKKEEPING or not np.isscalar(value):
                continue
            if metric.startswith("dc_dbfs_state"):
                continue          # per-state detail rows; worst is specced
            assert f"{r.name}.{metric}" in RESIDUAL_SPEC, (r.name, metric)


def test_residuals_block_pairs_every_value_with_its_spec(saved_state):
    path, _ = saved_state
    doc = json.loads(path.read_text())
    res = doc["residuals"]
    assert res["values"], "residuals block empty"
    assert set(res["specification"]) == set(res["values"])
    for entry in res["specification"].values():
        for field in ("unit", "meaning", "better", "apply", "role"):
            assert entry.get(field), entry
    for pair in res["duplicates"]:
        assert all(k in res["values"] for k in pair)
    assert "conditions" in doc and "bandwidth_hz" in doc["conditions"]


def test_replay_closes_on_an_honest_file(saved_state):
    path, _ = saved_state
    result = replay(path)
    assert result.verdict == "consistent", result.summary()
    assert abs(result.gap_db) <= 1.0
    # every key accounted for, and no key hit the loud failure bucket
    doc = json.loads(path.read_text())
    assert set(result.accounting) == set(doc["residuals"]["values"])
    assert not [k for k, e in result.accounting.items()
                if e["status"] == "no_recipe"], result.accounting
    # the duplicate pair was dropped by name, not silently
    assert (result.accounting["tx_lo_leak_envdet.lo_leak_dbc"]["status"]
            == "dropped_duplicate")
    # the in-band distortion term dominates and the cal-only row shows it
    assert result.explained_cal_only_db < result.explained_evm_db - 3.0


def test_replay_catches_a_falsified_dominant_term(saved_state, tmp_path):
    """The non-circularity pin.  The peer harness closed to 0.14 dB on a
    file with five falsified residuals because its fallback term was
    solved from the measured EVM; ours must break instead."""
    path, _ = saved_state
    doc = json.loads(path.read_text())
    doc["residuals"]["values"]["dpd.evm_db"] = -60.0   # a much better PA
    bad = tmp_path / "fraud.json"
    bad.write_text(json.dumps(doc))
    result = replay(bad)
    assert result.verdict == "gap", result.summary()
    assert result.gap_db < -1.0
    assert result.unexplained_evm_db is not None


def test_replay_refuses_a_file_it_cannot_check(saved_state, tmp_path):
    path, _ = saved_state
    doc = json.loads(path.read_text())
    doc.pop("conditions")
    legacy = tmp_path / "legacy.json"
    legacy.write_text(json.dumps(doc))
    with pytest.raises(ValueError, match="conditions"):
        replay(legacy)


def test_replay_reports_the_omission_in_a_no_dpd_file(tmp_path):
    """A no-DPD run ships no in-band-distortion entry at all, so the
    residual list cannot explain the measured EVM — the replay must say
    so.  This is the defect class (an *omission*) that per-entry review
    is structurally unable to find, and the reason B9 exists."""
    cfg, tx, rx, results = _run(40e6, 256, with_dpd=False)
    out = tmp_path / "cal_state.json"
    save_cal_state(out, tx.correction_state(), rx.correction_state(),
                   results, fs_hz=cfg.sample_rate_hz,
                   conditions=run_conditions(cfg, tx, rx, with_dpd=False))
    result = replay(out)
    assert result.verdict == "gap", result.summary()
    assert result.gap_db < -1.0          # explains less than measured
    assert result.unexplained_evm_db is not None


def test_readme_is_generated_and_cannot_drift(saved_state):
    path, _ = saved_state
    readme = path.with_name("README.md")
    assert readme.is_file()
    doc = json.loads(path.read_text())
    # regenerating from the JSON reproduces the file byte for byte —
    # the no-drift property is structural, not reviewed
    assert readme.read_text() == cal_state_readme(doc)
    text = readme.read_text()
    assert "final_loopback_evm" in text
    assert "handoff replay" in text
    assert "adc_backoff_db" in text


def test_inspector_flags_residual_spec_mismatch(saved_state):
    path, _ = saved_state
    doc = json.loads(path.read_text())
    # a value with its description deleted -> error; a described key
    # that was never shipped -> warning.  Both derived from the file
    # against itself, so a hand-edited bundle cannot pass unnoticed.
    doc["residuals"]["specification"].pop("dpd.evm_db")
    doc["residuals"]["specification"]["ghost.metric_db"] = {
        "unit": "dB", "meaning": "x", "better": "x", "apply": "x",
        "role": "figure"}
    findings = inspect_cal_state(doc)
    by = {(f["severity"], f["step"]) for f in findings}
    assert ("error", "dpd.evm_db") in by
    assert ("warning", "ghost.metric_db") in by
