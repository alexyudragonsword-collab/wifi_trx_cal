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
from ..impairments.clock import ClockError
from ..impairments.converters import ADCParams, DACParams
from ..impairments.iq_imbalance import FreqDepIQImbalance
from ..impairments.nonlinear import Im2Params, MemorylessNonlin
from ..impairments.phase_noise import LOModel
from .agc import DEFAULT_LNA_STATES, LNAState


def recommended_lpf_corner_hz(bandwidth_hz: float, role: str = "tx") -> float:
    """Per-mode channel-select corner (design insights #2 and #5).

    Wide modes (>= 80 MHz) need a corner >= 1.3x BW/2 on TX so the DPD
    pre-distortion spectrum survives (insight #2).  Narrow modes must
    RELAX the ratio instead: the WiFi guard interval is fixed in absolute
    time (0.8 us) while the filter impulse response scales as 1/BW, so a
    1.3x corner at 20 MHz rings ~1 us past the usable GI margin and
    floors EVM near -33 dB — ISI that no per-tone equalizer can remove.
    With fs >> BW in narrow modes, anti-aliasing costs nothing, so 3x is
    free (insight #5, found by the 20 MHz GUI run; measured LPF-only
    floor: 1.3x -33.3 / 2.5x -41.5 / 3x -47.2 dB).
    """
    if bandwidth_hz >= 80e6:
        ratio = 1.3 if role == "tx" else 1.12
    else:
        ratio = 3.0
    return bandwidth_hz / 2 * ratio


@dataclass
class TxParams:
    bandwidth_hz: float = 320e6
    dac: DACParams = field(default_factory=DACParams)
    lpf: TunableLPF = field(default_factory=lambda: TunableLPF(fc_nominal_hz=170e6))
    vga_gain_db: float = 0.0
    iq: FreqDepIQImbalance = field(default_factory=FreqDepIQImbalance)
    lo_leak_dbm: float | None = None      # absolute leak power at modulator output
    lo_leak_phase_deg: float = 0.0
    # leak power drift with temperature (bias-dependent feedthrough),
    # dB per degC away from the 25 degC calibration point
    lo_leak_tempco_db_per_c: float = 0.0
    # driver/bias gain drift ahead of the PA, dB per degC
    pa_gain_tempco_db_per_c: float = 0.0
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
            "lo_leak_tempco_db_per_c": self.lo_leak_tempco_db_per_c,
            "pa_gain_tempco_db_per_c": self.pa_gain_tempco_db_per_c,
            "lo": self.lo.injected(),
        }


@dataclass
class RxParams:
    bandwidth_hz: float = 320e6
    lna_states: tuple[LNAState, ...] = DEFAULT_LNA_STATES
    nonlin_enabled: bool = True
    im2: Im2Params = field(default_factory=lambda: Im2Params(enabled=False))
    iq: FreqDepIQImbalance = field(default_factory=FreqDepIQImbalance)
    # DC offset per LNA state at the baseband node [sqrt(mW) complex]; the
    # dominant physical source (LO self-mixing) changes with front-end gain.
    dc_offset: tuple = ()
    lpf: TunableLPF = field(default_factory=lambda: TunableLPF(fc_nominal_hz=170e6))
    adc: ADCParams = field(default_factory=ADCParams)
    adc_backoff_db: float = 12.0          # AGC target below ADC full scale
    lo: LOModel = field(default_factory=LOModel)
    # RX crystal error vs the transmitter's reference (OTA scenario);
    # disabled by default — in self-loopback both sides share the crystal
    clock: ClockError = field(default_factory=lambda: ClockError(enabled=False))
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
            im2=replace(
                self.im2,
                trim_best=int(rng.integers(30, 226)),
                phase_deg=float(rng.uniform(0.0, 360.0)),
                enabled=True,
            ),
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
            "im2": self.im2.injected(),
            "clock": self.clock.injected(),
        }
