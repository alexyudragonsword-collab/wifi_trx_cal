"""Chapter 3: the impairment models (physics -> math -> injected truth)."""
from __future__ import annotations

import figures
from model import Chapter, F, Fig, Section, T

CHAPTER = Chapter(
    id="ch3", title=T("3 损伤模型", "3 Impairment models"),
    sections=(
        Section(
            id="imp-iq", title=T("3.1 频变 IQ 失衡", "3.1 Frequency-dependent IQ imbalance"),
            body=(
                T("物理来源:I/Q 两条模拟轨(DAC→LPF→VGA 各自一份)不可能完全"
                  "一致——直流增益差、相位正交误差之外,宽带下两轨的<em>频响</em>"
                  "也有差异(纹波、群时延失配)。模型采用双实轨结构:两条实 FIR "
                  "$h_i, h_q$ 各自滤波 I、Q,再经带增益/相位误差的正交合成:",
                  "Physics: the I and Q analog rails (each its own "
                  "DAC→LPF→VGA) can never match exactly — beyond DC gain "
                  "and quadrature phase error, at wide bandwidth the two "
                  "rails' <em>frequency responses</em> differ too (ripple, "
                  "group-delay mismatch). The model uses a dual-real-rail "
                  "structure: real FIRs $h_i, h_q$ filter I and Q "
                  "separately, then the quadrature combiner adds gain and "
                  "phase error:"),
                F(r"y = g_i e^{+j\varphi/2}\,(h_i * I) \;+\; "
                  r"j\, g_q e^{-j\varphi/2}\,(h_q * Q)"),
                T("以 $I=(x+x^*)/2$、$Q=-j(x-x^*)/2$ 代入,任何这样的失衡都"
                  "化为 <em>widely-linear</em> 形式——输出同时含 $x$ 与共轭 "
                  "$x^*$ 两条通路:",
                  "Substituting $I=(x+x^*)/2$, $Q=-j(x-x^*)/2$, any such "
                  "imbalance reduces to the <em>widely-linear</em> form — "
                  "the output carries both $x$ and its conjugate $x^*$:"),
                F(r"Y(f) = G_1(f)\,X(f) + G_2(f)\,X^{*}(-f)"),
                F(r"G_{1,2}(f)=\frac{1}{2}\left[g_i e^{+j\varphi/2}H_i(f) "
                  r"\pm g_q e^{-j\varphi/2}H_q(f)\right]"),
                T("$+f$ 处的单音经 $G_2$ 在 $-f$ 处生成镜像,镜像抑制比因此是"
                  "逐频点的解析真值:",
                  "A tone at $+f$ produces its image at $-f$ through "
                  "$G_2$; the image rejection ratio is therefore an "
                  "analytic, per-frequency ground truth:"),
                F(r"\mathrm{IRR}(f)=20\log_{10}"
                  r"\left|\frac{G_1(f)}{G_2(-f)}\right|"),
                Fig(id="fig-irr-inj", build=figures.irr_injected,
                    caption=T("典型注入失衡的解析 IRR(f):频变结构正是宽带"
                              "校准必须用 FIR 而非单系数的原因",
                              "Analytic IRR(f) of a typical injected "
                              "imbalance: the frequency dependence is why "
                              "wideband correction needs an FIR, not one "
                              "coefficient")),
                T("注意镜像抑制的频率约定:$+f$ 音的镜像强度由 $G_2(-f)$ 决定"
                  "而不是 $G_2(+f)$——这个符号在开发早期错过一次,由注入真值"
                  "对拍测试当场抓获,此后所有 IRR 相关代码都以上式为准。",
                  "Mind the frequency convention: the image of a $+f$ tone "
                  "is set by $G_2(-f)$, not $G_2(+f)$ — this sign was got "
                  "wrong once early in development and caught immediately "
                  "by the injected-truth tests; every IRR formula since "
                  "follows the definition above."),
            )),
        Section(
            id="imp-lo", title=T("3.2 LO 泄漏与相位噪声", "3.2 LO leakage and phase noise"),
            body=(
                T("<b>LO 泄漏</b>:LO 向调制器 RF 端口的馈通,复基带下是叠加的"
                  "复常数,功率由 lo_leak_dbm 指定(绝对 dBm,默认随机 −32…−22),"
                  "相位任意。它落在信道正中央,既是频谱杂散又直接吃 EVM。",
                  "<b>LO leakage</b>: LO feedthrough to the modulator RF "
                  "port — at complex baseband an added complex constant "
                  "whose power is lo_leak_dbm (absolute dBm, randomized "
                  "−32…−22 by default) at arbitrary phase. It lands "
                  "dead-center in the channel: a spur and an EVM cost at "
                  "once."),
                T("<b>相位噪声</b>:LO 的相位抖动 $\\varphi(t)$ 乘性作用于信号 "
                  "$x\\,e^{j\\varphi(t)}$。谱由分段折线 $L(f)$ 描述(环内平台、"
                  "环路峰化、VCO 滚降),时域合成用 FFT 域整形高斯噪声。默认剖面"
                  "是 4096-QAM 真正需要的低相噪综合器级别:",
                  "<b>Phase noise</b>: LO phase jitter $\\varphi(t)$ acts "
                  "multiplicatively, $x\\,e^{j\\varphi(t)}$. The spectrum "
                  "is a piecewise profile $L(f)$ (in-band plateau, loop "
                  "peaking, VCO roll-off), synthesized by FFT-domain "
                  "shaping of Gaussian noise. The default profile is the "
                  "low-phase-noise synthesizer class 4096-QAM genuinely "
                  "requires:"),
                Fig(id="fig-pn", build=figures.pn_profile,
                    caption=T("默认 WiFi 7 综合器相噪剖面(构建时由模型计算"
                              "IPN)", "Default WiFi 7 synthesizer profile "
                              "(IPN computed by the model at build time)")),
                T("<b>frac-N 杂散</b>:小数分频的调制器残差是周期的,DTC 量化与 "
                  "INL 把它变成确定性单音,归一频率 $\\nu_k=(k\\cdot"
                  "\\mathrm{frac})\\ \\mathrm{mod}\\ 1$,近整数信道最差(拍频落进环路带宽内)。"
                  "杂散规划器据此扫信道网格标记'脏信道'。",
                  "<b>Fractional-N spurs</b>: the fractional divider's "
                  "modulator residual is periodic; DTC quantization and INL "
                  "turn it into deterministic tones at normalized "
                  "frequencies $\\nu_k=(k\\cdot\\mathrm{frac})\\ \\mathrm{mod}\\ 1$ — "
                  "worst on near-integer channels where the beat falls "
                  "inside the loop bandwidth. The spur planner sweeps the "
                  "channel grid and flags the dirty ones."),
            )),
        Section(
            id="imp-lpf", title=T("3.3 基带 LPF 与温漂", "3.3 Baseband LPF and temperature drift"),
            body=(
                T("信道选择 LPF 的绝对 RC 乘积随工艺漂移 ±20%,片上用电容阵列"
                  "调谐码补偿。模型:",
                  "The channel-select LPF's absolute RC product drifts "
                  "±20% with process; on-chip a capacitor-bank code trims "
                  "it back. The model:"),
                F(r"f_c = f_{c,nom}\,\frac{(1+\epsilon_{RC})"
                  r"\,(1+\alpha_{RC}\,\Delta T)}{1+s\,(code-code_{mid})}"),
                T("其中 $\\epsilon_{RC}$ 是工艺误差、$s$ 是每 LSB 的相对步进"
                  "(默认 2%)、$\\alpha_{RC}$ 是温度系数。滤波器本体是 5 阶 "
                  "Butterworth(可选 Chebyshev),因果 IIR 实现——它的群时延和"
                  "启动瞬态都是真实的,第 4 章的捕获对齐要为此买单。",
                  "with process error $\\epsilon_{RC}$, per-LSB fractional "
                  "step $s$ (2% default) and tempco $\\alpha_{RC}$. The "
                  "filter itself is a causal 5th-order Butterworth "
                  "(optionally Chebyshev) IIR — its group delay and "
                  "startup transient are real, and chapter 4's capture "
                  "alignment pays for them."),
                T("corner 的选取随模式而变:宽带模式为 DPD 带宽收紧"
                  "(≥1.3×BW/2,洞察②),窄带模式放宽到 3×——fs≫BW 时"
                  "抗混叠零成本,而更宽的 corner 缩短振铃相对固定 0.8 µs "
                  "GI 的占比,把 20 MHz 的 TX LPF 单项 ISI 地板从 −55 "
                  "压到 −76 dB(洞察⑤;测这个地板本身还揪出过两层时延"
                  "补偿伪影,见洞察⑥)。库里 "
                  "<code>recommended_lpf_corner_hz()</code> 封装了这条"
                  "策略。",
                  "The corner choice flips with mode: wide modes tighten "
                  "it for DPD bandwidth (≥1.3×BW/2, insight ②), narrow "
                  "modes relax it to 3× — with fs≫BW anti-aliasing costs "
                  "nothing, and a wider corner shrinks the ringing "
                  "relative to the fixed 0.8 µs GI, deepening the 20 MHz "
                  "TX LPF-only ISI floor from −55 to −76 dB (insight ⑤; "
                  "measuring that floor also flushed out two layers of "
                  "delay-compensation artifact, see insight ⑥). "
                  "<code>recommended_lpf_corner_hz()</code> encodes the "
                  "policy."),
            )),
        Section(
            id="imp-pa", title=T("3.4 PA 非线性", "3.4 PA nonlinearity"),
            body=(
                T("默认无记忆 Saleh 模型,AM/AM 与 AM/PM:",
                  "The default is the memoryless Saleh model, AM/AM and "
                  "AM/PM:"),
                F(r"A(r)=\frac{\alpha_a r}{1+\beta_a r^2},\qquad "
                  r"\Phi(r)=\frac{\alpha_p r^2}{1+\beta_p r^2}"),
                T("经 ScaledPA 包装成指定增益(26 dB)与 P<sub>sat</sub>"
                  "(28 dBm)。可切换 Wiener-Hammerstein 记忆 PA(ReferencePA)"
                  "或从谐波平衡仿真 CSV 导入实测 AM/AM。DPD 学习的广义记忆多项式"
                  "(GMP)基函数:",
                  "wrapped by ScaledPA to the specified gain (26 dB) and "
                  "P<sub>sat</sub> (28 dBm). A Wiener-Hammerstein memory PA "
                  "(ReferencePA) or a measured AM/AM imported from "
                  "harmonic-balance CSV can be swapped in. The generalized "
                  "memory polynomial (GMP) the DPD learns uses basis "
                  "terms:"),
                F(r"u(n)=\sum_{k,m} a_{km}\, x(n-m)\,|x(n-m)|^{k-1} + "
                  r"\mathrm{lag/lead\ cross\ terms}"),
                Fig(id="fig-amam", build=figures.pa_amam,
                    caption=T("默认 PA 的 AM/AM 与 AM/PM(构建时扫描)",
                              "Default PA AM/AM and AM/PM (swept at build "
                              "time)")),
            )),
        Section(
            id="imp-rx", title=T("3.5 接收机损伤", "3.5 Receiver impairments"),
            body=(
                T("<b>LNA/AGC</b>:四档前端增益态,每档有各自的增益/NF/IIP3/"
                  "切换门限;热噪声按当前档的 NF 在输入端注入。<b>三阶非线性</b>"
                  "按档位 IIP3 建模 $y \\rightarrow y - x|x|^2/\\mathrm{iip3_{mW}}$;"
                  "<b>二阶失真(IM2)</b>是直接变频的特有问题:混频器失配让包络"
                  "平方项 $|x|^2$ 漏到基带,IIP2 依赖片上 trim 码,最优码随工艺"
                  "随机。<b>DC 偏置</b>:LO 自混频,逐档不同。<b>ADC/DAC</b>:"
                  "量化 + 满量程边界 + 可选孔径抖动。<b>时钟</b>:CFO 与采样钟"
                  "偏差(SCO)同源(同一晶振 ppm)。",
                  "<b>LNA/AGC</b>: four front-end gain states, each with "
                  "its own gain/NF/IIP3/handover threshold; thermal noise "
                  "enters at the input per the active state's NF. "
                  "<b>Third-order nonlinearity</b> per-state, "
                  "$y \\rightarrow y - x|x|^2/\\mathrm{iip3_{mW}}$; <b>second-order "
                  "distortion (IM2)</b> is direct conversion's signature "
                  "problem: mixer mismatch leaks the squared envelope "
                  "$|x|^2$ to baseband, and the effective IIP2 depends on "
                  "an on-chip trim code whose optimum is a random process "
                  "variable. <b>DC offsets</b>: LO self-mixing, different "
                  "per gain state. <b>ADC/DAC</b>: quantization, the "
                  "full-scale boundary, optional aperture jitter. "
                  "<b>Clock</b>: CFO and sampling-clock offset (SCO) share "
                  "one crystal ppm."),
                T("每个损伤块都有 enabled 开关和 injected() 真值接口——校准"
                  "算法的每个估计量都能和注入值对拍,这是整个测试体系的地基"
                  "(inject → estimate → correct → verify)。",
                  "Every impairment block has an enabled switch and an "
                  "injected() ground-truth interface — every quantity a "
                  "calibration estimates can be checked against what was "
                  "injected, the foundation of the whole test methodology "
                  "(inject → estimate → correct → verify)."),
            )),
    ))
