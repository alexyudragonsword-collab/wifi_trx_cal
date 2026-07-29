"""TX chain: digital front-end -> DAC -> analog baseband -> IQ modulator -> PA.

Signal flow (complex baseband equivalent, sqrt(mW) after the DAC):

    x_digital (full-scale units)
      -> digital corrections: widely-linear (w1, w2), DC pre-subtraction, DPD
      -> DAC (quantize/clip, digital -> sqrt(mW))
      -> tunable LPF + VGA
      -> frequency-dependent IQ imbalance + LO leakage (complex DC)
      -> TX LO phase noise  exp(+j phi_tx)
      -> ScaledPA (Psat = 28 dBm)
      -> y [sqrt(mW)]

Correction state (dc_pre, w1/w2, dpd, power backoff) is what the calibration
algorithms program; all of it serializes via ``correction_state()``.
"""
from __future__ import annotations

import numpy as np

from ..dsp import conv_same
from ..pa.reference_pa import ReferencePA
from ..pa.saleh import SalehPA
from ..pa.scaled import ScaledPA
from ..units import db_to_amp, power_dbm
from .params import TxParams


def apply_widely_linear(x: np.ndarray, w1: np.ndarray | None,
                        w2: np.ndarray | None) -> np.ndarray:
    """x_c = w1 * x + w2 * conj(x)  (complex FIR pair; None = passthrough)."""
    x = np.asarray(x, dtype=complex)
    if w1 is None and w2 is None:
        return x
    y = conv_same(x, w1) if w1 is not None else x
    if w2 is not None:
        y = y + conv_same(np.conj(x), w2)
    return y


class TxChain:
    def __init__(self, params: TxParams, fs: float, pa=None):
        self.params = params
        self.fs = float(fs)
        if pa is not None:
            self.pa = pa  # prebuilt ScaledPA/DriftingScaledPA
        else:
            inner = (ReferencePA() if params.pa_model == "memory"
                     else SalehPA())
            self.pa = ScaledPA(inner, gain_db=params.pa_gain_db,
                               psat_dbm=params.psat_dbm,
                               pae_max=params.pae_max)
        # ---- calibration state (programmed by cal algorithms) ----
        self.dc_pre: complex = 0.0 + 0.0j       # digital DC pre-subtraction
        self.w1: np.ndarray | None = None       # widely-linear correction
        self.w2: np.ndarray | None = None
        self.dpd = None                          # callable x -> x
        self.gain_code_db: float = 0.0           # TX power control (digital+VGA)
        # inter-chain alignment (MIMO): digital pre-rotation and delay trim
        self.phase_corr_deg: float = 0.0
        self.delay_corr_samples: float = 0.0

    # ------------------------------------------------------------ pieces
    def _lo_leak(self) -> complex:
        p = self.params.lo_leak_dbm
        if p is None:
            return 0.0 + 0.0j
        amp = np.sqrt(10.0 ** (p / 10.0))
        return amp * np.exp(1j * np.deg2rad(self.params.lo_leak_phase_deg))

    def lo_phase(self, n: int, rng: np.random.Generator | None = None) -> np.ndarray:
        if rng is None:
            rng = np.random.default_rng(self.params.seed)
        return self.params.lo.phase(n, self.fs, rng)

    # ------------------------------------------------------------ main
    def __call__(self, x_digital: np.ndarray, phi_lo: np.ndarray | None = None,
                 nodes: dict | None = None) -> np.ndarray:
        """Run the chain.  Pass ``phi_lo`` explicitly for loopback scenarios
        (shared/independent LO control); ``nodes`` (a dict) collects per-node
        mean powers in dBm when provided."""
        p = self.params
        x = np.asarray(x_digital, dtype=complex)

        # digital front-end
        if self.dpd is not None:
            x = self.dpd(x)
        x = apply_widely_linear(x, self.w1, self.w2)
        x = x + self.dc_pre
        x = x * db_to_amp(self.gain_code_db)
        if self.phase_corr_deg:
            x = x * np.exp(-1j * np.deg2rad(self.phase_corr_deg))
        if self.delay_corr_samples:
            f = np.fft.fftfreq(x.size)
            x = np.fft.ifft(np.fft.fft(x)
                            * np.exp(2j * np.pi * f * self.delay_corr_samples))

        y = p.dac.apply(x, self.fs)
        if nodes is not None:
            nodes["dac_out_dbm"] = power_dbm(y)

        y = p.lpf.apply(y, self.fs)
        y = y * db_to_amp(p.vga_gain_db)
        if nodes is not None:
            nodes["bb_out_dbm"] = power_dbm(y)

        y = p.iq.apply(y, self.fs)
        y = y + self._lo_leak()

        if phi_lo is None and p.lo.enabled:
            phi_lo = self.lo_phase(y.size)
        if phi_lo is not None and p.lo.enabled:
            y = y * np.exp(1j * phi_lo)
        if nodes is not None:
            nodes["mixer_out_dbm"] = power_dbm(y)

        if p.pa_enabled:
            y = self.pa(y)
            if nodes is not None:
                nodes["pa_out_dbm"] = power_dbm(y)
                nodes["pa_avg_pae"] = self.pa.average_pae(y)
        return y

    # ------------------------------------------------------------ state
    def correction_state(self) -> dict:
        return {
            "dc_pre": [self.dc_pre.real, self.dc_pre.imag],
            "w1": None if self.w1 is None else
                 [list(np.real(self.w1)), list(np.imag(self.w1))],
            "w2": None if self.w2 is None else
                 [list(np.real(self.w2)), list(np.imag(self.w2))],
            "gain_code_db": self.gain_code_db,
            "phase_corr_deg": self.phase_corr_deg,
            "delay_corr_samples": self.delay_corr_samples,
            # analog tuning codes are corrections too: a chip restored from
            # JSON alone must not come up with an uncalibrated LPF corner
            "lpf_rc_code": self.params.lpf.rc_code,
        }

    def load_correction_state(self, state: dict) -> None:
        self.dc_pre = complex(state["dc_pre"][0], state["dc_pre"][1])
        for name in ("w1", "w2"):
            v = state.get(name)
            setattr(self, name, None if v is None else
                    np.asarray(v[0]) + 1j * np.asarray(v[1]))
        self.gain_code_db = float(state.get("gain_code_db", 0.0))
        self.phase_corr_deg = float(state.get("phase_corr_deg", 0.0))
        self.delay_corr_samples = float(state.get("delay_corr_samples", 0.0))
        if "lpf_rc_code" in state:
            self.params.lpf.rc_code = int(state["lpf_rc_code"])
