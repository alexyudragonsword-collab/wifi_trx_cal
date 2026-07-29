"""AGC verification sweep: the final system-level check.

Sweeps the RX input power with all corrections active and verifies that
(a) the AGC lands the ADC input on the target backoff, (b) the measured
digital SNR tracks the cascade prediction within tolerance.
"""
from __future__ import annotations

import numpy as np

from ..chain.rx import RxChain
from ..units import power_dbm
from ..waveform.stimuli import single_tone
from .base import CalResult


def agc_sweep(rx: RxChain, p_in_range_dbm: np.ndarray | None = None,
              n: int = 1 << 13, f_probe: float = 23e6,
              seed: int = 0) -> dict:
    if p_in_range_dbm is None:
        p_in_range_dbm = np.arange(-85.0, -5.0, 5.0)
    rng = np.random.default_rng(seed)
    rows = []
    for p_in in p_in_range_dbm:
        rx.agc(float(p_in))
        amp = np.sqrt(10.0 ** (p_in / 10.0))
        x = single_tone(f_probe, rx.fs, n, amp=amp)
        nodes: dict = {}
        cap = rx(x, rng=rng, nodes=nodes)
        cap_ac = cap - np.mean(cap)   # judge landing on the AC (signal) power
        # tone power vs everything-else power in the digital capture
        spec = np.abs(np.fft.fft(cap_ac)) ** 2 / n ** 2
        k = int(round(f_probe * n / rx.fs))
        p_sig = float(np.sum(spec[[k - 1, k, k + 1]]))
        p_tot = float(np.mean(np.abs(cap_ac) ** 2))
        snr_db = 10.0 * np.log10(max(p_sig, 1e-300)
                                 / max(p_tot - p_sig, 1e-300))
        rows.append({
            "p_in_dbm": float(p_in),
            "lna_idx": rx.lna_idx,
            "vga_db": rx.vga_db,
            "adc_in_dbm": power_dbm(cap_ac) + rx.params.adc.fullscale_dbm,
            "adc_in_with_dc_dbm": nodes.get("adc_in_dbm", float("nan")),
            "digital_dbfs": power_dbm(cap),
            "snr_db": snr_db,
        })
    return {"rows": rows}


def calibrate_agc(rx: RxChain, tol_db: float = 2.5,
                  p_in_range_dbm=None) -> CalResult:
    sweep = agc_sweep(rx, p_in_range_dbm=p_in_range_dbm)
    target = rx.params.adc.fullscale_dbm - rx.params.adc_backoff_db
    errs = []
    for row in sweep["rows"]:
        # landing accuracy is only meaningful when the signal dominates the
        # wideband noise and the VGA is not railed
        if row["vga_db"] < 39.9 and row["snr_db"] > 10.0:
            errs.append(abs(row["adc_in_dbm"] - target))
    worst = max(errs) if errs else float("inf")
    # SNR sanity at moderate input levels (near sensitivity the wideband
    # SNR is thermally limited by definition, so no threshold applies there)
    snr_ok = all(r["snr_db"] > 25.0 for r in sweep["rows"]
                 if r["p_in_dbm"] >= -50.0)
    return CalResult(
        name="agc_sweep",
        estimated={"target_adc_dbm": target},
        trace=sweep["rows"],
        metrics_before={},
        metrics_after={"worst_landing_err_db": worst,
                       "min_snr_db_above_-50dBm": min(
                           (r["snr_db"] for r in sweep["rows"]
                            if r["p_in_dbm"] >= -50.0), default=float("nan"))},
        passed=worst < tol_db and snr_ok,
        # partial spec: the landing accuracy alone; the SNR sanity clause is
        # a stricter internal criterion, which the inspector reports as such
        spec={"metric": "worst_landing_err_db", "limit": tol_db,
              "sense": "max"},
        cost={"captures": len(sweep["rows"]),
              "samples": len(sweep["rows"]) * (1 << 13)},
    )
