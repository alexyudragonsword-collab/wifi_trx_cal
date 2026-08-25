# Quantization/clipping/jitter appliers adapted from
# adc_toolbox:vendor/ADCToolbox .../siggen/nonidealities.py (refactored from a
# sine-bound class into free functions over (x, t), extended to complex IQ).
# See PROVENANCE.md.
"""DAC and ADC behavioral models at the simulation sample rate.

Both converters process complex baseband as two independent real rails that
share one sampling clock (aperture jitter is common to I and Q).  Digital
samples are full-scale normalized; ``fullscale_dbm`` is the mean power of a
full-scale CW tone (|x_digital| = 1), which sets the digital<->analog
amplitude scale ``a_fs = sqrt(10^(fullscale_dbm/10))`` per complex sample.

Images/replicas at multiples of the converter rate are NOT modeled (the
whole simulation runs at one oversampled rate); optional zero-order-hold
droop approximates the DAC sinc rolloff in-band.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.interpolate import CubicSpline

from ..units import dbm_to_mw


def quantize_clip(x: np.ndarray, bits: int, a_fs: float) -> np.ndarray:
    """Mid-tread uniform quantization of a real rail to +/- a_fs with clipping."""
    n_levels = 2 ** bits
    step = 2.0 * a_fs / n_levels
    q = np.round(x / step) * step
    return np.clip(q, -a_fs, a_fs - step)


def aperture_jitter(x: np.ndarray, fs: float, jitter_rms_s: float,
                    rng: np.random.Generator) -> np.ndarray:
    """Resample complex x at jittered instants t_n = n/fs + dt_n (shared clock)."""
    n = x.size
    t = np.arange(n) / fs
    dt = rng.normal(0.0, jitter_rms_s, n)
    ts = np.clip(t + dt, t[0], t[-1])
    re = CubicSpline(t, x.real)(ts)
    im = CubicSpline(t, x.imag)(ts)
    return re + 1j * im


def zoh_droop_fir(fs_conv: float, fs_sim: float, n_taps: int = 33) -> np.ndarray:
    """Linear-phase FIR approximating the DAC sinc(f/fs_conv) droop in-band."""
    n = 1024
    f = np.fft.rfftfreq(n, d=1.0 / fs_sim)
    h_f = np.sinc(f / fs_conv)
    h_t = np.fft.irfft(h_f, n=n)
    m = n_taps
    taps = np.concatenate([h_t[-(m // 2):], h_t[: m - m // 2]]) * np.hanning(m)
    return taps / taps.sum() * np.sinc(0.0)


@dataclass
class DACParams:
    bits: int = 12
    fullscale_dbm: float = 4.0        # full-scale CW tone power at DAC output
    fs_conv_hz: float = 1.92e9        # converter rate (for ZOH droop only)
    zoh_droop: bool = False
    enabled: bool = True

    @property
    def a_fs(self) -> float:
        return float(np.sqrt(dbm_to_mw(self.fullscale_dbm)))

    def apply(self, x_digital: np.ndarray, fs: float) -> np.ndarray:
        """Full-scale digital complex in -> sqrt(mW) analog complex out."""
        x = np.asarray(x_digital, dtype=complex)
        a = self.a_fs
        if not self.enabled:
            return x * a
        i = quantize_clip(x.real * a, self.bits, a)
        q = quantize_clip(x.imag * a, self.bits, a)
        y = i + 1j * q
        if self.zoh_droop:
            y = np.convolve(y, zoh_droop_fir(self.fs_conv_hz, fs), mode="same")
        return y


@dataclass
class ADCParams:
    bits: int = 11
    fullscale_dbm: float = 2.0        # full-scale CW tone power at ADC input
    jitter_ps_rms: float = 0.0
    seed: int = 0
    enabled: bool = True

    @property
    def a_fs(self) -> float:
        return float(np.sqrt(dbm_to_mw(self.fullscale_dbm)))

    def apply(self, x_analog: np.ndarray, fs: float) -> np.ndarray:
        """sqrt(mW) analog complex in -> full-scale digital complex out."""
        x = np.asarray(x_analog, dtype=complex)
        a = self.a_fs
        if not self.enabled:
            return x / a
        if self.jitter_ps_rms > 0.0:
            rng = np.random.default_rng(self.seed)
            x = aperture_jitter(x, fs, self.jitter_ps_rms * 1e-12, rng)
        i = quantize_clip(x.real, self.bits, a)
        q = quantize_clip(x.imag, self.bits, a)
        return (i + 1j * q) / a

    def injected(self) -> dict:
        return {"bits": self.bits, "fullscale_dbm": self.fullscale_dbm,
                "jitter_ps_rms": self.jitter_ps_rms}
