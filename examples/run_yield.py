"""Monte-Carlo calibration yield over process corners.

N random impairment draws -> full calibration -> post-cal metric
distribution and yield against limits (pattern from pllsim montecarlo's
yield_frac).  Usage:

    python examples/run_yield.py [--runs 20] [--bw 80e6] [--out reports/]
"""
from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from wifitrx.cal.sequence import run_full_cal
from wifitrx.chain import LoopbackPath, RxChain, RxParams, TxChain, TxParams
from wifitrx.waveform import OFDMConfig

LIMITS = {
    "tx_evm_db": -38.0,        # MCS13 TX EVM
    "loopback_evm_db": -34.0,  # composite TX+RX budget
    "tx_irr_db": 50.0,
    "rx_irr_db": 50.0,
    "lo_leak_dbc": -40.0,
}


def one_run(seed: int, bw: float, cfg: OFDMConfig) -> dict:
    fs = cfg.sample_rate_hz
    rng = np.random.default_rng(seed)
    txp = TxParams(bandwidth_hz=bw).randomize(rng)
    rxp = RxParams(bandwidth_hz=bw).randomize(rng)
    txp.lpf.fc_nominal_hz = bw / 2 * 1.3
    rxp.lpf.fc_nominal_hz = bw / 2 * 1.12
    tx = TxChain(txp, fs)
    rx = RxChain(rxp, fs)
    results = run_full_cal(tx, rx, cfg, LoopbackPath(atten_db=40.0, delay_ns=6.0))
    by = {r.name: r for r in results}
    return {
        "seed": seed,
        "tx_evm_db": by["final_loopback_evm"].metrics_after["tx_evm_db"],
        "loopback_evm_db": by["final_loopback_evm"].metrics_after["evm_db"],
        "tx_irr_db": by["tx_iq"].metrics_after["irr_min_db"],
        "rx_irr_db": by["rx_iq"].metrics_after["irr_min_db"],
        "lo_leak_dbc": by["tx_lo_leak_loopback"].metrics_after["lo_leak_dbc"],
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", type=int, default=20)
    ap.add_argument("--bw", type=float, default=80e6)
    ap.add_argument("--out", type=Path, default=Path("reports"))
    args = ap.parse_args()

    cfg = OFDMConfig(bandwidth_hz=args.bw, qam_order=1024, n_symbols=6,
                     oversampling=4)
    rows = [one_run(seed, args.bw, cfg) for seed in range(args.runs)]

    lines = [f"# 校准良率 (Monte-Carlo, {args.runs} 个工艺样本, "
             f"BW={args.bw/1e6:.0f} MHz)", "",
             "| 指标 | 限值 | p50 | 最差 | 良率 |", "|---|---|---|---|---|"]
    for key, limit in LIMITS.items():
        vals = np.array([r[key] for r in rows])
        if key in ("tx_irr_db", "rx_irr_db"):
            ok = vals > limit
            worst = float(np.min(vals))
        else:
            ok = vals < limit
            worst = float(np.max(vals))
        lines.append(f"| {key} | {limit} | {np.median(vals):.1f} | "
                     f"{worst:.1f} | {100 * np.mean(ok):.0f}% |")
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "yield.md").write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))

    fig, ax = plt.subplots(figsize=(6, 4))
    ax.hist([r["tx_evm_db"] for r in rows], bins=12, alpha=0.8)
    ax.axvline(LIMITS["tx_evm_db"], color="tab:red", ls="--",
               label="MCS13 limit -38 dB")
    ax.set_xlabel("Post-cal TX EVM [dB]")
    ax.set_ylabel("Count")
    ax.set_title("Calibration yield: TX EVM distribution")
    ax.legend()
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    fig.savefig(args.out / "yield_tx_evm.png", dpi=140)
    print(f"written: {args.out}/yield.md, yield_tx_evm.png")


if __name__ == "__main__":
    main()
