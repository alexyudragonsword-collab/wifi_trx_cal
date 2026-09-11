"""A frequency-selective propagation channel, for link-level study only.

Everything the calibration delivers is a conducted-mode figure: AWGN and
a unity loopback, no propagation (README, boundary paragraph).  That is
deliberate, and this module does not change it — it lives under
``link/`` precisely because ``tests/test_import_layering.py`` forbids
``cal`` and ``chain`` from importing ``link``, so the channel is
*structurally* unreachable from the cal sequence rather than merely
unused by it.

Model: a tapped delay line with an exponential power-delay profile,
taps on the sample grid, each tap an independent complex Gaussian
(Rayleigh), optionally with a Rician first tap.  Total tap power is
normalised to 1, so a realisation changes the frequency response and
not the average SNR.

**Why not the literal 802.11 TGn/TGax cluster tables.**  Those are an
external specification input this project does not hold, and a
half-remembered tap table is exactly the kind of number this repository
refuses to ship (AGENTS.md: a conclusion that cannot be verified is not
a conclusion).  The exponential profile is the standard analytical
stand-in, its rms delay spread is a closed form that
``realized_rms_delay_s`` recomputes from the actual taps, and the
presets below are named by that rms value rather than by a TGn letter.
If the link team supplies the real tables, ``TDLChannel`` takes explicit
taps and nothing else has to move — recorded in the backlog next to A2
and A4 as an optional external input.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

#: rms delay spreads (ns) spanning the range the 802.11 channel models
#: cover, from a small room to a large open space.  Named by the number,
#: not by a TGn letter — see the module docstring.
PRESET_RMS_DELAY_NS = {
    "flat": 0.0,
    "15ns": 15.0,
    "30ns": 30.0,
    "50ns": 50.0,
    "100ns": 100.0,
    "150ns": 150.0,
}


def coherence_bandwidth_hz(rms_delay_s: float) -> float:
    """The usual 1/(2 pi tau_rms) definition: the frequency separation
    over which the channel stays correlated.  A reference line, not a
    fitted quantity — the EVM readings are measured, this only says
    where to expect the knee."""
    if rms_delay_s <= 0.0:
        return float("inf")
    return 1.0 / (2.0 * np.pi * rms_delay_s)


@dataclass
class TDLChannel:
    """Exponential-PDP tapped delay line.  ``enabled=False`` (and
    ``rms_delay_ns=0``) leave the signal bit-identical."""

    rms_delay_ns: float = 50.0
    #: Rician K of the first tap in dB; None = Rayleigh throughout
    k_db: float | None = None
    #: profile truncation; None = 6 tau, where the residual power is
    #: exp(-6) = 0.25 % and the rms is within a fraction of a percent
    max_delay_ns: float | None = None
    enabled: bool = True

    @property
    def rms_delay_s(self) -> float:
        return self.rms_delay_ns * 1e-9

    def _truncation_s(self) -> float:
        if self.max_delay_ns is not None:
            return self.max_delay_ns * 1e-9
        return 6.0 * self.rms_delay_s

    def power_delay_profile(self, fs: float) -> tuple[np.ndarray, np.ndarray]:
        """(tap delays [s], tap powers summing to 1) on the ``fs`` sample
        grid.  A zero rms delay gives the single flat tap."""
        if not self.enabled or self.rms_delay_s <= 0.0:
            return np.zeros(1), np.ones(1)
        n = int(np.floor(self._truncation_s() * fs)) + 1
        delays = np.arange(n) / fs
        p = np.exp(-delays / self.rms_delay_s)
        return delays, p / p.sum()

    def realized_rms_delay_s(self, fs: float) -> float:
        """The rms delay spread the sampled, truncated profile actually
        has — recomputed from the taps rather than assumed equal to
        ``rms_delay_ns``, which it is not once the grid is coarse or the
        truncation is close in."""
        delays, p = self.power_delay_profile(fs)
        mean = float((p * delays).sum())
        return float(np.sqrt((p * (delays - mean) ** 2).sum()))

    def realize(self, fs: float, rng: np.random.Generator) -> np.ndarray:
        """One realisation of the complex tap gains.  E[sum |g|^2] = 1."""
        delays, p = self.power_delay_profile(fs)
        if not self.enabled or self.rms_delay_s <= 0.0:
            return np.ones(1, dtype=complex)
        g = (rng.standard_normal(p.size) + 1j * rng.standard_normal(p.size))
        g *= np.sqrt(p / 2.0)
        if self.k_db is not None:
            k = 10.0 ** (self.k_db / 10.0)
            # split the first tap into a deterministic and a diffuse part
            # of the same total power
            g[0] = (np.sqrt(p[0] * k / (k + 1.0))
                    + g[0] * np.sqrt(1.0 / (k + 1.0)))
        return g

    def frequency_response(self, taps: np.ndarray, tone_hz: np.ndarray,
                           fs: float) -> np.ndarray:
        """H at the given tone frequencies for a realisation's taps."""
        delays = np.arange(taps.size) / fs
        return np.exp(-2j * np.pi * np.outer(tone_hz, delays)) @ taps

    def apply(self, x: np.ndarray, fs: float,
              rng: np.random.Generator) -> tuple[np.ndarray, np.ndarray]:
        """Convolve and keep the input length; returns (y, taps).  The
        tail past the capture is dropped, which is what a receiver sees
        anyway.  Disabled, this is ``x`` unchanged."""
        x = np.asarray(x, dtype=complex)
        if not self.enabled or self.rms_delay_s <= 0.0:
            return x, np.ones(1, dtype=complex)
        taps = self.realize(fs, rng)
        return np.convolve(x, taps)[:x.size], taps
