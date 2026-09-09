"""The LO phase-noise / CPE-removal study's physics — the four
measurement configurations, the residual-CFO closed forms and the
realization-averaged readings — as library code.

Lived in app/specs.py (the GUI registry) until 0.7.20, which meant the
PDF-note generator under tools/ imported private functions from the
GUI layer to compute its numbers; the registry keeps only the pages.
Everything here is isolation-method: phase noise is the only
impairment, the channel is exactly unity, and each configuration is a
direct reading rather than a difference of totals.  Measured values
and the mechanisms behind them are recorded on the study page
(``app/specs.py:run_pn_cpe_study``) and in docs/pn_cpe_note_*.pdf.
"""
from __future__ import annotations

import numpy as np

from ..cal.tracking import pilot_cfo_hz
from ..impairments.phase_noise import DEFAULT_WIFI7_LO_PROFILE, LOModel
from ..metrics.cpe import correct_cpe, correct_cpe_pilots
from ..waveform.ofdm import OFDMConfig, demodulate_ofdm
from ..waveform.pilots import generate_ofdm_with_pilots, pilot_sequence
from ..waveform.preamble import apply_cfo, build_frame, channel_estimate, estimate_cfo

__all__ = ["study_config", "four_configs", "cfo_closed_forms", "sweep_point",
           "nominal_readings"]


def study_config(bw_hz: float, std: str = "11ax/be") -> OFDMConfig:
    """OFDM numerology for the phase-noise study: the run bandwidth at the
    selected standard (``"11ax/be"`` or ``"11ac/n"``), with the capture
    held at the same duration across standards (20 symbols of 12.8 us,
    80 of 3.2 us) so every estimator averages over the same time."""
    bw = float(bw_hz)
    if std == "11ac/n":
        if bw > 160e6:
            raise ValueError("802.11ac/n supports at most 160 MHz — "
                             "select the 11ax/be standard for 320 MHz")
        return OFDMConfig(bandwidth_hz=bw, qam_order=1024, n_symbols=80,
                          oversampling=4, subcarrier_spacing_hz=312.5e3,
                          cp_fraction=1 / 4)
    return OFDMConfig(bandwidth_hz=bw, qam_order=1024, n_symbols=20,
                      oversampling=4)


def four_configs(frame, cols, pilots, phi, cfo_hz: float = 0.0) -> np.ndarray:
    """EVM [dB] of the four measurement configurations for one
    phase-noise realization ``phi`` applied to ``frame``.

    1  no tracking at all, true channel (H = 1): CPE + ICI total
    2  genie CPE (all tones vs ideal reference), true channel: ICI floor
    3  LTF CFO acquisition + LTF channel estimate + genie CPE
    4  LTF CFO acquisition + LTF channel estimate + pilot-only CPE: the
       modem form

    Phase noise is the only impairment and the channel is flat, so the
    true channel is exactly unity and configs 1/2 need no equalizer at
    all — no self-fitted gain, hence no degrees-of-freedom correction.
    Data tones are scored in every config; pilot tones are excluded.

    ``cfo_hz`` adds a residual carrier offset on top of the phase noise.
    Configs 1 and 2 never see it estimated: 1 rotates symbol by symbol
    and smears, 2 removes each symbol's rotation and keeps the in-symbol
    ramp as ICI, exactly 1 - sinc^2(cfo T) — a CFO is a phase-noise line
    at offset cfo.  Configs 3 and 4 acquire it from the LTF pair before
    the channel estimate, as any modem does; the pilot CPE then absorbs
    what the acquisition left.  That difference is the tracking's real
    value, which the phase-noise-only reading structurally omits.
    """
    cfg = frame.config
    fs = cfg.sample_rate_hz
    y = frame.x * np.exp(1j * phi)
    if cfo_hz:
        y = apply_cfo(y, cfo_hz, fs)
    tx = frame.data.tx_symbols
    rx = demodulate_ofdm(y[frame.preamble_len:], frame.data)
    data = np.ones(cfg.n_active, dtype=bool)
    data[cols] = False
    ref = tx[:, data]
    p_ref = float((np.abs(ref) ** 2).mean())

    def score(sym):
        return 10.0 * np.log10(float((np.abs(sym[:, data] - ref) ** 2).mean())
                               / p_ref)

    # the modem's acquisition: coarse CFO from the LTF pair, then a fine
    # refinement from the slope of the pilots' common phase across the
    # frame (the tracking loop's CFO branch, cal/tracking.py), then the
    # channel estimate.  The coarse step alone is not enough: under phase
    # noise the LTF pair reads a spurious offset (~25 Hz rms for the
    # 12.8 us LTF, ~180 Hz for the 3.2 us one) and de-rotating the frame
    # by it puts that error back as in-symbol ramp ICI — 0.6 dB on the
    # legacy numerology.  The pilot baseline is the whole frame, two
    # orders of magnitude longer, and takes it out.
    y_acq = apply_cfo(y, -estimate_cfo(y, frame, fs), fs)
    y_acq = apply_cfo(y_acq, -_pilot_cfo_hz(y_acq, frame, cols, pilots), fs)
    h = channel_estimate(y_acq, frame)
    req = demodulate_ofdm(y_acq[frame.preamble_len:], frame.data) / h
    return np.array([score(rx), score(correct_cpe(rx, tx)),
                     score(correct_cpe(req, tx)),
                     score(correct_cpe_pilots(req, cols, pilots))])


def _pilot_cfo_hz(y, frame, cols, pilots) -> float:
    """Residual CFO [Hz] of one frame from the pilots' common phase vs
    symbol time — the tracking loop's own regression (cal/tracking.py)."""
    cfg = frame.config
    syms = demodulate_ofdm(y[frame.preamble_len:], frame.data)
    return pilot_cfo_hz(syms, cols, pilots, cfg, cfg.sample_rate_hz)


def cfo_closed_forms(frame, cfo_hz: float) -> tuple:
    """Error power a residual CFO adds, for the two untracked configs.

    Config 2 removes each symbol's rotation; the in-symbol ramp stays as
    ICI, 1 - sinc^2(cfo T).  Config 1 removes nothing: symbol k is
    rotated by the accumulated phase 2 pi cfo t_k plus the ramp's own
    half-symbol lag, so its error is |sinc(cfo T) e^{j theta_k} - 1|^2
    averaged over the frame's symbols — which walks off towards 2 (the
    "smeared" constellation) as the rotation covers the circle.
    """
    cfg = frame.config
    t_fft = 1.0 / cfg.subcarrier_spacing_hz
    fs = cfg.sample_rate_hz
    sym_len = (cfg.fft_size + cfg.cp_len) * cfg.oversampling
    cp = cfg.cp_len * cfg.oversampling
    starts = frame.preamble_len + cp + sym_len * np.arange(cfg.n_symbols)
    theta = 2 * np.pi * cfo_hz * (starts / fs + t_fft / 2)
    j0 = np.sinc(cfo_hz * t_fft)
    e1 = float(np.mean(np.abs(j0 * np.exp(1j * theta) - 1.0) ** 2))
    e2 = float(1.0 - j0 ** 2)
    return e1, e2


def sweep_point(profile, frame, cols, pilots, n_lo, n_frames, rng,
                    cfo_hz: float = 0.0):
    """Power-average the four readings over ``n_frames`` independent
    phase-noise realizations (``n_lo`` independent LOs summed)."""
    fs = frame.config.sample_rate_hz
    n = frame.x.size
    lo = LOModel(profile=profile)
    acc = np.zeros(4)
    for _ in range(n_frames):
        phi = np.zeros(n)
        for _k in range(n_lo):
            phi = phi + lo.phase(n, fs, rng)
        acc += 10.0 ** (four_configs(frame, cols, pilots, phi, cfo_hz)
                        / 10.0)
    return 10.0 * np.log10(acc / n_frames)


def nominal_readings(cfg, n_lo: int, n_frames: int, seed: int,
                cfo_hz: float = 0.0) -> np.ndarray:
    """The four readings at the shipped LO profile for one numerology:
    frame with pilots + LTF pair, ``n_frames`` realizations averaged."""
    wf, cols = generate_ofdm_with_pilots(cfg)
    frame = build_frame(cfg, data=wf)
    pilots = pilot_sequence(cfg.n_symbols, cols.size)
    return sweep_point(DEFAULT_WIFI7_LO_PROFILE, frame, cols, pilots, n_lo,
                           n_frames, np.random.default_rng(seed), cfo_hz)
