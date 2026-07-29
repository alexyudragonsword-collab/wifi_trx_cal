"""Frequency-dependent IQ imbalance (dual real-rail model).

Physics-matched structure for a direct-conversion modulator/demodulator at
wide bandwidth: the I and Q analog rails see slightly different low-pass
responses (real FIRs ``h_i``, ``h_q``, including a fractional-delay group
mismatch), then the quadrature combiner adds gain and phase error:

    y = gi*exp(+j*phi/2) * (h_i * I)  +  j * gq*exp(-j*phi/2) * (h_q * Q)

with gi = 10^(gain_db/40), gq = 1/gi and phi = phase error.  This is exactly
widely-linear:  Y(f) = G1(f) X(f) + G2(f) X*(-f), with

    G1(f) = [gi e^{+j phi/2} Hi(f) + gq e^{-j phi/2} Hq(f)] / 2
    G2(f) = [gi e^{+j phi/2} Hi(f) - gq e^{-j phi/2} Hq(f)] / 2

so the analytic per-bin image rejection IRR(f) = |G1/G2|^2 is available as
ground truth for calibration verification.

Rail-response mismatch is generated as sinusoidal magnitude/group-delay
ripple FIRs (frequency-sampling design vendored from PA_DPD loopback.py),
split anti-symmetrically between the two rails, plus a fractional delay on
the Q rail for the deterministic group-delay mismatch.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np


def _ripple_fir(fs: float, ripple_db: float, gd_ripple_ns: float,
                period_hz: float, n_taps: int, phase_offset: float = 0.0) -> np.ndarray:
    """Real FIR with sinusoidal magnitude ripple [dB pk-pk] and group-delay
    ripple [ns pk-pk] across frequency (period ``period_hz``).

    Frequency-sampling design (adapted from PA_DPD loopback.py) with the
    Hermitian symmetry enforced so taps are real.
    """
    n = 1024
    f = np.fft.rfftfreq(n, d=1.0 / fs)
    mag_db = 0.5 * ripple_db * np.cos(2 * np.pi * f / period_hz + phase_offset)
    gd = 0.5 * gd_ripple_ns * 1e-9 * np.sin(2 * np.pi * f / period_hz + phase_offset)
    phase = -2 * np.pi * np.cumsum(gd) * (fs / n)
    h_f = 10.0 ** (mag_db / 20.0) * np.exp(1j * phase)
    h_t = np.fft.irfft(h_f, n=n)
    m = n_taps
    taps = np.concatenate([h_t[-(m // 2):], h_t[: m - m // 2]])
    taps = taps * np.hanning(m)
    return taps / taps.sum()  # unit DC gain


def _frac_delay_fir(taps: np.ndarray, delay_samples: float) -> np.ndarray:
    """Apply a fractional delay to a real FIR via FFT phase ramp (stays real).

    The input FIR is referenced to its center tap (as used by convolve
    mode="same"); the output is odd-length with its center tap carrying the
    original response delayed by ``delay_samples``.
    """
    n = 256
    center = (taps.size - 1) // 2
    padded = np.zeros(n)
    padded[: taps.size] = taps
    padded = np.roll(padded, -center)  # reference center tap to index 0
    h_f = np.fft.rfft(padded)
    f = np.fft.rfftfreq(n)
    h_f = h_f * np.exp(-2j * np.pi * f * delay_samples)
    h_t = np.fft.irfft(h_f, n=n)
    m = taps.size + 2 * int(np.ceil(abs(delay_samples))) + 8
    m = m + 1 - m % 2  # odd length
    out = np.concatenate([h_t[-(m // 2):], h_t[: m - m // 2]])
    return out


@dataclass
class FreqDepIQImbalance:
    """Frequency-dependent IQ imbalance + rail response mismatch.

    Parameters
    ----------
    gain_db : I/Q amplitude imbalance (I is +gain_db/2, Q is -gain_db/2).
    phase_deg : quadrature phase error.
    gd_mismatch_ps : deterministic group-delay mismatch, Q rail delayed.
    rail_ripple_db, rail_gd_ripple_ns : peak-to-peak rail response mismatch,
        applied anti-symmetrically (+/2 on I, -/2 on Q) so the mismatch, not
        the common response, is what the model injects.
    ripple_period_hz : ripple period across frequency.
    n_taps : rail FIR length.
    enabled : bypass switch.
    """

    gain_db: float = 0.0
    phase_deg: float = 0.0
    gd_mismatch_ps: float = 0.0
    rail_ripple_db: float = 0.0
    rail_gd_ripple_ns: float = 0.0
    ripple_period_hz: float = 160e6
    n_taps: int = 33
    # additional quadrature phase error per RX front-end gain state index
    # (front-end load changes shift the LO quadrature slightly per state)
    state_phase_step_deg: float = 0.0
    enabled: bool = True

    def rail_firs(self, fs: float) -> tuple[np.ndarray, np.ndarray]:
        """(h_i, h_q) real rail FIRs at sample rate fs."""
        if self.rail_ripple_db == 0.0 and self.rail_gd_ripple_ns == 0.0:
            h_i = np.array([1.0])
            h_q = np.array([1.0])
        else:
            h_i = _ripple_fir(fs, +0.5 * self.rail_ripple_db,
                              +0.5 * self.rail_gd_ripple_ns,
                              self.ripple_period_hz, self.n_taps)
            h_q = _ripple_fir(fs, -0.5 * self.rail_ripple_db,
                              -0.5 * self.rail_gd_ripple_ns,
                              self.ripple_period_hz, self.n_taps)
        if self.gd_mismatch_ps != 0.0:
            h_q = _frac_delay_fir(h_q, self.gd_mismatch_ps * 1e-12 * fs)
        return h_i, h_q

    def _combiner(self) -> tuple[complex, complex]:
        gi = 10.0 ** (self.gain_db / 40.0)
        gq = 1.0 / gi
        phi = np.deg2rad(self.phase_deg)
        a = gi * np.exp(+0.5j * phi)       # multiplies filtered I
        b = 1j * gq * np.exp(-0.5j * phi)  # multiplies filtered Q
        return a, b

    def apply(self, x: np.ndarray, fs: float) -> np.ndarray:
        if not self.enabled:
            return np.asarray(x, dtype=complex)
        x = np.asarray(x, dtype=complex)
        h_i, h_q = self.rail_firs(fs)
        from ..dsp import conv_same
        i_f = conv_same(x.real, h_i) if h_i.size > 1 else x.real
        q_f = conv_same(x.imag, h_q) if h_q.size > 1 else x.imag
        a, b = self._combiner()
        return a * i_f + b * q_f

    # ------------------------------------------------------------ ground truth
    def g1g2(self, f: np.ndarray, fs: float) -> tuple[np.ndarray, np.ndarray]:
        """Analytic widely-linear responses G1(f), G2(f) at frequencies f [Hz]."""
        h_i, h_q = self.rail_firs(fs)
        w = 2 * np.pi * np.asarray(f, dtype=float) / fs

        def resp(h):
            n0 = (h.size - 1) / 2.0  # center-tap reference (mode="same")
            k = np.arange(h.size)
            return np.sum(h[None, :] * np.exp(-1j * np.outer(w, k - n0)), axis=1)

        hi_f = resp(h_i)
        hq_f = resp(h_q)
        a, b = self._combiner()
        # y = a*(hi*I) + b*(hq*Q); I=(x+x*)/2, Q=-j(x-x*)/2
        g1 = 0.5 * (a * hi_f - 1j * b * hq_f)
        g2 = 0.5 * (a * hi_f + 1j * b * hq_f)
        return g1, g2

    def irr_db(self, f: np.ndarray, fs: float) -> np.ndarray:
        """Analytic image rejection ratio [dB] for a tone at frequency f.

        The image of a tone at +f lands at -f with amplitude G2(-f)
        (G2(f) multiplies X*(-f) in Y(f)), so IRR(f) = |G1(f)/G2(-f)|.
        """
        f = np.asarray(f, dtype=float)
        g1, _ = self.g1g2(f, fs)
        _, g2m = self.g1g2(-f, fs)
        return 20.0 * np.log10(np.maximum(np.abs(g1), 1e-300)
                               / np.maximum(np.abs(g2m), 1e-300))

    def injected(self) -> dict:
        return {
            "gain_db": self.gain_db,
            "phase_deg": self.phase_deg,
            "gd_mismatch_ps": self.gd_mismatch_ps,
            "rail_ripple_db": self.rail_ripple_db,
            "rail_gd_ripple_ns": self.rail_gd_ripple_ns,
        }
