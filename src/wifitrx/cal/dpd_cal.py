"""DPD calibration through the TX -> loopback -> RX observation path.

Runs LAST in the sequence: the ILA identification would otherwise learn
residual observation-path impairments (IQ image, DC, delay) into the
predistorter coefficients.  The RX channel filter is opened up during the
capture (wideband observation mode, standard practice for DPD receivers —
the adjacent-channel regrowth must be visible to the identification).

Flow per iteration: transmit reference -> capture -> delay-align ->
gain-normalize -> single-shot ILA fit on the measured pair -> apply.
"""
from __future__ import annotations

import numpy as np

from ..chain.loopback import LoopbackPath, run_loopback
from ..chain.rx import RxChain
from ..chain.tx import TxChain
from ..metrics import aclr, evm
from ..pa.gmp import GMPModel
from ..waveform.ofdm import OFDMWaveform, demodulate_ofdm
from .base import CalResult
from .sync import _fractional_advance, align_delay


def _capture(tx: TxChain, rx: RxChain, path: LoopbackPath,
             x: np.ndarray) -> np.ndarray:
    """Delay-aligned (but not gain-normalized) loopback capture."""
    cap = run_loopback(tx, rx, x, path)
    _, _, info = align_delay(x, cap, max_lag=1024)
    return _fractional_advance(cap, info["lag_total"])


def calibrate_dpd(tx: TxChain, rx: RxChain, wf: OFDMWaveform,
                  path: LoopbackPath | None = None, n_iter: int = 2,
                  order: int = 7, memory_depth: int = 3,
                  drive_scale: float = 0.25, seed: int = 17) -> CalResult:
    """``drive_scale`` sets the digital rms level (unit-power reference times
    drive_scale) so the OFDM peaks stay inside DAC full scale and the PA
    runs at a sane backoff — ILA diverges if driven past saturation."""
    if path is None:
        path = LoopbackPath(atten_db=40.0, delay_ns=6.0)
    fs = tx.fs
    bw = wf.config.bandwidth_hz
    x = wf.x * drive_scale

    # wideband observation mode for the RX channel filter
    lpf_was_enabled = rx.params.lpf.enabled
    rx.params.lpf.enabled = False

    def pa_out_metrics() -> dict:
        y = tx(x)
        g = np.vdot(x, y) / np.vdot(x, x)
        res = evm(demodulate_ofdm(y / g, wf), wf.tx_symbols, equalize="per_tone")
        ac = aclr(y, fs, bw)
        return {"evm_db": res.db,
                "aclr_worst_dbc": max(ac["lower_dbc"], ac["upper_dbc"])}

    before = pa_out_metrics()
    trace = [before["aclr_worst_dbc"]]

    # Iterated indirect learning: fit the post-inverse on (capture/G0 -> u)
    # where u is the ACTUAL predistorted drive of the current iteration and
    # G0 is the composite linear gain frozen at iteration 0 (a drifting
    # normalization would fold gain error into the coefficients).
    dpd_model = None
    g0 = None
    for it in range(n_iter):
        u = x if dpd_model is None else dpd_model(x)
        cap = _capture(tx, rx, path, x)
        if g0 is None:
            g0 = np.vdot(x, cap) / np.vdot(x, x)
        model = GMPModel(order=order, memory_depth=memory_depth)
        model.fit(cap / g0, u)
        dpd_model = model
        tx.dpd = dpd_model
        trace.append(pa_out_metrics()["aclr_worst_dbc"])

    after = pa_out_metrics()
    rx.params.lpf.enabled = lpf_was_enabled
    return CalResult(
        name="dpd",
        estimated={"order": order, "memory_depth": memory_depth},
        corrections={"dpd": "GMP ILA predistorter programmed on TxChain"},
        trace=trace,
        metrics_before=before,
        metrics_after=after,
        passed=(after["aclr_worst_dbc"] < before["aclr_worst_dbc"] - 5.0
                and after["evm_db"] < before["evm_db"]),
    )
