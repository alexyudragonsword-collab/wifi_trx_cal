"""Parameter dataclasses for the TX/RX chains.

Every impairment block carries an ``enabled`` switch; ``injected()`` returns
the ground-truth dictionary that calibration tests verify against (pattern
from adc_toolbox app/tiadc_model.py).  ``randomize()`` draws a plausible
process corner for Monte-Carlo calibration tests.
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace

import numpy as np

from ..impairments.analog_filter import TunableLPF
from ..impairments.converters import ADCParams, DACParams
from ..impairments.iq_imbalance import FreqDepIQImbalance
from ..impairments.nonlinear import MemorylessNonlin
from ..impairments.phase_noise import LOModel
from .agc import DEFAULT_LNA_STATES, LNAState


@dataclass
class TxParams:
    bandwidth_hz: float = 320e6
    dac: DACParams = field(default_factory=DACParams)
    lpf: TunableLPF = field(default_factory=lambda: TunableLPF(fc_nominal_hz=170e6))
    vga_gain_db: float = 0.0
    iq: FreqDepIQImbalance = field(default_factory=FreqDepIQImbalance)
    lo_leak_dbm: float | None = None      # absolute leak power at modulator output
    lo_leak_phase_deg: float = 0.0
    lo: LOModel = field(default_factory=LOModel)
    pa_gain_db: float = 26.0
    psat_dbm: float = 28.0
    pae_max: float = 0.35
    pa_enabled: bool = True
    # "saleh" (memoryless) | "memory" (Wiener-Hammerstein ReferencePA);
    # a custom PAModel instance can be passed to TxChain(pa=...) instead
    pa_model: str = "saleh"
    seed: int = 0

    def randomize(self, rng: np.random.Generator) -> "TxParams":
        return replace(
            self,
            lpf=replace(self.lpf, rc_error=float(rng.uniform(-0.2, 0.2))),
            iq=replace(
                self.iq,
                gain_db=float(rng.uniform(-0.5, 0.5)),
                phase_deg=float(rng.uniform(-3.0, 3.0)),
                gd_mismatch_ps=float(rng.uniform(-300.0, 300.0)),
                rail_ripple_db=float(rng.uniform(0.1, 0.5)),
                rail_gd_ripple_ns=float(rng.uniform(0.05, 0.2)),
                enabled=True,
            ),
            lo_leak_dbm=float(rng.uniform(-32.0, -22.0)),
            lo_leak_phase_deg=float(rng.uniform(0.0, 360.0)),
            seed=int(rng.integers(0, 2 ** 31)),
        )

    def injected(self) -> dict:
        return {
            "lpf": self.lpf.injected(),
            "iq": self.iq.injected(),
            "lo_leak_dbm": self.lo_leak_dbm,
            "lo_leak_phase_deg": self.lo_leak_phase_deg,
            "lo": self.lo.injected(),
        }


@dataclass
class RxParams:
    bandwidth_hz: float = 320e6
    lna_states: tuple[LNAState, ...] = DEFAULT_LNA_STATES
    nonlin_enabled: bool = True
    iq: FreqDepIQImbalance = field(default_factory=FreqDepIQImbalance)
    # DC offset per LNA state at the baseband node [sqrt(mW) complex]; the
    # dominant physical source (LO self-mixing) changes with front-end gain.
    dc_offset: tuple = ()
    lpf: TunableLPF = field(default_factory=lambda: TunableLPF(fc_nominal_hz=170e6))
    adc: ADCParams = field(default_factory=ADCParams)
    adc_backoff_db: float = 12.0          # AGC target below ADC full scale
    lo: LOModel = field(default_factory=LOModel)
    seed: int = 0

    def nonlin_for_state(self, idx: int) -> MemorylessNonlin:
        st = self.lna_states[idx]
        return MemorylessNonlin(iip3_dbm=st.iip3_dbm, enabled=self.nonlin_enabled)

    def dc_for_state(self, idx: int) -> complex:
        if not self.dc_offset:
            return 0.0 + 0.0j
        return complex(self.dc_offset[idx % len(self.dc_offset)])

    def randomize(self, rng: np.random.Generator) -> "RxParams":
        # LO self-mixing DC: larger in high-gain states.
        dc = tuple(
            (rng.normal(0.0, s) + 1j * rng.normal(0.0, s))
            for s in (0.02, 0.01, 0.005, 0.003)[: len(self.lna_states)]
        )
        return replace(
            self,
            iq=replace(
                self.iq,
                gain_db=float(rng.uniform(-0.5, 0.5)),
                phase_deg=float(rng.uniform(-3.0, 3.0)),
                gd_mismatch_ps=float(rng.uniform(-300.0, 300.0)),
                rail_ripple_db=float(rng.uniform(0.1, 0.5)),
                rail_gd_ripple_ns=float(rng.uniform(0.05, 0.2)),
                enabled=True,
            ),
            dc_offset=dc,
            lpf=replace(self.lpf, rc_error=float(rng.uniform(-0.2, 0.2))),
            seed=int(rng.integers(0, 2 ** 31)),
        )

    def injected(self) -> dict:
        return {
            "iq": self.iq.injected(),
            "dc_offset": self.dc_offset,
            "lpf": self.lpf.injected(),
            "lo": self.lo.injected(),
        }
