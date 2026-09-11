"""Does an impairment care where in the band a narrow signal sits?

802.11ax/be gives a user a resource unit, not the whole channel, so the
question a transceiver owner actually has is not "what is the EVM of the
channel" but "what is the EVM of *this* 106-tone slice, and does it get
worse near DC or at the edge".  The answer is different for every
impairment, because each one is localised differently in frequency:

* DC offset and mixer IM2 land **on and around DC**, so a slice centred
  there eats them and a slice at the edge does not see them at all;
* the channel low-pass rolls off at the **band edge**;
* IQ imbalance folds a tone at ``+f`` onto ``-f``, so what a slice sees
  depends on what sits at its **mirror**, not at itself;
* phase noise is common to every tone and should be flat with offset.

Isolation method throughout: one impairment at a time, directly read,
never a full-minus-one difference.  The sub-band is built by
``waveform.tone_plan.subband`` and carries the model's evenly-spaced
pilot set (``pilot_set="model"``) — the standard's RU pilot tables are
an external input this project does not hold, so the sweep is labelled
as the model's and the shape of the curves, not their absolute offset,
is the result.
"""
from __future__ import annotations

from dataclasses import replace

import numpy as np

from ..cal.sequence import score_views
from ..chain.params import RxParams
from ..chain.rx import RxChain
from ..impairments.iq_imbalance import FreqDepIQImbalance
from ..impairments.phase_noise import LOModel
from ..units import power_dbm
from ..waveform.ofdm import OFDMConfig
from ..waveform.pilots import generate_ofdm_with_pilots, pilot_sequence
from ..waveform.preamble import build_frame
from ..waveform.tone_plan import subband

#: the impairment each curve isolates
IMPAIRMENTS = ("dc+im2", "iq", "lpf", "phase noise", "all")


def study_receiver(bandwidth_hz: float, only: str, seed: int = 0) -> RxParams:
    """A randomised receiver with exactly one impairment family left on.

    ``nonlin_enabled`` and the ADC stay as drawn in every case: they are
    the front end, not an impairment one can localise in frequency, and
    turning them off would change the operating point the others are
    measured at.

    The channel low-pass is re-cornered to track the bandwidth
    (``0.55 * bandwidth_hz``, a 10 % margin over the half-channel).  The
    default 170 MHz nominal is a 320 MHz part, and left there an 80 MHz
    sweep sees no roll-off at all.  Note what a static filter can and
    cannot cost: per-tone equalisation removes any fixed frequency
    response exactly, so the isolation view never sees the filter's
    *shape* — what it sees is the noise enhanced on the tones the filter
    attenuated.  A flat "lpf" curve therefore means the corner is far
    from the slice, not that filters are free."""
    if only not in IMPAIRMENTS:
        raise ValueError(f"unknown impairment {only!r}; use one of {IMPAIRMENTS}")
    p = RxParams(bandwidth_hz=bandwidth_hz).randomize(np.random.default_rng(seed))
    off_iq = FreqDepIQImbalance(enabled=False)
    off_lo = LOModel(enabled=False)
    p = replace(p, lpf=replace(p.lpf, fc_nominal_hz=0.55 * bandwidth_hz))
    flat_lpf = replace(p.lpf, fc_nominal_hz=20.0 * bandwidth_hz)
    if only == "all":
        return p
    if only == "dc+im2":
        return replace(p, iq=off_iq, lo=off_lo, lpf=flat_lpf)
    if only == "iq":
        return replace(p, im2=replace(p.im2, enabled=False), lo=off_lo,
                       dc_offset=(), lpf=flat_lpf)
    if only == "lpf":
        return replace(p, iq=off_iq, im2=replace(p.im2, enabled=False),
                       lo=off_lo, dc_offset=())
    return replace(p, iq=off_iq, im2=replace(p.im2, enabled=False),
                   dc_offset=(), lpf=flat_lpf)          # phase noise


def slice_config(bandwidth_hz: float, n_tones: int, centre_tone: int,
                 qam_order: int = 256, n_symbols: int = 6) -> OFDMConfig:
    """A config whose active set is one narrow slice of the channel."""
    base = OFDMConfig(bandwidth_hz=bandwidth_hz, qam_order=qam_order,
                      n_symbols=n_symbols, oversampling=4)
    plan = subband(bandwidth_hz, base.subcarrier_spacing_hz, n_tones, centre_tone)
    return replace(base, tone_plan=plan, pilot_set="model")


def slice_readings(cfg: OFDMConfig, rxp: RxParams, p_in_dbm: float,
                   seed: int = 0) -> dict:
    """One slice through the receiver, both EVM views."""
    cfg_pad = replace(cfg, n_symbols=cfg.n_symbols + 1)
    wf, cols = generate_ofdm_with_pilots(cfg_pad)
    frame = build_frame(cfg_pad, data=wf)
    pilots = pilot_sequence(cfg_pad.n_symbols, cols.size)
    fs = cfg.sample_rate_hz
    rx = RxChain(rxp, fs)
    rx.agc(p_in_dbm)
    amp = 10.0 ** ((p_in_dbm - power_dbm(frame.data.x)) / 20.0)
    y = rx(frame.x * amp, rng=np.random.default_rng(seed))
    g = np.vdot(frame.x, y) / np.vdot(frame.x, frame.x)
    views = score_views(y / g, frame, cols, pilots, cfg.n_symbols)
    return {"evm_db": float(views["evm_db"]),
            "evm_modem_db": float(views["evm_modem_db"])}


def centre_sweep(bandwidth_hz: float, n_tones: int, centres, p_in_dbm: float,
                 impairments=IMPAIRMENTS, seed: int = 0,
                 qam_order: int = 256) -> dict:
    """EVM against where the slice sits, one curve per isolated
    impairment.  ``centres`` are signed tone indices of the slice centre."""
    centres = np.asarray(centres, dtype=int)
    out = {}
    for only in impairments:
        rxp = study_receiver(bandwidth_hz, only, seed)
        vals = []
        for c in centres:
            cfg = slice_config(bandwidth_hz, n_tones, int(c), qam_order)
            vals.append(slice_readings(cfg, rxp, p_in_dbm, seed)["evm_db"])
        out[only] = np.asarray(vals)
    scs = OFDMConfig(bandwidth_hz=bandwidth_hz).subcarrier_spacing_hz
    return {"centres": centres, "centre_hz": centres * scs,
            "n_tones": int(n_tones), "evm_db": out,
            "impairments": tuple(impairments)}
