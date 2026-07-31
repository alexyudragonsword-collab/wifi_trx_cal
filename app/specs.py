# Declarative analysis registry, pattern from adc_toolbox:app/analyses/spec.py
# (GUI form, worker invocation and the parametrized smoke test are all
# generated from these entries; worker code never touches pyplot).
"""wifitrx workbench analyses.

Adding an analysis = one AnalysisSpec entry: declarative params + a run
function returning AnalysisResult.  Every entry is exercised by the
parametrized smoke test in tests/test_gui_specs.py.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

import numpy as np
from matplotlib.figure import Figure


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


def _five_panel(results, sb, sa, st, sr=None, sa_title="loopback AFTER",
                suptitle=None) -> Figure:
    """The full-cal result page: four constellations (loopback before /
    loopback current / TX @ PA output / RX @ digital output — the
    loopback view cancels common-LO phase noise, the TX view is the
    802.11be spec measurement point where it counts, the RX view feeds
    an ideal waveform into the receiver with an independent LO), the
    PA-output PSD overlay, and the per-step dB metrics of ``results``."""
    from wifitrx.metrics.spectrum import psd

    fig = new_figure(figsize=(12.5, 7))
    gs = fig.add_gridspec(2, 4)
    ax_cb = fig.add_subplot(gs[0, 0])
    ax_ca = fig.add_subplot(gs[0, 1])
    ax_ct = fig.add_subplot(gs[0, 2])
    ax_cr = fig.add_subplot(gs[0, 3])
    ax_psd = fig.add_subplot(gs[1, 0:2])
    ax_bar = fig.add_subplot(gs[1, 2:4])

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
    cfg = OFDMConfig(bandwidth_hz=bw, qam_order=int(p["qam"]),
                     n_symbols=6, oversampling=4)
    tx, rx = _chains(bw, int(p["seed"]), cfg.sample_rate_hz)
    return cfg, tx, rx, LoopbackPath(atten_db=40.0, delay_ns=6.0)


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
    results = _run(tx, rx, cfg, path, with_dpd=bool(p["with_dpd"]))
    final = {r.name: r for r in results}["final_loopback_evm"]
    fig = _five_panel(results, final.artifacts.get("snapshot_before"),
                      final.artifacts.get("snapshot_after"),
                      final.artifacts.get("snapshot_tx"),
                      final.artifacts.get("snapshot_rx"))
    return AnalysisResult(metrics=_cal_metrics(results, final), figure=fig,
                          cal_state={"tx_state": tx.correction_state(),
                                     "rx_state": rx.correction_state(),
                                     "results": results})


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
                                     "results": results})


def run_rx_evm_sweep(p: dict) -> AnalysisResult:
    """RX-mode EVM vs RF input power, uncalibrated vs calibrated, with
    the measured/analytic sensitivity crossings for a few MCS.  This is
    the receive-direction complement of tx_evm: an ideal transmitted
    waveform into the impaired RX (independent LO — phase noise counts
    in full, unlike the loopback view)."""
    from wifitrx.cal.sequence import run_full_cal as _run
    from wifitrx.link.mcs import mcs
    from wifitrx.link.sensitivity import (measured_rx_evm_db,
                                          sensitivity_study)

    cfg, tx, rx, path = _cal_setup(p)
    p_in = np.arange(-92.0, -23.0, 4.0)
    evm_uncal = [measured_rx_evm_db(rx, cfg, float(pi)) for pi in p_in]
    # RX corrections come from the standard sequence; DPD is TX-side
    # only and irrelevant here, so skip it for speed
    results = _run(tx, rx, cfg, path, with_dpd=False)
    evm_cal = [measured_rx_evm_db(rx, cfg, float(pi)) for pi in p_in]
    mcs_rows = sensitivity_study(rx, cfg, (7, 9, 11, 13))

    fig = new_figure(figsize=(9.5, 6))
    ax = fig.add_subplot(1, 1, 1)
    ax.plot(p_in, evm_uncal, "o-", label="RX EVM, uncalibrated")
    ax.plot(p_in, evm_cal, "s-", label="RX EVM, calibrated")
    for row in mcs_rows:
        ax.axhline(-row["snr_req_db"], ls="--", lw=0.7, color="gray")
        ax.axvline(row["measured_dbm"], ls=":", lw=0.7, color="tab:green")
        ax.annotate(f"MCS{row['mcs']} ({row['modulation']})",
                    (p_in[-1], -row["snr_req_db"]), fontsize=7,
                    ha="right", va="bottom", color="gray")
    ax.set_xlabel("RF input power [dBm]")
    ax.set_ylabel("EVM [dB]")
    ax.set_title("RX EVM vs input power (dashed: MCS SNR requirement, "
                 "dotted: measured sensitivity)", fontsize=10)
    ax.set_ylim(-60, 5)
    ax.legend(fontsize=9)
    ax.grid(True, alpha=0.3)
    fig.tight_layout()

    text = "sensitivity, measured vs analytic (Friis):\n" + "\n".join(
        f"  MCS{r['mcs']:2d} {r['modulation']:>9s}: "
        f"{r['measured_dbm']:7.1f} dBm  (analytic {r['analytic_dbm']:7.1f}, "
        f"delta {r['delta_db']:+.1f} dB)" for r in mcs_rows)
    metrics = {"rx_evm_floor_db": float(min(evm_cal)),
               "rx_evm_floor_uncal_db": float(min(evm_uncal))}
    for r in mcs_rows:
        metrics[f"sens_mcs{r['mcs']}_dbm"] = round(r["measured_dbm"], 1)
    return AnalysisResult(metrics=metrics, figure=fig, text=text,
                          cal_state={"tx_state": tx.correction_state(),
                                     "rx_state": rx.correction_state(),
                                     "results": results})


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
                      choices=(256, 1024, 4096)),
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
                      choices=(256, 1024, 4096)),
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
                      choices=(256, 1024, 4096)),
            ParamSpec("seed", "Process seed", "int", 5, minimum=0),
        ),
        run=run_rx_evm_sweep),
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
