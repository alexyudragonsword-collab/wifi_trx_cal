"""LPF corner (RC tuning) calibration.

On-chip flow: inject a tone at the wanted corner frequency plus a low-
frequency reference tone, sweep the RC tuning code, and pick the code whose
corner-to-reference power ratio is closest to -3 dB.  The RX variant reads
power at the ADC output; the TX variant reads the PA-output envelope
detector (tone power appears in the detector's beat spectrum) — here both
use a direct ratio measurement through their respective observation paths.
"""
from __future__ import annotations

import numpy as np

from ..chain.rx import RxChain
from ..chain.tx import TxChain
from ..chain.loopback import EnvelopeDetector
from ..waveform.stimuli import bin_value, single_tone
from .base import CalResult


def _rx_tone_ratio_db(rx: RxChain, f_probe: float, f_ref: float, n: int) -> float:
    """Corner-tone to reference-tone gain ratio through the RX baseband."""
    fs = rx.fs
    x = single_tone(f_probe, fs, n, amp=0.005) + single_tone(f_ref, fs, n, amp=0.005)
    out = rx(x, rng=np.random.default_rng(0))
    a_probe = abs(bin_value(out, f_probe, fs))
    a_ref = abs(bin_value(out, f_ref, fs))
    return 20.0 * np.log10(max(a_probe, 1e-300) / max(a_ref, 1e-300))


def _code_search(measure, n_codes: int, start: int, target_db: float,
                 mode: str) -> tuple[int, list]:
    """Find the code whose measured ratio is closest to target_db.

    mode="full": exhaustive sweep (factory).  mode="binary": bisection on
    the monotonic ratio-vs-code curve (power-on fast cal, ~log2 measures).
    """
    trace = []
    if mode == "full":
        best_code, best_err = start, np.inf
        for code in range(n_codes):
            ratio = measure(code)
            trace.append((code, ratio))
            if abs(ratio - target_db) < best_err:
                best_code, best_err = code, abs(ratio - target_db)
        return best_code, trace
    lo, hi = 0, n_codes - 1
    # higher code -> lower corner -> more attenuation -> ratio decreases
    while hi - lo > 1:
        mid = (lo + hi) // 2
        ratio = measure(mid)
        trace.append((mid, ratio))
        if ratio > target_db:
            lo = mid
        else:
            hi = mid
    r_lo = measure(lo)
    r_hi = measure(hi)
    trace += [(lo, r_lo), (hi, r_hi)]
    return (lo if abs(r_lo - target_db) < abs(r_hi - target_db) else hi), trace


def calibrate_lpf_corner_rx(rx: RxChain, n: int = 1 << 14,
                            target_db: float = -3.0,
                            search: str = "full") -> CalResult:
    """Find the RC code landing the corner ratio on -3 dB."""
    p = rx.params
    lpf = p.lpf
    f_probe = lpf.fc_nominal_hz
    f_ref = lpf.fc_nominal_hz / 32.0
    noise_state = rx.noise_enabled
    rx.noise_enabled = False
    fc_before = lpf.fc_actual_hz

    def measure(code: int) -> float:
        lpf.rc_code = code
        return _rx_tone_ratio_db(rx, f_probe, f_ref, n)

    best_code, trace = _code_search(measure, 2 ** lpf.rc_code_bits,
                                    lpf.rc_code, target_db, search)
    lpf.rc_code = best_code
    rx.noise_enabled = noise_state

    fc_after = lpf.fc_actual_hz
    return CalResult(
        name="rx_lpf_corner",
        estimated={"rc_error": lpf.rc_error, "best_code": best_code},
        corrections={"rc_code": best_code},
        trace=trace,
        metrics_before={"fc_hz": fc_before,
                        "fc_err_pct": 100 * (fc_before / lpf.fc_nominal_hz - 1)},
        metrics_after={"fc_hz": fc_after,
                       "fc_err_pct": 100 * (fc_after / lpf.fc_nominal_hz - 1)},
        passed=abs(fc_after / lpf.fc_nominal_hz - 1) <= lpf.rc_step,
        cost={"captures": len(trace), "samples": len(trace) * n},
    )


def calibrate_lpf_corner_tx(tx: TxChain, det: EnvelopeDetector | None = None,
                            n: int = 1 << 14, target_db: float = -3.0,
                            search: str = "full") -> CalResult:
    """TX LPF corner via the PA-output envelope detector.

    A baseband tone at f plus the LO leak beat in the square-law detector
    is messy; instead we use two sequential single-tone captures (probe at
    the corner, then the low-frequency reference) and compare detector AC
    power at each tone's self-beat-free fundamental: with a single complex
    tone the detector output is flat, so we read the tone amplitude at the
    chain output via the detector's input power instead.  Practical chips
    use exactly this two-tone power-ratio trick with a power detector.
    """
    p = tx.params
    lpf = p.lpf
    if det is None:
        det = EnvelopeDetector(enabled_adc=False)
    f_probe = lpf.fc_nominal_hz
    f_ref = lpf.fc_nominal_hz / 32.0
    fc_before = lpf.fc_actual_hz
    n_samp = n

    # baseline (LO leak etc.) measured once with no stimulus and subtracted
    v0 = float(np.mean(det.measure(tx(np.zeros(n_samp, dtype=complex)), tx.fs)))

    def tone_power_db(f_hz: float) -> float:
        x = single_tone(f_hz, tx.fs, n_samp, amp=0.05)
        y = tx(x)
        v = float(np.mean(det.measure(y, tx.fs)))
        return 10.0 * np.log10(max(v - v0, 1e-300))

    def measure(code: int) -> float:
        lpf.rc_code = code
        return tone_power_db(f_probe) - tone_power_db(f_ref)

    best_code, trace = _code_search(measure, 2 ** lpf.rc_code_bits,
                                    lpf.rc_code, target_db, search)
    lpf.rc_code = best_code

    fc_after = lpf.fc_actual_hz
    return CalResult(
        name="tx_lpf_corner",
        estimated={"rc_error": lpf.rc_error, "best_code": best_code},
        corrections={"rc_code": best_code},
        trace=trace,
        metrics_before={"fc_hz": fc_before,
                        "fc_err_pct": 100 * (fc_before / lpf.fc_nominal_hz - 1)},
        metrics_after={"fc_hz": fc_after,
                       "fc_err_pct": 100 * (fc_after / lpf.fc_nominal_hz - 1)},
        passed=abs(fc_after / lpf.fc_nominal_hz - 1) <= lpf.rc_step,
        cost={"captures": 2 * len(trace) + 1,
              "samples": (2 * len(trace) + 1) * n},
    )
