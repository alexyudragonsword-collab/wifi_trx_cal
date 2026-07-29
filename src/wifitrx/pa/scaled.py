"""dBm-scaled PA wrapper around the unit-power-normalized padpd PA models.

The vendored PA models (Saleh, GMP, ReferencePA...) operate on dimensionless
drive levels with an internal saturation point.  ``ScaledPA`` maps that
normalized domain to physical units: input/output in sqrt(mW) so that

* small-signal power gain equals ``gain_db``
* peak envelope output power saturates at ``psat_dbm``

P1dB is a derived quantity (the underlying model's AM-AM shape fixes the
Psat-to-P1dB relation).  PAE follows a class-AB-like square-root law
``pae(p) = pae_max * sqrt(p/psat)``, from which DC power and average PAE
for modulated signals are reported.
"""
from __future__ import annotations

import numpy as np

from ..units import dbm_to_mw, mw_to_dbm, db_to_amp
from .base import PAModel


class ScaledPA:
    def __init__(self, pa_model: PAModel, gain_db: float = 30.0,
                 psat_dbm: float = 28.0, pae_max: float = 0.35):
        self.pa_model = pa_model
        self.gain_db = float(gain_db)
        self.psat_dbm = float(psat_dbm)
        self.pae_max = float(pae_max)

        # Native-domain saturation amplitude and small-signal gain, found
        # numerically so any PAModel works — unit-normalized analytic models
        # (Saleh/GMP) and physical-amplitude LUT models (HB imports) alike.
        # Log sweep locates the AM-AM peak wherever the model's scale sits;
        # the small-signal gain is read at r_sat/100 (on the flat region,
        # not at the sweep bottom, which may be outside a LUT's table).
        r = np.logspace(-3, 3, 6000)
        a_out = np.abs(self.pa_model(r.astype(complex)))
        i_sat = int(np.argmax(a_out))
        self._r_sat = float(r[i_sat])
        self._a_sat = float(a_out[i_sat])
        # Small-signal gain = the gain plateau (d log(gain) / d log(r) ~ 0)
        # below saturation.  Neither end of the sweep is safe: LUT models
        # clamp below their table (slope -1 there) and everything
        # compresses near r_sat.
        gains = a_out / r
        slope = np.gradient(np.log(np.maximum(gains, 1e-300)), np.log(r))
        mask = r < self._r_sat / 3.0
        idx = int(np.argmin(np.abs(np.where(mask, slope, np.inf))))
        self._g0 = float(gains[idx])

        # |y_norm| = a_sat maps to sqrt(psat_mw)
        self._k_out = np.sqrt(dbm_to_mw(self.psat_dbm)) / self._a_sat
        # overall small-signal amplitude gain k_out * g0 * k_in = 10^(gain/20)
        self._k_in = db_to_amp(self.gain_db) / (self._k_out * self._g0)

    def __call__(self, x: np.ndarray) -> np.ndarray:
        """sqrt(mW) in -> sqrt(mW) out."""
        return self._k_out * self.pa_model(self._k_in * np.asarray(x, dtype=complex))

    # ------------------------------------------------------------ metrics
    def am_am(self, p_in_dbm: np.ndarray) -> np.ndarray:
        """Output power (dBm) vs input power (dBm) for a CW tone."""
        a_in = np.sqrt(dbm_to_mw(np.asarray(p_in_dbm, dtype=float)))
        a_out = np.abs(self(a_in.astype(complex)))
        return mw_to_dbm(a_out ** 2)

    @property
    def p1db_out_dbm(self) -> float:
        """Output-referred 1 dB compression point."""
        p_in = np.linspace(self.psat_dbm - self.gain_db - 40.0,
                           self.psat_dbm - self.gain_db + 10.0, 4000)
        p_out = self.am_am(p_in)
        comp = (p_in + self.gain_db) - p_out
        idx = np.argmax(comp >= 1.0)
        if comp[idx] < 1.0:
            return float(p_out[-1])
        return float(np.interp(1.0, comp[max(idx - 1, 0):idx + 1],
                               p_out[max(idx - 1, 0):idx + 1]))

    def pae(self, p_out_dbm) -> np.ndarray | float:
        """Instantaneous PAE at envelope power p_out_dbm (square-root law)."""
        p = dbm_to_mw(p_out_dbm)
        psat = dbm_to_mw(self.psat_dbm)
        return self.pae_max * np.sqrt(np.minimum(p / psat, 1.0))

    def dc_power_w(self, y: np.ndarray) -> float:
        """Average DC power consumption for output waveform y [sqrt(mW)].

        P_dc,inst = p_inst / pae(p_inst) = sqrt(psat * p_inst) / pae_max.
        """
        p_inst = np.abs(np.asarray(y)) ** 2  # mW
        psat = dbm_to_mw(self.psat_dbm)
        p_dc_mw = np.sqrt(psat * p_inst) / self.pae_max
        return float(np.mean(p_dc_mw)) * 1e-3

    def average_pae(self, y: np.ndarray) -> float:
        p_out_w = float(np.mean(np.abs(np.asarray(y)) ** 2)) * 1e-3
        p_dc = self.dc_power_w(y)
        return p_out_w / p_dc if p_dc > 0 else 0.0


class DriftingScaledPA:
    """dBm-scaled wrapper around a drifting PA (temperature/aging scenario).

    The dBm mapping (k_in/k_out) is frozen at drift state 0 — advancing the
    state then genuinely changes gain and compression at the chain level,
    which is what an adaptive DPD has to track.  Duck-types ScaledPA for
    TxChain use (__call__, average_pae, pae, dc_power_w).
    """

    def __init__(self, drift, gain_db: float = 26.0, psat_dbm: float = 28.0,
                 pae_max: float = 0.35):
        self.drift = drift
        self.scaled = ScaledPA(drift.pa(), gain_db=gain_db,
                               psat_dbm=psat_dbm, pae_max=pae_max)

    def set_state(self, state: float) -> None:
        self.drift.set_state(state)
        # swap only the inner model; keep the state-0 dBm scaling
        self.scaled.pa_model = self.drift.pa()

    @property
    def state(self) -> float:
        return self.drift.state

    def __call__(self, x: np.ndarray) -> np.ndarray:
        return self.scaled(x)

    def __getattr__(self, name):
        return getattr(self.scaled, name)
