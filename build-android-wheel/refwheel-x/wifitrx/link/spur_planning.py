# Fractional-spur prediction adapted from
# pll_simulator:src/pllsim/core/dtcspurs.py (mechanistic EFM1 + DTC
# quantization model, self-contained here: no pllsim architecture objects,
# single-pole loop NTF).  See PROVENANCE.md.
"""Fractional-N spur prediction and WiFi channel planning.

Fractional spurs are deterministic: the modulator residual is periodic in
the accumulator, so DTC quantization/INL produce coherent tones at

    nu_k = (k * frac) mod 1,    f_spur = min(nu_k, 1 - nu_k) * fref.

Near-integer channels are worst — the beat falls inside the loop
bandwidth where the NTF is ~1.  ``channel_spur_table`` sweeps a channel
grid and flags "dirty" channels whose predicted in-band spur exceeds a
threshold; ``lo_with_frac_spurs`` builds an LOModel carrying the
predicted spur set for time-domain injection.
"""
from __future__ import annotations

from dataclasses import dataclass, replace

import numpy as np

from ..impairments.phase_noise import LOModel

TWOPI = 2.0 * np.pi


@dataclass(frozen=True)
class FracNConfig:
    fref_hz: float = 38.4e6
    acc_bits: int = 24            # EFM1 accumulator width
    dtc_range_s: float = 30e-12   # DTC full range covers one ref UI residual? no: range of trim
    dtc_bits: int = 9             # DTC resolution: t_res = range / 2^bits
    inl_sin: tuple | None = (0.15e-12, 3.0, 0.7)   # (amp_s, cycles, phase)
    gain_eps: float = 0.002       # residual DTC gain error after cal
    loop_bw_hz: float = 150e3
    vco_mult: int = 2             # VCO runs at vco_mult * f_lo


def lock_time_s(cfg: FracNConfig, freq_step_hz: float = 100e6,
                settle_tol_hz: float = 1e3, zeta: float = 0.7) -> float:
    """Approximate PLL lock time for a ``freq_step_hz`` retune.

    Second-order type-II envelope: t ~ ln(step/tol) / (zeta * wn), with
    wn ~ 2*pi*loop_bw / 2 (loop -3 dB bandwidth roughly twice the natural
    frequency at zeta=0.7).  An engineering estimate for the power-on time
    budget — replace with the measured lock spec once the PLL team has
    one; the point is that PLL lock appears IN the budget at all.
    """
    wn = TWOPI * cfg.loop_bw_hz / 2.0
    ratio = max(abs(freq_step_hz) / settle_tol_hz, 1.0)
    return float(np.log(ratio) / (zeta * wn))


def frac_of(f_lo_hz: float, cfg: FracNConfig) -> float:
    n = cfg.vco_mult * f_lo_hz / cfg.fref_hz
    return float(n - np.floor(n))


def predict_spurs(f_lo_hz: float, cfg: FracNConfig, kmax: int = 6,
                  n_seq: int = 1 << 14, fmin: float = 1e3,
                  floor_dbc: float = -110.0) -> dict[float, float]:
    """Predicted {offset_hz: dbc} spurs for one LO frequency."""
    frac = frac_of(f_lo_hz, cfg)
    word = int(round(frac * (1 << cfg.acc_bits)))
    t_res = cfg.dtc_range_s / (1 << cfg.dtc_bits)

    # EFM1 residual ramp (bit-true accumulator), DTC target in seconds
    acc = (np.arange(n_seq, dtype=np.int64) * word) % (1 << cfg.acc_bits)
    res_ui = acc.astype(float) / (1 << cfg.acc_bits)      # 0..1 UI
    t_req = res_ui * cfg.dtc_range_s                       # mapped to DTC range
    codes = np.clip(np.round(t_req / t_res), 0, (1 << cfg.dtc_bits) - 1)
    err = codes * t_res - t_req
    if cfg.gain_eps:
        err = err + cfg.gain_eps * codes * t_res
    if cfg.inl_sin:
        amp, cyc, ph = cfg.inl_sin
        x = codes / ((1 << cfg.dtc_bits) - 1)
        err = err + amp * np.sin(TWOPI * cyc * x + ph)
    err = err - err.mean()

    n = np.arange(n_seq)
    w = 0.5 - 0.5 * np.cos(TWOPI * n / n_seq)
    wsum = w.sum()
    f_out = cfg.vco_mult * f_lo_hz

    out: dict[float, float] = {}
    for k in range(1, kmax + 1):
        nu = (k * frac) % 1.0
        f_off = min(nu, 1.0 - nu) * cfg.fref_hz
        if not (fmin < f_off < 0.45 * cfg.fref_hz):
            continue
        key = round(f_off, 3)
        if key in out:
            continue
        a = 2.0 * np.abs(np.sum(w * err * np.exp(-1j * TWOPI * nu * n))) / wsum
        dphi = TWOPI * f_out * a
        ntf = 1.0 / np.sqrt(1.0 + (f_off / cfg.loop_bw_hz) ** 2)  # in-band ~1
        # spur referred to the divided LO output
        dbc = 20.0 * np.log10(max(dphi * ntf / 2.0 / cfg.vco_mult, 1e-30))
        if dbc > floor_dbc:
            out[key] = dbc
    return out


def lo_with_frac_spurs(f_lo_hz: float, cfg: FracNConfig | None = None,
                       base: LOModel | None = None, **kw) -> LOModel:
    """LOModel at f_lo carrying the predicted fractional spur set."""
    cfg = cfg or FracNConfig()
    base = base or LOModel()
    spurs = predict_spurs(f_lo_hz, cfg, **kw)
    return replace(base, freq_hz=f_lo_hz,
                   spur_offsets_hz=tuple(spurs.keys()),
                   spur_dbc=tuple(spurs.values()))


# --------------------------------------------------------------- planning
WIFI_CHANNELS_HZ = {
    "2g4": tuple(2412e6 + 5e6 * i for i in range(13)),
    "5g": tuple(5180e6 + 20e6 * i for i in range(0, 36)),
    "6g": tuple(5955e6 + 20e6 * i for i in range(0, 59)),
}


def channel_spur_table(bandwidth_hz: float, cfg: FracNConfig | None = None,
                       bands: tuple = ("2g4", "5g", "6g"),
                       dirty_threshold_dbc: float = -75.0,
                       **kw) -> list[dict]:
    """Per-channel worst in-band spur and dirty flag.

    A spur is in-band if its offset is below bandwidth/2 (it lands inside
    the wanted channel after downconversion).
    """
    cfg = cfg or FracNConfig()
    rows = []
    for band in bands:
        for f_c in WIFI_CHANNELS_HZ[band]:
            spurs = predict_spurs(f_c, cfg, **kw)
            inband = {f: d for f, d in spurs.items()
                      if f < bandwidth_hz / 2}
            worst = max(inband.values()) if inband else None
            rows.append({
                "band": band,
                "f_c_hz": f_c,
                "frac": frac_of(f_c, cfg),
                "worst_inband_dbc": worst,
                "dirty": bool(worst is not None
                              and worst > dirty_threshold_dbc),
            })
    return rows
