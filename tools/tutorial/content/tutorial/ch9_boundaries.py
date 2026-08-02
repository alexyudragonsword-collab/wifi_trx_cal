"""Chapter 9: known simplifications and model boundaries."""
from __future__ import annotations

from model import Chapter, Section, T

CHAPTER = Chapter(
    id="ch9", title=T("9 已知简化与边界", "9 Known simplifications and boundaries"),
    sections=(
        Section(
            id="bounds",
            title=T("9.1 模型明确不覆盖什么", "9.1 What the model deliberately does not cover"),
            body=(
                T("诚实的边界清单,引用前请核对:"
                  "① DAC/ADC 镜像与 replica 不建模(单一仿真采样率;ZOH droop "
                  "可选);② 无信道编码与完整 802.11be 帧——PER 级链路验证属于"
                  "通信组的 PHY,本模型提供简化 preamble/pilot 供对拍;"
                  "③ PA 默认无记忆 Saleh,记忆效应用 ReferencePA/导入数据启用;"
                  "④ RX 谐波混频、镜像抑制混频器结构未建模;"
                  "⑤ MIMO 解耦按平坦耦合矩阵处理(频变互耦留待后续);"
                  "⑥ PLL 内部校准(VCO band select、KVCO 等)不在范围——"
                  "对系统层可见的是相噪剖面 + 杂散 + 锁定时间,这三者已覆盖;"
                  "⑦ 灵敏度的 SNR 需求列是预算近似,未经译码仿真复核;"
                  "⑧ 模拟基带的噪声与压缩默认合并在逐档 NF/IIP3 里,显式建模"
                  "(`RxParams.baseband`)要先 de-embed 档位表,且其默认参数"
                  "(6 nV/√Hz、1.0 Vpp)是为与现表自洽而推导的占位值,不是电路数据。",
                  "The honest boundary list — check before quoting: "
                  "① DAC/ADC images and replicas are not modeled (single "
                  "simulation rate; optional ZOH droop); ② no channel "
                  "coding or full 802.11be framing — PER-level link "
                  "validation belongs to the comm team's PHY, and the "
                  "model provides simplified preamble/pilots for "
                  "cross-checks; ③ the PA defaults to memoryless Saleh; "
                  "memory effects come via ReferencePA or imported data; "
                  "④ RX harmonic mixing and image-reject mixer topologies "
                  "are not modeled; ⑤ MIMO decoupling assumes a flat "
                  "coupling matrix (frequency-dependent coupling is future "
                  "work); ⑥ PLL-internal calibrations (VCO band select, "
                  "KVCO…) are out of scope — what the system sees is the "
                  "phase-noise profile, spurs and lock time, all covered; "
                  "⑦ the sensitivity table's SNR-requirement column is a "
                  "budgeting approximation, not verified by coded "
                  "simulation."),
                T("简化是声明出来的,不是藏起来的:每一条都对应源码里的"
                  "开关或文档标注,交付对象可以据此判断哪些结论能直接引用、"
                  "哪些需要自己的仿真补验。",
                  "Simplifications are declared, not hidden: each maps to "
                  "a switch or a documented annotation in the source, so "
                  "a recipient can tell which conclusions to quote "
                  "directly and which to re-verify with their own "
                  "simulations."),
            )),
    ))
