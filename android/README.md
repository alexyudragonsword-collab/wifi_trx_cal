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

> **端上 scipy/numpy 远旧于桌面**——"同一套物理"的最终裁决属于模拟器
> 金标对拍(`connectedDebugAndroidTest`),不是构建绿灯。旧版若在金标
> 上翻车,处置是把触发差异的调用点降级适配并重新对拍,不是放宽容差。

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

## 已知代价(选型时已明示)

- APK ~200 MB 量级(CPython + numpy + scipy + matplotlib × 2 ABI);
  只保留 arm64-v8a(真机)与 x86_64(模拟器/CI)。
- 320 MHz 全序列在手机上分钟级 + 发热——护栏与明示,不是要修的 bug。
- matplotlib 图内文字英文(项目语言规,CJK 字形本就不可用)。
