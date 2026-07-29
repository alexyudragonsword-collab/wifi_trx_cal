"""RX frequency-dependent IQ imbalance calibration.

Primary method — tone sweep through the calibrated TX (``calibrate_rx_iq``):
    With TX IQ already corrected (sequencing!), loop back a one-sided comb
    with NO LO offset.  At the RX digital output a source tone at f gives

        Y(+f) = G1rx(f)  * Z(f)
        Y(-f) = G2rx(-f) * conj(Z(f))

    (Z = tone at the RX input; any TX/loopback linear response and delay is
    inside Z and cancels in the ratio).  The post-corrector zeroing the
    image needs W2(f) = -G2(f)/G1*(-f), so per measured pair

        W2(-f) = - Y(-f) / conj(Y(+f)).

Secondary — preamble/frame-based (``estimate_rx_iq_from_frame``): with a
fully known OFDM cal frame, least-squares solve per mirror-tone pair
    Y_s(f) = H(f) S_s(f) + G(f) conj(S_s(-f))
over the symbols, then W2(f) = -G(f)/conj(H(-f)).  Works on modem-style
waveforms with no dedicated tone generator.
"""
from __future__ import annotations

import numpy as np

from ..chain.loopback import LoopbackPath, run_loopback
from ..chain.rx import RxChain
from ..chain.tx import TxChain
from ..metrics.irr import comb_irr_db
from ..waveform.ofdm import OFDMWaveform, demodulate_ofdm
from ..waveform.stimuli import bin_value, iq_cal_comb
from .base import CalResult
from .wl_fir import design_w2_fir


def measure_rx_w2(tx: TxChain, rx: RxChain, path: LoopbackPath,
                  n: int = 1 << 15, n_tones: int = 12, amp: float = 0.4,
                  seed: int = 11) -> tuple[np.ndarray, np.ndarray]:
    """Measured -W2 requirement, i.e. G2rx(-f)/G1rx*(f), on +/- comb freqs."""
    if path.rx_lo_offset_hz != 0.0:
        raise ValueError("RX IQ cal runs with shared LO (no offset)")
    fs = rx.fs
    bw = rx.params.bandwidth_hz
    w2_f, w2_v = [], []
    for sign in (+1, -1):
        x, freqs = iq_cal_comb(bw, fs, n, n_tones=n_tones, amp_total=amp,
                               seed=seed, sign=sign)
        cap = run_loopback(tx, rx, x, path)
        for f in freqs:
            y_dir = bin_value(cap, f, fs)
            y_img = bin_value(cap, -f, fs)
            w2_f.append(-f)
            w2_v.append(y_img / np.conj(y_dir))   # = G2rx(-f)/G1rx*(f)
    return np.asarray(w2_f), np.asarray(w2_v)


def measure_rx_irr(rx: RxChain, n: int = 1 << 14, n_tones: int = 8,
                   seed: int = 13) -> tuple[np.ndarray, np.ndarray]:
    """Direct RX IRR probe: inject a comb at the RX input (model-only)."""
    bw = rx.params.bandwidth_hz
    x, freqs = iq_cal_comb(bw, rx.fs, n, n_tones=n_tones, amp_total=0.01,
                           seed=seed, sign=+1)
    noise_state = rx.noise_enabled
    rx.noise_enabled = False
    cap = rx(x, rng=np.random.default_rng(0))
    rx.noise_enabled = noise_state
    return freqs, comb_irr_db(cap, freqs, rx.fs)


def calibrate_rx_iq(tx: TxChain, rx: RxChain, path: LoopbackPath | None = None,
                    n: int = 1 << 15, n_tones: int = 12, n_taps: int = 31,
                    n_iter: int = 2, seed: int = 11) -> CalResult:
    if path is None:
        path = LoopbackPath(atten_db=40.0, delay_ns=6.0, rx_lo_offset_hz=0.0)
    _, irr_before = measure_rx_irr(rx)
    trace = [float(np.min(irr_before))]
    bw = rx.params.bandwidth_hz

    for it in range(n_iter):
        w2_f, w2_v = measure_rx_w2(tx, rx, path, n=n, n_tones=n_tones,
                                   seed=seed + it)
        w2_new = design_w2_fir(w2_f, w2_v, rx.fs, n_taps=n_taps,
                               band_hz=0.55 * bw)
        if rx.w2 is None:
            rx.w2 = w2_new
        else:
            m = max(rx.w2.size, w2_new.size)
            pad = lambda a: np.pad(a, ((m - a.size) // 2,
                                       (m - a.size + 1) // 2))
            rx.w2 = pad(rx.w2) + pad(w2_new)
        _, irr_now = measure_rx_irr(rx)
        trace.append(float(np.min(irr_now)))

    _, irr_after = measure_rx_irr(rx)
    return CalResult(
        name="rx_iq",
        estimated={"w2_f_hz": w2_f, "w2_req": w2_v},
        corrections={"w2_taps": rx.w2},
        trace=trace,
        metrics_before={"irr_min_db": float(np.min(irr_before)),
                        "irr_db": irr_before},
        metrics_after={"irr_min_db": float(np.min(irr_after)),
                       "irr_db": irr_after},
        passed=float(np.min(irr_after)) > 50.0,
    )


def estimate_rx_iq_from_frame(cap: np.ndarray, ref: OFDMWaveform
                              ) -> tuple[np.ndarray, np.ndarray]:
    """Per-mirror-pair LS estimate of (H, G) from a fully known OFDM frame.

    ``cap`` must be time-aligned with the reference frame.  Returns
    (freqs_hz, w2_required) suitable for design_w2_fir.
    """
    cfg = ref.config
    tones = cfg.active_tone_indices()
    scs = cfg.sample_rate_hz / (cfg.fft_size * cfg.oversampling)  # = bw/fft_size
    y_sym = demodulate_ofdm(cap, ref)         # (n_sym, n_active)
    s_sym = ref.tx_symbols
    pos = {int(t): i for i, t in enumerate(tones)}

    freqs, w2_req = [], []
    h_map: dict[int, complex] = {}
    g_map: dict[int, complex] = {}
    for t in tones:
        if -int(t) not in pos:
            continue
        i, j = pos[int(t)], pos[-int(t)]
        a = s_sym[:, i]
        b = np.conj(s_sym[:, j])
        y = y_sym[:, i]
        m = np.stack([a, b], axis=1)
        sol, *_ = np.linalg.lstsq(m, y, rcond=None)
        h_map[int(t)] = complex(sol[0])
        g_map[int(t)] = complex(sol[1])
    for t, g in g_map.items():
        h_mirror = h_map.get(-t)
        if h_mirror is None or abs(h_mirror) < 1e-12:
            continue
        freqs.append(t * scs)
        w2_req.append(g / np.conj(h_mirror))
    return np.asarray(freqs), np.asarray(w2_req)
