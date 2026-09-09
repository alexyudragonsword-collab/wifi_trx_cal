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

from dataclasses import replace

import numpy as np

from ..chain.agc import CAL_OBSERVATION_STATE
from ..chain.loopback import LoopbackPath, run_loopback
from ..chain.rx import RxChain
from ..chain.tx import TxChain
from ..metrics import evm
from ..units import power_dbm
from ..metrics.cpe import correct_cpe, correct_cpe_pilots
from ..waveform.ofdm import OFDMConfig, demodulate_ofdm, generate_ofdm
from ..waveform.pilots import generate_ofdm_with_pilots, pilot_sequence
from ..waveform.preamble import (DEFAULT_CE_SMOOTH_TONES, apply_cfo, build_frame,
                                 channel_estimate, estimate_cfo, smooth_channel_estimate)
from .agc_cal import calibrate_agc
from .base import CalResult
from .deps import planned_steps, validate_order
from .dpd_cal import calibrate_dpd
from .group_delay import verify_gd_estimate
from .lpf_corner import calibrate_lpf_corner_rx, calibrate_lpf_corner_tx
from .rx_dc import calibrate_rx_dc
from .rx_iip2 import calibrate_rx_iip2
from .rx_iq import calibrate_rx_iq
from .sync import align_delay, compensate_delay
from .tracking import pilot_cfo_hz
from .tx_iq import calibrate_tx_iq
from .tx_lo_leak import (calibrate_tx_lo_leak_envdet,
                         calibrate_tx_lo_leak_loopback)
from .tx_power import calibrate_tx_power


def agc_for_loopback(tx: TxChain, rx: RxChain, path: LoopbackPath,
                     x_probe: np.ndarray) -> None:
    """Set the RX gain for the actual coupled TX power, pinned to the
    calibration observation state (see agc.CAL_OBSERVATION_STATE)."""
    p_rx_in = power_dbm(tx(x_probe)) - path.atten_db
    rx.agc_pinned(p_rx_in, CAL_OBSERVATION_STATE)


def capture_aligned(tx: TxChain, rx: RxChain, path: LoopbackPath,
                    x: np.ndarray, n_warmup: int = 512,
                    n_guard: int = 64, seed: int = 0) -> np.ndarray:
    """Loopback capture with a cyclic warm-up prefix (settles the IIR
    baseband filters — their startup transient otherwise corrupts the
    first OFDM symbol) and a cyclic guard tail (delay compensation must
    not run off the end of the frame), delay-aligned and trimmed back to
    len(x)."""
    xp = np.concatenate([x[-n_warmup:], x, x[:n_guard]])
    cap = run_loopback(tx, rx, xp, path, seed=seed)
    _, _, info = align_delay(xp, cap, max_lag=n_guard // 2)
    return compensate_delay(cap, info["lag_total"], n_warmup, len(x))


def scoring_frame(cfg: OFDMConfig):
    """The EVM scoring stimulus: [GI2 | LTF | LTF | data] with the
    standard's pilot set on the data symbols and one extra padding
    symbol (see ``tx_snapshot``).  Returns (frame, pilot_cols, pilots).
    One deterministic frame per config, so the three views (loopback /
    TX / RX) and every caller score the same waveform."""
    cfg_pad = replace(cfg, n_symbols=cfg.n_symbols + 1)
    wf, cols = generate_ofdm_with_pilots(cfg_pad)
    frame = build_frame(cfg_pad, data=wf)
    return frame, cols, pilot_sequence(cfg_pad.n_symbols, cols.size)


def score_views(y: np.ndarray, frame, cols: np.ndarray, pilots: np.ndarray,
                n_symbols: int, ce_smooth_tones: int = DEFAULT_CE_SMOOTH_TONES) -> dict:
    """Both EVM views of one captured, delay-aligned, gain-normalised
    frame ``y`` (same sample scale as ``frame.x``), data tones only:

    ``evm_db`` — the isolation view: per-tone LS equaliser fitted
    against the ideal reference over all scored symbols and genie CPE
    (every tone vs the reference).  What the impairments alone leave;
    the closure target of the residual replay, since a receiver's own
    estimation losses are not a residual of the chain.

    ``evm_modem_db`` — the modem form: coarse CFO from the LTF pair,
    fine CFO from the slope of the pilots' common phase across the
    frame, the LTF-pair channel estimate smoothed over
    ``ce_smooth_tones`` adjacent tones and frozen for the packet, then
    the N_p-pilot CPE per symbol — what a standard receiver actually
    reads.  On a noise-only chain and no smoothing it sits above the
    isolation view by exactly the two estimator terms the phase-noise
    study measures, 10 log(1 + rho/2) for the frozen LTF error and
    10 log(1 + 1/(2 N_p)) for the pilot noise (1.90 dB measured vs 1.89
    at 80 MHz).  On the calibrated chain the raw estimate also freezes
    the LTF pattern's share of the residual IQ image and PA distortion
    into H — 5.2 dB above the isolation view at 320 MHz / 4096-QAM —
    which the smoothing removes because that share flips sign tone to
    tone while the channel does not (1.0 dB at 9 tones).  The MCS13
    -38 dB verdict binds this view.
    """
    cfg = frame.config
    fs = cfg.sample_rate_hz
    n = n_symbols
    data = np.ones(cfg.n_active, dtype=bool)
    data[cols] = False
    ref = frame.data.tx_symbols[:n]
    syms = demodulate_ofdm(y[frame.preamble_len:], frame.data)[:n]
    genie = correct_cpe(syms, ref)
    # modem form
    y_acq = apply_cfo(y, -estimate_cfo(y, frame, fs), fs)
    syms_acq = demodulate_ofdm(y_acq[frame.preamble_len:], frame.data)
    y_acq = apply_cfo(y_acq, -pilot_cfo_hz(syms_acq, cols, pilots, cfg, fs), fs)
    h = smooth_channel_estimate(channel_estimate(y_acq, frame), ce_smooth_tones)
    req = demodulate_ofdm(y_acq[frame.preamble_len:], frame.data)[:n] / h
    modem = correct_cpe_pilots(req, cols, pilots[:n])
    p_ref = float((np.abs(ref[:, data]) ** 2).mean())
    err = float((np.abs(modem[:, data] - ref[:, data]) ** 2).mean())
    return {"evm_db": float(evm(genie[:, data], ref[:, data], equalize="per_tone").db),
            "evm_modem_db": float(10.0 * np.log10(err / p_ref)),
            "syms_eq": _equalize_per_tone(genie, ref)[:, data],
            "syms_modem": modem[:, data],
            "ref_syms": ref[:, data],
            "n_pilots": int(cols.size),
            "ce_smooth_tones": int(ce_smooth_tones)}


def tx_snapshot(tx: TxChain, cfg: OFDMConfig, drive_scale: float = 0.15,
                n_warmup: int = 512, n_guard: int = 64,
                ce_smooth_tones: int = DEFAULT_CE_SMOOTH_TONES) -> dict:
    """PA-output EVM plus the equalized constellation, as a
    standard-compliant test receiver sees it (the 802.11be TX spec
    measurement point), in both views of ``score_views``: the isolation
    view (per-tone EQ + genie CPE) and the modem form (LTF CFO
    acquisition + LTF channel estimate + pilot CPE).  A cyclic warm-up
    prefix settles the TX baseband filter, a cyclic guard tail keeps
    delay compensation inside the frame, and the capture is
    delay-aligned before demodulation.

    One extra padding symbol is transmitted and excluded from the score
    (lab practice: measure interior symbols).  The burst's final symbol
    is edge-contaminated by construction: delay compensation advances
    its FFT window a few samples past the burst end, where the truncated
    window ramp-down makes the continuation unrepresentative — worth
    >8 dB of bias on deep (<-55 dB) floors at small n_symbols."""
    frame, cols, pilots = scoring_frame(cfg)
    x = frame.x * drive_scale
    xp = np.concatenate([x[-n_warmup:], x, x[:n_guard]])
    y = tx(xp)
    _, _, info = align_delay(xp, y, max_lag=n_guard // 2)
    y = compensate_delay(y, info["lag_total"], n_warmup, len(x))
    g = np.vdot(x, y) / np.vdot(x, x)
    out = score_views(y / g / drive_scale, frame, cols, pilots, cfg.n_symbols,
                      ce_smooth_tones)
    out["bandwidth_hz"] = cfg.bandwidth_hz
    return out


def tx_evm(tx: TxChain, cfg: OFDMConfig, drive_scale: float = 0.15,
           n_warmup: int = 512, n_guard: int = 64, seed: int = 0) -> float:
    """TX EVM at the PA output; see ``tx_snapshot`` for the measurement
    conventions."""
    return tx_snapshot(tx, cfg, drive_scale=drive_scale,
                       n_warmup=n_warmup, n_guard=n_guard)["evm_db"]


def rx_snapshot(rx: RxChain, cfg: OFDMConfig, p_in_dbm: float,
                n_warmup: int = 512, n_guard: int = 64,
                seed: int = 0, ce_smooth_tones: int = DEFAULT_CE_SMOOTH_TONES) -> dict:
    """Receive-direction counterpart of ``tx_snapshot``: an ideal
    transmitted waveform at ``p_in_dbm`` RF input into the (impaired,
    possibly calibrated) RX chain, AGC engaged.  The LO here is
    independent of the transmitter's — phase noise counts in full,
    unlike the loopback view where the shared synthesizer cancels it.
    Same capture conventions: cyclic warm-up prefix and guard tail,
    integer-slice + fractional delay compensation, one padding symbol
    transmitted and excluded from the score, both views of
    ``score_views``."""
    frame, cols, pilots = scoring_frame(cfg)
    amp = 10.0 ** ((p_in_dbm - power_dbm(frame.data.x)) / 20.0)
    x = frame.x * amp
    rx.agc(p_in_dbm)
    xp = np.concatenate([x[-n_warmup:], x, x[:n_guard]])
    y = rx(xp, rng=np.random.default_rng(seed))
    _, _, info = align_delay(xp, y, max_lag=n_guard // 2)
    y = compensate_delay(y, info["lag_total"], n_warmup, len(x))
    g = np.vdot(x, y) / np.vdot(x, x)
    out = score_views(y / g / amp, frame, cols, pilots, cfg.n_symbols,
                      ce_smooth_tones)
    out["p_in_dbm"] = p_in_dbm
    out["bandwidth_hz"] = cfg.bandwidth_hz
    return out


def _equalize_per_tone(syms: np.ndarray, ref: np.ndarray) -> np.ndarray:
    """Apply the modem-style per-tone LS equalizer (for constellation plots;
    the EVM metric does its own equalization internally)."""
    g = (np.sum(np.conj(ref) * syms, axis=0)
         / np.maximum(np.sum(np.abs(ref) ** 2, axis=0), 1e-30))
    return syms / np.where(np.abs(g) > 1e-12, g, 1.0)


def loopback_snapshot(tx: TxChain, rx: RxChain, path: LoopbackPath,
                      cfg: OFDMConfig, drive_scale: float = 0.25,
                      seed: int = 0,
                      ce_smooth_tones: int = DEFAULT_CE_SMOOTH_TONES) -> dict:
    """Loopback EVM plus the raw material for before/after figures:
    equalized constellation symbols and the PA-output waveform.

    Transmits one extra padding symbol and scores interior symbols only,
    like ``tx_evm`` (the burst's final symbol is edge-contaminated once
    delay compensation advances its FFT window past the burst end)."""
    frame, cols, pilots = scoring_frame(cfg)
    x = frame.x * drive_scale
    agc_for_loopback(tx, rx, path, x)
    y_pa = tx(x)
    cap = capture_aligned(tx, rx, path, x, seed=seed)
    g = np.vdot(x, cap) / np.vdot(x, x)
    out = score_views(cap / g / drive_scale, frame, cols, pilots, cfg.n_symbols,
                      ce_smooth_tones)
    out.update({"pa_out": y_pa, "fs": tx.fs, "bandwidth_hz": cfg.bandwidth_hz})
    return out


def loopback_evm(tx: TxChain, rx: RxChain, path: LoopbackPath,
                 cfg: OFDMConfig, drive_scale: float = 0.25,
                 seed: int = 0) -> float:
    """End-to-end loopback EVM (per-tone EQ + CPE removal, modem-style)."""
    return loopback_snapshot(tx, rx, path, cfg, drive_scale, seed)["evm_db"]


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
        cost={"captures": 1, "samples": x.size},
    )


# capture-length / iteration knobs per calibration profile
PROFILES = {
    # exhaustive: full code sweeps, long captures, 2 IQ iterations
    "factory": {"lpf_search": "full", "n_iq": 1 << 15, "iq_iters": 2,
                "iq_tones": 12, "n_scalar": 1 << 14, "envdet_leak": True,
                "iip2_iters": 3, "iip2_avg": 4, "power_step_db": 1.0,
                "agc_step_db": 5.0},
    # power-on fast cal: bisection code search, half-length captures,
    # single IQ iteration, loopback-only LO-leak
    "poweron": {"lpf_search": "binary", "n_iq": 1 << 14, "iq_iters": 1,
                "iq_tones": 8, "n_scalar": 1 << 13, "envdet_leak": False,
                "iip2_iters": 2, "iip2_avg": 2, "power_step_db": 3.0,
                "agc_step_db": 10.0},
}


def run_full_cal(tx: TxChain, rx: RxChain, cfg: OFDMConfig,
                 path: LoopbackPath | None = None,
                 with_dpd: bool = True, target_pout_dbm: float | None = None,
                 final_drive_scale: float = 0.12, profile: str = "factory",
                 seed: int = 0,
                 on_step=None) -> list[CalResult]:
    """Execute the canonical sequence; returns the ordered CalResult list.

    ``final_drive_scale=0.12`` puts the final EVM check at ~16.5 dB PA
    output backoff (~11.6 dBm average out for the 26 dB-gain / 28 dBm-Psat
    default TX) — a typical 4096-QAM operating point: OFDM PAPR plus the
    EVM headroom the -38 dB MCS13 requirement demands.

    ``profile`` selects the capture-time budget: "factory" (exhaustive)
    or "poweron" (fast: bisection searches, shorter captures, single IQ
    iteration — a fraction of the capture time at a small EVM cost).

    ``on_step``, if given, is called with each CalResult right after its
    step completes (the GUI step-through mode hooks per-step snapshots
    here).  Observers must follow the reader contract pinned by
    tests/test_observers.py: they may capture through the chains but must
    leave every calibration correction untouched, and should save/restore
    the AGC runtime state so later steps see the level the sequence set.
    """
    if path is None:
        from ..chain.loopback import recommended_loopback_atten_db
        path = LoopbackPath(
            atten_db=recommended_loopback_atten_db(cfg.bandwidth_hz),
            delay_ns=6.0)
    prof = PROFILES[profile]
    # Validate the ordering constraints on the *plan*, before the first
    # capture: a mis-ordered calibration converges on a wrong answer
    # instead of failing, so runtime is too late to notice.
    plan = planned_steps(prof, with_iip2=rx.params.im2.enabled,
                         with_dpd=with_dpd)
    validate_order(plan)
    results: list[CalResult] = []

    def _emit(r: CalResult) -> None:
        results.append(r)
        if on_step is not None:
            on_step(r)

    snap_before = loopback_snapshot(tx, rx, path, cfg,
                                    drive_scale=final_drive_scale, seed=seed)
    evm_before = snap_before["evm_db"]

    # 1. LPF corners
    _emit(calibrate_lpf_corner_tx(tx, n=prof["n_scalar"],
                                           search=prof["lpf_search"]))
    _emit(calibrate_lpf_corner_rx(rx, n=prof["n_scalar"],
                                           search=prof["lpf_search"]))
    # 2. RX DC
    _emit(calibrate_rx_dc(rx, n=prof["n_scalar"]))
    # 3. TX LO leakage
    if prof["envdet_leak"]:
        _emit(calibrate_tx_lo_leak_envdet(tx))
    offset_path = LoopbackPath(atten_db=path.atten_db, delay_ns=path.delay_ns,
                               rx_lo_offset_hz=4.8e6)
    _emit(calibrate_tx_lo_leak_loopback(tx, rx, offset_path,
                                                 n=prof["n_scalar"]))
    # 3.5 RX IIP2 — MUST follow TX LO-leak cal: the PA's third-order
    # product tone2 x leak x tone1* lands exactly on the (f2 - f1) IM2
    # measurement bin, and with an uncalibrated carrier leak it buries the
    # IM2 null by ~35 dB.
    if rx.params.im2.enabled:
        # hotter than the main path for IM2 beat SNR, but never below
        # 30 dB: with the 320 MHz cal coupler at 34 dB, "-10" would put
        # the two-tone at -2 dBm and compress even the last gain state
        # (IM3 ~20 dBc), corrupting the two-level cancellation
        _emit(calibrate_rx_iip2(
            tx, rx, LoopbackPath(atten_db=max(path.atten_db - 10.0, 30.0),
                                 delay_ns=path.delay_ns),
            n=prof["n_scalar"], n_iter=prof["iip2_iters"],
            n_avg=prof["iip2_avg"]))
    # 4. loopback delay (AGC set for the coupled level first)
    wf_probe = generate_ofdm(cfg)
    agc_for_loopback(tx, rx, path, wf_probe.x * 0.25)
    _emit(measure_loopback_delay(tx, rx, path, cfg))
    # 5. TX IQ + group-delay verification.  The correction FIR tap count
    # scales with the oversampling ratio so its time span (and hence its
    # frequency resolution across the signal band) stays constant.
    n_taps = 2 * int(7.5 * tx.fs / tx.params.bandwidth_hz) + 1
    iq_path = LoopbackPath(atten_db=path.atten_db, delay_ns=path.delay_ns,
                           rx_lo_offset_hz=5.1e6)
    res_txiq = calibrate_tx_iq(tx, rx, iq_path, n_taps=n_taps,
                               n=prof["n_iq"], n_iter=prof["iq_iters"],
                               n_tones=prof["iq_tones"])
    _emit(res_txiq)
    rho_f = np.asarray(res_txiq.estimated["rho_f_hz"])
    rho_v = np.asarray(res_txiq.estimated["rho"])
    inj_gd = tx.params.iq.gd_mismatch_ps if tx.params.iq.enabled else 0.0
    _emit(verify_gd_estimate(rho_f, rho_v, inj_gd, tol_ps=80.0))
    # 6. RX IQ
    _emit(calibrate_rx_iq(tx, rx, LoopbackPath(
        atten_db=path.atten_db, delay_ns=path.delay_ns), n_taps=n_taps,
        n=prof["n_iq"], n_iter=prof["iq_iters"], n_tones=prof["iq_tones"]))
    # 7. TX power
    wf = generate_ofdm(cfg)
    _emit(calibrate_tx_power(
        tx, wf.x * 0.25, target_dbm=target_pout_dbm,
        codes_db=np.arange(-20.0, 6.5, prof["power_step_db"])))
    # 8. DPD (trained at the final operating drive).  The ILA is
    # bias-sensitive but noise-tolerant: LS averaging removes thermal
    # noise, while systematic RX third-order distortion gets LEARNED
    # into the predistorter and re-applied (ACLR regression).  The DPD
    # observation therefore always uses the cold coupler point
    # (>= 40 dB, RX IM3 >= 57 dBc) even when the IQ/EVM observations
    # run at the hot 320 MHz cal point (34 dB, IM3 ~45 dBc).
    if with_dpd:
        dpd_path = replace(path, atten_db=max(path.atten_db, 40.0))
        _emit(calibrate_dpd(tx, rx, wf, dpd_path,
                            drive_scale=final_drive_scale))
    # 9. AGC verification
    _emit(calibrate_agc(
        rx, p_in_range_dbm=np.arange(-85.0, -5.0, prof["agc_step_db"])))

    snap_after = loopback_snapshot(tx, rx, path, cfg,
                                   drive_scale=final_drive_scale, seed=seed)
    evm_after = snap_after["evm_db"]
    snap_tx = tx_snapshot(tx, cfg, drive_scale=final_drive_scale)
    # RX-direction EVM at the level the loopback actually delivers, so
    # the three views (loopback / TX / RX) share one operating point
    p_rx_dbm = power_dbm(snap_after["pa_out"]) - path.atten_db
    snap_rx = rx_snapshot(rx, cfg, p_rx_dbm)
    # The receive-side deliverable figures, measured at that same
    # operating point: effective NF (idle channel through the whole
    # chain) and post-tracking phase error.  Without them the residual
    # surface is transmit-heavy and the receive view's dominant error
    # sources travel nowhere.
    from .rx_figures import (measure_rx_im3_dbc, measure_rx_nf_db,
                             measure_rx_phase_err_dbc)
    rx_nf_db = measure_rx_nf_db(rx, cfg, p_rx_dbm)
    rx_phase_err_dbc = measure_rx_phase_err_dbc(rx, cfg, p_rx_dbm, rx_nf_db)
    rx_im3_dbc = measure_rx_im3_dbc(rx, cfg, p_rx_dbm)
    total_samples = sum(r.cost.get("samples", 0) for r in results)
    total_captures = sum(r.cost.get("captures", 0) for r in results)
    _emit(CalResult(
        name="final_loopback_evm",
        metrics_before={"evm_db": evm_before},
        metrics_after={"evm_db": evm_after,
                       "tx_evm_db": snap_tx["evm_db"],
                       "rx_evm_db": snap_rx["evm_db"],
                       "evm_modem_db": snap_after["evm_modem_db"],
                       "tx_evm_modem_db": snap_tx["evm_modem_db"],
                       "rx_evm_modem_db": snap_rx["evm_modem_db"],
                       "rx_input_dbm": p_rx_dbm,
                       "rx_gain_state": rx.lna_idx,
                       "rx_nf_db": rx_nf_db,
                       "rx_phase_err_dbc": rx_phase_err_dbc,
                       "rx_im3_dbc": rx_im3_dbc,
                       "capture_time_ms": total_samples / tx.fs * 1e3,
                       "total_captures": total_captures},
        passed=evm_after < evm_before,
        # the MCS13 TX EVM spec only binds the full (DPD) flow; a no-DPD
        # run targets lower MCS and carries no embedded spec.  It binds
        # the modem-form reading (what a standard receiver measures),
        # not the isolation view (0.7.18; before that the genie view was
        # gated, ~2 dB optimistic)
        spec={"metric": "tx_evm_modem_db", "limit": -38.0, "sense": "max"}
             if with_dpd else {},
        notes="evm_db: composite TX+RX loopback EVM (shared LO — phase "
              "noise cancels); tx_evm_db: PA-output EVM at the 802.11be "
              "TX spec measurement point; rx_evm_db: ideal waveform into "
              "the RX at the loopback's coupled level (independent LO). "
              "Each in two views: *_evm_db is the isolation view (per-tone "
              "EQ vs the ideal reference + genie CPE, the replay's closure "
              "target); *_evm_modem_db is the modem form (LTF CFO "
              "acquisition + LTF channel estimate smoothed over "
              f"{DEFAULT_CE_SMOOTH_TONES} tones + pilot CPE, the spec "
              f"verdict's input); profile={profile}",
        artifacts={"snapshot_before": snap_before,
                   "snapshot_after": snap_after,
                   "snapshot_tx": snap_tx,
                   "snapshot_rx": snap_rx},
    ))
    # The validated plan is only worth anything if it matches what actually
    # ran — this assert is what keeps planned_steps from drifting away from
    # the call sequence above.
    executed = [r.name for r in results]
    assert executed == plan, f"executed {executed} != planned {plan}"
    return results
