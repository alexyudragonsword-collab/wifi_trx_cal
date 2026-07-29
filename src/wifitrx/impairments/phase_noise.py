# Vendored from pll_simulator:src/pllsim/core/{colored,noise,jitter}.py (internal
# sibling repo), merged and trimmed for wifitrx (circuit-level noise sources and
# FreqResponse-based budgeting removed).  See PROVENANCE.md.
"""LO phase-noise profiles, time-domain synthesis and integrated-jitter metrics.

PSD convention (same as pllsim)
-------------------------------
Internal phase PSDs are **double-sideband** S_phi(f) in rad^2/Hz.
Spot numbers use L(f) = S_phi(f)/2 in dBc/Hz:

    L_dbc(f) = 10*log10(S_phi(f)/2)
    S_phi(f) = 2 * 10^(L_dbc/10)
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

TWOPI = 2.0 * np.pi


# ------------------------------------------------------------- conversions
def sphi_from_ldbc(l_dbc) -> np.ndarray:
    """dBc/Hz -> double-sideband S_phi [rad^2/Hz]."""
    return 2.0 * 10.0 ** (np.asarray(l_dbc, dtype=float) / 10.0)


def ldbc_from_sphi(s_phi) -> np.ndarray:
    """Double-sideband S_phi [rad^2/Hz] -> L(f) in dBc/Hz."""
    return 10.0 * np.log10(np.maximum(np.asarray(s_phi, dtype=float), 1e-300) / 2.0)


# ------------------------------------------------------------- PSD profiles
@dataclass
class NoiseSource:
    """Base class: white PSD of `level` unit^2/Hz."""

    name: str
    unit: str = "rad^2/Hz"
    level: float = 0.0

    def psd(self, f: np.ndarray) -> np.ndarray:
        return np.full(np.asarray(f).shape, self.level)


@dataclass
class FlickerFloorPhase(NoiseSource):
    """Phase noise with flat floor and 1/f flicker corner.

    S_phi(f) = floor * (1 + fc/f)   [rad^2/Hz, DSB]
    """

    fc: float = 0.0  # flicker corner [Hz]

    @classmethod
    def from_spot(cls, name: str, l_floor_dbchz: float, fc: float = 0.0) -> "FlickerFloorPhase":
        return cls(name=name, unit="rad^2/Hz", level=float(sphi_from_ldbc(l_floor_dbchz)), fc=fc)

    def psd(self, f: np.ndarray) -> np.ndarray:
        f = np.asarray(f, dtype=float)
        return self.level * (1.0 + self.fc / f)


@dataclass
class LeesonOscillator(NoiseSource):
    """Oscillator phase noise: 1/f^3 + 1/f^2 + floor.

    S_phi(f) = k2/f^2 * (1 + f_1f3/f) + floor   [rad^2/Hz DSB]
    """

    k2: float = 0.0        # rad^2*Hz  (S_phi = k2/f^2 in the 20 dB/dec region)
    f_1f3: float = 0.0     # 1/f^3 corner [Hz]
    floor: float = 0.0     # rad^2/Hz

    @classmethod
    def from_spot(cls, name: str, l_dbchz: float, f_offset: float,
                  f_1f3: float = 0.0, floor_dbchz: float = -170.0) -> "LeesonOscillator":
        """Spot L at f_offset assumed on the 1/f^2 asymptote."""
        s_spot = float(sphi_from_ldbc(l_dbchz))
        k2 = s_spot * f_offset**2
        return cls(name=name, unit="rad^2/Hz", k2=k2, f_1f3=f_1f3,
                   floor=float(sphi_from_ldbc(floor_dbchz)))

    def psd(self, f: np.ndarray) -> np.ndarray:
        f = np.asarray(f, dtype=float)
        return self.k2 / f**2 * (1.0 + self.f_1f3 / f) + self.floor


@dataclass
class TabulatedPhase(NoiseSource):
    """Piecewise log-log interpolated S_phi from (f, L_dbc) pairs.

    Use for measured or spec closed-loop PLL profiles: the in-band plateau,
    loop peaking and VCO roll-off of a WiFi synthesizer are captured directly
    from (offset, dBc/Hz) breakpoints.
    """

    f_pts: tuple = field(default_factory=tuple)
    l_dbc_pts: tuple = field(default_factory=tuple)

    def psd(self, f: np.ndarray) -> np.ndarray:
        lf = np.log10(np.asarray(f, dtype=float))
        li = np.interp(lf, np.log10(np.asarray(self.f_pts, dtype=float)),
                       np.asarray(self.l_dbc_pts, dtype=float))
        return sphi_from_ldbc(li)


# ------------------------------------------------- time-domain synthesis
def synth_from_psd(psd_func, fs: float, n: int, rng: np.random.Generator) -> np.ndarray:
    """Synthesize n samples at rate fs with one-sided PSD psd_func(f) [u^2/Hz].

    FFT-domain shaping of complex white Gaussian noise; Hermitian symmetry
    enforced by irfft.  The DC bin is zeroed (no information below fs/n).
    """
    nf = n // 2 + 1
    f = np.arange(nf) * (fs / n)
    amp = np.zeros(nf)
    if nf > 1:
        s = np.asarray(psd_func(f[1:]), dtype=float)
        s = np.maximum(s, 0.0)
        # X_k drawn so that E|X_k|^2 * 2/(fs*n) = S(f_k)  (one-sided Welch scaling)
        amp[1:] = np.sqrt(s * fs * n / 2.0)
    x = amp * (rng.standard_normal(nf) + 1j * rng.standard_normal(nf)) / np.sqrt(2.0)
    x[0] = 0.0
    if n % 2 == 0:
        x[-1] = np.real(x[-1]) * np.sqrt(2.0)
    return np.fft.irfft(x, n=n)


# ------------------------------------------------------------- integration
def _band_mask(f: np.ndarray, f1: float, f2: float):
    return (f >= f1) & (f <= f2)


def integrate_pn(f: np.ndarray, s_phi: np.ndarray, f1: float = 1e3, f2: float = 100e6) -> float:
    """Integral of S_phi df over [f1, f2] -> phase power [rad^2] (trapezoid)."""
    f = np.asarray(f, dtype=float)
    s = np.asarray(s_phi, dtype=float)
    m = _band_mask(f, f1, f2)
    fi, si = f[m], s[m]
    if f1 > f[0] and (fi.size == 0 or fi[0] > f1):
        s1 = np.interp(np.log10(f1), np.log10(f), s)
        fi, si = np.insert(fi, 0, f1), np.insert(si, 0, s1)
    if f2 < f[-1] and (fi.size == 0 or fi[-1] < f2):
        s2 = np.interp(np.log10(f2), np.log10(f), s)
        fi, si = np.append(fi, f2), np.append(si, s2)
    if fi.size < 2:
        return 0.0
    return float(np.trapezoid(si, fi))


def ipn_dbc(f: np.ndarray, s_phi: np.ndarray, f1: float = 1e3, f2: float = 100e6) -> float:
    """Integrated phase noise in dBc (single-sideband convention: power/2)."""
    p = integrate_pn(f, s_phi, f1, f2)
    return 10.0 * np.log10(max(p / 2.0, 1e-300))


def rms_jitter_s(f: np.ndarray, s_phi: np.ndarray, f0: float,
                 f1: float = 1e3, f2: float = 100e6) -> float:
    """RMS jitter [s] from double-sideband S_phi at carrier f0."""
    p = integrate_pn(f, s_phi, f1, f2)
    return float(np.sqrt(p) / (TWOPI * f0))


def rms_jitter_fs(f: np.ndarray, s_phi: np.ndarray, f0: float,
                  f1: float = 1e3, f2: float = 100e6) -> float:
    """RMS jitter [fs]."""
    return 1e15 * rms_jitter_s(f, s_phi, f0, f1, f2)
