"""Crystal/clock error: correlated CFO and SCO from one reference.

A real receiver derives BOTH its LO (via the PLL) and its ADC sampling
clock from the same crystal, so a crystal error of ``ppm`` produces a
carrier frequency offset of ``-ppm * 1e-6 * f_c`` AND a sampling clock
offset of the same ppm — correlated, not independent.  The modem can
exploit that (SCO inferred from CFO); the model reproduces it.

Applied at the RX front (CFO rotation at downconversion, SCO resampling
at the ADC).  In TX->RX self-loopback both share the crystal and the
error cancels; this impairment matters for the over-the-air scenario the
comm team simulates (their TX vs our RX).
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.interpolate import CubicSpline


@dataclass
class ClockError:
    ppm: float = 0.0
    enabled: bool = True

    def cfo_hz(self, f_carrier_hz: float) -> float:
        """RX LO error vs an ideal-transmitter carrier."""
        if not self.enabled:
            return 0.0
        return -self.ppm * 1e-6 * f_carrier_hz

    def apply_cfo(self, x: np.ndarray, fs: float, f_carrier_hz: float) -> np.ndarray:
        if not self.enabled or self.ppm == 0.0:
            return np.asarray(x, dtype=complex)
        t = np.arange(x.size) / fs
        return np.asarray(x, dtype=complex) * np.exp(
            2j * np.pi * self.cfo_hz(f_carrier_hz) * t)

    def apply_sco(self, x: np.ndarray, fs: float) -> np.ndarray:
        """Resample as sampled by a clock running (1 + ppm*1e-6) fast."""
        if not self.enabled or self.ppm == 0.0:
            return np.asarray(x, dtype=complex)
        n = x.size
        t = np.arange(n) / fs
        ts = np.arange(n) / (fs * (1.0 + self.ppm * 1e-6))
        ts = np.clip(ts, t[0], t[-1])
        return CubicSpline(t, x.real)(ts) + 1j * CubicSpline(t, x.imag)(ts)

    def apply(self, x: np.ndarray, fs: float, f_carrier_hz: float) -> np.ndarray:
        return self.apply_sco(self.apply_cfo(x, fs, f_carrier_hz), fs)

    def injected(self) -> dict:
        return {"ppm": self.ppm}
