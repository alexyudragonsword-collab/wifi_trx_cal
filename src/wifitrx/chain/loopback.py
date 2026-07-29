"""On-chip observation paths for self-calibration.

``LoopbackPath``: TX output -> coupler/attenuator -> RX input, with delay,
optional AWGN, and the RX-LO frequency-offset rotation used by the TX IQ
calibration (baseband equivalent of downconverting with f_rx != f_tx:
a TX baseband tone at +f appears at f - offset with offset = f_rx - f_tx...
here we rotate by exp(-j*2*pi*offset*t)).

``run_loopback`` orchestrates the LO phase-noise sequences: with a shared
synthesizer (the on-chip reality for TX->RX self-loopback) phi_rx == phi_tx
and the phase noise largely cancels; with ``shared_lo=False`` (e.g. the
offset LO comes from an auxiliary synthesizer) they are independent.

``EnvelopeDetector``: square-law power detector on the PA output — the
RX-independent observation path used to bootstrap TX LO-leakage and TX IQ
calibration (image beats at 2f, LO leakage beats at f).
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy import signal as sig

from ..impairments.converters import quantize_clip
from ..units import db_to_amp
from .rx import RxChain
from .tx import TxChain


def frac_delay(y: np.ndarray, delay_samples: float) -> np.ndarray:
    n = y.size
    f = np.fft.fftfreq(n)
    return np.fft.ifft(np.fft.fft(y) * np.exp(-2j * np.pi * f * delay_samples))


@dataclass
class LoopbackPath:
    atten_db: float = 40.0
    delay_ns: float = 6.0
    rx_lo_offset_hz: float = 0.0     # f_rx - f_tx during offset-LO captures
    snr_db: float | None = None      # extra AWGN on the coupled path
    seed: int = 0

    def apply(self, y: np.ndarray, fs: float) -> np.ndarray:
        y = np.asarray(y, dtype=complex) * db_to_amp(-self.atten_db)
        if self.delay_ns:
            y = frac_delay(y, self.delay_ns * 1e-9 * fs)
        if self.rx_lo_offset_hz:
            t = np.arange(y.size) / fs
            y = y * np.exp(-2j * np.pi * self.rx_lo_offset_hz * t)
        if self.snr_db is not None:
            rng = np.random.default_rng(self.seed)
            p = np.mean(np.abs(y) ** 2)
            sigma = np.sqrt(p / db_to_amp(self.snr_db) ** 2 / 2.0)
            y = y + sigma * (rng.standard_normal(y.size)
                             + 1j * rng.standard_normal(y.size))
        return y


def run_loopback(tx: TxChain, rx: RxChain, x_digital: np.ndarray,
                 path: LoopbackPath, shared_lo: bool = True,
                 seed: int = 0) -> np.ndarray:
    """TX -> coupler -> RX capture with explicit LO phase-noise handling."""
    rng = np.random.default_rng(seed)
    n = np.asarray(x_digital).size
    phi_tx = tx.lo_phase(n, rng) if tx.params.lo.enabled else None
    if shared_lo:
        phi_rx = phi_tx
    else:
        phi_rx = rx.lo_phase(n, rng) if rx.params.lo.enabled else None
    y = tx(x_digital, phi_lo=phi_tx)
    y = path.apply(y, tx.fs)
    return rx(y, phi_lo=phi_rx, rng=rng)


@dataclass
class EnvelopeDetector:
    """Square-law detector on the PA output: v = |y|^2, LPF, coarse ADC."""

    lpf_bw_hz: float = 60e6
    adc_bits: int = 10
    fullscale_dbm: float = 33.0      # detector full scale (power units)
    enabled_adc: bool = True

    def measure(self, y_pa: np.ndarray, fs: float) -> np.ndarray:
        v = np.abs(np.asarray(y_pa)) ** 2          # instantaneous power [mW]
        wn = min(self.lpf_bw_hz / (fs / 2.0), 0.99)
        b, a = sig.butter(3, wn)
        v = sig.lfilter(b, a, v)
        if self.enabled_adc:
            v_fs = 10.0 ** (self.fullscale_dbm / 10.0)
            v = quantize_clip(v - v_fs / 2.0, self.adc_bits, v_fs / 2.0) + v_fs / 2.0
        return v

    def response(self, f_hz: float, fs: float) -> complex:
        """Known detector LPF response (calibrated observation path)."""
        wn = min(self.lpf_bw_hz / (fs / 2.0), 0.99)
        b, a = sig.butter(3, wn)
        _, h = sig.freqz(b, a, worN=[2 * np.pi * abs(f_hz) / fs])
        h0 = complex(h[0])
        return h0 if f_hz >= 0 else np.conj(h0)
