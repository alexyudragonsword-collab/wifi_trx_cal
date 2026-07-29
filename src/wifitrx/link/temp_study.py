"""Temperature hold study: how far does a 25 degC calibration survive?

Calibration corrections are programmed once (factory or power-on) but the
die does not stay at the calibration temperature.  This study moves the
modeled die across temperature with the corrections FROZEN and re-measures
each calibrated spec, answering the production question the saturation
flag only hints at: which corrections hold over the range, which need a
recalibration trigger, and at what temperature the first spec breaks.

Verdicts are judged against the specs EMBEDDED in the CalResult list (the
spec each step was actually calibrated to), the same rule the handoff
inspector follows.  The derived hold range ships as ``expiry`` metadata in
the cal-state JSON so a consumer knows the corrections' validity window.

Observation honesty: lo_leak/IRR/EVM are *measured* through the modeled
observation paths; the LPF corner residual is read from model truth
(a real bench would re-run the tone-ratio measurement) — cheap and exact,
and this study is about drift, not estimator quality.
"""
from __future__ import annotations

import numpy as np

from ..cal.base import CalResult
from ..cal.sequence import agc_for_loopback, tx_evm
from ..cal.tx_iq import measure_tx_rho
from ..chain.loopback import LoopbackPath
from ..chain.rx import RxChain
from ..chain.tx import TxChain
from ..metrics.irr import lo_leak_dbc
from ..waveform.ofdm import OFDMConfig, generate_ofdm
from ..waveform.stimuli import single_tone

CAL_TEMP_C = 25.0


def _limit(results: list[CalResult], name: str, default: float) -> float:
    for r in results:
        if r.name == name and r.spec:
            return float(r.spec["limit"])
    return default


def _fc_err_pct(lpf) -> float:
    return 100.0 * (lpf.fc_actual_hz / lpf.fc_nominal_hz - 1.0)


def temperature_hold_study(tx: TxChain, rx: RxChain, path: LoopbackPath,
                           cfg: OFDMConfig, results: list[CalResult],
                           temps: tuple = (-40.0, -10.0, 25.0, 55.0, 85.0),
                           drive_scale: float = 0.12,
                           n_iq: int = 1 << 14, seed: int = 0) -> dict:
    """Re-measure calibrated specs across ``temps`` with corrections frozen.

    Returns {"rows": [...], "expiry": {...}}; expiry carries the contiguous
    hold range around the calibration temperature for the cal-state JSON.
    """
    lim_leak = _limit(results, "tx_lo_leak_loopback", -40.0)
    lim_irr = _limit(results, "tx_iq", 50.0)
    lim_fc_tx = _limit(results, "tx_lpf_corner", 2.0)
    lim_fc_rx = _limit(results, "rx_lpf_corner", 2.0)
    lim_txevm = None
    for r in results:
        if r.name == "final_loopback_evm" and r.spec:
            lim_txevm = float(r.spec["limit"])

    t_tx0, t_rx0 = tx.temperature_c, rx.temperature_c
    try:
        tx.set_temperature(CAL_TEMP_C)
        rx.set_temperature(CAL_TEMP_C)
        ref_txevm = tx_evm(tx, cfg, drive_scale=drive_scale)
        # no embedded EVM spec (e.g. no-DPD flow): hold = within 2 dB of
        # the calibrated-temperature value
        evm_lim = lim_txevm if lim_txevm is not None else ref_txevm + 2.0

        rows = []
        for t in temps:
            tx.set_temperature(t)
            rx.set_temperature(t)

            tone = single_tone(11e6, tx.fs, 1 << 13, amp=0.25)
            leak = lo_leak_dbc(tx(tone), tx.fs)

            wf = generate_ofdm(cfg)
            agc_for_loopback(tx, rx, path, wf.x * 0.25)
            iq_path = LoopbackPath(atten_db=path.atten_db,
                                   delay_ns=path.delay_ns,
                                   rx_lo_offset_hz=5.1e6)
            _, rho = measure_tx_rho(tx, rx, iq_path, n=n_iq, n_tones=8,
                                    seed=seed)
            irr_min = float(np.min(-20.0 * np.log10(
                np.maximum(np.abs(rho), 1e-12))))

            te = tx_evm(tx, cfg, drive_scale=drive_scale)
            fc_tx = _fc_err_pct(tx.params.lpf)
            fc_rx = _fc_err_pct(rx.params.lpf)

            holds = {
                "lo_leak_dbc": leak <= lim_leak,
                "irr_min_db": irr_min >= lim_irr,
                "tx_fc_err_pct": abs(fc_tx) <= lim_fc_tx,
                "rx_fc_err_pct": abs(fc_rx) <= lim_fc_rx,
                "tx_evm_db": te <= evm_lim,
            }
            rows.append({
                "temp_c": float(t), "lo_leak_dbc": leak,
                "irr_min_db": irr_min, "tx_evm_db": te,
                "tx_fc_err_pct": fc_tx, "rx_fc_err_pct": fc_rx,
                "holds": holds, "all_hold": all(holds.values()),
            })
    finally:
        tx.set_temperature(t_tx0)
        rx.set_temperature(t_rx0)

    # contiguous hold range around the calibration temperature: walking
    # outward stops at the first failing point on each side — a pass
    # beyond a failure does not extend validity
    order = sorted(rows, key=lambda r: r["temp_c"])
    hold_min = hold_max = CAL_TEMP_C
    for r in [r for r in order if r["temp_c"] <= CAL_TEMP_C][::-1]:
        if not r["all_hold"]:
            break
        hold_min = r["temp_c"]
    for r in [r for r in order if r["temp_c"] >= CAL_TEMP_C]:
        if not r["all_hold"]:
            break
        hold_max = r["temp_c"]

    expiry = {
        "calibrated_at_c": CAL_TEMP_C,
        "hold_min_c": hold_min,
        "hold_max_c": hold_max,
        "criteria": {"lo_leak_dbc_max": lim_leak, "irr_min_db_min": lim_irr,
                     "tx_fc_err_pct_abs_max": lim_fc_tx,
                     "rx_fc_err_pct_abs_max": lim_fc_rx,
                     "tx_evm_db_max": evm_lim},
        "note": "corrections frozen at the calibration values; outside the "
                "hold range a recalibration (or tracking loop) is required",
    }
    return {"rows": rows, "expiry": expiry}
