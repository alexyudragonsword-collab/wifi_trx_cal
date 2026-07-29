"""I/Q rail group-delay mismatch estimation.

For a pure rail delay mismatch tau (Q delayed vs I):
    G1(f) ~ 1,   G2(f) ~ j * pi * f * tau     (small tau)
so tau falls out of a least-squares fit of Im{rho(f)} against pi*f, using
the rho(f) = G2/G1 measurements already produced by the TX or RX IQ cal.
The wideband w2 FIR absorbs the mismatch anyway; the dedicated estimate
(a) verifies the injected ground truth and (b) drives the separate
fractional-delay trim when a shorter w2 is desired.
"""
from __future__ import annotations

import numpy as np

from .base import CalResult


def estimate_gd_mismatch_ps(rho_f_hz: np.ndarray, rho: np.ndarray) -> float:
    """LS fit of Im{rho} = pi * f * tau -> tau in picoseconds."""
    f = np.asarray(rho_f_hz, dtype=float)
    y = np.imag(np.asarray(rho))
    x = np.pi * f
    denom = float(np.dot(x, x))
    if denom == 0.0:
        return 0.0
    return float(np.dot(x, y) / denom) * 1e12


def verify_gd_estimate(rho_f_hz: np.ndarray, rho: np.ndarray,
                       injected_ps: float, tol_ps: float = 40.0) -> CalResult:
    est = estimate_gd_mismatch_ps(rho_f_hz, rho)
    return CalResult(
        name="group_delay",
        estimated={"gd_mismatch_ps": est},
        metrics_before={"injected_ps": injected_ps},
        metrics_after={"estimated_ps": est, "error_ps": est - injected_ps},
        passed=abs(est - injected_ps) < tol_ps,
        spec={"metric": "error_ps", "limit": tol_ps, "sense": "abs_max"},
    )
