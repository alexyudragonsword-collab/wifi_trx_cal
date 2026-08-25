"""Inter-chain phase/delay alignment for MIMO operation.

Beamforming needs the chains phase- and delay-matched.  Using one RX
(chain 0) as the common reference through the calibration coupler, each
TX chain transmits the same one-sided comb; the per-bin complex ratio of
chain i's capture to chain 0's cancels the shared RX/loopback response
and leaves chain i's relative response.  A linear fit of its phase vs
frequency separates delay (slope) from LO-distribution phase (intercept),
both programmed as digital pre-corrections on TX_i.
"""
from __future__ import annotations

import numpy as np

from ..chain.loopback import LoopbackPath
from ..chain.mimo import MimoTrx
from ..units import power_dbm
from ..waveform.stimuli import bin_value, iq_cal_comb
from .base import CalResult


def _chain_response(mimo: MimoTrx, i: int, x: np.ndarray,
                    freqs: np.ndarray, path: LoopbackPath) -> np.ndarray:
    cap = mimo.loopback_capture(i, 0, x, path)
    return np.array([bin_value(cap, f, mimo.fs) / bin_value(x, f, mimo.fs)
                     for f in freqs])


def _fit_phase(freqs: np.ndarray, ratio: np.ndarray) -> tuple[float, float]:
    """LS fit angle(ratio) = intercept + slope * f; returns (deg, seconds)."""
    ph = np.unwrap(np.angle(ratio))
    a = np.vstack([np.ones_like(freqs), freqs]).T
    coef, *_ = np.linalg.lstsq(a, ph, rcond=None)
    intercept_deg = float(np.degrees(coef[0]))
    tau_s = float(-coef[1] / (2 * np.pi))
    return intercept_deg, tau_s


def measure_coupling_matrix(mimo: MimoTrx, path: LoopbackPath | None = None,
                            n: int = 1 << 14, f_probe: float = 23e6,
                            amp: float = 0.05, seed: int = 31) -> np.ndarray:
    """Measured port-coupling matrix (diag-normalized).

    Chain i transmits alone; every antenna port j is observed through the
    common reference RX_0, so the RX response cancels in the ratio
    C[j,i] = port_j / port_i.  Run AFTER mimo_align (the TX chains are
    then phase/delay matched, so C describes the coupling itself).
    """
    from ..waveform.stimuli import single_tone
    if path is None:
        path = LoopbackPath(atten_db=40.0, delay_ns=6.0)
    n_ch = mimo.params.n_chains
    tone = single_tone(f_probe, mimo.fs, n, amp=amp)
    mimo.rxs[0].agc(power_dbm(mimo.txs[0](tone)) - path.atten_db)
    c = np.zeros((n_ch, n_ch), dtype=complex)
    for i in range(n_ch):
        x_mat = np.zeros((n_ch, n), dtype=complex)
        x_mat[i] = tone
        refs = {}
        for j in range(n_ch):
            cap = mimo.port_capture(j, x_mat, path, seed=seed)
            refs[j] = bin_value(cap, f_probe, mimo.fs)
        for j in range(n_ch):
            c[j, i] = refs[j] / refs[i]
    return c


def calibrate_mimo_decouple(mimo: MimoTrx, path: LoopbackPath | None = None,
                            n: int = 1 << 14, seed: int = 31) -> CalResult:
    """Digital decoupling precoder W = C^-1 from the measured coupling."""
    c_meas = measure_coupling_matrix(mimo, path, n=n, seed=seed)
    before_xtalk = _worst_crosstalk_db(mimo, path, n, seed)
    mimo.precoder = np.linalg.inv(c_meas)
    after_xtalk = _worst_crosstalk_db(mimo, path, n, seed + 1)
    return CalResult(
        name="mimo_decouple",
        estimated={"coupling_matrix": c_meas},
        corrections={"precoder": mimo.precoder},
        metrics_before={"worst_crosstalk_db": before_xtalk},
        metrics_after={"worst_crosstalk_db": after_xtalk},
        passed=after_xtalk < -45.0,
        cost={"captures": 2 * mimo.params.n_chains ** 2,
              "samples": 2 * mimo.params.n_chains ** 2 * n},
    )


def _worst_crosstalk_db(mimo: MimoTrx, path: LoopbackPath | None,
                        n: int, seed: int) -> float:
    """Worst port-to-port leakage with one stream active at a time."""
    from ..waveform.stimuli import single_tone
    n_ch = mimo.params.n_chains
    tone = single_tone(23e6, mimo.fs, n, amp=0.05)
    worst = -np.inf
    for i in range(n_ch):
        x_mat = np.zeros((n_ch, n), dtype=complex)
        x_mat[i] = tone
        own = None
        for j in range(n_ch):
            cap = mimo.port_capture(j, x_mat, path, seed=seed)
            v = abs(bin_value(cap, 23e6, mimo.fs))
            if j == i:
                own = v
        for j in range(n_ch):
            if j == i:
                continue
            cap = mimo.port_capture(j, x_mat, path, seed=seed)
            v = abs(bin_value(cap, 23e6, mimo.fs))
            worst = max(worst, 20 * np.log10(v / own))
    return float(worst)


def calibrate_mimo_align(mimo: MimoTrx, path: LoopbackPath | None = None,
                         n: int = 1 << 14, n_tones: int = 8,
                         amp: float = 0.04, seed: int = 21) -> CalResult:
    if path is None:
        path = LoopbackPath(atten_db=40.0, delay_ns=6.0)
    bw = mimo.txs[0].params.bandwidth_hz
    x, freqs = iq_cal_comb(bw, mimo.fs, n, n_tones=n_tones, amp_total=amp,
                           seed=seed, sign=+1)
    mimo.rxs[0].agc(power_dbm(mimo.txs[0](x)) - path.atten_db)

    resp0 = _chain_response(mimo, 0, x, freqs, path)
    before, after = {}, {}
    for i in range(1, mimo.params.n_chains):
        d = _chain_response(mimo, i, x, freqs, path) / resp0
        ph_deg, tau_s = _fit_phase(freqs, d)
        before[i] = {"phase_deg": ph_deg, "delay_ps": tau_s * 1e12}
        # program the pre-corrections (phase_corr multiplies exp(-j*corr);
        # positive delay_corr_samples advances the chain)
        mimo.txs[i].phase_corr_deg += ph_deg
        mimo.txs[i].delay_corr_samples += tau_s * mimo.fs
        # verify residual
        d2 = _chain_response(mimo, i, x, freqs, path) / \
            _chain_response(mimo, 0, x, freqs, path)
        ph2, tau2 = _fit_phase(freqs, d2)
        after[i] = {"phase_deg": ph2, "delay_ps": tau2 * 1e12}

    worst_ph = max(abs(v["phase_deg"]) for v in after.values())
    worst_tau = max(abs(v["delay_ps"]) for v in after.values())
    return CalResult(
        name="mimo_align",
        estimated={f"chain{i}": before[i] for i in before},
        corrections={f"chain{i}": {
            "phase_corr_deg": mimo.txs[i].phase_corr_deg,
            "delay_corr_samples": mimo.txs[i].delay_corr_samples,
        } for i in before},
        metrics_before={f"chain{i}_{k}": v
                        for i in before for k, v in before[i].items()},
        metrics_after={f"chain{i}_{k}": v
                       for i in after for k, v in after[i].items()},
        passed=worst_ph < 2.0 and worst_tau < 100.0,
    )
