"""TX frequency-dependent IQ imbalance calibration.

Primary method — RX-LO-offset loopback (``calibrate_tx_iq``):
    Transmit a one-sided comb (tones at +f_i), loop back with the RX LO
    offset by df (f_rx = f_tx + df), capture; repeat with the mirrored comb.
    In each capture a TX tone at f lands at f - df, its TX image at
    -f - df, and the RX image of the direct tone at -(f - df) — three
    distinct bins, so the TX image is read uncontaminated.

    The measurement pair at ONE bin (-f_i - df) across the two captures,

        A_img(+comb) = conj(X_i) * G2tx(-f_i) * C(-f_i - df)
        A_dir(-comb) = X'_i     * G1tx(-f_i) * C(-f_i - df)

    shares the same loopback/RX linear response C, which cancels exactly in
    the ratio, giving rho(-f_i) = G2tx(-f_i) / G1tx(-f_i) with no knowledge
    of the RX required.  The mirrored bins give rho(+f_i).  The correction
    FIR realizes W2 = -rho (pre-corrector: image zero requires
    G1(f) W2(f) + G2(f) W1*(-f) = 0, W1 = 1).

Fallback — envelope detector (``calibrate_tx_iq_envdet``): the image beats
against the direct tone at 2f in the square-law detector; first-order
estimate assuming the common baseband response is Hermitian, iterated.
RX-independent but approximate; the primary method is exact in the model.
"""
from __future__ import annotations

import numpy as np

from ..chain.loopback import EnvelopeDetector, LoopbackPath, run_loopback
from ..chain.rx import RxChain
from ..chain.tx import TxChain
from ..metrics.irr import comb_irr_db
from ..waveform.stimuli import bin_value, grid_freq, iq_cal_comb, single_tone
from .base import CalResult
from .wl_fir import design_w2_fir


def _capture_pair(tx: TxChain, rx: RxChain, path: LoopbackPath,
                  n: int, n_tones: int, amp: float, seed: int):
    """One-sided comb captures for both comb signs."""
    caps, combs = {}, {}
    bw = tx.params.bandwidth_hz
    for sign in (+1, -1):
        x, freqs = iq_cal_comb(bw, tx.fs, n, n_tones=n_tones,
                               amp_total=amp, seed=seed, sign=sign)
        caps[sign] = run_loopback(tx, rx, x, path)
        combs[sign] = (x, freqs)
    return caps, combs


def measure_tx_rho(tx: TxChain, rx: RxChain, path: LoopbackPath,
                   n: int = 1 << 15, n_tones: int = 12, amp: float = 0.04,
                   seed: int = 3) -> tuple[np.ndarray, np.ndarray]:
    """Measured rho(f) = G2tx(f)/G1tx(f) on the +/- comb frequencies."""
    df = path.rx_lo_offset_hz
    if df == 0.0:
        raise ValueError("TX IQ cal needs a nonzero RX-LO offset")
    caps, combs = _capture_pair(tx, rx, path, n, n_tones, amp, seed)
    fs = tx.fs

    rho_f, rho_v = [], []
    xp, fp = combs[+1]
    xm, fm = combs[-1]
    for i, f in enumerate(fp):
        x_i = bin_value(xp, f, fs)                       # known tone phasor
        xm_i = bin_value(xm, -f, fs)
        # rho(-f): TX image of +comb and direct of -comb, same bin -f - df
        a_img = bin_value(caps[+1], -f - df, fs) / np.conj(x_i)
        a_dir = bin_value(caps[-1], -f - df, fs) / xm_i
        rho_f.append(-f)
        rho_v.append(a_img / a_dir)
        # rho(+f): TX image of -comb and direct of +comb, same bin +f - df
        a_img2 = bin_value(caps[-1], f - df, fs) / np.conj(xm_i)
        a_dir2 = bin_value(caps[+1], f - df, fs) / x_i
        rho_f.append(+f)
        rho_v.append(a_img2 / a_dir2)
    return np.asarray(rho_f), np.asarray(rho_v)


def measure_tx_irr(tx: TxChain, n: int = 1 << 14, n_tones: int = 8,
                   seed: int = 5) -> tuple[np.ndarray, np.ndarray]:
    """Direct PA-output IRR measurement (model-only verification probe)."""
    bw = tx.params.bandwidth_hz
    # low drive: PA IM3 products of a one-sided comb land on image bins and
    # would masquerade as IQ image (f_i + f_j - f_k < 0 terms)
    x, freqs = iq_cal_comb(bw, tx.fs, n, n_tones=n_tones, amp_total=0.03,
                           seed=seed, sign=+1)
    y = tx(x)
    return freqs, comb_irr_db(y, freqs, tx.fs)


def calibrate_tx_iq(tx: TxChain, rx: RxChain, path: LoopbackPath | None = None,
                    n: int = 1 << 15, n_tones: int = 12, n_taps: int = 31,
                    n_iter: int = 2, seed: int = 3) -> CalResult:
    if path is None:
        path = LoopbackPath(atten_db=40.0, delay_ns=6.0, rx_lo_offset_hz=5.1e6)
    # snap the LO offset to the capture FFT grid: leakage-free bin readout
    path.rx_lo_offset_hz = grid_freq(path.rx_lo_offset_hz, tx.fs, n)
    f_chk, irr_before = measure_tx_irr(tx)
    trace = [float(np.min(irr_before))]
    bw = tx.params.bandwidth_hz

    rho_raw_f = rho_raw_v = None
    for it in range(n_iter):
        rho_f, rho_v = measure_tx_rho(tx, rx, path, n=n, n_tones=n_tones,
                                      seed=seed + it)
        if rho_raw_f is None:
            rho_raw_f, rho_raw_v = rho_f, rho_v  # pre-correction imbalance
        w2_new = design_w2_fir(rho_f, rho_v, tx.fs, n_taps=n_taps,
                               band_hz=0.55 * bw)
        if tx.w2 is None:
            tx.w2 = w2_new
        else:
            # first-order composition: w2_total ~= w2_old + w2_new
            m = max(tx.w2.size, w2_new.size)
            pad = lambda a: np.pad(a, ((m - a.size) // 2,
                                       (m - a.size + 1) // 2))
            tx.w2 = pad(tx.w2) + pad(w2_new)
        _, irr_now = measure_tx_irr(tx)
        trace.append(float(np.min(irr_now)))

    f_chk, irr_after = measure_tx_irr(tx)
    return CalResult(
        name="tx_iq",
        estimated={"rho_f_hz": rho_raw_f, "rho": rho_raw_v},
        corrections={"w2_taps": tx.w2},
        trace=trace,
        metrics_before={"irr_min_db": float(np.min(irr_before)),
                        "irr_db": irr_before},
        metrics_after={"irr_min_db": float(np.min(irr_after)),
                       "irr_db": irr_after},
        passed=float(np.min(irr_after)) > 50.0,
        cost={"captures": 2 * n_iter, "samples": 2 * n_iter * n},
    )


def calibrate_tx_iq_envdet(tx: TxChain, det: EnvelopeDetector | None = None,
                           n: int = 1 << 14, n_tones: int = 10,
                           n_taps: int = 31, n_iter: int = 3,
                           seed: int = 4) -> CalResult:
    """Envelope-detector fallback (RX-independent, first-order, iterated).

    For a tone at f the detector bin at 2f holds D * conj(I) with
    D = G1(f) X and I = G2(-f) conj(X); assuming the common response is
    Hermitian (|G1(f)| ~ |G1(-f)|, common phase cancels to first order),
    rho(-f) ~= conj(bin(2f) / X^2) normalized by the direct power.
    """
    bw = tx.params.bandwidth_hz
    if det is None:
        # wideband detector: the 2f beats reach 2 * 0.44 * bw
        det = EnvelopeDetector(lpf_bw_hz=1.2 * bw, enabled_adc=False)
    f_chk, irr_before = measure_tx_irr(tx)
    trace = [float(np.min(irr_before))]
    fs = tx.fs

    f_lo, f_hi = 0.05 * bw / 2, 0.44 * bw  # keep 2f inside Nyquist
    # snap to the FFT grid so the tone AND its 2f beat land on exact bins
    cal_freqs = np.array([grid_freq(f, fs, n)
                          for f in np.linspace(f_lo, f_hi, n_tones)])

    for it in range(n_iter):
        rho_f, rho_v = [], []
        for f in cal_freqs:
            for sgn in (+1, -1):
                x = single_tone(sgn * f, fs, n, amp=0.25)
                y = tx(x)
                v = det.measure(y, fs).astype(complex)
                x_ph = bin_value(x, sgn * f, fs)
                # compensate the known detector LPF response at the beat freq
                beat = bin_value(v, 2 * sgn * f, fs) / det.response(2 * sgn * f, fs)
                p_dir = np.mean(np.abs(y) ** 2)  # ~ |D|^2 (image negligible)
                rho = np.conj(beat / (x_ph ** 2)) * (abs(x_ph) ** 2 / p_dir)
                rho_f.append(-sgn * f)
                rho_v.append(rho)
        w2_new = design_w2_fir(np.asarray(rho_f), np.asarray(rho_v), fs,
                               n_taps=n_taps, band_hz=0.55 * bw)
        if tx.w2 is None:
            tx.w2 = w2_new
        else:
            m = max(tx.w2.size, w2_new.size)
            pad = lambda a: np.pad(a, ((m - a.size) // 2,
                                       (m - a.size + 1) // 2))
            tx.w2 = pad(tx.w2) + pad(w2_new)
        _, irr_now = measure_tx_irr(tx)
        trace.append(float(np.min(irr_now)))

    _, irr_after = measure_tx_irr(tx)
    return CalResult(
        name="tx_iq_envdet",
        estimated={},
        corrections={"w2_taps": tx.w2},
        trace=trace,
        metrics_before={"irr_min_db": float(np.min(irr_before))},
        metrics_after={"irr_min_db": float(np.min(irr_after))},
        passed=float(np.min(irr_after)) > 45.0,
    )
