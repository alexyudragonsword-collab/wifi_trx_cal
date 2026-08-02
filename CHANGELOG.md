# 变更记录

版本号语义:`0.x` 期间接口仍可能调整;凡是改动 **cal-state JSON schema**
或 `wifitrx.*` 公开签名的条目都在下面显式标注,交付方按此判断是否需要
重新取包。日期为落地日期。

## 0.3.0 — 2026-08-02

### 模型

- **模拟基带(LPF/VGA/ADC 驱动)可显式建模**(B5,默认关):
  `RxParams.baseband` 按电路口径描述——输入参考噪声电压密度(V/√Hz)与
  输出摆幅(Vpp),而不是 NF/IIP3。噪声注入在 LPF 之前、压缩施加在 VGA 之后
  (输出参考天花板)。开启前须用 `link.budget.deembed_states` 把官方档位表
  (级联总值)拆成 RF-only 值,否则噪声重复计算。
- 新增 `link.budget` 的 `baseband_equivalent_stage / effective_nf_db /
  effective_iip3_dbm / deembed_states`,以及 `link/baseband_study.py`
  (VGA 摆动与 ADC backoff 两个扫描)。
- `units` 增加 `R_REF_OHM` 与电压↔dBm 换算(此前参考阻抗是隐含的)。
- **结论**:`adc_backoff_db` 从自由参数变成有价参数——1.0 Vpp 输出摆幅下
  最优 backoff 从 ~10 dB 推到 ≥18 dB,当前 12 dB 要多付约 2.6 dB EVM。
  详见 `docs/backlog_zh.md` B5 的实测记录。

## 0.2.0 — 2026-08-02

### 交付格式(需要接收方留意)

- **cal-state JSON 新增 `results[].cost`**(`{captures, samples}`):每步
  的捕获开销随包交付,产测方可据此排时间预算。旧文件缺此字段,检查器
  照常工作。
- **cal-state JSON 新增顶层 `fs_hz`**:`cost.samples` 的分母。没有它,
  "样本数"无法换算成测试时间。`save_cal_state(..., fs_hz=...)` 新增可选
  参数,GUI 与两个 example 已传入。
- **移除 `wifitrx.cal.LMSGainCal / SignSignLMS / LUTCal`**(`cal/loops.py`)。
  从 pll_simulator 搬来后全项目零调用,且 docstring 声称的收敛断言在本
  仓库并不存在。链路内实际使用的跟踪环是 `cal/tracking.py`(导频环)与
  `cal/dpd_tracking.py`(RLS DPD)。

### 模型

- **RX AGC 改为官方 8 档表**(增益 37→−5 dB、NF 3.5→34 dB、
  IIP3 −20→+12 dBm),切换门限按噪声-IM3 平衡解出;校准观测钉档迁到
  NF=22 档。320 MHz 工作点 RX EVM −36.6 → −40.0 dB。
- **RX DC 改为两级校正**:逐档模拟微调 DAC(基带节点,±0.064 √mW /
  2e-3 步进)+ 数字细调(按基带节点参考存储,运行时按 VGA 换算)。
  修复了高增益下模拟 DC 打饱和 ADC 的失锁;20 MHz 低 MCS 灵敏度首次与
  Friis 闭合(MCS0 −95.8 dBm,Δ−0.3)。
- **LO 相噪剖面锚定 120 fs rms jitter**(10 kHz–100 MHz @6 GHz,
  IPN −46.9 dBc)。
- **RX IIP2 校准改用双电平分离**:每个 trim 码在相差 6 dB 的两个耦合
  衰减下各测一次并复比值相减,消掉 DAC 偶阶失真的透传背景(此前 320 MHz
  下整个码域只剩 ~1 dB 起伏、trim 落点偏 18 码)。
- 环回耦合衰减按带宽取推荐值(320 MHz→34 dB,其余 40 dB);DPD 观测固定
  用冷耦合点(≥40 dB),避免 RX 自身 IM3 被学进预失真器。

### 计量学修正(影响此前所有窄带结论)

- 时延补偿曾用循环 FFT 移位,把 warm-up 样本卷进最后一个 OFDM 符号的
  FFT 窗——误差正比于群时延、反比于 FFT 长度,完美伪装成"corner 越紧
  ISI 越大"。修复为循环 guard 尾垫 + 整数切片 + 仅小数部分移位
  (`compensate_delay`),并让 `tx_evm` 多发一个 padding 符号、只对内部
  符号打分。基于伪影数据定下的窄带 3× corner 策略随之撤销,全带宽统一
  1.3×(TX)/1.12×(RX)。

### 工具与交付物

- **GUI 新增 Reference 页签**:信号链框图、校准顺序表、依赖图(逐边物理
  理由)、AGC 档位表、损伤参数表;跑完校准或打开 cal-state 后,顺序表的
  验收列与捕获成本表填入实测值。
- GUI RX EVM 扫描增加 AGC 门限标注与贡献分解(纯热噪声 / 纯 IM3 由功率
  域相减得到);新增"RX 高性能"假设开关(逐档 NF −1 dB、IIP3 +2 dB,
  门限重解);校准类分析支持 11ac/n 制式与 64-QAM;新增逐步检查模式。
- 图文教程 `docs/tutorial.html` 与开发说明 `docs/devguide.html`(中英双语
  可切换,单文件离线);构建确定性化,重建除溯源时间戳外字节一致。
- 新增 `tools/build_assets.py`:框图预渲染为 `assets/schematics/*.svg`,
  GUI 与 exe 不再需要 schemdraw。

### 工程

- 接入 ruff(pycodestyle + pyflakes)与覆盖率门槛(≥85%,当前 92.5%);
  CI 快档跑 lint + 非慢速测试,夜跑全量 + 覆盖率 + **校验已提交的 HTML
  与资产没有落后于代码**。
- 新增模块可达性护栏:任何 tests/examples/tools/app 都无法经 import 到达
  的模块必须给出调用者、测试或删除。
- 补齐交付面测试(plotting / units / CFR / preamble 估计器 /
  `python -m wifitrx.handoff` CLI),这些此前覆盖率为 0–25%。

## 0.1.0

首个完整版本:复基带收发器行为模型 + 14 步校准序列 + 交付闭环
(cal-state JSON、独立检查器、波形交接与批量回归、GUI 工作台、
Windows exe)。详见 README 与 `docs/`。
