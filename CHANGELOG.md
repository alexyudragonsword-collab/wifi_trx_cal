# 变更记录

版本号语义:`0.x` 期间接口仍可能调整;凡是改动 **cal-state JSON schema**
或 `wifitrx.*` 公开签名的条目都在下面显式标注,交付方按此判断是否需要
重新取包。日期为落地日期。

## 0.4.0 — 2026-08-08

### 交付件(B9/B10/B11,来源:对同类工程交付包的分析)

- **cal-state JSON 新增 `residuals` 块**(schema 扩展,向后兼容:旧字段全部
  不动):平铺的交付残差面,每个 `步名.指标名` 键带自己的说明书——
  `unit / meaning / better / role / apply`。`apply` 给公式级注入配方
  (如镜像抑制 → `y = u + g·conj(u)`,`|g| = 10^(−IRR/20)`);`role` 机器可读地
  区分 impairment(可注入)/ figure / condition / total(实测整体,绝不可回注)。
  同一物理量的两次观测(包络检波 vs 环回的 LO 泄漏)以 `duplicates` 数据声明,
  不写散文。新增 `conditions` 块:波形配方 + `adc_backoff_db` + LPF 阶数,
  没有它们收方无法从文件外部重生成激励做核验。
- **新增 replay 对拍**:`python -m wifitrx.handoff replay cal_state.json` 把
  残差表按 `apply` 字面施加到干净波形,与文件自己的 `tx_evm_db` 闭合,输出
  解释 / 实测 / 未解释三个数。**闭合项中禁止任何由实测反解的兜底量**;每个
  键的去向(applied / skipped 带原因 / dropped_duplicate 点名 / no_recipe
  响亮报错)逐项列出。实测:诚实文件 gap +0.55 dB(consistent);把 DPD 残差
  伪造成 −60 dB → gap −8.5 dB 且报出未解释项 −43.8 dB;无 DPD 文件(在带
  失真无条目)必然报 gap——遗漏类缺陷首次可测。
- **cal-state 旁自生成 README.md**:文件清单、测量条件、逐步结果表、残差表、
  消费方式,全部由 JSON 渲染,与数据在结构上不可能漂移。
- 独立检查器(仍 stdlib-only)新增残差面自洽检查:值缺说明 = error、说明缺值
  = warning、重复对提示至多施加其一;GUI 检查器页新增残差表(照旧只渲染
  不判断)。
- 反漂移护栏:任何步骤新增标量指标而不给 spec 条目,
  `tests/test_residual_replay.py` 立即失败(落地当天即抓到
  `group_delay.estimated_ps` 一例)。

## 0.3.2 — 2026-08-03

### 模型 / GUI

- **AGC 门限的锚定带宽提为显式参数**,新增开关 `agc_rebw`(三个校准类分析都有,
  默认关)。关 = 320 MHz 出厂约定(一套寄存器值走天下);开 = 按本次运行带宽
  重解平衡点。
- **⚠ 行为变更**:`baseband=True` 路径此前**恒按运行带宽**重解门限,与
  `rx_hp` 路径的 320 MHz 锚定互相矛盾。现在两条路径都跟随 `agc_rebw`,默认
  320 MHz。B5 的结论不受影响(基带天花板的代价与输入功率无关),但 0.3.0/0.3.1
  里 80 MHz 基带图上的换档位置偏低 2.0 dB。
- **实测**(20 MHz / 4096-QAM):重解后强信号段平均 EVM 好 1.16 dB,锯齿起伏
  从 2.8 dB 收到 1.45 dB,单点最大收益 3.17 dB。落在同一档的点差值恰好 0.00,
  收益全部来自换档位置的改变。各 QAM 平均收益 0.6–1.1 dB;灵敏度不变。

## 0.3.1 — 2026-08-03

### 计量学修正(影响 GUI 分解图的读数,不影响任何交付数字)

- **贡献分解从"功率域相减"改为"隔离法"**:每条曲线是只开该损伤的链路
  直接读数。相减把交叉项 `2Re⟨e_源, e_其余⟩` 记到被减源头上,对确定性
  损伤不可忽略——实测基带天花板在 1.0 Vpp 处交叉项占 **48%**,把它对
  OIP3 的斜率从解析值 −2.00 压到 −1.49 dB/dB。孤立立方原语给出精确的
  −2.00/+2.01,两项拟合的残差 0.14 dB,拟合出的纯失真项与孤立实测差
  0.1 dB。旧口径读天花板 −43.8 dB,新口径 −46.3 dB。
  (先怀疑过 ADC 削顶,旁路 ADC 后斜率不变,假设已证伪。)
- **`RxParams.nonlin_enabled` 现在也管基带压缩**(`BasebandStage.nonlin`
  新增 `enabled` 形参)。此前"关掉非线性"只关得掉逐档 IM3,天花板会漏进
  残余曲线。默认关基带时行为不变。
- **结论未变但更划算**:天花板与天线功率无关、OIP3 是唯一杠杆——这两条
  不受影响;但真实灵敏度是 2 dB/dB,1.0→1.4 Vpp 买 5.8 dB(不是 4.0),
  ADC backoff 每加 1 dB 买 2 dB(不是 1.37)。
- 隔离曲线**不满足功率相加**(确定性源相关,且每条都含隔离底板),图注与
  GUI 文本已写明。

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
