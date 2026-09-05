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

# GUI 工作台 (pip install -e .[gui]):三个页签 ——
#   Analyses  八个分析:全量校准(含逐步检查模式)、RX EVM/灵敏度扫描
#             (含隔离贡献分解曲线)、基带噪声扫描(5–40 nV/√Hz 逐密度
#             重解 AGC 门限)、漂移跟踪、阻塞退敏、LO 相噪 vs CPE 去除
#             (四种测量配置隔离读数 + 闭式对拍 + PLL 环路带宽扫描)、
#             杂散规划;校准类分析
#             支持 11ax/be 与 11ac/n 两种制式、64~4096-QAM,基带噪声
#             密度做成参数旋钮(RF-only 前端固定在 6 nV 参考下反嵌)
#   Cal-state inspector  打开交付 JSON,读检查器结论
#   Reference 信号链框图、校准顺序与依赖图(逐边物理理由)、AGC 档位表、
#             损伤参数表;跑完校准后自动填入本次验收与捕获成本
# 结果图为活的 matplotlib 画布,带导航工具栏(框选缩放/平移/另存视图)
python app/main.py

# Android 工作台(android/,Chaquopy + WebView 整包):分析层与桌面同源
# 零改动,图形 SVG 矢量缩放;构建步骤/版本锁/已知代价见 android/README.md


# CI: scripts/ci_fast.sh (快速门禁) / scripts/ci_nightly.sh (全量+示例)
```

## 模型覆盖的损伤

| 环节 | 损伤 |
|---|---|
| DAC/ADC | 量化、削顶、孔径抖动、满量程 dBm 标定、ZOH droop(可选) |
| 模拟基带 | 可调 LPF(RC 工艺偏差 ±20% + 调谐码)、VGA/AGC |
| IQ 调制/解调 | **频率相关** IQ 失衡(I/Q 双实轨 FIR + 增益/相位 + 群时延失配)、TX LO 泄漏、RX DC(随 AGC 档变化) |
| LO/PLL | 查表/Leeson 相噪剖面时域合成(默认按 PLL 抖动指标锚定:120 fs rms,IPN −46.9 dBc @10 kHz–100 MHz/6 GHz)、fractional-N 杂散、TX/RX 共用或独立 LO |
| PA | Saleh/GMP 归一化模型的 dBm 封装(Psat=28 dBm、P1dB 导出、PAE 平方根律)|
| RX 前端 | **8 档** LNA+混频器(增益 37→−5 dB、NF 3.5→34 dB、IIP3 −20→+12 dBm,门限按噪声-IM3 平衡解出)、级联噪声一次性注入、无记忆非线性 |
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

- **`docs/tutorial.html`** — 图文教程(中英双语可切换,单文件离线):建模原理、
  逐项校准推导与运行结果、设计洞察;`docs/devguide.html` 为开发说明。
  两者由 `python tools/build_docs.py` 构建,正文数字全部来自构建时实跑
- `docs/interface_zh.md` — 面向通信算法工程师的接口文档(调用契约、单位、JSON schema、外部波形接入)
- `docs/units.md` — 全链路单位约定
- `docs/cal_order_zh.md` — 校准顺序依据
- `docs/handoff_zh.md` — 交付/联合验证流程;`docs/circuit_data_zh.md` — 电路数据导入格式
- `docs/pn_cpe_note_11ac_vs_11ax.pdf` — 英文技术短文(3 页):为什么 11ax/be 数制下逐符号
  去 CPE 对相噪 EVM 的收益远小于 11ac/n(推导 + 出货 LO 谱的数字 + 三联图);
  由 `python tools/build_pn_cpe_note.py --out docs/` 生成,数字来自库本身
- `docs/backlog_zh.md` — 待办与已落地项的决策记录
- `CHANGELOG.md` — 版本变更(交付格式的改动在这里显式标注)
- `PROVENANCE.md` — 拷贝代码来源

## 模型给出的设计洞察

1. **4096-QAM 必须配低相噪综合器**:IPN ≈ −38 dBc 的 LO 单独就吃掉整个 −38 dB EVM 预算;需 −43 dBc 量级。模型默认剖面按 PLL 组的抖动指标锚定:**120 fs rms**(10 kHz–100 MHz 积分,6 GHz 载频,IPN −46.9 dBc,0.26° rms);CPE 机制允许积分下限放宽到 ~10 kHz,近端 frac-N 噪声被逐符号公共相位去除赦免。
2. **320 MHz 模式 TX 基带滤波器必须比信道宽**(≥1.3×BW/2),否则 DPD 预校正频谱被滤除,PA 残余 EVM 卡在 −39 dB 附近。
3. **IIP2 校准必须排在 TX LO 泄漏校准之后**:PA 三阶产物 tone2×leak×tone1* 与 IM2 拍频同 bin,未校载波泄漏时零点被掩埋 ~35 dB;测量还需相位随机化相干平均以压制 ADC/DAC 量化杂散。但相位随机化救不了 **TX 侧偶阶失真**——DAC 对双音的二阶积同 bin 且与音对相位差相干,这个透传背景与 trim 码无关,会把 null 填平推歪(320 MHz 下整个码域只剩 ~1 dB 起伏、trim 落点偏 18 码)。解法是**双电平分离**:每码在相差 6 dB 的两个耦合衰减下各测一次,按音调 bin 复比值归一化后相减,线性信道连同 TX 背景精确对消,只留本地混频器 IM2——修复后 trim 正中真值、IIP2 打到 75 dBm 硬件上限(`cal/rx_iip2.py`)。
4. **DPD 温漂跟踪的遗忘因子必须按"块"激进设置**(~0.4/块):每个观测块含数千样本,统计噪声极小,而保守遗忘会让漂移前的陈旧数据主导 RLS 协方差,跟踪落后 oracle 10 dB 以上。
5. **窄带模式:校准激励频率必须随带宽缩放,corner 比例保持统一、不要放宽**:23 MHz 探测音在 20 MHz 信道是带外音——IIP2 trim 在噪声上乱走、AGC 扫描读不到 SNR,这是 20 MHz 校准失败的真正(也是唯一的)功能性原因(`scaled_probe`)。corner 比例全带宽统一 1.3×(TX,DPD 带宽)/1.12×(RX,信道选择):无伪影仪表实测 20 MHz 单 LPF 地板分别为 −55/−50 dB,比校准后整链实际到达的 ~−42 dB 低 12 dB 以上,4096-QAM 的 −38 dB 也满足有余。曾短暂采用的窄带 3× 策略已撤销:它只多买 ~1.5 dB TX EVM 和 ~11 dB 环回观测底板——没人消费的余量——代价却是邻道(+20 MHz)模拟抑制从 ~25 dB 塌到 ~0 dB,blocker 全压到 ADC 动态范围上。EVM 指标不给 blocker 定价,corner 规格必须给(`recommended_lpf_corner_hz`)。
6. **先校准测量仪器,再给电路定规格**:最初诊断出的"20 MHz 下 1.3× corner 把 EVM 钉死在 −33 dB"是**测量伪影**——测试接收机模型里的时延补偿用循环 FFT 移位整体前移捕获,把 warm-up 样本卷进最后一个 OFDM 符号的 FFT 窗;误差幅度正比于滤波器群时延(所以跟着 corner 变!)、反比于 FFT 长度(所以 320 MHz 看不见、20 MHz 最重),完美伪装成"corner 越紧 ISI 越大"的物理地板。修复(循环 guard 尾垫 + 整数切片 + 仅小数部分 FFT 移位,`compensate_delay`)后还剩第二层小伪影——时延补偿把最后一个符号的 FFT 窗推出 burst 末尾几个采样,截断的 ramp-down 让"延续内容"失真,在 −55 dB 以下的深地板上仍值 >8 dB;`tx_evm` 现在多发一个 padding 符号、只对内部符号打分(实验室标准做法)。全部修完后真实地板在 1.3× 就有 −55 dB。滤波器阶数同理:修复前测得"3 阶比 5 阶好 6 dB",修复后只剩 2–4 dB、且全部发生在 −50 dB 以下的深水区。两层伪影修完后重新裁决,基于伪影数据定下的窄带 3× corner 策略随之撤销(见洞察 5)。任何"随测量配置漂移"的结论都要先怀疑测量本身。
7. **AGC 把 VGA 输出钉死,所以基带的输出天花板是唯一躲不掉的损伤**:显式建模模拟基带(输入参考噪声电压密度 + 输出摆幅,而不是 NF/IIP3)后,输入参考 IIP3 随 VGA 增益 1 dB/dB 塌陷,而由于 AGC 把 VGA **输出**电平伺服在固定点,输出参考压缩的 EVM 代价**与天线功率无关**——实测 −40 dBm 与 −20 dBm 处都是 +2.55 dB。它只能靠加大 ADC backoff 缓解,于是 `adc_backoff_db` 从自由参数变成有价参数:1.0 Vpp 摆幅下最优 backoff 从 ~10 dB 推到 ≥18 dB,当前的 12 dB 要多付约 2.6 dB EVM(`link/baseband_study.py`)。顺带纠正一条直觉:基带噪声在 VGA **之前**,不可能带来"NF 随 VGA 变"——那个效应来自 ADC,模型里本来就有。
8. **"关掉一个源再相减"对确定性损伤是错的口径**:分解 EVM 贡献时,把全量读数减去"关掉某源"的读数,得到的不是该源的功率,而是 `|e_源|² + 2Re⟨e_源, e_其余⟩`。交叉项对随机源(热噪声、量化)因独立而消失,对**确定性源**(IM3、基带天花板、ISI 同源于信号)一点都不小:实测基带天花板在 1.0 Vpp 处交叉项占 **48%**(0.5 Vpp 时 19%,2.0 Vpp 时 76%),把它对 OIP3 的斜率从解析值 **−2.00 压到 −1.49 dB/dB**——于是照着这条曲线定规格会**系统性低估**加摆幅/加 backoff 的收益。判据很硬:孤立立方原语(不接链路)给出精确的 −2.00/+2.01 dB/dB,两项拟合 `a/P₃²+b/P₃` 的残差 0.14 dB(单项模型 3.3 dB),拟合出的纯失真项与孤立实测差 0.1 dB。改成**隔离法**(只开该损伤直接读数)即可消除;代价是能隔离的只有无校正的源——IQ/DC/LPF 的校正是减法型的,只关注入不关校正会注入等量反向误差,剩下的记为"隔离底板"。隔离曲线不满足功率相加,别拿它当预算表逐项加。(与洞察 6 同类:先怀疑测量,再怀疑电路。)
9. **AGC 切换门限是 320 MHz 锚定的,窄带下白丢约 1 dB**:门限解自噪声-IM3 平衡点 `t_i = (2·IIP3_i + NF_{i+1} + (−174 + 10log10 BW))/3`,而平衡点随噪声底板走——也就是**带宽变化的 1/3**。出厂表在 320 MHz 上解一次、一套寄存器值用在所有带宽,于是 20 MHz 下每档门限偏高 **4.0 dB**,每一档都被留过了自己的平衡点:省下的是用不着的热噪声余量,付出的是实实在在的 IM3。实测 20 MHz/4096-QAM 强信号段,重解门限后平均 EVM 好 **1.16 dB**、锯齿起伏从 2.8 dB 收到 **1.45 dB**、单点最大 **3.17 dB**;而且结构干净得可以当判据——两种配置**落在同一档的点差值恰好 0.00 dB**,收益全部来自换档位置改变的那些点(平均 1.87 dB)。收益最大的点正是紧贴门限下方 IM3 达峰处,重解把换档提前,那些点就不存在了。门限做成带宽相关要多一套寄存器/固件逻辑,值不值由系统组定,模型只负责把价码测出来(`agc_rebw` 开关)。
10. **复包络模型里注入 IM3,组合系数是"约定"不是常数,错了就是 2.5 dB**:实通带三次方的双音 IM3 带教科书 3/4 系数,而复包络立方 `y = x − x·|x|²/P₃` 下同一 IM3 的组合系数是 **1**——把 3/4 搬进复包络注入器,注入项整体抬高 20·log₁₀(8/3 ÷ 2) ≈ **2.5 dB**。同坑第二层:立方必须在 2× 过采样下施加再带限回原速率,否则带外三阶产物混叠进带内,又是 ~2.5 dB 的高估。这两个错都不是代码审查抓到的,而是被交付件自带的 **RX 视角 replay 闭环**(±2 dB 判决带)当成 +1.3 dB 的系统性偏置暴露出来的——期间还先误诊为"缺调制失真项"并被隔离逐源对拍否决(过程存档在 `docs/backlog_zh.md` B13)。闭环验证不只防对方的包,也防自己的注入器;残差表里每个 `apply` 配方现在都写明幅度约定属于配方本身。
