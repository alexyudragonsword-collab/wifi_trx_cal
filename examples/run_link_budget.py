"""RX link budget and sensitivity/EVM budget per 802.11be MCS.

Usage: python examples/run_link_budget.py [--bw 320e6] [--out reports/]
"""
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np

from wifitrx.chain.agc import DEFAULT_LNA_STATES
from wifitrx.impairments.phase_noise import DEFAULT_WIFI7_LO_PROFILE, integrate_pn
from wifitrx.link import (EvmBudget, MCS_TABLE, Stage, adc_equivalent_stage,
                          cascade_iip3_dbm, cascade_nf_db, sensitivity_dbm)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--bw", type=float, default=320e6)
    ap.add_argument("--out", type=Path, default=Path("reports"))
    args = ap.parse_args()
    bw = args.bw

    lines = [f"# 接收链路预算 (BW = {bw/1e6:.0f} MHz)", ""]
    lines += ["## 各 AGC 档级联 NF / IIP3", "",
              "| LNA 档 | 增益 (dB) | 级联 NF (dB) | 级联 IIP3 (dBm) |",
              "|---|---|---|---|"]
    adc = adc_equivalent_stage(bits=11, fullscale_dbm=2.0, backoff_db=12.0,
                               fs_hz=bw * 2, bw_hz=bw)
    nf_by_state = {}
    for i, st in enumerate(DEFAULT_LNA_STATES):
        stages = [
            Stage("lna+mixer", st.gain_db, st.nf_db, st.iip3_dbm),
            Stage("bb (lpf+vga)", 20.0, 18.0, 12.0),
            adc,
        ]
        nf = cascade_nf_db(stages)
        iip3 = cascade_iip3_dbm(stages)
        nf_by_state[i] = nf
        lines.append(f"| {i} | {st.gain_db:.0f} | {nf:.2f} | {iip3:.1f} |")
    lines.append("")

    f = np.logspace(4, 8, 500)
    ipn_rad2 = integrate_pn(f, DEFAULT_WIFI7_LO_PROFILE.psd(f), 1e4, 1e8)
    lines += [f"LO 积分相噪:{10*np.log10(ipn_rad2/2):.1f} dBc "
              f"({np.degrees(np.sqrt(ipn_rad2)):.2f}° rms)", ""]

    lines += ["## 每 MCS 灵敏度与 EVM 预算 (最高增益档)", "",
              "| MCS | 调制 | 所需 SNR (dB) | 灵敏度 (dBm) | TX EVM 限值 (dB) "
              "| 预测 EVM (dB) | 裕量 (dB) |", "|---|---|---|---|---|---|---|"]
    nf0 = nf_by_state[0]
    for m in MCS_TABLE:
        sens = sensitivity_dbm(nf0, bw, m.snr_req_db)
        budget = EvmBudget(snr_db=45.0, irr_db=52.0, ipn_rad2=ipn_rad2,
                           cpe_tracked_fraction=0.5, pa_nmse_db=-45.0,
                           sqnr_db=55.0)
        pred = budget.predicted_evm_db()
        margin = m.tx_evm_limit_db - pred
        lines.append(f"| {m.index} | {m.modulation} r{m.coding_rate} | "
                     f"{m.snr_req_db:.1f} | {sens:.1f} | {m.tx_evm_limit_db:.0f} "
                     f"| {pred:.1f} | {margin:.1f} |")
    lines.append("")

    args.out.mkdir(parents=True, exist_ok=True)
    out = args.out / "link_budget.md"
    out.write_text("\n".join(lines), encoding="utf-8")
    print(f"written: {out}")
    print("\n".join(lines[:14]))


if __name__ == "__main__":
    main()
