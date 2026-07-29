"""4x4 MIMO demo: inter-chain alignment, decoupling, beamforming gain.

Usage: python examples/run_mimo_4x4.py [--out reports/]
"""
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np

from wifitrx.cal.mimo_align import (calibrate_mimo_align,
                                    calibrate_mimo_decouple)
from wifitrx.chain import RxParams, TxParams
from wifitrx.chain.mimo import MimoParams, MimoTrx
from wifitrx.link.beamforming import beamforming_study


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--bw", type=float, default=80e6)
    ap.add_argument("--out", type=Path, default=Path("reports"))
    args = ap.parse_args()
    bw = args.bw
    fs = bw * 4

    def factory():
        mp = MimoParams(n_chains=4,
                        lo_skew_deg=(0.0, 45.0, -50.0, 30.0),
                        lo_skew_ps=(0.0, 250.0, -280.0, 200.0))
        mimo = MimoTrx(mp, fs, bandwidth_hz=bw, seed=7)
        for tx in mimo.txs:
            tx.params.lpf.enabled = False
            tx.params.iq.enabled = False
            tx.params.lo.enabled = False
            tx.params.lo_leak_dbm = None
            tx.params.pa_enabled = False
            tx.params.dac.enabled = False
        for rx in mimo.rxs:
            rx.params.iq.enabled = False
            rx.params.lpf.enabled = False
            rx.params.adc.enabled = False
            rx.params.lo.enabled = False
            rx.params.nonlin_enabled = False
            rx.params.dc_offset = ()
            rx.noise_enabled = False
        return mimo

    mimo = factory()
    res_a = calibrate_mimo_align(mimo)
    res_d = calibrate_mimo_decouple(mimo)
    study = beamforming_study(factory)

    lines = ["# MIMO 4x4 校准与波束赋形验证", "", "## 链间对齐", ""]
    for k in sorted(res_a.metrics_before):
        lines.append(f"- {k}: {res_a.metrics_before[k]:.2f} -> "
                     f"{res_a.metrics_after[k]:.2f}")
    lines += ["", "## 解耦", "",
              f"- 最差串扰: {res_d.metrics_before['worst_crosstalk_db']:.1f}"
              f" -> {res_d.metrics_after['worst_crosstalk_db']:.1f} dB", "",
              "## 阵列增益 (理想 12.04 dB)", ""]
    for k in ("unaligned_db", "aligned_db", "aligned_decoupled_db"):
        lines.append(f"- {k}: {study[k]:.2f} dB")
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "mimo_4x4.md").write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))
    print(f"written: {args.out / 'mimo_4x4.md'}")


if __name__ == "__main__":
    main()
