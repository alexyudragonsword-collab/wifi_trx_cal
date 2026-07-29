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


def _plot_constellation(ax, syms, evm_db, title, max_pts=6000):
    pts = np.ravel(syms)
    if pts.size > max_pts:
        idx = np.random.default_rng(0).choice(pts.size, max_pts, replace=False)
        pts = pts[idx]
    ax.plot(pts.real, pts.imag, ".", ms=1.2, alpha=0.5)
    ax.set_title(f"{title}  (EVM {evm_db:.1f} dB)", fontsize=9)
    ax.set_aspect("equal")
    ax.grid(True, alpha=0.25)
    lim = 1.55
    ax.set_xlim(-lim, lim)
    ax.set_ylim(-lim, lim)


def fig_constellation_compare(snap_before: dict, snap_after: dict):
    """Equalized RX constellation before vs after the full calibration."""
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(8, 4))
    _plot_constellation(ax1, snap_before["syms_eq"], snap_before["evm_db"],
                        "before calibration")
    _plot_constellation(ax2, snap_after["syms_eq"], snap_after["evm_db"],
                        "after calibration")
    fig.suptitle("Loopback constellation (per-tone EQ + CPE removed)")
    fig.tight_layout()
    return fig


def fig_psd_compare(snap_before: dict, snap_after: dict):
    """PA-output PSD before vs after calibration, with the WiFi mask."""
    from ..metrics.spectrum import check_mask, default_wifi_mask, psd

    fs = snap_before["fs"]
    bw = snap_before["bandwidth_hz"]
    fig, ax = plt.subplots(figsize=(8, 4))
    for snap, label, color in ((snap_before, "before calibration", "tab:blue"),
                               (snap_after, "after calibration", "tab:orange")):
        f, p = psd(snap["pa_out"], fs)
        # padpd psd() is peak-normalized; before cal the peak is the LO-leak
        # spike, which would shift the whole curve down and fake the
        # adjacent-channel comparison.  Re-reference each curve to its
        # in-band median so shoulders compare and the leak spike shows
        # above 0 dB.
        inband = np.abs(f) < 0.4 * bw
        p = p - np.median(p[inband])
        ax.plot(f / 1e6, p, lw=0.9, label=label, color=color)
    try:
        mask = default_wifi_mask(bw)
        _, _, mask_db = check_mask(f, p, mask)
        ax.plot(f / 1e6, mask_db, "k--", lw=1.0, label="spectral mask")
    except Exception:
        pass
    ax.set_xlabel("Frequency [MHz]")
    ax.set_ylabel("PSD [dB]")
    ax.set_title("PA output spectrum")
    ax.set_ylim(-90, 5)
    ax.legend(fontsize=8)
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
