"""EVM budget: RSS aggregation of impairment contributions vs measured EVM.

All contributions are expressed as error-vector power relative to signal
power (linear), then root-sum-squared:

    EVM_total = sqrt(sum_i e_i)     with e_i in linear power ratio

Components:
* thermal/SNR:            e = 10^(-SNR/10)
* residual IQ image:      e = 10^(-IRR/10)
* integrated phase noise: e = sigma_phi^2 * (1 - tracked)   (rad^2; the
                          common-phase-error share the modem's per-symbol
                          tracking removes is excluded — see below)
* PA nonlinearity:        e = 10^(NMSE/10)  (post-DPD residual NMSE)
* quantization:           e = 10^(-SQNR/10) at the operating backoff

The tracked share is not a free constant.  Per-symbol CPE removal takes
out the phase power weighted by sinc^2(f T_FFT), i.e. the part below
~0.443/T_FFT (35 kHz for the 12.8 us 11ax/be symbol); everything above
survives as ICI.  For the shipped LO profile that is ~5.5 % of the
10 kHz - 100 MHz phase power under 11ax/be and ~28 % under the 3.2 us
legacy symbol.  Until 0.7.9 this field defaulted to 0.5, which
overstated the tracked share ~9x and made the phase-noise term ~2.7 dB
optimistic; it is now computed from the profile and symbol length
(``cpe_partition``) unless a caller pins it explicitly.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from ..impairments.phase_noise import (DEFAULT_WIFI7_LO_PROFILE, NoiseSource,
                                       cpe_partition)

# T_FFT of the 802.11ax/be numerology (78.125 kHz subcarrier spacing)
T_FFT_11AX_S = 12.8e-6
# the band LOModel.ipn_dbc integrates by default; the tracked share must
# be taken over the same band as the ipn_rad2 it multiplies
PN_BAND_HZ = (1e4, 1e8)


def cpe_tracked_fraction(profile: NoiseSource = DEFAULT_WIFI7_LO_PROFILE,
                         t_fft_s: float = T_FFT_11AX_S,
                         band_hz: tuple = PN_BAND_HZ) -> float:
    """Share of the LO's phase power over ``band_hz`` that per-symbol CPE
    removal takes out, for a symbol of FFT length ``t_fft_s``."""
    f1, f2 = band_hz
    return float(cpe_partition(profile.psd, t_fft_s, f1, f2)["tracked_fraction"])


@dataclass
class EvmBudget:
    snr_db: float | None = None
    irr_db: float | None = None
    ipn_rad2: float | None = None
    # None: computed from lo_profile / t_fft_s / pn_band_hz.  Pin a number
    # only when the modem's tracking is known to differ from an ideal
    # per-symbol common-phase rotation.
    cpe_tracked_fraction: float | None = None
    lo_profile: NoiseSource = field(default_factory=lambda: DEFAULT_WIFI7_LO_PROFILE)
    t_fft_s: float = T_FFT_11AX_S
    pn_band_hz: tuple = PN_BAND_HZ
    pa_nmse_db: float | None = None
    sqnr_db: float | None = None
    extra_db: dict = field(default_factory=dict)

    def effective_cpe_tracked_fraction(self) -> float:
        if self.cpe_tracked_fraction is not None:
            return float(self.cpe_tracked_fraction)
        return cpe_tracked_fraction(self.lo_profile, self.t_fft_s,
                                    self.pn_band_hz)

    def components_db(self) -> dict:
        out = {}
        if self.snr_db is not None:
            out["thermal"] = -self.snr_db
        if self.irr_db is not None:
            out["iq_image"] = -self.irr_db
        if self.ipn_rad2 is not None:
            resid = self.ipn_rad2 * (1.0 - self.effective_cpe_tracked_fraction())
            out["phase_noise"] = 10.0 * np.log10(max(resid, 1e-30))
        if self.pa_nmse_db is not None:
            out["pa_nonlinearity"] = self.pa_nmse_db
        if self.sqnr_db is not None:
            out["quantization"] = -self.sqnr_db
        out.update(self.extra_db)
        return out

    def predicted_evm_db(self) -> float:
        comps = self.components_db()
        p = sum(10.0 ** (v / 10.0) for v in comps.values())
        return float(10.0 * np.log10(max(p, 1e-30)))

    def report(self, measured_evm_db: float | None = None) -> dict:
        doc = {"components_db": self.components_db(),
               "predicted_evm_db": self.predicted_evm_db(),
               "cpe_tracked_fraction": self.effective_cpe_tracked_fraction()}
        if measured_evm_db is not None:
            doc["measured_evm_db"] = measured_evm_db
            doc["delta_db"] = measured_evm_db - doc["predicted_evm_db"]
        return doc
