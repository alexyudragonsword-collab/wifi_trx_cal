"""Figure adapters: RunContext -> matplotlib Figures, plus the generated
calibration-dependency SVG.

Thin by design — real plotting lives in wifitrx.report.figures /
wifitrx.plotting; this file only wires RunContext products into them and
adds the few tutorial-specific views.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
from matplotlib.figure import Figure

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))


def _fig(w=6.4, h=3.6):
    fig = Figure(figsize=(w, h), layout="constrained")
    ax = fig.add_subplot(111)
    ax.grid(True, alpha=0.3)
    return fig, ax


# ------------------------------------------------------------ chapter 1/3
def impairment_psd(ctx):
    from wifitrx.metrics import psd
    st = ctx.impairment_study
    fig, ax = _fig(8.2, 4.6)
    for name, sig in st["signals"].items():
        f, p = psd(sig, st["fs"])
        ax.plot(f / 1e6, p, lw=0.9, label=name)
    ax.set_xlabel("Frequency [MHz]")
    ax.set_ylabel("PSD [dB]")
    ax.set_ylim(-90, 5)
    ax.legend(fontsize=7, ncols=2)
    return fig


def impairment_evm(ctx):
    st = ctx.impairment_study
    rows = st["rows"]
    fig, ax = _fig(7.0, 3.4)
    names = [r["case"] for r in rows]
    evms = [r["evm_db"] for r in rows]
    ax.barh(names, evms, color="tab:blue")
    ax.invert_yaxis()
    ax.set_xlabel("Loopback EVM [dB] (per-tone EQ)")
    return fig


def irr_injected(ctx):
    from wifitrx.impairments.iq_imbalance import FreqDepIQImbalance
    iq = FreqDepIQImbalance(gain_db=0.3, phase_deg=2.0, gd_mismatch_ps=200.0,
                            rail_ripple_db=0.3, rail_gd_ripple_ns=0.1)
    fs = 320e6
    f = np.linspace(-120e6, 120e6, 481)
    fig, ax = _fig()
    ax.plot(f / 1e6, iq.irr_db(f, fs), lw=1.2)
    ax.set_xlabel("Baseband frequency [MHz]")
    ax.set_ylabel("IRR [dB] (analytic)")
    return fig


def pn_profile(ctx):
    from wifitrx.impairments.phase_noise import (DEFAULT_WIFI7_LO_PROFILE,
                                                 ipn_dbc, ldbc_from_sphi)
    f = np.logspace(4, 8, 400)
    s = DEFAULT_WIFI7_LO_PROFILE.psd(f)
    fig, ax = _fig()
    ax.semilogx(f, ldbc_from_sphi(s), lw=1.2)
    ipn = ipn_dbc(f, s, 1e4, 1e8)
    ax.set_xlabel("Offset frequency [Hz]")
    ax.set_ylabel("L(f) [dBc/Hz]")
    ax.set_title(f"Default WiFi 7 synthesizer profile, IPN = {ipn:.1f} dBc",
                 fontsize=10)
    return fig


def pa_amam(ctx):
    from wifitrx.pa.saleh import SalehPA
    from wifitrx.pa.scaled import ScaledPA
    pa = ScaledPA(SalehPA(), gain_db=26.0, psat_dbm=28.0, pae_max=0.35)
    x = np.linspace(1e-4, 0.5, 400).astype(complex)
    y = pa(x)
    fig = Figure(figsize=(8.0, 3.4), layout="constrained")
    ax1, ax2 = fig.subplots(1, 2)
    pin = 20 * np.log10(np.abs(x))
    ax1.plot(pin + 10, 10 * np.log10(np.abs(y) ** 2), lw=1.2)
    ax1.set_xlabel("Input power [dBm]")
    ax1.set_ylabel("Output power [dBm]")
    ax1.grid(True, alpha=0.3)
    ax2.plot(pin + 10, np.unwrap(np.angle(y / x)) * 180 / np.pi, lw=1.2)
    ax2.set_xlabel("Input power [dBm]")
    ax2.set_ylabel("AM/PM [deg]")
    ax2.grid(True, alpha=0.3)
    return fig


# ------------------------------------------------------------ per-step
def _res(ctx, name):
    return ctx.full_cal["by_name"][name]


def lpf_code_sweep(ctx):
    from wifitrx.report.figures import fig_code_sweep
    r = _res(ctx, "tx_lpf_corner")
    return fig_code_sweep(r.trace, r.estimated["best_code"],
                          "TX LPF corner: RC code sweep")


def lo_leak_convergence(ctx):
    from wifitrx.report.figures import fig_convergence
    r = _res(ctx, "tx_lo_leak_loopback")
    return fig_convergence(r.trace, "TX LO leak (loopback method)",
                           "LO leakage [dBc]")


def iip2_trace(ctx):
    r = _res(ctx, "rx_iip2")
    codes = [c for c, _ in r.trace]
    vals = [v for _, v in r.trace]
    fig, ax = _fig()
    ax.plot(codes, vals, "o-")
    ax.set_xlabel("IM2 trim code (search order)")
    ax.set_ylabel("Effective IIP2 [dBm]")
    return fig


def tx_iq_irr(ctx):
    from wifitrx.report.figures import fig_irr_before_after
    r = _res(ctx, "tx_iq")
    f = np.sort(np.abs(np.asarray(r.estimated["rho_f_hz"])))
    n = len(r.metrics_before["irr_db"])
    return fig_irr_before_after(f[-n:], r.metrics_before["irr_db"],
                                r.metrics_after["irr_db"],
                                "TX IQ: IRR before/after")


def rx_iq_irr(ctx):
    from wifitrx.report.figures import fig_irr_before_after
    r = _res(ctx, "rx_iq")
    f = np.sort(np.abs(np.asarray(r.estimated["w2_f_hz"])))
    n = len(r.metrics_before["irr_db"])
    return fig_irr_before_after(f[-n:], r.metrics_before["irr_db"],
                                r.metrics_after["irr_db"],
                                "RX IQ: IRR before/after")


def tx_power_table(ctx):
    from wifitrx.report.figures import fig_power_table
    return fig_power_table(_res(ctx, "tx_power").trace,
                           "TX power: gain code vs measured output")


def dpd_convergence(ctx):
    from wifitrx.report.figures import fig_convergence
    return fig_convergence(_res(ctx, "dpd").trace,
                           "DPD: worst ACLR per ILA iteration",
                           "ACLR [dBc]")


def agc_sweep(ctx):
    from wifitrx.report.figures import fig_agc_sweep
    r = _res(ctx, "agc_sweep")
    return fig_agc_sweep(r.trace, r.estimated["target_adc_dbm"], "AGC sweep")


def constellation_compare(ctx):
    from wifitrx.report.figures import fig_constellation_compare
    fc = ctx.full_cal
    return fig_constellation_compare(fc["snap_before"], fc["snap_after"])


def psd_compare(ctx):
    from wifitrx.report.figures import fig_psd_compare
    fc = ctx.full_cal
    return fig_psd_compare(fc["snap_before"], fc["snap_after"])


# ------------------------------------------------------------ chapter 6
def temp_hold(ctx):
    rows = ctx.temp_study["rows"]
    t = [r["temp_c"] for r in rows]
    fig = Figure(figsize=(8.0, 3.4), layout="constrained")
    ax1, ax2 = fig.subplots(1, 2)
    ax1.plot(t, [r["lo_leak_dbc"] for r in rows], "o-", label="measured")
    lim = ctx.temp_study["expiry"]["criteria"]["lo_leak_dbc_max"]
    ax1.axhline(lim, color="tab:red", ls="--", label="spec")
    ax1.set_xlabel("Temperature [degC]")
    ax1.set_ylabel("LO leak [dBc]")
    ax1.legend(fontsize=8)
    ax1.grid(True, alpha=0.3)
    ax2.plot(t, [r["irr_min_db"] for r in rows], "s-", color="tab:orange",
             label="measured")
    lim2 = ctx.temp_study["expiry"]["criteria"]["irr_min_db_min"]
    ax2.axhline(lim2, color="tab:red", ls="--", label="spec")
    ax2.set_xlabel("Temperature [degC]")
    ax2.set_ylabel("min IRR [dB]")
    ax2.legend(fontsize=8)
    ax2.grid(True, alpha=0.3)
    return fig


def drift_tracking(ctx):
    tr = ctx.drift_tracking["trace"]
    states = [t["state"] for t in tr]
    fig, ax = _fig()
    ax.plot(states, [t["evm_track_db"] for t in tr], "o-",
            label="tracking DPD (RLS)")
    if tr and tr[0]["evm_frozen_db"] is not None:
        ax.plot(states, [t["evm_frozen_db"] for t in tr], "s--",
                label="frozen DPD")
    oracle = ctx.drift_tracking["metrics"]["evm_oracle_final_db"]
    ax.axhline(oracle, color="tab:green", ls=":",
               label="oracle (retrained at final state)")
    ax.set_xlabel("Thermal drift state")
    ax.set_ylabel("TX EVM [dB]")
    ax.legend(fontsize=8)
    return fig


def mc_hist(ctx):
    evms = ctx.mc_yield["evms"]
    fig, ax = _fig(5.6, 3.2)
    ax.hist(evms, bins=8, color="tab:blue", alpha=0.8)
    ax.set_xlabel("Post-cal loopback EVM [dB]")
    ax.set_ylabel("Dies")
    return fig


# ---------------------------------------------------- dependency graph
def depgraph_svg(ctx) -> str:
    """Layered SVG of cal/deps.py STEP_REQUIRES.

    Layout rules that keep it readable: Kahn depth -> column (a column
    header names the stage), the dependency-free steps get their own
    band at the bottom so they do not pad the constrained columns,
    edges are routed orthogonally through per-edge gutters (no crossing
    curves) and carry a numbered badge that indexes the reason table in
    the prose.  Reasons stay as <title> tooltips too.
    """
    from wifitrx.cal.deps import STEP_REQUIRES, planned_steps
    from wifitrx.cal.sequence import PROFILES
    order = planned_steps(PROFILES["factory"], with_iip2=True, with_dpd=True)

    # ---- levels: only steps that participate in an ordering constraint
    dependents = {r for n in order for r in STEP_REQUIRES.get(n, {})}
    constrained = [n for n in order
                   if STEP_REQUIRES.get(n) or n in dependents]
    free = [n for n in order if n not in constrained]

    level = {}
    for name in order:
        level[name] = 1 + max(
            (level.get(r, 0) for r in STEP_REQUIRES.get(name, {})), default=0)
    cols: dict[int, list[str]] = {}
    for name in constrained:
        cols.setdefault(level[name], []).append(name)

    BW_, BH, HGAP, VGAP = 158, 32, 130, 20
    TOP = 34                                   # column-header band
    n_col = max(cols)
    rows_max = max(len(v) for v in cols.values())
    pos = {}
    for lv, names in sorted(cols.items()):
        x = 12 + (lv - 1) * (BW_ + HGAP)
        for i, name in enumerate(names):
            pos[name] = (x, TOP + i * (BH + VGAP))
    band_y = TOP + rows_max * (BH + VGAP) + 30      # free-steps band
    per_row = 4
    for i, name in enumerate(free):
        pos[name] = (12 + (i % per_row) * (BW_ + 16),
                     band_y + 22 + (i // per_row) * (BH + 10))

    width = max(n_col * (BW_ + HGAP) + 12,
                per_row * (BW_ + 16) + 12)
    height = band_y + 22 + ((len(free) - 1) // per_row + 1) * (BH + 10) + 12

    p = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} '
         f'{height}" style="max-width:100%;height:auto;'
         f'font-family:sans-serif">',
         '<defs><marker id="arr" viewBox="0 0 8 8" refX="7.5" refY="4" '
         'markerWidth="7" markerHeight="7" orient="auto">'
         '<path d="M0 0 L8 4 L0 8 z" fill="#445"/></marker></defs>']

    # ---- column headers + the free-step band
    for lv in sorted(cols):
        x = 12 + (lv - 1) * (BW_ + HGAP)
        p.append(f'<text x="{x + BW_ / 2}" y="20" text-anchor="middle" '
                 f'font-size="11" fill="#667">stage {lv}</text>')
        if lv > 1:                       # dashed separator between stages
            gx = x - HGAP / 2
            p.append(f'<line x1="{gx}" y1="26" x2="{gx}" y2="{band_y - 12}" '
                     f'stroke="#ccd" stroke-dasharray="3 4"/>')
    p.append(f'<line x1="12" y1="{band_y}" x2="{width - 12}" y2="{band_y}" '
             f'stroke="#ccd" stroke-dasharray="3 4"/>')
    p.append(f'<text x="12" y="{band_y + 16}" font-size="11" fill="#667">'
             f'no ordering constraint (any order)</text>')

    # ---- orthogonal edges, one gutter lane each, numbered
    lanes: dict[int, int] = {}
    idx = 0
    for name in order:
        for req, reason in STEP_REQUIRES.get(name, {}).items():
            if req not in pos or name not in pos:
                continue
            idx += 1
            x1, y1 = pos[req]
            x2, y2 = pos[name]
            gcol = level[name]
            lanes[gcol] = lanes.get(gcol, 0) + 1
            gx = x2 - HGAP + 30 + (lanes[gcol] - 1) * 16     # lane offset
            sx, sy = x1 + BW_, y1 + BH / 2
            ex, ey = x2, y2 + BH / 2
            straight = abs(sy - ey) <= 1
            d = (f"M{sx} {sy} H{ex}" if straight
                 else f"M{sx} {sy} H{gx} V{ey} H{ex}")
            # badge on the clear part of the run: mid-gutter for a
            # dog-leg, mid-span for a straight edge
            # (a straight edge's midpoint would land on the other edges'
            # gutter lanes, so sit it right after the source box)
            bx, by = (sx + 16, sy) if straight else (gx, (sy + ey) / 2)
            p.append(f'<path d="{d}" fill="none" stroke="#7a8598" '
                     f'stroke-width="1.4" marker-end="url(#arr)">'
                     f"<title>{req} → {name}: {reason}</title></path>")
            p.append(f'<circle cx="{bx}" cy="{by}" r="7.5" '
                     f'fill="#fff" stroke="#7a8598" stroke-width="1"/>'
                     f'<text x="{bx}" y="{by + 3.5}" '
                     f'text-anchor="middle" font-size="9" fill="#445">'
                     f'{idx}</text>')

    # ---- nodes (execution index prefixed so the table cross-references)
    rank = {n: i for i, n in enumerate(order, 1)}
    for name, (x, y) in pos.items():
        dashed = ' stroke-dasharray="4 3"' if name in free else ""
        p.append(
            f'<rect x="{x}" y="{y}" width="{BW_}" height="{BH}" rx="6" '
            f'fill="#eef3f8" stroke="#0b5fa5"{dashed}/>'
            f'<text x="{x + BW_ / 2}" y="{y + BH / 2 + 4}" '
            f'text-anchor="middle" font-size="11">'
            f'{rank[name]}. {name}</text>')
    p.append("</svg>")
    return "".join(p)
