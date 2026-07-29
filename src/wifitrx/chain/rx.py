"""RX chain: LNA -> IQ demodulator -> analog baseband -> ADC -> digital.

Signal flow (input in sqrt(mW) at the antenna/loopback port):

    y_rf
      -> thermal noise injection (cascaded NF of the current AGC state)
      -> memoryless nonlinearity (input-referred IIP3 of the state)
      -> LNA gain
      -> RX LO phase noise  exp(-j phi_rx)
      -> frequency-dependent IQ imbalance
      -> DC offset (gain-state dependent, LO self-mixing)
      -> tunable LPF
      -> VGA (AGC-computed gain to the ADC target level)
      -> ADC (jitter/quantize/clip, sqrt(mW) -> full-scale digital)
      -> digital corrections: DC subtraction, widely-linear (w1, w2),
         fractional-delay trim
"""
from __future__ import annotations

import numpy as np

from ..impairments.noise import thermal_noise
from ..units import db_to_amp, power_dbm
from .agc import select_lna_state, vga_gain_db
from .params import RxParams
from .tx import apply_widely_linear


def fractional_advance(y: np.ndarray, frac: float) -> np.ndarray:
    """FFT phase-ramp fractional delay (positive = advance)."""
    n = y.size
    f = np.fft.fftfreq(n)
    return np.fft.ifft(np.fft.fft(y) * np.exp(2j * np.pi * f * frac))


class RxChain:
    def __init__(self, params: RxParams, fs: float):
        self.params = params
        self.fs = float(fs)
        self.lna_idx: int = 0
        self.vga_db: float = 20.0
        # ---- calibration state ----
        self.dc_post: dict[int, complex] = {}   # per-LNA-state digital DC sub
        self.w1: np.ndarray | None = None
        self.w2: np.ndarray | None = None
        self.w2_by_state: dict[int, np.ndarray] = {}  # overrides w2 per state
        self.frac_delay_iq: float = 0.0         # residual I/Q delay trim [samples]
        self.im2_trim_code: int = 1 << (params.im2.trim_bits - 1)  # analog trim
        self.noise_enabled: bool = True

    # ------------------------------------------------------------ AGC
    def agc(self, p_in_dbm: float) -> None:
        """Select LNA state and VGA gain for an expected input power."""
        p = self.params
        self.lna_idx = select_lna_state(p.lna_states, p_in_dbm)
        target = p.adc.fullscale_dbm - p.adc_backoff_db
        self.vga_db = vga_gain_db(p_in_dbm, p.lna_states[self.lna_idx].gain_db,
                                  target)

    def lo_phase(self, n: int, rng: np.random.Generator | None = None) -> np.ndarray:
        if rng is None:
            rng = np.random.default_rng(self.params.seed + 1)
        return self.params.lo.phase(n, self.fs, rng)

    # ------------------------------------------------------------ main
    def __call__(self, y_rf: np.ndarray, phi_lo: np.ndarray | None = None,
                 rng: np.random.Generator | None = None,
                 nodes: dict | None = None) -> np.ndarray:
        p = self.params
        st = p.lna_states[self.lna_idx]
        y = np.asarray(y_rf, dtype=complex)
        if rng is None:
            rng = np.random.default_rng(p.seed + 2)

        if self.noise_enabled:
            y = y + thermal_noise(y.size, self.fs, st.nf_db, rng)
        y = p.nonlin_for_state(self.lna_idx).apply(y)
        y = y * db_to_amp(st.gain_db)
        if p.im2.enabled:
            y = p.im2.apply(y, self.im2_trim_code)  # mixer IM2 at this node
        if nodes is not None:
            nodes["lna_out_dbm"] = power_dbm(y)

        if phi_lo is None and p.lo.enabled:
            phi_lo = self.lo_phase(y.size)
        if phi_lo is not None and p.lo.enabled:
            y = y * np.exp(-1j * phi_lo)
        if p.clock.enabled:
            y = p.clock.apply_cfo(y, self.fs, p.lo.freq_hz)

        if p.iq.state_phase_step_deg and self.lna_idx:
            from dataclasses import replace as _replace
            iq_eff = _replace(p.iq, phase_deg=p.iq.phase_deg
                              + p.iq.state_phase_step_deg * self.lna_idx)
            y = iq_eff.apply(y, self.fs)
        else:
            y = p.iq.apply(y, self.fs)
        y = y + p.dc_for_state(self.lna_idx)
        y = p.lpf.apply(y, self.fs)
        y = y * db_to_amp(self.vga_db)
        if nodes is not None:
            nodes["adc_in_dbm"] = power_dbm(y)

        if p.clock.enabled:
            y = p.clock.apply_sco(y, self.fs)
        x = p.adc.apply(y, self.fs)

        # digital back-end corrections
        x = x - self.dc_post.get(self.lna_idx, 0.0 + 0.0j)
        w2 = self.w2_by_state.get(self.lna_idx, self.w2)
        x = apply_widely_linear(x, self.w1, w2)
        if self.frac_delay_iq != 0.0:
            # trim residual I/Q delay: advance Q rail relative to I
            q = fractional_advance(x.imag.astype(complex), self.frac_delay_iq)
            x = x.real + 1j * q.real
        return x

    # ------------------------------------------------------------ state
    def correction_state(self) -> dict:
        return {
            "dc_post": {str(k): [v.real, v.imag] for k, v in self.dc_post.items()},
            "w1": None if self.w1 is None else
                 [list(np.real(self.w1)), list(np.imag(self.w1))],
            "w2": None if self.w2 is None else
                 [list(np.real(self.w2)), list(np.imag(self.w2))],
            "frac_delay_iq": self.frac_delay_iq,
        }

    def load_correction_state(self, state: dict) -> None:
        self.dc_post = {int(k): complex(v[0], v[1])
                        for k, v in state.get("dc_post", {}).items()}
        for name in ("w1", "w2"):
            v = state.get(name)
            setattr(self, name, None if v is None else
                    np.asarray(v[0]) + 1j * np.asarray(v[1]))
        self.frac_delay_iq = float(state.get("frac_delay_iq", 0.0))
