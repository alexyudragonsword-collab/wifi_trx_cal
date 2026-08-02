"""Chapter 7: the four design insights the model produced."""
from __future__ import annotations

from model import Chapter, Section, T

CHAPTER = Chapter(
    id="ch7", title=T("7 设计洞察", "7 Design insights"),
    sections=(
        Section(
            id="insights",
            title=T("7.1 模型换来的电路结论", "7.1 Circuit conclusions the model paid for"),
            body=(
                T("<b>① 4096-QAM 必须配低相噪综合器。</b>IPN ≈ −38 dBc 的 LO "
                  "单独就吃掉整个 −38 dB EVM 预算——CPE 去除救不了子载波间"
                  "相噪;需要 −43 dBc 量级。模型默认剖面按 PLL 组的抖动"
                  "指标锚定:120 fs rms(10 kHz–100 MHz 积分,6 GHz 载频,"
                  "IPN −46.9 dBc,0.26° rms)。积分下限取 10 kHz 是 CPE "
                  "给的松绑——更近端的 frac-N 噪声被逐符号公共相位去除"
                  "赦免。这是给 PLL 组的硬指标,不是仿真参数偏好。",
                  "<b>① 4096-QAM demands a low-phase-noise synthesizer.</b> "
                  "An LO at IPN ≈ −38 dBc alone consumes the entire −38 dB "
                  "EVM budget — CPE removal does not rescue "
                  "inter-subcarrier phase noise; a −43 dBc class is "
                  "required. The default profile is anchored to the PLL "
                  "team's jitter target: 120 fs rms (integrated "
                  "10 kHz–100 MHz at the 6 GHz carrier; IPN −46.9 dBc, "
                  "0.26° rms). The 10 kHz lower integration bound is "
                  "CPE's gift — closer-in fractional-N noise is absolved "
                  "by per-symbol common-phase removal. A hard requirement "
                  "for the PLL team, not a simulation preference."),
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
                T("<b>⑤ 窄带模式:校准激励随带宽缩放,corner 比例保持"
                  "统一。</b>23 MHz 探测音在 20 MHz 信道里是带外音——IIP2 "
                  "trim 在噪声上乱走、AGC 扫描读不到 SNR,这是窄带校准失败"
                  "的真正(也是唯一的)功能性原因,激励频率必须随带宽缩放。"
                  "corner 比例则全带宽统一 1.3×(TX)/1.12×(RX):无伪影"
                  "仪表实测 20 MHz 单 LPF 地板 −55/−50 dB,比整链实际到达"
                  "的 ~−42 dB 低 12 dB 以上。曾短暂采用的窄带 3× 策略已"
                  "撤销——它只买到没人消费的余量(TX EVM +1.5 dB、环回观测"
                  "底板 +11 dB),代价是邻道模拟抑制从 ~25 dB 塌到 ~0 dB、"
                  "blocker 全压到 ADC 动态范围。EVM 指标不给 blocker 定价,"
                  "corner 规格必须给。此条由 20 MHz GUI 运行的异常直接换来。",
                  "<b>⑤ Narrow modes: scale calibration probes with "
                  "bandwidth; keep the corner ratios uniform.</b> A "
                  "23 MHz probe tone is out-of-channel at 20 MHz — the "
                  "IIP2 trim walks on noise and the AGC sweep reads no "
                  "SNR at all; that is the real (and only) functional "
                  "failure of narrow-mode calibration, so probe "
                  "frequencies must scale with bandwidth. The corner "
                  "ratios stay uniform at every bandwidth — 1.3× (TX) / "
                  "1.12× (RX): the artifact-free 20 MHz single-LPF "
                  "floors are −55/−50 dB, 12+ dB below the ~−42 dB the "
                  "calibrated chain actually reaches. A briefly-adopted "
                  "3× narrow-mode policy was reverted: it bought only "
                  "unconsumed margin (+1.5 dB TX EVM, +11 dB loopback-"
                  "observation floor) while collapsing analog adjacent-"
                  "channel rejection from ~25 dB to ~0 dB, dumping the "
                  "blocker onto ADC dynamic range. EVM does not price "
                  "blockers; the corner spec must. Paid for directly by "
                  "an anomalous 20 MHz GUI run."),
                T("<b>⑥ 先校准测量仪器,再给电路定规格。</b>最初诊断出的"
                  "\"1.3× corner 在 20 MHz 把 EVM 钉死在 −33 dB\"是测量"
                  "伪影:测试接收机模型的时延补偿用循环 FFT 移位整体前移"
                  "捕获,把 warm-up 样本卷进最后一个符号的 FFT 窗。误差"
                  "正比于滤波器群时延(所以跟着 corner 变!)、反比于 FFT "
                  "长度(所以 320 MHz 看不见、20 MHz 最重),完美伪装成"
                  "物理 ISI 地板;换一个符号数,数字就漂移——这正是暴露"
                  "它的线索。修复后还剩第二层:时延补偿把最后一个符号的 "
                  "FFT 窗推出 burst 末尾几个采样,截断的 ramp-down 让延续"
                  "内容失真,在深地板上仍值 >8 dB——现在多发一个 padding "
                  "符号、只对内部符号打分(实验室标准做法)。全部修完后"
                  "真实地板在 1.3× 即有 −55 dB,基于伪影数据定下的窄带 "
                  "3× corner 策略随之撤销(见⑤)。任何随测量配置漂移的"
                  "\"物理结论\"都要先怀疑测量本身。",
                  "<b>⑥ Calibrate the measuring instrument before "
                  "spec'ing the circuit.</b> The originally diagnosed "
                  "\"−33 dB EVM floor at a 1.3× corner\" was a "
                  "measurement artifact: the test-receiver model's delay "
                  "compensation circularly advanced the whole capture, "
                  "wrapping warm-up samples into the last symbol's FFT "
                  "window. The error scales with filter group delay (so "
                  "it tracked the corner!) and inversely with FFT size "
                  "(so 320 MHz never saw it and 20 MHz was hit hardest) "
                  "— a perfect impostor of a physical ISI floor. Its "
                  "numbers drifted with the symbol count, which is the "
                  "clue that exposed it. A second layer remained after "
                  "the fix: delay compensation pushes the final symbol's "
                  "FFT window a few samples past the burst end, where "
                  "the truncated ramp-down misrepresents the "
                  "continuation — still worth >8 dB on deep floors; the "
                  "EVM meter now transmits one padding symbol and "
                  "scores interior symbols only (lab practice). With "
                  "both fixed, the true floor at 1.3× is already "
                  "−55 dB, and the narrow-mode 3× corner policy that "
                  "had been founded on the artifact data was reverted "
                  "(see ⑤). Any \"physical\" conclusion that drifts "
                  "with the measurement configuration indicts the "
                  "measurement first."),
            )),
    ))
