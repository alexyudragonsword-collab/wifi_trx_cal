"""Temperature axis: tempco truth, bypass identity, and the hold study."""
from __future__ import annotations

import numpy as np
import pytest

from wifitrx.cal.sequence import run_full_cal
from wifitrx.chain import LoopbackPath, RxChain, RxParams, TxChain, TxParams
from wifitrx.impairments.analog_filter import TunableLPF
from wifitrx.impairments.iq_imbalance import FreqDepIQImbalance
from wifitrx.link.temp_study import temperature_hold_study
from wifitrx.metrics.irr import lo_leak_dbc
from wifitrx.waveform import OFDMConfig
from wifitrx.waveform.stimuli import single_tone


# ------------------------------------------------------------ tempco truth
def test_zero_tempco_is_temperature_invariant():
    lpf = TunableLPF(fc_nominal_hz=100e6)
    iq = FreqDepIQImbalance(phase_deg=2.0)
    fc25, ph25 = lpf.fc_actual_hz, iq.phase_eff_deg
    lpf.temperature_c = iq.temperature_c = 85.0
    assert lpf.fc_actual_hz == fc25
    assert iq.phase_eff_deg == ph25


def test_lpf_corner_drifts_per_tempco():
    lpf = TunableLPF(fc_nominal_hz=100e6, rc_tempco_per_c=4e-4)
    fc25 = lpf.fc_actual_hz
    lpf.temperature_c = 85.0
    assert lpf.fc_actual_hz == pytest.approx(fc25 * (1 + 4e-4 * 60.0))


def test_iq_phase_drifts_per_tempco():
    iq = FreqDepIQImbalance(phase_deg=1.0, phase_tempco_deg_per_c=0.01)
    iq.temperature_c = -40.0
    assert iq.phase_eff_deg == pytest.approx(1.0 - 0.01 * 65.0)
    # the drift must reach the actual transfer, not just the label
    x = np.exp(1j * 2 * np.pi * 5e6 * np.arange(4096) / 100e6)
    iq0 = FreqDepIQImbalance(phase_deg=1.0 - 0.01 * 65.0)
    assert np.allclose(iq.apply(x, 100e6), iq0.apply(x, 100e6))


def test_lo_leak_drifts_on_the_chain():
    p = TxParams(bandwidth_hz=80e6, lo_leak_dbm=-25.0,
                 lo_leak_tempco_db_per_c=0.05, pa_enabled=False)
    tx = TxChain(p, 320e6)
    tone = single_tone(11e6, tx.fs, 1 << 13, amp=0.25)
    leak25 = lo_leak_dbc(tx(tone), tx.fs)
    tx.set_temperature(85.0)
    leak85 = lo_leak_dbc(tx(tone), tx.fs)
    assert leak85 - leak25 == pytest.approx(0.05 * 60.0, abs=0.3)


def test_set_temperature_reaches_all_tempco_carriers():
    tx = TxChain(TxParams(bandwidth_hz=80e6), 320e6)
    rx = RxChain(RxParams(bandwidth_hz=80e6), 320e6)
    for ch in (tx, rx):
        ch.set_temperature(60.0)
        assert ch.params.lpf.temperature_c == 60.0
        assert ch.params.iq.temperature_c == 60.0


# ------------------------------------------------------------ hold study
@pytest.fixture(scope="module")
def calibrated_pair():
    bw = 80e6
    cfg = OFDMConfig(bandwidth_hz=bw, qam_order=256, n_symbols=4,
                     oversampling=2)
    rng = np.random.default_rng(11)
    txp = TxParams(bandwidth_hz=bw).randomize(rng)
    rxp = RxParams(bandwidth_hz=bw).randomize(rng)
    txp.lpf.fc_nominal_hz = bw / 2 * 1.12
    rxp.lpf.fc_nominal_hz = bw / 2 * 1.12
    # tempcos sized so a 25 degC cal holds the industrial range against
    # the -40 dBc / 50 dB / 2 % specs: the leak null is amplitude-matched
    # at 25 degC, so residual ~ leak * (10^(tempco*dT/20) - 1) — 20
    # mdB/degC over 30 degC leaves ~ -46 dBc on a -25 dBc injected leak;
    # the LPF corner cal may leave up to 1 LSB (2 %) residual, so its
    # drift budget over 35 degC is what's left of the 2 % spec (200
    # ppm/degC * 35 = 0.7 %).  Larger tempcos genuinely break the specs
    # (that is the second test — and 300 ppm/degC on a part calibrated
    # 1 % low really does break the corner spec at -10 degC).
    for p in (txp, rxp):
        p.lpf.rc_tempco_per_c = 2e-4
        p.iq.phase_tempco_deg_per_c = 0.004
    txp.lo_leak_tempco_db_per_c = 0.02
    tx, rx = TxChain(txp, cfg.sample_rate_hz), RxChain(rxp, cfg.sample_rate_hz)
    path = LoopbackPath(atten_db=40.0, delay_ns=6.0)
    results = run_full_cal(tx, rx, cfg, path, with_dpd=False,
                           profile="poweron")
    return tx, rx, path, cfg, results


def test_moderate_tempco_holds_over_industrial_range(calibrated_pair):
    tx, rx, path, cfg, results = calibrated_pair
    out = temperature_hold_study(tx, rx, path, cfg, results,
                                 temps=(-10.0, 25.0, 55.0))
    assert all(r["all_hold"] for r in out["rows"]), out["rows"]
    assert out["expiry"]["hold_min_c"] <= -10.0
    assert out["expiry"]["hold_max_c"] >= 55.0
    # temperatures restored after the study
    assert tx.temperature_c == 25.0 and rx.temperature_c == 25.0
    # the expiry answers "then what": a priced minimal recal plan
    plan = out["expiry"]["recal_plan"]
    assert "tx_lo_leak_loopback" in plan["steps"]
    assert plan["capture_ms"] > 0.0
    assert len(plan["steps"]) < sum(1 for _ in results)


def test_large_tempco_shrinks_the_hold_range(calibrated_pair):
    tx, rx, path, cfg, results = calibrated_pair
    saved = tx.params.lo_leak_tempco_db_per_c
    # premise first: the criterion CAN fail — a huge leak tempco must
    # break the hold verdict, otherwise the study measures nothing.
    # The null is amplitude-matched at 25 degC, so a large drift in
    # EITHER direction breaks it (colder = smaller leak still un-nulls
    # the 25 degC dc_pre).
    tx.params.lo_leak_tempco_db_per_c = 0.6
    try:
        out = temperature_hold_study(tx, rx, path, cfg, results,
                                     temps=(-40.0, 25.0, 85.0))
        cold = next(r for r in out["rows"] if r["temp_c"] == -40.0)
        hot = next(r for r in out["rows"] if r["temp_c"] == 85.0)
        assert not hot["holds"]["lo_leak_dbc"], hot
        assert not cold["holds"]["lo_leak_dbc"], cold
        assert out["expiry"]["hold_min_c"] == 25.0
        assert out["expiry"]["hold_max_c"] == 25.0
    finally:
        tx.params.lo_leak_tempco_db_per_c = saved
