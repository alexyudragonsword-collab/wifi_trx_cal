"""AGC settling dynamics: the gain state is not where the packet needs it
at the packet's first sample.

The static AGC (``RxChain.agc``) picks the LNA state and VGA gain for an
expected input level and applies them to the whole capture — the
receiver as it is *after* it has settled.  A real receiver idles at its
highest gain waiting for a packet, detects the power over the first
short-training periods, switches the front-end state after an attack
delay, and then the VGA and the DC-correction loop settle with their
own time constants.  Whatever has not settled by the LTF is frozen into
the channel estimate; whatever the ADC clipped during the attack window
is lost.  802.11 gives the AGC the 8 us L-STF to finish.

The model is piecewise where the chain is memoryless and continuous
where it is not:

* samples before ``attack_s``: the start state's NF, IIP3, gain and DC
  (the LNA ladder entry the receiver idled in), VGA at ``start_vga_db``;
* at ``attack_s`` the LNA state steps to the target chosen by the AGC;
  the VGA gain then moves exponentially to its target with
  ``vga_tau_s`` and the DC offset decays from the start state's value
  to the target state's with ``dc_tau_s`` (the DC loop re-settling);
* all of that enters the chain ahead of the channel LPF, so the filter
  shapes the steps exactly as hardware does, and ahead of the ADC, so a
  gain overshoot clips there.

Disabled (the default) the chain is bit-identical to the static AGC.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass
class AgcDynamics:
    enabled: bool = False
    #: time from the first sample until the LNA state switches: power
    #: detection over the STF plus decision latency
    attack_s: float = 1.6e-6
    #: VGA gain settling time constant after the switch
    vga_tau_s: float = 0.2e-6
    #: DC-correction loop time constant after the gain step
    dc_tau_s: float = 0.5e-6
    #: LNA ladder index the receiver idles in (0 = highest gain)
    start_state: int = 0
    #: VGA gain while idling [dB]
    start_vga_db: float = 40.0

    def attack_samples(self, fs: float) -> int:
        return int(round(self.attack_s * fs))

    def envelopes(self, n: int, fs: float, gain_start: float, gain_target: float,
                  vga_start_db: float, vga_target_db: float,
                  dc_start: complex, dc_target: complex
                  ) -> tuple[int, np.ndarray, np.ndarray, np.ndarray]:
        """Per-sample front-end gain (linear), VGA gain (dB) and DC offset
        trajectories over ``n`` samples; returns (n_attack, gain, vga_db,
        dc).  Gains are linear amplitude factors; the VGA is returned in
        dB because the chain converts it after compression modelling."""
        n_att = min(self.attack_samples(fs), n)
        t_after = (np.arange(n) - n_att) / fs
        settled = np.clip(t_after, 0.0, None)
        gain = np.full(n, float(gain_target))
        gain[:n_att] = float(gain_start)
        vga = np.where(np.arange(n) < n_att, float(vga_start_db),
                       vga_target_db + (vga_start_db - vga_target_db)
                       * np.exp(-settled / max(self.vga_tau_s, 1e-12)))
        dc = np.where(np.arange(n) < n_att, complex(dc_start),
                      complex(dc_target) + (complex(dc_start) - complex(dc_target))
                      * np.exp(-settled / max(self.dc_tau_s, 1e-12)))
        return n_att, gain, vga.astype(float), dc.astype(complex)

    def injected(self) -> dict:
        return {"enabled": self.enabled, "attack_s": self.attack_s,
                "vga_tau_s": self.vga_tau_s, "dc_tau_s": self.dc_tau_s,
                "start_state": self.start_state, "start_vga_db": self.start_vga_db}
