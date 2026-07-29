# 代码来源说明 (Provenance)

本仓库为自包含交付仓库:以下模块从内部同级仓库拷贝(vendored),仅依赖
numpy/scipy/matplotlib。上游修复需手工同步;每个文件头部有来源标注。

| wifitrx 路径 | 来源仓库:路径 | 改动 |
|---|---|---|
| `src/wifitrx/waveform/ofdm.py` | `PA_DPD:src/padpd/waveform/ofdm.py` | 无(后续经 wrapper 扩展 preamble/pilot) |
| `src/wifitrx/waveform/qam.py` | `PA_DPD:src/padpd/waveform/qam.py` | 无 |
| `src/wifitrx/metrics/{evm,aclr,spectrum,ccdf,amam}.py` | `PA_DPD:src/padpd/metrics/*` | 去除 opendpd_compat |
| `src/wifitrx/pa/{base,saleh,memory_polynomial,gmp,reference_pa}.py` | `PA_DPD:src/padpd/pa/*` | 精简 `__init__`(去 ddr/drift/hb_import/presets) |
| `src/wifitrx/dpd/{ila,adaptive}.py` | `PA_DPD:src/padpd/dpd/*` | 无 |
| `src/wifitrx/dpd/cfr.py` | `PA_DPD:src/padpd/cfr.py` | 移动到 dpd/ 下 |
| `src/wifitrx/cal/sync.py` | `PA_DPD:src/padpd/data/align.py` | M2 起扩展 CFO/SCO 估计 |
| `src/wifitrx/cal/loops.py` | `pll_simulator:src/pllsim/calibration/lms.py` | 无 |
| `src/wifitrx/plotting.py` | `PA_DPD:src/padpd/plotting.py` | 无 |
| `src/wifitrx/impairments/phase_noise.py` | `pll_simulator:src/pllsim/core/{colored,noise,jitter}.py` | 合并;删除电路级噪声源与 FreqResponse 预算部分 |

概念/结构参考(未逐行拷贝):

- `receiver_link_budget:modules/{nf,ip3,snr}_calculator.py, agc_sweep.py` → `src/wifitrx/link/budget.py`, `src/wifitrx/chain/agc.py`
- `adc_toolbox:vendor/ADCToolbox .../siggen/nonidealities.py` → `src/wifitrx/impairments/converters.py`(重构为 (x,t) 自由函数)
- `adc_toolbox:app/tiadc_model.py` 的 注入真值→估计→校正→验证 模式 → `src/wifitrx/cal/base.py`
