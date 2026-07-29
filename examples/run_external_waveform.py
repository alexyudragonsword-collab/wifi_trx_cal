"""Comm-engineer handoff demo: run an EXTERNAL IQ waveform through the
calibrated transceiver model.

The communication team's own 802.11be PHY waveform (complex baseband,
full-scale digital units, |I|,|Q| <= 1, at fs = bandwidth * oversampling)
is passed through TX -> loopback -> RX with all corrections active; the
script returns the corrected RX IQ and channel metrics.

Usage:
  python examples/run_external_waveform.py --iq my_wave.npy --fs 640e6 --bw 160e6
  (without --iq a demo OFDM waveform is generated)
"""
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np

from wifitrx.cal.sequence import agc_for_loopback, run_full_cal
from wifitrx.cal.sync import _fractional_advance, align_delay
from wifitrx.chain import LoopbackPath, RxChain, RxParams, TxChain, TxParams, run_loopback
from wifitrx.units import power_dbm
from wifitrx.waveform import OFDMConfig, generate_ofdm


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--iq", type=Path, default=None,
                    help=".npy complex64/128 baseband waveform (digital FS units)")
    ap.add_argument("--bw", type=float, default=160e6)
    ap.add_argument("--fs", type=float, default=None,
                    help="sample rate of the waveform (default bw*4)")
    ap.add_argument("--seed", type=int, default=5)
    ap.add_argument("--out", type=Path, default=Path("reports/external_rx_iq.npy"))
    args = ap.parse_args()

    bw = args.bw
    fs = args.fs or bw * 4

    if args.iq is not None:
        x = np.load(args.iq).astype(complex)
        print(f"loaded {args.iq}: {x.size} samples, "
              f"digital power {10*np.log10(np.mean(np.abs(x)**2)):.1f} dBFS")
    else:
        cfg = OFDMConfig(bandwidth_hz=bw, qam_order=1024, n_symbols=8,
                         oversampling=int(round(fs / bw)))
        x = generate_ofdm(cfg).x * 0.12
        print("no --iq given; generated a demo OFDM waveform at 0.12 FS rms")

    # build + calibrate the impaired transceiver (in a real handoff the
    # correction state would be loaded from cal_state.json instead)
    rng = np.random.default_rng(args.seed)
    txp = TxParams(bandwidth_hz=bw).randomize(rng)
    rxp = RxParams(bandwidth_hz=bw).randomize(rng)
    txp.lpf.fc_nominal_hz = bw / 2 * 1.3
    rxp.lpf.fc_nominal_hz = bw / 2 * 1.12
    tx = TxChain(txp, fs)
    rx = RxChain(rxp, fs)
    cal_cfg = OFDMConfig(bandwidth_hz=bw, qam_order=256, n_symbols=4,
                         oversampling=int(round(fs / bw)))
    path = LoopbackPath(atten_db=40.0, delay_ns=6.0)
    run_full_cal(tx, rx, cal_cfg, path)

    # run the external waveform through the calibrated chain
    agc_for_loopback(tx, rx, path, x)
    nodes: dict = {}
    y_pa = tx(x, nodes=nodes)
    cap = run_loopback(tx, rx, x, path)
    _, _, info = align_delay(x, cap, max_lag=2048)
    cap = _fractional_advance(cap, info["lag_total"])

    args.out.parent.mkdir(parents=True, exist_ok=True)
    np.save(args.out, cap)
    print(f"PA output power: {nodes['pa_out_dbm']:.1f} dBm, "
          f"avg PAE {100*nodes['pa_avg_pae']:.1f} %")
    print(f"loopback delay: {info['lag_total']/fs*1e9:.1f} ns; "
          f"corrected RX IQ written to {args.out}")


if __name__ == "__main__":
    main()
