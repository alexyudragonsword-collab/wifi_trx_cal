"""Directory-level handoff regression: waves/*.npz -> reconciliation report.

Each waveform in the directory runs through the same calibrated chains;
the Markdown report lists our metrics with an empty column for the comm
team's demod-side numbers — the shared reconciliation sheet.
"""
from __future__ import annotations

from pathlib import Path

from ..chain import RxChain, TxChain
from .runner import HandoffResult, run_handoff
from .waveform_io import load_waveform, save_waveform

_COLUMNS = ("pa_out_dbm", "pa_avg_pae", "aclr_worst_dbc",
            "composite_gain_db", "digital_out_dbfs")


def run_regression(wave_dir: str | Path, tx: TxChain, rx: RxChain,
                   out_dir: str | Path, scenario: str = "loopback") -> Path:
    wave_dir = Path(wave_dir)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    files = sorted(wave_dir.glob("*.npz"))
    if not files:
        raise FileNotFoundError(f"{wave_dir} 下没有 .npz 波形文件")

    lines = ["# 联合验证指标对账单", "",
             f"场景:{scenario};波形目录:`{wave_dir}`", "",
             "| 波形 | " + " | ".join(_COLUMNS)
             + " | 通信侧 EVM (dB) | 通信侧误码 | 备注 |",
             "|" + "---|" * (len(_COLUMNS) + 4)]
    for f in files:
        try:
            wave = load_waveform(f)
            res: HandoffResult = run_handoff(wave, tx, rx, scenario=scenario)
            save_waveform(out_dir / f"{f.stem}_out.npz", res.output)
            vals = []
            for c in _COLUMNS:
                v = res.metrics.get(c)
                vals.append(f"{v:.2f}" if isinstance(v, float) else "—")
            lines.append(f"| {f.name} | " + " | ".join(vals)
                         + " |  |  |  |")
        except (ValueError, KeyError) as e:
            lines.append(f"| {f.name} | " + "— | " * len(_COLUMNS)
                         + f" |  |  | 失败: {e} |")
    report = out_dir / "handoff_report.md"
    report.write_text("\n".join(lines), encoding="utf-8")
    return report
