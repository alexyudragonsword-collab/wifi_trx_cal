"""Pilot-based CFO/SCO/CPE tracking loop (the modem-side clock recovery).

Frame-by-frame closed loop: apply the current CFO derotation + SCO
resampling, demodulate, read the pilot phases, and update the estimates
with first-order loop gains.  Because LO and sampling clock derive from
one crystal, the SCO estimate can be slaved to the CFO estimate
(``slave_sco=True``) — faster convergence, exactly what real modems do.

Pull-in range: the symbol-rate pilot phase is unambiguous only for
|CFO| < 1/(2 * T_symbol) (~±36 kHz at 78.125 kHz SCS).  Larger offsets
must be acquired first from the preamble (``preamble.estimate_cfo``, or
an L-STF-style short training field); seed ``cfo_hz`` with that coarse
estimate before tracking.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
from scipy.interpolate import CubicSpline

from ..waveform.ofdm import OFDMWaveform, demodulate_ofdm
from ..waveform.pilots import pilot_sequence


@dataclass
class ClockTracker:
    fs: float
    f_carrier_hz: float
    mu_cfo: float = 0.6
    mu_sco: float = 0.6
    slave_sco: bool = True      # derive SCO from CFO (shared-crystal)
    cfo_hz: float = 0.0
    sco_ppm: float = 0.0
    trace: list = field(default_factory=list)

    # ------------------------------------------------------------ correction
    def correct(self, x: np.ndarray) -> np.ndarray:
        y = np.asarray(x, dtype=complex)
        if self.cfo_hz != 0.0:
            t = np.arange(y.size) / self.fs
            y = y * np.exp(-2j * np.pi * self.cfo_hz * t)
        if self.sco_ppm != 0.0:
            n = y.size
            t = np.arange(n) / self.fs
            # invert a clock running (1 + ppm) fast
            ts = np.arange(n) / self.fs * (1.0 + self.sco_ppm * 1e-6)
            ts = np.clip(ts, t[0], t[-1])
            y = CubicSpline(t, y.real)(ts) + 1j * CubicSpline(t, y.imag)(ts)
        return y

    # ------------------------------------------------------------ update
    def process_frame(self, cap: np.ndarray, ref: OFDMWaveform,
                      pilot_cols: np.ndarray,
                      pilot_seed: int = 42) -> np.ndarray:
        """Correct the capture, demodulate, update CFO/SCO from pilots.

        Returns the corrected demodulated symbols (n_symbols, n_active).
        """
        cfg = ref.config
        y = self.correct(cap)
        syms = demodulate_ofdm(y, ref)

        pilots = pilot_sequence(cfg.n_symbols, pilot_cols.size, pilot_seed)
        ph = np.angle(syms[:, pilot_cols] * np.conj(pilots))
        ph = np.unwrap(ph, axis=0)

        sym_len_s = (cfg.fft_size + cfg.cp_len) * cfg.oversampling / self.fs
        t_sym = (np.arange(cfg.n_symbols) + 0.5) * sym_len_s

        # residual CFO: slope of the per-symbol common pilot phase vs time
        common = ph.mean(axis=1)
        denom = float(np.dot(t_sym - t_sym.mean(), t_sym - t_sym.mean()))
        slope = float(np.dot(t_sym - t_sym.mean(), common - common.mean()))
        cfo_resid = slope / denom / (2 * np.pi) if denom > 0 else 0.0
        self.cfo_hz += self.mu_cfo * cfo_resid

        if self.slave_sco:
            # crystal ppm implied by the CFO estimate drives the SCO
            self.sco_ppm = -self.cfo_hz / self.f_carrier_hz * 1e6
        else:
            scs = self.fs / (cfg.fft_size * cfg.oversampling)
            tones = cfg.active_tone_indices()
            f_k = tones[pilot_cols] * scs
            ph_t = ph - common[:, None]
            x_reg = np.outer(t_sym, f_k - f_k.mean()).ravel()
            y_reg = ph_t.ravel()
            d2 = float(np.dot(x_reg, x_reg))
            sco_resid = (float(np.dot(x_reg, y_reg)) / d2 / (2 * np.pi) * 1e6
                         if d2 > 0 else 0.0)
            self.sco_ppm += self.mu_sco * sco_resid

        self.trace.append({"cfo_hz": self.cfo_hz, "sco_ppm": self.sco_ppm,
                           "cfo_resid_hz": cfo_resid})
        return syms
