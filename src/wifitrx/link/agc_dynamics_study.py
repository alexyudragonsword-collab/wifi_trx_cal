"""What the AGC's settling costs at the front of a packet.

The receiver idles at its highest gain, detects the packet over the
short training field, switches state after an attack delay, and its
VGA and DC loop settle with their own time constants
(``impairments.agc_dynamics``).  Everything that has not settled by the
LTF is frozen into the channel estimate for the whole packet; what the
ADC clipped before the switch is simply gone.  This study drives one
packet — [silence | STF | GI2 | LTF | LTF | data with pilots] — through
an otherwise clean receiver and reads both EVM views of
``cal.sequence.score_views`` plus the modem form symbol by symbol, as a
function of the attack delay and of the DC-loop time constant.  The
802.11 budget is the 8 us L-STF: an AGC that has not finished by then
is switching under the LTF.

Isolation method: the receiver carries thermal noise, the channel LPF,
the ADC and the state-dependent DC offsets, and nothing else that the
calibration would otherwise remove, so the readings are the AGC's own.
"""
from __future__ import annotations

from dataclasses import replace

import numpy as np

from ..cal.sequence import score_views
from ..cal.sync import align_delay, compensate_delay
from ..chain.rx import RxChain
from ..chain.params import RxParams
from ..impairments.agc_dynamics import AgcDynamics
from ..impairments.iq_imbalance import FreqDepIQImbalance
from ..impairments.phase_noise import LOModel
from ..units import power_dbm
from ..waveform.ofdm import OFDMConfig
from ..waveform.pilots import generate_ofdm_with_pilots, pilot_sequence
from ..waveform.preamble import STF_PERIOD_S, build_frame

#: the L-STF the standard gives the AGC
STF_PERIODS = 10
STF_S = STF_PERIODS * STF_PERIOD_S


def study_receiver(bandwidth_hz: float, seed: int = 0) -> RxParams:
    """A receiver with the AGC's own ingredients and no other impairment:
    the state ladder, state-dependent DC offsets (drawn like a real
    part's LO self-mixing), the channel LPF, thermal noise and the ADC.
    IQ imbalance, mixer IM2 and phase noise are off — the calibration
    removes them and they would mask the settling."""
    rxp = RxParams(bandwidth_hz=bandwidth_hz).randomize(np.random.default_rng(seed))
    return replace(rxp, iq=FreqDepIQImbalance(enabled=False),
                   im2=replace(rxp.im2, enabled=False),
                   lo=LOModel(enabled=False))


def study_frame(cfg: OFDMConfig):
    """[STF (8 us) | GI2 | LTF | LTF | data with pilots], one padding
    symbol like the calibration's scoring frame; returns (frame, cols,
    pilots)."""
    cfg_pad = replace(cfg, n_symbols=cfg.n_symbols + 1)
    wf, cols = generate_ofdm_with_pilots(cfg_pad)
    frame = build_frame(cfg_pad, data=wf, stf_periods=STF_PERIODS)
    return frame, cols, pilot_sequence(cfg_pad.n_symbols, cols.size)


def packet_readings(rxp: RxParams, cfg: OFDMConfig, p_in_dbm: float,
                    dyn: AgcDynamics, frame=None, cols=None, pilots=None,
                    silence_s: float = 1.0e-6, seed: int = 0) -> dict:
    """One packet through the receiver with ``dyn`` in force.  Returns
    both EVM views (``evm_db`` isolation, ``evm_modem_db`` modem form),
    the modem form per data symbol (``per_symbol_db``), the target state
    and the number of ladder steps the AGC crossed."""
    if frame is None:
        frame, cols, pilots = study_frame(cfg)
    fs = cfg.sample_rate_hz
    rx = RxChain(replace(rxp, agc_dynamics=dyn), fs)
    rx.agc(p_in_dbm)
    amp = 10.0 ** ((p_in_dbm - power_dbm(frame.data.x)) / 20.0)
    n_sil = int(round(silence_s * fs))
    x = frame.x * amp
    guard = 64
    xp = np.concatenate([np.zeros(n_sil, dtype=complex), x, x[:guard]])
    y = rx(xp, rng=np.random.default_rng(seed))
    # bulk delay from the data part (the head may be clipped or mid-step)
    n_head = frame.preamble_len
    _, _, info = align_delay(xp[n_sil + n_head:n_sil + x.size],
                             y[n_sil + n_head:n_sil + x.size + guard // 2],
                             max_lag=guard // 2)
    y = compensate_delay(y, info["lag_total"], n_sil, x.size)
    xd, yd = x[n_head:], y[n_head:]
    g = np.vdot(xd, yd) / np.vdot(xd, xd)
    views = score_views(y / g / amp, frame, cols, pilots, cfg.n_symbols)
    err = np.abs(views["syms_modem"] - views["ref_syms"]) ** 2
    p_ref = float((np.abs(views["ref_syms"]) ** 2).mean())
    per_symbol = 10.0 * np.log10(err.mean(axis=1) / p_ref)
    return {"evm_db": float(views["evm_db"]),
            "evm_modem_db": float(views["evm_modem_db"]),
            "per_symbol_db": per_symbol,
            "target_state": int(rx.lna_idx),
            "states_crossed": int(abs(rx.lna_idx - dyn.start_state)),
            "vga_db": float(rx.vga_db)}


def sweep(rxp: RxParams, cfg: OFDMConfig, p_in_dbm: float, base: AgcDynamics,
          field: str, values: np.ndarray, seed: int = 0) -> dict:
    """``packet_readings`` over ``values`` of one ``AgcDynamics`` field
    (``attack_s``, ``vga_tau_s`` or ``dc_tau_s``), the others held at
    ``base``; ``settled`` is the same packet with the dynamics off."""
    frame, cols, pilots = study_frame(cfg)
    rows = [packet_readings(rxp, cfg, p_in_dbm,
                            replace(base, enabled=True, **{field: float(v)}),
                            frame, cols, pilots, seed=seed) for v in values]
    settled = packet_readings(rxp, cfg, p_in_dbm, replace(base, enabled=False),
                              frame, cols, pilots, seed=seed)
    return {"field": field, "values": np.asarray(values, dtype=float),
            "evm_modem_db": np.array([r["evm_modem_db"] for r in rows]),
            "evm_db": np.array([r["evm_db"] for r in rows]),
            "per_symbol_db": np.array([r["per_symbol_db"] for r in rows]),
            "settled": settled, "rows": rows}


def budget(times_s: np.ndarray, evm_db: np.ndarray, settled_db: float,
           margin_db: float = 0.5) -> float:
    """The largest time on the sweep whose reading is still within
    ``margin_db`` of the settled value, walking up from the smallest
    time and stopping at the first point outside (a later point that
    happens to fall back inside does not extend the budget).  NaN when
    even the first point is outside."""
    ok = np.asarray(evm_db) <= settled_db + margin_db
    t = np.asarray(times_s, dtype=float)
    order = np.argsort(t)
    last = float("nan")
    for i in order:
        if not ok[i]:
            break
        last = float(t[i])
    return last
