# Project Cairn 日志

本文件按倒序记录实质性进展——最新条目在顶部、紧跟本行之下。每条尽量短——只写摘要与指针;结论沉淀进 `cairn/<topic>.md`。

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
