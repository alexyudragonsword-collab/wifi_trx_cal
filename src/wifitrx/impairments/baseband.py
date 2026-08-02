"""The analog baseband stage: LPF + VGA + ADC driver.

Specified the way a baseband block actually is — an input-referred
**noise voltage density** (nV/sqrt(Hz)) or an integrated noise voltage
over the channel, and an **output swing** (Vpp) — not by a noise figure
and an input-referred IP3.  NF is meaningless here without a source
impedance the on-chip node does not have; the cascade maths that does
need an NF derives one (``link.budget.baseband_equivalent_stage``).

Why the two ends of the stage are modelled at different points
(``chain/rx.py``): the noise is injected at the LPF *input*, so the
channel filter shapes it as it does in hardware, while the compression
is applied after the VGA, because it is the VGA output / ADC driver that
clips and its ceiling is a fixed *output* level.  That asymmetry is the
physics worth having: raising the VGA moves the signal toward a fixed
ceiling, and lowering it moves the signal away — neither of which a
front-end IIP3 can express.

Default parameters are PLACEHOLDERS, derived to be consistent with the
official 8-state ladder rather than measured:

- ``noise_v_sqrthz = 6e-9`` costs 0.07 dB of NF in the top gain state and
  0.89 dB in the bottom one (the referral divides by the RF gain, so the
  baseband matters most where the RF gain is least).  Above roughly
  11 nV/sqrt(Hz) the bottom state's stated 34 dB NF stops being
  realizable at all — ``link.budget.deembed_states`` says so rather than
  silently producing a negative RF noise figure.
- ``out_swing_vpp = 1.0`` is +3.98 dBm at 50 ohm, 14 dB above the AGC's
  mean ADC target of -10 dBm, so OFDM peaks land a few dB below
  compression.

Replacing them with circuit data is one line each::

    BasebandStage(noise_v_sqrthz=8.5e-9, out_swing_vpp=1.2, enabled=True)
    BasebandStage.from_rms_noise(180e-6, bw_hz=160e6, enabled=True)
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from ..units import R_REF_OHM, v_sqrthz_to_dbm_hz, vpp_to_dbm
from .nonlinear import MemorylessNonlin
from .noise import noise_at_density

# third-order intercept above the 1 dB compression point, the standard
# relation for a memoryless cubic nonlinearity
OIP3_ABOVE_OP1DB_DB = 9.6


@dataclass
class BasebandStage:
    noise_v_sqrthz: float = 6.0e-9   # input-referred, at the baseband node
    r_node_ohm: float = R_REF_OHM    # impedance that voltage is quoted at
    out_swing_vpp: float = 1.0       # VGA / ADC-driver output compression
    enabled: bool = False            # off: the ladder stays a cascade total

    # ------------------------------------------------------- constructors
    @classmethod
    def from_rms_noise(cls, v_rms: float, bw_hz: float,
                       **kw) -> "BasebandStage":
        """Build from an integrated noise voltage over ``bw_hz``.

        The other way circuit teams quote it: "180 uVrms over the
        160 MHz channel" rather than a density.
        """
        return cls(noise_v_sqrthz=float(v_rms) / np.sqrt(bw_hz), **kw)

    # ------------------------------------------------------- derived specs
    def psd_dbm_hz(self) -> float:
        """Input-referred noise density at the baseband node [dBm/Hz]."""
        return float(v_sqrthz_to_dbm_hz(self.noise_v_sqrthz, self.r_node_ohm))

    def rms_noise_v(self, bw_hz: float) -> float:
        """Integrated input-referred noise voltage over a bandwidth."""
        return float(self.noise_v_sqrthz * np.sqrt(bw_hz))

    def op1db_dbm(self) -> float:
        """Output 1 dB compression point [dBm]."""
        return float(vpp_to_dbm(self.out_swing_vpp, self.r_node_ohm))

    def oip3_dbm(self) -> float:
        return self.op1db_dbm() + OIP3_ABOVE_OP1DB_DB

    # ------------------------------------------------------------- apply
    def noise(self, n: int, fs: float, rng: np.random.Generator) -> np.ndarray:
        """Noise samples for the baseband node [sqrt(mW)]."""
        if not self.enabled:
            return np.zeros(n, dtype=complex)
        return noise_at_density(n, fs, self.psd_dbm_hz(), rng)

    def nonlin(self) -> MemorylessNonlin:
        """Output-referred compression, applied after the VGA."""
        return MemorylessNonlin(iip3_dbm=self.oip3_dbm(), enabled=self.enabled)

    def injected(self) -> dict:
        return {"noise_v_sqrthz": self.noise_v_sqrthz,
                "noise_dbm_hz": self.psd_dbm_hz(),
                "out_swing_vpp": self.out_swing_vpp,
                "op1db_dbm": self.op1db_dbm()}
