# 变更记录

版本号语义:`0.x` 期间接口仍可能调整;凡是改动 **cal-state JSON schema**
或 `wifitrx.*` 公开签名的条目都在下面显式标注,交付方按此判断是否需要
重新取包。日期为落地日期。

## 0.6.5 — 2026-08-23

### Android:Reference 资源缺失 + Inspector 内容不全

- **Reference 页 FileNotFoundError**:`assets/schematics/*.svg` 从未打进
  APK——Chaquopy 只装 source dir 里的东西,而 `assets/` 不在其中;且它把
  所有 source dir 平铺进一个根,`asset_path` 的"上一级"布局在端上不成立。
  修复:gradle 新增 `stageAssets`(Sync 仓库 `assets/` 进 srcDir)+
  `asset_path` 认识扁平布局(桌面/exe 路径不变)。
- **Inspector 只显示 findings**:Qt 页有四个区块(findings + 逐步表 +
  残差表 + 溯源表),Android 桥只返回了 findings——两个前端各写各的必然
  漂移。修复:新增 **`app/inspector_data.py`**(Qt-free,`inspector_sections`
  是"检查器显示什么"的唯一定义),Qt 页与桥共用;Android UI 渲染同一套
  表格。decides-nothing 守卫扩到新文件。
- **补上让这两个 bug 溜过的盲区**:端上测试新增
  `referenceAndInspectorRenderOnDevice`(真机/模拟器上实跑 reference_data
  与 inspect_cal_state——此前只测 run 一条路径);桌面新增两项守卫:
  桥返回的 sections 必须逐字等于 `inspector_sections`、gradle 资源暂存
  必须在位。278 测试通过。

## 0.6.4 — 2026-08-23

### 金标对拍通过:端上物理 = 桌面物理

- 模拟器金标 job(run 32618761315,Android 14/x86_64)重放三个代表
  分析(full_cal 80M/256/seed5、rx_evm_sweep 80M、spur_planner 320M),
  与桌面生成的 golden.json 逐指标对拍**全部通过**(0.05 dB / 1e-3
  容差)——numpy 1.19.5 / scipy 1.4.1 / OpenBLAS 0.2.20 的端上栈复现
  桌面物理成立。"构建绿≠物理对"的告诫在 android/README.md 降级为
  已裁决记录;残余告诫仅剩 arm64 ABI 未单独对拍(x86_64 已拍,真机
  功能性运行已验证)。

## 0.6.3 — 2026-08-23

### Android UI 修复:跑完看不到结果图

- `showPage()` 在结果区还处于 `hidden` 时排版 SVG,容器 `clientWidth`
  为 0,图被设成 0 宽——metrics/文本正常、图永远空白(真机第二个
  现场报告)。修复:先取消隐藏再排版,并加视口宽度兜底(旋转/中途
  布局等边缘态下也不会把图排成零宽)。单页结果时保留 Reset view
  按钮(此前随页选择器一起被藏掉)。

## 0.6.2 — 2026-08-23

### Android 端上首报错修复 + 图标

- **真机首跑崩溃修复**:`cal/sync.py` 的 `sig.correlation_lags` 是
  scipy 1.5 新增 API,端上 wheel 是 1.4.1——替换为数学恒等的
  `np.arange(-(len(x)-1), len(y))`(mode="full" 的滞后轴定义),
  276 测试零改动通过。**新增守卫测试**:扫描全仓 scipy 调用面并对照
  "已对 1.4.1 核验"allowlist,未核验的新 scipy 调用在桌面测试就报警,
  不再等装进手机才炸(本次事故的直接教训)。
- APK 启动图标改用与 Windows exe 相同的 `assets/icon.png`
  (五档 mipmap 由同一源图生成)。

## 0.6.1 — 2026-08-23

### Android CI 构建打通(APK 首次在 GitHub Actions 上编译成功)

- 三轮迭代驱动到绿(run 32613192402,1m17s,44 任务):
  ① `--only-binary :all:` 阻止 pip 落到 PyPI sdist 源码编译(scipy
  1.17.1 sdist + "meson not found");② 该开关变探针,证实 Chaquopy
  wheel 仓**无 cp311 scipy**;③ 内嵌 Python 3.11→3.8(源码树预先审计
  3.8 兼容:future annotations 全覆盖、无 match/运行时泛型/3.9+ stdlib)。
- **端上解析版本**:numpy 1.19.5 / scipy 1.4.1 / matplotlib 3.6.0。
  scipy/numpy 低于桌面下限——物理一致性以模拟器金标对拍为准,已在
  `android/README.md` 显著标注。debug APK artifact 71 MB(双 ABI),
  远低于 ~200 MB 预估。

## 0.6.0 — 2026-08-16

### 新交付形态:Android 工作台(`android/`)

- **Chaquopy + WebView 整包**:分析层零改动(`src/wifitrx` +
  `app/specs.py`/`reference.py` 源码打入 APK,PySide6 永不 import),
  Qt 壳换成 Kotlin 薄壳(`MainActivity` WebView + JSON 桥,
  `AnalysisService` 前台服务跑分钟级分析)+ 离线单页 UI(表单由
  `list_specs()` JSON 生成,图形 Agg→SVG 矢量,自写触控平移/缩放——
  对应桌面工具栏)。manifest **不申请 INTERNET 权限**。
- Python 侧唯一新代码 `bridge.py`(JSON 进出、错误以 JSON 返回不崩进程);
  契约由 `tests/test_android_bridge.py` 在桌面主套件钉死。
- 端上金标对拍:`GoldenTest` 在模拟器/真机重放三个代表分析,与桌面生成的
  `golden.json` 逐指标对拍(0.05 dB / 1e-3 容差,不追位一致);
  `android/tools/make_golden.py` 重生成。CI:push 触碰 android/ 构建
  APK,金标 job 手动 dispatch(`.github/workflows/android.yml`)。
- 版本锁:Chaquopy 16.0.0 / Python 3.11 / AGP 8.7.3 / Gradle 8.9 /
  minSdk 24(依据与已知代价见 `android/README.md`:APK ~200 MB、
  320 MHz 端上分钟级+发热有两段式确认护栏、不支持中途取消)。
- 选型决策(否决项)记 `docs/backlog_zh.md` R1。

## 0.5.9 — 2026-08-16

### 计量学(公开行为变化)

- **`metrics.evm` 自拟合偏差修正**:逐音/标量均衡增益由被打分的符号自身
  最小二乘解出,期望吸收 1/N 噪声功率——6 符号帧的 per-tone 读数偏乐观
  0.79 dB、24 符号帧偏 0.18 dB,制式相关的仪器偏差曾把 11n vs 11ax 的
  0.66 dB 占用带宽真实差价抵消成 +0.13 dB。现加 Bessel 型自由度重标
  N/(N−1),读数无偏;**per_tone 要求 ≥2 符号,单符号直接 raise**(原先
  静默返回空洞读数)。全部绝对 EVM 读数因此上移 10·log₁₀(N/(N−1)):
  320 MHz/4096-QAM 验收数 −41.1 → **−40.2 dB**(未校 −25.7,规格 −38
  余量 2.2 dB);重放闭环 gap 两侧同步移动,判决带不变;270 测试零改动
  通过。详见 backlog B14。两份 HTML 教程随实跑数字重建。

## 0.5.8 — 2026-08-16

### 工程基础设施

- **初始化 Project Cairn**(git_policy: track;知识库 provider 暂缓对接;
  文档语言中文;历史处理 inventory_only):新增 `AGENTS.md`(规则与导航
  入口)、`.cairn/config.yaml`(冻结配置)、`cairn/LOG.md`(编年日志,
  含历史知识源清点)、`cairn/ROADMAP.md`(粗粒度镜像,待办权威仍是
  `docs/backlog_zh.md`)。
- 原 `CLAUDE.md` 的项目约定(语言/结构/计量学纪律/验证,17 条规则)
  整体并入 `AGENTS.md`"项目约定"章(中文化);`CLAUDE.md` 改为一行
  `@AGENTS.md` 桩,Claude Code 与 Codex 自此读同一套规则。

## 0.5.7 — 2026-08-15

### 文档

- **设计规格书 `docs/wifitrx_design_spec.docx` 大修至 0.5.6**(此前停在
  v0.1):RX 链框图补显式基带段;损伤表 RX 前端 4 档→8 档、PLL 默认改为
  120 fs 抖动锚定、新增模拟基带行(噪声密度/摆幅规格方式与占位值声明);
  验收表 TX EVM 更新为 P9 伪影修复后的实测 −41.1 dB(未校 −24.5),新增
  重放闭环 gap 行(10 种子 TX −0.45±0.51 / RX +0.42±0.45,±2 dB 判决带);
  设计洞察 4 条补到 10 条;交付接口补残差表六元组 spec、重放闭环、RX 实测
  三件套、stdlib-only 检查器;边界章补占位参数与 PER 门限开口项。
- README:GUI 段更新为七个分析(含基带噪声扫描、密度旋钮、导航工具栏),
  设计洞察补第 10 条(复包络 IM3 组合系数约定,B13)。
- 教程 ch8:RX EVM 扫描补"仅前端/仅基带"两条隔离曲线的说明与结果图
  工具栏说明;两份 HTML 重建。

## 0.5.6 — 2026-08-10

### GUI

- 结果图区补上 matplotlib 导航工具栏(缩放/平移/前进后退/子图边距/
  另存)。图一直是活的 `FigureCanvasQTAgg`(不是 PNG),缺的只是交互
  入口;现在每页图上方都有工具栏,可以框选放大看细节、按住平移、
  Home 一键复位,也可以把当前视图直接另存成 PNG/SVG/PDF。翻页时
  工具栏随画布一起重建,不同页的缩放状态互不串扰。

## 0.5.5 — 2026-08-09

### GUI

- RX EVM 扫描补上噪声三件套的最后一条:**"仅前端热噪声"**(基带密度以
  1e-6 nV 仪器态压掉),与 0.5.4 的"仅基带噪声"对称。至此
  总热噪声 = 前端 ⊕ 基带,三条均为隔离直读,任一输入功率下两个噪声源
  谁主导、差多少 dB 一眼可读;与 Baseband noise sweep 分析同一套仪器态,
  两处读数可互相对拍。基带关闭时图形不变。

## 0.5.4 — 2026-08-09

### GUI

- RX EVM 扫描在 `baseband=True` 时新增第八条隔离曲线**"仅基带噪声"**
  (前端热噪声以 NF=−100 dB 仪器态压掉的直接读数),"thermal only"图例
  改为"thermal only (front-end + baseband)"点明其构成;基带关闭时图形
  不变。实测(80M/1024/25 nV):斜坡区基带噪声比总热噪声低 ~7 dB,
  高输入端随 RF 增益下降逐渐并轨。

## 0.5.3 — 2026-08-09

### GUI

- **新增第七个分析:基带噪声扫描(Baseband noise sweep)**。每个密度
  (5–40 nV/√Hz,quick 档只跑 5/40 端点)一页:该密度重解门限后快速校准,
  画五条隔离曲线(全链已校 / 总热噪声 / 仅前端热噪声 / 仅基带噪声 /
  全关隔离底板)与基带噪声占总 EVM 的功率占比条带;占比在"仅基带读数距
  底板不足 3 dB"的区间打灰色掩码——那里读的是底板(IQ/DC 残差 + LPF ISI),
  记到基带头上就是底板线存在要防的那个错(20M/11ac/n 底板 ~−46 dB,
  25 nV 以下整段归它)。多页机制沿用逐步检查模式的页面选择器。

## 0.5.2 — 2026-08-09

### GUI

- **基带噪声密度成为研究旋钮**:三个校准类分析新增 `bb_noise_nv`
  (5–40 nV/√Hz,5 步进,默认 5;仅在 `baseband=True` 时生效)。口径:
  RF-only 前端**固定按 6 nV 参考拆解**,旋钮只扫基带段本身——同密度拆解会
  悄悄改善 RF 前端以保持级联总值不变,"基带更吵会怎样"就什么都测不到;
  因此 >11 nV 时级联劣于官方表是研究本身而非错误(同密度拆解在那里会直接
  拒绝)。实测(80M/256,state 0):5→40 nV 有效 NF 3.48→5.79 dB,
  −60 dBm 处 RX EVM 劣化 1.1 dB,切换门限随有效 NF 上移(平衡点公式的
  1/3 斜率)。`conditions` 块新增 `bb_noise_v_sqrthz`/`bb_out_swing_vpp`
  (基带开启时)——它改变每个 RX 数字,文件必须记录。

## 0.5.1 — 2026-08-09

### 修正(B13:0.5.0 的 RX 偏差归因是错的)

- **0.5.0 所称"RX 闭合缺调制下失真项(+1.28 dB 系统偏差)"不成立**,予以更正:
  隔离法逐项对拍显示各隔离源与交付数字吻合到 0.7 dB 内,偏差方向实为"多算"。
  真因是 replay 的 IM3 注入配方把**实通带系数(c=8/3·√r)套在复包络立方上**
  ——本模型复包络双音系数为 1,正确常数 c = 2·√r,错配多算 2.5 dB。
- 修正后重扫 10 seed:RX gap +1.28 → **+0.42 ± 0.45**,10/10 consistent;
  RX 容差带收回对称 ±2.0;`apply` 文本明确写出两种包络约定与混用代价
  (交付给用实通带仿真器的同事时,常数要换 8/3)。
- 0.5.0 的 (−1.0, +2.5) 非对称带与"已知遗漏项"说明随之删除;两处归因文字
  (replay 注释、backlog)已更正并保留原记录作对照。

## 0.5.0 — 2026-08-09

### 交付件(B12:RX 侧残差面 + 双视图闭合)

- **cal-state 新增四个 RX 实测键**(schema 扩展,向后兼容):`rx_nf_db`(静默信道
  过整链的有效 NF)、`rx_phase_err_dbc`(跟踪后相位误差,刻意不叫相噪)、
  `rx_im3_dbc`(双音三阶)、`rx_input_dbm`/`rx_gain_state`(测量条件)。此前残差面
  是 TX 偏科的——RX 链路仿真最先要的噪声/相位/失真数字一个都没交付。
- **spec 全表新增 `plane` 字段**,replay 拆成 TX/RX 双视图,各自只施加本平面的键并
  闭合到本平面的实测 EVM。修正 0.4.0 的口径缺陷:RX 镜像曾被计入 PA 口闭合。
- **闭合容差由 10-seed 扫描实测定带**:TX (−2.0, +2.0)(均值 −0.45/σ 0.51);
  RX (−1.0, +2.5)——正侧展宽携带一个**已知且公开声明的遗漏项**:调制下失真
  (ADC 削顶/高斯尾),音类仪器结构性不可见,replay 输出中明文标注,B13 排期交付。
  这正是 replay 环节的本职:又一次抓到"没交付的损伤项"。
- IM3 注入配方:2× 升采样施加立方再限带(1× 下带外产物混叠回带内多算 ~2.5 dB)。
- GitHub:同类工程 wifi_rf_calibration 的三项分析结论已提为 issue #1–#3
  (恒等式闭合 / tx_irr_db 静默丢弃 / 启发式冲突误报)。

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
