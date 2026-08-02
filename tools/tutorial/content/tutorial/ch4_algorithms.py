"""Chapter 4: every calibration — principle, implementation, proof.

Each section follows the same shape: derivation with formulas and a
measurement-setup schematic, implementation pointers into src/wifitrx,
then the before/after evidence from the build-time 80 MHz factory run
(RunContext.full_cal) — the proof that the algorithm works.
"""
from __future__ import annotations

import figures
import schematics
from model import Chapter, F, Fig, Diagram, Section, T


def _r(ctx, name):
    return ctx.full_cal["by_name"][name]


# ---------------------------------------------------------------- values
def _lpf_values(ctx):
    r = _r(ctx, "tx_lpf_corner")
    return {"fc_before_pct": f"{r.metrics_before['fc_err_pct']:.1f}",
            "fc_after_pct": f"{r.metrics_after['fc_err_pct']:.2f}",
            "best_code": str(r.estimated["best_code"])}


def _dc_values(ctx):
    r = _r(ctx, "rx_dc_offset")
    return {"dc_before": f"{r.metrics_before['dc_dbfs_state0']:.1f}",
            "dc_after": f"{r.metrics_after['worst_dc_dbfs']:.1f}"}


def _leak_values(ctx):
    r = _r(ctx, "tx_lo_leak_loopback")
    return {"leak_before": f"{r.metrics_before['lo_leak_dbc']:.1f}",
            "leak_after": f"{r.metrics_after['lo_leak_dbc']:.1f}"}


def _iip2_values(ctx):
    r = _r(ctx, "rx_iip2")
    return {"iip2_before": f"{r.metrics_before['iip2_dbm']:.1f}",
            "iip2_after": f"{r.metrics_after['iip2_dbm']:.1f}",
            "trim_code": str(r.estimated["trim_code"]),
            "trim_truth": str(r.estimated["trim_best_truth"])}


def _delay_values(ctx):
    r = _r(ctx, "loopback_delay")
    return {"delay_ns": f"{r.metrics_after['delay_ns']:.2f}"}


def _txiq_values(ctx):
    r = _r(ctx, "tx_iq")
    return {"irr_before": f"{r.metrics_before['irr_min_db']:.1f}",
            "irr_after": f"{r.metrics_after['irr_min_db']:.1f}"}


def _gd_values(ctx):
    r = _r(ctx, "group_delay")
    return {"gd_est": f"{r.metrics_after['estimated_ps']:.0f}",
            "gd_inj": f"{r.metrics_before['injected_ps']:.0f}",
            "gd_err": f"{r.metrics_after['error_ps']:.0f}"}


def _rxiq_values(ctx):
    r = _r(ctx, "rx_iq")
    return {"irr_before": f"{r.metrics_before['irr_min_db']:.1f}",
            "irr_after": f"{r.metrics_after['irr_min_db']:.1f}"}


def _dpd_values(ctx):
    r = _r(ctx, "dpd")
    return {"evm_before": f"{r.metrics_before['evm_db']:.1f}",
            "evm_after": f"{r.metrics_after['evm_db']:.1f}",
            "aclr_before": f"{r.metrics_before['aclr_worst_dbc']:.1f}",
            "aclr_after": f"{r.metrics_after['aclr_worst_dbc']:.1f}"}


def _agc_values(ctx):
    r = _r(ctx, "agc_sweep")
    return {"landing_err": f"{r.metrics_after['worst_landing_err_db']:.2f}"}


def _final_values(ctx):
    fc = ctx.full_cal
    return {"evm_before": f"{fc['evm_before']:.1f}",
            "evm_after": f"{fc['evm_after']:.1f}",
            "tx_evm": f"{fc['tx_evm_db']:.1f}"}


CHAPTER = Chapter(
    id="ch4", title=T("4 校准算法逐项讲解", "4 The calibrations, one by one"),
    sections=(
        Section(
            id="cal-intro", title=T("4.0 阅读方式", "4.0 How to read this chapter"),
            body=(
                T("每节固定四段:<b>原理</b>(推导+测量设置示意)→ <b>实现</b>"
                  "(源码函数指引)→ <b>证据</b>(构建时真实运行的前后对比)→ "
                  "关键数字。所有前后数字来自同一次 80 MHz factory 档全序列运行"
                  "(工艺种子固定),与第 5 章的顺序图、第 6 章的结果同源。",
                  "Every section has the same four parts: <b>principle</b> "
                  "(derivation + measurement-setup schematic) → "
                  "<b>implementation</b> (pointers into the source) → "
                  "<b>evidence</b> (before/after from a real run at build "
                  "time) → the key numbers. All numbers come from one "
                  "80 MHz factory-profile full-sequence run (fixed process "
                  "seed), the same run behind chapter 5's ordering and "
                  "chapter 6's results."),
            )),
        Section(
            id="cal-lpf", title=T("4.1 LPF corner(RC 调谐)", "4.1 LPF corner (RC tuning)"), level=3,
            values=_lpf_values,
            value_keys=("fc_before_pct", "fc_after_pct", "best_code"),
            body=(
                T("<b>原理</b>:在标称截止频率 $f_c$ 与低频参考 $f_c/32$ 处"
                  "各发一个单音,二者的功率比给出通带边沿的实际衰减;扫描 RC "
                  "调谐码,选功率比最接近 −3 dB 的码字。TX 侧经包络检波器读出"
                  "(不依赖 RX),RX 侧经 ADC 读出。",
                  "<b>Principle</b>: transmit one tone at the nominal "
                  "corner $f_c$ and one at a low-frequency reference "
                  "$f_c/32$; their power ratio reads the actual edge "
                  "attenuation. Sweep the RC code and pick the one landing "
                  "closest to −3 dB. The TX side reads through the "
                  "envelope detector (no RX involved), the RX side through "
                  "the ADC."),
                Diagram(id="dg-envdet", build=schematics.envdet_path,
                        caption=T("RX 无关的包络检波观测路径",
                                  "The RX-independent envelope-detector "
                                  "observation path")),
                T("<b>实现</b>:<code>cal/lpf_corner.py</code>,factory 档全码"
                  "扫描、poweron 档二分搜索;检波器响应用 det.response() 补偿。"
                  "<b>为什么最先做</b>:后续所有频域估计都经过这两个滤波器,"
                  "corner 不校准,后面全被通带畸变污染。",
                  "<b>Implementation</b>: <code>cal/lpf_corner.py</code> — "
                  "full code sweep in the factory profile, bisection in "
                  "poweron; the detector's own response is compensated via "
                  "det.response(). <b>Why first</b>: every later "
                  "frequency-domain estimate passes through these filters; "
                  "an uncalibrated corner pollutes everything downstream."),
                Fig(id="fig-lpf-sweep", build=figures.lpf_code_sweep,
                    caption=T("TX LPF 码扫描与选中码",
                              "TX LPF code sweep and the selected code")),
                T("<b>证据</b>:本次运行 corner 误差从 {fc_before_pct}% 校到 "
                  "{fc_after_pct}%(选中码 {best_code}),压进 1 LSB 步进内。",
                  "<b>Evidence</b>: this run pulled the corner error from "
                  "{fc_before_pct}% to {fc_after_pct}% (code {best_code}), "
                  "inside one LSB step."),
            )),
        Section(
            id="cal-rxdc", title=T("4.2 RX DC 偏置", "4.2 RX DC offset"), level=3,
            values=_dc_values, value_keys=("dc_before", "dc_after"),
            body=(
                T("<b>原理</b>:端口端接(零输入)下逐 AGC 档平均 ADC 输出,"
                  "得到每档的复 DC,建立逐档数字消除表。逐档是物理要求:主要"
                  "来源是 LO 自混频,其电平随前端增益档变化。",
                  "<b>Principle</b>: with the port terminated (zero input), "
                  "average the ADC output per AGC state to get each state's "
                  "complex DC and build a per-state digital subtraction "
                  "table. Per-state is physics, not caution: the dominant "
                  "source is LO self-mixing, which changes with front-end "
                  "gain."),
                T("<b>实现</b>:<code>cal/rx_dc.py</code>。<b>证据</b>:最高"
                  "增益档 DC 从 {dc_before} dBFS 压到全档最差 {dc_after} "
                  "dBFS。<b>为什么在 LO 泄漏校准之前</b>:环回法里 TX 泄漏与 "
                  "RX 残余 DC 都在近零频,先清掉 RX 自己的 DC,泄漏测量才"
                  "干净(第 5 章依赖图里这是一条被强制执行的边)。",
                  "<b>Implementation</b>: <code>cal/rx_dc.py</code>. "
                  "<b>Evidence</b>: highest-gain-state DC pulled from "
                  "{dc_before} dBFS to a worst-state {dc_after} dBFS. "
                  "<b>Why before the LO-leak cal</b>: in the loopback "
                  "method both the TX leak and the RX's own residual DC "
                  "live near zero frequency; purging the RX DC first keeps "
                  "the leak measurement clean (an enforced edge in chapter "
                  "5's dependency graph)."),
            )),
        Section(
            id="cal-leak", title=T("4.3 TX LO 泄漏", "4.3 TX LO leakage"), level=3,
            values=_leak_values, value_keys=("leak_before", "leak_after"),
            body=(
                T("<b>方法一(包络检波,粗校)</b>:发单音 $A e^{j2\\pi f_0 t}$,"
                  "泄漏 $c$ 与主音在平方律检波器输出中拍频于 $f_0$:",
                  "<b>Method 1 (envelope detector, coarse)</b>: transmit a "
                  "tone $A e^{j2\\pi f_0 t}$; the leak $c$ beats with it in "
                  "the square-law detector at $f_0$:"),
                F(r"|A e^{j2\pi f_0 t}+c|^2 = A^2+|c|^2+"
                  r"2A\,\mathrm{Re}[c^* e^{j2\pi f_0 t}]"),
                T("拍频功率是数字预失调 dc_pre 的<em>二次型</em>,对 I、Q 两轴"
                  "各做三点抛物线拟合直接跳到顶点,迭代两三轮收敛——不依赖 RX。",
                  "The beat power is a <em>quadratic</em> in the digital "
                  "pre-offset dc_pre; a three-point parabola fit per axis "
                  "jumps straight to the vertex, converging in two-three "
                  "iterations — no RX involved."),
                T("<b>方法二(环回,精校)</b>:RX LO 加偏移 $\\Delta f$,TX "
                  "载波泄漏在捕获频谱里落到 $-\\Delta f$ bin,与 RX 残余 DC"
                  "(0 bin)分离;注入已知数字 DC 导频测出 dc_pre → 泄漏 bin "
                  "的复传输增益 $g$,一步解出:",
                  "<b>Method 2 (loopback, fine)</b>: offset the RX LO by "
                  "$\\Delta f$ so the TX carrier leak lands on the "
                  "$-\\Delta f$ bin, separated from the RX's residual DC "
                  "(bin 0). Inject a known digital DC pilot to measure the "
                  "complex transfer gain $g$ from dc_pre to the leak bin, "
                  "then solve in one step:"),
                F(r"dc_{pre} \leftarrow dc_{pre} - \mathrm{bin}"
                  r"(-\Delta f)/g"),
                Diagram(id="dg-lb-offset", build=schematics.loopback_offset,
                        caption=T("RX-LO 偏移环回:泄漏与 RX DC 在频域分离",
                                  "Loopback with RX-LO offset: leak and RX "
                                  "DC separated in frequency")),
                Fig(id="fig-leak-conv", build=figures.lo_leak_convergence,
                    caption=T("环回法收敛轨迹", "Loopback-method "
                              "convergence")),
                T("<b>证据</b>:{leak_before} dBc → {leak_after} dBc。"
                  "实现:<code>cal/tx_lo_leak.py</code>。",
                  "<b>Evidence</b>: {leak_before} dBc → {leak_after} dBc. "
                  "Implementation: <code>cal/tx_lo_leak.py</code>."),
            )),
        Section(
            id="cal-iip2", title=T("4.4 RX IIP2 trim", "4.4 RX IIP2 trim"), level=3,
            values=_iip2_values,
            value_keys=("iip2_before", "iip2_after", "trim_code",
                        "trim_truth"),
            body=(
                T("<b>原理</b>:发双音 $(f_1,f_2)$,混频器二阶失真把包络平方项"
                  "下变频到基带,在 $f_2-f_1$ 产生 IM2 拍;IM2 幅度与 trim 码"
                  "近似线性,故 IM2 <em>功率</em>是 trim 码的抛物线,三点拟合"
                  "+ 信赖域迭代找零点。",
                  "<b>Principle</b>: transmit a two-tone $(f_1,f_2)$; "
                  "second-order mixer distortion downconverts the squared "
                  "envelope, producing an IM2 beat at $f_2-f_1$. The IM2 "
                  "amplitude is ~linear in the trim code, so IM2 "
                  "<em>power</em> is a parabola in the code — three-point "
                  "fit plus a trust-region iteration finds the null."),
                T("<b>三个必须知道的陷阱</b>(都是被真实调试逼出来的):"
                  "① 必须排在 TX LO 泄漏校准<em>之后</em>——PA 三阶积 "
                  "$f_2\\times leak \\times f_1^*$ 恰好落在 $f_2-f_1$ 测量 "
                  "bin 上,未校的载波泄漏能把 IM2 null 埋掉 ~35 dB;"
                  "② 量化器杂散会污染弱 IM2 读数,用<em>相位随机化相干平均</em>"
                  "(每次捕获给双音一个随机公共相位,IM2 bin 相干、杂散非相干)"
                  "压掉;③ 相位随机化救不了 <em>TX 侧的偶阶失真</em>——DAC "
                  "对双音的二阶积同样落在 $f_2-f_1$ 且与音对相位差相干,这个"
                  "随信道透传的背景与 trim 码无关,会把 null 填平甚至推歪"
                  "(320 MHz 下整个码域只剩 ~1 dB 起伏)。解法是<em>双电平"
                  "分离</em>:每个码在两个相差 6 dB 的耦合衰减下各测一次,"
                  "线性信道(音与 TX 背景一起)按音调 bin 复比值 $g$ 归一化后"
                  "相减 $beat_{lo}-g\\,beat_{hi}$,只留下本地混频器 IM2——"
                  "真实硅片上激励源自身 IP2 不可信时用的同一招。",
                  "<b>Three traps you must know</b> (all earned in real "
                  "debugging): ① it must run <em>after</em> the TX LO-leak "
                  "cal — the PA's third-order product "
                  "$f_2\\times leak \\times f_1^*$ lands exactly on the "
                  "$f_2-f_1$ measurement bin, and an uncalibrated carrier "
                  "leak buries the IM2 null by ~35 dB; ② quantizer spurs "
                  "pollute weak IM2 readings — suppressed by "
                  "<em>phase-randomized coherent averaging</em> (each "
                  "capture gives the tone pair a random common phase: the "
                  "IM2 bin adds coherently, the spurs don't); ③ phase "
                  "randomization cannot save you from <em>TX-side "
                  "even-order distortion</em> — the DAC's second-order "
                  "product of the tone pair lands on the same $f_2-f_1$ "
                  "bin, coherent with the tone phase difference. That "
                  "transmitted, code-independent background flattens or "
                  "tilts the null (at 320 MHz the whole code range showed "
                  "~1 dB of ripple). The cure is <em>two-level "
                  "separation</em>: measure each code at two coupler "
                  "attenuations 6 dB apart and subtract after normalizing "
                  "by the complex tone-bin ratio $g$ "
                  "($beat_{lo}-g\\,beat_{hi}$) — the linear channel (tones "
                  "and TX background alike) cancels, leaving only the "
                  "local mixer IM2. The same trick real silicon uses when "
                  "the cal source's own IP2 cannot be trusted."),
                Fig(id="fig-iip2", build=figures.iip2_trace,
                    caption=T("trim 码搜索轨迹(有效 IIP2)",
                              "Trim-code search trace (effective IIP2)")),
                T("<b>证据</b>:有效 IIP2 {iip2_before} → {iip2_after} dBm,"
                  "搜索停在码 {trim_code}(注入真值最优码 {trim_truth})。"
                  "实现:<code>cal/rx_iip2.py</code>。",
                  "<b>Evidence</b>: effective IIP2 {iip2_before} → "
                  "{iip2_after} dBm, search settled on code {trim_code} "
                  "(injected-truth optimum {trim_truth}). Implementation: "
                  "<code>cal/rx_iip2.py</code>."),
            )),
        Section(
            id="cal-delay", title=T("4.5 环回时延测量", "4.5 Loopback delay"), level=3,
            values=_delay_values, value_keys=("delay_ns",),
            body=(
                T("<b>原理</b>:整数时延由互相关峰给出,分数部分由峰值三点"
                  "抛物线插值估计、FFT 相位斜坡去除。它本身不编程任何校正,"
                  "但后续所有 FFT-bin 校准的捕获对齐都靠它——IIR 滤波器还贡献"
                  "启动瞬态,捕获统一带 512 样本循环预热前缀。本次运行时延 "
                  "{delay_ns} ns。实现:<code>cal/sync.py</code>。",
                  "<b>Principle</b>: the integer delay is the "
                  "cross-correlation peak; the fractional part comes from "
                  "three-point parabolic interpolation of the peak and is "
                  "removed with an FFT phase ramp. It programs nothing "
                  "itself, but every later FFT-bin calibration aligns its "
                  "captures with this estimate — and because the IIR "
                  "filters also contribute startup transients, captures "
                  "carry a 512-sample cyclic warm-up prefix. This run: "
                  "{delay_ns} ns. Implementation: "
                  "<code>cal/sync.py</code>."),
            )),
        Section(
            id="cal-txiq",
            title=T("4.6 TX 频变 IQ(核心)", "4.6 TX frequency-dependent IQ (the core)"), level=3,
            values=_txiq_values, value_keys=("irr_before", "irr_after"),
            body=(
                T("这是整套校准里最精巧的一步。<b>难点</b>:环回观测里 TX 镜像、"
                  "RX 镜像、环回信道响应搅在一起,如何只测 TX?<b>解法</b>:"
                  "RX-LO 偏移 $\\Delta f$ 让三者落到<em>三个不同的 bin</em>:"
                  "频率 $f$ 的 TX 音出现在 $f-\\Delta f$,TX 镜像在 "
                  "$-f-\\Delta f$,RX 自己的镜像在 $-f+\\Delta f$。",
                  "The most delicate step in the suite. <b>The problem</b>: "
                  "in loopback the TX image, RX image and loopback channel "
                  "response are entangled — how do you measure only TX? "
                  "<b>The trick</b>: an RX-LO offset $\\Delta f$ separates "
                  "all three onto <em>different bins</em>: a TX tone at "
                  "$f$ lands at $f-\\Delta f$, its TX image at "
                  "$-f-\\Delta f$, and the RX's own image at "
                  "$-f+\\Delta f$."),
                T("发正频梳状音,再发负频梳状音。第一次捕获在镜像 bin 读到 "
                  "$A_{img}=G_2^{tx}(f)\\,H(-f-\\Delta f)$;第二次捕获在同一"
                  "物理 bin(此时是直达音)读到 "
                  "$A_{dir}=G_1^{tx}(-f)\\,H(-f-\\Delta f)$——"
                  "两式共享同一个环回/RX 线性响应 $H$,取比值精确抵消:",
                  "Transmit a positive-frequency comb, then a negative one. "
                  "The first capture reads the image bin "
                  "$A_{img}=G_2^{tx}(f)\\,H(-f-\\Delta f)$; the second "
                  "reads the same physical bin (now carrying a direct "
                  "tone), $A_{dir}=G_1^{tx}(-f)\\,H(-f-\\Delta f)$ — both "
                  "share the same loopback/RX response $H$, so the ratio "
                  "cancels it exactly:"),
                F(r"\rho(f)=\frac{A_{img}}{A_{dir}}"
                  r"=\frac{G_2^{tx}(f)}{G_1^{tx}(-f)}"),
                T("逐频点得到 $\\rho(f)$ 后,预失真采用 widely-linear 校正 "
                  "$x_c = x + w_2 * x^*$,共轭路 FIR 由频率采样最小二乘设计:",
                  "With $\\rho(f)$ measured per frequency, the "
                  "pre-corrector is widely-linear, $x_c = x + w_2 * x^*$, "
                  "its conjugate-path FIR designed by frequency-sampling "
                  "least squares:"),
                F(r"W_2(f) \approx -\rho(f)"),
                T("设计细节有一个真实教训:只约束测量频点会让 FIR 在未约束的 "
                  "Nyquist 区间自由振荡(系数范数爆到 12.9,放大共轭路噪声),"
                  "必须在全 $\\pm f_s/2$ 网格上约束、带外锥化到零 + 岭正则。"
                  "梳状音幅度也有讲究:压到 0.03–0.04,否则 PA 的单边 IM3 组合"
                  "$(f_i+f_j-f_k)$ 恰好落进镜像 bin,把弱镜像淹掉。",
                  "One earned lesson in the FIR design: constraining only "
                  "the measured tones lets the FIR ring freely in the "
                  "unconstrained Nyquist region (tap norm blew up to 12.9, "
                  "amplifying conjugate-path noise) — constrain the full "
                  "$\\pm f_s/2$ grid with out-of-band taper-to-zero plus "
                  "ridge regularization. Comb amplitude matters too: kept "
                  "at 0.03–0.04, or the PA's one-sided IM3 combinations "
                  "$(f_i+f_j-f_k)$ land in the image bins and bury the "
                  "weak image."),
                Fig(id="fig-txiq-irr", build=figures.tx_iq_irr,
                    caption=T("TX IRR 逐频点前后对比",
                              "TX IRR per frequency, before/after")),
                T("<b>证据</b>:最差 IRR {irr_before} dB → {irr_after} dB。"
                  "实现:<code>cal/tx_iq.py</code>(测量)、"
                  "<code>cal/wl_fir.py</code>(FIR 设计)。",
                  "<b>Evidence</b>: worst IRR {irr_before} dB → "
                  "{irr_after} dB. Implementation: "
                  "<code>cal/tx_iq.py</code> (measurement), "
                  "<code>cal/wl_fir.py</code> (FIR design)."),
            )),
        Section(
            id="cal-gd", title=T("4.7 群时延失配验证", "4.7 Group-delay mismatch check"), level=3,
            values=_gd_values, value_keys=("gd_est", "gd_inj", "gd_err"),
            body=(
                T("I/Q 轨间纯群时延失配 $\\tau$ 是频变失衡的特例:小失配下 "
                  "$G_1\\approx 1$、$G_2(f)\\approx j\\pi f\\tau$,因此 "
                  "$\\mathrm{Im}\\,\\rho(f)$ 对 $\\pi f$ 的斜率就是 $\\tau$。"
                  "从 4.6 已测的 $\\rho(f)$ 免费提取,并与注入真值对照:估计 "
                  "{gd_est} ps,注入 {gd_inj} ps,误差 {gd_err} ps。实现:"
                  "<code>cal/group_delay.py</code>。",
                  "A pure inter-rail group-delay mismatch $\\tau$ is a "
                  "special case of the frequency-dependent imbalance: for "
                  "small mismatch $G_1\\approx 1$ and "
                  "$G_2(f)\\approx j\\pi f\\tau$, so the slope of "
                  "$\\mathrm{Im}\\,\\rho(f)$ against $\\pi f$ is $\\tau$ — "
                  "extracted for free from 4.6's measured $\\rho(f)$ and "
                  "checked against the injected truth: estimated {gd_est} "
                  "ps vs injected {gd_inj} ps, error {gd_err} ps. "
                  "Implementation: <code>cal/group_delay.py</code>."),
            )),
        Section(
            id="cal-rxiq", title=T("4.8 RX 频变 IQ", "4.8 RX frequency-dependent IQ"), level=3,
            values=_rxiq_values, value_keys=("irr_before", "irr_after"),
            body=(
                T("TX 校好之后,RX 侧不再需要偏移:共 LO 发单边梳状音 $Z(f)$,"
                  "捕获里 $Y(+f)=G_1^{rx}Z$、$Y(-f)=G_2^{rx}Z^*$,两 bin 相除"
                  "让<em>信源项完全抵消</em>:",
                  "With TX already clean, the RX side needs no offset: "
                  "transmit single-sideband combs $Z(f)$ with shared LO; "
                  "the capture gives $Y(+f)=G_1^{rx}Z$ and "
                  "$Y(-f)=G_2^{rx}Z^*$, and dividing the two bins makes "
                  "<em>the source term cancel entirely</em>:"),
                F(r"W_2(-f) = -\,\frac{Y(-f)}{Y^{*}(+f)}"),
                T("后置 widely-linear FIR 校正。<b>顺序为什么不能反</b>:若 "
                  "TX 镜像还在,这一步会把它归罪给 RX,得到一个'TX 抵消 RX'的"
                  "解——环回里镜像消了,天线口的镜像反而更差。这条约束在 "
                  "cal/deps.py 里是数据,由测试强制执行。<b>证据</b>:最差 "
                  "IRR {irr_before} → {irr_after} dB。实现:"
                  "<code>cal/rx_iq.py</code>。",
                  "A post widely-linear FIR corrects it. <b>Why the order "
                  "cannot flip</b>: with the TX image still present this "
                  "step attributes it to the RX and converges on a "
                  "TX-cancels-RX solution — the loopback image nulls while "
                  "the antenna-side image gets worse. That constraint is "
                  "data in cal/deps.py, enforced by tests. "
                  "<b>Evidence</b>: worst IRR {irr_before} → {irr_after} "
                  "dB. Implementation: <code>cal/rx_iq.py</code>."),
            )),
        Section(
            id="cal-txpwr", title=T("4.9 TX 功率", "4.9 TX power"), level=3,
            body=(
                T("OFDM 激励下扫增益码,经观测路径实测 PA 输出功率,建立"
                  "码字→dBm 查找表并可插值命中目标功率;表内单调性是通过判据。"
                  "np.interp 会静默钳位,目标落在表外时结果码触轨——这正是 "
                  "saturated 标志(见第 6 章)存在的原因之一。实现:"
                  "<code>cal/tx_power.py</code>。",
                  "Sweep the gain code under OFDM drive, measure true PA "
                  "output power through the observation path, and build "
                  "the code→dBm lookup (interpolating to hit a target). "
                  "Monotonicity is the pass criterion. np.interp clips "
                  "silently — a target outside the table rails the "
                  "resulting code, one of the reasons the saturated flag "
                  "(chapter 6) exists. Implementation: "
                  "<code>cal/tx_power.py</code>."),
                Fig(id="fig-txpwr", build=figures.tx_power_table,
                    caption=T("码字→实测输出功率", "Gain code vs measured "
                              "output power")),
            )),
        Section(
            id="cal-dpd", title=T("4.10 DPD(间接学习)", "4.10 DPD (indirect learning)"), level=3,
            values=_dpd_values,
            value_keys=("evm_before", "evm_after", "aclr_before",
                        "aclr_after"),
            body=(
                T("<b>原理</b>:间接学习架构(ILA)。环回捕获对齐后,以第 0 轮"
                  "的线性增益为<em>固定目标增益</em>:",
                  "<b>Principle</b>: the indirect-learning architecture "
                  "(ILA). After aligned loopback capture, fix the target "
                  "gain from iteration 0:"),
                F(r"G_0 = \frac{\langle x, y\rangle}{\langle x, x\rangle}"),
                T("对 (捕获/$G_0$ → 实际驱动 $u$) 拟合 GMP 后逆,再把系数复制"
                  "为预失真器;迭代至 ACLR 收敛。$G_0$ 冻结是稳定性关键:目标"
                  "增益随轮漂移会让迭代追自己的尾巴。",
                  "fit a GMP post-inverse from (capture/$G_0$ → the actual "
                  "drive $u$), copy the coefficients into the "
                  "predistorter, iterate until ACLR converges. Freezing "
                  "$G_0$ is the stability key: a per-iteration drifting "
                  "target makes the loop chase its own tail."),
                Diagram(id="dg-ila", build=schematics.ila_loop,
                        caption=T("ILA:拟合后逆,再复制为预失真器",
                                  "ILA: fit the post-inverse, copy it as "
                                  "the predistorter")),
                T("<b>为什么必须最后做</b>:ILA 对观测到的一切失真照单全收,"
                  "残余 IQ 镜像/泄漏会被学进 GMP 系数并在所有驱动电平上重放。"
                  "<b>带宽有两个硬前提</b>:过采样率 4(os=2 时预失真频谱被"
                  "混叠+TX LPF 剥掉,EVM 卡死在 −35 dB 与电平无关);观测路径"
                  "用宽带模式(RX LPF 旁路)。",
                  "<b>Why it must run last</b>: ILA learns whatever "
                  "distortion it observes — residual IQ image/leak gets "
                  "baked into the GMP coefficients and replayed at every "
                  "drive level. <b>Two hard bandwidth prerequisites</b>: "
                  "oversampling 4 (at os=2 aliasing plus the TX LPF strip "
                  "the correction spectrum and EVM pins at −35 dB "
                  "regardless of level), and a wideband observation path "
                  "(RX LPF bypassed)."),
                Fig(id="fig-dpd-conv", build=figures.dpd_convergence,
                    caption=T("每轮 ILA 的最差 ACLR",
                              "Worst ACLR per ILA iteration")),
                T("<b>证据</b>:EVM {evm_before} → {evm_after} dB,最差 ACLR "
                  "{aclr_before} → {aclr_after} dBc。实现:"
                  "<code>cal/dpd_cal.py</code>、<code>dpd/ila.py</code>、"
                  "<code>pa/gmp.py</code>。",
                  "<b>Evidence</b>: EVM {evm_before} → {evm_after} dB, "
                  "worst ACLR {aclr_before} → {aclr_after} dBc. "
                  "Implementation: <code>cal/dpd_cal.py</code>, "
                  "<code>dpd/ila.py</code>, <code>pa/gmp.py</code>."),
            )),
        Section(
            id="cal-agc", title=T("4.11 AGC 验证", "4.11 AGC verification"), level=3,
            values=_agc_values, value_keys=("landing_err",),
            body=(
                T("全部校正生效后扫输入功率:验证 LNA 档位切换、ADC 落点"
                  "(目标 FS − 12 dB)与 SNR 单调性。本次最差落点误差 "
                  "{landing_err} dB。实现:<code>cal/agc_cal.py</code>。",
                  "With every correction active, sweep the input power: "
                  "verify LNA handovers, the ADC landing point (target "
                  "FS − 12 dB) and SNR sanity. Worst landing error this "
                  "run: {landing_err} dB. Implementation: "
                  "<code>cal/agc_cal.py</code>."),
                Fig(id="fig-agc", build=figures.agc_sweep,
                    caption=T("AGC 扫描:ADC 落点与 SNR",
                              "AGC sweep: ADC landing and SNR")),
            )),
        Section(
            id="cal-final", title=T("4.12 最终环回 EVM", "4.12 Final loopback EVM"), level=3,
            values=_final_values,
            value_keys=("evm_before", "evm_after", "tx_evm"),
            body=(
                T("全链路验收:同一 OFDM 帧,逐音均衡 + 公共相位去除(规范 "
                  "EVM 测法)。复合环回 EVM {evm_before} → {evm_after} dB;"
                  "PA 输出处的 TX EVM(802.11be 规范测量点)为 {tx_evm} dB。"
                  "星座图与频谱前后对比:",
                  "The end-to-end acceptance: the same OFDM frame, "
                  "per-tone equalization plus common-phase removal (the "
                  "standard EVM method). Composite loopback EVM "
                  "{evm_before} → {evm_after} dB; TX EVM at the PA output "
                  "(the 802.11be measurement point) {tx_evm} dB. "
                  "Constellation and spectrum, before vs after:"),
                Fig(id="fig-const", build=figures.constellation_compare,
                    caption=T("均衡后星座图:校准前 vs 校准后",
                              "Equalized constellation: before vs after")),
                Fig(id="fig-psd-cmp", build=figures.psd_compare,
                    caption=T("PA 输出频谱与 WiFi 谱模板(带内中位数归一,"
                              "避免泄漏尖峰扭曲对比)",
                              "PA-output spectrum vs the WiFi mask "
                              "(in-band-median normalized so the leak "
                              "spike cannot skew the comparison)")),
            )),
    ))
