"""RX IIP2 calibration: mixer IM2 trim-code search.

Direct-conversion RX must-have: the mixer's second-order beat dumps
blocker envelope energy at DC/low frequency, and the achievable IIP2
hinges on trimming the mixer mismatch.  TX sends a strong two-tone
through the loopback; the RX capture's bin at (f2 - f1) holds the IM2
beat, whose power is quadratic in (trim_code - best) — a three-point
parabolic fit per iteration finds the null (same estimator family as the
TX LO-leak envelope method).  Runs after RX DC cal, before the IQ cals.

The TX side is NOT a clean stimulus source: DAC even-order products of
the two tones land on the very same (f2 - f1) bin, phase-coherent with
(phi2 - phi1), so phase-randomized averaging keeps them.  That
transmitted background is code-independent and buries/tilts the RX null
(at 320 MHz it flattens the whole trim surface to ~1 dB).  Each code is
therefore measured at TWO coupler attenuations 6 dB apart: the linear
channel (tones and TX background alike) scales identically in both, the
locally-generated mixer IM2 does not, so the tone-ratio-normalized
difference ``beat_lo - g * beat_hi`` cancels the TX background exactly
and restores the null — the two-level separation used on real silicon
when the cal source's own IP2 cannot be trusted.
"""
from __future__ import annotations

from dataclasses import replace

import numpy as np

from ..chain.loopback import LoopbackPath, run_loopback
from ..chain.rx import RxChain
from ..chain.tx import TxChain
from ..units import power_dbm
from ..waveform.stimuli import (bin_value, grid_freq, scaled_probe,
                                single_tone)
from .base import CalResult


def _im2_beat(tx: TxChain, rx: RxChain, path: LoopbackPath,
              f1: float, f2: float, n: int, amp: float,
              n_avg: int = 4, seed: int = 0) -> tuple[complex, complex]:
    """Phase-randomized coherent average of the (f2 - f1) beat.

    The IM2 beat is phase-coherent with (phi2 - phi1) of the stimulus
    tones; converter quantization spurs at the same bin are not.  Rotating
    the tone phases capture-to-capture and derotating the beat before
    averaging keeps the IM2 term coherent while the spurs average down —
    the standard trick for measuring an IM2 null below the spur floor.

    Returns ``(beat, tone)``: the averaged complex beat and the averaged
    complex f1-tone bin (the linear-channel reference used by the
    two-level TX-background cancellation).
    """
    rng = np.random.default_rng(seed)
    fs = rx.fs
    acc = 0.0 + 0.0j
    tone = 0.0 + 0.0j
    for _ in range(n_avg):
        ph1 = float(rng.uniform(0, 2 * np.pi))
        ph2 = float(rng.uniform(0, 2 * np.pi))
        x = (single_tone(f1, fs, n, amp=amp / np.sqrt(2), phase=ph1)
             + single_tone(f2, fs, n, amp=amp / np.sqrt(2), phase=ph2))
        cap = run_loopback(tx, rx, x, path)
        acc += bin_value(cap, f2 - f1, fs) * np.exp(-1j * (ph2 - ph1))
        tone += bin_value(cap, f1, fs) * np.exp(-1j * ph1)
    return acc / n_avg, tone / n_avg


def calibrate_rx_iip2(tx: TxChain, rx: RxChain,
                      path: LoopbackPath | None = None,
                      n: int = 1 << 14, f1: float | None = None,
                      f2: float | None = None,
                      amp: float = 0.5, n_iter: int = 3,
                      delta: int = 24, n_avg: int = 4,
                      level_step_db: float = 6.0) -> CalResult:
    p = rx.params
    if not p.im2.enabled:
        return CalResult(name="rx_iip2", passed=None,
                         notes="IM2 model disabled; nothing to trim")
    if path is None:
        path = LoopbackPath(atten_db=40.0, delay_ns=6.0)
    # second coupler setting for the TX-background cancellation: less
    # attenuation drives the mixer harder, growing the local IM2 while
    # the transmitted background scales with the tones
    path_lo = replace(path, atten_db=path.atten_db - level_step_db)
    fs = rx.fs
    if f1 is None:
        f1 = scaled_probe(17e6, rx.params.bandwidth_hz)
    if f2 is None:
        f2 = scaled_probe(23e6, rx.params.bandwidth_hz)
    f1 = grid_freq(f1, fs, n)
    f2 = grid_freq(f2, fs, n)
    x_probe = (single_tone(f1, fs, n, amp=amp / np.sqrt(2))
               + single_tone(f2, fs, n, amp=amp / np.sqrt(2), phase=1.0))

    # AGC input levels for the two coupler settings (strong stimulus,
    # must not clip)
    p_pa = power_dbm(tx(x_probe))
    p_in_hi = p_pa - path.atten_db
    p_in_lo = p_pa - path_lo.atten_db

    def _rx_beat(pathx: LoopbackPath, p_in: float, seed: int) -> complex:
        # deliberately-hot two-tone: use the NORMAL ladder, not the
        # cal-observation pin — the low-gain state's linearity is what
        # protects the mixer here, and the IM2 trim is state-independent
        rx.agc(p_in)
        return _im2_beat(tx, rx, pathx, f1, f2, n, amp,
                         n_avg=n_avg, seed=seed)

    code_max = (1 << p.im2.trim_bits) - 1
    iip2_before = p.im2.iip2_eff_dbm(rx.im2_trim_code)
    trace = [(rx.im2_trim_code, iip2_before)]

    step = delta
    n_captures = 0
    for it in range(n_iter):
        c0 = rx.im2_trim_code
        cm = int(np.clip(c0 - step, 0, code_max))
        cp = int(np.clip(c0 + step, 0, code_max))
        powers = {}
        for c in (cm, c0, cp):
            rx.im2_trim_code = c
            beat_hi, tone_hi = _rx_beat(path, p_in_hi, seed=it)
            beat_lo, tone_lo = _rx_beat(path_lo, p_in_lo, seed=it)
            # tone-ratio normalization makes the linear channel (and the
            # TX background riding on it) cancel exactly, VGA step
            # rounding included; the residual is pure local mixer IM2
            g = tone_lo / tone_hi
            powers[c] = abs(beat_lo - g * beat_hi) ** 2
            n_captures += 2 * n_avg  # two coupler levels per code
        p_m, p_0, p_p = powers[cm], powers[c0], powers[cp]
        # stop when the surface is flat vs the residual floor (curvature
        # below measurement significance -> unconstrained extrapolation
        # would walk away from the null on noise)
        if max(powers.values()) < 1.6 * max(min(powers.values()), 1e-30):
            rx.im2_trim_code = min(powers, key=powers.get)
            break
        denom = p_p - 2 * p_0 + p_m
        if denom > 0:
            frac = -0.5 * (p_p - p_m) / denom
            frac = float(np.clip(frac, -4.0, 4.0))  # trust region
            best = c0 + frac * step
        else:
            frac = 4.0
            best = min(powers, key=powers.get)
        rx.im2_trim_code = int(np.clip(round(best), 0, code_max))
        trace.append((rx.im2_trim_code,
                      p.im2.iip2_eff_dbm(rx.im2_trim_code)))
        if abs(frac) < 1.5:   # converged at this scale -> refine
            step = max(step // 3, 1)

    iip2_after = p.im2.iip2_eff_dbm(rx.im2_trim_code)
    return CalResult(
        name="rx_iip2",
        estimated={"trim_code": rx.im2_trim_code,
                   "trim_best_truth": p.im2.trim_best},
        corrections={"im2_trim_code": rx.im2_trim_code},
        trace=trace,
        metrics_before={"iip2_dbm": iip2_before},
        metrics_after={"iip2_dbm": iip2_after},
        passed=iip2_after > iip2_before + 15.0 or iip2_after > 70.0,
        saturated=rx.im2_trim_code in (0, code_max),
        # floor spec: a self-imposed design gate (WiFi direct-conversion RX
        # class), looser than the pass criterion above — the step's own
        # criterion additionally demands improvement or a 70 dBm landing
        spec={"metric": "iip2_dbm", "limit": 55.0, "sense": "min"},
        cost={"captures": n_captures, "samples": n_captures * n},
    )
