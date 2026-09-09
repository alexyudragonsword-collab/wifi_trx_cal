---
type: project_topic
status: active
summary: "LO 相噪经 OFDM 每符号公共相位(CPE)去除后剩下什么:四配置隔离法、sinc² 分割、自由 VCO 地板、估计台阶、两种 EVM 口径——0.7.8–0.7.21 的物理结论与被推翻的判断。"
tags: [phase-noise, cpe, ofdm, pll, evm, metrology]
contains: [conclusion, pitfall, decision, correction]
created: "2026-09-09"
updated: "2026-09-09"
related: [docs/pn_cpe_note_11ac_vs_11ax.pdf, docs/pn_cpe_note_loop_bandwidth.pdf, docs/pn_cpe_note_estimation_ladder.pdf, docs/backlog_zh.md#B15, docs/backlog_zh.md#B17, docs/backlog_zh.md#B18]
authoring_mode: ai_generated
---
# 相噪与 CPE 去除(当前真相)

## 形成背景

4096-QAM 的 −38 dB TX EVM 预算里 LO 相噪是最大单项。调制解调器每个 OFDM 符号
会从导频估一个公共相位并转掉,所以"相噪吃掉多少 EVM"不是积分相噪(IPN),而是
CPE 去除后**剩下**的那部分。2026-09-04 起用隔离法(只开相噪、真信道 = 1、直接
读数)把这件事做成 `pn_cpe_study` 分析(五页)、库函数
`wifitrx.link.pn_cpe_study` / `impairments.phase_noise.cpe_partition` 与三篇
英文 PDF 短文。本文是这些结论的当前版本;数字若与本文不符,以代码与测试为准。

## 当前结论

- **分割公式**:符号平均相位是长 T 的矩形平均,可去除份额的权重是 sinc²(fT),
  留下的 ICI 权重是 1 − sinc²(fT);交接频率 f₋₃dB = 0.443/T——11ax/be(12.8 µs)
  35 kHz,传统 3.2 µs 138 kHz。平台宽于 1/T 时 σ²_CPE ≈ S₀/(2T)。出货 LO 剖面
  (−104.1 dBc/Hz 平台,10–100 kHz)恰好落在两个交接频率之间:11ac/n 去掉约
  28 %,11ax/be 约 6 %(80 MHz 实测 6.6 % / 28.7 %)。
- **`EvmBudget.cpe_tracked_fraction`**(0.7.9)不再是 0.5 常数,而是按剖面与符号长
  现算——旧常数在 11ax 上乐观约 2.7 dB。
- **四个测量配置**(每个都是直接读数,不是总量减一):① 不去 CPE;② genie CPE
  (全音对理想参考);③ LTF 对粗 CFO + 导频斜率细 CFO 捕获 + LTF 信道估计 +
  genie CPE;④ 同 ③ 但 N_p 导频 CPE(modem 形式)。40 MHz 11ax/be 单 LO 8 帧:
  ② −44.2,③ −42.5,④ −42.4 dB。
- **估计台阶的闭式**:③−② ≈ 10·log(1+ρ/2)(两个 LTF 平均,ρ≈1 → 1.76 dB,实测
  1.73):冻结的 LTF 误差整包付一次,随 LTF 数平均、不随符号数平均;
  ④−③ ≈ 10·log(1+1/(2N_p))(共模,随导频数平均):N_p = 16 → 0.13 dB,实测 0.09。
- **残余 CFO 是频偏处的一根相噪线**:② 只留符号内斜坡 1 − sinc²(ΔfT)(2 kHz →
  −26.7 dB,闭式 −26.6);① 逐符号旋转直至糊掉(+4.1 dB);③/④ 经捕获级免疫。
  LTF 对单独会在相噪下读出伪 CFO(12.8 µs LTF 约 25 Hz rms,3.2 µs 约 180 Hz),
  必须用导频斜率(整帧基线)细估,否则误差灌回符号内 ICI(11ac 差 0.6 dB)。
- **自由 VCO 地板**:1/f² 振荡器经 CPE 去除后剩 ∫k₂/f²[1−sinc²(fT)]df = π²k₂T/3,
  随 T 线性——3.2 µs −42.9 dB、12.8 µs −36.8 dB(k₂ 取 1 MHz 处 −116.1 dBc/Hz)。
  这解释了 PLL 环路带宽页的形状:11ax 是尖谷(距最优 5.0 dB),11ac 左侧平坦
  (0.9 dB);11ax 上抖动最优 ≈ EVM 最优(300 kHz),11ac 上不是。
- **两制式差距**(40 MHz,32 帧 × 4 种子):11ax/be 在 modem 形式下比 11ac/n 差
  **1.10 ± 0.27 dB**;主体是两符号长的 ICI 底板比(约 1.2 dB),导频项只是修正量。
- **两种 EVM 口径**(0.7.18,交付层面):`*_evm_db` 隔离口径(逐音均衡到理想参考 +
  genie CPE,重放闭环目标);`*_evm_modem_db` modem 口径(LTF CFO 捕获 + 跨音
  平滑 9 音的 LTF 信道估计 + 导频 CPE),MCS13 判定按后者。纯噪声链上两者之差
  = 1.90 dB(理论 1.89)。旗舰 320 MHz / 4096-QAM:−42.4 / −41.9 dB。

## 坑与被推翻的判断(contains: pitfall, correction)

- **导频表曾是 802.11a/ac 的**,对 11ax/be 也照用(40 MHz 6 个而标准 16 个;320 MHz
  只覆盖 24 % 带宽)。0.7.17 分表并按序号映射进无空音的模型音块。更正:40 MHz
  制式差距 1.4 ± 0.2 → 1.10 ± 0.27 dB;导频台阶 0.33 → 0.09 dB。**我在体检报告里
  把这个更正的方向写反了**(说会变大);导频变多是 11ax 变好,差距变小。
- **"32 帧钉死"说过头了**(0.7.11):8 帧每柱约 0.3 dB rms,32 帧约 0.15;差值
  要报散布。
- **"PLL 的 EVM 最优 ≠ 抖动最优"只对 11ac 成立**,11ax 上两者重合——最初的
  一般化说法被 0.7.13 的地板闭式推翻。
- **modem 口径只差两项估计噪声(≈1.9 dB)"只对白噪声成立**:校准后的链上原始 LTF
  估计会把残余 IQ 镜像 / PA 失真的 LTF 图案冻结进 H(逐音变号),旗舰 modem 口径
  读 −37.2 dB 不过线;跨音平滑(接收机算法)去掉它:3/5/9/17 音 → −40.0/−40.8/
  −41.4/−41.8。用户拍板默认 9 音,宽度写进 cal-state `conditions.ce_smooth_tones`。
- **用训练波形给 DPD 打分是隐性乐观**:打分帧一换成带导频的帧,一个峰值超训练
  包络 1.2 dB 的符号让多项式 DPD 外推,该符号读 −3.8 dB。`dpd.BoundedDPD` 在训练
  峰值处饱和(LUT 行为)。
- **计量纪律**:所有拆分用隔离法;闭式只用来对拍,不用来拟合;随测量配置漂移的
  结论先当伪影(参见 0.7.11 的散布量化与 0.7.16 的 CI 硬件抖动)。

## 指针

- 代码:`src/wifitrx/link/pn_cpe_study.py`、`impairments/phase_noise.py`
  (`cpe_partition`、`TypeIIPllPhase`、`free_vco_ici_floor`)、`cal/sequence.py`
  (`score_views`)、`waveform/pilots.py`、`waveform/preamble.py`
  (`smooth_channel_estimate`)、`dpd/bounded.py`。
- 守卫:`tests/test_phase_noise.py`、`tests/test_gui_specs.py`(pn 三条)、
  `tests/test_waveform.py`(导频表)、`tests/test_evm_views.py`。
- 记录:`docs/backlog_zh.md` B15/B17/B18;`cairn/LOG.md` R18–R26;
  CHANGELOG 0.7.8–0.7.18。
