"""Standardized waveform exchange format: wifitrx-wave-v1.

One ``.npz`` file per waveform:

* ``iq``       — complex 1-D baseband samples
* ``meta``     — JSON string: {format, fs_hz, bandwidth_hz, scale,
                 description, extra...}

``scale`` declares the amplitude convention (see docs/units.md):
* ``"digital_fs"`` — full-scale digital units (|I|,|Q| <= 1); what the
  comm team's PHY hands to the TX chain;
* ``"sqrt_mw"``    — physical sqrt(mW) (PA output / RX input nodes).

Validation returns human-readable Chinese issue strings so waveform
problems surface on the producer's side instead of as mystery EVM.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

FORMAT = "wifitrx-wave-v1"
SCALES = ("digital_fs", "sqrt_mw")


@dataclass
class Waveform:
    iq: np.ndarray
    fs_hz: float
    bandwidth_hz: float
    scale: str = "digital_fs"
    description: str = ""
    extra: dict = field(default_factory=dict)


def save_waveform(path: str | Path, wave: Waveform) -> Path:
    meta = {"format": FORMAT, "fs_hz": wave.fs_hz,
            "bandwidth_hz": wave.bandwidth_hz, "scale": wave.scale,
            "description": wave.description, **wave.extra}
    p = Path(path)
    np.savez_compressed(p, iq=np.asarray(wave.iq, dtype=np.complex128),
                        meta=json.dumps(meta))
    return p if p.suffix == ".npz" else p.with_suffix(p.suffix + ".npz")


def load_waveform(path: str | Path) -> Waveform:
    with np.load(path, allow_pickle=False) as d:
        if "iq" not in d or "meta" not in d:
            raise ValueError(f"{path}: 不是 wifitrx-wave 文件(缺少 iq/meta)")
        meta = json.loads(str(d["meta"]))
        iq = np.asarray(d["iq"])
    if meta.get("format") != FORMAT:
        raise ValueError(f"{path}: 未知格式 {meta.get('format')!r},"
                         f"期望 {FORMAT}")
    known = {"format", "fs_hz", "bandwidth_hz", "scale", "description"}
    return Waveform(iq=iq, fs_hz=float(meta["fs_hz"]),
                    bandwidth_hz=float(meta["bandwidth_hz"]),
                    scale=str(meta.get("scale", "digital_fs")),
                    description=str(meta.get("description", "")),
                    extra={k: v for k, v in meta.items() if k not in known})


def validate_waveform(wave: Waveform) -> list[str]:
    """Returns a list of issues; empty list = valid."""
    issues: list[str] = []
    iq = np.asarray(wave.iq)
    if iq.ndim != 1:
        issues.append(f"iq 必须是一维数组(当前 {iq.ndim} 维)")
    if not np.iscomplexobj(iq):
        issues.append("iq 必须是复数数组(complex64/complex128)")
    if iq.size < 1024:
        issues.append(f"样本数过少({iq.size} < 1024),指标测量不可靠")
    if iq.size and not np.all(np.isfinite(iq)):
        issues.append("iq 含 NaN/Inf")
    if wave.scale not in SCALES:
        issues.append(f"scale 必须是 {SCALES} 之一(当前 {wave.scale!r})")
    if wave.fs_hz <= 0 or wave.bandwidth_hz <= 0:
        issues.append("fs_hz / bandwidth_hz 必须为正")
    else:
        ratio = wave.fs_hz / wave.bandwidth_hz
        if ratio < 2.0:
            issues.append(f"fs/bandwidth = {ratio:.2f} < 2,欠采样")
        if abs(ratio - round(ratio)) > 1e-6:
            issues.append(f"fs/bandwidth = {ratio:.4f} 不是整数倍,"
                          "OFDM 网格将不对齐(建议 2 或 4 倍)")
    if (wave.scale == "digital_fs" and iq.size
            and np.isfinite(iq).all()):
        peak = float(np.max(np.abs(np.concatenate([iq.real, iq.imag]))))
        if peak > 1.0 + 1e-9:
            issues.append(f"digital_fs 波形超满量程(峰值 {peak:.3f} > 1),"
                          "DAC 将削顶")
        rms = float(np.sqrt(np.mean(np.abs(iq) ** 2)))
        if rms > 0.3:
            issues.append(f"digital_fs 波形 rms={rms:.2f} 过高,"
                          "PAPR 余量不足(建议 0.10–0.15)")
    return issues
