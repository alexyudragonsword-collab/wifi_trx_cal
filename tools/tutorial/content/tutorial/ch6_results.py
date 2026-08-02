"""Chapter 6: tracking, temperature, yield and the flagship numbers."""
from __future__ import annotations

import numpy as np

import figures
from model import Chapter, Fig, Section, T, Table


def _drift_values(ctx):
    m = ctx.drift_tracking["metrics"]
    return {"track_final": f"{m['evm_track_final_db']:.1f}",
            "gap": f"{m['track_vs_oracle_db']:.1f}",
            "frozen_worst": f"{m['evm_frozen_worst_db']:.1f}"}


def _temp_values(ctx):
    e = ctx.temp_study["expiry"]
    plan = e["recal_plan"]
    return {"hold_min": f"{e['hold_min_c']:.0f}",
            "hold_max": f"{e['hold_max_c']:.0f}",
            "recal_n": str(len(plan["steps"])),
            "recal_ms": f"{plan['capture_ms']:.1f}"}


def _temp_rows(ctx):
    return [[f"{r['temp_c']:.0f}", f"{r['lo_leak_dbc']:.1f}",
             f"{r['irr_min_db']:.1f}", f"{r['tx_evm_db']:.1f}",
             "✓" if r["all_hold"] else "✗"]
            for r in ctx.temp_study["rows"]]


def _sens_rows(ctx):
    return [[str(r["mcs"]), r["modulation"], f"{r['snr_req_db']:.1f}",
             f"{r['analytic_dbm']:.1f}", f"{r['measured_dbm']:.1f}",
             f"{r['delta_db']:+.1f}"]
            for r in ctx.sensitivity]


def _mc_values(ctx):
    evms = ctx.mc_yield["evms"]
    return {"mc_n": str(len(evms)),
            "mc_median": f"{float(np.median(evms)):.1f}",
            "mc_worst": f"{max(evms):.1f}"}


CHAPTER = Chapter(
    id="ch6", title=T("6 跟踪、温度与端到端结果", "6 Tracking, temperature and end-to-end results"),
    sections=(
        Section(
            id="res-drift",
            title=T("6.1 PA 热漂移跟踪(RLS DPD)", "6.1 PA thermal-drift tracking (RLS DPD)"),
            values=_drift_values,
            value_keys=("track_final", "gap", "frozen_worst"),
            body=(
                T("工厂校准的 DPD 在 PA 温漂下会过期。RLS 跟踪环在线更新 GMP "
                  "系数;关键参数是遗忘因子——这里的教训:每<em>块</em>更新而非"
                  "每样本,forget=0.995 级别的'常规'取值在块级更新下等于几乎"
                  "不遗忘,漂移后残留 20 dB 滞后;块级 forget=0.4 才跟得上。"
                  "本次运行:跟踪 DPD 收敛到 {track_final} dB,距逐状态重训"
                  "的 oracle 仅 {gap} dB,而冻结 DPD 最差劣化到 "
                  "{frozen_worst} dB。",
                  "A factory-calibrated DPD goes stale as the PA drifts "
                  "thermally. An RLS tracking loop updates the GMP "
                  "coefficients online; the critical knob is the "
                  "forgetting factor — the lesson here: updates are per "
                  "<em>block</em>, not per sample, so a 'textbook' "
                  "forget=0.995 barely forgets at block level and lags "
                  "drift by 20 dB; block-level forget=0.4 keeps up. This "
                  "run: tracking DPD converges to {track_final} dB, only "
                  "{gap} dB from the per-state retrained oracle, while the "
                  "frozen DPD degrades to {frozen_worst} dB at worst."),
                Fig(id="fig-drift", build=figures.drift_tracking,
                    caption=T("热漂移下:跟踪 vs 冻结 vs oracle",
                              "Under thermal drift: tracking vs frozen vs "
                              "oracle")),
            )),
        Section(
            id="res-temp",
            title=T("6.2 温度保持性与失效窗口", "6.2 Temperature hold and the validity window"),
            values=_temp_values,
            value_keys=("hold_min", "hold_max", "recal_n", "recal_ms"),
            body=(
                T("校正冻结在 25°C 值,扫温逐规格复测(判据用结果里<em>内嵌"
                  "的 spec</em>,与交付检查器同一条规则)。泄漏 null 是按校准"
                  "温度幅度配平的,温漂任一方向都会破坏它:",
                  "Corrections frozen at their 25 °C values, specs "
                  "re-measured across temperature (judged against the "
                  "specs <em>embedded in the results</em> — the same rule "
                  "the handoff inspector applies). The leak null is "
                  "amplitude-matched at the calibration temperature, so "
                  "drift in either direction breaks it:"),
                Table(header=(T("温度 [°C]", "T [°C]"),
                              T("LO 泄漏 [dBc]", "LO leak [dBc]"),
                              T("最差 IRR [dB]", "min IRR [dB]"),
                              T("TX EVM [dB]", "TX EVM [dB]"),
                              T("保持", "holds")),
                      rows_from=_temp_rows,
                      caption=T("保持性研究(构建时运行)",
                                "Hold study (run at build time)")),
                Fig(id="fig-temp", build=figures.temp_hold,
                    caption=T("泄漏与 IRR 随温度,虚线为内嵌 spec",
                              "Leak and IRR vs temperature; dashed = "
                              "embedded spec")),
                T("结论写进交付文件的 expiry 元数据:本次保持窗口 "
                  "{hold_min}…{hold_max} °C;越界后的最小重校子序列 "
                  "{recal_n} 步、约 {recal_ms} ms 捕获(由依赖闭包自动推导,"
                  "含测量前置步骤)。",
                  "The conclusion ships as expiry metadata in the "
                  "cal-state file: hold window {hold_min}…{hold_max} °C "
                  "this run; the minimal recal subsequence after leaving "
                  "it is {recal_n} steps / ~{recal_ms} ms of captures "
                  "(derived automatically as the dependency closure, "
                  "measurement prerequisites included)."),
            )),
        Section(
            id="res-sens", title=T("6.3 灵敏度:模型对拍解析预算",
                                   "6.3 Sensitivity: model vs analytic budget"),
            body=(
                T("同一个数,两条独立路径:Friis 解析底限 $P_{sens}=kT+"
                  "10\\log_{10}B+NF+SNR_{req}$,与行为模型实测(EVM 过 "
                  "$-SNR_{req}$ 交点)。二者一致校验的是整条噪声/单位/EVM "
                  "管线——这类交叉验证曾当场抓到 rx-only 路径漏掉群时延对齐"
                  "导致的 −28 dB EVM 地板。",
                  "One number, two independent routes: the analytic Friis "
                  "floor $P_{sens}=kT+10\\log_{10}B+NF+SNR_{req}$, and the "
                  "behavioral model's measurement (the input power where "
                  "EVM crosses $-SNR_{req}$). Their agreement validates "
                  "the whole noise/units/EVM plumbing — this exact "
                  "cross-check caught a −28 dB EVM floor from a missing "
                  "group-delay alignment in the rx-only path."),
                Table(header=(T("MCS", "MCS"), T("调制", "Mod"),
                              T("SNR需求 [dB]", "SNR req [dB]"),
                              T("解析 [dBm]", "analytic [dBm]"),
                              T("实测 [dBm]", "measured [dBm]"),
                              T("差 [dB]", "Δ [dB]")),
                      rows_from=_sens_rows,
                      caption=T("20 MHz 灵敏度对拍(SNR 列为预算近似值,"
                                "绝对值引用前需复核;两路径的差值才是"
                                "可信量)",
                                "20 MHz sensitivity cross-check (the SNR "
                                "column is a budgeting approximation — "
                                "verify before quoting absolutes; the "
                                "delta between the two routes is the "
                                "trustworthy quantity)")),
            )),
        Section(
            id="res-yield", title=T("6.4 工艺良率与旗舰结果",
                                    "6.4 Process yield and the flagship numbers"),
            values=_mc_values, value_keys=("mc_n", "mc_median", "mc_worst"),
            body=(
                T("小规模 Monte-Carlo({mc_n} 个随机工艺角,poweron 快速档):"
                  "校后环回 EVM 中位数 {mc_median} dB、最差 {mc_worst} dB。"
                  "完整良率门禁是 nightly 的 run_yield(20 角、全档),历史"
                  "结果 100% 通过全部限值。",
                  "A small Monte-Carlo ({mc_n} random process corners, "
                  "poweron profile): post-cal loopback EVM median "
                  "{mc_median} dB, worst {mc_worst} dB. The full yield "
                  "gate is the nightly run_yield (20 corners, factory "
                  "profile), historically 100% against every limit."),
                Fig(id="fig-mc", build=figures.mc_hist,
                    caption=T("校后 EVM 分布(构建时 Monte-Carlo)",
                              "Post-cal EVM distribution (build-time "
                              "Monte-Carlo)")),
                T("旗舰配置 320 MHz / 4096-QAM 的验收数字由测试套件断言"
                  "(tests/test_e2e.py::test_full_sequence_320mhz 及相关):"
                  "TX EVM ≤ −38 dB(802.11be MCS13),实测约 −39.8 dB,"
                  "真实电路数据导入路径约 −41.4 dB。本教程的构建配置(80 MHz)"
                  "为求速度,不替代上述验收值。",
                  "The flagship 320 MHz / 4096-QAM acceptance numbers are "
                  "asserted by the test suite "
                  "(tests/test_e2e.py::test_full_sequence_320mhz and "
                  "friends): TX EVM ≤ −38 dB (802.11be MCS13), measured "
                  "≈ −39.8 dB, and ≈ −41.4 dB on the circuit-data import "
                  "path. This tutorial's build config (80 MHz) trades "
                  "fidelity for speed and does not replace those "
                  "acceptance values."),
            )),
    ))
