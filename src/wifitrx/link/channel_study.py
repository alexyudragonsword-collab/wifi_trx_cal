"""What a dispersive channel costs, and what it does to a receiver
setting that was chosen on a flat one.

Isolation method: the frame meets the channel and thermal noise and
nothing else — no front end, no IQ imbalance, no phase noise — so every
reading here is the channel's own.  Both EVM views of
``cal.sequence.score_views`` are read on the same capture:

* ``evm_db``, the isolation view, equalises per tone against the ideal
  reference, so it knows the channel exactly and what is left is the
  noise *enhanced* by 1/|H| on the faded tones.
* ``evm_modem_db`` estimates the channel from the LTF pair and smooths
  it over ``ce_smooth_tones`` adjacent tones.

**The isolation view is not a floor here, and the first draft of this
module said it was.**  Measured at 40 MHz / 30 dB in-band SNR, the modem
form reads *better* than it at moderate delay spreads (-27.1 against
-24.9 dB at 15 ns, -26.4 against -22.2 at 50 ns).  That is not an error:
knowing the channel exactly and dividing by it is zero-forcing, and
zero-forcing is not the best thing to do in a deep fade.  Smoothing the
estimate biases |H| upward exactly where the channel is nulled, which
limits the noise enhancement the way a regularised equaliser would.  The
isolation view is a floor on a *flat* channel only; on a fading one it
is one particular estimator, and a plainly suboptimal one.

The second one is the point of this module.  The 9-tone default was
decided in 0.7.18 on a **flat** chain, where smoothing is free variance
reduction: the thing it removes (the residual IQ image and PA
distortion frozen into the raw LTF estimate) flips sign tone to tone
while the channel does not.  On a dispersive channel the channel does
too, over a coherence bandwidth 1/(2 pi tau_rms), and the same smoothing
starts biasing the estimate.  So the useful width is a bias-variance
trade-off that moves with the delay spread, and a default picked in
conducted mode does not automatically survive the air.
"""
from __future__ import annotations

from dataclasses import replace

import numpy as np

from ..cal.sequence import score_views
from ..waveform.ofdm import OFDMConfig
from ..waveform.pilots import generate_ofdm_with_pilots, pilot_sequence
from ..waveform.preamble import build_frame
from .channel import TDLChannel, coherence_bandwidth_hz

#: smoothing widths worth comparing; 9 is the shipped default
SMOOTH_WIDTHS = (1, 3, 5, 9, 17, 33)


def study_frame(cfg: OFDMConfig):
    """[GI2 | LTF | LTF | data with pilots], one padding symbol, exactly
    the calibration's scoring frame; returns (frame, cols, pilots)."""
    cfg_pad = replace(cfg, n_symbols=cfg.n_symbols + 1)
    wf, cols = generate_ofdm_with_pilots(cfg_pad)
    frame = build_frame(cfg_pad, data=wf)
    return frame, cols, pilot_sequence(cfg_pad.n_symbols, cols.size)


def summarize_db(values_db) -> dict:
    """The ensemble statistic for a fading sweep: the **median** across
    realisations, plus the 90th percentile as the labelled tail.

    The first draft of this module averaged in the power domain, on the
    argument that the deep-fade realisations dominate and must not be
    averaged away.  They do dominate — and that is exactly why the mean
    is the wrong statistic here.  Zero-forcing through a Rayleigh tone
    costs 1/|H|^2, and for |H|^2 exponential the expectation of 1/|H|^2
    **diverges**, so the power-domain mean of these EVMs has no limit to
    converge to: it tracks whichever realisation happened to contain the
    deepest null.

    Measured, rather than argued: at 50 ns and 30 dB, three independent
    seed groups of 128 realisations each give power-mean modem EVMs of
    -18.3, -11.2 and -19.4 dB, a spread of 8.2 dB that does **not**
    shrink when going from 8 realisations to 128.  The medians of the
    same nine groups sit within 0.5 dB, and are already stable at 32.
    So the median is reported and the mean is not offered at all."""
    v = np.asarray(values_db, dtype=float)
    # the tail is taken by sorting rather than np.percentile: the Android
    # call-surface allowlist is a set of names someone verified against
    # numpy 1.19.5, and percentile is not one of them.  Nothing is lost —
    # a labelled tail does not need interpolation between order
    # statistics — and the allowlist keeps meaning "verified".
    order = np.sort(v)
    idx = min(int(np.ceil(0.9 * order.size)) - 1, order.size - 1)
    return {"median_db": float(np.median(v)),
            "p90_db": float(order[max(idx, 0)]),
            "n": int(v.size)}


def median_db(values_db) -> float:
    return summarize_db(values_db)["median_db"]


def cp_duration_s(cfg: OFDMConfig) -> float:
    """The guard interval in seconds: the delay budget the channel has
    before its tail lands in the next symbol."""
    return cfg.cp_len / cfg.bandwidth_hz


def packet_readings(cfg: OFDMConfig, chan: TDLChannel, snr_db: float,
                    ce_smooth_tones: int = 9, seed: int = 0,
                    frame=None, cols=None, pilots=None) -> dict:
    """One packet through ``chan`` plus AWGN at ``snr_db``, scored in
    both views.  Also returns the realisation's tone-by-tone |H| so the
    fades can be plotted against the EVM they cause."""
    if frame is None:
        frame, cols, pilots = study_frame(cfg)
    fs = cfg.sample_rate_hz
    rng = np.random.default_rng(seed)
    y, taps = chan.apply(frame.x, fs, rng)
    p_sig = float(np.mean(np.abs(frame.x) ** 2))
    # snr_db is the IN-BAND, per-tone SNR, so a flat channel reads an EVM
    # of about -snr_db.  Noise lands in every one of the os_nfft bins
    # while the signal sits in n_active of them, so a time-domain SNR
    # would read 10 log10(os_nfft / n_active) better here -- 6.26 dB at
    # 4x oversampling and 484 of 512 tones, which is a large enough gap
    # to make the parameter mean the wrong thing to a reader.
    bins = cfg.fft_size * cfg.oversampling / cfg.n_active
    sigma = np.sqrt(p_sig * bins / (10.0 ** (snr_db / 10.0)) / 2.0)
    y = y + sigma * (rng.standard_normal(y.size) + 1j * rng.standard_normal(y.size))
    views = score_views(y, frame, cols, pilots, cfg.n_symbols, ce_smooth_tones)
    tone_hz = cfg.active_tone_indices() * cfg.subcarrier_spacing_hz
    h = chan.frequency_response(taps, tone_hz, fs)
    return {"evm_db": float(views["evm_db"]),
            "evm_modem_db": float(views["evm_modem_db"]),
            "tone_hz": tone_hz, "h_abs_db": 20.0 * np.log10(np.abs(h) + 1e-18),
            "rms_delay_s": chan.realized_rms_delay_s(fs),
            "n_taps": int(taps.size)}


def smoothing_sweep(cfg: OFDMConfig, rms_delays_ns, snr_db: float,
                    widths=SMOOTH_WIDTHS, n_real: int = 32,
                    seed: int = 0) -> dict:
    """Modem-form EVM against the channel-estimate smoothing width, one
    curve per delay spread, averaged over ``n_real`` realisations.  The
    isolation view is carried alongside for reference; it does not depend
    on the width, and per the module docstring it is *not* a floor on a
    fading channel."""
    frame, cols, pilots = study_frame(cfg)
    widths = list(widths)
    modem = np.zeros((len(rms_delays_ns), len(widths)))
    iso = np.zeros(len(rms_delays_ns))
    best = []
    for i, rms in enumerate(rms_delays_ns):
        chan = TDLChannel(rms_delay_ns=float(rms))
        iso_r = []
        for j, w in enumerate(widths):
            vals = [packet_readings(cfg, chan, snr_db, w, seed + r,
                                    frame, cols, pilots)
                    for r in range(n_real)]
            modem[i, j] = median_db([v["evm_modem_db"] for v in vals])
            if j == 0:
                iso_r = [v["evm_db"] for v in vals]
        iso[i] = median_db(iso_r)
        best.append(widths[int(np.argmin(modem[i]))])
    return {"rms_delays_ns": np.asarray(rms_delays_ns, dtype=float),
            "widths": np.asarray(widths), "modem_db": modem,
            "iso_db": iso, "best_width": np.asarray(best),
            "coherence_bw_hz": np.array([coherence_bandwidth_hz(r * 1e-9)
                                         for r in rms_delays_ns])}


def delay_sweep(cfg: OFDMConfig, rms_delays_ns, snr_db: float,
                ce_smooth_tones: int = 9, n_real: int = 32,
                seed: int = 0) -> dict:
    """Both views against the delay spread at a fixed smoothing width.
    ``cp_s`` is the guard interval: past it the channel's tail leaves the
    cyclic prefix and no per-tone equaliser can undo the result."""
    frame, cols, pilots = study_frame(cfg)
    iso, modem, realized = [], [], []
    for rms in rms_delays_ns:
        chan = TDLChannel(rms_delay_ns=float(rms))
        vals = [packet_readings(cfg, chan, snr_db, ce_smooth_tones, seed + r,
                                frame, cols, pilots) for r in range(n_real)]
        iso.append(median_db([v["evm_db"] for v in vals]))
        modem.append(median_db([v["evm_modem_db"] for v in vals]))
        realized.append(vals[0]["rms_delay_s"])
    return {"rms_delays_ns": np.asarray(rms_delays_ns, dtype=float),
            "iso_db": np.asarray(iso), "modem_db": np.asarray(modem),
            "realized_rms_s": np.asarray(realized),
            "cp_s": cp_duration_s(cfg),
            "ce_smooth_tones": int(ce_smooth_tones)}
