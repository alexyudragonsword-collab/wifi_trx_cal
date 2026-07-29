# Vendored from PA_DPD:src/padpd/plotting.py (internal sibling repo), adapted for wifitrx.
# Upstream changes should be ported manually; see PROVENANCE.md.
"""Standard comparison plots for PA modeling and DPD results."""

from __future__ import annotations

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np

from .metrics.amam import am_am_am_pm
from .metrics.ccdf import ccdf
from .metrics.spectrum import psd


def plot_psd_comparison(signals: dict[str, np.ndarray], fs: float,
                        mask: np.ndarray | None = None,
                        path: str | None = None):
    """Overlay PSDs of several signals (dB relative to each peak)."""
    fig, ax = plt.subplots(figsize=(8, 5))
    for label, x in signals.items():
        f, p = psd(x, fs)
        ax.plot(f / 1e6, p, label=label, lw=1)
    if mask is not None:
        f_mask = np.concatenate([-mask[::-1, 0], mask[:, 0]])
        v_mask = np.concatenate([mask[::-1, 1], mask[:, 1]])
        ax.plot(f_mask / 1e6, v_mask, "k--", label="spectral mask", lw=1.2)
    ax.set_xlabel("Frequency (MHz)")
    ax.set_ylabel("PSD (dBr)")
    ax.set_ylim(-90, 5)
    ax.grid(True, alpha=0.3)
    ax.legend()
    fig.tight_layout()
    if path:
        fig.savefig(path, dpi=150)
        plt.close(fig)
    return fig


def plot_constellation(points_by_label: dict[str, np.ndarray],
                       path: str | None = None):
    """Scatter one or more received constellations side by side."""
    n = len(points_by_label)
    fig, axes = plt.subplots(1, n, figsize=(5 * n, 5), squeeze=False)
    for ax, (label, pts) in zip(axes[0], points_by_label.items()):
        pts = np.asarray(pts).ravel()
        step = max(1, len(pts) // 20_000)  # cap point count
        ax.plot(pts.real[::step], pts.imag[::step], ".", ms=1, alpha=0.5)
        ax.set_title(label)
        ax.set_xlabel("I")
        ax.set_ylabel("Q")
        ax.set_aspect("equal")
        ax.grid(True, alpha=0.3)
    fig.tight_layout()
    if path:
        fig.savefig(path, dpi=150)
        plt.close(fig)
    return fig


def plot_ccdf(cases: dict[str, np.ndarray], path: str | None = None):
    """Overlay power CCDF curves of several signals."""
    fig, ax = plt.subplots(figsize=(7, 5))
    for label, x in cases.items():
        level, prob = ccdf(x)
        ax.semilogy(level, np.maximum(prob, 1e-8), label=label, lw=1.2)
    ax.set_xlabel("dB above average power")
    ax.set_ylabel("CCDF  P(power > level)")
    ax.set_ylim(1e-6, 1.1)
    ax.grid(True, which="both", alpha=0.3)
    ax.legend()
    fig.tight_layout()
    if path:
        fig.savefig(path, dpi=150)
        plt.close(fig)
    return fig


def plot_am_curves(cases: dict[str, tuple[np.ndarray, np.ndarray]],
                   path: str | None = None):
    """AM-AM and AM-PM scatter for one or more (x, y) signal pairs."""
    fig, (ax_am, ax_pm) = plt.subplots(1, 2, figsize=(11, 5))
    for label, (x, y) in cases.items():
        res = am_am_am_pm(x, y)
        step = max(1, len(res["r_in"]) // 20_000)
        ax_am.plot(res["r_in"][::step], res["gain"][::step], ".", ms=1,
                   alpha=0.4, label=label)
        ax_pm.plot(res["r_in"][::step], res["phase_deg"][::step], ".", ms=1,
                   alpha=0.4, label=label)
    ax_am.set_xlabel("|x| (input envelope)")
    ax_am.set_ylabel("|y| / |x| (gain)")
    ax_am.set_title("AM-AM")
    ax_pm.set_xlabel("|x| (input envelope)")
    ax_pm.set_ylabel("phase shift (deg)")
    ax_pm.set_title("AM-PM")
    for ax in (ax_am, ax_pm):
        ax.grid(True, alpha=0.3)
        ax.legend(markerscale=8)
    fig.tight_layout()
    if path:
        fig.savefig(path, dpi=150)
        plt.close(fig)
    return fig
