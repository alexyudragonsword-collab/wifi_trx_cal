"""Chapter 8: the user guide (comm-engineer deliverable interfaces)."""
from __future__ import annotations

from model import Chapter, Code, Section, T, Table

CHAPTER = Chapter(
    id="ch8", title=T("8 使用指南与交付接口", "8 User guide and deliverable interfaces"),
    sections=(
        Section(
            id="use-quickstart",
            title=T("8.1 安装与最小调用", "8.1 Install and the minimal contract"),
            body=(
                T("<code>pip install -e .</code>(GUI 需要 "
                  "<code>pip install -e '.[gui]'</code>;库、CLI 与独立检查器"
                  "都不依赖 Qt)。最小调用:",
                  "<code>pip install -e .</code> (the GUI needs "
                  "<code>pip install -e '.[gui]'</code>; the library, CLI "
                  "and standalone inspector need no Qt). The minimal "
                  "contract:"),
                Code("import numpy as np\n"
                     "from wifitrx.chain import (TxChain, TxParams, RxChain,"
                     " RxParams,\n                            LoopbackPath,"
                     " run_loopback)\n\n"
                     "bw, fs = 320e6, 320e6 * 4\n"
                     "rng = np.random.default_rng(1)\n"
                     "tx = TxChain(TxParams(bandwidth_hz=bw).randomize(rng),"
                     " fs)\n"
                     "rx = RxChain(RxParams(bandwidth_hz=bw).randomize(rng),"
                     " fs)\n\n"
                     "x = np.load('your_11be_waveform.npy')  # digital FS,"
                     " rms ~0.1-0.15\n"
                     "y_pa = tx(x)                    # sqrt(mW) @ PA out\n"
                     "cap = run_loopback(tx, rx, x,\n"
                     "                   LoopbackPath(atten_db=40.0,"
                     " delay_ns=6.0))"),
                Table(header=(T("波形要求", "Waveform requirement"),
                              T("值", "Value")),
                      rows=(("fs", "bandwidth × oversampling (DPD/ACLR: 4)"),
                            ("amplitude", "|I|,|Q| ≤ 1, rms 0.10–0.15"),
                            ("dtype", "numpy complex128, 1-D"),
                            ("frame", "arbitrary (model is frame-agnostic)")),
                      ),
            )),
        Section(
            id="use-calstate",
            title=T("8.2 校准状态文件与独立检查器",
                    "8.2 The cal-state file and the standalone inspector"),
            body=(
                T("<code>save_cal_state()</code> 产出的 JSON 是核心交付物:"
                  "全部数字校正 + 模拟调谐码(仅凭文件即可恢复芯片编程)、"
                  "逐步结果(passed / saturated / 内嵌 spec)、溯源与 expiry"
                  "(温度有效窗 + 最小重校计划)。三种方式读它,结论同源:",
                  "The JSON from <code>save_cal_state()</code> is the core "
                  "deliverable: every digital correction plus the analog "
                  "tuning codes (the file alone restores the chip), "
                  "per-step results (passed / saturated / embedded spec), "
                  "provenance and expiry (temperature validity window + "
                  "minimal recal plan). Three ways to read it, one set of "
                  "verdicts:"),
                Code("python -m wifitrx.handoff inspect cal_state.json\n"
                     "# or copy src/wifitrx/handoff/inspector.py next to"
                     " the JSON:\n"
                     "python inspector.py cal_state.json   # stdlib-only\n"
                     "# or the GUI tab: Cal-state inspector"),
                T("检查器以文件<em>内嵌的 spec</em> 为判据——旧文件按其校准"
                  "当时的规格判定,而不是按库的当前表;这保证半年后检查一个"
                  "旧交付包时,报出的是文件的问题而不是库的演进。",
                  "The inspector judges against the spec <em>embedded in "
                  "the file</em> — an old file is held to the spec it was "
                  "calibrated to, not the library's current table, so "
                  "inspecting a six-month-old bundle reports the file's "
                  "problems, not the library's evolution."),
                T("文件还平铺一份<b>残差面</b>:每个校后残差(镜像抑制、"
                  "LO 泄漏、DC、IIP2……)带着自己的说明书同行——单位、含义、"
                  "大小方向,以及最要紧的 <code>apply</code>:链路仿真"
                  "<em>怎么注入</em>这个数(镜像抑制按增益失衡注入和按正交"
                  "误差注入,同一个 dB 出来的星座不一样)。配套的对拍命令 "
                  "<code>python -m wifitrx.handoff replay cal_state.json</code> "
                  "把残差表按 apply 字面施加到干净波形上,与文件自己的实测 "
                  "TX EVM 闭合,输出三个数:解释 / 实测 / 未解释。这是唯一"
                  "能抓<b>遗漏</b>的检查——没交付的损伤项,逐项评审永远看"
                  "不见;闭合项里禁止任何由实测反解的兜底量(有则闭合是"
                  "恒等式,伪造的文件也能全过——这是同类工程用实测教的"
                  "反面课),每个键的去向逐项点名,不静默。JSON 旁另有一份"
                  "由数据自生成的 README,说明与数据在结构上不可能漂移。",
                  "The file also carries a flat <b>residual surface</b>: "
                  "every post-cal residual (image rejection, LO leakage, "
                  "DC, IIP2…) travels with its own specification — unit, "
                  "meaning, which direction is better, and above all "
                  "<code>apply</code>: <em>how a link simulation "
                  "injects</em> the number (an image-rejection figure "
                  "applied as a gain imbalance and the same dB applied "
                  "as a quadrature error give different constellations). "
                  "The companion cross-check, <code>python -m "
                  "wifitrx.handoff replay cal_state.json</code>, applies "
                  "the residual list literally to a clean waveform and "
                  "closes it against the file's own measured TX EVM, "
                  "reporting three numbers: explained / measured / "
                  "unexplained. It is the only check that catches an "
                  "<b>omission</b> — an impairment never shipped is "
                  "invisible to per-entry review; no term in the closure "
                  "may be solved from the measured EVM (with one, "
                  "closure holds by construction and a falsified file "
                  "passes — a lesson a peer project taught by "
                  "measurement), and every key's fate is named rather "
                  "than silent. A README generated from the JSON sits "
                  "beside it, structurally unable to drift from the "
                  "data."),
            )),
        Section(
            id="use-handoff", title=T("8.3 波形交接与批量回归",
                                      "8.3 Waveform handoff and batch regression"),
            body=(
                T("波形走 <code>wifitrx-wave-v1</code>(.npz:iq + 元数据,"
                  "带采样率/幅度/NaN 校验);单波形与目录级批量:",
                  "Waveforms travel as <code>wifitrx-wave-v1</code> (.npz: "
                  "iq + metadata, with rate/amplitude/NaN validation); "
                  "single-shot and directory-level batch:"),
                Code("python -m wifitrx.handoff run --wave wave.npz "
                     "--bw 320e6 --scenario loopback\n"
                     "python -m wifitrx.handoff regress --dir waves/ "
                     "--bw 320e6   # -> handoff_report.md"),
                T("scenario 三选:tx_only(PA 输出)/ loopback / rx_only。"
                  "regress 产出双方各填一列的指标对账单。电路数据接入"
                  "(PA 谐波平衡、LPF AC、PLL 相噪 CSV)见 "
                  "docs/circuit_data_zh.md,模板在 circuit_data/。",
                  "Three scenarios: tx_only (PA output) / loopback / "
                  "rx_only. regress produces the reconciliation sheet with "
                  "one column per party. Circuit-data import (PA harmonic "
                  "balance, LPF AC, PLL phase-noise CSVs) is documented in "
                  "docs/circuit_data_zh.md with templates under "
                  "circuit_data/."),
            )),
        Section(
            id="use-gui", title=T("8.4 GUI 工作台", "8.4 The GUI workbench"),
            body=(
                T("<code>python app/main.py</code>,三个页签。"
                  "<b>Analyses</b>:七个分析(参数表单由声明式 spec 生成)"
                  "——全量校准(结果页 = 四星座:环回前/环回后/TX @ PA 口/"
                  "RX @ 数字口,加 PSD、RX EVM-输入功率曲线与逐步指标;"
                  "校准类分析支持 11ax/be 与 11ac/n 制式、64~4096-QAM,"
                  "外加三个 what-if 开关:<code>rx_hp</code>(逐档 NF −1、"
                  "IIP3 +2)、<code>baseband</code>(显式基带段,见 3.5;"
                  "输入参考噪声密度 5–40 nV/√Hz 可调,RF-only 前端按 "
                  "6 nV 参考拆解后保持不变,扫的是基带本身)、"
                  "<code>agc_rebw</code>(切换门限按本次带宽重解,而不是"
                  "沿用 320 MHz 锚定的出厂表,见洞察⑨))、"
                  "逐步检查模式(每步一页快照 + EVM 三轨迹汇总,多页结果"
                  "带页面选择器;与一口气模式校正逐位一致,由测试钉死)、"
                  "RX EVM 扫描(未校/已校曲线、MCS 需求线、AGC 切换门限、"
                  "实测灵敏度,外加<b>按隔离法</b>做的贡献分解:每条曲线是"
                  "只开该损伤的链路直接读数,不做相减。相减(全量减去关掉"
                  "某源)会把交叉项 2Re⟨e_源,e_其余⟩ 记到该源头上,对确定性"
                  "损伤(IM3、基带天花板、ISI 同源于信号)一点都不小——"
                  "实测基带天花板在 1.0 Vpp 处交叉项占 48%,把它对 OIP3 的"
                  "斜率从解析值 −2.0 压到 −1.5 dB/dB。IQ/DC/LPF 在每条曲线里"
                  "都保持开启:它们的校正是减法型的,只关注入不关校正会引入"
                  "等量反向误差,剩下的就是隔离底板。各条隔离曲线<b>不满足"
                  "功率相加</b>)、"
                  "基带噪声扫描(每个密度一页:门限按该密度重解的五条"
                  "隔离曲线 + 基带噪声占比,底板主导区打灰色掩码)、"
                  "漂移跟踪、阻塞退敏、杂散规划。"
                  "<b>Cal-state inspector</b>:打开 JSON,渲染检查器结论/"
                  "逐步表/溯源——页面自身不做任何判断,measured by test。"
                  "<b>Reference</b>:本教程的信号链框图(随包交付的 SVG)、"
                  "校准顺序表、依赖图与逐边理由表、AGC 档位表与损伤参数表——"
                  "全部由 <code>wifitrx.cal.reference</code> 与参数类现算,"
                  "与本文档同源;跑完一次校准后,顺序表的验收列与捕获成本表"
                  "自动填入本次实测值。",
                  "<code>python app/main.py</code>, three tabs. "
                  "<b>Analyses</b>: seven analyses (forms generated from "
                  "declarative specs) — full calibration (result page = "
                  "four constellations: loopback before / loopback after "
                  "/ TX @ PA out / RX @ digital out, plus PSD, the RX "
                  "EVM vs input power curve and per-step metrics; the "
                  "calibration analyses support the 11ax/be and 11ac/n "
                  "standards and 64–4096-QAM, plus three what-if "
                  "switches: <code>rx_hp</code> (per-state NF −1, "
                  "IIP3 +2), <code>baseband</code> (the explicit "
                  "baseband stage, see 3.5, its input-referred noise "
                  "density adjustable 5–40 nV/√Hz — the RF-only front "
                  "end is de-embedded at the 6 nV reference and held "
                  "fixed, so the sweep exercises the baseband itself) "
                  "and <code>agc_rebw</code> "
                  "(re-solve the hand-over thresholds at this run's "
                  "bandwidth instead of inheriting the 320 MHz-anchored "
                  "factory table, see insight ⑨)), a step-through mode (one "
                  "snapshot page per step plus a three-trajectory EVM "
                  "summary, multi-page results with a page selector; "
                  "corrections bit-identical to the one-shot mode, "
                  "pinned by test), the RX EVM sweep (uncal/cal curves, "
                  "MCS requirement lines, AGC hand-over thresholds, "
                  "measured sensitivity, plus a contribution split "
                  "<b>by isolation</b>: each curve is the chain with "
                  "only that impairment active, read directly. "
                  "Subtracting instead (full chain minus one source) "
                  "charges that source with the cross term "
                  "2Re⟨e_source, e_rest⟩, which is not small for the "
                  "deterministic impairments — IM3, the baseband "
                  "ceiling and ISI all derive from the same signal. "
                  "Measured: at 1.0 Vpp the cross term is 48% of the "
                  "extracted baseband ceiling and flattens its OIP3 "
                  "slope from the analytic −2.0 to −1.5 dB/dB. IQ, DC "
                  "and the LPF stay on in every curve because their "
                  "corrections are subtractive — removing the injection "
                  "while keeping the correction would inject an equal "
                  "and opposite error — and what remains is the "
                  "isolation floor. Isolated curves are <b>not "
                  "power-additive</b>), the baseband-noise sweep (one page "
                  "per density: five isolation curves with "
                  "thresholds re-solved for that density, "
                  "plus the baseband share with the floor-"
                  "dominated region masked), drift tracking, "
                  "blocker desense and spur planning. "
                  "<b>Cal-state inspector</b>: open a JSON and read the "
                  "inspector's findings / step table / provenance — the "
                  "page itself decides nothing, and a test enforces "
                  "that. <b>Reference</b>: this tutorial's signal-chain "
                  "diagrams (shipped as SVG assets), the calibration "
                  "order, the dependency graph with its per-edge reason "
                  "table, the AGC ladder and the impairment parameters — "
                  "all derived live from <code>wifitrx.cal.reference</code> "
                  "and the parameter classes, the same sources this "
                  "document uses; after a calibration run the order "
                  "table's acceptance column and the capture-cost table "
                  "fill in with that run's own measurements)."),
            )),
    ))
