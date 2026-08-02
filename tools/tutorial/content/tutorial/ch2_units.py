"""Chapter 2: units convention."""
from __future__ import annotations

from model import Chapter, Code, F, Section, T, Table

CHAPTER = Chapter(
    id="ch2", title=T("2 单位约定", "2 Units convention"),
    sections=(
        Section(
            id="units",
            title=T("2.1 sqrt(mW) 基带与数字满量程边界",
                    "2.1 sqrt(mW) baseband and the digital full-scale boundary"),
            body=(
                T("模拟域信号统一用 $\\sqrt{\\mathrm{mW}}$ 为单位的复包络表示:"
                  "这样 $|x|^2$ 直接就是瞬时功率 [mW],平均功率 "
                  "$P_{dBm}=10\\log_{10}\\overline{|x|^2}$,增益就是乘系数 "
                  "$10^{G_{dB}/20}$,全链路不需要任何阻抗换算。",
                  "Analog-domain signals are complex envelopes in units of "
                  "$\\sqrt{\\mathrm{mW}}$: $|x|^2$ is then instantaneous "
                  "power in mW, average power is "
                  "$P_{dBm}=10\\log_{10}\\overline{|x|^2}$, gain is a plain "
                  "multiplication by $10^{G_{dB}/20}$, and no impedance "
                  "bookkeeping is needed anywhere in the chain."),
                T("数字域(DAC 输入、ADC 输出、全部校正器)用满量程归一:"
                  "$|I|,|Q|\\leq 1$。两个域在数据转换器处衔接,换算系数由转换器"
                  "的满量程功率参数决定:",
                  "The digital domain (DAC input, ADC output, every "
                  "corrector) is full-scale normalized: $|I|,|Q|\\leq 1$. The "
                  "two domains meet at the data converters; the scale factor "
                  "comes from the converter's full-scale power parameter:"),
                F(r"a_{fs}=\sqrt{10^{\,\mathrm{fullscale\_dbm}/10}}"),
                Table(header=(T("节点", "Node"), T("默认值", "Default"),
                              T("说明", "Notes")),
                      rows=(("DAC full-scale", "+4 dBm",
                             "digital 1.0 → +4 dBm rms"),
                            ("PA", "26 dB / 28 dBm",
                             "gain / P<sub>sat</sub>"),
                            ("loopback coupler+atten", "−40 dB",
                             "PA output → RX input"),
                            ("ADC full-scale", "+2 dBm",
                             "AGC targets FS − 12 dB")),
                      caption=T("默认电平计划(units.md)",
                                "Default level plan (units.md)")),
                T("推荐的数字驱动幅度是 rms 0.10–0.15:给 OFDM 的 PAPR 和 DAC "
                  "余量留出空间,同时把 PA 推到有代表性的回退点。",
                  "The recommended digital drive is 0.10–0.15 rms: room for "
                  "OFDM PAPR and DAC headroom while driving the PA at a "
                  "representative backoff."),
                Code("y_pa = tx(x)          # sqrt(mW) at the PA output\n"
                     "p_dbm = power_dbm(y_pa)\n"
                     "cap = run_loopback(tx, rx, x, path)  # digital FS again"),
            )),
        Section(
            id="pn-units", title=T("2.2 相噪单位约定", "2.2 Phase-noise conventions"),
            body=(
                T("相噪谱统一内部用双边带 $S_\\varphi(f)$ [rad²/Hz];对外报告"
                  "用单边带 $L(f)$ [dBc/Hz],二者换算:",
                  "Phase noise is carried internally as the double-sideband "
                  "$S_\\varphi(f)$ in rad²/Hz and reported as the "
                  "single-sideband $L(f)$ in dBc/Hz:"),
                F(r"L(f)=10\log_{10}\left[S_\varphi(f)/2\right]"),
                T("积分相噪(IPN)与 rms 相位/抖动:",
                  "Integrated phase noise (IPN) and rms phase/jitter:"),
                F(r"\mathrm{IPN}_{dBc}=10\log_{10}\left[\frac{1}{2}"
                  r"\int_{f_1}^{f_2} S_\varphi(f)\,df\right],\qquad "
                  r"\sigma_\varphi=\sqrt{\int S_\varphi\,df}"),
                T("模型里任何 NoiseSource 都带 unit 字段,LOModel 在合成前"
                  "检查它必须是 rad²/Hz——一个曾经没人读的标签,现在是被"
                  "强制执行的契约(死旋钮测试的直接产物,见开发说明)。",
                  "Every NoiseSource carries a unit field, and LOModel "
                  "refuses to synthesize anything that is not rad²/Hz — a "
                  "label nothing used to read, now an enforced contract (a "
                  "direct product of the dead-knob test; see the developer "
                  "guide)."),
            )),
    ))
