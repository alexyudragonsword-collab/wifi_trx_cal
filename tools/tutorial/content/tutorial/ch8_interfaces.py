"""Chapter 8: the user guide (comm-engineer deliverable interfaces)."""
from __future__ import annotations

from model import Chapter, Code, Section, T, Table

CHAPTER = Chapter(
    id="ch8", title=T("8 使用指南与交付接口", "8 User guide and deliverable interfaces"),
    sections=(
        Section(
            id="use-quickstart", title=T("8.1 安装与最小调用", "8.1 Install and the minimal contract"),
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
            id="use-calstate", title=T("8.2 校准状态文件与独立检查器", "8.2 The cal-state file and the standalone inspector"),
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
            )),
        Section(
            id="use-handoff", title=T("8.3 波形交接与批量回归", "8.3 Waveform handoff and batch regression"),
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
                T("<code>python app/main.py</code>,两个页签。"
                  "<b>Analyses</b>:六个分析(参数表单由声明式 spec 生成)"
                  "——全量校准(结果页 = 四星座:环回前/环回后/TX @ PA 口/"
                  "RX @ 数字口,加 PSD、RX EVM-输入功率曲线与逐步指标;"
                  "校准类分析支持 11ax/be 与 11ac/n 制式、64~4096-QAM)、"
                  "逐步检查模式(每步一页快照 + EVM 三轨迹汇总,多页结果"
                  "带页面选择器;与一口气模式校正逐位一致,由测试钉死)、"
                  "RX EVM 扫描(未校/已校曲线、MCS 需求线、AGC 切换门限、"
                  "实测灵敏度,外加贡献分解:灰线为残余底板(相噪+ISI+"
                  "IQ+ADC),纯热噪声与纯 IM3 曲线由对应开关关断读数与"
                  "残余底板做功率域相减得到,差值低于测量分辨率处留空——"
                  "开关只能关掉热噪声/非线性,残余在每条原始读数里都在,"
                  "不减掉会在低功率端把 IM3 误读成卡在底板上)、"
                  "漂移跟踪、阻塞退敏、杂散规划。"
                  "<b>Cal-state inspector</b>:打开 JSON,渲染检查器结论/"
                  "逐步表/溯源——页面自身不做任何判断,measured by test。",
                  "<code>python app/main.py</code>, two tabs. "
                  "<b>Analyses</b>: six analyses (forms generated from "
                  "declarative specs) — full calibration (result page = "
                  "four constellations: loopback before / loopback after "
                  "/ TX @ PA out / RX @ digital out, plus PSD, the RX "
                  "EVM vs input power curve and per-step metrics; the "
                  "calibration analyses support the 11ax/be and 11ac/n "
                  "standards and 64–4096-QAM), a step-through mode (one "
                  "snapshot page per step plus a three-trajectory EVM "
                  "summary, multi-page results with a page selector; "
                  "corrections bit-identical to the one-shot mode, "
                  "pinned by test), the RX EVM sweep (uncal/cal curves, "
                  "MCS requirement lines, AGC hand-over thresholds, "
                  "measured sensitivity, plus a contribution split: the "
                  "gray line is the residual floor (phase noise + ISI + "
                  "IQ + ADC), and the pure-thermal and pure-IM3 curves "
                  "are obtained by power-domain subtraction of that "
                  "floor from the corresponding switch-off readings, "
                  "blanked where the difference falls below the "
                  "measurement resolution — the runtime switches only "
                  "remove thermal noise / nonlinearity, so every raw "
                  "reading still contains the residual, and without the "
                  "subtraction the low-power IM3 would misread as stuck "
                  "on the floor), drift tracking, blocker desense and "
                  "spur planning. "
                  "<b>Cal-state inspector</b>: open a JSON and read the "
                  "inspector's findings / step table / provenance — the "
                  "page itself decides nothing, and a test enforces "
                  "that)."),
            )),
    ))
