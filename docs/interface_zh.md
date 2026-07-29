# wifitrx 接口文档(面向通信算法工程师)

本文档说明如何把你们的 802.11be PHY 波形接入收发器模型、如何使用/复现校准
状态,以及各损伤参数的含义。单位约定见 `units.md`。

## 1. 最小调用契约

```python
import numpy as np
from wifitrx.chain import TxChain, TxParams, RxChain, RxParams, LoopbackPath, run_loopback

bw = 320e6
fs = bw * 4                      # 你们波形的采样率必须等于 bw * oversampling
rng = np.random.default_rng(1)
tx = TxChain(TxParams(bandwidth_hz=bw).randomize(rng), fs)   # 随机工艺损伤
rx = RxChain(RxParams(bandwidth_hz=bw).randomize(rng), fs)

x = np.load("your_11be_waveform.npy")   # 复基带,数字满量程单位,|I|,|Q| <= 1
                                        # 建议 rms ~ 0.1-0.15(PAPR 余量)

y_pa = tx(x)                            # -> PA 输出,sqrt(mW) 单位
cap  = run_loopback(tx, rx, x, LoopbackPath(atten_db=40.0, delay_ns=6.0))
                                        # -> RX 数字输出(满量程单位)
```

- `TxChain.__call__(x_digital, phi_lo=None, nodes=None)`:
  - `x_digital`:复基带数字样本(满量程归一)。
  - `nodes`:传入 dict 可回读各节点功率(`dac_out_dbm / bb_out_dbm /
    mixer_out_dbm / pa_out_dbm / pa_avg_pae`)。
  - 返回 PA 输出(sqrt(mW))。
- `RxChain.__call__(y_rf, phi_lo=None, rng=None, nodes=None)`:
  - `y_rf`:RX 输入(sqrt(mW));先调 `rx.agc(p_in_dbm)` 设定增益。
  - 返回数字输出(满量程归一,已应用数字校正)。
- `run_loopback(tx, rx, x, path, shared_lo=True)`:片上自环回
  (共 LO 时 TX/RX 相噪相关,环回中大部分抵消——与真实芯片一致)。
- 捕获对齐:`wifitrx.cal.sequence.capture_aligned(tx, rx, path, x)`
  自带 512 样本循环预热(稳定 IIR 滤波器)+ 时延对齐。

## 2. 波形要求

| 项 | 要求 |
|---|---|
| 采样率 | `fs = bandwidth * oversampling`;需要 ACLR/DPD 时 oversampling=4,仅带内验证可用 2 |
| 幅度 | 数字满量程 |I|,|Q| ≤ 1;推荐 rms 0.10–0.15(4096-QAM PAPR + DAC 余量) |
| 类型 | numpy complex128 一维数组 |
| 帧结构 | 任意(模型与帧结构无关)。若使用本仓库的简化 preamble/pilot:`wifitrx.waveform.preamble.build_frame` / `pilots.generate_ofdm_with_pilots` |

## 3. 校准状态 JSON(交付物)

```python
from wifitrx.cal.base import save_cal_state, load_cal_state
save_cal_state("cal_state.json", tx.correction_state(), rx.correction_state())
tx_state, rx_state = load_cal_state("cal_state.json")
tx.load_correction_state(tx_state); rx.load_correction_state(rx_state)
```

Schema(`wifitrx-cal-state-v1`):

```jsonc
{
  "format": "wifitrx-cal-state-v1",
  "tx": {
    "dc_pre":  [re, im],          // TX LO 泄漏数字预消除(DC)
    "w1": null | [[re...],[im...]],  // widely-linear 直通 FIR(通常 null=1)
    "w2": [[re...],[im...]],      // widely-linear 共轭路复 FIR(镜像校正)
    "gain_code_db": float,        // TX 功率码
    "phase_corr_deg": float,      // MIMO 链间相位对齐(单链为 0)
    "delay_corr_samples": float,  // MIMO 链间时延对齐(单链为 0)
    "lpf_rc_code": int            // TX LPF RC 调谐码(模拟寄存器)
  },
  "rx": {
    "dc_post": {"0": [re,im], ...},  // 逐 AGC 档数字 DC 消除
    "w1": null, "w2": [[re...],[im...]],
    "frac_delay_iq": float,       // I/Q 分数延迟微调(样本)
    "lpf_rc_code": int,           // RX LPF RC 调谐码
    "im2_trim_code": int          // 混频器 IM2 trim 码
  },
  "results": [ ... ],             // 每步 summary,含:
                                  //   passed     是否达标
                                  //   saturated  校准码是否触轨(达标但
                                  //              无温度/老化余量,独立事实)
                                  //   spec       该步当时生效的验收规格
                                  //              {metric, limit, sense},
                                  //              随文件走,校验时以此为准
  "provenance": { ... }           // 生成溯源:git commit、dirty、时间、版本
}
```

**独立检查器**:`python -m wifitrx.handoff inspect cal_state.json`;
`src/wifitrx/handoff/inspect.py` 只依赖标准库,可直接拷到 JSON 旁边
`python inspect.py cal_state.json` 运行(无需安装本库)。检查以文件内嵌的
spec 为准——旧文件按其校准当时的规格判定,而不是按本库当前的表。

widely-linear 校正定义:`x_c = w1*x + w2*conj(x)`(w1 为 null 时取 1)。
FIR 以中心抽头为群时延参考(等效 `np.convolve(mode="same")`)。
等价的 2×2 实系数 MIMO 形式:`[I';Q'] = [[Re(w1+w2), -Im(w1-w2)],
[Im(w1+w2), Re(w1-w2)]] * [I;Q]`(逐抽头)。

模拟域调谐码(`lpf_rc_code`、`im2_trim_code`)已随数字校正状态一并序列化:
仅凭 JSON 即可完整恢复芯片的全部校准编程,无需手工补设。

## 4. 损伤参数速查(`chain/params.py`)

| 参数 | 单位 | 典型/默认 | 说明 |
|---|---|---|---|
| `TxParams.iq.gain_db / phase_deg` | dB / ° | ±0.5 / ±3 | 频率平坦 IQ 失衡 |
| `TxParams.iq.gd_mismatch_ps` | ps | ±300 | I/Q 轨群时延失配(Q 轨延迟) |
| `TxParams.iq.rail_ripple_db / rail_gd_ripple_ns` | dB / ns | 0.1–0.5 / 0.05–0.2 | 双轨频响失配(反对称分配) |
| `TxParams.lo_leak_dbm` | dBm | −32…−22 | 调制器输出处 LO 泄漏绝对功率 |
| `TxParams.lpf.rc_error` | — | ±0.2 | LPF corner 工艺偏差 |
| `TxParams.lo.profile` | dBc/Hz | WiFi7 级(IPN≈−44dBc) | 相噪剖面(查表) |
| `psat_dbm / pa_gain_db / pae_max` | dBm/dB/— | 28 / 26 / 0.35 | PA |
| `RxParams.dc_offset` | sqrt(mW) | 逐档 ~0.003–0.02 | 基带节点 DC(LO 自混频) |
| `RxParams.lna_states` | — | 4 档 | 增益/NF/IIP3/切换门限 |
| `RxParams.adc.bits / fullscale_dbm / jitter_ps_rms` | — | 11 / 2 / 0 | ADC |

每个损伤块都有 `enabled` 开关;`params.injected()` 返回注入真值(校准算法
的对照标准);`params.randomize(rng)` 生成随机工艺样本(Monte-Carlo)。

## 5. 指标工具

- `wifitrx.metrics.evm(rx_syms, tx_syms, equalize="per_tone")`,
  `metrics.cpe.correct_cpe`(逐符号公共相位去除,规范 EVM 测法)
- `metrics.aclr(x, fs, bw)`(需 fs ≥ 3bw)、`metrics.psd` + `default_wifi_mask`
- `metrics.irr.tone_image_irr_db / comb_irr_db / lo_leak_dbc`
- `cal.sequence.tx_evm`(PA 输出、802.11be TX 规范测量点)、
  `cal.sequence.loopback_evm`(TX+RX 复合)

## 6. 已知建模简化

- DAC/ADC 镜像/replica 不建模(单一仿真采样率);ZOH droop 可选。
- 无信道编码/完整 11be 帧——全链路调制解调由你们的 PHY 负责。
- PA 为无记忆 Saleh(可换 GMP/记忆多项式,`ScaledPA` 支持任意 `PAModel`)。
- RX 镜像抑制混频器、谐波混频等未建模。
