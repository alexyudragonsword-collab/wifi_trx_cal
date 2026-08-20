# Project Cairn 日志

本文件按倒序记录实质性进展——最新条目在顶部、紧跟本行之下。每条尽量短——只写摘要与指针;结论沉淀进 `cairn/<topic>.md`。

## 2026-08-16 · B14:EVM 估计器自拟合偏差修正(0.5.9)

- 11n vs 11ax 灵敏度对照暴露仪器伪影:per-tone 均衡器自拟合吞 1/N 噪声,6 符号帧偏乐观 0.79 dB,曾把 0.66 dB 占用带宽真实差抵消成 +0.13 dB。
- 修正:`metrics/evm.py` 加自由度重标 N/(N−1);合成数据验证偏差律精确成立;修正后 MCS7 灵敏度差 +0.69 dB 回归理论。
- 交付数字整体上移:320M/4096 验收 −41.1→−40.2 dB(docx/教程已同步);闭环 gap 不受影响;270 测试零改动。
- 指针:`docs/backlog_zh.md` B14、`CHANGELOG.md` 0.5.9。被推翻的结论("两制式灵敏度几乎相同")按惯例留档于 B14。

## 2026-08-16 · 历史知识清点(inventory_only)

- 既有知识源清单(只清点、不迁移,各文档继续各司其职):
  - `docs/backlog_zh.md` — 决策记录 + 工程待办唯一权威来源(头部"当前状态"块;含被推翻假设的原文留档,如 B13);
  - `CHANGELOG.md` — 版本变更 0.1→0.5.7,schema/公开签名变化显式标注;
  - `README.md` — 设计洞察 1–10(结论浓缩版);
  - `docs/tutorial.html` / `docs/devguide.html` — 构建时实跑数字的双语教程与开发指南(源码在 `tools/tutorial/content/`);
  - `docs/wifitrx_design_spec.docx` — 对外设计规格书(v0.5.6 状态);
  - `docs/interface_zh.md` / `handoff_zh.md` / `units.md` / `cal_order_zh.md` / `circuit_data_zh.md` — 接口与交付约定。
- 后续如需将某条历史结论升为 `cairn/` 知识专题文档,按 selective_migrate 逐条确认后再做。

## 2026-08-16 · Project Cairn 初始化

- 初始化 Project Cairn 结构(git_policy: track;provider 暂缓对接;文档语言中文)。
- 历史迁移模式:`inventory_only`。
- 原 `CLAUDE.md` 项目约定整体并入 `AGENTS.md`("项目约定"章);`CLAUDE.md` 改为一行 `@AGENTS.md` 桩。
- 详见 `AGENTS.md` 与 `.cairn/config.yaml`。
