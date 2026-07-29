# 电路仿真数据导入规范(给电路设计师)

把 Virtuoso/Spectre 仿真结果按下列 CSV 格式导出,放进 `circuit_data/`
(目录内已有同名模板可比对格式),运行:

```bash
python examples/run_with_circuit_data.py --data-dir circuit_data --bw 320e6
```

即可在**真实电路参数**下复验全部校准算法并产出报告。通用规则:UTF-8 纯文本
CSV;`#`/`!`/`*`/`;` 开头的行视为注释;允许表头行;逗号或 Tab 分隔。

## 1. PLL 相位噪声 `pll_pn_*.csv`

| 列 | 单位 | 说明 |
|---|---|---|
| offset_hz | Hz | 载波偏移(升序或任意序均可) |
| dbchz | dBc/Hz | SSB 相噪 L(f) |

- 来源:spectre `pnoise` 分析或仪表导出;覆盖 10 kHz – 100 MHz,每十倍频程
  ≥3 点(闭环平台、环路峰值、VCO 滚降、远端底噪都要覆盖到)。
- 导入:`circuit_import.load_pll_pn_csv(path)` → `TabulatedPhase`,直接作为
  `LOModel.profile`;积分相噪自动进入 EVM 预算。

## 2. 基带 LPF AC 响应 `lpf_ac_*.csv`

| 列 | 单位 | 说明 |
|---|---|---|
| freq_hz | Hz | AC 扫描频点(建议对数扫描,1 MHz – 5×corner) |
| mag_db | dB | 幅度响应(任意基准,内部取低频段为 0 dB 参考) |
| phase_deg | ° | 可选 |

- 导出条件:**典型工艺角之外,请另导 ss/ff 角文件**——`rc_error` 正是从
  测得 corner 与标称 corner 之差提取的,这是 RC 校准算法要消的量。
- 导入:`circuit_import.fit_lpf_from_ac(path, fc_nominal_hz)` →
  (`TunableLPF`, 拟合信息:实测 corner/等效阶数/rc_error)。

## 3. PA HB 扫描 `pa_hb_*.csv`

| 列 | 单位 | 说明 |
|---|---|---|
| pin_dbm | dBm | 输入功率扫描(建议 −30 → Psat+2,步进 ≤1 dB) |
| pout_dbm | dBm | 输出功率(AM-AM) |
| phase_deg | ° | 相对相移(AM-PM);无则填 0 |

- 也接受 `r_in,r_out,phase_deg`(50Ω 峰值包络幅度)。
- 匹配网络色散(可选):另导 S21 表 `freq_hz,mag_db,phase_deg`(相对载波的
  基带频偏),经 `pa.hb_import.s21_to_fir` 变为输入/输出 FIR。
- 导入:`pa.hb_import.load_hb_pa(amam_csv[, s21_in, s21_out, fs])` →
  `WienerHammersteinPA`,再包 `ScaledPA(pa, gain_db, psat_dbm)` 进链路。
- 注意:表下限以下模型按线性小信号外推;表上限以上按饱和保持——扫描范围务必
  盖过 Psat。

## 常见问题

- **单位错**:相噪填成 dBm、功率填成 dBW 会被范围检查拒收并给出中文报错。
- **点太稀**:LPF 滚降段(>2×corner)至少 4 点,否则阶数拟合退回默认 5 阶。
- **多工艺角**:每个角一套文件,`run_with_circuit_data.py --seed` 无关(真实
  数据模式下工艺角来自你的文件,不再随机)。
