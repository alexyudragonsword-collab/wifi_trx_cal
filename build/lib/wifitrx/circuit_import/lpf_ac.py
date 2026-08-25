"""Baseband LPF AC-response import: spectre AC CSV -> TunableLPF.

Reads (freq_hz, mag_db[, phase_deg]), finds the -3 dB corner and fits the
equivalent Butterworth order from the rolloff slope, then builds a
TunableLPF whose ``rc_error`` is the measured corner error against the
declared nominal — i.e. the process corner the RC calibration must trim
out.  Optionally returns the measured response itself as a real FIR for
exact common-mode injection.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np

from ..impairments.analog_filter import TunableLPF


def load_lpf_ac_csv(path: str | Path) -> tuple[np.ndarray, np.ndarray, np.ndarray | None]:
    """Returns (freq_hz, mag_db, phase_deg|None)."""
    f, m, p = [], [], []
    has_phase = False
    for raw in Path(path).read_text().splitlines():
        line = raw.strip()
        if not line or line[0] in "#!*;":
            continue
        parts = [s.strip() for s in line.replace("\t", ",").split(",")
                 if s.strip()]
        try:
            vals = [float(v) for v in parts]
        except ValueError:
            continue  # header
        if len(vals) < 2:
            continue
        f.append(vals[0])
        m.append(vals[1])
        if len(vals) >= 3:
            p.append(vals[2])
            has_phase = True
    if len(f) < 8:
        raise ValueError(f"{path}: AC 数据点不足({len(f)} < 8)")
    order = np.argsort(f)
    f_arr = np.asarray(f, dtype=float)[order]
    m_arr = np.asarray(m, dtype=float)[order]
    p_arr = (np.asarray(p, dtype=float)[order] if has_phase else None)
    return f_arr, m_arr, p_arr


def fit_lpf_from_ac(path: str | Path, fc_nominal_hz: float,
                    **lpf_kwargs) -> tuple[TunableLPF, dict]:
    """Fit corner + order from an AC sweep; return the configured TunableLPF
    and a fit-info dict (measured corner, order, rc_error)."""
    f, mag_db, _ = load_lpf_ac_csv(path)
    ref_db = float(np.median(mag_db[f < 0.05 * np.max(f)][:8]))
    rel = mag_db - ref_db
    # -3 dB crossing (first)
    below = np.nonzero(rel <= -3.0)[0]
    if below.size == 0:
        raise ValueError(f"{path}: 扫描范围内未达到 -3 dB,corner 不可测")
    i = below[0]
    fc_meas = float(np.interp(-3.0, rel[i - 1:i + 1][::-1],
                              f[i - 1:i + 1][::-1])) if i > 0 else float(f[0])
    # equivalent order from the asymptotic slope (dB/decade / 20); keep the
    # fit window below ~5x corner — near Nyquist a sampled/measured response
    # rolls off faster than the analog asymptote and inflates the order
    tail = (f > 2.0 * fc_meas) & (f < 5.0 * fc_meas) & (rel < -10.0)
    if np.count_nonzero(tail) >= 4:
        slope = np.polyfit(np.log10(f[tail]), rel[tail], 1)[0]
        order = int(np.clip(round(-slope / 20.0), 1, 9))
    else:
        order = 5
    rc_error = fc_meas / fc_nominal_hz - 1.0
    lpf = TunableLPF(fc_nominal_hz=fc_nominal_hz, order=order,
                     rc_error=rc_error, **lpf_kwargs)
    info = {"fc_measured_hz": fc_meas, "order": order, "rc_error": rc_error}
    return lpf, info
