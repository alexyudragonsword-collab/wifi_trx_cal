# IIPx-parameterized memoryless nonlinearity, concept adapted from
# receiver_link_budget:modules/modulated_signal.py (apply_polynomial_distortion),
# re-derived for sqrt(mW) complex-baseband units.  See PROVENANCE.md.
"""Memoryless RX front-end nonlinearity from IIP3/IIP2 in dBm.

Complex-baseband equivalent of a passband polynomial y = a1 v + a2 v^2 + a3 v^3
with a1 = 1 (gain handled separately):

* third order (odd, in-band):   y += -(x |x|^2) / iip3_mw
  (at input power = IIP3 the IM3 tone equals the fundamental)
* second order (envelope, near DC): y += |x|^2 / sqrt(iip2_mw)
  (documented approximation: the baseband IM2 beat referred to IIP2)

Compressive sign for the third-order term.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from ..units import dbm_to_mw


@dataclass
class Im2Params:
    """Trimmable second-order distortion of the direct-conversion mixer.

    The IM2 beat coefficient crosses zero at ``trim_best`` (mixer
    load-mismatch trim DAC); away from it IIP2 degrades toward
    ``iip2_worst_dbm`` at the code rails.  A residual orthogonal-phase
    component bounds the achievable IIP2 at ``iip2_peak_dbm`` — the trim
    cannot null it, which is exactly the hardware behavior.
    """

    iip2_peak_dbm: float = 75.0
    iip2_worst_dbm: float = 42.0
    phase_deg: float = 0.0
    trim_best: int = 128
    trim_bits: int = 8
    enabled: bool = True

    def a2(self, code: int) -> complex:
        """IM2 coefficient [1/sqrt(mW)] at a trim code."""
        if not self.enabled:
            return 0.0 + 0.0j
        half = float(1 << (self.trim_bits - 1))
        a_max = 1.0 / np.sqrt(dbm_to_mw(self.iip2_worst_dbm))
        a_res = 1.0 / np.sqrt(dbm_to_mw(self.iip2_peak_dbm))
        ph = np.deg2rad(self.phase_deg)
        main = a_max * (code - self.trim_best) / half * np.exp(1j * ph)
        resid = a_res * np.exp(1j * (ph + np.pi / 2.0))
        return complex(main + resid)

    def iip2_eff_dbm(self, code: int) -> float:
        a = abs(self.a2(code))
        if a <= 0:
            return float("inf")
        return float(-10.0 * np.log10(a ** 2))

    def apply(self, x: np.ndarray, code: int) -> np.ndarray:
        if not self.enabled:
            return np.asarray(x, dtype=complex)
        x = np.asarray(x, dtype=complex)
        return x + self.a2(code) * (np.abs(x) ** 2)

    def injected(self) -> dict:
        return {"trim_best": self.trim_best,
                "iip2_peak_dbm": self.iip2_peak_dbm,
                "iip2_worst_dbm": self.iip2_worst_dbm}


@dataclass
class MemorylessNonlin:
    iip3_dbm: float | None = None
    iip2_dbm: float | None = None
    enabled: bool = True

    def apply(self, x: np.ndarray) -> np.ndarray:
        if not self.enabled:
            return np.asarray(x, dtype=complex)
        x = np.asarray(x, dtype=complex)
        y = x.copy()
        if self.iip3_dbm is not None:
            y = y - x * (np.abs(x) ** 2) / dbm_to_mw(self.iip3_dbm)
        if self.iip2_dbm is not None:
            y = y + (np.abs(x) ** 2) / np.sqrt(dbm_to_mw(self.iip2_dbm))
        return y

    def injected(self) -> dict:
        return {"iip3_dbm": self.iip3_dbm, "iip2_dbm": self.iip2_dbm}
