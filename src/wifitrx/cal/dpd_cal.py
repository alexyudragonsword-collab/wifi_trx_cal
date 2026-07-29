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
             x: np.ndarray, n_warmup: int = 512) -> np.ndarray:
    """Delay-aligned loopback capture with a cyclic warm-up prefix that
    settles the IIR baseband filters (not gain-normalized)."""
    xp = np.concatenate([x[-n_warmup:], x])
    cap = run_loopback(tx, rx, xp, path)
    _, _, info = align_delay(xp, cap, max_lag=1024)
    cap = _fractional_advance(cap, info["lag_total"])
    return cap[n_warmup:]


def calibrate_dpd(tx: TxChain, rx: RxChain, wf: OFDMWaveform,
                  path: LoopbackPath | None = None, n_iter: int = 2,
                  order: int = 7, memory_depth: int = 5,
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

    # AGC for the actual coupled level (the observation ADC must not clip)
    from ..units import power_dbm
    rx.agc(power_dbm(tx(x)) - path.atten_db)

    def pa_out_metrics() -> dict:
        y = tx(x)
        g = np.vdot(x, y) / np.vdot(x, x)
        res = evm(demodulate_ofdm(y / g, wf), wf.tx_symbols, equalize="per_tone")
        if fs >= 3.0 * bw:
            ac = aclr(y, fs, bw)
            ac_worst = max(ac["lower_dbc"], ac["upper_dbc"])
        else:
            ac_worst = float("nan")  # adjacent channel outside Nyquist
        return {"evm_db": res.db, "aclr_worst_dbc": ac_worst}

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
        # ACLR may be phase-noise-limited rather than distortion-limited, so
        # the pass gate is EVM-driven with ACLR required not to regress
        # (ACLR is NaN when fs < 3*bw and then only the EVM gate applies).
        # A PA already linear enough (post EVM <= -40 dB, beyond MCS13
        # needs) passes even without a 3 dB improvement to show.
        passed=((after["evm_db"] < before["evm_db"] - 3.0
                 or after["evm_db"] <= -40.0)
                and not (after["aclr_worst_dbc"]
                         > before["aclr_worst_dbc"] + 1.0)),
        cost={"captures": n_iter, "samples": n_iter * (x.size + 512)},
    )
