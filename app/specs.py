# Declarative analysis registry, pattern from adc_toolbox:app/analyses/spec.py
# (GUI form, worker invocation and the parametrized smoke test are all
# generated from these entries; worker code never touches pyplot).
"""wifitrx workbench analyses.

Adding an analysis = one AnalysisSpec entry: declarative params + a run
function returning AnalysisResult.  Every entry is exercised by the
parametrized smoke test in tests/test_gui_specs.py.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

import numpy as np
from matplotlib.figure import Figure

from wifitrx.cal.residuals import run_conditions


@dataclass(frozen=True)
class ParamSpec:
    name: str
    label: str
    kind: str = "float"          # 'float' | 'int' | 'bool' | 'choice'
    default: object = 0.0
    choices: tuple = ()
    minimum: float | None = None
    maximum: float | None = None
    tooltip: str = ""


@dataclass
class AnalysisResult:
    metrics: dict
    figure: Figure | None = None
    text: str = ""
    # optional cal-state material: {"tx_state","rx_state","results"} —
    # when present the main window offers "Save cal-state JSON…" so a
    # frozen exe (no examples/, no CLI) can still produce the deliverable
    # and feed the inspector tab
    cal_state: dict | None = None
    # optional multi-page output: ((title, Figure), ...).  When present
    # the main window shows a page selector; ``figure`` stays the
    # single-figure fallback (and the page shown by default)
    figures: tuple = ()


@dataclass(frozen=True)
class AnalysisSpec:
    key: str
    title: str
    params: tuple[ParamSpec, ...]
    run: Callable[[dict], AnalysisResult]
    description: str = ""


def new_figure(figsize=(8, 5)) -> Figure:
    return Figure(figsize=figsize)  # plain Figure: safe in worker threads


# ------------------------------------------------------------------ runs
def _chains(bw: float, seed: int, fs: float):
    from wifitrx.chain import RxChain, RxParams, TxChain, TxParams
    rng = np.random.default_rng(seed)
    txp = TxParams(bandwidth_hz=bw).randomize(rng)
    rxp = RxParams(bandwidth_hz=bw).randomize(rng)
    from wifitrx.chain.params import recommended_lpf_corner_hz
    txp.lpf.fc_nominal_hz = recommended_lpf_corner_hz(bw, "tx")
    rxp.lpf.fc_nominal_hz = recommended_lpf_corner_hz(bw, "rx")
    return TxChain(txp, fs), RxChain(rxp, fs)


def _five_panel(results, sb, sa, st, sr=None, rx_sweep=None,
                sa_title="loopback AFTER", suptitle=None) -> Figure:
    """The full-cal result page: four constellations (loopback before /
    loopback current / TX @ PA output / RX @ digital output — the
    loopback view cancels common-LO phase noise, the TX view is the
    802.11be spec measurement point where it counts, the RX view feeds
    an ideal waveform into the receiver with an independent LO), the
    PA-output PSD overlay, the RX EVM vs input power curve (when
    provided) and the per-step dB metrics of ``results``."""
    from wifitrx.metrics.spectrum import psd

    fig = new_figure(figsize=(13.5, 7))
    gs = fig.add_gridspec(2, 12)
    ax_cb = fig.add_subplot(gs[0, 0:3])
    ax_ca = fig.add_subplot(gs[0, 3:6])
    ax_ct = fig.add_subplot(gs[0, 6:9])
    ax_cr = fig.add_subplot(gs[0, 9:12])
    ax_psd = fig.add_subplot(gs[1, 0:4])
    ax_swp = fig.add_subplot(gs[1, 4:8])
    ax_bar = fig.add_subplot(gs[1, 8:12])

    panels = [(ax_cb, sb, "loopback BEFORE"),
              (ax_ca, sa, sa_title),
              (ax_ct, st, "TX @ PA out"),
              (ax_cr, sr, "RX @ digital out")]
    for ax, snap, title in panels:
        if snap is None:      # cal-states saved by older runs
            ax.set_axis_off()
            continue
        pts = np.ravel(snap["syms_eq"])
        if pts.size > 6000:
            idx = np.random.default_rng(0).choice(pts.size, 6000,
                                                  replace=False)
            pts = pts[idx]
        ax.plot(pts.real, pts.imag, ".", ms=1.0, alpha=0.5)
        ax.set_title(f"{title}\n(EVM {snap['evm_db']:.1f} dB)", fontsize=9)
        ax.set_aspect("equal")
        ax.set_xlim(-1.55, 1.55)
        ax.set_ylim(-1.55, 1.55)
        ax.grid(True, alpha=0.25)

    # PA-output PSD overlay (re-referenced to each curve's in-band median:
    # peak normalization would let the pre-cal LO-leak spike shift the
    # whole curve and fake the shoulder comparison)
    for snap, label in ((sb, "before"), (sa, "current")):
        if snap is None or "pa_out" not in snap:
            continue
        f, p = psd(snap["pa_out"], snap["fs"])
        inband = np.abs(f) < 0.4 * snap["bandwidth_hz"]
        ax_psd.plot(f / 1e6, p - np.median(p[inband]), lw=0.8, label=label)
    ax_psd.set_xlabel("Frequency [MHz]")
    ax_psd.set_ylabel("PSD [dB rel. in-band]")
    ax_psd.set_title("PA output spectrum", fontsize=9)
    ax_psd.set_ylim(-80, 25)
    ax_psd.legend(fontsize=8)
    ax_psd.grid(True, alpha=0.3)

    # RX EVM vs input power (final result page only)
    if rx_sweep is not None:
        if rx_sweep.get("evm_uncal") is not None:
            ax_swp.plot(rx_sweep["p_in"], rx_sweep["evm_uncal"], "o-",
                        ms=3, color="tab:blue", label="uncalibrated")
        ax_swp.plot(rx_sweep["p_in"], rx_sweep["evm"], "s-", ms=3,
                    color="tab:orange", label="calibrated")
        ax_swp.axhline(rx_sweep["req_db"], ls="--", lw=0.8, color="gray")
        ax_swp.annotate(rx_sweep["label"],
                        (rx_sweep["p_in"][0], rx_sweep["req_db"]),
                        fontsize=7, va="bottom", color="gray")
        ax_swp.plot(*rx_sweep["op"], "o", ms=7, mfc="none",
                    color="tab:red", label="loopback op. point")
        p_lo, p_hi = rx_sweep["p_in"][0], rx_sweep["p_in"][-1]
        for p_th, lbl in rx_sweep.get("agc", ()):
            if p_lo <= p_th <= p_hi:
                ax_swp.axvline(p_th, ls="-.", lw=0.7, color="tab:purple",
                               alpha=0.7)
                ax_swp.annotate(lbl, (p_th, 3.0), fontsize=6, rotation=90,
                                ha="right", va="top", color="tab:purple")
        ax_swp.set_xlabel("RF input [dBm]")
        ax_swp.set_ylabel("EVM [dB]")
        ax_swp.set_title("RX EVM vs input power", fontsize=9)
        ax_swp.set_ylim(-60, 5)
        ax_swp.legend(fontsize=7)
        ax_swp.grid(True, alpha=0.3)
    else:
        ax_swp.set_axis_off()

    # per-step dB metrics
    names, befores, afters = [], [], []
    for r in results:
        for key in r.metrics_after:
            kb = r.metrics_before.get(key)
            ka = r.metrics_after.get(key)
            # keep only dB-scale scalars: a mixed-unit bar chart (Hz next
            # to dB) is unreadable
            if (isinstance(kb, (int, float)) and isinstance(ka, (int, float))
                    and abs(kb) < 200 and abs(ka) < 200
                    and ("db" in key or "dbc" in key or "dbfs" in key)):
                names.append(f"{r.name}\n{key}")
                befores.append(float(kb))
                afters.append(float(ka))
                break
    xpos = np.arange(len(names))
    ax_bar.bar(xpos - 0.2, befores, 0.4, label="before")
    ax_bar.bar(xpos + 0.2, afters, 0.4, label="after")
    ax_bar.set_xticks(xpos)
    ax_bar.set_xticklabels(names, rotation=40, ha="right", fontsize=5)
    ax_bar.set_ylabel("dB")
    ax_bar.set_title("Per-step dB metrics", fontsize=9)
    ax_bar.legend(fontsize=8)
    ax_bar.grid(True, alpha=0.3)
    if suptitle:
        fig.suptitle(suptitle, fontsize=11)
        fig.tight_layout(rect=(0, 0, 1, 0.96))
    else:
        fig.tight_layout()
    return fig


def _cal_setup(p: dict):
    from wifitrx.chain import LoopbackPath
    from wifitrx.waveform import OFDMConfig

    bw = float(p["bw_mhz"]) * 1e6
    if p.get("std", "11ax/be") == "11ac/n":
        if bw > 160e6:
            raise ValueError("802.11ac/n supports at most 160 MHz — "
                             "select the 11ax/be standard for 320 MHz")
        # legacy numerology: 312.5 kHz spacing, 3.2 us symbol, 0.8 us
        # long GI; 4x the symbol count keeps the capture length (and
        # hence every estimator's averaging) comparable to 11ax runs
        cfg = OFDMConfig(bandwidth_hz=bw, qam_order=int(p["qam"]),
                         n_symbols=24, oversampling=4,
                         subcarrier_spacing_hz=312.5e3, cp_fraction=1 / 4)
    else:
        cfg = OFDMConfig(bandwidth_hz=bw, qam_order=int(p["qam"]),
                         n_symbols=6, oversampling=4)
    tx, rx = _chains(bw, int(p["seed"]), cfg.sample_rate_hz)
    from dataclasses import replace as _replace

    from wifitrx.chain.agc import rebalance_thresholds

    # Anchor bandwidth for the hand-over thresholds.  The official table
    # solves the noise-vs-IM3 balance once at 320 MHz and ships one
    # register set for every bandwidth; the balance point moves with the
    # noise floor, i.e. by a third of the bandwidth change, so at 20 MHz
    # the factory thresholds sit ~4 dB high and each state is held past
    # its own balance point.  `agc_rebw` re-solves at the run's own
    # bandwidth instead — a what-if for a bandwidth-aware AGC, not the
    # shipping behaviour.
    rebw = bool(p.get("agc_rebw", False))
    anchor_bw = bw if rebw else 320e6

    if p.get("rx_hp", False):
        # "RX high-performance" study knob: every LNA/mixer gain state
        # gets NF -1 dB and IIP3 +2 dB.  A modified ladder always needs
        # its thresholds re-solved, whatever the anchor.
        rx.params.lna_states = tuple(
            _replace(s, nf_db=s.nf_db - 1.0, iip3_dbm=s.iip3_dbm + 2.0)
            for s in rx.params.lna_states)
    if not p.get("baseband", False) and (p.get("rx_hp", False) or rebw):
        # the baseband branch re-solves below with its own effective
        # NF/IIP3, so don't solve twice
        rx.params.lna_states = rebalance_thresholds(rx.params.lna_states,
                                                    bandwidth_hz=anchor_bw)
    if p.get("baseband", False):
        # explicit analog baseband: an input-referred noise voltage and
        # an output swing, replacing the share of both that the ladder
        # carries today.  The noise density is a study knob
        # (`bb_noise_nv`, 5..40 nV/sqrt(Hz)); the de-embed below always
        # uses the 6 nV/sqrt(Hz) REFERENCE stage — the placeholder the
        # official ladder was derived to be consistent with — so the
        # RF-only front end stays one part across the sweep.  Sweeping
        # the de-embed instead would quietly improve the RF ladder to
        # keep the cascade totals constant, and "what if the baseband
        # were noisier" would measure nothing.  Densities above
        # ~11 nV/sqrt(Hz) therefore make the cascade genuinely worse
        # than the official table (and would make a same-density
        # de-embed raise): that IS the study.
        from wifitrx.chain.agc import vga_gain_db
        from wifitrx.impairments.baseband import BasebandStage
        from wifitrx.link.budget import (deembed_states, effective_iip3_dbm,
                                         effective_nf_db)
        bb = BasebandStage(
            noise_v_sqrthz=float(p.get("bb_noise_nv", 5.0)) * 1e-9,
            enabled=True)
        rx.params.baseband = bb
        states = deembed_states(rx.params.lna_states,
                                BasebandStage(enabled=True))
        # the ceiling is output-referred, so each state's effective IIP3
        # has to be read at the VGA the AGC actually lands on there —
        # evaluated at the state's own hand-over edge, its worst case
        target = rx.params.adc.fullscale_dbm - rx.params.adc_backoff_db
        rx.params.lna_states = rebalance_thresholds(
            states, bandwidth_hz=anchor_bw, effective={
                "nf_db": [effective_nf_db(s, bb) for s in states],
                "iip3_dbm": [
                    effective_iip3_dbm(s, bb, vga_gain_db(s.max_input_dbm,
                                                          s.gain_db, target))
                    for s in states]})
    from wifitrx.chain.loopback import recommended_loopback_atten_db
    return cfg, tx, rx, LoopbackPath(
        atten_db=recommended_loopback_atten_db(bw), delay_ns=6.0)


_QAM_MCS = {64: 7, 256: 9, 1024: 11, 4096: 13}
# up to -12 dBm so the last AGC hand-over (state 2 -> 3 at -18 dBm) and
# the IM3 sawtooth just below it stay inside the plot
_RX_SWEEP_PIN = np.arange(-90.0, -11.0, 6.0)


def _rx_sweep_points(rx, cfg) -> list:
    """RX EVM at each _RX_SWEEP_PIN level for the chain's CURRENT
    correction state — call once before the sequence (uncalibrated
    curve) and once after (calibrated curve)."""
    from wifitrx.link.sensitivity import measured_rx_evm_db
    return [measured_rx_evm_db(rx, cfg, float(pi)) for pi in _RX_SWEEP_PIN]


def _rx_sweep(rx, cfg, snap_rx, evm_uncal) -> dict:
    """Calibrated RX EVM vs input power, paired with the pre-cal curve,
    the SNR requirement of the MCS matching the run's QAM order and the
    loopback operating point."""
    from wifitrx.link.mcs import mcs

    idx = _QAM_MCS.get(int(cfg.qam_order), 11)
    m = mcs(idx)
    states = rx.params.lna_states
    return {"p_in": _RX_SWEEP_PIN,
            "evm": _rx_sweep_points(rx, cfg),
            "evm_uncal": evm_uncal,
            "req_db": -m.snr_req_db,
            "label": f"MCS{idx} ({m.modulation})",
            "op": (snap_rx["p_in_dbm"], snap_rx["evm_db"]),
            # AGC hand-over thresholds: above max_input_dbm of state i
            # the AGC selects state i+1 (each state's IM3 penalty peaks
            # right below its own threshold)
            "agc": [(st.max_input_dbm, f"AGC {i}→{i + 1}")
                    for i, st in enumerate(states[:-1])]}


def _cal_metrics(results, final):
    m = {"loopback_evm_db": final.metrics_after["evm_db"],
         "tx_evm_db": final.metrics_after["tx_evm_db"],
         "steps_passed": sum(1 for r in results if r.passed),
         "steps_total": len(results)}
    if "rx_evm_db" in final.metrics_after:
        m["rx_evm_db"] = final.metrics_after["rx_evm_db"]
    return m


def run_full_cal(p: dict) -> AnalysisResult:
    from wifitrx.cal.sequence import run_full_cal as _run

    cfg, tx, rx, path = _cal_setup(p)
    evm_uncal = _rx_sweep_points(rx, cfg)   # before any correction
    results = _run(tx, rx, cfg, path, with_dpd=bool(p["with_dpd"]))
    final = {r.name: r for r in results}["final_loopback_evm"]
    sr = final.artifacts.get("snapshot_rx")
    fig = _five_panel(results, final.artifacts.get("snapshot_before"),
                      final.artifacts.get("snapshot_after"),
                      final.artifacts.get("snapshot_tx"), sr,
                      rx_sweep=_rx_sweep(rx, cfg, sr, evm_uncal))
    return AnalysisResult(metrics=_cal_metrics(results, final), figure=fig,
                          cal_state={"tx_state": tx.correction_state(),
                                     "rx_state": rx.correction_state(),
                                     "results": results,
                                     # sample rate: the step costs are in
                                     # samples, and tester time needs both
                                     "fs_hz": cfg.sample_rate_hz,
                                     "conditions": run_conditions(
                                         cfg, tx, rx,
                                         with_dpd=bool(p["with_dpd"]))})


def run_full_cal_steps(p: dict) -> AnalysisResult:
    """Step-through mode: the same canonical sequence, but after every
    step a read-only snapshot trio is taken and rendered as one result
    page, so each step's direct payoff is visible.  Snapshots follow the
    observer contract (tests/test_observers.py): corrections untouched,
    AGC runtime state saved and restored so later steps see exactly the
    level the sequence set — the corrections this mode programs are
    bit-identical to the one-shot mode's."""
    from wifitrx.cal.sequence import (loopback_snapshot, run_full_cal as
                                      _run, rx_snapshot, tx_snapshot)
    from wifitrx.units import power_dbm

    cfg, tx, rx, path = _cal_setup(p)
    drive = 0.12                       # final_drive_scale of the sequence
    evm_uncal = _rx_sweep_points(rx, cfg)   # before any correction
    sb = loopback_snapshot(tx, rx, path, cfg, drive_scale=drive)
    pages: list[tuple[str, Figure]] = []
    seen: list = []
    track: list[tuple[str, float, float, float]] = []

    def on_step(res) -> None:
        seen.append(res)
        if res.name == "final_loopback_evm":
            sa = res.artifacts["snapshot_after"]
            st = res.artifacts["snapshot_tx"]
            sr = res.artifacts["snapshot_rx"]
        else:
            agc_state = (rx.lna_idx, rx.vga_db)
            sa = loopback_snapshot(tx, rx, path, cfg, drive_scale=drive)
            st = tx_snapshot(tx, cfg, drive_scale=drive)
            sr = rx_snapshot(rx, cfg,
                             power_dbm(sa["pa_out"]) - path.atten_db)
            rx.lna_idx, rx.vga_db = agc_state
        track.append((res.name, sa["evm_db"], st["evm_db"], sr["evm_db"]))
        n = len(seen)
        pages.append((f"step {n}: {res.name}", _five_panel(
            seen, sb, sa, st, sr, sa_title="loopback after this step",
            suptitle=f"After step {n}: {res.name}")))

    results = _run(tx, rx, cfg, path, with_dpd=bool(p["with_dpd"]),
                   on_step=on_step)
    final = {r.name: r for r in results}["final_loopback_evm"]

    # re-render the final page with the RX EVM vs input power sweep
    # (sweeping at every intermediate step would cost ~12 RX captures
    # per step for little insight; the calibrated curve is what matters)
    sr_f = final.artifacts["snapshot_rx"]
    pages[-1] = (pages[-1][0], _five_panel(
        seen, sb, final.artifacts["snapshot_after"],
        final.artifacts["snapshot_tx"], sr_f,
        rx_sweep=_rx_sweep(rx, cfg, sr_f, evm_uncal),
        sa_title="loopback after this step",
        suptitle=f"After step {len(seen)}: final_loopback_evm"))

    # summary page: EVM trajectory across the sequence
    fig = new_figure(figsize=(11.5, 5.5))
    ax = fig.add_subplot(1, 1, 1)
    xpos = np.arange(len(track) + 1)
    lb = [sb["evm_db"]] + [t[1] for t in track]
    te = [t[2] for t in track]
    re_ = [t[3] for t in track]
    ax.plot(xpos, lb, "o-", label="loopback EVM")
    ax.plot(xpos[1:], te, "s-", label="TX EVM @ PA out")
    ax.plot(xpos[1:], re_, "^-", label="RX EVM @ digital out")
    ax.set_xticks(xpos)
    ax.set_xticklabels(["(uncal)"] + [t[0] for t in track],
                       rotation=40, ha="right", fontsize=7)
    ax.set_ylabel("EVM [dB]")
    ax.set_title("EVM after each calibration step")
    ax.legend(fontsize=9)
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    pages.append(("summary: EVM per step", fig))

    return AnalysisResult(metrics=_cal_metrics(results, final), figure=fig,
                          figures=tuple(pages),
                          cal_state={"tx_state": tx.correction_state(),
                                     "rx_state": rx.correction_state(),
                                     "results": results,
                                     # sample rate: the step costs are in
                                     # samples, and tester time needs both
                                     "fs_hz": cfg.sample_rate_hz,
                                     "conditions": run_conditions(
                                         cfg, tx, rx,
                                         with_dpd=bool(p["with_dpd"]))})


def run_rx_evm_sweep(p: dict) -> AnalysisResult:
    """RX-mode EVM vs RF input power, uncalibrated vs calibrated, with
    the measured/analytic sensitivity crossings for a few MCS.  This is
    the receive-direction complement of tx_evm: an ideal transmitted
    waveform into the impaired RX (independent LO — phase noise counts
    in full, unlike the loopback view)."""
    from wifitrx.cal.sequence import run_full_cal as _run
    from wifitrx.link.sensitivity import (measured_rx_evm_db,
                                          sensitivity_study)

    cfg, tx, rx, path = _cal_setup(p)
    p_in = np.arange(-92.0, -11.0, 4.0)
    evm_uncal = [measured_rx_evm_db(rx, cfg, float(pi)) for pi in p_in]
    # RX corrections come from the standard sequence; DPD is TX-side
    # only and irrelevant here, so skip it for speed
    results = _run(tx, rx, cfg, path, with_dpd=False)
    evm_cal = [measured_rx_evm_db(rx, cfg, float(pi)) for pi in p_in]

    # Contribution split by ISOLATION: each curve is the chain with only
    # the named sources active, read directly.  The alternative — running
    # the full chain, removing one source and subtracting in the power
    # domain — charges that source with the cross term
    # 2*Re<e_source, e_rest>, which is not small for the deterministic
    # sources (IM3, the baseband ceiling, LPF ISI all derive from the
    # same signal).  Measured on the baseband ceiling: the cross term is
    # 48% of the extracted contribution at 1.0 Vpp, and it flattens the
    # term's OIP3 slope from the analytic -2.0 to -1.5 dB/dB.
    #
    # IQ, DC and the LPF stay on in every curve: their corrections are
    # subtractive, so removing the injection while keeping the correction
    # would inject an equal and opposite error.  What is left with
    # everything switchable off is the isolation floor.
    def _only(*, noise=False, nonlin=False, pn=False, adc=False):
        pr = rx.params
        saved = (rx.noise_enabled, pr.nonlin_enabled, pr.lo.enabled,
                 pr.adc.enabled)
        rx.noise_enabled, pr.nonlin_enabled = noise, nonlin
        pr.lo.enabled, pr.adc.enabled = pn, adc
        out = [measured_rx_evm_db(rx, cfg, float(pi)) for pi in p_in]
        (rx.noise_enabled, pr.nonlin_enabled, pr.lo.enabled,
         pr.adc.enabled) = saved
        return out

    evm_thermal = _only(noise=True)                # thermal only
    evm_nonlin = _only(nonlin=True)                # IM3 (+ BB ceiling) only
    evm_det = _only(pn=True, adc=True)             # PN + ADC + floor
    evm_floor = _only()                            # IQ/DC residue + LPF ISI

    # with the explicit baseband on, "nonlinearity" is two mechanisms —
    # separate them by making each one unreachable in turn — and the
    # thermal curve likewise splits: the baseband stage's own noise gets
    # its isolation reading (front-end thermal silenced with the
    # nf = -100 dB instrument state)
    evm_im3_rf = evm_ceiling = evm_bb_noise = evm_fe_noise = None
    if p.get("baseband", False):
        from dataclasses import replace as _replace
        saved_states, saved_bb = rx.params.lna_states, rx.params.baseband
        rx.params.baseband = _replace(saved_bb, out_swing_vpp=1e6)
        evm_im3_rf = _only(nonlin=True)            # RF per-state IM3 alone
        rx.params.baseband = saved_bb
        rx.params.lna_states = tuple(_replace(s, iip3_dbm=200.0)
                                     for s in saved_states)
        evm_ceiling = _only(nonlin=True)           # baseband ceiling alone
        rx.params.lna_states = saved_states
        evm_bb_noise = list(_iso_sweep(rx, cfg, p_in, noise=True,
                                       fe_nf_db=-100.0))
        evm_fe_noise = list(_iso_sweep(rx, cfg, p_in, noise=True,
                                       bb_nv=1e-6))

    mcs_rows = sensitivity_study(rx, cfg, (7, 9, 11, 13))

    # the split curves only mean something where the receiver locks;
    # below that the analog DC saturates the ADC at railed VGA gain
    # (digital-only DC correction — a recorded model limitation) and
    # every toggle combination reads garbage alike
    ok = np.asarray(evm_cal) < -15.0

    def _mask(v):
        return np.where(ok, np.asarray(v), np.nan)

    fig = new_figure(figsize=(9.5, 6))
    ax = fig.add_subplot(1, 1, 1)
    ax.plot(p_in, evm_uncal, "o--", color="lightgray", ms=4,
            label="uncalibrated")
    ax.plot(p_in, evm_cal, "o-", color="tab:red", label="calibrated (all)")
    ax.plot(p_in, _mask(evm_thermal), "s-", color="tab:blue", ms=3,
            label="thermal only (front-end + baseband)"
                  if evm_bb_noise is not None else "thermal only")
    if evm_fe_noise is not None:
        ax.plot(p_in, _mask(evm_fe_noise), "d--", color="steelblue", ms=3,
                label="front-end thermal only (RF-only NF)")
    if evm_bb_noise is not None:
        ax.plot(p_in, _mask(evm_bb_noise), "^-", color="deepskyblue", ms=3,
                label="baseband noise only (noise density)")
    if evm_ceiling is None:
        ax.plot(p_in, _mask(evm_nonlin), "v-", color="darkgreen", ms=3,
                label="nonlinearity only (per-state IM3)")
    else:
        ax.plot(p_in, _mask(evm_im3_rf), "v-", color="darkgreen", ms=3,
                label="RF IM3 only (per-state IIP3)")
        ax.plot(p_in, _mask(evm_ceiling), "P-", color="saddlebrown", ms=4,
                label="baseband ceiling only (output swing)")
    ax.plot(p_in, _mask(evm_det), "--", color="gray", lw=1,
            label="PN + ADC + IQ/DC residue + ISI")
    ax.plot(p_in, _mask(evm_floor), ":", color="darkgray", lw=1,
            label="isolation floor (IQ/DC residue + ISI)")
    for row in mcs_rows:
        ax.axhline(-row["snr_req_db"], ls="--", lw=0.7, color="gray")
        ax.axvline(row["measured_dbm"], ls=":", lw=0.7, color="tab:green")
        ax.annotate(f"MCS{row['mcs']} ({row['modulation']})",
                    (p_in[-1], -row["snr_req_db"]), fontsize=7,
                    ha="right", va="bottom", color="gray")
    for i, st in enumerate(rx.params.lna_states[:-1]):
        if p_in[0] <= st.max_input_dbm <= p_in[-1]:
            ax.axvline(st.max_input_dbm, ls="-.", lw=0.8,
                       color="tab:purple", alpha=0.7)
            ax.annotate(f"AGC {i}→{i + 1}", (st.max_input_dbm, 4.0),
                        fontsize=7, rotation=90, ha="right", va="top",
                        color="tab:purple")
    ax.set_xlabel("RF input power [dBm]")
    ax.set_ylabel("EVM [dB]")
    ax.set_title("RX EVM vs input power — contributions by isolation "
                 "(not power-additive)\ndashed: MCS SNR requirement · "
                 "dotted: measured sensitivity · dash-dot: AGC hand-over",
                 fontsize=9)
    ax.set_ylim(-60, 5)
    ax.legend(fontsize=8)
    ax.grid(True, alpha=0.3)
    fig.tight_layout()

    text = ("contribution curves are isolations — the chain with only "
            "that source active, read directly. They do NOT add up to "
            "the total: the deterministic sources (IM3, baseband "
            "ceiling, ISI) correlate, and every isolated curve also "
            "carries the isolation floor.\n\n"
            "sensitivity, measured vs analytic (Friis):\n") + "\n".join(
        f"  MCS{r['mcs']:2d} {r['modulation']:>9s}: "
        f"{r['measured_dbm']:7.1f} dBm  (analytic {r['analytic_dbm']:7.1f}, "
        f"delta {r['delta_db']:+.1f} dB)"
        + ("  [floor-limited]" if r["floor_limited"] else "")
        for r in mcs_rows)
    metrics = {"rx_evm_floor_db": float(min(evm_cal)),
               "rx_evm_floor_uncal_db": float(min(evm_uncal))}
    for r in mcs_rows:
        metrics[f"sens_mcs{r['mcs']}_dbm"] = round(r["measured_dbm"], 1)
    return AnalysisResult(metrics=metrics, figure=fig, text=text,
                          cal_state={"tx_state": tx.correction_state(),
                                     "rx_state": rx.correction_state(),
                                     "results": results,
                                     # sample rate: the step costs are in
                                     # samples, and tester time needs both
                                     "fs_hz": cfg.sample_rate_hz,
                                     "conditions": run_conditions(
                                         cfg, tx, rx, with_dpd=False)})


def _iso_sweep(rx, cfg, p_in, *, noise=False, nonlin=False, pn=False,
               adc=False, bb_nv=None, fe_nf_db=None):
    """EVM curve with only the named sources active (isolation method).

    ``bb_nv`` overrides the baseband density (1e-6 nV silences it);
    ``fe_nf_db`` overrides every state's NF (-100 silences the
    front-end thermal).  Both are instrument states — impossible parts
    a study is allowed to build — and everything is restored after.
    IQ/DC/LPF stay on throughout: their corrections are subtractive,
    and what remains with everything switchable off is the isolation
    floor that bounds every curve from below.
    """
    from dataclasses import replace as _replace

    from wifitrx.link.sensitivity import measured_rx_evm_db
    pr = rx.params
    saved = (rx.noise_enabled, pr.nonlin_enabled, pr.lo.enabled,
             pr.adc.enabled, pr.baseband, pr.lna_states)
    rx.noise_enabled, pr.nonlin_enabled = noise, nonlin
    pr.lo.enabled, pr.adc.enabled = pn, adc
    if bb_nv is not None:
        pr.baseband = _replace(pr.baseband, noise_v_sqrthz=bb_nv * 1e-9)
    if fe_nf_db is not None:
        pr.lna_states = tuple(_replace(s, nf_db=fe_nf_db)
                              for s in pr.lna_states)
    out = np.array([measured_rx_evm_db(rx, cfg, float(pi)) for pi in p_in])
    (rx.noise_enabled, pr.nonlin_enabled, pr.lo.enabled,
     pr.adc.enabled, pr.baseband, pr.lna_states) = saved
    return out


def run_bb_noise_sweep(p: dict) -> AnalysisResult:
    """Baseband-noise density sweep: one RX EVM page per density.

    Per density: a fast calibration (thresholds re-solved for that
    density's effective NF/IIP3 — `agc_rebw` picks the anchor), then
    five isolation curves and the baseband-noise share of the total
    EVM.  The share strip masks the region where the baseband-only
    reading sits within 3 dB of the isolation floor: there the curve is
    the floor (IQ/DC residue + LPF ISI), and attributing it to the
    baseband would repeat the mistake the floor line exists to expose —
    at 20 MHz / 11ac/n the floor (~-46 dB) owns everything below
    ~25 nV.
    """
    from wifitrx.cal.sequence import run_full_cal

    densities = (5, 40) if p.get("quick", False) else (5, 10, 15, 20,
                                                       25, 30, 35, 40)
    p_in = np.arange(-92.0, -11.0, 8.0 if p.get("quick", False) else 4.0)

    pages = []
    metrics: dict = {}
    lines = []
    for nv in densities:
        cfg, tx, rx, path = _cal_setup({**p, "baseband": True,
                                        "bb_noise_nv": nv})
        run_full_cal(tx, rx, cfg, path, with_dpd=False)

        evm_full = _iso_sweep(rx, cfg, p_in, noise=True, nonlin=True,
                              pn=True, adc=True)
        evm_thermal = _iso_sweep(rx, cfg, p_in, noise=True)
        evm_fe = _iso_sweep(rx, cfg, p_in, noise=True, bb_nv=1e-6)
        evm_bb = _iso_sweep(rx, cfg, p_in, noise=True, fe_nf_db=-100.0)
        evm_floor = _iso_sweep(rx, cfg, p_in)

        share = np.clip(100.0 * 10.0 ** (evm_bb / 10.0)
                        / 10.0 ** (evm_full / 10.0), 0.0, 100.0)
        floor_dom = evm_bb < evm_floor + 3.0

        fig = new_figure(figsize=(9.2, 7.2))
        gs = fig.add_gridspec(2, 1, height_ratios=(3, 1), hspace=0.07)
        ax = fig.add_subplot(gs[0])
        axs = fig.add_subplot(gs[1], sharex=ax)
        ax.plot(p_in, evm_full, "s-", ms=3.5, color="tab:orange",
                label="calibrated, all impairments")
        ax.plot(p_in, evm_thermal, "o-", ms=3, color="tab:blue",
                label="thermal only (front-end + baseband)")
        ax.plot(p_in, evm_fe, "^--", ms=3, color="tab:cyan",
                label="front-end thermal only")
        ax.plot(p_in, evm_bb, "v-", ms=3, color="tab:red",
                label="baseband noise only")
        ax.plot(p_in, evm_floor, ":", lw=1.2, color="gray",
                label="isolation floor (all off)")
        for i, s in enumerate(rx.params.lna_states[:-1]):
            if p_in[0] <= s.max_input_dbm <= p_in[-1]:
                ax.axvline(s.max_input_dbm, ls="-.", lw=0.7,
                           color="tab:purple", alpha=0.6)
                ax.annotate(f"{i}→{i + 1}", (s.max_input_dbm, 2.5),
                            fontsize=6, rotation=90, ha="right",
                            va="top", color="tab:purple")
        ax.set_ylabel("EVM [dB]")
        ax.set_ylim(-62, 5)
        ax.grid(True, alpha=0.3)
        ax.legend(fontsize=8, loc="upper center")
        ax.tick_params(labelbottom=False)
        ax.set_title(
            f"RX EVM vs input power — baseband noise "
            f"{nv} nV/√Hz\n{p['bw_mhz']} MHz / {p['qam']}-QAM "
            f"({p.get('std', '11ax/be')}), thresholds re-solved for "
            "this density (isolation curves: only that source active; "
            "not power-additive)", fontsize=10)

        ok = ~floor_dom
        axs.plot(p_in[ok], share[ok], "d-", ms=3, color="tab:red")
        axs.plot(p_in[floor_dom], share[floor_dom], "d", ms=3,
                 mfc="none", color="gray")
        if floor_dom.any():
            axs.annotate("open gray = floor-dominated,\nnot "
                         "attributable to bb noise", (0.99, 0.92),
                         xycoords="axes fraction", fontsize=6.5,
                         ha="right", va="top", color="gray")
        axs.set_ylabel("BB noise share\nof total EVM [%]", fontsize=8)
        axs.set_xlabel("RF input [dBm]")
        axs.set_ylim(0, 100)
        axs.grid(True, alpha=0.3)

        pages.append((f"{nv} nV/√Hz", fig))
        metrics[f"floor_db_{nv}nv"] = round(float(evm_full.min()), 2)
        peak = float(share[ok].max()) if ok.any() else float("nan")
        metrics[f"bb_share_pct_{nv}nv"] = round(peak, 1)
        lines.append(f"{nv:2d} nV: calibrated floor "
                     f"{evm_full.min():6.2f} dB, peak attributable "
                     f"share {peak:5.1f}%, t0 "
                     f"{rx.params.lna_states[0].max_input_dbm:.1f} dBm")

    text = ("Isolation curves are direct readings with only the named "
            "source active; they are not power-additive.  The share is "
            "the baseband-only power over the full-chain power, masked "
            "where the isolation floor owns the reading.\n\n"
            + "\n".join(lines))
    return AnalysisResult(metrics=metrics, figure=pages[0][1],
                          figures=tuple(pages), text=text)


def run_drift_tracking(p: dict) -> AnalysisResult:
    from wifitrx.cal.dpd_tracking import track_dpd
    from wifitrx.chain import RxChain, RxParams, TxChain, TxParams
    from wifitrx.impairments.analog_filter import TunableLPF
    from wifitrx.impairments.converters import ADCParams, DACParams
    from wifitrx.impairments.iq_imbalance import FreqDepIQImbalance
    from wifitrx.impairments.phase_noise import LOModel
    from wifitrx.pa import DriftingReferencePA, DriftingScaledPA
    from wifitrx.waveform import OFDMConfig, generate_ofdm

    bw = float(p["bw_mhz"]) * 1e6
    cfg = OFDMConfig(bandwidth_hz=bw, qam_order=256, n_symbols=6,
                     oversampling=4)
    fs = cfg.sample_rate_hz
    wf = generate_ofdm(cfg)
    pa = DriftingScaledPA(DriftingReferencePA(drive0=0.13, drive_span=0.02,
                                              beta_a_span=0.15,
                                              alpha_p_span=0.5))
    tx = TxChain(TxParams(bandwidth_hz=bw, dac=DACParams(enabled=True),
                          lpf=TunableLPF(enabled=False),
                          iq=FreqDepIQImbalance(enabled=False),
                          lo=LOModel(enabled=False), pa_enabled=True),
                 fs, pa=pa)
    rx = RxChain(RxParams(bandwidth_hz=bw, nonlin_enabled=False,
                          iq=FreqDepIQImbalance(enabled=False), dc_offset=(),
                          lpf=TunableLPF(enabled=False),
                          adc=ADCParams(enabled=False),
                          lo=LOModel(enabled=False)), fs)
    rx.noise_enabled = False
    rx.agc(-20.0)
    schedule = np.linspace(0.0, 1.0, int(p["n_states"]))
    res = track_dpd(tx, rx, wf, schedule, drive_scale=0.12)

    fig = new_figure()
    ax = fig.add_subplot(111)
    states = [t["state"] for t in res.trace]
    ax.plot(states, [t["evm_track_db"] for t in res.trace], "o-",
            label="tracking DPD")
    ax.plot(states, [t["evm_frozen_db"] for t in res.trace], "s--",
            label="frozen DPD")
    ax.set_xlabel("Drift state")
    ax.set_ylabel("TX EVM [dB]")
    ax.legend()
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    return AnalysisResult(metrics=res.metrics_after, figure=fig)


def run_blocker_desense(p: dict) -> AnalysisResult:
    from wifitrx.chain import RxChain, RxParams
    from wifitrx.impairments.blocker import Blocker
    from wifitrx.impairments.phase_noise import LOModel
    from wifitrx.units import dbm_to_mw
    from wifitrx.waveform.stimuli import single_tone

    bw = float(p["bw_mhz"]) * 1e6
    fs = bw * 4
    rx = RxChain(RxParams(bandwidth_hz=bw, lo=LOModel(enabled=True)), fs)
    p_sig = float(p["p_sig_dbm"])
    n = 1 << 15
    rows = []
    for p_b in np.arange(-70.0, -14.0, 5.0):
        p_tot = 10 * np.log10(dbm_to_mw(p_sig) + dbm_to_mw(p_b))
        rx.agc(p_tot)
        sig = single_tone(23e6, fs, n, amp=np.sqrt(dbm_to_mw(p_sig)))
        blk = Blocker(offset_hz=float(p["offset_mhz"]) * 1e6,
                      power_dbm=p_b).signal(n, fs)
        cap = rx(sig + blk, rng=np.random.default_rng(1))
        spec = np.abs(np.fft.fft(cap - np.mean(cap))) ** 2 / n ** 2
        k = int(round(23e6 * n / fs))
        p_s = float(np.sum(spec[[k - 1, k, k + 1]]))
        band = np.arange(n) * fs / n
        sel = (band > 2e6) & (band < bw / 2)
        sel[[k - 1, k, k + 1]] = False
        rows.append((p_b, 10 * np.log10(p_s / float(np.sum(spec[sel])))))

    fig = new_figure()
    ax = fig.add_subplot(111)
    ax.plot([r[0] for r in rows], [r[1] for r in rows], "o-")
    ax.set_xlabel("Blocker power [dBm]")
    ax.set_ylabel("In-band SNR [dB]")
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    return AnalysisResult(metrics={"snr_at_-20dBm_blocker_db": rows[-2][1]},
                          figure=fig)


def _pn_config(p: dict):
    """OFDM numerology for the phase-noise study: the run bandwidth at the
    selected standard, with the capture held at the same duration across
    standards (20 symbols of 12.8 us, 80 of 3.2 us) so every estimator
    averages over the same time."""
    from wifitrx.waveform import OFDMConfig

    bw = float(p["bw_mhz"]) * 1e6
    if p.get("std", "11ax/be") == "11ac/n":
        if bw > 160e6:
            raise ValueError("802.11ac/n supports at most 160 MHz — "
                             "select the 11ax/be standard for 320 MHz")
        return OFDMConfig(bandwidth_hz=bw, qam_order=1024, n_symbols=80,
                          oversampling=4, subcarrier_spacing_hz=312.5e3,
                          cp_fraction=1 / 4)
    return OFDMConfig(bandwidth_hz=bw, qam_order=1024, n_symbols=20,
                      oversampling=4)


def _pn_four_configs(frame, cols, pilots, phi) -> np.ndarray:
    """EVM [dB] of the four measurement configurations for one
    phase-noise realization ``phi`` applied to ``frame``.

    1  no CPE correction, true channel (H = 1): CPE + ICI total
    2  genie CPE (all tones vs ideal reference), true channel: ICI floor
    3  genie CPE, channel estimate from the received LTF pair
    4  pilot-only CPE (N_p tones), LTF channel estimate: the modem form

    Phase noise is the only impairment and the channel is flat, so the
    true channel is exactly unity and configs 1/2 need no equalizer at
    all — no self-fitted gain, hence no degrees-of-freedom correction.
    Data tones are scored in every config; pilot tones are excluded.
    """
    from wifitrx.metrics.cpe import correct_cpe, correct_cpe_pilots
    from wifitrx.waveform.ofdm import demodulate_ofdm
    from wifitrx.waveform.preamble import channel_estimate

    cfg = frame.config
    y = frame.x * np.exp(1j * phi)
    tx = frame.data.tx_symbols
    rx = demodulate_ofdm(y[frame.preamble_len:], frame.data)
    data = np.ones(cfg.n_active, dtype=bool)
    data[cols] = False
    ref = tx[:, data]
    p_ref = float((np.abs(ref) ** 2).mean())

    def score(sym):
        return 10.0 * np.log10(float((np.abs(sym[:, data] - ref) ** 2).mean())
                               / p_ref)

    h = channel_estimate(y, frame)
    req = rx / h
    return np.array([score(rx), score(correct_cpe(rx, tx)),
                     score(correct_cpe(req, tx)),
                     score(correct_cpe_pilots(req, cols, pilots))])


def _pn_sweep_point(profile, frame, cols, pilots, n_lo, n_frames, rng):
    """Power-average the four readings over ``n_frames`` independent
    phase-noise realizations (``n_lo`` independent LOs summed)."""
    from wifitrx.impairments.phase_noise import LOModel

    fs = frame.config.sample_rate_hz
    n = frame.x.size
    lo = LOModel(profile=profile)
    acc = np.zeros(4)
    for _ in range(n_frames):
        phi = np.zeros(n)
        for _k in range(n_lo):
            phi = phi + lo.phase(n, fs, rng)
        acc += 10.0 ** (_pn_four_configs(frame, cols, pilots, phi) / 10.0)
    return 10.0 * np.log10(acc / n_frames)


def _pn_nominal(cfg, n_lo: int, n_frames: int, seed: int) -> np.ndarray:
    """The four readings at the shipped LO profile for one numerology:
    frame with pilots + LTF pair, ``n_frames`` realizations averaged."""
    from wifitrx.impairments.phase_noise import DEFAULT_WIFI7_LO_PROFILE
    from wifitrx.waveform.pilots import generate_ofdm_with_pilots, pilot_sequence
    from wifitrx.waveform.preamble import build_frame

    wf, cols = generate_ofdm_with_pilots(cfg)
    frame = build_frame(cfg, data=wf)
    pilots = pilot_sequence(cfg.n_symbols, cols.size)
    return _pn_sweep_point(DEFAULT_WIFI7_LO_PROFILE, frame, cols, pilots, n_lo,
                           n_frames, np.random.default_rng(seed))


def run_pn_cpe_study(p: dict) -> AnalysisResult:
    """LO phase noise through the baseband's CPE removal: four measurement
    configurations, isolation method (phase noise is the only impairment).

    Four pages.  (a) The LO profile split by the per-symbol weight
    1 - sinc^2(f T_FFT) into what a common-phase rotation removes and
    what stays as ICI.  (b) A type-II PLL family anchored on the shipped
    profile's plateau/VCO/floor, loop bandwidth swept: rms jitter and
    the post-CPE EVM do not have to share an optimum, because jitter
    integrates the spectrum with unit weight while EVM ignores what CPE
    removes.  (c) The four configurations vs LO phase-noise level, with
    the closed forms overlaid on configs 1 and 2 — the cross-check that
    the model's ICI weighting (and PSD convention) is right.  Each
    configuration is a direct reading; the differences are mechanisms
    and do not add in power.  (d) The two standards side by side at this
    bandwidth and LO configuration, stacked in error POWER (where the
    mechanisms do add along the chain 2 -> 3 -> 4): ICI floor, the LTF
    estimate's frozen error, the pilot estimator's noise, with the
    no-CPE reading as a level — the 12.8 us symbol leaves CPE removal
    almost nothing to take out, so 11ax/be reads ~1.4 dB worse than
    11ac/n for the same LO (40 MHz, measured).
    """
    from wifitrx.impairments.phase_noise import (
        DEFAULT_WIFI7_LO_PROFILE, TabulatedPhase, TypeIIPllPhase,
        cpe_partition, ici_weight, integrate_pn, ldbc_from_sphi)
    from wifitrx.waveform.pilots import generate_ofdm_with_pilots, pilot_sequence
    from wifitrx.waveform.preamble import build_frame

    cfg = _pn_config(p)
    n_lo = 2 if p.get("lo_count", "single") == "tx+rx" else 1
    n_frames = max(1, int(p.get("n_frames", 8)))
    seed = int(p.get("seed", 0))
    f_1f3 = float(p.get("vco_1f3_khz", 0.0)) * 1e3
    t_fft = 1.0 / cfg.subcarrier_spacing_hz

    wf, cols = generate_ofdm_with_pilots(cfg)
    frame = build_frame(cfg, data=wf)
    pilots = pilot_sequence(cfg.n_symbols, cols.size)
    fs = cfg.sample_rate_hz
    n = frame.x.size
    f_lo, f_hi = fs / n, fs / 2          # the synthesized band, exactly
    base = DEFAULT_WIFI7_LO_PROFILE
    f_carrier = 6.0e9

    def scaled(off_db):
        return TabulatedPhase("lo", f_pts=base.f_pts,
                              l_dbc_pts=tuple(v + off_db
                                              for v in base.l_dbc_pts))

    def closed(profile):
        part = cpe_partition(lambda f: n_lo * profile.psd(f), t_fft,
                             f_lo, f_hi)
        return (10.0 * np.log10(part["total_rad2"]),
                10.0 * np.log10(part["ici_rad2"]), part)

    # ---------------------------------------------- (c) level sweep
    offsets = np.arange(-10.0, 21.0, 5.0)
    rng = np.random.default_rng(seed)
    readings = np.array([_pn_sweep_point(scaled(o), frame, cols, pilots,
                                         n_lo, n_frames, rng)
                         for o in offsets])
    cf = [closed(scaled(o)) for o in offsets]
    cf_total = np.array([c[0] for c in cf])
    cf_ici = np.array([c[1] for c in cf])
    i0 = int(np.argmin(np.abs(offsets)))
    c1, c2, c3, c4 = readings[i0]
    part0 = cf[i0][2]

    # ---------------------------------------------- (b) loop-bandwidth sweep
    plateau_dbc, vco_dbc, floor_dbc = -104.1, -116.1, -155.0
    loop_bws = np.logspace(np.log10(30e3), np.log10(3e6), 13)
    f_int = np.logspace(np.log10(f_lo), np.log10(f_hi), 6000)
    lb_total, lb_ici, lb_jit, lb_td = [], [], [], []
    rng_lb = np.random.default_rng(seed + 1)
    for lbw in loop_bws:
        prof = TypeIIPllPhase.from_spot("pll", lbw, plateau_dbc, vco_dbc,
                                        floor_dbc, zeta=1.0, f_1f3=f_1f3)
        tot, ici, _ = closed(prof)
        lb_total.append(tot)
        lb_ici.append(ici)
        pwr = integrate_pn(f_int, n_lo * prof.psd(f_int), f_lo, f_hi)
        lb_jit.append(1e15 * np.sqrt(pwr) / (2 * np.pi * f_carrier))
        lb_td.append(_pn_sweep_point(prof, frame, cols, pilots, n_lo,
                                     n_frames, rng_lb)[:2])
    lb_total, lb_ici = np.array(lb_total), np.array(lb_ici)
    lb_jit, lb_td = np.array(lb_jit), np.array(lb_td)
    i_jit = int(np.argmin(lb_jit))
    i_evm = int(np.argmin(lb_ici))

    # ---------------------------------------------- page (a): PSD partition
    f_plot = np.logspace(3, 8, 600)
    fig_a = new_figure(figsize=(8.6, 5.2))
    ax = fig_a.add_subplot(111)
    ax.semilogx(f_plot, ldbc_from_sphi(base.psd(f_plot)), color="tab:blue",
                lw=1.8, label="shipped LO profile L(f)")
    prof_nom = TypeIIPllPhase.from_spot("pll", loop_bws[i_jit], plateau_dbc,
                                        vco_dbc, floor_dbc, zeta=1.0,
                                        f_1f3=f_1f3)
    ax.semilogx(f_plot, ldbc_from_sphi(prof_nom.psd(f_plot)), "--",
                color="tab:purple", lw=1.2,
                label=f"type-II PLL family at its jitter optimum "
                      f"({loop_bws[i_jit] / 1e3:.0f} kHz loop BW)")
    ax.set_xlabel("Offset from carrier [Hz]")
    ax.set_ylabel("L(f) [dBc/Hz]")
    ax.set_ylim(-165, -85)
    ax.grid(True, which="both", alpha=0.3)
    ax2 = ax.twinx()
    ax2.semilogx(f_plot, ici_weight(f_plot, t_fft), color="tab:red", lw=1.4,
                 label="ICI weight 1 - sinc²(f·T_FFT)")
    ax2.set_ylabel("share left after CPE removal", color="tab:red")
    ax2.set_ylim(0, 1.05)
    f3 = part0["f_3db_hz"]
    ax.axvspan(1e3, f3, color="tab:green", alpha=0.10)
    ax.axvline(f3, color="tab:green", ls=":", lw=1.2)
    ax.annotate(f"CPE-removable\nbelow {f3 / 1e3:.0f} kHz\n"
                f"(T_FFT = {t_fft * 1e6:.1f} µs)", (f3, -90), fontsize=8,
                ha="right", va="top", color="tab:green",
                xytext=(-4, 0), textcoords="offset points")
    h1, l1 = ax.get_legend_handles_labels()
    h2, l2 = ax2.get_legend_handles_labels()
    ax.legend(h1 + h2, l1 + l2, fontsize=7.5, loc="lower left")
    ax.set_title(
        f"LO phase noise vs per-symbol CPE removal — {p['bw_mhz']} MHz "
        f"{p.get('std', '11ax/be')}\nCPE tracks out "
        f"{100 * part0['tracked_fraction']:.1f}% of the phase power "
        f"({f_lo / 1e3:.1f} kHz – {f_hi / 1e6:.0f} MHz); the rest is ICI "
        f"(closed form {cf_ici[i0]:.1f} dB, no CPE {cf_total[i0]:.1f} dB)",
        fontsize=9.5)
    fig_a.tight_layout()

    # ---------------------------------------------- page (b): loop BW sweep
    fig_b = new_figure(figsize=(8.6, 5.2))
    ax = fig_b.add_subplot(111)
    ax.semilogx(loop_bws / 1e3, lb_total, "--", color="gray", lw=1.2,
                label="closed form, no CPE removal")
    ax.semilogx(loop_bws / 1e3, lb_ici, "-", color="tab:red", lw=1.6,
                label="closed form, after CPE removal (ICI)")
    ax.semilogx(loop_bws / 1e3, lb_td[:, 0], "s", ms=4, mfc="none",
                color="gray", label="model: config 1 (no CPE)")
    ax.semilogx(loop_bws / 1e3, lb_td[:, 1], "o", ms=4, color="tab:red",
                label="model: config 2 (genie CPE)")
    ax.axvline(loop_bws[i_jit] / 1e3, color="tab:blue", ls=":", lw=1.2)
    ax.axvline(loop_bws[i_evm] / 1e3, color="tab:red", ls=":", lw=1.2)
    ax.set_xlabel("PLL loop bandwidth (-3 dB of |H|²) [kHz]")
    ax.set_ylabel("phase-noise EVM contribution [dB]")
    ax.grid(True, which="both", alpha=0.3)
    ax3 = ax.twinx()
    ax3.semilogx(loop_bws / 1e3, lb_jit, "-", color="tab:blue", lw=1.2,
                 label="rms jitter (right axis)")
    ax3.set_ylabel("rms jitter [fs]", color="tab:blue")
    h1, l1 = ax.get_legend_handles_labels()
    h2, l2 = ax3.get_legend_handles_labels()
    ax.legend(h1 + h2, l1 + l2, fontsize=7.5, loc="upper center")
    gain = lb_ici[i_jit] - lb_ici[i_evm]
    ax.set_title(
        f"Type-II PLL family (plateau {plateau_dbc} dBc/Hz, VCO {vco_dbc} "
        f"dBc/Hz @1 MHz, 1/f³ corner {f_1f3 / 1e3:.0f} kHz, zeta 1.0)\n"
        f"jitter optimum {loop_bws[i_jit] / 1e3:.0f} kHz "
        f"({lb_jit[i_jit]:.0f} fs), post-CPE EVM optimum "
        f"{loop_bws[i_evm] / 1e3:.0f} kHz — moving there buys "
        f"{gain:.2f} dB", fontsize=9.5)
    fig_b.tight_layout()

    # ---------------------------------------------- page (c): four configs
    fig_c = new_figure(figsize=(8.6, 5.6))
    ax = fig_c.add_subplot(111)
    styles = (("1  no CPE correction, true channel", "s-", "gray"),
              ("2  genie CPE, true channel (ICI floor)", "o-", "tab:red"),
              ("3  genie CPE, LTF channel estimate", "^-", "tab:orange"),
              ("4  pilot CPE (N_p tones), LTF estimate — modem form",
               "v-", "tab:purple"))
    for k, (lab, st, col) in enumerate(styles):
        ax.plot(offsets, readings[:, k], st, ms=4.5, color=col, label=lab)
    ax.plot(offsets, cf_total, "--", color="gray", lw=1.0,
            label="closed form ∫S_φ df (config 1)")
    ax.plot(offsets, cf_ici, "--", color="tab:red", lw=1.0,
            label="closed form ∫S_φ·[1 − sinc²(fT)] df (config 2)")
    ax.axhline(-38.0, color="k", ls="-.", lw=0.8)
    ax.annotate("4096-QAM TX EVM target −38 dB", (offsets[0], -38.0),
                fontsize=7.5, va="bottom", xytext=(2, 2),
                textcoords="offset points")
    ax.set_xlabel("LO phase-noise level relative to the shipped profile [dB]")
    ax.set_ylabel("EVM, phase noise only [dB]")
    ax.grid(True, alpha=0.3)
    ax.legend(fontsize=7.5, loc="upper left")
    lo_txt = "TX + RX independent LOs" if n_lo == 2 else "single LO"
    ax.set_title(
        f"Four measurement configurations — {p['bw_mhz']} MHz "
        f"{p.get('std', '11ax/be')}, {lo_txt}, N_p = {cols.size}, "
        f"{n_frames} frame(s)\nat 0 dB: CPE buys {c1 - c2:.2f} dB, "
        f"LTF estimate costs {c3 - c2:.2f} dB, pilot CPE costs "
        f"{c4 - c3:.2f} dB (direct readings, not power-additive)",
        fontsize=9.5)
    fig_c.tight_layout()

    # ---------------------------------------------- page (d): standards
    std_here = p.get("std", "11ax/be")
    other_std = "11ac/n" if std_here == "11ax/be" else "11ax/be"
    per_std = {std_here: readings[i0]}
    bw_mhz = float(p["bw_mhz"])
    if other_std == "11ac/n" and bw_mhz > 160:
        other_note = "\n11ac/n is undefined above 160 MHz — omitted"
    else:
        other_note = ""
        per_std[other_std] = _pn_nominal(
            _pn_config({**p, "std": other_std}), n_lo, n_frames, seed + 2)
    order = [s for s in ("11ac/n", "11ax/be") if s in per_std]

    def lin(db):
        return 10.0 ** (db / 10.0) * 1e5    # error power / signal, in 1e-5

    fig_d = new_figure(figsize=(8.6, 5.6))
    ax = fig_d.add_subplot(111)
    xs = np.arange(len(order))
    bar_w = 0.5
    seg_style = (("ICI floor (config 2: genie CPE, true channel)", "tab:red"),
                 ("+ LTF channel-estimate frozen error (config 3 − 2)",
                  "tab:orange"),
                 (f"+ pilot-CPE estimator noise, N_p = {cols.size} "
                  "(config 4 − 3)", "tab:purple"))
    top = 0.0
    top_guess = max(lin(v[0]) for v in per_std.values()) * 1.3
    for i, std in enumerate(order):
        d1, d2, d3, d4 = per_std[std]
        segs = (lin(d2), lin(d3) - lin(d2), lin(d4) - lin(d3))
        bottom = 0.0
        for seg, (lab, col) in zip(segs, seg_style):
            ax.bar(xs[i], seg, bar_w, bottom=bottom, color=col,
                   edgecolor="white", label=lab if i == 0 else None)
            bottom += seg
        # boundary labels, nudged apart when a thin segment would stack
        # two of them on top of each other (32-pilot 320 MHz: 0.03 dB)
        ys = [lin(d2), lin(d3), lin(d4)]
        for k in range(1, 3):
            ys[k] = max(ys[k], ys[k - 1] + 0.035 * top_guess)
        for lvl, db in zip(ys, (d2, d3, d4)):
            ax.annotate(f"{db:.1f} dB", (xs[i] + bar_w / 2 + 0.03, lvl),
                        fontsize=7.5, va="center", ha="left")
        ax.hlines(lin(d1), xs[i] - bar_w / 2, xs[i] + bar_w / 2, colors="k",
                  linestyles="--", lw=1.2,
                  label="no CPE removal at all (config 1)" if i == 0 else None)
        # below the dashed level, inside the bar: above it the label would
        # collide with the total when CPE removes little (11ax/be)
        ax.annotate(f"CPE removes\n{d1 - d2:.2f} dB", (xs[i], lin(d1)),
                    fontsize=7, ha="center", va="top", xytext=(0, -3),
                    textcoords="offset points",
                    bbox=dict(boxstyle="round,pad=0.15", fc="white", ec="none",
                              alpha=0.85))
        ax.annotate(f"total {d4:.2f} dB", (xs[i], bottom), fontsize=9.5,
                    ha="center", va="bottom", xytext=(0, 4),
                    textcoords="offset points", fontweight="bold")
        top = max(top, bottom, lin(d1))
    ax.set_xticks(xs)
    ax.set_xticklabels([f"{std}  ({'3.2' if std == '11ac/n' else '12.8'} µs "
                        "symbol)" for std in order])
    ax.set_ylabel("phase-noise error power / signal power  [×1e-5]\n"
                  "(−50 dB = 1, −40 dB = 10)")
    ax.set_ylim(0, top * 1.25)
    if len(order) == 1:                 # one bar: centre it, legend beside
        ax.set_xlim(-1.0, 1.0)
        ax.legend(fontsize=8, loc="upper right")
    else:
        ax.set_xlim(-0.6, len(order) - 0.4)
        ax.legend(fontsize=8, loc="upper left")
    ax.grid(True, axis="y", alpha=0.3)
    ax.set_title(
        f"Standards side by side — modem form (N_p = {cols.size} pilot CPE + "
        f"LTF estimate), {p['bw_mhz']} MHz, {lo_txt}, {n_frames} frame(s)\n"
        "stacked in error POWER so the segments add: every boundary is the "
        f"direct reading of one configuration{other_note}", fontsize=9.5)
    fig_d.tight_layout()
    if len(order) == 2:
        std_gap = float(per_std["11ax/be"][3] - per_std["11ac/n"][3])
    else:
        std_gap = None

    metrics = {
        "evm_no_cpe_db": round(float(c1), 2),
        "evm_genie_cpe_db": round(float(c2), 2),
        "evm_ltf_ce_db": round(float(c3), 2),
        "evm_pilot_cpe_db": round(float(c4), 2),
        "closed_form_total_db": round(float(cf_total[i0]), 2),
        "closed_form_ici_db": round(float(cf_ici[i0]), 2),
        "cpe_gain_db": round(float(c1 - c2), 2),
        "ltf_penalty_db": round(float(c3 - c2), 2),
        "pilot_penalty_db": round(float(c4 - c3), 2),
        "cpe_tracked_pct": round(100.0 * float(part0["tracked_fraction"]), 2),
        "f_cpe_3db_khz": round(float(part0["f_3db_hz"]) / 1e3, 1),
        "n_pilots": int(cols.size),
        "loopbw_opt_jitter_khz": round(float(loop_bws[i_jit]) / 1e3, 1),
        "loopbw_opt_evm_khz": round(float(loop_bws[i_evm]) / 1e3, 1),
        "loopbw_evm_gain_db": round(float(gain), 2),
        "evm_pilot_cpe_11ac_db": (round(float(per_std["11ac/n"][3]), 2)
                                  if "11ac/n" in per_std else None),
        "evm_pilot_cpe_11ax_db": (round(float(per_std["11ax/be"][3]), 2)
                                  if "11ax/be" in per_std else None),
        "std_gap_db": None if std_gap is None else round(std_gap, 2),
    }
    text = (
        "Isolation method: phase noise is the only impairment, so the true "
        "channel is unity and configs 1/2 use no equalizer.  Each "
        "configuration is a direct reading; the deltas are mechanisms and "
        "do not add in power.\n"
        f"Config 1 (no CPE) {c1:.2f} dB vs closed form {cf_total[i0]:.2f} "
        f"dB; config 2 (genie CPE) {c2:.2f} dB vs closed form "
        f"{cf_ici[i0]:.2f} dB — residuals {c1 - cf_total[i0]:+.2f} / "
        f"{c2 - cf_ici[i0]:+.2f} dB (single-frame realization spread is "
        "~0.3 dB rms; the closed form is the expectation).\n"
        f"CPE removal buys {c1 - c2:.2f} dB with this profile and "
        f"T_FFT = {t_fft * 1e6:.1f} µs: it tracks out "
        f"{100 * part0['tracked_fraction']:.1f}% of the phase power, the "
        f"part below {part0['f_3db_hz'] / 1e3:.0f} kHz.\n"
        f"Config 3: the LTF-derived channel estimate carries its own "
        f"frozen ICI onto every data symbol, +{c3 - c2:.2f} dB — it does "
        "not average down with symbol count (two LTF repeats averaged).\n"
        f"Config 4: estimating the CPE from N_p = {cols.size} pilots "
        f"instead of every tone costs a further {c4 - c3:.2f} dB, common-"
        "mode across all data subcarriers.\n"
        f"Loop-bandwidth family: jitter optimum {loop_bws[i_jit] / 1e3:.0f} "
        f"kHz, post-CPE EVM optimum {loop_bws[i_evm] / 1e3:.0f} kHz "
        f"(choosing the latter changes the phase-noise EVM by {gain:.2f} "
        "dB).")
    if std_gap is not None:
        text += (f"\nStandards side by side (modem form): 11ax/be "
                 f"{per_std['11ax/be'][3]:.2f} dB vs 11ac/n "
                 f"{per_std['11ac/n'][3]:.2f} dB — 11ax/be is "
                 f"{std_gap:+.2f} dB; same LO, the difference is what the 4x "
                 "longer symbol denies CPE removal.  The gap scatters ~0.4 dB "
                 f"rms at {n_frames} frame(s) because the LTF frozen error is "
                 "one realization per frame; 32 frames settle it.")
    return AnalysisResult(metrics=metrics, figure=fig_c,
                          figures=(("PSD partition", fig_a),
                                   ("PLL loop bandwidth", fig_b),
                                   ("Four configurations", fig_c),
                                   ("Standards side by side", fig_d)),
                          text=text)


def run_spur_planner(p: dict) -> AnalysisResult:
    from wifitrx.link.spur_planning import channel_spur_table

    rows = channel_spur_table(float(p["bw_mhz"]) * 1e6,
                              bands=(str(p["band"]),))
    dirty = [r for r in rows if r["dirty"]]
    text = "\n".join(f"{r['f_c_hz']/1e6:.0f} MHz  frac={r['frac']:.4f}  "
                     f"worst={r['worst_inband_dbc']:.1f} dBc"
                     for r in dirty) or "(no dirty channels)"
    fig = new_figure()
    ax = fig.add_subplot(111)
    f_c = [r["f_c_hz"] / 1e6 for r in rows]
    worst = [r["worst_inband_dbc"] if r["worst_inband_dbc"] is not None
             else -120.0 for r in rows]
    colors = ["tab:red" if r["dirty"] else "tab:blue" for r in rows]
    ax.bar(f_c, worst, width=15, color=colors)
    ax.set_xlabel("Channel center [MHz]")
    ax.set_ylabel("Worst in-band spur [dBc]")
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    return AnalysisResult(metrics={"n_channels": len(rows),
                                   "n_dirty": len(dirty)},
                          figure=fig, text=text)


ALL_ANALYSES: tuple[AnalysisSpec, ...] = (
    AnalysisSpec(
        key="full_cal", title="Full calibration sequence",
        description="Randomized impairments -> 9-step calibration -> EVM",
        params=(
            ParamSpec("bw_mhz", "Bandwidth [MHz]", "choice", 80,
                      choices=(20, 40, 80, 160, 320)),
            ParamSpec("qam", "QAM order", "choice", 1024,
                      choices=(64, 256, 1024, 4096)),
            ParamSpec("std", "Standard", "choice", "11ax/be",
                      choices=("11ax/be", "11ac/n"),
                      tooltip="11ac/n: 312.5 kHz spacing, 3.2 us symbol, "
                              "0.8 us long GI; max 160 MHz"),
            ParamSpec("rx_hp", "RX high-performance", "bool", False,
                      tooltip="Every LNA gain state: NF -1 dB, IIP3 +2 dB "
                              "(hand-over thresholds unchanged)"),
            ParamSpec("agc_rebw", "AGC thresholds at run BW", "bool", False,
                      tooltip="Re-solve the hand-over thresholds at this "
                              "run's bandwidth. The shipped table solves "
                              "the noise-vs-IM3 balance once at 320 MHz "
                              "and uses one register set everywhere; the "
                              "balance point moves by a third of the "
                              "bandwidth change, so at 20 MHz the factory "
                              "thresholds sit ~4 dB high."),
            ParamSpec("baseband", "Explicit baseband stage", "bool", False,
                      tooltip="Model the LPF/VGA/ADC-driver separately "
                              "(input-referred noise from the density knob "
                              "below, 1.0 Vpp output swing); the ladder is "
                              "de-embedded at the 6 nV/sqrt(Hz) reference"),
            ParamSpec("bb_noise_nv", "BB noise density [nV/sqrt(Hz)]",
                      "choice", 5, choices=(5, 10, 15, 20, 25, 30, 35, 40),
                      tooltip="Input-referred noise of the baseband stage, "
                              "at the baseband node. Only read when the "
                              "explicit baseband stage is on. The RF-only "
                              "front end is held fixed (de-embedded at the "
                              "6 nV reference), so above ~11 nV the cascade "
                              "is genuinely worse than the official ladder "
                              "— that is the study, not an error"),
            ParamSpec("seed", "Process seed", "int", 5, minimum=0),
            ParamSpec("with_dpd", "Run DPD", "bool", False),
        ),
        run=run_full_cal),
    AnalysisSpec(
        key="full_cal_steps", title="Full calibration, step-through",
        description="Same sequence, one result page per step (snapshot "
                    "trio after every calibration) plus an EVM-per-step "
                    "summary — shows each step's direct payoff",
        params=(
            ParamSpec("bw_mhz", "Bandwidth [MHz]", "choice", 80,
                      choices=(20, 40, 80, 160, 320)),
            ParamSpec("qam", "QAM order", "choice", 1024,
                      choices=(64, 256, 1024, 4096)),
            ParamSpec("std", "Standard", "choice", "11ax/be",
                      choices=("11ax/be", "11ac/n"),
                      tooltip="11ac/n: 312.5 kHz spacing, 3.2 us symbol, "
                              "0.8 us long GI; max 160 MHz"),
            ParamSpec("rx_hp", "RX high-performance", "bool", False,
                      tooltip="Every LNA gain state: NF -1 dB, IIP3 +2 dB "
                              "(hand-over thresholds unchanged)"),
            ParamSpec("agc_rebw", "AGC thresholds at run BW", "bool", False,
                      tooltip="Re-solve the hand-over thresholds at this "
                              "run's bandwidth. The shipped table solves "
                              "the noise-vs-IM3 balance once at 320 MHz "
                              "and uses one register set everywhere; the "
                              "balance point moves by a third of the "
                              "bandwidth change, so at 20 MHz the factory "
                              "thresholds sit ~4 dB high."),
            ParamSpec("baseband", "Explicit baseband stage", "bool", False,
                      tooltip="Model the LPF/VGA/ADC-driver separately "
                              "(input-referred noise from the density knob "
                              "below, 1.0 Vpp output swing); the ladder is "
                              "de-embedded at the 6 nV/sqrt(Hz) reference"),
            ParamSpec("bb_noise_nv", "BB noise density [nV/sqrt(Hz)]",
                      "choice", 5, choices=(5, 10, 15, 20, 25, 30, 35, 40),
                      tooltip="Input-referred noise of the baseband stage, "
                              "at the baseband node. Only read when the "
                              "explicit baseband stage is on. The RF-only "
                              "front end is held fixed (de-embedded at the "
                              "6 nV reference), so above ~11 nV the cascade "
                              "is genuinely worse than the official ladder "
                              "— that is the study, not an error"),
            ParamSpec("seed", "Process seed", "int", 5, minimum=0),
            ParamSpec("with_dpd", "Run DPD", "bool", False),
        ),
        run=run_full_cal_steps),
    AnalysisSpec(
        key="rx_evm_sweep", title="RX EVM vs input power",
        description="Receive-direction EVM (ideal TX waveform into the "
                    "impaired RX), uncalibrated vs calibrated, with "
                    "measured sensitivity crossings per MCS",
        params=(
            ParamSpec("bw_mhz", "Bandwidth [MHz]", "choice", 80,
                      choices=(20, 40, 80, 160, 320)),
            ParamSpec("qam", "QAM order", "choice", 1024,
                      choices=(64, 256, 1024, 4096)),
            ParamSpec("std", "Standard", "choice", "11ax/be",
                      choices=("11ax/be", "11ac/n"),
                      tooltip="11ac/n: 312.5 kHz spacing, 3.2 us symbol, "
                              "0.8 us long GI; max 160 MHz"),
            ParamSpec("rx_hp", "RX high-performance", "bool", False,
                      tooltip="Every LNA gain state: NF -1 dB, IIP3 +2 dB "
                              "(hand-over thresholds unchanged)"),
            ParamSpec("agc_rebw", "AGC thresholds at run BW", "bool", False,
                      tooltip="Re-solve the hand-over thresholds at this "
                              "run's bandwidth. The shipped table solves "
                              "the noise-vs-IM3 balance once at 320 MHz "
                              "and uses one register set everywhere; the "
                              "balance point moves by a third of the "
                              "bandwidth change, so at 20 MHz the factory "
                              "thresholds sit ~4 dB high."),
            ParamSpec("baseband", "Explicit baseband stage", "bool", False,
                      tooltip="Model the LPF/VGA/ADC-driver separately "
                              "(input-referred noise from the density knob "
                              "below, 1.0 Vpp output swing); the ladder is "
                              "de-embedded at the 6 nV/sqrt(Hz) reference"),
            ParamSpec("bb_noise_nv", "BB noise density [nV/sqrt(Hz)]",
                      "choice", 5, choices=(5, 10, 15, 20, 25, 30, 35, 40),
                      tooltip="Input-referred noise of the baseband stage, "
                              "at the baseband node. Only read when the "
                              "explicit baseband stage is on. The RF-only "
                              "front end is held fixed (de-embedded at the "
                              "6 nV reference), so above ~11 nV the cascade "
                              "is genuinely worse than the official ladder "
                              "— that is the study, not an error"),
            ParamSpec("seed", "Process seed", "int", 5, minimum=0),
        ),
        run=run_rx_evm_sweep),
    AnalysisSpec(
        key="bb_noise_sweep", title="Baseband noise sweep (RX EVM)",
        description="One RX-EVM-vs-input-power page per baseband noise "
                    "density (5..40 nV/sqrt(Hz)): thresholds re-solved "
                    "per density, five isolation curves, and the "
                    "baseband share of the total EVM with the "
                    "floor-dominated region masked",
        params=(
            ParamSpec("bw_mhz", "Bandwidth [MHz]", "choice", 80,
                      choices=(20, 40, 80, 160, 320)),
            ParamSpec("qam", "QAM order", "choice", 256,
                      choices=(64, 256, 1024, 4096)),
            ParamSpec("std", "Standard", "choice", "11ax/be",
                      choices=("11ax/be", "11ac/n")),
            ParamSpec("seed", "Process seed", "int", 5, minimum=0),
            ParamSpec("agc_rebw", "AGC thresholds at run BW", "bool", True,
                      tooltip="On (default here): each density's "
                              "thresholds are solved at this run's "
                              "bandwidth — the study asks what an "
                              "optimized AGC does with a noisier "
                              "baseband. Off: 320 MHz factory anchor"),
            ParamSpec("quick", "Endpoints only (quick)", "bool", False,
                      tooltip="Run 5 and 40 nV only, with a coarser "
                              "power grid — a preview/CI profile; the "
                              "full study is 8 pages"),
        ),
        run=run_bb_noise_sweep),
    AnalysisSpec(
        key="drift_tracking", title="PA drift tracking DPD",
        description="RLS DPD vs frozen DPD over a thermal ramp",
        params=(
            ParamSpec("bw_mhz", "Bandwidth [MHz]", "choice", 80,
                      choices=(20, 40, 80)),
            ParamSpec("n_states", "Drift steps", "int", 6, minimum=3,
                      maximum=20),
        ),
        run=run_drift_tracking),
    AnalysisSpec(
        key="blocker_desense", title="Blocker desense sweep",
        description="In-band SNR vs CW blocker power (reciprocal mixing, "
                    "AGC backoff, ADC dynamic range)",
        params=(
            ParamSpec("bw_mhz", "Bandwidth [MHz]", "choice", 160,
                      choices=(80, 160)),
            ParamSpec("offset_mhz", "Blocker offset [MHz]", "float", 200.0),
            ParamSpec("p_sig_dbm", "Signal power [dBm]", "float", -60.0),
        ),
        run=run_blocker_desense),
    AnalysisSpec(
        key="pn_cpe_study", title="LO phase noise vs CPE removal",
        description="Isolation study of LO phase noise through the "
                    "baseband's common-phase-error removal: four "
                    "measurement configurations (no CPE / genie CPE / "
                    "LTF channel estimate / pilot CPE) vs phase-noise "
                    "level with closed-form cross-checks, the "
                    "CPE-vs-ICI partition of the LO profile, and a PLL "
                    "loop-bandwidth sweep (jitter optimum vs post-CPE "
                    "EVM optimum)",
        params=(
            ParamSpec("bw_mhz", "Bandwidth [MHz]", "choice", 80,
                      choices=(20, 40, 80, 160, 320),
                      tooltip="Sets the pilot count N_p (4/6/8/16/32) "
                              "and the tone plan"),
            ParamSpec("std", "Standard", "choice", "11ax/be",
                      choices=("11ax/be", "11ac/n"),
                      tooltip="11ax/be: 12.8 us symbol, CPE removes "
                              "below ~35 kHz; 11ac/n: 3.2 us symbol, "
                              "~138 kHz (max 160 MHz)"),
            ParamSpec("lo_count", "LO configuration", "choice", "single",
                      choices=("single", "tx+rx"),
                      tooltip="single: one LO, the TX-EVM (or RX-EVM) "
                              "sign-off view; tx+rx: two independent "
                              "LOs as in an OTA link (phase PSD doubles)"),
            ParamSpec("n_frames", "Frames averaged", "int", 8, minimum=1,
                      maximum=64,
                      tooltip="Independent phase-noise realizations "
                              "power-averaged per point; one frame's "
                              "reading scatters ~0.3 dB rms around the "
                              "closed form (the LTF-estimate config "
                              "~0.7 dB, its error being frozen per frame)"),
            ParamSpec("vco_1f3_khz", "VCO 1/f³ corner [kHz]", "float", 0.0,
                      minimum=0.0, maximum=5000.0,
                      tooltip="For the loop-bandwidth page only: the "
                              "type-II family's VCO flicker corner. 0 "
                              "matches the shipped table's pure 1/f² "
                              "roll-off"),
            ParamSpec("seed", "Noise seed", "int", 0, minimum=0),
        ),
        run=run_pn_cpe_study),
    AnalysisSpec(
        key="spur_planner", title="Frac-N dirty-channel planner",
        description="Predicted in-band fractional spurs across a WiFi band",
        params=(
            ParamSpec("bw_mhz", "Bandwidth [MHz]", "choice", 320,
                      choices=(20, 40, 80, 160, 320)),
            ParamSpec("band", "Band", "choice", "6g",
                      choices=("2g4", "5g", "6g")),
        ),
        run=run_spur_planner),
)
