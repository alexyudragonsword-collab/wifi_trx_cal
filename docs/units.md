# 单位约定 (Units Convention)

全链路采用统一的 dBm 记账,任何节点功率可直接读出。

## 复基带样本 = sqrt(mW)

模拟域复基带样本的单位是 `sqrt(mW)`:

```
power_dbm(x) = 10*log10(mean(|x|^2))
```

即 `mean(|x|^2)` 直接就是该节点的平均功率(mW)。`wifitrx.units` 提供
`power_dbm / peak_dbm / scale_to_dbm / dbm_to_mw / db_to_amp` 等工具。

## 数字域 = 满量程归一

DAC 输入与 ADC 输出为满量程归一的数字样本(|I|, |Q| ≤ 1)。数字↔模拟边界
由转换器持有 `fullscale_dbm` 参数完成:

- **定义**:`fullscale_dbm` = 满量程 CW 音(|x_digital| = 1)的平均功率。
- DAC:`x_analog = x_digital * sqrt(10^(fullscale_dbm/10))`(默认 +4 dBm)
- ADC:反向,默认 +2 dBm;AGC 目标 = `fullscale_dbm - adc_backoff_db`(默认回退 12 dB)。

数字域功率读数(`power_dbm(x_digital)`)可理解为 dBFS:加上
`fullscale_dbm` 即得对应模拟功率。

## 重要节点默认值

| 节点 | 约定 |
|---|---|
| DAC 满量程 | +4 dBm(CW) |
| PA | 增益 26 dB,Psat 28 dBm(峰值包络),P1dB ≈ 22 dBm(Saleh 导出) |
| 环回耦合 | −40 dB |
| ADC 满量程 | +2 dBm,AGC 目标 −10 dBm |
| 热噪声 | −173.98 dBm/Hz + NF,在 RX 输入按当前 AGC 档级联 NF 一次性注入 |

## 相位噪声

内部 PSD 为**双边带** S_phi(f) [rad²/Hz];谱点与 dBc/Hz 的换算:
`L(f) = 10*log10(S_phi/2)`。时域样本经 `synth_from_psd` 合成,作用方式
`x * exp(1j*phi)`(TX)/ `x * exp(-1j*phi)`(RX)。

## 仿真采样率

`fs = bandwidth * oversampling`。ACLR / DPD 需要 `oversampling = 4`
(邻道与三阶再生长带宽);仅带内校准验证可用 `oversampling = 2` 提速。
DAC/ADC 镜像/replica 不建模(全链单一采样率)。
