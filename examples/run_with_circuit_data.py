"""Full calibration with circuit-simulation data instead of behavioral defaults.

Builds the transceiver from the CSV exports in --data-dir (see
docs/circuit_data_zh.md for schemas; circuit_data/ holds templates),
runs the canonical calibration sequence and writes the report.

Usage: python examples/run_with_circuit_data.py [--data-dir circuit_data]
       [--bw 160e6] [--out reports/circuit]
"""
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np

from wifitrx.cal.base import save_cal_state
from wifitrx.cal.residuals import run_conditions
from wifitrx.cal.sequence import run_full_cal
from wifitrx.chain import LoopbackPath, RxChain, RxParams, TxChain, TxParams
from wifitrx.circuit_import import fit_lpf_from_ac, load_pll_pn_csv
from wifitrx.impairments.phase_noise import LOModel
from wifitrx.pa import ScaledPA, load_hb_pa
from wifitrx.report.generator import generate_report
from wifitrx.waveform import OFDMConfig


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir", type=Path, default=Path("circuit_data"))
    ap.add_argument("--bw", type=float, default=320e6,
                    help="320e6 matches the template LPF (208 MHz corner)")
    ap.add_argument("--seed", type=int, default=5,
                    help="seed for impairments NOT covered by circuit data")
    ap.add_argument("--out", type=Path, default=Path("reports/circuit"))
    args = ap.parse_args()

    bw = args.bw
    cfg = OFDMConfig(bandwidth_hz=bw, qam_order=1024, n_symbols=6,
                     oversampling=4)
    fs = cfg.sample_rate_hz
    d = args.data_dir

    # circuit data: LO profile, TX LPF, PA
    lo_profile = load_pll_pn_csv(d / "pll_pn_6g.csv")
    tx_lpf, lpf_info = fit_lpf_from_ac(d / "lpf_ac_tx.csv",
                                       fc_nominal_hz=bw / 2 * 1.3)
    wh_pa = load_hb_pa(str(d / "pa_hb_amam.csv"))
    print(f"LPF: corner {lpf_info['fc_measured_hz']/1e6:.1f} MHz "
          f"(rc_error {100*lpf_info['rc_error']:+.1f}%), "
          f"order {lpf_info['order']}")

    # remaining impairments (IQ, DC, IM2...) still randomized process draws
    rng = np.random.default_rng(args.seed)
    txp = TxParams(bandwidth_hz=bw).randomize(rng)
    rxp = RxParams(bandwidth_hz=bw).randomize(rng)
    txp.lpf = tx_lpf
    txp.lo = LOModel(freq_hz=6.0e9, profile=lo_profile)
    rxp.lo = LOModel(freq_hz=6.0e9, profile=lo_profile)
    rxp.lpf.fc_nominal_hz = bw / 2 * 1.12

    scaled_pa = ScaledPA(wh_pa, gain_db=26.0, psat_dbm=28.0)
    tx = TxChain(txp, fs, pa=scaled_pa)
    rx = RxChain(rxp, fs)
    print(f"PA from HB table: P1dB(out) {scaled_pa.p1db_out_dbm:.1f} dBm")

    results = run_full_cal(tx, rx, cfg, LoopbackPath(atten_db=40.0, delay_ns=6.0))
    args.out.mkdir(parents=True, exist_ok=True)
    report = generate_report(results, args.out,
                             title=f"电路数据校准报告 (BW={bw/1e6:.0f} MHz)")
    save_cal_state(args.out / "cal_state.json", tx.correction_state(),
                   rx.correction_state(), results,
                   fs_hz=cfg.sample_rate_hz,
                   conditions=run_conditions(cfg, tx, rx, with_dpd=True))
    final = {r.name: r for r in results}["final_loopback_evm"]
    print(f"final loopback EVM {final.metrics_after['evm_db']:.1f} dB, "
          f"TX EVM {final.metrics_after['tx_evm_db']:.1f} dB")
    print(f"report: {report}")


if __name__ == "__main__":
    main()
