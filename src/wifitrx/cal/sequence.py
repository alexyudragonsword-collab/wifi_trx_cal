"""Canonical power-up calibration sequence.

Order rationale (each step's estimate would be corrupted by the ones before
it being uncalibrated):

1. LPF corner (TX, RX)   — corner error distorts every later frequency-
                           domain estimate.
2. RX DC offset          — the loopback DC region must read TX LO leakage,
                           not RX DC.
3. TX LO leakage         — envelope detector first (RX-independent), then
                           loopback DC-bin refinement; must precede TX IQ
                           because carrier leakage corrupts near-DC image
                           bins.
4. Loopback delay        — measured and reported; all FFT-bin calibrations
                           delay-align their captures.
5. TX freq-dep IQ        — RX-LO-offset method; group-delay mismatch
                           verified from the measured rho(f) phase slope.
6. RX freq-dep IQ        — tone sweep through the now-clean TX.
7. TX power              — needs a clean TX so measured power is
                           wanted-signal power.
8. DPD                   — last: identification learns any residual
                           observation-path impairment into coefficients.
9. AGC verification      — final system check with all corrections active.
"""
from __future__ import annotations

import numpy as np

from ..chain.loopback import LoopbackPath, run_loopback
from ..chain.rx import RxChain
from ..chain.tx import TxChain
from ..metrics import evm
from ..units import power_dbm
from ..metrics.cpe import correct_cpe
from ..waveform.ofdm import OFDMConfig, demodulate_ofdm, generate_ofdm
from .agc_cal import calibrate_agc
from .base import CalResult
from .dpd_cal import calibrate_dpd
from .group_delay import verify_gd_estimate
from .lpf_corner import calibrate_lpf_corner_rx, calibrate_lpf_corner_tx
from .rx_dc import calibrate_rx_dc
from .rx_iip2 import calibrate_rx_iip2
from .rx_iq import calibrate_rx_iq
from .sync import _fractional_advance, align_delay
from .tx_iq import calibrate_tx_iq, measure_tx_rho
from .tx_lo_leak import (calibrate_tx_lo_leak_envdet,
                         calibrate_tx_lo_leak_loopback)
from .tx_power import calibrate_tx_power


def agc_for_loopback(tx: TxChain, rx: RxChain, path: LoopbackPath,
                     x_probe: np.ndarray) -> None:
    """Set the RX gain for the actual coupled TX power."""
    p_rx_in = power_dbm(tx(x_probe)) - path.atten_db
    rx.agc(p_rx_in)


def capture_aligned(tx: TxChain, rx: RxChain, path: LoopbackPath,
                    x: np.ndarray, n_warmup: int = 512,
                    seed: int = 0) -> np.ndarray:
    """Loopback capture with a cyclic warm-up prefix (settles the IIR
    baseband filters — their startup transient otherwise corrupts the
    first OFDM symbol), delay-aligned and trimmed back to len(x)."""
    xp = np.concatenate([x[-n_warmup:], x])
    cap = run_loopback(tx, rx, xp, path, seed=seed)
    _, _, info = align_delay(xp, cap, max_lag=1024)
    cap = _fractional_advance(cap, info["lag_total"])
    return cap[n_warmup:]


def tx_evm(tx: TxChain, cfg: OFDMConfig, drive_scale: float = 0.15,
           n_warmup: int = 512, seed: int = 0) -> float:
    """TX EVM at the PA output (the 802.11be TX spec measurement point):
    per-tone EQ + CPE removal, as a standard-compliant test receiver does.
    A cyclic warm-up prefix settles the TX baseband filter and the capture
    is delay-aligned before demodulation."""
    wf = generate_ofdm(cfg)
    x = wf.x * drive_scale
    xp = np.concatenate([x[-n_warmup:], x])
    y = tx(xp)
    _, _, info = align_delay(xp, y, max_lag=256)
    y = _fractional_advance(y, info["lag_total"])[n_warmup:]
    g = np.vdot(x, y) / np.vdot(x, x)
    syms = demodulate_ofdm(y / g / drive_scale, wf)
    syms = correct_cpe(syms, wf.tx_symbols)
    return evm(syms, wf.tx_symbols, equalize="per_tone").db


def loopback_evm(tx: TxChain, rx: RxChain, path: LoopbackPath,
                 cfg: OFDMConfig, drive_scale: float = 0.25,
                 seed: int = 0) -> float:
    """End-to-end loopback EVM (per-tone EQ + CPE removal, modem-style)."""
    wf = generate_ofdm(cfg)
    x = wf.x * drive_scale
    agc_for_loopback(tx, rx, path, x)
    cap = capture_aligned(tx, rx, path, x, seed=seed)
    g = np.vdot(x, cap) / np.vdot(x, x)
    syms = demodulate_ofdm(cap / g / drive_scale, wf)
    syms = correct_cpe(syms, wf.tx_symbols)
    return evm(syms, wf.tx_symbols, equalize="per_tone").db


def measure_loopback_delay(tx: TxChain, rx: RxChain, path: LoopbackPath,
                           cfg: OFDMConfig) -> CalResult:
    wf = generate_ofdm(cfg)
    x = wf.x * 0.2
    cap = run_loopback(tx, rx, x, path)
    _, _, info = align_delay(x, cap, max_lag=4096)
    delay_ns = info["lag_total"] / tx.fs * 1e9
    return CalResult(
        name="loopback_delay",
        estimated={"delay_samples": info["lag_total"], "delay_ns": delay_ns},
        metrics_after={"delay_ns": delay_ns},
        passed=True,
        notes="captures in later cals are aligned with this estimate",
    )


def run_full_cal(tx: TxChain, rx: RxChain, cfg: OFDMConfig,
                 path: LoopbackPath | None = None,
                 with_dpd: bool = True, target_pout_dbm: float | None = None,
                 final_drive_scale: float = 0.12, seed: int = 0) -> list[CalResult]:
    """Execute the canonical sequence; returns the ordered CalResult list.

    ``final_drive_scale=0.12`` puts the final EVM check at ~16.5 dB PA
    output backoff (~11.6 dBm average out for the 26 dB-gain / 28 dBm-Psat
    default TX) — a typical 4096-QAM operating point: OFDM PAPR plus the
    EVM headroom the -38 dB MCS13 requirement demands.
    """
    if path is None:
        path = LoopbackPath(atten_db=40.0, delay_ns=6.0)
    results: list[CalResult] = []

    evm_before = loopback_evm(tx, rx, path, cfg, drive_scale=final_drive_scale,
                              seed=seed)

    # 1. LPF corners
    results.append(calibrate_lpf_corner_tx(tx))
    results.append(calibrate_lpf_corner_rx(rx))
    # 2. RX DC
    results.append(calibrate_rx_dc(rx))
    # 3. TX LO leakage
    results.append(calibrate_tx_lo_leak_envdet(tx))
    offset_path = LoopbackPath(atten_db=path.atten_db, delay_ns=path.delay_ns,
                               rx_lo_offset_hz=4.8e6)
    results.append(calibrate_tx_lo_leak_loopback(tx, rx, offset_path))
    # 3.5 RX IIP2 — MUST follow TX LO-leak cal: the PA's third-order
    # product tone2 x leak x tone1* lands exactly on the (f2 - f1) IM2
    # measurement bin, and with an uncalibrated carrier leak it buries the
    # IM2 null by ~35 dB.
    if rx.params.im2.enabled:
        results.append(calibrate_rx_iip2(tx, rx, LoopbackPath(
            atten_db=path.atten_db - 10.0, delay_ns=path.delay_ns)))
    # 4. loopback delay (AGC set for the coupled level first)
    wf_probe = generate_ofdm(cfg)
    agc_for_loopback(tx, rx, path, wf_probe.x * 0.25)
    results.append(measure_loopback_delay(tx, rx, path, cfg))
    # 5. TX IQ + group-delay verification.  The correction FIR tap count
    # scales with the oversampling ratio so its time span (and hence its
    # frequency resolution across the signal band) stays constant.
    n_taps = 2 * int(7.5 * tx.fs / tx.params.bandwidth_hz) + 1
    iq_path = LoopbackPath(atten_db=path.atten_db, delay_ns=path.delay_ns,
                           rx_lo_offset_hz=5.1e6)
    res_txiq = calibrate_tx_iq(tx, rx, iq_path, n_taps=n_taps)
    results.append(res_txiq)
    rho_f = np.asarray(res_txiq.estimated["rho_f_hz"])
    rho_v = np.asarray(res_txiq.estimated["rho"])
    inj_gd = tx.params.iq.gd_mismatch_ps if tx.params.iq.enabled else 0.0
    results.append(verify_gd_estimate(rho_f, rho_v, inj_gd, tol_ps=80.0))
    # 6. RX IQ
    results.append(calibrate_rx_iq(tx, rx, LoopbackPath(
        atten_db=path.atten_db, delay_ns=path.delay_ns), n_taps=n_taps))
    # 7. TX power
    wf = generate_ofdm(cfg)
    results.append(calibrate_tx_power(tx, wf.x * 0.25,
                                      target_dbm=target_pout_dbm))
    # 8. DPD (trained at the final operating drive)
    if with_dpd:
        results.append(calibrate_dpd(tx, rx, wf, path,
                                     drive_scale=final_drive_scale))
    # 9. AGC verification
    results.append(calibrate_agc(rx))

    evm_after = loopback_evm(tx, rx, path, cfg, drive_scale=final_drive_scale,
                             seed=seed)
    results.append(CalResult(
        name="final_loopback_evm",
        metrics_before={"evm_db": evm_before},
        metrics_after={"evm_db": evm_after,
                       "tx_evm_db": tx_evm(tx, cfg,
                                           drive_scale=final_drive_scale)},
        passed=evm_after < evm_before,
        notes="evm_db: composite TX+RX loopback EVM; tx_evm_db: PA-output "
              "EVM at the 802.11be TX spec measurement point (per-tone EQ "
              "+ CPE removal in both)",
    ))
    return results
