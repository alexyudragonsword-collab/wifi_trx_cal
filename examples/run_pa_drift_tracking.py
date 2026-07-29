"""PA thermal-drift scenario: RLS tracking DPD vs frozen DPD.

Usage: python examples/run_pa_drift_tracking.py [--out reports/]
Produces a Markdown table + PNG of EVM vs drift state for the tracking
DPD, the frozen DPD and the per-state oracle floor.
"""
from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from wifitrx.cal.dpd_tracking import track_dpd
from wifitrx.chain import RxChain, RxParams, TxChain, TxParams
from wifitrx.impairments.analog_filter import TunableLPF
from wifitrx.impairments.converters import ADCParams, DACParams
from wifitrx.impairments.iq_imbalance import FreqDepIQImbalance
from wifitrx.impairments.phase_noise import LOModel
from wifitrx.pa import DriftingReferencePA, DriftingScaledPA
from wifitrx.waveform import OFDMConfig, generate_ofdm


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--bw", type=float, default=80e6)
    ap.add_argument("--out", type=Path, default=Path("reports"))
    args = ap.parse_args()

    cfg = OFDMConfig(bandwidth_hz=args.bw, qam_order=256, n_symbols=6,
                     oversampling=4)
    fs = cfg.sample_rate_hz
    wf = generate_ofdm(cfg)

    drift = DriftingReferencePA(drive0=0.13, drive_span=0.02,
                                beta_a_span=0.15, alpha_p_span=0.5)
    pa = DriftingScaledPA(drift, gain_db=26.0, psat_dbm=28.0)
    tx = TxChain(TxParams(bandwidth_hz=args.bw, dac=DACParams(enabled=True),
                          lpf=TunableLPF(enabled=False),
                          iq=FreqDepIQImbalance(enabled=False),
                          lo=LOModel(enabled=False), pa_enabled=True),
                 fs, pa=pa)
    rx = RxChain(RxParams(bandwidth_hz=args.bw, nonlin_enabled=False,
                          iq=FreqDepIQImbalance(enabled=False), dc_offset=(),
                          lpf=TunableLPF(enabled=False),
                          adc=ADCParams(enabled=False),
                          lo=LOModel(enabled=False)), fs)
    rx.noise_enabled = False
    rx.agc(-20.0)

    schedule = np.linspace(0.0, 1.0, 10)
    res = track_dpd(tx, rx, wf, schedule, drive_scale=0.12)

    states = [t["state"] for t in res.trace]
    fig, ax = plt.subplots(figsize=(7, 4))
    ax.plot(states, [t["evm_track_db"] for t in res.trace], "o-",
            label="tracking DPD (RLS)")
    ax.plot(states, [t["evm_frozen_db"] for t in res.trace], "s--",
            label="frozen DPD")
    ax.axhline(res.metrics_after["evm_oracle_final_db"], color="tab:gray",
               ls=":", label="oracle floor @ final state")
    ax.set_xlabel("Drift state (0 = cold, 1 = hot)")
    ax.set_ylabel("TX EVM [dB]")
    ax.set_title("DPD tracking under PA thermal drift")
    ax.legend()
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    args.out.mkdir(parents=True, exist_ok=True)
    fig.savefig(args.out / "pa_drift_tracking.png", dpi=140)

    print(f"track final {res.metrics_after['evm_track_final_db']:.1f} dB, "
          f"oracle {res.metrics_after['evm_oracle_final_db']:.1f} dB, "
          f"gap {res.metrics_after['track_vs_oracle_db']:.1f} dB, "
          f"frozen worst {res.metrics_after['evm_frozen_worst_db']:.1f} dB")
    print(f"figure: {args.out / 'pa_drift_tracking.png'}")


if __name__ == "__main__":
    main()
