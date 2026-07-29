"""Comm-engineer handoff demo, now on the standardized handoff API.

Converts a raw .npy (if given) into wifitrx-wave-v1, validates it, runs
the chosen scenario through a calibrated transceiver and writes the
output waveform + metrics.  See docs/handoff_zh.md for the full contract.

Usage:
  python examples/run_external_waveform.py --iq my_wave.npy --fs 1.28e9 --bw 320e6
  (without --iq a demo OFDM waveform is generated)
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

from wifitrx.handoff import (Waveform, build_calibrated_trx, run_handoff,
                             save_waveform, validate_waveform)
from wifitrx.waveform import OFDMConfig, generate_ofdm


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--iq", type=Path, default=None,
                    help=".npy complex baseband waveform (digital FS units)")
    ap.add_argument("--bw", type=float, default=160e6)
    ap.add_argument("--fs", type=float, default=None)
    ap.add_argument("--seed", type=int, default=5)
    ap.add_argument("--scenario", default="loopback",
                    choices=("tx_only", "loopback", "rx_only"))
    ap.add_argument("--out", type=Path, default=Path("reports/handoff"))
    args = ap.parse_args()

    bw = args.bw
    fs = args.fs or bw * 4
    if args.iq is not None:
        iq = np.load(args.iq).astype(complex)
    else:
        cfg = OFDMConfig(bandwidth_hz=bw, qam_order=1024, n_symbols=8,
                         oversampling=int(round(fs / bw)))
        iq = generate_ofdm(cfg).x * 0.12
        print("no --iq given; generated a demo OFDM waveform at 0.12 FS rms")

    wave = Waveform(iq=iq, fs_hz=fs, bandwidth_hz=bw,
                    description="external handoff demo")
    issues = validate_waveform(wave)
    if issues:
        raise SystemExit("波形校验未通过:\n- " + "\n- ".join(issues))

    tx, rx = build_calibrated_trx(bw, fs, seed=args.seed)
    res = run_handoff(wave, tx, rx, scenario=args.scenario)

    args.out.mkdir(parents=True, exist_ok=True)
    out_npz = save_waveform(args.out / "external_out.npz", res.output)
    (args.out / "external_metrics.json").write_text(
        json.dumps(res.metrics, indent=2, default=float))
    for k, v in res.metrics.items():
        print(f"  {k}: {v:.3f}" if isinstance(v, float) else f"  {k}: {v}")
    print(f"output waveform: {out_npz}")


if __name__ == "__main__":
    main()
