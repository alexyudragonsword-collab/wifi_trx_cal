"""Figures for the calibration report (matplotlib Agg, English labels)."""
from __future__ import annotations

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402


def fig_convergence(trace, title: str, ylabel: str):
    fig, ax = plt.subplots(figsize=(6, 3.5))
    ax.plot(np.arange(len(trace)), trace, "o-")
    ax.set_xlabel("Iteration")
    ax.set_ylabel(ylabel)
    ax.set_title(title)
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    return fig


def fig_irr_before_after(freqs_hz, irr_before, irr_after, title: str):
    fig, ax = plt.subplots(figsize=(6, 3.5))
    ax.plot(np.asarray(freqs_hz) / 1e6, irr_before, "o-", label="before cal")
    ax.plot(np.asarray(freqs_hz) / 1e6, irr_after, "s-", label="after cal")
    ax.set_xlabel("Frequency [MHz]")
    ax.set_ylabel("IRR [dB]")
    ax.set_title(title)
    ax.legend()
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    return fig


def fig_code_sweep(trace, best_code: int, title: str):
    codes = [c for c, _ in trace]
    vals = [v for _, v in trace]
    fig, ax = plt.subplots(figsize=(6, 3.5))
    ax.plot(codes, vals, "o-")
    ax.axvline(best_code, color="tab:red", ls="--", label=f"selected code {best_code}")
    ax.axhline(-3.0, color="tab:gray", ls=":", label="-3 dB target")
    ax.set_xlabel("RC tuning code")
    ax.set_ylabel("Corner/reference ratio [dB]")
    ax.set_title(title)
    ax.legend()
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    return fig


def fig_power_table(table, title: str):
    codes = [c for c, _ in table]
    pouts = [p for _, p in table]
    fig, ax = plt.subplots(figsize=(6, 3.5))
    ax.plot(codes, pouts, "o-")
    ax.set_xlabel("Gain code [dB]")
    ax.set_ylabel("PA output power [dBm]")
    ax.set_title(title)
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    return fig


def fig_agc_sweep(rows, target_dbm: float, title: str):
    p_in = [r["p_in_dbm"] for r in rows]
    landed = [r["adc_in_dbm"] for r in rows]
    snr = [r["snr_db"] for r in rows]
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(6, 5), sharex=True)
    ax1.plot(p_in, landed, "o-")
    ax1.axhline(target_dbm, color="tab:red", ls="--", label="target")
    ax1.set_ylabel("ADC input (AC) [dBm]")
    ax1.legend()
    ax1.grid(True, alpha=0.3)
    ax2.plot(p_in, snr, "s-", color="tab:green")
    ax2.set_xlabel("RX input power [dBm]")
    ax2.set_ylabel("SNR [dB]")
    ax2.grid(True, alpha=0.3)
    fig.suptitle(title)
    fig.tight_layout()
    return fig
