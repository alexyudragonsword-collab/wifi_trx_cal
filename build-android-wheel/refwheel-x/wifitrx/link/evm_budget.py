"""EVM budget: RSS aggregation of impairment contributions vs measured EVM.

All contributions are expressed as error-vector power relative to signal
power (linear), then root-sum-squared:

    EVM_total = sqrt(sum_i e_i)     with e_i in linear power ratio

Components:
* thermal/SNR:            e = 10^(-SNR/10)
* residual IQ image:      e = 10^(-IRR/10)
* integrated phase noise: e = sigma_phi^2   (rad^2, common-phase-error
                          tracked portion removed by the modem is excluded
                          via ``cpe_tracked`` — in-loop-BW noise is largely
                          corrected by pilot CPE tracking)
* PA nonlinearity:        e = 10^(NMSE/10)  (post-DPD residual NMSE)
* quantization:           e = 10^(-SQNR/10) at the operating backoff
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np


@dataclass
class EvmBudget:
    snr_db: float | None = None
    irr_db: float | None = None
    ipn_rad2: float | None = None
    cpe_tracked_fraction: float = 0.5   # fraction of phase power the modem tracks out
    pa_nmse_db: float | None = None
    sqnr_db: float | None = None
    extra_db: dict = field(default_factory=dict)

    def components_db(self) -> dict:
        out = {}
        if self.snr_db is not None:
            out["thermal"] = -self.snr_db
        if self.irr_db is not None:
            out["iq_image"] = -self.irr_db
        if self.ipn_rad2 is not None:
            resid = self.ipn_rad2 * (1.0 - self.cpe_tracked_fraction)
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
               "predicted_evm_db": self.predicted_evm_db()}
        if measured_evm_db is not None:
            doc["measured_evm_db"] = measured_evm_db
            doc["delta_db"] = measured_evm_db - doc["predicted_evm_db"]
        return doc
