"""TX LO leakage (carrier leakage) calibration.

Two observation paths, both implemented:

(a) ``calibrate_tx_lo_leak_envdet`` — RX-independent bootstrap.  Transmit a
    single baseband tone at f0; in the square-law detector output the LO
    leak beats against the tone producing a line at f0 whose power is
    proportional to |leak|^2.  The beat power is a quadratic bowl in the
    digital DC pre-subtraction (dc_pre), so each axis is solved with a
    three-point parabolic fit, iterated for the residual.

(b) ``calibrate_tx_lo_leak_loopback`` — FFT DC-bin refinement through the
    RX (run after RX DC cal, with an RX-LO offset so the TX carrier lands
    on a nonzero bin, separated from residual RX DC).  A known digital DC
    pilot measures the complex gain from dc_pre to the leak bin, then one
    correction step cancels the measured leak.
"""
from __future__ import annotations

import numpy as np

from ..chain.loopback import EnvelopeDetector, LoopbackPath, run_loopback
from ..chain.rx import RxChain
from ..chain.tx import TxChain
from ..metrics.irr import lo_leak_dbc
from ..waveform.stimuli import bin_value, single_tone
from .base import CalResult


def _beat_power(tx: TxChain, det: EnvelopeDetector, x: np.ndarray,
                f0: float) -> float:
    y = tx(x)
    v = det.measure(y, tx.fs)
    return abs(bin_value(v.astype(complex), f0, tx.fs)) ** 2


def calibrate_tx_lo_leak_envdet(tx: TxChain, det: EnvelopeDetector | None = None,
                                n: int = 1 << 13, f0: float = 11e6,
                                n_iter: int = 3, delta: float = 0.02) -> CalResult:
    if det is None:
        det = EnvelopeDetector(enabled_adc=False)
    x = single_tone(f0, tx.fs, n, amp=0.25)
    before_dbc = lo_leak_dbc(tx(x), tx.fs)
    trace = []

    for it in range(n_iter):
        for axis in (1.0, 1j):
            p_m = _beat_power(tx, det, x, f0)
            base = tx.dc_pre
            tx.dc_pre = base + delta * axis
            p_p = _beat_power(tx, det, x, f0)
            tx.dc_pre = base - delta * axis
            p_n = _beat_power(tx, det, x, f0)
            # parabola vertex: step = -delta*(p_p - p_n) / (2*(p_p - 2 p_m + p_n))
            denom = p_p - 2 * p_m + p_n
            step = 0.0 if denom <= 0 else -delta * (p_p - p_n) / (2 * denom)
            step = float(np.clip(step, -5 * delta, 5 * delta))
            tx.dc_pre = base + step * axis
            trace.append(lo_leak_dbc(tx(x), tx.fs))
        delta *= 0.3

    after_dbc = lo_leak_dbc(tx(x), tx.fs)
    return CalResult(
        name="tx_lo_leak_envdet",
        estimated={"dc_pre": tx.dc_pre},
        corrections={"dc_pre": [tx.dc_pre.real, tx.dc_pre.imag]},
        trace=trace,
        metrics_before={"lo_leak_dbc": before_dbc},
        metrics_after={"lo_leak_dbc": after_dbc},
        passed=after_dbc < -40.0,
        spec={"metric": "lo_leak_dbc", "limit": -40.0, "sense": "max"},
        cost={"captures": 6 * n_iter, "samples": 6 * n_iter * n},
    )


def calibrate_tx_lo_leak_loopback(tx: TxChain, rx: RxChain,
                                  path: LoopbackPath | None = None,
                                  n: int = 1 << 14, f_probe: float = 23e6,
                                  n_iter: int = 2) -> CalResult:
    """Loopback DC-bin method with RX-LO offset (run after RX DC cal).

    The TX carrier appears at -path.rx_lo_offset_hz in the RX capture.  A
    probe tone keeps the AGC/PA at a representative level.
    """
    if path is None:
        path = LoopbackPath(atten_db=40.0, delay_ns=6.0, rx_lo_offset_hz=4.8e6)
    f_leak = -path.rx_lo_offset_hz
    x = single_tone(f_probe, tx.fs, n, amp=0.25)
    before_dbc = lo_leak_dbc(tx(x), tx.fs)
    trace = []

    for it in range(n_iter):
        cap = run_loopback(tx, rx, x, path)
        leak_bin = bin_value(cap, f_leak, tx.fs)
        # measure complex gain dc_pre -> leak bin with a known DC pilot
        pilot = 0.05
        base = tx.dc_pre
        tx.dc_pre = base + pilot
        cap_p = run_loopback(tx, rx, x, path)
        tx.dc_pre = base
        g = (bin_value(cap_p, f_leak, tx.fs) - leak_bin) / pilot
        if abs(g) < 1e-12:
            break
        tx.dc_pre = base - leak_bin / g
        trace.append(lo_leak_dbc(tx(x), tx.fs))

    after_dbc = lo_leak_dbc(tx(x), tx.fs)
    return CalResult(
        name="tx_lo_leak_loopback",
        estimated={"dc_pre": tx.dc_pre},
        corrections={"dc_pre": [tx.dc_pre.real, tx.dc_pre.imag]},
        trace=trace,
        metrics_before={"lo_leak_dbc": before_dbc},
        metrics_after={"lo_leak_dbc": after_dbc},
        passed=after_dbc < -40.0,
        spec={"metric": "lo_leak_dbc", "limit": -40.0, "sense": "max"},
        cost={"captures": 2 * n_iter, "samples": 2 * n_iter * n},
    )
