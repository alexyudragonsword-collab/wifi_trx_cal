"""Chapter 7: the four design insights the model produced."""
from __future__ import annotations

from model import Chapter, Section, T

CHAPTER = Chapter(
    id="ch7", title=T("7 设计洞察", "7 Design insights"),
    sections=(
        Section(
            id="insights", title=T("7.1 模型换来的电路结论", "7.1 Circuit conclusions the model paid for"),
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
                T("<b>⑤ 窄带模式:校准激励随带宽缩放,corner 放宽是免费"
                  "余量。</b>23 MHz 探测音在 20 MHz 信道里是带外音——IIP2 "
                  "trim 在噪声上乱走、AGC 扫描读不到 SNR,这是窄带校准失败"
                  "的真正功能性原因,激励频率必须随带宽缩放。corner 方面,"
                  "窄带下 fs≫BW、抗混叠零成本,放到 3×BW/2 把 TX LPF 单项"
                  "地板从 −53 压到 −69 dB、环回 EVM 提升 ~10 dB——实打实的"
                  "余量,但不是悬崖。此条由 20 MHz GUI 运行的异常直接换来。",
                  "<b>⑤ Narrow modes: scale calibration probes with "
                  "bandwidth; a relaxed corner is free margin.</b> A "
                  "23 MHz probe tone is out-of-channel at 20 MHz — the "
                  "IIP2 trim walks on noise and the AGC sweep reads no "
                  "SNR at all; that is the real functional failure of "
                  "narrow-mode calibration, so probe frequencies must "
                  "scale with bandwidth. As for the corner: with fs≫BW "
                  "anti-aliasing costs nothing, and relaxing to 3×BW/2 "
                  "deepens the TX LPF-only floor from −53 to −69 dB and "
                  "buys ~10 dB of loopback EVM — real margin, though not "
                  "a cliff. Paid for directly by an anomalous 20 MHz GUI "
                  "run."),
                T("<b>⑥ 先校准测量仪器,再给电路定规格。</b>最初诊断出的"
                  "\"1.3× corner 在 20 MHz 把 EVM 钉死在 −33 dB\"是测量"
                  "伪影:测试接收机模型的时延补偿用循环 FFT 移位整体前移"
                  "捕获,把 warm-up 样本卷进最后一个符号的 FFT 窗。误差"
                  "正比于滤波器群时延(所以跟着 corner 变!)、反比于 FFT "
                  "长度(所以 320 MHz 看不见、20 MHz 最重),完美伪装成"
                  "物理 ISI 地板;换一个符号数,数字就漂移——这正是暴露"
                  "它的线索。修复(guard 尾垫 + 整数切片 + 仅小数 FFT "
                  "移位)后真实地板在 1.3× 即有 −53 dB。任何随测量配置"
                  "漂移的\"物理结论\"都要先怀疑测量本身。",
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
                  "clue that exposed it. After the fix (cyclic guard "
                  "tail + integer slicing + fractional-only FFT "
                  "advance), the true floor at 1.3× is already −53 dB. "
                  "Any \"physical\" conclusion that drifts with the "
                  "measurement configuration indicts the measurement "
                  "first."),
            )),
    ))
