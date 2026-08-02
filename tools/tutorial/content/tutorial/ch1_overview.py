"""Chapter 1: transceiver architecture and the modeling approach."""
from __future__ import annotations

import figures
import schematics
from model import Chapter, Diagram, F, Fig, Section, T, Table


def _impairment_rows(ctx):
    return [[r["case"], f"{r['evm_db']:.1f}", f"{r['aclr_dbc']:.1f}"]
            for r in ctx.impairment_study["rows"]]


def _overview_values(ctx):
    rows = {r["case"]: r for r in ctx.impairment_study["rows"]}
    return {
        "evm_clean": f"{rows['clean']['evm_db']:.1f}",
        "evm_txiq": f"{rows['tx_iq_imbalance']['evm_db']:.1f}",
        "evm_leak": f"{rows['tx_lo_leak']['evm_db']:.1f}",
    }


CHAPTER = Chapter(
    id="ch1", title=T("1 收发器架构与建模方法",
                      "1 Transceiver architecture and modeling approach"),
    sections=(
        Section(
            id="arch",
            title=T("1.1 直接变频 IQ 收发器", "1.1 The direct-conversion IQ transceiver"),
            body=(
                T("本教程围绕一颗 CMOS WiFi 7 收发器展开:TX 与 RX 均为直接变频"
                  "(zero-IF)IQ 结构,信道带宽最高 320 MHz,TX 采用模拟 PA"
                  "(P<sub>sat</sub> = 28 dBm,PAE@P<sub>sat</sub> = 35%),"
                  "频率综合由 fractional-N PLL 完成。下图是本模型覆盖的信号链:"
                  "上排为发射链,下排为接收链,中间是共用的 LO/PLL,右侧耦合器"
                  "引出两条<em>片上观测路径</em>——环回衰减路与包络检波路,"
                  "它们是所有校准算法的眼睛。",
                  "This tutorial is built around a CMOS WiFi 7 transceiver: "
                  "direct-conversion (zero-IF) IQ on both TX and RX, channel "
                  "bandwidth up to 320 MHz, an analog PA (P<sub>sat</sub> = "
                  "28 dBm, PAE at P<sub>sat</sub> = 35%), and a fractional-N "
                  "PLL for frequency synthesis. The figure shows the signal "
                  "chain the model covers: TX on top, RX below, the shared "
                  "LO/PLL in between, and — off the output coupler — the two "
                  "<em>on-chip observation paths</em> (loopback attenuator "
                  "and envelope detector) that every calibration algorithm "
                  "sees the chip through."),
                Diagram(id="dg-arch", build=schematics.architecture,
                        caption=T("直接变频收发器与两条观测路径",
                                  "Direct-conversion transceiver with both "
                                  "observation paths")),
                T("为什么直接变频需要大量校准?因为它把对器件匹配的要求换成了"
                  "对<em>校准</em>的要求:I/Q 两条模拟通路的任何失配都直接变成"
                  "镜像;LO 与 RF 端口的任何耦合都直接落在信道中央;"
                  "基带滤波器的工艺偏差直接畸变信号频谱。窄带系统里这些是"
                  "二阶效应,到了 320 MHz / 4096-QAM(EVM 要求 −38 dB,即误差"
                  "矢量幅度 1.26%),它们每一项都足以单独超掉整个误差预算。",
                  "Why does direct conversion need so much calibration? "
                  "Because it trades component-matching requirements for "
                  "<em>calibration</em> requirements: any mismatch between "
                  "the I and Q analog rails becomes image leakage; any "
                  "coupling between the LO and RF ports lands dead-center in "
                  "the channel; any process error in the baseband filters "
                  "distorts the signal spectrum directly. In narrowband "
                  "systems these are second-order effects — at 320 MHz / "
                  "4096-QAM (TX EVM spec −38 dB, an error vector of 1.26%) "
                  "each one alone can blow the entire error budget."),
            )),
        Section(
            id="baseband",
            title=T("1.2 复基带等效建模", "1.2 Complex-baseband equivalent modeling"),
            body=(
                T("模型不在射频载波上仿真。载频 6 GHz 下直接仿 RF 需要 >12 GHz "
                  "采样率,而所有我们关心的物理量(失配、泄漏、非线性、相噪)在"
                  "<em>复基带等效</em>下都有精确表示:实信号 "
                  "$x_{RF}(t)=\\mathrm{Re}[x(t)e^{j2\\pi f_c t}]$ 中的复包络 "
                  "$x(t)$ 就是仿真变量,采样率只需覆盖信道带宽的少数倍"
                  "($f_s = \\mathrm{BW}\\times o$,DPD 场景 $o=4$)。",
                  "The model does not simulate the RF carrier. At a 6 GHz "
                  "carrier a true RF simulation needs >12 GHz sampling, yet "
                  "every quantity we care about (mismatch, leakage, "
                  "nonlinearity, phase noise) has an exact representation in "
                  "the <em>complex-baseband equivalent</em>: for the real "
                  "signal $x_{RF}(t)=\\mathrm{Re}[x(t)e^{j2\\pi f_c t}]$ the "
                  "complex envelope $x(t)$ is the simulation variable, and "
                  "the sample rate only needs a small multiple of the channel "
                  "bandwidth ($f_s = \\mathrm{BW}\\times o$, with $o=4$ for "
                  "DPD scenarios)."),
                T("镜像、LO 泄漏这些'射频现象'在复基带下的形态:实系数处理"
                  "对 $x$ 与共轭 $x^*$ 作用相同,任何 I/Q 失配都表现为输出中"
                  "混入 $x^*$ 的分量(频谱上翻转到 $-f$,即镜像);LO 泄漏则是"
                  "叠加在基带上的复常数(DC)。这就是第 4 章所有 IQ/泄漏校准"
                  "在 FFT bin 上做文章的原因。",
                  "What 'RF phenomena' look like at complex baseband: real-"
                  "coefficient processing acts identically on $x$ and its "
                  "conjugate $x^*$, so any I/Q mismatch shows up as an "
                  "$x^*$ component in the output (spectrally mirrored to "
                  "$-f$ — the image), and LO leakage is a complex constant "
                  "(DC) added at baseband. This is why every IQ/leakage "
                  "calibration in chapter 4 works on FFT bins."),
            )),
        Section(
            id="why-cal",
            title=T("1.3 为什么必须校准:损伤逐项点名",
                    "1.3 Why calibrate: naming each impairment's cost"),
            values=_overview_values,
            value_keys=("evm_clean", "evm_txiq", "evm_leak"),
            body=(
                T("下面的实验每次只打开一种损伤,其余全部关闭,让同一帧 "
                  "1024-QAM OFDM 过 TX→环回→RX,测每种损伤单独的 EVM/ACLR "
                  "代价(本页所有数字都由构建脚本现场运行得到)。干净链路 EVM "
                  "为 {evm_clean} dB;仅注入典型 TX IQ 失衡就恶化到 "
                  "{evm_txiq} dB,仅 −28 dBm 的 LO 泄漏就是 {evm_leak} dB——"
                  "对照 4096-QAM 需要的 −38 dB,校准不是锦上添花,而是"
                  "各项损伤从'不可用'到'达标'的必经之路。",
                  "The experiment below turns on one impairment at a time "
                  "(everything else off) and passes the same 1024-QAM OFDM "
                  "frame through TX → loopback → RX, measuring each "
                  "impairment's isolated EVM/ACLR cost (every number on this "
                  "page was produced by the build script running the model). "
                  "The clean chain reads {evm_clean} dB EVM; typical TX IQ "
                  "imbalance alone degrades it to {evm_txiq} dB, and a "
                  "−28 dBm LO leak alone to {evm_leak} dB — against the "
                  "−38 dB that 4096-QAM demands, calibration is not polish, "
                  "it is the only route from 'unusable' to 'in spec'."),
                Table(header=(T("损伤(单独开启)", "Impairment (alone)"),
                              T("EVM [dB]", "EVM [dB]"),
                              T("最差 ACLR [dBc]", "worst ACLR [dBc]")),
                      rows_from=_impairment_rows,
                      caption=T("单损伤研究:80 MHz / 1024-QAM,构建时运行",
                                "Single-impairment study: 80 MHz / "
                                "1024-QAM, run at build time")),
                Fig(id="fig-imp-psd", build=figures.impairment_psd,
                    caption=T("各损伤单独开启时的 PA 输出频谱",
                              "PA-output spectra with each impairment "
                              "enabled alone")),
                T("EVM 预算的合成方式是各独立误差项的功率和(RSS):",
                  "Independent error contributions combine as a "
                  "root-sum-square (RSS) of error powers:"),
                F(r"\mathrm{EVM}^2_{total}=\sum_k \mathrm{EVM}^2_k"
                  r"\qquad \mathrm{EVM}_{dB}=10\log_{10}\mathrm{EVM}^2"),
                T("−38 dB 的总预算折算成线性误差功率后,留给每一项的空间都很小:"
                  "这就是 §7 设计洞察里'低相噪综合器不可妥协'等结论的来源。",
                  "Converted to linear error power, a −38 dB total budget "
                  "leaves little room for any single term — the origin of "
                  "the design insights in §7, such as the non-negotiable "
                  "low-phase-noise synthesizer."),
            )),
    ))
