# wifitrx — WiFi 7 直接变频收发器行为模型与校准算法套件

面向 CMOS WiFi 7(802.11be)收发器设计的**复基带等效行为模型 + 校准算法验证平台**,
最大带宽 320 MHz,TX/RX 均为直接变频 IQ 结构,PA Psat = 28 dBm(PAE@Psat = 35%)。
自包含仓库:核心波形/PA/DPD/相噪代码从内部同级仓库拷贝(见 `PROVENANCE.md`),
仅依赖 numpy / scipy / matplotlib。

## 快速上手

```bash
pip install -e .            # 安装
pip install pytest && python -m pytest tests/ -v    # 全部测试 (~15 s)

# 逐损伤 EVM/ACLR 研究
python examples/run_impairment_study.py

# 完整校准序列 + 中文报告 (reports/cal_report.md + 图)
python examples/run_full_calibration.py --bw 160e6

# 通信算法工程师接入示例:外部 IQ 波形过已校准链路
python examples/run_external_waveform.py --iq your_wave.npy --bw 320e6 --fs 1.28e9

# 链路预算 / MCS 灵敏度 / EVM 预算
python examples/run_link_budget.py --bw 320e6

# 第二期:PA 温漂跟踪 DPD / 阻塞与脏信道 / MIMO 2x2 / Monte-Carlo 良率
python examples/run_pa_drift_tracking.py
python examples/run_blocker_study.py
python examples/run_mimo_2x2.py
python examples/run_yield.py --runs 20

# GUI 工作台 (pip install -e .[gui])
python app/main.py

# CI: scripts/ci_fast.sh (快速门禁) / scripts/ci_nightly.sh (全量+示例)
```

## 模型覆盖的损伤

| 环节 | 损伤 |
|---|---|
| DAC/ADC | 量化、削顶、孔径抖动、满量程 dBm 标定、ZOH droop(可选) |
| 模拟基带 | 可调 LPF(RC 工艺偏差 ±20% + 调谐码)、VGA/AGC |
| IQ 调制/解调 | **频率相关** IQ 失衡(I/Q 双实轨 FIR + 增益/相位 + 群时延失配)、TX LO 泄漏、RX DC(随 AGC 档变化) |
| LO/PLL | 查表/Leeson 相噪剖面时域合成(默认 WiFi7 级 IPN ≈ −44 dBc)、fractional-N 杂散、TX/RX 共用或独立 LO |
| PA | Saleh/GMP 归一化模型的 dBm 封装(Psat=28 dBm、P1dB 导出、PAE 平方根律)|
| RX 前端 | 分档 LNA(增益/NF/IIP3)、级联噪声一次性注入、无记忆非线性 |
| 环回 | 耦合衰减、延迟、RX-LO 频偏旋转、包络检波器(平方律)观测路 |

## 校准算法(`wifitrx.cal`,规范顺序见 `docs/cal_order_zh.md`)

1. LPF corner(TX 经包络检波 / RX 经 ADC,RC 码搜索)
2. RX DC offset(逐 AGC 档数字消除表)
3. TX LO 泄漏(包络检波抛物线下降 + 环回 DC-bin 精修)
4. 环回时延对齐 / CFO / SCO 估计
5. TX 频变 IQ(**RX-LO 偏移法**,RX 响应精确抵消;包络检波兜底)→ 群时延
6. RX 频变 IQ(经已校 TX 比值法;另有基于已知帧的 LS 估计器)
7. TX 功率(码字→dBm 查找表)
8. DPD(ILA + GMP,宽带观测模式,工作点训练)
9. AGC 验证扫描

端到端结果(随机工艺损伤 + 全部校准,见 `tests/test_e2e.py`):
320 MHz / 4096-QAM 下 **TX EVM ≤ −38 dB**(802.11be MCS13 要求),
校正状态可导出/导入 JSON(`cal_state.json`)交付通信算法团队。

## 文档

- `docs/interface_zh.md` — 面向通信算法工程师的接口文档(调用契约、单位、JSON schema、外部波形接入)
- `docs/units.md` — 全链路单位约定
- `docs/cal_order_zh.md` — 校准顺序依据
- `PROVENANCE.md` — 拷贝代码来源

## 模型给出的设计洞察

1. **4096-QAM 必须配低相噪综合器**:IPN ≈ −38 dBc 的 LO 单独就吃掉整个 −38 dB EVM 预算;需 −43 dBc 量级(0.4° rms)。
2. **320 MHz 模式 TX 基带滤波器必须比信道宽**(≥1.3×BW/2),否则 DPD 预校正频谱被滤除,PA 残余 EVM 卡在 −39 dB 附近。
3. **IIP2 校准必须排在 TX LO 泄漏校准之后**:PA 三阶产物 tone2×leak×tone1* 与 IM2 拍频同 bin,未校载波泄漏时零点被掩埋 ~35 dB;测量还需相位随机化相干平均以压制 ADC/DAC 量化杂散。
4. **DPD 温漂跟踪的遗忘因子必须按"块"激进设置**(~0.4/块):每个观测块含数千样本,统计噪声极小,而保守遗忘会让漂移前的陈旧数据主导 RLS 协方差,跟踪落后 oracle 10 dB 以上。
5. **窄带模式:校准激励频率必须随带宽缩放,corner 比例保持统一、不要放宽**:23 MHz 探测音在 20 MHz 信道是带外音——IIP2 trim 在噪声上乱走、AGC 扫描读不到 SNR,这是 20 MHz 校准失败的真正(也是唯一的)功能性原因(`scaled_probe`)。corner 比例全带宽统一 1.3×(TX,DPD 带宽)/1.12×(RX,信道选择):无伪影仪表实测 20 MHz 单 LPF 地板分别为 −55/−50 dB,比校准后整链实际到达的 ~−42 dB 低 12 dB 以上,4096-QAM 的 −38 dB 也满足有余。曾短暂采用的窄带 3× 策略已撤销:它只多买 ~1.5 dB TX EVM 和 ~11 dB 环回观测底板——没人消费的余量——代价却是邻道(+20 MHz)模拟抑制从 ~25 dB 塌到 ~0 dB,blocker 全压到 ADC 动态范围上。EVM 指标不给 blocker 定价,corner 规格必须给(`recommended_lpf_corner_hz`)。
6. **先校准测量仪器,再给电路定规格**:最初诊断出的"20 MHz 下 1.3× corner 把 EVM 钉死在 −33 dB"是**测量伪影**——测试接收机模型里的时延补偿用循环 FFT 移位整体前移捕获,把 warm-up 样本卷进最后一个 OFDM 符号的 FFT 窗;误差幅度正比于滤波器群时延(所以跟着 corner 变!)、反比于 FFT 长度(所以 320 MHz 看不见、20 MHz 最重),完美伪装成"corner 越紧 ISI 越大"的物理地板。修复(循环 guard 尾垫 + 整数切片 + 仅小数部分 FFT 移位,`compensate_delay`)后还剩第二层小伪影——时延补偿把最后一个符号的 FFT 窗推出 burst 末尾几个采样,截断的 ramp-down 让"延续内容"失真,在 −55 dB 以下的深地板上仍值 >8 dB;`tx_evm` 现在多发一个 padding 符号、只对内部符号打分(实验室标准做法)。全部修完后真实地板在 1.3× 就有 −55 dB。滤波器阶数同理:修复前测得"3 阶比 5 阶好 6 dB",修复后只剩 2–4 dB、且全部发生在 −50 dB 以下的深水区。两层伪影修完后重新裁决,基于伪影数据定下的窄带 3× corner 策略随之撤销(见洞察 5)。任何"随测量配置漂移"的结论都要先怀疑测量本身。
