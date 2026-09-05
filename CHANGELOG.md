# 变更记录

版本号语义:`0.x` 期间接口仍可能调整;凡是改动 **cal-state JSON schema**
或 `wifitrx.*` 公开签名的条目都在下面显式标注,交付方按此判断是否需要
重新取包。日期为落地日期。

## 0.7.10 — 2026-09-05

### `pn_cpe_study` 第四页:两制式并排(误差功率堆叠)

- **需求**:用户问"同为 40 MHz、导频 CPE + LTF 估计条件下,11ac 与 11ax 谁的
  EVM 更差",先以临时图回答,再要求进 GUI。
- **做法**:同带宽、同 LO 配置下,对本次制式与另一制式各取出货谱下的四配置
  读数,按**误差功率**(不是 dB——dB 不能叠)堆叠:ICI 地板(②)、LTF 冻结
  误差增量(③−②)、导频估计噪声增量(④−③),每段顶边就是对应配置的直接
  读数,虚线为不去 CPE 的读数(①)。11ac/n 在 160 MHz 以上无定义,320 MHz
  时只画 11ax 一根并在标题注明。新增指标 `evm_pilot_cpe_11ac_db` /
  `evm_pilot_cpe_11ax_db` / `std_gap_db`(11ax − 11ac,配置 ④)。
- **实测(40 MHz,单 LO,32 帧)**:11ac −43.18 vs 11ax −41.77 dB,**11ax 差
  1.4 dB**。①两边相同(总相噪一样),差别几乎全在 CPE 买回多少(1.55 vs
  0.36 dB);LTF 冻结误差两边比例持平(+2.1 / +2.0 dB),但因 11ax 地板更高
  绝对量更大;导频项最薄(+0.26 / +0.51 dB)。TX+RX 双 LO 等比 +3 dB,结构
  不变。**注意**:40 MHz 两制式导频都是 6 个,不是 8 个。
- **散布提醒**:LTF 冻结误差按帧不按符号平均,8 帧时两制式差值 ±0.4 dB rms
  (同一 40 MHz 点 8 帧读 0.6 dB、32 帧读 1.4 dB);页内文字注明,要下结论用
  32 帧。
- **守卫**:第四页存在且是末页;本制式的 ④ 与 `evm_pilot_cpe_db` 一致;
  80 MHz 默认种子下 `std_gap_db` 在 0.8–2.5 dB 且等于两制式 ④ 之差。金标
  `golden.json` 重生成(新增三指标、页数 3→4),端上条数不变。
- **裁决(run #51)**:三 job 全绿——解释版与编译版端上均 5 run / 0 failed /
  0 skipped,金标按 4 页 / 18 指标通过;编译版 wheel 打 0.7.10、52 模块导出
  检查通过。

## 0.7.9 — 2026-09-05

### EVM 预算的 CPE 追踪份额改由物理算出(用户裁决,交付数字变动)

- **改动**:`link/evm_budget.py::EvmBudget.cpe_tracked_fraction` 默认值由硬编码
  0.5 改为 `None` → 按 LO 谱与符号长度用 `cpe_partition()` 现算(新增字段
  `lo_profile` / `t_fft_s` / `pn_band_hz`,默认出货谱、11ax 12.8 µs、
  10 kHz–100 MHz——与 `ipn_rad2` 同一积分带,份额与总量不能各取各的带宽);
  显式传数仍优先。新增模块级 `cpe_tracked_fraction()` 与
  `report()["cpe_tracked_fraction"]`。**公开签名变化**:字段默认值与类型
  (`float` → `float | None`),既有调用方不传该参即自动改用物理值。
- **数字**:出货谱 + 11ax 追踪份额 **5.48%**(11ac 27.8%),预算相噪项由
  ipn·0.5 变为 ipn·0.945,**+2.7 dB**;`examples/run_link_budget.py` 的五项
  RSS 预测 EVM 由 −40.3 → **−39.5 dB**,4096-QAM 裕量由 2.3 → **1.5 dB**
  (其余四项不变:SNR 45、IRR 52、PA NMSE −45、SQNR 55)。
- **为什么不是保留 0.5**:0.7.8 的 `pn_cpe_study` 用时域模型与闭式解两条路
  对上了同一个数——12.8 µs 符号下 CPE 只管 35 kHz 以下,这类 PLL 的噪声都在
  其上。0.5 是早期"环内噪声大半被追掉"的估计,对 3.2 µs 符号勉强、对
  WiFi 7 数制差 9 倍。
- **守卫**:默认份额 == `cpe_partition` 同带同符号的值(实测 0.0548)、
  11ac 数制 > 3.5×、显式 0.5 相对物理值恰差 −2.7 dB(变异把默认改回 0.5
  即红)。
- **两端**:`src/wifitrx/link` 随 APK 出货但无金标案例消费;金标 job 按规则
  重新 dispatch:**run #49 三 job 全绿**,解释版与编译版端上均 5 run / 0 failed /
  0 skipped(含四金标案例),编译版 wheel 打 0.7.9、52 模块导出检查通过。

## 0.7.8 — 2026-09-04

### 新增分析:LO 相噪 vs CPE 去除(四种测量配置的隔离研究)

- **起因**:讨论"基带在信道估计/CPE 去除过程中会不会因 LO 相噪引入额外
  误差"时发现,本模型的 `correct_cpe()` 是 genie 估计器(全部子载波对理想
  参考做 LS 相位),EVM 均衡器又是对被测点自拟合、不走 LTF——于是"信道估计
  被相噪污染"与"导频估计噪声共模注入"两条机理在模型里**结构性不可见**。
  本版把这件事做成可量的东西,而不是留在讨论里。
- **`pn_cpe_study`**(`app/specs.py`,两端共用注册表):相噪是唯一损伤
  (隔离法,真信道恒为 1,配置 1/2 不用均衡器、无自拟合自由度偏差),四种
  配置直接读数:① 不去 CPE;② genie CPE;③ genie CPE + 收到的 LTF 信道
  估计;④ N_p 导频估 CPE + LTF 估计(modem 形态)。三页:LO 谱按
  `1 − sinc²(f·T_FFT)` 权重拆成 CPE 可去除/ICI 两部分;type-II PLL 家族
  扫环路带宽(rms jitter 最优 vs 去 CPE 后 EVM 最优);四配置随相噪电平扫描,
  配置 1/2 叠加闭式解 ∫S_φ df 与 ∫S_φ·[1 − sinc²] df 做对拍。
- **实测(80 MHz / 11ax,单 LO,8 帧)**:配置 1/2 读数 −43.94 / −44.22 dB,
  闭式解 −43.81 / −44.10 dB(残差 0.13 / 0.12 dB,单帧散布 ~0.3 dB rms)——
  模型的 ICI 加权与 PSD 约定(DSB)对得上;**CPE 只买回 0.29 dB**(12.8 µs
  符号下 CPE 可去除带宽 35 kHz,只追掉出货 LO 谱 6.6% 的相位功率;11ac 的
  3.2 µs 符号是 138 kHz / 28.7%,买回 1.66 dB);**LTF 信道估计的冻结 ICI
  使相噪 EVM 贡献再 +1.74 dB**(不随符号数平均,两次 LTF 平均后仍如此);
  8 导频 CPE 再 +0.33 dB(320 MHz 32 导频时 0.03 dB)。
- **一条被自己的数据推翻的判断**:讨论时我说"PLL 环路带宽的去 CPE 后 EVM
  最优点与最小 rms jitter 最优点不是同一个"。对 11ax/be 数制**不成立**:
  type-II 家族(平台 −104.1、VCO −116.1 dBc/Hz@1 MHz)两者同在 300 kHz,
  差 0.00 dB;对 11ac/n 才成立(300 vs 139 kHz,差 0.58 dB)。原因就是上一条:
  35 kHz 以下 CPE 才管得着,而这类 PLL 的噪声都在其上。详见 backlog B15。
- **顺带暴露**:`link/evm_budget.py::EvmBudget.cpe_tracked_fraction` 默认 0.5
  ("modem 追掉一半相位功率")——按出货谱与 11ax 数制实算是 **6.6%**,预算表
  的相噪项因此**乐观约 2.7 dB**。本版未改默认值(改它会动交付数字,须用户
  裁决),`cpe_partition()` 已提供按谱与符号长度算出的准确值。
- **公开接口变化**(向后兼容):`impairments.phase_noise` 新增
  `ici_weight()`、`cpe_partition()`、`TypeIIPllPhase`;`metrics.cpe` 新增
  `correct_cpe_pilots()`;`waveform.preamble.build_frame()` 新增可选
  `data=` 形参。cal-state schema 不变。
- **守卫**(全部经变异验证会红):闭式分解对白噪声 PSD 的 sinc² 积分恒等式;
  11ax vs 11ac 的 CPE 可去除比例 4× 关系;type-II 环路带宽即 |H|² 的 −3 dB
  点(首稿把远端滚降写成 −40 dB/dec,实为 −20 dB/dec——type-II 的零点决定,
  测试文档里留了这条纠错);研究级:模型读数对闭式解 ±0.3 dB、四配置单调
  (② ≤ ①、③ 比 ② 高 1–3 dB、④ > ③)、导频估计器全音时与 genie 逐位一致。
- **Android**:金标案例由三个增为四个(`pn_cpe_study` 80M/2 帧——numpy
  Generator + irfft 合成 + `np.sinc` 闭式,是桌面守卫核不到的端上物理面),
  `golden.json` 重生成;端上测试条数不变(5)。**run #44**:解释版金标
  5/5 通过(含第四案例);编译版当轮未跑到——见下一条。

### CI:APK 上传撞存储配额不得掩盖端上裁决

- run #44 两个 flavour 的 `upload-artifact` 均报 "Artifact storage quota has
  been hit"(GitHub 账户级配额,每 6–12 小时重算,与本仓代码无关),而编译版
  的上传步骤排在模拟器之前——上传一失败,编译版**唯一的物理检查被跳过**,
  job 红的原因却是存储记账。改法:两处上传 `continue-on-error: true`(APK
  下载是便利,不是门禁),编译版上传移到 `on-device tests actually ran` 之后,
  保留期 14→7 天以少吃配额;桌面守卫断言顺序与非致命标记(匹配干活的行,
  变异 3 处已红)。
- **裁决(run #47,修后重跑)**:三个 job 全绿——编译版端上 5 run / 0 failed /
  0 skipped(含第四金标案例),wheel 打 0.7.8、52 模块导出检查通过;解释版
  同样 5/5。0.7.8 的两种出货形态至此都验过。

## 0.7.7 — 2026-08-25

### Android 编译版:交叉编译出的 `.so` 不导出 `PyInit_*`(根因与守卫)

- **症状**:编译版 APK 构建全绿、`--native` 门禁通过、wheel 里 52 个 `.so`
  一个不少,端上 import 却报
  `dynamic module does not define module export function (PyInit_sync)`。
- **根因**(已在本机用两版头文件证明,非推测):`android_wheel.py` 用
  `-fvisibility=hidden` 编译,而 **CPython 3.8 的 `PyMODINIT_FUNC` 不带
  可见性属性**——Python 3.9 才通过 `Py_EXPORTED_SYMBOL` 给它加上
  `visibility("default")`。Chaquopy 的 Android target 正是 3.8,于是
  模块初始化函数被隐藏;而宿主机是 3.11,同一份代码编出来的 wheel
  `nm -D` 看得到 `PyInit_evm`。**宿主构建复现不了这个 bug,两边头文件不同。**
  修法:命令行显式 `-DPyMODINIT_FUNC=__attribute__((visibility("default")))
  PyObject*`(该宏在每个 CPython 里都由 `#ifndef` 兜底,不会与头文件冲突)。
- **更正一条早先的判断**:上一版把同类失败(`PyInit_cal`)归因于"扩展模块
  当包初始化器被 Chaquopy 导入器拒绝",并据此不再编译 `__init__.py`。
  那个归因是错的——真因就是本条。不编译 `__init__.py` 的改动本身仍保留
  (re-export 壳编译了也没保护价值),但理由已在
  `android/tools/android_wheel.py` 文件头更正。
- **两道守卫**:
  - 桌面侧断言构建器**实际拼出的命令行**(不是文件文本):
    `-fvisibility=hidden` 出现时必须同时出现带 `visibility("default")` 的
    `-DPyMODINIT_FUNC=`(经变异验证会红);
  - CI 侧新增 `android/tools/check_wheel_exports.py`,用 NDK 自带 `llvm-nm`
    逐个检查 wheel 内**每一个** `.so` 是否导出 `PyInit_<模块名>`——出货件
    上的物理检查,在装模拟器之前二十分钟就能否掉。
- **裁决**:编译版端上金标 5/5 通过(0 失败 0 跳过),含
  `GoldenTest.metricsMatchDesktopGolden`。至此编译版与解释版同为可交付形态;
  wheel 内 52 个 `.so`(每 ABI)全部通过导出检查。

### 顺带修掉两件在同一轮里暴露出来的事

- **两处构建暂存目录被误提交进仓库**:`build-android-wheel/`(197 个文件
  7.7 MB,混在 0.7.6 的 `git add -A` 里)与 `build/`(setuptools 暂存,
  96 个文件,0.7.5 混进去的)。前者**不是占地方而已**:`android_wheel.py`
  会缓存一个"参考 wheel"来取 dist-info,于是这个陈旧副本让编译版的
  METADATA 冻在 0.7.6——连续两个版本的 wheel 都打着 0.7.6 的名字与依赖表
  出货,而仓库里 `pyproject.toml` 早已是 0.7.7。两者均已 `git rm --cached`
  并加进 `.gitignore`;CI 增一步断言 wheel 文件名必须带 `pyproject.toml`
  里的版本号(匹配与不匹配两个方向都本地验过)。
- **模块数更正**:0.7.6 条目写的"57 个模块"是把 5 个包 `__init__.py` 一并
  算了,而那一版恰好开始不编译它们;实际为 **52**(CI 日志
  `cythonised 52 modules`,导出检查 52 × 2 ABI 全过)。

## 0.7.6 — 2026-08-25

### Android:并出一个编译版 APK(wifitrx 以 .so 出货)

- 现有解释版不动,新增 `compiled` product flavor:`wifitrx` 不再以源码进包,
  改由 `android/tools/android_wheel.py` 交叉编译成**逐 ABI 的 wheel**,
  57 个模块为 `.so`。**编译版的 srcDirs 必须不含 `../../src`**——源码目录的
  导入优先级高于 site-packages,漏进去就会遮蔽全部 `.so`,产出一个"自以为
  编译过"的解释版,而构建日志对此只字不提(已加守卫,经变异验证)。
- **两个必须钉死的前提**(都是实测,不是推测):
  - **Cython 3.3.0 不可用**——在虚数字面量上编译器崩溃(`ImagNode` →
    `AttributeError`),而本仓是复基带、`1j` 遍地;3.0.11 与 3.1.6 验证可用,
    CI 钉 `cython<3.3`。
  - **必须 `-X annotation_typing=False`**——cythonise 会把 Python 类型标注
    变成运行时强制的 C 类型,而本仓标注是描述性的、numpy 标量四处流动:
    `max_db: float | None` 会拒收 `metrics/ccdf.py` 赋给它的 `np.float64`。
    首次编译后全量测试 291 过 / **2 败**即此;加该选项后 **293 全过**。
    修法是让编译器别把标注当类型,而不是改分析层去迁就打包需求。
- **两个脚本 vendoring 进仓库**(`android/tools/android_wheel.py` /
  `inspect_apk.py`,出处与本地改动写在文件头):CI 只 checkout 仓库,
  技能装在开发者 home 目录里,runner 看不见。
- **两个 APK 双向卡住**:解释版断言 `--pure`、编译版断言 `--native`——
  一个悄悄回退到相邻 `.py` 的模块,与正确编译的模块长得一模一样。
  编译版另跑一遍端上金标(交叉编译干净 ≠ 能在设备上 import)。
- **这个变更买到什么,说清楚**:它把读**算法**的成本从"解压即读"抬到
  "要反汇编"。WebView 资产仍是明文(把每个桥接口与整个流程写得清清楚楚),
  未编译模块仍是字节码,**字面常量原样留在常量池**——金标值、
  `GAP_TOLERANCE_DB`、`RESIDUAL_SPEC` 里的文字照样可被精确搜出。
  它不是许可保护,也不是对 UI 已展示内容的混淆。

## 0.7.5 — 2026-08-25

### Android:按 `python-android-apk` 技能清单体检,修掉四处只在手机上才犯的问题

- **启动无加载态**(最要紧的一条):页面加载时同步调 `list_specs()`,而它
  要付整个分析栈的导入——桌面冷启实测 **14.2 s**,其中字体缓存只占 ~1.6 s,
  大头是全树 `.py → .pyc` 首次编译(APK 不带本解释器的 .pyc)。此前这段时间
  界面是空表单、零提示,看起来就是卡死。现在先绘制外壳再发起阻塞调用,
  并显式告知"首次启动要导入 numpy/scipy/matplotlib"。
- **matplotlib 缓存目录未钉死**:`Python.start()` 之前设置 `MPLCONFIGDIR`
  与 `XDG_CACHE_HOME` 到 `filesDir`。此前能跑是运气——首次导入建字体缓存,
  落到只读目录就是首算崩溃。
- **`[hidden]` 被作者样式压过**:`#fig svg { display:block }` 会盖掉 UA 的
  `[hidden] { display:none }`,而游标覆盖层正是用 `hidden` 开关的 `<svg>`。
  补 `#fig-cursors[hidden]` 显式规则(今天因内容为空而无害,明天不是)。
- **刘海与手势条**:补 `viewport-fit=cover` 与 `env(safe-area-inset-*)`
  内边距,否则首个控件压在状态栏下、标签条压在手势条下。
- **已确认干净的一条**:全仓无 `bbox_inches`——这对我们尤其关键,它会悄悄
  改变图幅范围,让游标与读数依赖的坐标轴矩形描述另一张图。现已加守卫钉住。
- 守卫:新增 `test_the_phone_only_traps_stay_fixed` 覆盖以上五条,经变异
  验证(把两行 setenv 挪到 `Python.start()` 之后当场判红)。**该守卫初版
  自己也踩了坑**:用 `index("Python.start")` 找调用,结果先找到的是我写在
  上面那行注释里的同名文字——已改为匹配真实调用。293 桌面测试通过。

## 0.7.4 — 2026-08-24

### Android:仪器式游标(双标记吸附到采样点 + Δ 读数)

- 结果图新增 **Cursor** 模式:点击放置两个标记,各自**吸附到真实绘制的
  采样点**并显示所属曲线名,同时给出 Δx/Δy——频谱仪/示波器上的 marker
  用法。标记以**数据坐标**保存,平移缩放后重新投影,读数不随视图漂移。
- **判据不是图例标签,是坐标变换**:`axvline`/`axhline` 的辅助线(AGC
  切换点、MCS 门限)带混合变换,只有 `transData` 的图元才是数据。用标签
  区分会两头错——星座图与 blocker 曲线都是**无标签的真数据**,而那 8 条
  辅助线同样无标签。吸附到门限上会把规格线报成测量值。
- **数据按页惰性下发**(`bridge.page_series(i)` + `Native.pageSeries`),
  不进 `run()`:full_cal_steps 十四页共 ~10.6 MB,而用户可能根本不开这个
  功能。星座点云(每页四张 × 5976 点)标记为不吸附并**附原因随包下发**
  ——不是静默丢弃,UI 会说明该处为自由定位。最坏单页 815 KB → **192 KB**。
- **修掉一个会静默吞数据的真 bug**:隔离底板掩码点是 `NaN`,而 Python 的
  `json.dumps` 输出裸 `NaN`,浏览器 `JSON.parse` 直接拒收整个 payload。
  现在非有限值一律转 `null`(掩码点本就"不可归因",游标不得吸附),
  `_jsonable` 同步加固,`page_series` 用 `allow_nan=False` 让任何残余
  当场炸而不是产出解析不了的字符串。
- 守卫:桌面新增四条(payload 必须是严格 JSON、掩码点必须是 null、辅助线
  不得入列且点云须声明、页预算与非法页号),全部经变异验证(且每次先断言
  变异确已注入);端上新增 `cursorSamplesAndProjectionSurviveOnDevice`
  ——样本过桥 + 投影/反解往返(实测往返误差 0)。端上条数 4 → 5,
  workflow 期望值同步。292 桌面测试通过。
- schema:`run()` 的 page 对象未变;新增 `page_series(index)` 接口。

## 0.7.3 — 2026-08-24

### Android:结果图补齐 matplotlib 工具栏(Home/Back/Forward/Pan/Zoom + 数据坐标读数)

- 此前 Android 侧看图只有"拖动 + 双指 + 双击 + Reset",而桌面 Qt 画布挂的是
  matplotlib 自己的 `NavigationToolbar2QT`。现在补齐对等控件:**Home /
  ◀ / ▶ / Pan / Zoom**,以及 matplotlib 工具栏里最有用的那一项——
  **数据坐标读数**。
- **框选缩放**(Zoom 模式拖矩形,橡皮筋提示,松手后该矩形填满视口)与
  **视图历史**(Back/Forward 走 view 栈,与桌面工具栏语义一致);Pan 模式
  保留拖动/双指/双击。
- **数据坐标读数**需要 SVG 本身没有的信息,故 `bridge.run()` 的每页新增
  `axes` 元数据(位置图幅分数 + xlim/ylim + xscale/yscale + 轴标签);
  在 `_svg()` **之后**采集,并有守卫钉住"报出的矩形必须与渲染图里坐标轴
  边框的实际像素位置一致"(实测吻合到 0.0011 图幅 ≈ 轴线线宽)。
  log 轴按对数插值。
- **两处看图体验修复**:读数行放在图**上方**——放下方时,52vh 的图框会把它
  挤出屏幕,而那正是手指按在图上的时刻;图框高度改为贴合图形本身,此前
  固定 52vh 在宽扁图下白白浪费近半屏。
- 端上新增 `toolbarReportsDataCoordinatesOnDevice`(真 WebView 里验坐标
  映射:轴心、左上角的 y 翻转、轴外返回 null、平移缩放后仍正确);桌面新增
  三条守卫(axes 元数据齐全且 JSON 安全、矩形与像素边框一致、工具栏按钮
  存在且已接线),三条均经变异验证——其中 y 翻转那条最初"通过"是因为**变异
  本身没打进去**,修正锚点后当场判红。
- 端上测试条数 3 → 4。288 桌面测试通过。schema:`run()` 返回的 page 对象
  新增 `axes` 键(纯增量,旧字段不变)。
- **金标 job 自证条数**(同日追加,CI 改动,不升版本号):新增
  `on-device tests actually ran` 步骤,解析 instrumented 结果 XML,断言
  实跑条数、失败数与跳过数,并把测试清单打印在日志末尾。此前这条纪律靠
  人工翻日志核对——而日志接口按大小截断、取不到中段那几行,取证方式本身
  就是脆的。三种失败模式(少跑、被 skip、结果文件缺失)均已实测拦截。
  条数断言取**精确值**而非下限:下限挡不住"新加一条、同时旧的一条悄悄
  不跑"这种总数不变的漂移。新增端上测试时须同步更新该期望值(已写入
  `AGENTS.md`)。四种情形(恰好/多一条/少一条/被 skip)均已实测。

## 0.7.2 — 2026-08-24

### Android:图形导出改为 PNG 优先(0.7.1 的 SVG 导出在手机上打不开)

- **根因:Android 平台层没有 SVG 解码器。** 相册、文件管理器、缩略图、
  聊天应用预览全都不认 `.svg`,只有浏览器能开。0.7.1 补的 `Export SVG`
  因此产出了一个"分享成功、字节完好、收件人打不开"的文件——用户现场
  报告即此。已核实导出的字节本身没有任何问题(严格 XML 解析通过、572 处
  `xlink:href` 完整、独立渲染出完整图形),**错的是交付格式选型**,不是
  序列化。桌面工具栏默认给 PNG,正是同一个道理。
- **修法:`Export PNG` 成为首选,`Export SVG` 保留为矢量选项。** PNG 由
  WebView 自己栅格化(`rasterizePng`,固定 2000 px 宽,先铺白底再绘——
  matplotlib 输出透明背景,深色主题下会显示成黑块),经新增的
  `Native.saveBinary()` 落盘并交分享面板。结果图与 Reference 图两处
  共用同一个 `exportFigure()`。
- **导出的是桥送来的原始 SVG,不再是 DOM 里那份**。`showPage()` 会把显示
  用的副本按 px 定宽并删掉 `height` 属性,导出它等于交付一个没有固有
  尺寸的文件;`outerHTML` 另有元素名被小写化等 HTML 序列化副作用。
- **三处静默失败一并修掉**:取不到图时静默 `return`(点了没反应)、两处
  `JSON.parse(native.…)` 无保护(桥一抛异常整个 handler 就死),以及
  Reference 按钮把真实异常压成 "Export failed" 四个字。现在一律回显
  壳侧的原始错误文本。
- **补上从未存在的端上覆盖**:`ExportTest.figuresRasterizeToPngOnDevice`
  在真 WebView 里加载出货的 `index.html` 并栅格化一张出货示意图,断言
  PNG magic 与合理体积——导出这条路此前在设备上一次都没跑过。桌面侧新增
  两条守卫(PNG 必须是首选导出;出货示意图必须自包含,否则离线加载失败
  或污染 canvas 使 `toDataURL` 抛错),两条均经变异验证。
- 端上测试条数 2 → 3。285 桌面测试通过。

## 0.7.1 — 2026-08-23

### Android:与 Qt 版功能对齐(逐项核对后补差)

- **Inspector 载入的交付文件现在也喂 Reference 表**。Qt 用
  `inspector.loaded` 信号把文件的 `results/fs_hz` 送进 Reference 页;
  Android 的 `reference_data()` 只读 `run()` 写的状态,于是**收包方在
  手机上打开别人的 cal_state.json,验收列与捕获成本表全是空的**——恰好
  是 Android 版最主要的使用场景。bridge 新增 `_set_reference_source()`,
  run 与 inspect 两条路都喂它(与桌面两条通路一一对应)。
  语义对齐 Qt:**仅在文件成功通过检查后才改写**(桌面也是渲染成功才
  emit),读不了的文件不得悄悄改表。
- **Reference 页不再是一次性缓存**。此前 `refLoaded` 让它只加载一次,
  "先看 Reference 再跑分析"会永远看到旧数据。bridge 给数据源加版本戳
  (`reference_version()`),UI 进页时比对,过期即重载——对应 Qt 每次
  `set_run_results` 重绘。
- **补上两处导出**:结果图 `Export SVG`(对应桌面工具栏的"另存当前视图")
  与 Reference 图 `Export SVG`(对应 Qt 的 `Save SVG…`);均写入应用私有
  目录后交系统分享面板(Android 没有"选路径另存"的惯例,与 cal-state
  导出同一处理)。
- **新增跨层接线守卫**:UI 里每个 `native.*` 调用必须在 MainActivity 中
  声明,每个 `callAttr("...")` 必须是真实的 bridge 函数——这条 JS→Kotlin
  →Python 链全靠手写胶水,改名只会在设备上炸,现在改名当场红。283 测试
  通过。
- `android/README.md` 新增与 Qt 的逐项功能对照表(含有意保留的平台差异)。

## 0.7.0 — 2026-08-23

### Android:设备自裁决(Self-check 页签)

- **新增第四个页签 Self-check**:金标值随 APK 出货,一键在**本机**重放
  三个代表案例并逐指标对比,显示 PASS/FAIL、平台信息(ABI / numpy /
  scipy / Python)与每项 delta。补的是一个真实缺口——CI 模拟器只能为
  x86_64 背书,而交付硬件是 arm64、OpenBLAS 也不同;现在裁决权在**用户
  手里那台真机**上,换机/升级 Android/Chaquopy 换 wheel 后随时可复验。
- **对拍逻辑只有一份**:`bridge.self_check()`;CI 的 `GoldenTest` 改为
  调用它并只断言其结论(此前是 Kotlin 里的第二份实现)——手机与 CI 不可能
  按不同容差或不同规则裁决。金标文件从 androidTest assets 移入 Chaquopy
  源目录(`make_golden.py` 同步改写入位置),APK 与测试共用同一份。
- 自检走前台服务(与分析同一条路径):跑的是真校准,分钟级,熄屏不中断。
- 桌面新增两项测试:`self_check` 在生成金标的机器上必须**每项 delta 恰为
  零**(这测的是对拍逻辑本身,不是物理),以及金标文件必须位于随 APK
  出货的目录。281 测试通过。
- `AGENTS.md` 验证章新增纪律:**改动随 APK 出货的代码或新增端上测试后,
  必须重跑金标 job 并核对日志里的测试条数**——构建绿不等于端上物理对,
  没跑过的端上守卫等于没有守卫(两次事故的教训)。
- **实测追记(2026-08-23):用户真机(arm64)Self-check 通过。** 三条 ABI
  路径至此全部裁决:桌面(生成金标)/ 模拟器 x86_64(CI run 32627470392)
  / 真机 arm64。`android/README.md` 的 arm64 残余告诫随之取消。

## 0.6.6 — 2026-08-23

### Android:Reference 表格侧 numpy 2.0 API 越界

- 0.6.5 修好 SVG 后 Reference 页停在表格侧:`integrate_pn` 用了
  **`np.trapezoid`——numpy 2.0 才有的名字**(端上 1.19.5 只有 `np.trapz`)。
  与 `correlation_lags` 同一类:桌面 numpy 2.x 下写法完全正常,只在手机上
  炸。修复:模块级一次性绑定 `getattr(np, "trapezoid", None) or np.trapz`,
  不在调用点做版本判断;IPN 读数不变(默认剖面 −46.8 dBc)。
- **守卫补齐 numpy 面**:上次只扫了 scipy——本次事故正好落在没扫的那一半。
  现扫描随 APK 出货的全部 Python 文件的 `np.*` 调用面(90 个名),对照
  numpy 1.19.5 已核验清单;scipy 守卫同步重构共用文件清单。两个守卫都做了
  变异验证:把 `np.trapezoid` 与 `sig.correlation_lags` 分别放回去,均被
  当场判红(不是空跑)。279 测试通过。

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
