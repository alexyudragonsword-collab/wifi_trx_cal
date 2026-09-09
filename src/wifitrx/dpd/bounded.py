"""Envelope-bounded predistortion: saturate the correction outside the
fitted envelope.

A polynomial post-inverse is only a model of the PA on the envelope it
was fitted over; beyond the largest training amplitude it extrapolates,
and a 5th/7th-order polynomial extrapolates violently.  The calibration
scores its EVM on a frame that is not the DPD training waveform (pilot
tones and an LTF pair on top of the data), and one symbol whose peak
sat 1.2 dB above the training maximum read -3.8 dB on its own and pulled
a -42.6 dB TX EVM down to -36.2 (802.11ac 20 MHz, 256-QAM, 0.7.18).
Before that release the scoring burst was the training data itself, so
the extrapolation never showed.

Real implementations do not extrapolate: a LUT holds its last entry and
a CFR stage bounds the envelope in front of the DPD.  ``BoundedDPD``
does the LUT thing — for a sample above ``x_max`` it applies the
correction gain of the fitted edge, i.e. scales the sample onto the
edge, predistorts, and scales back — and delegates everything else
(coefficients, config, fixed-point export) to the wrapped model.
"""
from __future__ import annotations

import numpy as np


class BoundedDPD:
    def __init__(self, model, x_max: float):
        self.model = model
        self.x_max = float(x_max)

    def __call__(self, x: np.ndarray) -> np.ndarray:
        x = np.asarray(x, dtype=complex)
        r = np.abs(x)
        s = np.minimum(1.0, self.x_max / np.maximum(r, 1e-30))
        return self.model(x * s) / s

    def __getattr__(self, name):
        # coefficients, order, memory depth, get_config, ... live on the
        # fitted model; exports and inspectors read them through here
        return getattr(self.model, name)
