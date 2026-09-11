---
type: project_topic
status: active
summary: "wifitrx 的 Android 出货线(Chaquopy + WebView,解释版与 Cython 编译版两种 APK):裁决协议、端上栈约束、以及每一次'构建绿但端上错'的根因。"
tags: [android, chaquopy, cython, ci, packaging]
contains: [procedure, reference, lesson, decision]
created: "2026-09-09"
updated: "2026-09-11"
related:
  - android/README.md
  - .github/workflows/android.yml
  - tests/test_android_bridge.py
  - docs/backlog_zh.md#R1
  - cairn/守卫有效性.md
authoring_mode: ai_generated
---
# Android 出货线(当前真相)

## 形成背景

同一套 `src/wifitrx/` + `app/` 数据层要在 Qt 桌面与 Android 两端出货。Android
是 Chaquopy 嵌入的 CPython 3.8 + WebView 壳(`android/`),桥 `bridge.py` JSON
进出;0.7.6 起并出一个 Cython 编译版 APK(`cal/chain/impairments/metrics/link/dsp`
编成 `.so`)。端上 numpy 1.19.5 / scipy 1.4.1 / matplotlib 3.6.0,**低于桌面下限**,
所以物理是否一致不能由构建结论回答。

## 当前结论(裁决协议)

- **构建绿 ≠ 端上物理对。** 出货代码(`src/wifitrx/`、`app/specs.py`、
  `app/reference.py`、`app/inspector_data.py`、`android/`)一变,必须重新 dispatch
  `android.yml`,读三个 job(`build` / `golden` / `compiled`)的**断言步骤**结论:
  `on-device tests actually ran`(精确条数 5,不是下限)、`the wheels must carry
  this tree's version`、`every compiled module must export its init symbol`。
  条数核对由 job 自身断言,不靠人工翻日志(日志接口按大小截断,取不到中段)。
- **金标**:`android/tools/make_golden.py` 在桌面生成 `golden.json`(四个案例:
  full_cal / rx_evm_sweep / spur_planner / pn_cpe_study),端上 `bridge.self_check()`
  与模拟器 GoldenTest 调同一函数比对(0.05 dB 绝对或 1e-3 相对)。真机 arm64 的
  Self-check 是用户手动,已裁决过一次(2026-08-23)。
- **两端共用数据层**:分析注册表、检查器内容、参考页数据、金标对拍都只写一份;
  各写各的必然漂移(0.6.5 Inspector 缺三张表、0.7.1 Reference 收不到文件)。
- **端上调用面守卫**在桌面测试期拦截:`tests/test_android_bridge.py` 扫全仓的
  scipy / numpy 调用对照 1.4.1 / 1.19.5 允许表(`np.trapezoid`、`np.newaxis` 不在
  表内;`np.trapz`、`np.sinc`、`np.unwrap`、`np.convolve` 在)。
- **版本**:`appVersion` 一处(0.7.19 起),`versionCode` 由它派生;wheel 文件名
  必须带 pyproject 的版本号(CI 断言)。

## 坑(contains: lesson)——每一条都是"所有构建期信号全绿"的缺陷

- **`correlation_lags`**(0.6.2):scipy 1.4.1 没有;标注的风险一天内兑现。
  修法用数学恒等替代;由此建立调用面守卫。
- **numpy 2.0 API 越界**(0.6.6):守卫补齐 numpy 面。
- **`PyInit_*` 未导出**(0.7.7):`-fvisibility=hidden` 把模块初始化函数一并藏了,
  因为 **CPython 3.8 的 `PyMODINIT_FUNC` 不带可见性属性**(3.9 起才有),宿主
  3.11 头文件替你导出,`--host` 试编译永远复现不了。修法显式
  `-DPyMODINIT_FUNC=__attribute__((visibility("default"))) PyObject*`,并用 NDK
  `llvm-nm` 逐个 `.so` 查导出(`check_wheel_exports.py`)。更正了 R16 把它归因为
  "包初始化器被拒"的判断。
- **Cython 3.3 在虚数字面量上崩溃**,钉 `<3.3`;必须 `-X annotation_typing=False`,
  否则描述性标注被当强制 C 类型(291/2 败 → 293 全过)。修编译器行为,不修分析层。
- **`build-android-wheel/` 误提交**(0.7.6):构建器缓存参考 wheel 取 dist-info,
  陈旧副本把编译版 METADATA 冻在 0.7.6,连续两版错标签出货。已 ignore + CI 断言。
- **artifact 存储配额**(run #44):上传失败排在模拟器之前,把唯一的物理检查跳过。
  修法:上传移到端上门禁之后、`continue-on-error`、保留 7 天;守卫断言顺序。
- **桌面 CI 按硬件抖动**(0.7.16):自检要求金标差值精确 0,GitHub runner 的
  CPU/BLAS 求和顺序读出 7e-15,八天全红没人看——同 numpy 版本也不保证位级复现。
- **守卫要匹配真正干活的那一行**,写完必须用变异确认会红(2026-08-24/25 连踩
  四次:`Python.start`、`annotation_typing=False`、`_drop_package_initializers`)。

## 有意只在一端的能力

Self-check(端上)、≥160 MHz 护栏、Save 的平台惯例差异——见 `android/README.md`
功能对照表;不在表里的单端差异视为漏做。

## 指针

- `android/README.md`(对照表、构建步骤)、`android/tools/android_wheel.py`
  (交叉编译)、`android/tools/check_wheel_exports.py`、`.github/workflows/android.yml`。
- 记录:`cairn/LOG.md` R1–R17、R24;`docs/backlog_zh.md` R1;CHANGELOG 0.6.0–0.7.7、0.7.16。
