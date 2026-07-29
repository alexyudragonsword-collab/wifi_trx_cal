"""Chapter 7: the four design insights the model produced."""
from __future__ import annotations

from model import Chapter, Section, T

CHAPTER = Chapter(
    id="ch7", title=T("7 设计洞察", "7 Design insights"),
    sections=(
        Section(
            id="insights", title=T("7.1 模型换来的四条电路结论", "7.1 Four circuit conclusions the model paid for"),
            body=(
                T("<b>① 4096-QAM 必须配低相噪综合器。</b>IPN ≈ −38 dBc 的 LO "
                  "单独就吃掉整个 −38 dB EVM 预算——CPE 去除救不了子载波间"
                  "相噪;需要 −43 dBc 量级(≈0.4° rms)。这是给 PLL 组的"
                  "硬指标,不是仿真参数偏好。",
                  "<b>① 4096-QAM demands a low-phase-noise synthesizer.</b> "
                  "An LO at IPN ≈ −38 dBc alone consumes the entire −38 dB "
                  "EVM budget — CPE removal does not rescue "
                  "inter-subcarrier phase noise; a −43 dBc class "
                  "(≈0.4° rms) is required. A hard requirement for the PLL "
                  "team, not a simulation preference."),
                T("<b>② 320 MHz 模式的 TX 基带 LPF 必须比信道宽"
                  "(≥1.3×BW/2)。</b>DPD 预失真频谱比信号宽;corner 贴着"
                  "信道边沿会把校正剥掉,PA 残余 EVM 卡在 −39 dB 附近,"
                  "怎么加迭代都无用。滤波器规格要为 DPD 留带宽。",
                  "<b>② The 320 MHz-mode TX baseband LPF must be wider "
                  "than the channel (≥1.3×BW/2).</b> The predistorted "
                  "spectrum is wider than the signal; a corner hugging the "
                  "channel edge strips the correction and pins residual "
                  "PA EVM near −39 dB no matter how many iterations run. "
                  "Spec the filter for DPD bandwidth."),
                T("<b>③ IIP2 校准必须排在 LO 泄漏校准之后。</b>PA 三阶积 "
                  "$f_2\\times leak\\times f_1^*$ 正落在 IM2 测量 bin,"
                  "未校泄漏埋掉 null ~35 dB。这是校准<em>顺序</em>由电路"
                  "机理决定的最典型例子。",
                  "<b>③ The IIP2 cal must follow the LO-leak cal.</b> The "
                  "PA product $f_2\\times leak\\times f_1^*$ lands exactly "
                  "on the IM2 measurement bin; an uncalibrated leak buries "
                  "the null by ~35 dB. The clearest case of calibration "
                  "<em>order</em> being dictated by circuit mechanism."),
                T("<b>④ 跟踪环的遗忘因子按块不按样本。</b>RLS 每块更新一次时,"
                  "forget=0.995 意味着几乎永不遗忘,PA 漂移后残留 20 dB 滞后;"
                  "块级 forget=0.4 才是同一物理时间常数的正确换算。",
                  "<b>④ Tracking-loop forgetting factors are per block, "
                  "not per sample.</b> With one RLS update per block, "
                  "forget=0.995 means almost never forgetting — 20 dB of "
                  "lag after PA drift; block-level forget=0.4 is the same "
                  "physical time constant correctly rescaled."),
            )),
    ))
