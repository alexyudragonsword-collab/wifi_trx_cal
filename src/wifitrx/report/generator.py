"""Chinese Markdown calibration report from a CalResult list.

Consumes the ordered output of ``cal.sequence.run_full_cal`` and writes
``cal_report.md`` plus PNG figures.  Report text is Chinese (project
convention); figure text stays English (matplotlib font limitation).
"""
from __future__ import annotations

from pathlib import Path

import numpy as np

from ..cal.base import CalResult
from . import figures

_PRINCIPLES = {
    "tx_lpf_corner": "在标称截止频率与低频参考处各注入单音,扫描 RC 调谐码,"
                     "通过包络检波器读出两音功率比,选择最接近 -3 dB 的码字。"
                     "RC 工艺偏差 ±20% 被压到 1 LSB 以内。",
    "rx_lpf_corner": "与 TX 同理,但经 ADC 读出音功率比。LPF corner 必须最先校准,"
                     "否则后续所有频域估计都会被通带畸变污染。",
    "rx_dc_offset": "端口端接(无输入)下按 AGC 增益档逐档平均 ADC 输出,"
                    "建立逐档数字 DC 消除表(LO 自混频 DC 随前端增益变化)。",
    "tx_lo_leak_envdet": "发单音,LO 泄漏与主音在平方律包络检波器中拍频于 f0;"
                         "拍频功率是数字 DC 预失调 (dc_pre) 的二次型,"
                         "对 I/Q 两轴做三点抛物线拟合迭代求最小值。不依赖 RX。",
    "tx_lo_leak_loopback": "RX LO 频偏 Δf 环回,TX 载波泄漏落在 -Δf bin(与 RX 残余 DC"
                           " 分离);注入已知数字 DC 导频测出传输增益后一步校正。",
    "loopback_delay": "整数互相关 + 抛物线插值分数延迟估计,为所有 FFT-bin 校准"
                      "提供捕获对齐。",
    "tx_iq": "正/负单边梳状音 + RX LO 偏移法:TX 音、TX 镜像、RX 镜像分别落在三个"
             "不同 bin;两次捕获在同一测量 bin 上取比值,环回/RX 线性响应精确抵消,"
             "得到逐频点 rho=G2/G1,设计 widely-linear 复 FIR (w2) 预校正。",
    "group_delay": "由 tx_iq 首轮测得的 rho(f) 虚部斜率提取 I/Q 群时延失配"
                   "(Im{rho} ~ pi*f*tau),与注入真值对照验证。",
    "rx_iq": "经已校 TX 的单边梳状音(共 LO、无偏移):W2(-f) = -Y(-f)/conj(Y(+f)),"
             "信源项完全抵消;后置 widely-linear 复 FIR 校正。",
    "tx_power": "OFDM 激励下扫描增益码,实测 PA 输出功率建立 码字->dBm 查找表,"
                "并插值命中目标功率。",
    "dpd": "间接学习 (ILA) 迭代:环回捕获对齐后以第 0 轮线性增益为固定目标增益,"
           "对 (capture/G0 -> 实际驱动 u) 拟合 GMP 后逆;观测路径使用宽带模式"
           "(RX LPF 旁路)。必须最后执行,否则残余损伤会被学进系数。",
    "agc_sweep": "全部校正生效后扫描输入功率,验证 LNA 档位切换、ADC 落点与 SNR。",
    "final_loopback_evm": "全链路验证:evm_db 为 TX+RX 复合环回 EVM;tx_evm_db 为"
                          " PA 输出处的 TX EVM(802.11be 规范测量点,MCS13 要求"
                          " <= -38 dB)。两者均为 per-tone 均衡 + CPE 去除。",
}


def _fmt(v) -> str:
    if isinstance(v, float):
        return f"{v:.2f}"
    if isinstance(v, np.floating):
        return f"{float(v):.2f}"
    if isinstance(v, np.ndarray):
        return "[" + ", ".join(f"{float(x):.1f}" for x in np.ravel(v)[:8]) + "]"
    return str(v)


def _figures_for(res: CalResult, figdir: Path, prefix: str) -> list[str]:
    paths = []

    def save(fig, name):
        p = figdir / f"{prefix}_{name}.png"
        fig.savefig(p, dpi=130)
        import matplotlib.pyplot as plt
        plt.close(fig)
        paths.append(p.name)

    if res.name in ("tx_lpf_corner", "rx_lpf_corner") and res.trace:
        save(figures.fig_code_sweep(res.trace, res.estimated.get("best_code", 0),
                                    f"{res.name}: RC code sweep"), "sweep")
    elif res.name in ("tx_lo_leak_envdet", "tx_lo_leak_loopback") and res.trace:
        save(figures.fig_convergence(res.trace, f"{res.name}: convergence",
                                     "LO leakage [dBc]"), "conv")
    elif res.name in ("tx_iq", "rx_iq"):
        if "irr_db" in res.metrics_before and "irr_db" in res.metrics_after:
            f = res.estimated.get("rho_f_hz")
            if f is None:
                f = res.estimated.get("w2_f_hz")
            n = len(res.metrics_before["irr_db"])
            fpos = np.sort(np.abs(np.asarray(f)))[-n:] if f is not None \
                else np.arange(n)
            save(figures.fig_irr_before_after(
                fpos, res.metrics_before["irr_db"], res.metrics_after["irr_db"],
                f"{res.name}: IRR before/after"), "irr")
        if res.trace:
            save(figures.fig_convergence(res.trace, f"{res.name}: worst IRR",
                                         "min IRR [dB]"), "conv")
    elif res.name == "tx_power" and res.trace:
        save(figures.fig_power_table(res.trace, "TX power vs gain code"), "table")
    elif res.name == "dpd" and res.trace:
        save(figures.fig_convergence(res.trace, "DPD: worst ACLR per iteration",
                                     "ACLR [dBc]"), "conv")
    elif res.name == "agc_sweep" and res.trace:
        save(figures.fig_agc_sweep(res.trace,
                                   res.estimated.get("target_adc_dbm", 0.0),
                                   "AGC sweep"), "sweep")
    elif res.name == "final_loopback_evm" and res.artifacts:
        sb = res.artifacts.get("snapshot_before")
        sa = res.artifacts.get("snapshot_after")
        if sb and sa:
            save(figures.fig_constellation_compare(sb, sa), "constellation")
            save(figures.fig_psd_compare(sb, sa), "psd")
    return paths


def generate_report(results: list[CalResult], out_dir: str | Path,
                    title: str = "WiFi 7 收发器校准报告",
                    fs_hz: float | None = None) -> Path:
    out = Path(out_dir)
    figdir = out / "figs"
    figdir.mkdir(parents=True, exist_ok=True)

    lines = [f"# {title}", ""]

    # ---- capture-time budget (when any step reports cost)
    if any(r.cost for r in results):
        lines += ["## 校准耗时预算(捕获时间)", "",
                  "| 步骤 | 捕获次数 | 样本数 | 捕获时间 (ms) |",
                  "|---|---|---|---|"]
        tot_c = tot_s = 0
        for r in results:
            if not r.cost:
                continue
            c = int(r.cost.get("captures", 0))
            s = int(r.cost.get("samples", 0))
            tot_c += c
            tot_s += s
            t = f"{s / fs_hz * 1e3:.2f}" if fs_hz else "—"
            lines.append(f"| {r.name} | {c} | {s:,} | {t} |")
        t_tot = f"{tot_s / fs_hz * 1e3:.2f}" if fs_hz else "—"
        lines += [f"| **合计** | {tot_c} | {tot_s:,} | {t_tot} |", "",
                  "> 捕获时间 = 样本数 / fs,不含 DSP 处理时间;"
                  "上电快速档 (profile='poweron') 用二分码搜索与短捕获压缩此预算。",
                  ""]

    # ---- summary table
    lines += ["## 校准结果汇总", "",
              "| 步骤 | 关键指标 | 校准前 | 校准后 | 通过 |",
              "|---|---|---|---|---|"]
    for r in results:
        key_b = next(iter(r.metrics_before.items()), ("-", "-"))
        key_a = next(iter(r.metrics_after.items()), ("-", "-"))
        ok = {True: "✅", False: "❌", None: "—"}[
            None if r.passed is None else bool(r.passed)]
        lines.append(f"| {r.name} | {key_a[0]} | {_fmt(key_b[1])} | "
                     f"{_fmt(key_a[1])} | {ok} |")
    lines.append("")

    # ---- per-step sections
    for i, r in enumerate(results):
        lines += [f"## {i + 1}. {r.name}", ""]
        principle = _PRINCIPLES.get(r.name)
        if principle:
            lines += [f"**原理**:{principle}", ""]
        if r.metrics_before or r.metrics_after:
            lines += ["| 指标 | 校准前 | 校准后 |", "|---|---|---|"]
            keys = list(dict.fromkeys(list(r.metrics_before) + list(r.metrics_after)))
            for k in keys:
                b = _fmt(r.metrics_before.get(k, "—"))
                a = _fmt(r.metrics_after.get(k, "—"))
                lines.append(f"| {k} | {b} | {a} |")
            lines.append("")
        if r.notes:
            lines += [f"> {r.notes}", ""]
        for name in _figures_for(r, figdir, f"{i + 1:02d}_{r.name}"):
            lines += [f"![{name}](figs/{name})", ""]

    path = out / "cal_report.md"
    path.write_text("\n".join(lines), encoding="utf-8")
    return path
