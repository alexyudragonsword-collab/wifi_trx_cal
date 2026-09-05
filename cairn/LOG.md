# Project Cairn 日志

本文件按倒序记录实质性进展——最新条目在顶部、紧跟本行之下。每条尽量短——只写摘要与指针;结论沉淀进 `cairn/<topic>.md`。

## 2026-09-05 · R19:EVM 预算的 CPE 追踪份额改为物理现算(0.7.9)

- 用户对 R18 留下的裁决项说"做吧"。`EvmBudget.cpe_tracked_fraction` 默认 0.5 → `None`,按 `lo_profile`/`t_fft_s`/`pn_band_hz` 用 `cpe_partition` 现算;显式值仍优先。
- **份额随积分带走**:B15 写的 6.6% 是 3.3 kHz–160 MHz 下的数,与 `ipn_rad2` 同带(10 kHz–100 MHz)是 **5.48%**;因此带宽做成显式字段,不再让份额与总量各取各的带。
- **交付数字变动**:示例预算预测 EVM −40.3 → −39.5 dB,4096-QAM 裕量 2.3 → 1.5 dB(相噪项 +2.7 dB)。仓库内无 docx 引用该数。
- 守卫:默认 == 同带同符号闭式值、11ac > 3.5×、显式 0.5 相对物理值 −2.7 dB;变异(默认改回 0.5)已红。
- 指针:`CHANGELOG.md` 0.7.9、`docs/backlog_zh.md` B15 末尾、`src/wifitrx/link/evm_budget.py`。
- **run #49 裁决(adc1306)**:三 job 全绿。解释版与编译版端上均 **5 run / 0 failed / 0 skipped**(含 `metricsMatchDesktopGolden` 四案例);编译版 wheel `wifitrx-0.7.9-cp38-cp38-android_21_{arm64_v8a,x86_64}`,`cythonised 52 modules`,版本门禁与导出检查通过。0.7.9 两种出货形态均已裁决。

## 2026-09-04 · R18:LO 相噪 vs CPE 去除——四配置隔离研究做成分析(0.7.8)

- 起因:用户问 CPE 去除会不会因 LO 相噪引入额外误差。读码结论:模型的 `correct_cpe()` 是 genie、EVM 均衡不走 LTF,机理 B(LTF 估计被相噪污染并冻结)与 C(导频估计噪声共模注入)在模型里**结构性不可见**。用户拍板把四配置做成 `AnalysisSpec`。
- 落地 `pn_cpe_study`(两端共用注册表,三页):谱按 `1 − sinc²(f·T_FFT)` 拆分;type-II PLL 环路带宽扫描;四配置随相噪电平扫描 + 闭式对拍。新增 `cpe_partition`/`ici_weight`/`TypeIIPllPhase`、`correct_cpe_pilots`、`build_frame(data=)`。
- **实测**(80 MHz/11ax/单 LO/8 帧):①/② 对闭式残差 0.13/0.12 dB(ICI 加权与 DSB 约定对上);CPE 只买回 0.29 dB(追掉 6.6%);LTF 估计 +1.74 dB;8 导频 +0.33 dB。
- **推翻自己一条断言**:11ax/be 下 PLL 环路带宽的"jitter 最优"与"去 CPE 后 EVM 最优"**重合**(300 kHz,差 0 dB);只有 11ac/n 才分开(0.58 dB)。原因即 35 kHz 可去除带宽——与"CPE 几乎帮不上忙"是同一件事。
- **量出预算问题**:`EvmBudget.cpe_tracked_fraction=0.5` 实为 6.6%,相噪项乐观 2.7 dB;未改默认值,待用户裁决(backlog 头部)。
- 测试自身纠错留档:type-II 远端滚降是 −20 不是 −40 dB/dec。7 处守卫经变异验证。
- 金标案例 3 → 4(`pn_cpe_study`),端上条数仍 5;job 结论追记于本条末尾。
- **run #44 裁决**:解释版金标 **5 run / 0 failed / 0 skipped**,`metricsMatchDesktopGolden` 含第四案例通过——端上 numpy 1.19.5 复现了 Generator + irfft + `np.sinc` 这条物理。编译版**未裁决**:两个 flavour 的 `upload-artifact` 撞上 GitHub **artifact 存储配额**("Artifact storage quota has been hit",与代码无关),而编译版的上传排在模拟器之前,把唯一的物理检查跳过了。修法:上传移到端上门禁之后、`continue-on-error`、保留期 14→7 天;守卫断言顺序与非致命(变异 3 处已红)。
- **run #47 裁决(修后重跑,commit 3f04e8c)**:三个 job 全绿。编译版 wheel `wifitrx-0.7.8-cp38-cp38-android_21_{arm64_v8a,x86_64}`、`cythonised 52 modules`、版本门禁与 `PyInit_*` 导出检查通过,端上 **compiled tests: 5 run / 0 failed / 0 skipped**(含 `metricsMatchDesktopGolden` 第四案例);解释版同样 5/5。配额恰好重算,两处上传也成功(77 MB)。**0.7.8 两种出货形态均已裁决。**
- 指针:`CHANGELOG.md` 0.7.8、`docs/backlog_zh.md` B15、`app/specs.py::run_pn_cpe_study`。

## 2026-08-25 · R17:编译版端上 import 失败的根因是符号可见性(0.7.7)

- 现象:构建全绿、`--native` 通过、`.so` 一个不少,端上 `ImportError: dynamic module does not define module export function (PyInit_sync)`。
- **根因(本机两版头文件直接证明)**:`-fvisibility=hidden` 把模块初始化函数一起隐藏了,因为 **CPython 3.8 的 `PyMODINIT_FUNC` 不带可见性属性**(3.9 起才由 `Py_EXPORTED_SYMBOL` 加上),而 Chaquopy 的 Android target 就是 3.8。宿主机 3.11 头文件替你导出,所以 `--host` 试编译永远复现不了。修法:命令行显式 `-DPyMODINIT_FUNC=__attribute__((visibility("default"))) PyObject*`。
- **更正 R16 的一个判断**:上一版把同类失败(`PyInit_cal`)归因为"扩展模块当包初始化器被导入器拒绝",错了;真因即本条。不编译 `__init__.py` 保留(re-export 壳无保护价值),理由已在 `android_wheel.py` 文件头更正。
- **教训**:这类缺陷在**所有构建期信号上都是绿的**,只有出货件上的物理检查能拦。新增 `android/tools/check_wheel_exports.py`,用 NDK `llvm-nm` 逐个查每个 `.so` 是否导出 `PyInit_<模块名>`;桌面侧守卫断言构建器**拼出的命令行**(变异验证已红)。
- **裁决**:修后编译版端上金标 5/5 通过(0 失败 0 跳过),含 `metricsMatchDesktopGolden`;52 个 `.so` × 2 ABI 全部通过导出检查。编译版自此与解释版同为可交付形态。
- **同轮暴露的第二件事**:`build-android-wheel/`(197 文件 7.7 MB)被 0.7.6 的 `git add -A` 误提交。危害不在体积——构建器会缓存参考 wheel 取 dist-info,陈旧副本把编译版 METADATA 冻在 0.7.6,连续两版打着旧版本号与旧依赖表出货。已 untrack + ignore,并加 CI 断言"wheel 文件名必须带 pyproject 的版本号"。
- 指针:`CHANGELOG.md` 0.7.7、`android/README.md`「三个必须钉死的前提」、`docs/backlog_zh.md` R1 增补。

## 2026-08-25 · R16:并出编译版 APK(0.7.6)

- 新增 `compiled` flavor,wifitrx 以逐 ABI wheel(57 个 `.so`)进包;解释版不动。**编译版 srcDirs 必须不含 `../../src`**,否则源码遮蔽 `.so`、产出"自以为编译过"的解释版(守卫 + 变异验证)。
- **两个实测前提**:Cython 3.3.0 在虚数字面量上崩溃(复基带工程致命),钉 `<3.3`;必须 `-X annotation_typing=False`,否则描述性标注被当成强制 C 类型(`np.float64` 进不了 `float`),不加时 291/2 败、加后 293 全过。**修编译器行为,不修分析层**。
- 技能脚本 vendoring 进 `android/tools/`:CI 只 checkout 仓库,技能在 home 目录里 runner 看不见。两个 APK 用 `--pure`/`--native` 双向卡住,编译版另跑端上金标。
- **诚实边界写进 README**:抬高的是读算法的成本;WebView 资产明文、未编译模块仍是字节码、字面常量原样在常量池(金标值/`RESIDUAL_SPEC` 可被精确搜出)。
- **同一类失误第三次**:守卫用朴素子串匹配,命中的是解释该事项的注释而非代码本身,删掉真代码照样通过。已写进 `AGENTS.md`:**匹配代码形态,不匹配词句**。

## 2026-08-25 · R15:按 python-android-apk 技能清单体检 Android 线(0.7.5)

- 用户要求对照新装的技能核一遍手搭配置。查出**四处只在真机上才犯的问题**并修:启动无加载态(冷启 14.2 s 空白)、matplotlib 缓存目录未钉死、`[hidden]` 被 `#fig svg{display:block}` 压过、缺 `viewport-fit`/安全区内边距。
- **最有价值的一条是量化**:冷启 14.2 s 里字体缓存仅 ~1.6 s,大头是全树 `.py→.pyc` 首次编译——即我们一直记作"已知非致命警告"的 buildPython 不匹配,其代价第一次被量出来。
- 确认干净:全仓无 `bbox_inches`(对我们尤其要命,会让游标/读数依赖的坐标轴矩形描述另一张图),已加守卫钉住。
- **守卫初版自身踩坑留档**:用 `index("Python.start")` 判定顺序,结果匹配到的是我自己注释里的同名文字;改为匹配真实调用后变异验证通过。又一次"测量工具先自证"。
- 指针:`CHANGELOG.md` 0.7.5、`tests/test_android_bridge.py::test_the_phone_only_traps_stay_fixed`。

## 2026-08-24 · R14:Android 仪器式游标(0.7.4)

- 双标记吸附到真实采样点 + Δ 读数;标记存数据坐标,平移缩放后重投影,读数不漂。
- **判据纠错(核心)**:区分数据与辅助线用**坐标变换**,不用图例标签——星座图/blocker 曲线是无标签的真数据,AGC/MCS 辅助线也无标签;吸附到门限=把规格线报成测量值。
- **payload**:`page_series(i)` 按页惰性下发(全页合计 10.6 MB 不能进 `run()`);点云标不吸附并附原因,最坏单页 815→192 KB。
- **顺带修掉静默吞数据的真 bug**:掩码点 NaN → `json.dumps` 裸 `NaN` → `JSON.parse` 拒收整包。统一转 `null` + "payload 必须严格 JSON" 守卫。
- **两次自身误判留档**:管道读退出码把断言测成全失效;凭截图断言图被裁(实为文字放大错觉,四角映射数值证伪)。**测量工具先自证**。
- 桌面 292 通过,端上 4 → 5;指针:`CHANGELOG.md` 0.7.4、`android/README.md`、`docs/backlog_zh.md` R1 增补。

## 2026-08-24 · R13:Android 结果图补 matplotlib 工具栏(0.7.3)

- 用户要"matplotlib 控件方便看图"。桌面由 `NavigationToolbar2QT` 提供,端上是一张 SVG,必须自实现:Home/Back/Forward/Pan/框选 Zoom + **数据坐标读数**。
- **读数是这次的技术核心**:SVG 不含数据范围,`bridge.run()` 每页新增 `axes` 元数据(图幅分数位置 + xlim/ylim + scale + 标签),log 轴按对数插值。
- **守卫不自证**:用渲染图的像素找坐标轴边框,反查报出的矩形是否吻合(0.0011 图幅 ≈ 轴线线宽)。端上加 `toolbarReportsDataCoordinatesOnDevice` 在真 WebView 验映射(轴心/y 翻转/轴外 null/缩放后)。
- **自身失误留档**:y 翻转变异最初"通过"是因为替换锚点跨行未匹配、变异没注入;修正后判红。**变异测试本身要核实变异确实生效**。
- 顺带修两处看图体验:读数行移到图上方(此前被 52vh 图框挤出屏幕),图框高度贴合图形(此前宽扁图浪费近半屏)。288 测试通过,端上 3 → 4。
- **纪律机械化**:金标 job 新增断言步骤自证端上实跑条数/失败/跳过并在日志末尾打印清单——此前靠人工翻日志,而日志接口按大小截断取不到中段,取证方式本身是脆的;三种失败模式实测拦截。`AGENTS.md` 同步改写该条,并新增"变异验证前先确认变异真的注入"。
- 指针:`CHANGELOG.md` 0.7.3、`android/README.md` 对照表与工具栏说明、`docs/backlog_zh.md` R1 增补。

## 2026-08-24 · R12:Android 图形导出改 PNG 优先(0.7.2)

- 用户报告 Export SVG "文件发出去了但打不开"。先证伪"字节坏了":导出的 SVG 严格 XML 解析通过、572 处 `xlink:href` 完整、独立渲染出完整图形——**实现没问题,格式选错了**。
- 根因是平台事实:**Android 平台层没有 SVG 解码器**(相册/文件管理器/缩略图/聊天预览全不认),SVG 是手机上唯一打不开的图片格式。0.7.1 按"矢量更优"选 SVG-only,是把桌面推理直接搬到移动端。
- 修法:`Export PNG` 首选(WebView canvas 栅格化,2000 px、白底),SVG 保留矢量选项;导出改用桥送来的**原始** SVG,不再用被 `showPage()` 改过的 `outerHTML`(那份没有固有尺寸)。顺带修掉三处静默失败(静默 `return`、两处无保护 `JSON.parse`、真实异常被压成 "Export failed")。
- **盲区**:导出路径在设备上从未执行过,与 0.6.5 同型;已补端上 `ExportTest`(真 WebView 加载出货 UI)+ 两条桌面守卫,均经变异验证。端上测试 2 → 3。
- 指针:`CHANGELOG.md` 0.7.2、`docs/backlog_zh.md` R1 增补、`android/README.md` 导出格式说明与对照表。

## 2026-08-23 · 仓库拓扑:建立 main 分支(与开发分支同一提交)

- 用户要求"合并到 main"。核查发现**远端此前只有 `claude/wifi7-transceiver-calibration-o03ay0` 一个分支,且它就是仓库默认分支**——开发分支一直在当主干,不存在分叉待合并。
- 处置:在当前提交上建立 `main`(内容零差异,非真实合并),使发布名与开发名分离。两分支指向同一 SHA。
- **未改动仓库默认分支设置**(仍指向开发分支)——这属于仓库形态决策,留给用户裁决。
- 无代码改动,不升版本号、不触发金标重跑纪律。

## 2026-08-23 · 规则:任何更新都要两端(Qt + Android)完整验证

- 用户要求立规。写入 `AGENTS.md`:**验证章**新增"两端各自验证完整,缺一不算完成",逐条列明各自的门禁(Qt: gui_specs + gui_inspector;Android: android_bridge 四类守卫 + 重跑金标并核对测试条数),并声明"只改了单端"通常不成立(两端共用 `src/wifitrx/` 与 `app/` 数据层)。
- 配套写入**结构章**:用户可见能力必须放进两端共用数据层(`specs.py` / `inspector_data.py` / `reference.py` / `bridge.self_check()`),不得只写进一端——附 0.6.5(Inspector 缺三张表)与 0.7.1(Reference 收不到检查器载入的文件)两次实际漂移作依据。
- 有意的单端差异必须进 `android/README.md` 对照表并注明理由,否则按漏做处理。
- 纯规则/文档改动,不升版本号、不触发金标重跑。

## 2026-08-23 · R11:Android 与 Qt 功能逐项核对并补差(0.7.1)

- 暂停 Android 线前做全面对照,查出**两个真缺陷**:① Inspector 载入的文件不喂 Reference 表(Qt 有 `loaded` 信号通路)——收包方场景下表是空的;② Reference 页一次性缓存,先看再跑就永远旧。
- 修法:bridge 加 `_set_reference_source()` + 版本戳,run/inspect 两条路都喂(对齐 Qt 两条通路);**仅在检查成功后才改写**(Qt 也是渲染成功才 emit)。UI 按版本戳失效重载。
- 另补两处导出(结果图 / Reference 图 Export SVG → 分享面板),对应 Qt 工具栏另存与 Save SVG。
- 新增跨层接线守卫(`native.*` ↔ MainActivity ↔ bridge 函数名),这条手写胶水链改名此前只会在设备上炸。283 测试通过;对照表写入 `android/README.md`。

## 2026-08-23 · 真机 arm64 Self-check 通过——Android 验证链闭合

- 用户在真机(arm64)上运行应用内 Self-check:**PASS**。这是整条验证链最后一个空格,且发生在真实交付硬件上,不再由模拟器代理。
- 三条 ABI 路径全部裁决:桌面(生成金标)/ 模拟器 x86_64(CI run 32627470392)/ 真机 arm64(用户手动)。端上 numpy 1.19.5 + scipy 1.4.1 + OpenBLAS 在两种 CPU 架构上都复现桌面物理。
- 文档同步:`android/README.md` arm64 残余告诫取消并写入实测结论;CHANGELOG 0.7.0 追记;backlog R1 增补。无代码改动,故不升版本号、不触发金标重跑纪律。
- 未采集:平台信息行与实际耗时(README 里"分钟级"仍是估计,待补)。

## 2026-08-23 · R10:设备自裁决 Self-check + 金标重跑纪律(0.7.0)

- 补 arm64 缺口:金标随 APK 出货,应用内 Self-check 页签让**真机自己**裁决物理一致性(PASS/FAIL + 平台信息 + 每项 delta),不再只由 x86_64 模拟器代理。
- 结构:对拍逻辑唯一实现 `bridge.self_check()`,CI GoldenTest 改为调用并断言其结论——同 inspector_data 的思路,消灭第二份实现。
- 桌面测试钉死"生成金标的机器上 delta 必须恰为零"(测的是对拍逻辑本身);`AGENTS.md` 新增纪律:动了随 APK 出货的代码或加了端上测试就必须重跑金标 job 并核对测试条数。
- 指针:`CHANGELOG.md` 0.7.0、`android/README.md` arm64 段。281 测试通过。

## 2026-08-23 · R9:numpy 2.0 API 越界 + 守卫补齐 numpy 面(0.6.6)

- Reference 表格侧 `np.trapezoid`(numpy 2.0 名)在端上 1.19.5 崩溃——与 correlation_lags 同类,而 0.6.2 的守卫只覆盖了 scipy,事故正落在没扫的另一半。
- 修复:模块级 `getattr(np,"trapezoid",None) or np.trapz` 绑定;IPN −46.8 dBc 不变。
- 守卫扩到 numpy(90 个名对照 1.19.5 清单),两个守卫均通过变异验证(放回越界调用当场判红)。
- **教训**:跨版本兼容守卫必须覆盖"全部随包出货的依赖",按库补一半等于没补。279 测试通过。指针:`CHANGELOG.md` 0.6.6。

## 2026-08-23 · R8:Reference 资源缺失 + Inspector 内容不全(0.6.5)

- 真机第三、四个现场报告:Reference 页 FileNotFoundError(assets 没进 APK,且 Chaquopy 平铺布局让 asset_path 的"上一级"失效);Inspector 只有 findings、缺 Qt 版的三张表。
- 结构性修法:新增 `app/inspector_data.py` 作为"检查器显示什么"的唯一定义,Qt 页与 Android 桥共用——两端不再各写各的;gradle `stageAssets` 把 assets/ 送进 Chaquopy srcDir。
- **盲区归因**:端上测试只跑 run 一条路径,Reference/Inspector 从未在设备上被执行过;已补 `referenceAndInspectorRenderOnDevice` + 桌面两项守卫(sections 一致性、gradle 暂存在位)。
- 指针:`CHANGELOG.md` 0.6.5。278 测试通过。

## 2026-08-23 · R7:金标对拍通过——端上物理 = 桌面物理(0.6.4)

- 模拟器金标 job(run 32618761315,Android 14/x86_64)三个代表分析逐指标对拍全过(0.05 dB/1e-3 容差);先怀疑"3 分钟太快"核了日志,确认 GoldenTest 真实执行(1 test,0 failed)。
- 结论:numpy 1.19.5 / scipy 1.4.1 / OpenBLAS 端上栈复现桌面物理;裁决前抓出的唯一真实不兼容是 correlation_lags(已修,0.6.2)。
- README 告诫降级为已裁决记录;残余:arm64 ABI 未单独对拍(x86_64 已拍、真机功能运行已验证),存疑时换 arm64 AVD 重跑、不放宽容差。
- 指针:`CHANGELOG.md` 0.6.4、`android/README.md` 版本表下告诫块。

## 2026-08-23 · R7 途中:真机第二报告——结果图空白修复(0.6.3)

- 根因:`app.js` 的 `showPage()` 在 `#a-out` 仍 hidden 时排版,容器 clientWidth=0 → SVG 零宽,图永远空白(metrics/文本正常)。
- 修复:先 unhide 再排版 + 视口宽度兜底;单页结果保留 Reset 按钮。`node --check` 过;金标对拍 run 同时在跑。
- 指针:`CHANGELOG.md` 0.6.3。

## 2026-08-23 · R6:真机首跑崩溃修复 + scipy 调用面守卫(0.6.2)

- 用户真机 full_cal 触发 `correlation_lags` AttributeError——0.6.1 标注的"端上 scipy 1.4.1 低于桌面下限"风险首次兑现,离预言到兑现不到一天。
- 修复:`cal/sync.py` 换数学恒等 `np.arange`(276 测试零改动);**守卫测试**扫描全仓 scipy 调用面对照 1.4.1 allowlist,同类问题此后在桌面测试期暴露。
- numpy Generator 用面审计干净;APK 图标与 Windows exe 同源(assets/icon.png → 五档 mipmap)。
- 指针:`CHANGELOG.md` 0.6.2、backlog R1 增补、`tests/test_android_bridge.py` 守卫。

## 2026-08-23 · R2':Android APK 在 GitHub Actions 上编译成功(0.6.1)

- 三轮迭代到绿:pip sdist 陷阱(`--only-binary :all:`)→ 探针证实 wheel 仓无 cp311 scipy → 内嵌 Python 降 3.8(源码树预审计兼容后才动)。
- 端上解析 numpy 1.19.5 / scipy 1.4.1 / matplotlib 3.6.0——scipy/numpy 低于桌面下限,**物理一致性归模拟器金标对拍裁决,构建绿≠物理对**(README 显著标注)。
- debug APK artifact 71 MB(双 ABI),远低于 200 MB 预估;首次成功 run 32613192402。
- 指针:`CHANGELOG.md` 0.6.1、backlog R1 增补、`android/README.md` 版本表。

## 2026-08-16 · R1:Android 整包落地(0.6.0)

- Chaquopy + WebView 壳:分析层零改动打入 APK,桥 `bridge.py` JSON 进出,图形 SVG 矢量缩放,manifest 无 INTERNET 权限。
- 三条路线否决记录(pyside6-android-deploy / Kivy / 去 scipy 化)与选型依据沉淀在 backlog R1;版本锁与已知代价在 `android/README.md`。
- 桥契约 5 项进桌面主套件;端上金标对拍进 CI 手动 job;Gradle 侧本容器无 SDK 未编译,首建步骤已文档化。
- 指针:`CHANGELOG.md` 0.6.0、`docs/backlog_zh.md` R1、`android/README.md`。

## 2026-08-16 · B14:EVM 估计器自拟合偏差修正(0.5.9)

- 11n vs 11ax 灵敏度对照暴露仪器伪影:per-tone 均衡器自拟合吞 1/N 噪声,6 符号帧偏乐观 0.79 dB,曾把 0.66 dB 占用带宽真实差抵消成 +0.13 dB。
- 修正:`metrics/evm.py` 加自由度重标 N/(N−1);合成数据验证偏差律精确成立;修正后 MCS7 灵敏度差 +0.69 dB 回归理论。
- 交付数字整体上移:320M/4096 验收 −41.1→−40.2 dB(docx/教程已同步);闭环 gap 不受影响;270 测试零改动。
- 指针:`docs/backlog_zh.md` B14、`CHANGELOG.md` 0.5.9。被推翻的结论("两制式灵敏度几乎相同")按惯例留档于 B14。

## 2026-08-16 · 历史知识清点(inventory_only)

- 既有知识源清单(只清点、不迁移,各文档继续各司其职):
  - `docs/backlog_zh.md` — 决策记录 + 工程待办唯一权威来源(头部"当前状态"块;含被推翻假设的原文留档,如 B13);
  - `CHANGELOG.md` — 版本变更 0.1→0.5.7,schema/公开签名变化显式标注;
  - `README.md` — 设计洞察 1–10(结论浓缩版);
  - `docs/tutorial.html` / `docs/devguide.html` — 构建时实跑数字的双语教程与开发指南(源码在 `tools/tutorial/content/`);
  - `docs/wifitrx_design_spec.docx` — 对外设计规格书(v0.5.6 状态);
  - `docs/interface_zh.md` / `handoff_zh.md` / `units.md` / `cal_order_zh.md` / `circuit_data_zh.md` — 接口与交付约定。
- 后续如需将某条历史结论升为 `cairn/` 知识专题文档,按 selective_migrate 逐条确认后再做。

## 2026-08-16 · Project Cairn 初始化

- 初始化 Project Cairn 结构(git_policy: track;provider 暂缓对接;文档语言中文)。
- 历史迁移模式:`inventory_only`。
- 原 `CLAUDE.md` 项目约定整体并入 `AGENTS.md`("项目约定"章);`CLAUDE.md` 改为一行 `@AGENTS.md` 桩。
- 详见 `AGENTS.md` 与 `.cairn/config.yaml`。
