"""Run an external waveform through the (calibrated) transceiver model.

The comm-algorithm team's entry point: build/restore a calibrated
transceiver, push their wifitrx-wave file through the chosen scenario and
get back the output waveform plus channel metrics.  EVM closure happens
on THEIR demodulator — that is the point of the handoff; this side
reports the physical-channel quantities (power, PAE, ACLR, delay).
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np

from ..cal.base import load_cal_state
from ..cal.sequence import agc_for_loopback, capture_aligned, run_full_cal
from ..chain import LoopbackPath, RxChain, RxParams, TxChain, TxParams
from ..metrics import aclr
from ..units import power_dbm
from ..waveform.ofdm import OFDMConfig
from .waveform_io import Waveform, validate_waveform

SCENARIOS = ("tx_only", "loopback", "rx_only")


@dataclass
class HandoffResult:
    output: Waveform
    metrics: dict


def build_calibrated_trx(bandwidth_hz: float, fs_hz: float, seed: int = 5,
                         cal_state_json: str | Path | None = None,
                         with_dpd: bool = False) -> tuple[TxChain, RxChain]:
    """Randomized-impairment chains, corrected either by loading a stored
    cal state (fast, reproducible handoff) or by running the sequence."""
    rng = np.random.default_rng(seed)
    txp = TxParams(bandwidth_hz=bandwidth_hz).randomize(rng)
    rxp = RxParams(bandwidth_hz=bandwidth_hz).randomize(rng)
    txp.lpf.fc_nominal_hz = bandwidth_hz / 2 * 1.3
    rxp.lpf.fc_nominal_hz = bandwidth_hz / 2 * 1.12
    tx = TxChain(txp, fs_hz)
    rx = RxChain(rxp, fs_hz)
    if cal_state_json is not None:
        tx_state, rx_state = load_cal_state(cal_state_json)
        tx.load_correction_state(tx_state)
        rx.load_correction_state(rx_state)
        # analog codes travel with the params, not the digital state:
        # rerun the two cheap analog searches
        from ..cal.lpf_corner import (calibrate_lpf_corner_rx,
                                      calibrate_lpf_corner_tx)
        calibrate_lpf_corner_tx(tx)
        calibrate_lpf_corner_rx(rx)
    else:
        os_ratio = max(2, int(round(fs_hz / bandwidth_hz)))
        cfg = OFDMConfig(bandwidth_hz=bandwidth_hz, qam_order=256,
                         n_symbols=4, oversampling=os_ratio)
        run_full_cal(tx, rx, cfg, LoopbackPath(atten_db=40.0, delay_ns=6.0),
                     with_dpd=with_dpd)
    return tx, rx


def run_handoff(wave: Waveform, tx: TxChain, rx: RxChain,
                scenario: str = "loopback",
                path: LoopbackPath | None = None) -> HandoffResult:
    if scenario not in SCENARIOS:
        raise ValueError(f"scenario 必须是 {SCENARIOS} 之一")
    issues = validate_waveform(wave)
    if issues:
        raise ValueError("波形校验未通过:\n- " + "\n- ".join(issues))
    if abs(wave.fs_hz - tx.fs) > 1e-3:
        raise ValueError(f"波形采样率 {wave.fs_hz} 与链路 {tx.fs} 不一致")
    if path is None:
        path = LoopbackPath(atten_db=40.0, delay_ns=6.0)
    x = np.asarray(wave.iq, dtype=complex)
    fs, bw = tx.fs, wave.bandwidth_hz
    metrics: dict = {}

    if scenario == "rx_only":
        if wave.scale != "sqrt_mw":
            raise ValueError("rx_only 场景要求 scale='sqrt_mw'(RX 输入节点)")
        rx.agc(power_dbm(x))
        out = rx(x, rng=np.random.default_rng(0))
        metrics["rx_in_dbm"] = power_dbm(x)
        metrics["digital_out_dbfs"] = power_dbm(out)
        out_scale = "digital_fs"
    else:
        if wave.scale != "digital_fs":
            raise ValueError(f"{scenario} 场景要求 scale='digital_fs'")
        nodes: dict = {}
        y_pa = tx(x, nodes=nodes)
        metrics.update({k: v for k, v in nodes.items()})
        if fs >= 3.0 * bw:
            ac = aclr(y_pa, fs, bw)
            metrics["aclr_worst_dbc"] = max(ac["lower_dbc"], ac["upper_dbc"])
        if scenario == "tx_only":
            out = y_pa
            out_scale = "sqrt_mw"
        else:
            agc_for_loopback(tx, rx, path, x)
            out = capture_aligned(tx, rx, path, x)
            g = np.vdot(x, out) / np.vdot(x, x)
            metrics["composite_gain_db"] = float(20 * np.log10(abs(g)))
            metrics["loopback_delay_ns"] = path.delay_ns
            out_scale = "digital_fs"

    return HandoffResult(
        output=Waveform(iq=out, fs_hz=fs, bandwidth_hz=bw, scale=out_scale,
                        description=f"wifitrx {scenario} output",
                        extra={"scenario": scenario}),
        metrics=metrics,
    )
