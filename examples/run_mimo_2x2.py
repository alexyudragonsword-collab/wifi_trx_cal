"""MIMO 2x2 demo: per-chain calibration + inter-chain phase/delay alignment.

Usage: python examples/run_mimo_2x2.py [--out reports/]
"""
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np

from wifitrx.cal.mimo_align import calibrate_mimo_align
from wifitrx.cal.sequence import run_full_cal
from wifitrx.chain import LoopbackPath
from wifitrx.chain.mimo import MimoParams, MimoTrx
from wifitrx.waveform import OFDMConfig


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--bw", type=float, default=80e6)
    ap.add_argument("--seed", type=int, default=3)
    ap.add_argument("--out", type=Path, default=Path("reports"))
    args = ap.parse_args()

    bw = args.bw
    cfg = OFDMConfig(bandwidth_hz=bw, qam_order=1024, n_symbols=6,
                     oversampling=4)
    fs = cfg.sample_rate_hz
    rng = np.random.default_rng(args.seed)
    mimo = MimoTrx(MimoParams(n_chains=2).randomize(rng), fs,
                   bandwidth_hz=bw, seed=args.seed)
    for tx in mimo.txs:
        tx.params.lpf.fc_nominal_hz = bw / 2 * 1.3
    for rx in mimo.rxs:
        rx.params.lpf.fc_nominal_hz = bw / 2 * 1.12
    path = LoopbackPath(atten_db=40.0, delay_ns=6.0)

    # per-chain isolated calibration (others idle), then inter-chain align
    lines = [f"# MIMO 2x2 校准结果 (BW={bw/1e6:.0f} MHz)", ""]
    for i, (tx, rx) in enumerate(zip(mimo.txs, mimo.rxs)):
        results = run_full_cal(tx, rx, cfg, path, with_dpd=False)
        final = {r.name: r for r in results}["final_loopback_evm"]
        lines.append(f"- 链 {i}: 环回 EVM {final.metrics_after['evm_db']:.1f} dB, "
                     f"TX EVM {final.metrics_after['tx_evm_db']:.1f} dB")
        print(lines[-1])

    res = calibrate_mimo_align(mimo)
    lines += ["", "## 链间对齐", ""]
    for k in sorted(res.metrics_before):
        lines.append(f"- {k}: {res.metrics_before[k]:.2f} -> "
                     f"{res.metrics_after[k]:.2f}")
        print(lines[-1])
    lines.append(f"\n对齐通过: {res.passed}")

    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "mimo_2x2.md").write_text("\n".join(lines), encoding="utf-8")
    print(f"written: {args.out / 'mimo_2x2.md'}")


if __name__ == "__main__":
    main()
