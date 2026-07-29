"""Blocker/desense study: measured SNR vs the C/N budget decomposition.

Sweeps blocker power at a fixed wanted-signal level, measures in-band SNR
through the RX model, and overlays the budget terms (thermal at the AGC-
selected NF, reciprocal mixing).  Also prints the frac-N dirty-channel
table for the 6 GHz band.

Usage: python examples/run_blocker_study.py [--out reports/]
"""
from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from wifitrx.chain import RxChain, RxParams
from wifitrx.impairments.blocker import Blocker, reciprocal_mixing_noise_dbm
from wifitrx.impairments.phase_noise import (DEFAULT_WIFI7_LO_PROFILE, LOModel,
                                             ldbc_from_sphi)
from wifitrx.link.spur_planning import channel_spur_table
from wifitrx.units import KT_DBM_HZ, dbm_to_mw
from wifitrx.waveform.stimuli import single_tone

FS = 640e6
BW = 160e6


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, default=Path("reports"))
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)

    rx = RxChain(RxParams(bandwidth_hz=BW, lo=LOModel(enabled=True)), FS)
    p_sig = -60.0
    f_sig = 23e6
    offset = 200e6
    n = 1 << 16

    rows = []
    for p_b in np.arange(-70.0, -14.0, 5.0):
        p_tot = 10 * np.log10(dbm_to_mw(p_sig) + dbm_to_mw(p_b))
        rx.agc(p_tot)
        st = rx.params.lna_states[rx.lna_idx]
        sig = single_tone(f_sig, FS, n,
                          amp=np.sqrt(dbm_to_mw(p_sig)))
        blk = Blocker(offset_hz=offset, power_dbm=p_b, kind="cw")
        cap = rx(sig + blk.signal(n, FS), rng=np.random.default_rng(1))
        spec = np.abs(np.fft.fft(cap - np.mean(cap))) ** 2 / n ** 2
        k = int(round(f_sig * n / FS))
        p_s = float(np.sum(spec[[k - 1, k, k + 1]]))
        band = np.arange(n) * FS / n
        sel = (band > 2e6) & (band < BW / 2)
        sel[[k - 1, k, k + 1]] = False
        p_n = float(np.sum(spec[sel]))
        snr_meas = 10 * np.log10(p_s / p_n)

        # budget terms (referred to RX input)
        n_th = KT_DBM_HZ + st.nf_db + 10 * np.log10(BW / 2)
        l_off = float(ldbc_from_sphi(
            DEFAULT_WIFI7_LO_PROFILE.psd(np.array([offset])))[0])
        n_rm = reciprocal_mixing_noise_dbm(p_b, l_off, BW / 2)
        # ADC dynamic range: the blocker owns the AGC target level, pushing
        # the wanted signal toward the quantization floor
        adc = rx.params.adc
        q_dbfs = -(6.02 * adc.bits + 1.76) + 10 * np.log10((BW / 2) / (FS / 2))
        g_total = st.gain_db + rx.vga_db
        n_adc = adc.fullscale_dbm + q_dbfs - g_total
        n_tot = 10 * np.log10(dbm_to_mw(n_th) + dbm_to_mw(n_rm)
                              + dbm_to_mw(n_adc))
        rows.append((p_b, snr_meas, p_sig - n_tot, rx.lna_idx))
        print(f"P_blocker={p_b:6.1f} dBm  SNR_meas={snr_meas:6.1f} dB  "
              f"SNR_budget={p_sig - n_tot:6.1f} dB  lna_state={rx.lna_idx}")

    p_bs = [r[0] for r in rows]
    fig, ax = plt.subplots(figsize=(7, 4))
    ax.plot(p_bs, [r[1] for r in rows], "o-", label="measured SNR")
    ax.plot(p_bs, [r[2] for r in rows], "s--", label="budget (thermal + recip. mixing)")
    ax.set_xlabel("Blocker power at RX input [dBm]")
    ax.set_ylabel("In-band SNR [dB]")
    ax.set_title(f"Desense vs CW blocker @ {offset/1e6:.0f} MHz offset")
    ax.legend()
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    fig.savefig(args.out / "blocker_desense.png", dpi=140)

    dirty = [r for r in channel_spur_table(320e6, bands=("6g",))
             if r["dirty"]]
    lines = ["# 6 GHz 脏信道表 (320 MHz, frac-N 杂散)", "",
             "| 信道中心 (MHz) | frac | 最差带内杂散 (dBc) |", "|---|---|---|"]
    for r in dirty:
        lines.append(f"| {r['f_c_hz']/1e6:.0f} | {r['frac']:.4f} | "
                     f"{r['worst_inband_dbc']:.1f} |")
    (args.out / "dirty_channels.md").write_text("\n".join(lines),
                                                encoding="utf-8")
    print(f"\n{len(dirty)} dirty channels of 59; "
          f"written {args.out}/blocker_desense.png, dirty_channels.md")


if __name__ == "__main__":
    main()
