"""Full calibration sequence on a randomized impaired transceiver + report.

Usage:  python examples/run_full_calibration.py [--bw 160e6] [--seed 5]
        [--out reports/]
Output: reports/cal_report.md + reports/figs/*.png + reports/cal_state.json
"""
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np

from wifitrx.cal.base import save_cal_state
from wifitrx.cal.residuals import run_conditions
from wifitrx.cal.sequence import run_full_cal
from wifitrx.chain import LoopbackPath, RxChain, RxParams, TxChain, TxParams
from wifitrx.report.generator import generate_report
from wifitrx.waveform import OFDMConfig


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--bw", type=float, default=160e6)
    ap.add_argument("--qam", type=int, default=1024)
    ap.add_argument("--seed", type=int, default=5)
    ap.add_argument("--out", type=Path, default=Path("reports"))
    args = ap.parse_args()

    bw = args.bw
    cfg = OFDMConfig(bandwidth_hz=bw, qam_order=args.qam, n_symbols=6,
                     oversampling=4)
    fs = cfg.sample_rate_hz

    rng = np.random.default_rng(args.seed)
    txp = TxParams(bandwidth_hz=bw).randomize(rng)
    rxp = RxParams(bandwidth_hz=bw).randomize(rng)
    # TX baseband wider than the channel so DPD keeps its correction BW
    txp.lpf.fc_nominal_hz = bw / 2 * 1.3
    rxp.lpf.fc_nominal_hz = bw / 2 * 1.12
    tx = TxChain(txp, fs)
    rx = RxChain(rxp, fs)

    path = LoopbackPath(atten_db=40.0, delay_ns=6.0)
    results = run_full_cal(tx, rx, cfg, path)

    args.out.mkdir(parents=True, exist_ok=True)
    report = generate_report(results, args.out,
                             title=f"WiFi 7 收发器校准报告 (BW={bw/1e6:.0f} MHz, "
                                   f"{args.qam}-QAM, seed={args.seed})")
    save_cal_state(args.out / "cal_state.json", tx.correction_state(),
                   rx.correction_state(), results,
                   fs_hz=cfg.sample_rate_hz,
                   conditions=run_conditions(cfg, tx, rx, with_dpd=True))
    print(f"report:    {report}")
    print(f"cal state: {args.out / 'cal_state.json'}")
    final = {r.name: r for r in results}["final_loopback_evm"]
    print(f"final loopback EVM: {final.metrics_after['evm_db']:.2f} dB, "
          f"TX EVM: {final.metrics_after['tx_evm_db']:.2f} dB")


if __name__ == "__main__":
    main()
