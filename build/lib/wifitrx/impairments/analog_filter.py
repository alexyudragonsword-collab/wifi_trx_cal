"""Tunable analog baseband low-pass filter with RC-tuning-code corner error.

Models the on-chip channel-select LPF: the absolute RC product varies with
process (``rc_error``, e.g. +/-20 %), and a capacitor-bank tuning code
(``rc_code``) trims the corner in discrete steps.  The RC calibration
algorithm's job is to find the code that lands the corner back on nominal.

    fc_actual = fc_nominal * (1 + rc_error) / (1 + rc_step * (code - code_mid))

(A larger code switches in more capacitance -> lower corner.)  The filter is
applied causally (scipy sosfilt) to I and Q with the same coefficients; rail
mismatch is modeled separately in FreqDepIQImbalance.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy import signal as sig


@dataclass
class TunableLPF:
    fc_nominal_hz: float = 160e6      # nominal -3 dB corner (half the RF BW)
    order: int = 5
    family: str = "butter"            # 'butter' | 'cheby1'
    cheby_ripple_db: float = 0.5
    rc_error: float = 0.0             # process corner error, e.g. +0.15
    rc_code_bits: int = 5
    rc_step: float = 0.02             # fractional corner change per LSB
    rc_code: int = 16                 # current tuning code (mid = 2^(bits-1))
    # RC-product temperature drift: fractional corner change per degC
    # away from the 25 degC calibration point (poly-R + MOM-C tempco,
    # typically a few 100 ppm/degC)
    rc_tempco_per_c: float = 0.0
    temperature_c: float = 25.0
    enabled: bool = True

    @property
    def code_mid(self) -> int:
        return 1 << (self.rc_code_bits - 1)

    @property
    def fc_actual_hz(self) -> float:
        denom = 1.0 + self.rc_step * (self.rc_code - self.code_mid)
        drift = 1.0 + self.rc_tempco_per_c * (self.temperature_c - 25.0)
        return self.fc_nominal_hz * (1.0 + self.rc_error) * drift / max(denom, 1e-3)

    def _sos(self, fs: float) -> np.ndarray:
        wn = min(self.fc_actual_hz / (fs / 2.0), 0.99)
        if self.family == "cheby1":
            return sig.cheby1(self.order, self.cheby_ripple_db, wn, output="sos")
        return sig.butter(self.order, wn, output="sos")

    def apply(self, x: np.ndarray, fs: float) -> np.ndarray:
        if not self.enabled:
            return np.asarray(x, dtype=complex)
        x = np.asarray(x, dtype=complex)
        sos = self._sos(fs)
        return sig.sosfilt(sos, x.real) + 1j * sig.sosfilt(sos, x.imag)

    def freq_response(self, f: np.ndarray, fs: float) -> np.ndarray:
        sos = self._sos(fs)
        _, h = sig.sosfreqz(sos, worN=2 * np.pi * np.asarray(f) / fs)
        return h

    def injected(self) -> dict:
        return {"rc_error": self.rc_error, "fc_actual_hz": self.fc_actual_hz,
                "rc_code": self.rc_code,
                "rc_tempco_per_c": self.rc_tempco_per_c,
                "temperature_c": self.temperature_c}
