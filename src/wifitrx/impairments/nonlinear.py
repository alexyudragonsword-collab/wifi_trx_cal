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
