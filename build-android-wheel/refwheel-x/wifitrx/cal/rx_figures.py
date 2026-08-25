"""Measured receive-side deliverable figures: NF and post-tracking phase error.

The residual surface was transmit-heavy until B12: the receive view's
dominant error sources — the noise floor and the LO phase noise —
shipped nowhere, so a consumer building a receive link simulation had
to take them from the parameter tables, which is exactly the
model-trusts-model shortcut the handoff exists to remove.  These are
*measurements at the delivered operating point*, made the way a lab
would:

* **Effective noise figure** from an idle-channel capture through the
  whole chain (LNA to digital output), referred to the input through a
  correlation gain estimate.  Measured this way it absorbs everything
  that raises the floor — thermal, quantization, DC-correction residue
  — which is what makes the replay's SNR reconstruction self-consistent
  rather than a Friis paper number.
* **Integrated post-tracking phase error** from a CW tone through the
  same state: per-symbol mean and slope removed (what common-phase and
  frequency tracking remove), thermal phase variance subtracted using
  the NF measured above (an instrument correction with an
  independently measured quantity — not a term solved from any closure
  target).  Deliberately *not* called phase noise: whatever else the
  delivered state puts into the angle at this level — residual
  per-state IQ, spurs — lands in the figure too, and that is what
  makes it the right number to inject, because the closure target sees
  the same physics.

Both are read at the AGC state the stated input level lands on, because
the receive figures of this part are properties of a gain state, not of
the die.
"""
from __future__ import annotations

import numpy as np

from ..units import power_dbm
from ..waveform.ofdm import OFDMConfig

KT_DBM_HZ = -173.975


def measure_rx_nf_db(rx, cfg: OFDMConfig, p_in_dbm: float,
                     n: int = 16384, seed: int = 0) -> float:
    """Idle-channel effective NF at the state ``p_in_dbm`` lands on.

    Gain comes from a correlation estimate on a modest tone (robust to
    the noise the capture deliberately keeps); the floor comes from a
    zero-input capture at the same settings.  The noise is integrated
    at the digital output — i.e. over the channel filter the consumer's
    samples also pass through — and referred to the nominal bandwidth,
    so replaying ``-174 + NF + 10log10(BW)`` reconstructs exactly the
    measured noise-to-signal ratio.
    """
    rx.agc(p_in_dbm)
    fs = rx.fs
    t = np.arange(n) / fs
    # a tone at the stated level, mid-band so filter droop is negligible
    f0 = cfg.bandwidth_hz / 8.0
    amp = 10.0 ** ((p_in_dbm - 30.0) / 20.0) * np.sqrt(1000.0)
    x = amp * np.exp(2j * np.pi * f0 * t)
    y = rx(x, rng=np.random.default_rng(seed))
    g = np.vdot(x, y) / np.vdot(x, x)
    gain_db = 20.0 * np.log10(abs(g))

    quiet = rx(np.zeros(n, dtype=complex),
               rng=np.random.default_rng(seed + 1))
    floor_in_dbm = power_dbm(quiet) - gain_db
    return float(floor_in_dbm
                 - (KT_DBM_HZ + 10.0 * np.log10(cfg.bandwidth_hz)))


def measure_rx_phase_err_dbc(rx, cfg: OFDMConfig, p_in_dbm: float,
                             nf_db: float, seed: int = 0) -> float:
    """Integrated post-tracking phase error at the same state, in dBc.

    The tracking window is one OFDM symbol at the capture rate — mean
    per symbol (CPE) and slope per symbol (frequency tracking) — so the
    figure is what the angle costs *after* the tracking every real
    modem runs, which is the number a link simulation should inject.
    Thermal phase variance (half the inverse SNR, from the
    independently measured NF) is subtracted; without that the figure
    would be an SNR reading at low drive.
    """
    n_symbol = (cfg.fft_size + cfg.cp_len) * cfg.oversampling
    n = 64 * n_symbol
    rx.agc(p_in_dbm)
    fs = rx.fs
    t = np.arange(n) / fs
    f0 = cfg.bandwidth_hz / 8.0
    amp = 10.0 ** ((p_in_dbm - 30.0) / 20.0) * np.sqrt(1000.0)
    x = amp * np.exp(2j * np.pi * f0 * t)
    y = rx(x, rng=np.random.default_rng(seed + 2))

    phi = np.unwrap(np.angle(y * np.conj(x)))
    blocks = phi[: (n // n_symbol) * n_symbol].reshape(-1, n_symbol)
    # remove per-symbol mean AND slope: the mean is what CPE tracking
    # takes out, the slope is what frequency tracking takes out — a
    # figure that kept the CFO ramp would price the synthesizer for the
    # clock's sins
    k = np.arange(n_symbol) - (n_symbol - 1) / 2.0
    slope = (blocks @ k) / float(k @ k)
    resid = (blocks - blocks.mean(axis=1, keepdims=True)
             - slope[:, None] * k)
    var_total = float(np.var(resid))

    snr_db = (p_in_dbm
              - (KT_DBM_HZ + nf_db + 10.0 * np.log10(cfg.bandwidth_hz)))
    var_thermal = 0.5 / 10.0 ** (snr_db / 10.0)
    var_pn = max(var_total - var_thermal, 1e-12)
    return float(10.0 * np.log10(var_pn))


def measure_rx_im3_dbc(rx, cfg: OFDMConfig, p_in_dbm: float,
                       seed: int = 0) -> float:
    """Two-tone IM3 at the same state and level, in dBc per tone.

    The receive view's in-band distortion — the term whose absence the
    replay closure exposed: at the delivered level the landing state's
    third-order products sit tens of dB up, and a residual list without
    them under-explains the measured receive EVM.  Measured the way a
    lab does it: two equal tones at the stated total power, read the
    2f1-f2 / 2f2-f1 products against a tone, worst of the two.
    """
    n = 32768
    rx.agc(p_in_dbm)
    fs = rx.fs
    t = np.arange(n) / fs
    # tone spacing chosen so both IM3 products land in-band on FFT bins
    df = fs / n
    f1 = round(cfg.bandwidth_hz / 8.0 / df) * df
    f2 = round((cfg.bandwidth_hz / 8.0 + cfg.bandwidth_hz / 32.0) / df) * df
    amp = 10.0 ** ((p_in_dbm - 30.0) / 20.0) * np.sqrt(1000.0 / 2.0)
    x = amp * (np.exp(2j * np.pi * f1 * t) + np.exp(2j * np.pi * f2 * t))
    y = rx(x, rng=np.random.default_rng(seed + 3))
    spec = np.abs(np.fft.fft(y)) ** 2

    def bin_power(f_hz: float) -> float:
        return float(spec[int(round(f_hz / df)) % n])

    tone = max(bin_power(f1), bin_power(f2))
    im3 = max(bin_power(2 * f1 - f2), bin_power(2 * f2 - f1))
    return float(10.0 * np.log10(max(im3, 1e-30) / tone))
