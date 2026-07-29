"""Simplified L-LTF-like training preamble.

Structure (per 802.11 convention, simplified — no L-STF, no channel coding):

    [ GI2 | LTF | LTF ]

where LTF is one OFDM symbol of known BPSK on every active tone and GI2 is a
double-length cyclic prefix.  The exact repetition enables:

* frame timing via cross-correlation,
* CFO estimation from the phase drift between the two repeats,
* per-tone channel estimation for the data-symbol equalizer,
* preamble-based RX IQ/DC estimation (M3).
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .ofdm import OFDMConfig, OFDMWaveform, generate_ofdm


def ltf_tones(config: OFDMConfig, seed: int = 7) -> np.ndarray:
    """Known BPSK training values on all active tones (deterministic)."""
    rng = np.random.default_rng(seed)
    return (2.0 * rng.integers(0, 2, size=config.n_active) - 1.0).astype(complex)


@dataclass
class Frame:
    """Preamble + data frame with the indices needed to slice captures."""

    x: np.ndarray                  # full frame samples (unit average power scale of data part)
    data: OFDMWaveform             # vendored data waveform (reference for EVM)
    ltf: np.ndarray                # known BPSK per active tone
    config: OFDMConfig
    gi2_len: int                   # samples
    ltf_len: int                   # samples per LTF repeat (FFT window only)

    @property
    def preamble_len(self) -> int:
        return self.gi2_len + 2 * self.ltf_len

    def ltf_starts(self) -> tuple[int, int]:
        return self.gi2_len, self.gi2_len + self.ltf_len


def build_frame(config: OFDMConfig, ltf_seed: int = 7) -> Frame:
    """Assemble [GI2 | LTF | LTF | data]."""
    data = generate_ofdm(config)
    ltf = ltf_tones(config, ltf_seed)

    os_nfft = config.fft_size * config.oversampling
    tones = config.active_tone_indices()
    freq = np.zeros(os_nfft, dtype=complex)
    freq[tones % os_nfft] = ltf
    sym = np.fft.ifft(freq) * os_nfft / np.sqrt(config.n_active)
    sym = sym / data.scale                    # same amplitude scale as data part
    gi2 = 2 * config.cp_len * config.oversampling
    x = np.concatenate([sym[-gi2:], sym, sym, data.x])
    return Frame(x=x, data=data, ltf=ltf, config=config,
                 gi2_len=gi2, ltf_len=os_nfft)


def estimate_cfo(rx: np.ndarray, frame: Frame, fs: float) -> float:
    """CFO [Hz] from the phase drift between the two LTF repeats.

    Assumes coarse frame alignment (rx[0] is the frame start).  Unambiguous
    range is +/- fs / (2 * ltf_len) = +/- subcarrier_spacing/2 * oversampling.
    """
    s1, s2 = frame.ltf_starts()
    n = frame.ltf_len
    r1 = rx[s1:s1 + n]
    r2 = rx[s2:s2 + n]
    acc = np.vdot(r1, r2)  # sum conj(r1) * r2
    dt = n / fs
    return float(np.angle(acc) / (2 * np.pi * dt))


def apply_cfo(x: np.ndarray, cfo_hz: float, fs: float) -> np.ndarray:
    t = np.arange(x.size) / fs
    return x * np.exp(2j * np.pi * cfo_hz * t)


def channel_estimate(rx: np.ndarray, frame: Frame) -> np.ndarray:
    """Per-active-tone channel estimate from the averaged LTF repeats."""
    s1, s2 = frame.ltf_starts()
    n = frame.ltf_len
    cfg = frame.config
    tones = cfg.active_tone_indices()
    avg = 0.5 * (rx[s1:s1 + n] + rx[s2:s2 + n])
    spec = np.fft.fft(avg) / (n / np.sqrt(cfg.n_active)) * frame.data.scale
    return spec[tones % n] / frame.ltf


def estimate_sco(pilot_phases: np.ndarray, pilot_tone_idx: np.ndarray,
                 symbol_len_s: float, scs_hz: float) -> float:
    """Sampling clock offset [ppm] from pilot phase evolution.

    ``pilot_phases``: (n_symbols, n_pilots) unwrapped phase of
    rx_pilot * conj(known_pilot).  SCO makes the per-symbol phase slope
    across tone index grow linearly with time:
        dphi[sym, k] = 2*pi * f_k * sco * t_sym
    Least-squares fit over (tone frequency x symbol time).
    """
    n_sym, n_p = pilot_phases.shape
    t = (np.arange(n_sym) + 0.5) * symbol_len_s
    f_k = pilot_tone_idx * scs_hz
    # regress phase on f_k * t (outer product), per-symbol common phase removed
    ph = pilot_phases - pilot_phases.mean(axis=1, keepdims=True)
    x = np.outer(t, f_k - f_k.mean()).ravel()
    y = ph.ravel()
    denom = float(np.dot(x, x))
    if denom == 0.0:
        return 0.0
    slope = float(np.dot(x, y)) / denom       # = 2*pi*sco
    return slope / (2 * np.pi) * 1e6          # ppm
