"""Blocker/coexistence stimuli at the RX input.

Blockers are complex-baseband signals at an offset from our carrier
(sqrt(mW) units, added at the RX input).  Reciprocal mixing needs no
extra model: the RX chain multiplies its LO phase noise onto the TOTAL
input, so a strong blocker automatically drags the LO skirt into the
wanted band — the tests only have to measure it.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from ..units import dbm_to_mw
from ..waveform.ofdm import OFDMConfig, generate_ofdm


@dataclass
class Blocker:
    offset_hz: float = 160e6
    power_dbm: float = -30.0
    kind: str = "cw"          # "cw" | "ofdm"
    bw_hz: float = 20e6       # for kind="ofdm"
    seed: int = 0
    enabled: bool = True

    def signal(self, n: int, fs: float) -> np.ndarray:
        if not self.enabled:
            return np.zeros(n, dtype=complex)
        if abs(self.offset_hz) + self.bw_hz / 2 > fs / 2:
            raise ValueError("blocker offset outside simulation Nyquist; "
                             "raise the oversampling")
        amp = np.sqrt(dbm_to_mw(self.power_dbm))
        t = np.arange(n) / fs
        if self.kind == "cw":
            base = np.ones(n, dtype=complex)
        else:
            cfg = OFDMConfig(bandwidth_hz=self.bw_hz, qam_order=64,
                             n_symbols=8,
                             oversampling=max(2, int(round(fs / self.bw_hz))),
                             seed=self.seed)
            wf = generate_ofdm(cfg)
            reps = int(np.ceil(n / wf.x.size))
            base = np.tile(wf.x, reps)[:n]
        return amp * base * np.exp(2j * np.pi * self.offset_hz * t)

    def injected(self) -> dict:
        return {"offset_hz": self.offset_hz, "power_dbm": self.power_dbm,
                "kind": self.kind}


def reciprocal_mixing_noise_dbm(p_blocker_dbm: float, l_dbchz_at_offset: float,
                                bw_hz: float) -> float:
    """In-band noise power from the LO skirt mixed onto a blocker."""
    return p_blocker_dbm + l_dbchz_at_offset + 10.0 * np.log10(bw_hz)
