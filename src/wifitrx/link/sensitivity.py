"""RX sensitivity: behavioral model vs analytic budget, cross-checked.

Two fully independent paths to the same number:

- analytic: Friis floor ``sensitivity_dbm(nf, bw, snr_req)`` from
  ``link.budget`` (KT + 10log10(B) + NF + SNR_req);
- measured: OFDM at a swept RF input power through the RxChain (thermal
  noise injected per the AGC-selected LNA state), per-tone-equalized EVM,
  sensitivity = input power where EVM crosses -snr_req.

Agreement validates the whole noise/units/EVM plumbing chain — the class
of bug where a "twin" implementation silently diverges from the model it
grades.  Disagreement means one side is wrong, which is the point.

Caveats (deliberate): ``snr_req_db`` is a budgeting approximation (see
``link.mcs`` verification status), so absolute sensitivities inherit that
caveat — deltas between the two paths and between MCS rows are the
trustworthy quantities.  Run with a clean RX (impairments corrected or
disabled) so residuals don't pollute the noise-limited comparison.
"""
from __future__ import annotations

import numpy as np

from ..cal.sync import _fractional_advance, align_delay
from ..chain.rx import RxChain
from ..metrics.cpe import correct_cpe
from ..metrics.evm import evm
from ..units import power_dbm
from ..waveform.ofdm import OFDMConfig, demodulate_ofdm, generate_ofdm
from .budget import sensitivity_dbm
from .mcs import mcs

_WARMUP = 512  # cyclic prefix samples to flush IIR startup transients
_GUARD = 64    # cyclic tail so delay compensation never runs out of frame


def measured_rx_evm_db(rx: RxChain, cfg: OFDMConfig, p_in_dbm: float,
                       seed: int = 0) -> float:
    """Per-tone-equalized EVM of an OFDM frame at ``p_in_dbm`` RF input.

    The RX LPF's group delay must be removed before demodulation: a few
    samples of un-compensated delay push the FFT window into the windowed
    symbol edges and floor the EVM near -28 dB regardless of SNR (per-tone
    EQ fixes linear response, not inter-symbol interference).
    """
    wf = generate_ofdm(cfg)
    x = wf.x * 10.0 ** ((p_in_dbm - power_dbm(wf.x)) / 20.0)
    rx.agc(p_in_dbm)
    x_w = np.concatenate([x[-_WARMUP:], x, x[:_GUARD]])  # cyclic extension
    y_full = rx(x_w, rng=np.random.default_rng(seed))
    _, _, info = align_delay(x, y_full[_WARMUP:_WARMUP + x.size],
                             max_lag=_GUARD // 2)
    d = info["lag_total"]
    start = _WARMUP + int(round(d))
    y = _fractional_advance(y_full[start:start + x.size], d - round(d))
    syms = correct_cpe(demodulate_ofdm(y, wf), wf.tx_symbols)
    return evm(syms, wf.tx_symbols, equalize="per_tone").db


def _state_nf_db(rx, idx: int, vga_db: float = 0.0) -> float:
    """Input-referred NF of one gain state, baseband stage included."""
    from .budget import effective_nf_db
    return effective_nf_db(rx.params.lna_states[idx],
                           getattr(rx.params, "baseband", None), vga_db)


def sensitivity_study(rx: RxChain, cfg: OFDMConfig, mcs_indices,
                      impl_loss_db: float = 0.0, seed: int = 0,
                      probe_span_db: float = 4.0) -> list[dict]:
    """Measured vs analytic sensitivity per MCS.

    For each MCS: predict the analytic floor from the AGC-selected state's
    NF, measure EVM at three input levels around it, and interpolate the
    -snr_req crossing (EVM in dB is ~linear in input power in the
    noise-limited region).

    ``floor_limited`` marks rows whose -snr_req sits within 5 dB of the
    strong-signal EVM floor: there the crossing leaves the pure 1 dB/dB
    noise slope and the measured sensitivity legitimately deviates from
    the Friis analytic value (e.g. 4096-QAM at 320 MHz measured +2.6 dB
    against a -43.6 dB floor) — a floor-vs-noise joint limit, not a
    model error.
    """
    floor_evm_db = measured_rx_evm_db(rx, cfg, -30.0, seed=seed)
    rows = []
    for idx in mcs_indices:
        m = mcs(idx)
        # NF of the state the AGC would sit in near sensitivity — via
        # the cascade, so an enabled baseband stage is included at the
        # VGA setting the AGC actually lands on
        guess = sensitivity_dbm(_state_nf_db(rx, 0), cfg.bandwidth_hz,
                                m.snr_req_db, impl_loss_db)
        rx.agc(guess)
        nf = _state_nf_db(rx, rx.lna_idx, rx.vga_db)
        analytic = sensitivity_dbm(nf, cfg.bandwidth_hz, m.snr_req_db,
                                   impl_loss_db)

        p_probe = analytic + np.array([-probe_span_db, 0.0, probe_span_db])
        e = [measured_rx_evm_db(rx, cfg, p, seed=seed) for p in p_probe]
        # EVM falls ~1 dB per input dB; interpolate the -snr_req crossing
        measured = float(np.interp(-m.snr_req_db, e[::-1], p_probe[::-1]))
        rows.append({
            "mcs": idx, "modulation": m.modulation,
            "snr_req_db": m.snr_req_db, "nf_db": nf,
            "analytic_dbm": analytic, "measured_dbm": measured,
            "delta_db": measured - analytic,
            "floor_evm_db": floor_evm_db,
            "floor_limited": bool(floor_evm_db > -(m.snr_req_db + 5.0)),
        })
    return rows
