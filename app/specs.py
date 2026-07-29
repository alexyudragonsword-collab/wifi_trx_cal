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
    txp.lpf.fc_nominal_hz = bw / 2 * 1.3
    rxp.lpf.fc_nominal_hz = bw / 2 * 1.12
    return TxChain(txp, fs), RxChain(rxp, fs)


def run_full_cal(p: dict) -> AnalysisResult:
    from wifitrx.cal.sequence import run_full_cal as _run
    from wifitrx.chain import LoopbackPath
    from wifitrx.waveform import OFDMConfig

    bw = float(p["bw_mhz"]) * 1e6
    cfg = OFDMConfig(bandwidth_hz=bw, qam_order=int(p["qam"]),
                     n_symbols=6, oversampling=4)
    tx, rx = _chains(bw, int(p["seed"]), cfg.sample_rate_hz)
    results = _run(tx, rx, cfg, LoopbackPath(atten_db=40.0, delay_ns=6.0),
                   with_dpd=bool(p["with_dpd"]))
    by = {r.name: r for r in results}
    final = by["final_loopback_evm"]

    fig = new_figure()
    ax = fig.add_subplot(111)
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
    ax.bar(xpos - 0.2, befores, 0.4, label="before")
    ax.bar(xpos + 0.2, afters, 0.4, label="after")
    ax.set_xticks(xpos)
    ax.set_xticklabels(names, rotation=40, ha="right", fontsize=6)
    ax.set_ylabel("dB")
    ax.set_title("Per-step dB metrics, before vs after calibration")
    ax.legend()
    ax.grid(True, alpha=0.3)
    fig.tight_layout()

    metrics = {"loopback_evm_db": final.metrics_after["evm_db"],
               "tx_evm_db": final.metrics_after["tx_evm_db"],
               "steps_passed": sum(1 for r in results if r.passed),
               "steps_total": len(results)}
    return AnalysisResult(metrics=metrics, figure=fig)


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
