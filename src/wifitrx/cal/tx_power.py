"""TX power calibration: closed-loop gain-code table.

Sweeps the digital gain code with an OFDM-like stimulus, measures the true
PA output power through the observation path (here: directly at the PA
output, standing in for the calibrated power detector), and builds the
code -> dBm lookup table plus the inverse (target dBm -> code).
"""
from __future__ import annotations

import numpy as np

from ..chain.tx import TxChain
from ..units import power_dbm
from .base import CalResult


def calibrate_tx_power(tx: TxChain, x_ref: np.ndarray,
                       codes_db: np.ndarray | None = None,
                       target_dbm: float | None = None) -> CalResult:
    """Build the gain-code table; optionally program the code hitting
    ``target_dbm`` average output power."""
    if codes_db is None:
        codes_db = np.arange(-20.0, 6.5, 1.0)
    saved = tx.gain_code_db
    table = []
    for code in codes_db:
        tx.gain_code_db = float(code)
        y = tx(x_ref)
        table.append((float(code), power_dbm(y)))
    tx.gain_code_db = saved

    codes = np.array([c for c, _ in table])
    pouts = np.array([p for _, p in table])
    est = {"table": [list(row) for row in table]}
    metrics_after = {}
    if target_dbm is not None:
        # interpolate on the monotonic section
        code_t = float(np.interp(target_dbm, pouts, codes))
        tx.gain_code_db = code_t
        achieved = power_dbm(tx(x_ref))
        est["target_dbm"] = target_dbm
        est["code"] = code_t
        metrics_after = {"target_dbm": target_dbm, "achieved_dbm": achieved,
                         "error_db": achieved - target_dbm}
    monotonic = bool(np.all(np.diff(pouts) > 0))
    return CalResult(
        name="tx_power",
        estimated=est,
        corrections={"gain_code_db": tx.gain_code_db},
        trace=[list(row) for row in table],
        metrics_before={},
        metrics_after=metrics_after,
        passed=monotonic and (target_dbm is None
                              or abs(metrics_after["error_db"]) < 0.5),
        # np.interp clips silently: a target outside the measured table
        # lands on an end code and reads as a (wrong-power) success
        saturated=None if target_dbm is None else
                  bool(est["code"] <= codes[0] or est["code"] >= codes[-1]),
        spec={} if target_dbm is None else
             {"metric": "error_db", "limit": 0.5, "sense": "abs_max"},
        cost={"captures": len(codes) + (1 if target_dbm is not None else 0),
              "samples": (len(codes) + (1 if target_dbm is not None else 0))
                         * np.asarray(x_ref).size},
    )
