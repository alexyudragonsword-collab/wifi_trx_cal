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

# numpy renamed trapz -> trapezoid in 2.0 and dropped the old name; the
# Android wheel is numpy 1.19.5, which only has trapz.  One binding here
# instead of a version test at every call site.
_trapezoid = getattr(np, "trapezoid", None) or np.trapz

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
    return float(_trapezoid(si, fi))


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


# ------------------------------------------------ OFDM CPE / ICI partition
def ici_weight(f, t_fft: float) -> np.ndarray:
    """Share of phase-noise power at offset ``f`` that survives per-symbol
    common-phase-error (CPE) removal: ``1 - sinc^2(f * T_FFT)``.

    Within one OFDM symbol of FFT length T_FFT, phase noise splits into
    the symbol-mean rotation J0 (the CPE, removable by a single complex
    rotation) and inter-carrier interference (ICI).  A phase-noise
    component at offset f contributes sinc^2(f T) to the mean and the
    rest to ICI; the -3 dB hand-over sits at 0.443 / T_FFT — ~35 kHz for
    the 12.8 us 11ax/be symbol, ~138 kHz for the 3.2 us legacy symbol.
    """
    return 1.0 - np.sinc(np.asarray(f, dtype=float) * t_fft) ** 2


def cpe_partition(psd_func, t_fft: float, f1: float, f2: float,
                  n: int = 6000) -> dict:
    """Closed-form split of a DSB S_phi(f) into CPE-removable and ICI
    phase power over [f1, f2] (log grid, trapezoid).

    Returns rad^2 totals plus the fraction the modem's CPE tracking takes
    out and the -3 dB hand-over frequency.  ``ici_rad2`` is the phase-
    noise error-vector power a genie CPE correction leaves behind — the
    analytic twin of a time-domain post-CPE EVM reading, which is what
    makes the two comparable (and the PSD convention checkable).
    """
    f = np.logspace(np.log10(f1), np.log10(f2), n)
    s = np.asarray(psd_func(f), dtype=float)
    w = ici_weight(f, t_fft)
    total = float(_trapezoid(s, f))
    ici = float(_trapezoid(s * w, f))
    return {"total_rad2": total, "ici_rad2": ici,
            "cpe_rad2": total - ici,
            "tracked_fraction": (total - ici) / total if total > 0 else 0.0,
            "f_3db_hz": 0.443 / t_fft}


def free_vco_ici_floor(k2: float, t_fft: float, n_lo: int = 1) -> float:
    """Phase-noise error power [rad^2] that per-symbol CPE removal leaves
    from a free-running 1/f^2 oscillator: (pi^2 / 3) * k2 * T_FFT.

    The weighted integral int k2/f^2 [1 - sinc^2(f T)] df converges —
    the integrand tends to (pi T)^2 / 3 at low offset — because a random
    walk cannot travel far inside one symbol and the symbol mean absorbs
    the rest.  What survives scales with the symbol length, so the
    12.8 us 11ax/be symbol keeps 4x (6 dB) more than the 3.2 us legacy
    one.  This is the floor a PLL loop-bandwidth sweep saturates at once
    the loop no longer holds the VCO: with a quiet in-band plateau the
    post-CPE EVM cannot get worse than this however narrow the loop.
    ``n_lo`` independent LOs add their k2.
    """
    return float(np.pi ** 2 / 3.0 * k2 * t_fft * n_lo)


@dataclass
class TypeIIPllPhase(NoiseSource):
    """Parametric closed-loop synthesizer profile for loop-bandwidth studies.

    S_phi(f) = |H|^2 * S_ib + |1 - H|^2 * S_vco(f) + floor   [rad^2/Hz DSB]

    with the type-II second-order closed-loop response
    H(s) = (2 zeta wn s + wn^2) / (s^2 + 2 zeta wn s + wn^2).  ``loop_bw_hz``
    is the -3 dB frequency of |H|^2 (wn is solved from it and zeta), so
    sweeping it moves the in-band-plateau-to-VCO hand-over without moving
    either asymptote — the question a PLL team asks when trading loop
    bandwidth.  The in-band plateau (reference/PFD/CP/divider noise times
    N^2) is flat and independent of the loop bandwidth; the VCO follows
    Leeson (1/f^2 with an optional 1/f^3 corner).
    """

    loop_bw_hz: float = 250e3
    zeta: float = 1.0
    plateau: float = 0.0      # in-band S_phi [rad^2/Hz]
    k2: float = 0.0           # VCO: S = k2/f^2 in the 1/f^2 region [rad^2*Hz]
    f_1f3: float = 0.0        # VCO 1/f^3 corner [Hz]
    floor: float = 0.0        # far-out floor [rad^2/Hz]

    @classmethod
    def from_spot(cls, name: str, loop_bw_hz: float, plateau_dbchz: float,
                  vco_dbchz_at_1mhz: float, floor_dbchz: float = -155.0,
                  zeta: float = 1.0, f_1f3: float = 0.0) -> "TypeIIPllPhase":
        return cls(name=name, unit="rad^2/Hz", loop_bw_hz=loop_bw_hz,
                   zeta=zeta, plateau=float(sphi_from_ldbc(plateau_dbchz)),
                   k2=float(sphi_from_ldbc(vco_dbchz_at_1mhz)) * 1e12,
                   f_1f3=f_1f3, floor=float(sphi_from_ldbc(floor_dbchz)))

    def psd(self, f: np.ndarray) -> np.ndarray:
        f = np.asarray(f, dtype=float)
        w = TWOPI * f
        a = 1.0 + 2.0 * self.zeta ** 2
        # |H|^2 = 1/2 at w3 = wn * sqrt(a + sqrt(a^2 + 1))
        wn = TWOPI * self.loop_bw_hz / np.sqrt(a + np.sqrt(a * a + 1.0))
        den = (wn ** 2 - w ** 2) ** 2 + 4.0 * self.zeta ** 2 * wn ** 2 * w ** 2
        h2 = (wn ** 4 + 4.0 * self.zeta ** 2 * wn ** 2 * w ** 2) / den
        e2 = w ** 4 / den
        s_vco = self.k2 / f ** 2 * (1.0 + self.f_1f3 / f)
        return h2 * self.plateau + e2 * s_vco + self.floor


# ------------------------------------------------------------------ LO model
# Default WiFi 7 fractional-N synthesizer closed-loop profile (offset, dBc/Hz):
# in-band plateau, mild loop peaking near 200 kHz, VCO roll-off, far-out
# floor.  Anchored to the PLL team's jitter target: 120 fs rms integrated
# 10 kHz - 100 MHz at the 6 GHz carrier (IPN -46.9 dBc, 0.26 deg rms) —
# the low-IPN synthesizer class that 4096-QAM (MCS12/13, TX EVM <= -38 dB)
# genuinely requires; a -38 dBc LO alone eats the whole EVM budget.
DEFAULT_WIFI7_LO_PROFILE = TabulatedPhase(
    "wifi7_lo",
    f_pts=(1e4, 1e5, 2e5, 1e6, 1e7, 1e8),
    l_dbc_pts=(-104.1, -104.1, -102.1, -116.1, -138.1, -154.1),
)


@dataclass
class LOModel:
    """Local oscillator: carrier frequency + phase-noise profile + spurs.

    ``phase(n, fs, rng)`` returns the time-domain phase deviation phi[n]
    [rad] at the baseband simulation rate; apply as ``x * exp(1j*phi)``.
    TX and RX may share one LOModel instance (correlated phase noise in
    loopback, the on-chip reality) or use independent instances/seeds.
    """

    freq_hz: float = 6.0e9
    profile: NoiseSource = field(default_factory=lambda: DEFAULT_WIFI7_LO_PROFILE)
    spur_offsets_hz: tuple = ()      # discrete spurs (e.g. fractional-N)
    spur_dbc: tuple = ()
    enabled: bool = True

    def phase(self, n: int, fs: float, rng: np.random.Generator) -> np.ndarray:
        if not self.enabled:
            return np.zeros(n)
        # synth + ipn_dbc below assume S_phi in rad^2/Hz; a NoiseSource
        # carrying e.g. a V^2/Hz supply-noise PSD must not be silently
        # synthesized as phase.
        if self.profile.unit != "rad^2/Hz":
            raise ValueError(
                f"LOModel needs a rad^2/Hz profile, got {self.profile.unit!r}")
        phi = synth_from_psd(self.profile.psd, fs, n, rng)
        t = np.arange(n) / fs
        for f_off, dbc in zip(self.spur_offsets_hz, self.spur_dbc):
            # narrowband FM spur: L_spur dBc <-> phase amplitude 2*10^(dbc/20)
            beta = 2.0 * 10.0 ** (dbc / 20.0)
            phi = phi + beta * np.sin(2 * np.pi * f_off * t + rng.uniform(0, 2 * np.pi))
        return phi

    def ipn_dbc(self, f1: float = 1e4, f2: float = 1e8) -> float:
        f = np.logspace(np.log10(f1), np.log10(f2), 600)
        return ipn_dbc(f, self.profile.psd(f), f1, f2)

    def injected(self) -> dict:
        return {"freq_hz": self.freq_hz, "ipn_dbc": self.ipn_dbc(),
                "spur_offsets_hz": self.spur_offsets_hz, "spur_dbc": self.spur_dbc}
