# 联合验证 Handoff 指南(通信算法团队用)

本指南定义双方交换波形的**标准格式**与**批量回归流程**。原则:EVM/误码在
你们的解调侧闭环;本模型侧提供物理信道量(功率、PAE、ACLR、复合增益、时延)。
双方各自把数字填进同一张对账单(`handoff_report.md`)。

## 1. 波形文件格式 wifitrx-wave-v1

`.npz` 文件,两个键:

| 键 | 内容 |
|---|---|
| `iq` | 复数一维数组(complex64/128) |
| `meta` | JSON 字符串:`{"format":"wifitrx-wave-v1","fs_hz":...,"bandwidth_hz":...,"scale":...,"description":...}` |

`scale` 幅度约定(详见 `units.md`):
- `digital_fs`:数字满量程(|I|,|Q| ≤ 1;建议 rms 0.10–0.15)——你们 PHY 给 TX 的波形
- `sqrt_mw`:物理 sqrt(mW)——PA 输出 / RX 输入节点

生成与校验(Python):

```python
from wifitrx.handoff import Waveform, save_waveform, validate_waveform
w = Waveform(iq=my_iq, fs_hz=1.28e9, bandwidth_hz=320e6, scale="digital_fs",
             description="11be MCS13 320MHz frame")
assert not validate_waveform(w)   # 返回中文问题列表,空 = 合格
save_waveform("mcs13_320.npz", w)
```

校验规则:复数一维、无 NaN/Inf、样本 ≥1024、fs/bw 为 ≥2 的整数倍、
digital_fs 不超满量程且 rms ≤ 0.3。

## 2. 单波形运行

```bash
python -m wifitrx.handoff run --wave mcs13_320.npz --bw 320e6 \
    --scenario loopback --seed 5 [--cal-state cal_state.json]
```

- `--seed`:被建模芯片的工艺角(同 seed = 同一颗"芯片")
- `--cal-state`:加载已存的校准状态(可复现同一校准结果);不给则现场跑全序列
- `--scenario`:`tx_only`(输出 PA 口波形,sqrt_mw)/ `loopback`(TX→耦合→RX,
  输出数字域,已对齐)/ `rx_only`(输入 sqrt_mw 直接进 RX)

输出:`<name>_out.npz`(结果波形,同格式)+ `<name>_metrics.json`。

## 3. 批量回归与对账单

```bash
python -m wifitrx.handoff regress --dir waves/ --bw 320e6 --out reports/handoff
```

对 `waves/*.npz` 逐个运行,产出 `handoff_report.md`:每行一个波形,左侧为本
模型指标,右侧"通信侧 EVM / 误码 / 备注"三列留空,由你们解调结果回填后双方
对账。坏文件不会中断批量,失败原因写入备注列。

## 4. Python API(嵌入你们的仿真框架)

```python
from wifitrx.handoff import build_calibrated_trx, run_handoff, Waveform
tx, rx = build_calibrated_trx(320e6, 1.28e9, seed=5,
                              cal_state_json="cal_state.json")
res = run_handoff(Waveform(iq=x, fs_hz=1.28e9, bandwidth_hz=320e6),
                  tx, rx, scenario="loopback")
y = res.output.iq        # 喂给你们的解调器
print(res.metrics)       # pa_out_dbm / pa_avg_pae / aclr / 复合增益 / 时延
```

注意:`loopback` 输出已做时延对齐与预热截除,但**未做**均衡/CPE 去除——那是
解调器的职责,保持与真实接收一致。

## 5. 拿到 cal_state.json 后先做的两件事

```bash
python -m wifitrx.handoff inspect cal_state.json   # 结论级检查(仅标准库)
python -m wifitrx.handoff replay  cal_state.json   # 残差表 vs 文件自己的 EVM
```

replay 把 `residuals` 里的每个数按其内嵌 `apply` 配方字面注入干净波形,与
文件自己的实测 TX EVM 闭合,输出三个数:**解释 / 实测 / 未解释**。gap 超过
1 dB 时退出码为 1——意味着残差表解释不了这块芯片的实测,照单搭建的链路仿真
会给出不存在的余量,先来找我们对表,不要往下游传。

往你们仿真里注入残差时**只用 `role: impairment` 的键**,并按 `apply` 文本
的公式来;`duplicates` 里的成对键至多施加其一(取后者);`total` 类是实测
整体,回注一次就是重复计数。JSON 旁的 README.md 由数据自生成,可当速查表。
