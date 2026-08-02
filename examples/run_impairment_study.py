"""Per-impairment EVM/ACLR study through the TX -> loopback -> RX chain.

Turns each impairment on alone (mirroring PA_DPD scripts/run_loopback_study.py)
and reports the EVM/ACLR cost, plus a PSD comparison figure.

Usage:  python examples/run_impairment_study.py [--bw 80e6] [--out reports/]
"""
from __future__ import annotations

import argparse
from dataclasses import replace
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from wifitrx.cal.sync import _fractional_advance, align_delay
from wifitrx.chain import LoopbackPath, RxChain, RxParams, TxChain, TxParams, run_loopback
from wifitrx.impairments.analog_filter import TunableLPF
from wifitrx.impairments.converters import ADCParams, DACParams
from wifitrx.impairments.iq_imbalance import FreqDepIQImbalance
from wifitrx.impairments.phase_noise import LOModel
from wifitrx.metrics import aclr, evm, psd
from wifitrx.waveform import OFDMConfig, demodulate_ofdm, generate_ofdm


def clean_tx(bw: float) -> TxParams:
    return TxParams(bandwidth_hz=bw, dac=DACParams(enabled=False),
                    lpf=TunableLPF(enabled=False),
                    iq=FreqDepIQImbalance(enabled=False), lo_leak_dbm=None,
                    lo=LOModel(enabled=False), pa_enabled=False)


def clean_rx(bw: float) -> RxParams:
    return RxParams(bandwidth_hz=bw, nonlin_enabled=False,
                    iq=FreqDepIQImbalance(enabled=False), dc_offset=(),
                    lpf=TunableLPF(enabled=False), adc=ADCParams(enabled=False),
                    lo=LOModel(enabled=False))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--bw", type=float, default=80e6)
    ap.add_argument("--qam", type=int, default=1024)
    ap.add_argument("--out", type=Path, default=Path("reports"))
    args = ap.parse_args()

    bw = args.bw
    cfg = OFDMConfig(bandwidth_hz=bw, qam_order=args.qam, n_symbols=8,
                     oversampling=4)
    fs = cfg.sample_rate_hz
    wf = generate_ofdm(cfg)
    x = wf.x * 0.1  # digital backoff

    cases: dict[str, tuple[TxParams, RxParams]] = {
        "clean": (clean_tx(bw), clean_rx(bw)),
        "tx_iq_imbalance": (replace(clean_tx(bw), iq=FreqDepIQImbalance(
            gain_db=0.3, phase_deg=2.0, gd_mismatch_ps=200.0,
            rail_ripple_db=0.3, rail_gd_ripple_ns=0.1)), clean_rx(bw)),
        "tx_lo_leak": (replace(clean_tx(bw), lo_leak_dbm=-28.0), clean_rx(bw)),
        "tx_phase_noise": (replace(clean_tx(bw), lo=LOModel(enabled=True)),
                           clean_rx(bw)),
        "tx_pa_8db_backoff": (replace(clean_tx(bw), dac=DACParams(enabled=False),
                                      pa_enabled=True), clean_rx(bw)),
        "rx_iq_imbalance": (clean_tx(bw), replace(clean_rx(bw),
            iq=FreqDepIQImbalance(gain_db=0.3, phase_deg=2.0,
                                  gd_mismatch_ps=200.0))),
        "rx_dc_offset": (clean_tx(bw), replace(clean_rx(bw),
            dc_offset=(0.02 + 0.015j,) * 4)),
        "adc_9bit": (clean_tx(bw), replace(clean_rx(bw),
            adc=ADCParams(bits=9, enabled=True))),
        "lpf_corner_-20pct": (replace(clean_tx(bw),
            lpf=TunableLPF(fc_nominal_hz=bw / 2 * 1.1, rc_error=-0.2)),
            clean_rx(bw)),
    }

    args.out.mkdir(parents=True, exist_ok=True)
    rows = []
    psds = {}
    for name, (txp, rxp) in cases.items():
        tx = TxChain(txp, fs)
        rx = RxChain(rxp, fs)
        rx.noise_enabled = False
        # AGC on the actual coupled power at the RX input
        from wifitrx.units import power_dbm
        probe = tx(x)
        rx.agc(power_dbm(probe))
        out = run_loopback(tx, rx, x, LoopbackPath(atten_db=0.0, delay_ns=0.0))
        # undo the chain group delay before demodulation
        _, _, info = align_delay(wf.x, out, max_lag=256)
        out = _fractional_advance(out, info["lag_total"])
        g = np.vdot(wf.x, out) / np.vdot(wf.x, wf.x)
        res = evm(demodulate_ofdm(out / g, wf), wf.tx_symbols,
                  equalize="per_tone")
        try:
            ac = aclr(out, fs, bw)
            ac_worst = max(ac["lower_dbc"], ac["upper_dbc"])
        except Exception:
            ac_worst = float("nan")
        rows.append((name, res.db, ac_worst))
        psds[name] = out
        print(f"{name:24s} EVM {res.db:7.2f} dB   worst ACLR {ac_worst:7.2f} dBc")

    fig, ax = plt.subplots(figsize=(10, 6))
    for name, sigl in psds.items():
        f, p = psd(sigl, fs)
        ax.plot(f / 1e6, p, label=name, lw=0.9)
    ax.set_xlabel("Frequency [MHz]")
    ax.set_ylabel("PSD [dB]")
    ax.set_title(f"Impairment study, BW={bw/1e6:.0f} MHz")
    ax.legend(fontsize=7)
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    fig.savefig(args.out / "impairment_study_psd.png", dpi=140)

    with open(args.out / "impairment_study.md", "w") as fh:
        fh.write("| case | EVM (dB) | worst ACLR (dBc) |\n|---|---|---|\n")
        for name, e, a in rows:
            fh.write(f"| {name} | {e:.2f} | {a:.2f} |\n")
    print(f"written: {args.out}/impairment_study.md, impairment_study_psd.png")


if __name__ == "__main__":
    main()
