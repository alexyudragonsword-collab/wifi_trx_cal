"""Build docs/pn_cpe_note_11ac_vs_11ax.pdf — why per-symbol CPE removal
buys less phase-noise EVM on the 11ax/be numerology than on 11ac/n.

Three pages: the derivation (symbol-mean phase -> sinc^2 weight ->
hand-over at 0.443/T), the numbers for the shipped LO profile, and a
three-panel figure (time domain, weight over L(f), cumulative removed
share).  Typeset with matplotlib mathtext, so it builds without LaTeX::

    MPLBACKEND=Agg python tools/build_pn_cpe_note.py --out docs/

The numbers are computed here from the library, not copied in, so the
note cannot drift from cpe_partition().  The time-domain readings quoted
in the text (1.55 / 0.36 dB, 1.4 +/- 0.2 dB) are from pn_cpe_study at
40 MHz / 32 frames (CHANGELOG 0.7.10-0.7.11).
"""
from __future__ import annotations

import argparse
import sys
import textwrap
from pathlib import Path

import matplotlib
import matplotlib.image as mpimg
import numpy as np
from matplotlib.backends.backend_pdf import PdfPages
from matplotlib.figure import Figure
from matplotlib.lines import Line2D

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from wifitrx.impairments.phase_noise import (  # noqa: E402
    DEFAULT_WIFI7_LO_PROFILE, LOModel, cpe_partition, ldbc_from_sphi,
    sphi_from_ldbc)

matplotlib.rcParams["mathtext.fontset"] = "cm"

T_AX, T_AC = 12.8e-6, 3.2e-6
F1, F2 = 1e4, 1e8                 # the ipn band LOModel.ipn_dbc integrates
W, H = 8.27, 11.69                # A4 inches
LM, RM, TOP = 0.9, 0.9, 0.75
BODY = 10.5


def numbers() -> dict:
    lo = DEFAULT_WIFI7_LO_PROFILE
    pa = cpe_partition(lo.psd, T_AX, F1, F2)
    pc = cpe_partition(lo.psd, T_AC, F1, F2)
    s0 = float(sphi_from_ldbc(-104.1))
    tot = pa["total_rad2"]
    gain = lambda p: -10 * np.log10(1 - p["tracked_fraction"])  # noqa: E731
    return {"s0": s0, "tot": tot, "ax": pa, "ac": pc,
            "approx_ax": s0 / (2 * T_AX) / tot, "approx_ac": s0 / (2 * T_AC) / tot,
            "gain_ax": gain(pa), "gain_ac": gain(pc)}


def figure(nb: dict, path: Path) -> None:
    lo = DEFAULT_WIFI7_LO_PROFILE
    pa, pc = nb["ax"], nb["ac"]
    fig = Figure(figsize=(11, 9.2))
    gs = fig.add_gridspec(3, 1, height_ratios=(1.15, 1.2, 0.9), hspace=0.42)

    # (1) one realization with the per-symbol means of both symbol lengths
    fs = 40e6 * 4
    n = int(round(4 * T_AX * fs))
    phi = LOModel(profile=lo).phase(1 << 16, fs, np.random.default_rng(3))[:n]
    t = np.arange(n) / fs * 1e6
    ax = fig.add_subplot(gs[0])
    ax.plot(t, np.degrees(phi), color="0.35", lw=0.7,
            label="LO phase φ(t), shipped profile (one realization)")
    for T, col, nm in ((T_AC, "tab:green", "11ac/n: 3.2 µs"),
                       (T_AX, "tab:red", "11ax/be: 12.8 µs")):
        L = int(round(T * fs))
        means = np.repeat([np.degrees(phi[i:i + L].mean())
                           for i in range(0, n, L)], L)[:n]
        ax.step(t, means, where="post", color=col, lw=1.8,
                label=f"per-symbol mean = the CPE the modem removes, {nm} symbol")
    for i in range(0, n, int(round(T_AX * fs))):
        ax.axvline(t[i], color="tab:red", lw=0.6, ls=":", alpha=0.6)
    ax.set_xlim(0, t[-1])
    ax.set_xlabel("time [µs]")
    ax.set_ylabel("phase [deg]")
    ax.set_title("(1) Time domain: CPE removal subtracts one number per symbol — "
                 "the symbol-mean phase.\nWhat is left, φ(t) − mean, becomes ICI.  "
                 "A 4× longer symbol follows the wander 4× more coarsely.", fontsize=9.5)
    ax.legend(fontsize=7.5, loc="upper right")
    ax.grid(alpha=0.3)

    # (2) L(f) with the removable weight sinc^2(fT)
    f = np.logspace(3, 8, 800)
    S = lo.psd(f)
    ax = fig.add_subplot(gs[1])
    ax.semilogx(f, ldbc_from_sphi(S), color="tab:blue", lw=1.8, label="shipped LO profile L(f)")
    ax.set_ylabel("L(f) [dBc/Hz]")
    ax.set_ylim(-160, -95)
    ax.set_xlabel("offset from carrier [Hz]")
    ax2 = ax.twinx()
    for T, col, p in ((T_AC, "tab:green", pc), (T_AX, "tab:red", pa)):
        w = np.sinc(f * T) ** 2
        ax2.semilogx(f, w, color=col, lw=1.6,
                     label=f"removable share sinc²(f·T), T = {T * 1e6:.1f} µs")
        ax2.axvline(p["f_3db_hz"], color=col, ls=":", lw=1.2)
        ax2.annotate(f"f₋₃dB = 0.443/T\n= {p['f_3db_hz'] / 1e3:.0f} kHz",
                     (p["f_3db_hz"], 0.52), fontsize=7.5, color=col,
                     ha="left" if T == T_AC else "right",
                     xytext=(4 if T == T_AC else -4, 0), textcoords="offset points")
        ax.fill_between(f, -160, ldbc_from_sphi(S * w), color=col, alpha=0.18)
    ax2.set_ylim(0, 1.05)
    ax2.set_ylabel("share CPE removes")
    h1, l1 = ax.get_legend_handles_labels()
    h2, l2 = ax2.get_legend_handles_labels()
    ax.legend(h1 + h2, l1 + l2, fontsize=7.5, loc="lower left")
    ax.grid(alpha=0.3, which="both")
    ax.set_title("(2) Frequency domain: the symbol mean is a rectangular average, "
                 "|W(f)|² = sinc²(f·T).\nShaded = the part of S_φ(f) that CPE removes; "
                 "the plateau (10–100 kHz) sits between the two hand-over points.",
                 fontsize=9.5)

    # (3) cumulative removed fraction
    ax = fig.add_subplot(gs[2])
    fi = np.logspace(np.log10(F1), np.log10(F2), 4000)
    Si = lo.psd(fi)

    def cum(w):
        inc = 0.5 * (Si[1:] * w[1:] + Si[:-1] * w[:-1]) * np.diff(fi)
        return np.concatenate([[0.0], np.cumsum(inc)]) / nb["tot"]

    for T, col, nm, p, g in ((T_AC, "tab:green", "11ac/n", pc, nb["gain_ac"]),
                             (T_AX, "tab:red", "11ax/be", pa, nb["gain_ax"])):
        c = 100 * cum(np.sinc(fi * T) ** 2)
        ax.semilogx(fi, c, color=col, lw=1.8,
                    label=f"{nm}: removes {100 * p['tracked_fraction']:.1f}% of the phase "
                          f"power → CPE buys {g:.2f} dB")
        ax.annotate(f"{c[-1]:.1f}%", (fi[-1], c[-1]), fontsize=8, color=col,
                    ha="right", va="bottom")
    ax.set_xlabel("offset from carrier [Hz]")
    ax.set_ylabel("removed phase power\n(cumulative) [% of total]")
    ax.set_ylim(0, 35)
    ax.grid(alpha=0.3, which="both")
    ax.legend(fontsize=8, loc="upper left")
    ax.set_title("(3) Cumulative:  removed / total = ∫S_φ·sinc²(fT)df / ∫S_φ df   "
                 "(10 kHz – 100 MHz, the ipn band)\nflat-plateau estimate S₀/(2T): "
                 f"11ac {100 * nb['approx_ac']:.0f} %, 11ax {100 * nb['approx_ax']:.0f} % "
                 "— the gain scales as 1/T", fontsize=9.5)
    fig.savefig(path, dpi=125)


class Page:
    """Top-down text layout on an A4 Figure (mathtext for the formulas)."""

    def __init__(self, pdf, title=None):
        self.pdf = pdf
        self.fig = Figure(figsize=(W, H))
        self.y = H - TOP
        if title:
            self.text(title, size=15, weight="bold", gap=0.18)

    def _yf(self):
        return self.y / H

    def text(self, s, size=BODY, weight="normal", gap=0.06, x=LM, style="normal",
             color="black"):
        self.fig.text(x / W, self._yf(), s, fontsize=size, weight=weight, va="top",
                      ha="left", style=style, color=color)
        self.y -= size / 72 * 1.35 + gap

    def para(self, s, width=92, size=BODY, gap=0.12):
        for line in textwrap.wrap(s, width=width):
            self.text(line, size=size, gap=0.0)
        self.y -= gap

    def heading(self, s):
        self.y -= 0.1
        self.text(s, size=12.5, weight="bold", gap=0.08)

    def formula(self, s, size=13, height=0.55, gap=0.14):
        self.y -= 0.08
        self.fig.text(0.5, (self.y - height / 2) / H, s, fontsize=size, va="center",
                      ha="center")
        self.y -= height + gap

    def table(self, header, rows, colx, size=BODY):
        xs = [LM + c for c in colx]
        for x, h in zip(xs, header):
            self.fig.text(x / W, self._yf(), h, fontsize=size, weight="bold", va="top")
        self.y -= size / 72 * 1.45
        self.fig.add_artist(Line2D([LM / W, (W - RM) / W], [self._yf() + 0.004] * 2,
                                   lw=0.6, color="0.3", transform=self.fig.transFigure))
        for r in rows:
            for x, c in zip(xs, r):
                self.fig.text(x / W, self._yf(), c, fontsize=size, va="top")
            self.y -= size / 72 * 1.45
        self.y -= 0.14

    def image(self, path):
        img = mpimg.imread(path)
        ar = img.shape[0] / img.shape[1]
        w = W - LM - RM
        h = w * ar
        ax = self.fig.add_axes([LM / W, (self.y - h) / H, w / W, h / H])
        ax.imshow(img)
        ax.axis("off")
        self.y -= h + 0.12

    def footer(self, s):
        self.fig.text(0.5, 0.35 / H, s, fontsize=8, ha="center", color="0.4")

    def close(self):
        self.pdf.savefig(self.fig)


def build(out_dir: Path) -> Path:
    nb = numbers()
    pa, pc = nb["ax"], nb["ac"]
    png = out_dir / "pn_cpe_note_11ac_vs_11ax.png"
    figure(nb, png)
    pdf_path = out_dir / "pn_cpe_note_11ac_vs_11ax.pdf"
    foot = "wifitrx — pn_cpe_study — page {} / 3"
    with PdfPages(pdf_path) as pdf:
        p = Page(pdf, "Why CPE removal buys less on 11ax/be than on 11ac/n")
        p.text("wifitrx phase-noise / CPE study — 40 MHz, shipped WiFi 7 LO profile, "
               "single LO", size=9.5, style="italic", color="0.35", gap=0.14)
        p.heading("1.  What CPE removal is: one number per symbol")
        p.para("Within one OFDM symbol of FFT length T, the received phase noise "
               "exp(jφ(t)) becomes, after the DFT,")
        p.formula(r"$Y_k \;=\; J_0\,X_k \;+\; \sum_{m\neq k} J_{k-m}\,X_m,\qquad "
                  r"J_0=\dfrac{1}{T}\int_0^T e^{\,j\varphi(t)}\,dt\;\approx\;"
                  r"e^{\,j\bar{\varphi}}$", height=0.7)
        p.para("The sum over m ≠ k is the inter-carrier interference (ICI).  CPE removal "
               "multiplies each symbol by exp(−j φ̂̄): it subtracts the symbol-mean phase "
               "φ̄, a single number per symbol.  Whatever remains, φ(t) − φ̄, turns into "
               "ICI, and no single rotation can touch it.")
        p.para("Panel (1) of the figure (page 3): the grey trace is one LO phase "
               "realization; the green staircase is the per-symbol mean for 3.2 µs "
               "symbols, the red one for 12.8 µs.  The red staircase follows the wander "
               "four times more coarsely, and the area between the grey trace and the red "
               "staircase is the ICI that 11ax keeps.")
        p.heading("2.  Taking the symbol mean is a sinc² weight in frequency")
        p.para("The symbol mean is a rectangular-window average, whose squared frequency "
               "response is")
        p.formula(r"$|W(f)|^2 \;=\; \mathrm{sinc}^2(fT) \;=\; "
                  r"\left[\dfrac{\sin(\pi f T)}{\pi f T}\right]^2$", height=0.65)
        p.para("so the phase-noise power is split by frequency into a removable part and "
               "a part left behind:")
        p.formula(r"$\sigma^2_{\mathrm{CPE}} = \int S_\varphi(f)\,\mathrm{sinc}^2(fT)\,df "
                  r"\quad(\mathrm{removable}),\qquad \sigma^2_{\mathrm{ICI}} = "
                  r"\int S_\varphi(f)\,\left[1-\mathrm{sinc}^2(fT)\right]df "
                  r"\quad(\mathrm{left\ behind})$", size=12, height=0.55)
        p.para("Solving sinc²(fT) = 1/2 gives the hand-over frequency:")
        p.formula(r"$f_{-3\,\mathrm{dB}} \;=\; \dfrac{0.443}{T}$", height=0.6)
        p.table(("", "T", "f₋₃dB"),
                (("11ac/n", "3.2 µs", f"{pc['f_3db_hz'] / 1e3:.0f} kHz"),
                 ("11ax/be", "12.8 µs", f"{pa['f_3db_hz'] / 1e3:.0f} kHz")),
                (0.0, 1.6, 3.0))
        p.para("A 4× longer symbol makes the band CPE can act on 4× narrower.  This is "
               "pure geometry and has nothing to do with the LO.  The two S-shaped curves "
               "in panel (2) are the two weights; the shaded areas are S_φ(f)·sinc²(fT), "
               "the slice of the spectrum each standard actually removes.")
        p.footer(foot.format(1))
        p.close()

        p = Page(pdf)
        p.heading("3.  How much gets removed depends on where the LO's noise sits")
        p.para("The shipped LO profile has a flat plateau S₀ (−104.1 dBc/Hz) from 10 to "
               "100 kHz.  That plateau sits exactly between 35 kHz and 138 kHz: the 11ac "
               "weight covers most of it, while the 11ax weight has already fallen to zero "
               "before the plateau ends.")
        p.para("For a plateau wider than 1/T there is a handy approximation, using")
        p.formula(r"$\int_0^{\infty}\mathrm{sinc}^2(fT)\,df \;=\; \dfrac{1}{2T}\qquad"
                  r"\Longrightarrow\qquad \sigma^2_{\mathrm{CPE}} \;\approx\; "
                  r"\dfrac{S_0}{2T},\qquad \mathrm{removed\ fraction} \;\approx\; "
                  r"\dfrac{S_0}{2T\,\sigma^2_\varphi} \;\propto\; \dfrac{1}{T}$",
                  size=12, height=0.75)
        p.para(f"With S₀ = {nb['s0'] * 1e11:.1f}×10⁻¹¹ rad²/Hz and total phase power "
               f"σ²_φ = {nb['tot'] * 1e5:.1f}×10⁻⁵ rad² (10 kHz – 100 MHz, IPN "
               f"{10 * np.log10(nb['tot'] / 2):.1f} dBc):")
        p.table(("", "approx. S₀/(2T)", "exact integral",
                 "CPE gain  −10·log₁₀(1 − fraction)"),
                (("11ac/n", f"{100 * nb['approx_ac']:.1f} %",
                  f"{100 * pc['tracked_fraction']:.1f} %", f"{nb['gain_ac']:.2f} dB"),
                 ("11ax/be", f"{100 * nb['approx_ax']:.1f} %",
                  f"{100 * pa['tracked_fraction']:.1f} %", f"{nb['gain_ax']:.2f} dB")),
                (0.0, 1.3, 2.9, 4.4))
        p.para("Panel (3) is the cumulative exact integral: the green curve climbs to "
               f"{100 * pc['tracked_fraction']:.1f} %, the red one flattens around 35 kHz "
               f"and stops at {100 * pa['tracked_fraction']:.1f} %.  This agrees with the "
               "time-domain model's direct readings of 1.55 / 0.36 dB (40 MHz, 32 frames); "
               "the difference is the integration band and realization spread.")
        p.heading("In one sentence")
        p.para("The CPE-removal gain is ∫ S_φ(f)·sinc²(fT) df and the weight's width scales "
               "as 1/T.  WiFi 7 stretches T by 4×, shrinking the removable band from "
               "138 kHz to 35 kHz, and this class of PLL puts its noise plateau exactly "
               "between those two numbers — so 11ac takes out nearly a third of the phase "
               "power and 11ax less than a tenth.  The extra loss is not a weaker modem "
               "algorithm; it is ICI, and it cannot be removed.")
        p.heading("Where the numbers come from")
        p.para("Model: wifitrx pn_cpe_study (isolation method, phase noise the only "
               "impairment, true channel unity).  Closed forms: cpe_partition() over the "
               "LO profile with the 12.8 µs / 3.2 µs FFT lengths, computed by this "
               "script.  Time-domain readings: 40 MHz, 6-pilot CPE + LTF channel "
               "estimate, 32 frames; the standards gap in the modem form is 1.4 ± 0.2 dB "
               "(1σ over seeds), the ICI floor alone scatters 0.05 dB.")
        p.footer(foot.format(2))
        p.close()

        p = Page(pdf, "Figure: time domain, sinc² weight, cumulative removed share")
        p.image(png)
        p.para("(1) One LO phase realization with the per-symbol means for both symbol "
               "lengths.  (2) L(f) of the shipped profile with the removable share "
               "sinc²(fT) for T = 3.2 µs and 12.8 µs; shaded = S_φ·sinc².  (3) Cumulative "
               f"removed fraction over 10 kHz – 100 MHz: {100 * pc['tracked_fraction']:.1f} % "
               f"(11ac/n) vs {100 * pa['tracked_fraction']:.1f} % (11ax/be).", size=9.5)
        p.footer(foot.format(3))
        p.close()
    return pdf_path


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", type=Path, default=Path("docs"))
    a = ap.parse_args(argv)
    a.out.mkdir(parents=True, exist_ok=True)
    print("written:", build(a.out))


if __name__ == "__main__":
    main()
