# Project Cairn 日志

本文件按倒序记录实质性进展——最新条目在顶部、紧跟本行之下。每条尽量短——只写摘要与指针;结论沉淀进 `cairn/<topic>.md`。

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
