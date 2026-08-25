# wifitrx Android 工作台(Chaquopy + WebView 壳)

把桌面工作台整包搬上 Android:**分析层一行未改**(`src/wifitrx` +
`app/specs.py`/`app/reference.py` 以源码形式打进 APK),只有 Qt 壳
(`app/main.py`)换成了 Kotlin + WebView 对应物。图形以 SVG 矢量交给
WebView 平移/缩放——对应桌面 0.5.6 的 NavigationToolbar。

## 架构

```
WebView 单页 UI (assets/ui/, 离线零依赖)
   ↕ JSON (addJavascriptInterface: Native.*)
Kotlin 薄壳 (MainActivity / AnalysisService 前台服务)
   ↕ JSON (Chaquopy PyObject)
bridge.py  →  specs.ALL_ANALYSES / reference / inspector / save_cal_state
```

- **无 INTERNET 权限**(manifest 层面,比任何 WebView 配置都硬)。
- 长跑分析在前台服务的 Python 线程里,熄屏/切后台不被杀;≥160 MHz
  运行前 UI 两段式确认(手机 SoC 分钟级 + 发热)。
- 不支持中途取消:分析函数没有取消点,已知限制。
- Inspector 直调 stdlib-only 的 `wifitrx.handoff.inspector`;
  Save cal-state 复用 `save_cal_state`(README 自动伴生),经系统分享面板导出。

## 版本锁(一起动,不单独动)

| 组件 | 版本 | 依据 |
|---|---|---|
| Chaquopy | 16.0.0 | AGP 8.6–8.8,Python 3.8–3.13 |
| Python(内嵌) | **3.8** | CI 探针(run 32612946416)证实 wheel 仓无 cp311 scipy;科学栈在 3.8 覆盖最全 |
| AGP | 8.7.3 | Chaquopy 16 支持窗内 |
| Gradle | 8.9+ | AGP 8.7 要求 |
| minSdk / target | 24 / 34 | Chaquopy 下限 / 前台服务类型要求 |

**端上实际解析版本**(首次成功构建 run 32613192402,2026-08-23,
`--only-binary` 下 pip 的解析结果,两 ABI 相同):

| 包 | 端上版本 | 桌面下限 | 备注 |
|---|---|---|---|
| numpy | 1.19.5 | ≥1.23 | **低于桌面下限** |
| scipy | 1.4.1 | ≥1.9 | **低于桌面下限**;`oaconvolve` 需 ≥1.4.0,恰好够 |
| matplotlib | 3.6.0 | ≥3.6 | 达标 |
| OpenBLAS / libgfortran | 0.2.20 / 4.9 | — | Chaquopy 运行库 |

> **端上 scipy/numpy 远旧于桌面——已裁决:金标对拍通过**
> (run 32624752010,2026-08-23,Android 14/x86_64 模拟器,0.6.6):
> full_cal 80M/256/seed5、rx_evm_sweep 80M、spur_planner 320M 全部指标与
> 桌面金标在 0.05 dB / 1e-3 容差内一致。期间抓出并修掉两个真实不兼容
> (`correlation_lags` scipy 1.5 / `np.trapezoid` numpy 2.0),现由
> `tests/test_android_bridge.py` 的 scipy+numpy 调用面守卫拦在桌面。

**arm64 已由真机裁决(Self-check 页签)**:CI 只能为它跑的 ABI 背书
(x86_64),而真机是 arm64、OpenBLAS 也不同。金标值随 APK 出货,应用内
Self-check 页签一键在**本机**重放三个案例并逐指标对比,给出 PASS/FAIL、
平台信息(ABI / numpy / scipy / Python)与每项 delta。

> **实测结果(2026-08-23,用户真机 arm64,0.7.0):PASS。**
> 至此三条 ABI 路径全部裁决完毕——桌面(生成金标)、模拟器 x86_64
> (CI run 32627470392)、真机 arm64(用户手动)。端上 numpy 1.19.5 /
> scipy 1.4.1 / OpenBLAS 0.2.20 复现桌面物理,在两种 CPU 架构上都成立。

对拍逻辑只有一份(`bridge.self_check()`),CI 的 GoldenTest 调的是同一个
函数——手机与 CI 不可能按不同规则裁决。换机、升级 Android、Chaquopy 换
wheel 之后重跑一次即可复验;耗时数分钟(跑的是真校准)。

实测:debug APK artifact 71 MB(zip,arm64+x86_64 双 ABI),远低于
~200 MB 预估。已知非致命警告:runner buildPython 3.12 不能为 3.8 预编
译 .pyc(只慢首次导入;要消除可在 CI 装 Python 3.8 并设 `buildPython`)。

## 构建

本仓不含 gradle wrapper 二进制(不提交 jar)。两种方式:

```bash
# Android Studio:直接 Open android/,同步后 Run。
# 命令行:
cd android
gradle wrapper --gradle-version 8.9   # 首次;之后用 ./gradlew
./gradlew :app:assembleDebug          # APK 在 app/build/outputs/apk/debug/
```

## 验证

- **桥契约(桌面,免 Android 环境)**:`tests/test_android_bridge.py`
  在主测试套件里跑——list_specs 与注册表逐键一致、run 返回 SVG 页与
  metrics、错误以 JSON 返回而非崩溃、reference 两类条目齐全。
- **端上金标对拍(模拟器/真机)**:
  `./gradlew :app:connectedDebugAndroidTest` 跑三个代表分析
  (full_cal 80M/256/seed5、rx_evm_sweep 80M、spur_planner 320M),与
  `src/androidTest/assets/golden.json`(桌面同参数生成,
  `python android/tools/make_golden.py` 重生成)逐指标对拍:数值容差
  0.05 dB / 相对 1e-3(BLAS/FFT 实现差异,不追位一致),非数值精确相等。
  这是"同一套物理搬上手机"的证明。
- CI:`.github/workflows/android.yml`——push 触碰 android/ 时
  assembleDebug;金标对拍模拟器 job 手动 dispatch(模拟器 20+ 分钟,
  不进每次 push)。

## 与桌面 Qt 版的功能对照

逐项核对过一次(0.7.1),差异要么已消除,要么是有意的平台适配:

| 功能 | Qt | Android | 说明 |
|---|---|---|---|
| 七个分析 + 参数表单 | ✅ | ✅ | 同一份 `list_specs()` 注册表 |
| 结果 metrics / 文本 / 多页图 | ✅ | ✅ | |
| **图形工具栏** | NavigationToolbar2QT | **Home / ◀ / ▶ / Pan / Zoom(框选)** | 0.7.3 补齐;桌面由 matplotlib 提供,端上自实现 |
| **数据坐标读数** | 工具栏右下角 | **图上方一行,触摸即读** | 0.7.3;SVG 不含数据范围,由 `bridge.run()` 的 `axes` 元数据支撑 |
| **游标(仪器式 marker)** | — | **双标记吸附采样点 + Δ 读数** | 0.7.4;Android 独有,桌面可用工具栏读数替代 |
| **图形导出** | 工具栏另存 PNG/SVG/PDF | **Export PNG / Export SVG → 分享面板** | 0.7.2:PNG 为首选(见下方格式说明),SVG 保留矢量 |
| Save cal-state | 文件对话框选路径 | 私有目录 + 分享面板 | 平台惯例差异,非缺陷 |
| Inspector 四区块 | ✅ | ✅ | 共用 `inspector_data.inspector_sections` |
| **Inspector 载入 → Reference 表** | `loaded` 信号 | **✅ 0.7.1 补齐** | 此前收包方打开交付文件,Reference 表是空的 |
| **Reference 随结果刷新** | 每次 `set_run_results` 重绘 | **✅ 0.7.1 补齐**(版本戳失效重载) | 此前只加载一次,先看 Reference 再跑分析就永远是旧的 |
| **Reference 图导出** | Save SVG… | **Export PNG / Export SVG → 分享面板** | 0.7.2 同上 |
| Self-check(设备自裁决) | — | ✅ | Android 独有,Qt 是金标生成方,不需要 |
| ≥160 MHz 两段式确认 | — | ✅ | 桌面不需要护栏 |

> **导出格式:PNG 优先,不是随便选的。** Android 平台层没有 SVG 解码器
> ——相册、文件管理器、缩略图与聊天应用预览都不认 `.svg`,只有浏览器能
> 开。0.7.1 只提供 SVG 导出,结果是"分享成功但收件人打不开"(用户现场
> 报告;导出的字节经核实完全合法,错的是格式选型)。PNG 由 WebView 自己
> 栅格化(2000 px 宽,白底),SVG 保留给需要矢量的场合。端上守卫见
> `ExportTest.figuresRasterizeToPngOnDevice`。

> **图形工具栏是两端各自实现的唯一一项能力。** 桌面画布上的 Home/Back/
> Forward/Pan/Zoom 与坐标读数由 matplotlib 的 `NavigationToolbar2QT` 直接
> 提供;WebView 里显示的是一张 SVG,这些必须自己写。因此坐标读数所需的
> 坐标轴位置与范围由 `bridge.run()` 的 `axes` 元数据随图下发,并由
> `tests/test_android_bridge.py` 钉住(报出的矩形必须与渲染图里坐标轴边框
> 的像素位置一致),端上由 `ExportTest.toolbarReportsDataCoordinatesOnDevice`
> 复验映射本身。Reference 页的示意图不带工具栏(静态图,无数据坐标可言)。

> **游标吸附到的是真实采样点,不是插值。** 数据由 `bridge.page_series(i)`
> 按页惰性下发(不进 `run()`:full_cal_steps 全部页合计 ~10.6 MB)。判定
> 哪些图元算"数据"用的是**坐标变换**而非图例标签——`axvline`/`axhline`
> 的辅助线(AGC 切换、MCS 门限)带混合变换,吸附上去会把规格线报成测量
> 值;而星座图与 blocker 曲线恰恰是无标签的真数据。星座点云(5976 点 ×4)
> 标为不吸附并附原因,该处游标自由定位并在读数里注明。隔离底板掩码点以
> `null` 传输,游标不吸附——它们的含义就是"不可归因"。

## 两种出货形态:解释版与编译版

| flavor | wifitrx 如何进包 | 用途 |
|---|---|---|
| `interpreted`(默认) | 源码,走 Chaquopy srcDirs | 日常构建、金标对拍、端上守卫 |
| `compiled` | 逐 ABI 的 wheel,52 个模块为 `.so` | 交付给外部时不想让算法被解压即读 |

```bash
# 本机试(不需要 NDK,用自己的编译器验"能编、编完测试还过不过")
pip install "cython<3.3" build
python android/tools/android_wheel.py --package wifitrx \
    --compile cal,chain,impairments,metrics,link,dsp --host --outdir /tmp/w
# CI 里的交叉编译见 .github/workflows/android.yml 的 compiled job
```

**三个必须钉死的前提**(实测,非推测):

- **Cython 3.3.0 不可用**:在虚数字面量上编译器崩溃(`ImagNode` →
  `AttributeError`),而本仓是复基带、`1j` 遍地。3.0.11 / 3.1.6 可用。
- **必须 `-X annotation_typing=False`**:cythonise 会把类型标注变成运行时
  强制的 C 类型,而本仓标注是描述性的、numpy 标量四处流动
  (`max_db: float | None` 拒收 `np.float64`)。不加该选项时全量测试
  291 过 / 2 败,加上后 293 全过。
- **必须显式导出模块初始化函数**:`-fvisibility=hidden` 会把
  `PyInit_<模块名>` 一起隐藏,因为 **CPython 3.8 的 `PyMODINIT_FUNC` 不带
  可见性属性**(3.9 起才由 `Py_EXPORTED_SYMBOL` 加上),而 Chaquopy 的
  Android target 正是 3.8。表现是构建全绿、端上 import 报
  `does not define module export function (PyInit_sync)`。所以命令行显式
  `-DPyMODINIT_FUNC=__attribute__((visibility("default"))) PyObject*`。
  **`--host` 试编译复现不了它**:宿主机 Python ≥3.9,头文件替你导出了。

> **为什么这一条要有物理门禁。** 上面三条里,只有它在所有构建期信号上都
> 看不出来:编译成功、wheel 完整、`--native` 通过、APK 里 `.so` 就在该在
> 的位置。所以 CI 在打包前用 NDK 的 `llvm-nm` 逐个查 wheel 里每个 `.so`
> 是否导出 `PyInit_<模块名>`(`android/tools/check_wheel_exports.py`);
> 桌面侧另有守卫断言构建器拼出的命令行(见 `tests/test_android_bridge.py`)。

> **这个变更买到什么,以及买不到什么。** 它把读**算法**的成本从"解压即读"
> 抬到"要反汇编"。它**不**保护:WebView 资产(明文,写清了每个桥接口与
> 整个流程)、未编译模块(仍是字节码)、以及**字面常量**——它们原样留在
> 常量池里,金标值、`GAP_TOLERANCE_DB`、`RESIDUAL_SPEC` 的文字说明都能被
> 精确搜出。它不是许可保护,也不是对 UI 已展示内容的混淆。

## 已知代价(选型时已明示)

- APK ~200 MB 量级(CPython + numpy + scipy + matplotlib × 2 ABI);
  只保留 arm64-v8a(真机)与 x86_64(模拟器/CI)。
- 320 MHz 全序列在手机上分钟级 + 发热——护栏与明示,不是要修的 bug。
- matplotlib 图内文字英文(项目语言规,CJK 字形本就不可用)。
