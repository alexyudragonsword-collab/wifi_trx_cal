"""CLI:  python -m wifitrx.handoff run|regress ...

run:      单个波形过链路,输出结果波形 + 指标 JSON
regress:  目录级批量回归,输出对账单 handoff_report.md
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from .regress import run_regression
from .runner import build_calibrated_trx, run_handoff
from .waveform_io import load_waveform, save_waveform


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(prog="python -m wifitrx.handoff")
    sub = ap.add_subparsers(dest="cmd", required=True)

    def common(p):
        p.add_argument("--bw", type=float, required=True,
                       help="channel bandwidth [Hz]")
        p.add_argument("--fs", type=float, default=None,
                       help="sample rate [Hz], default bw*4")
        p.add_argument("--seed", type=int, default=5,
                       help="process-corner seed of the modeled chip")
        p.add_argument("--cal-state", type=Path, default=None,
                       help="cal_state.json to restore instead of recalibrating")
        p.add_argument("--scenario", choices=("tx_only", "loopback", "rx_only"),
                       default="loopback")
        p.add_argument("--out", type=Path, default=Path("reports/handoff"))

    p_run = sub.add_parser("run", help="single waveform")
    common(p_run)
    p_run.add_argument("--wave", type=Path, required=True)

    p_reg = sub.add_parser("regress", help="directory of waveforms")
    common(p_reg)
    p_reg.add_argument("--dir", type=Path, required=True)

    args = ap.parse_args(argv)
    fs = args.fs or args.bw * 4
    tx, rx = build_calibrated_trx(args.bw, fs, seed=args.seed,
                                  cal_state_json=args.cal_state)
    args.out.mkdir(parents=True, exist_ok=True)

    if args.cmd == "run":
        wave = load_waveform(args.wave)
        res = run_handoff(wave, tx, rx, scenario=args.scenario)
        out_npz = args.out / f"{args.wave.stem}_out.npz"
        save_waveform(out_npz, res.output)
        out_json = args.out / f"{args.wave.stem}_metrics.json"
        out_json.write_text(json.dumps(res.metrics, indent=2, default=float))
        print(f"output:  {out_npz}\nmetrics: {out_json}")
        for k, v in res.metrics.items():
            print(f"  {k}: {v:.3f}" if isinstance(v, float) else f"  {k}: {v}")
    else:
        report = run_regression(args.dir, tx, rx, args.out,
                                scenario=args.scenario)
        print(f"report: {report}")


if __name__ == "__main__":
    main()
