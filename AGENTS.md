# wifitrx 协作规则

> 本项目使用 Project Cairn 组织项目知识:`AGENTS.md` 是规则与导航入口,`cairn/` 是项目知识/状态层。
> 同目录的 `CLAUDE.md` 只保留一行 `@AGENTS.md`,使 Claude Code 读取同一套规则;Codex 直接读本文件。

## 项目一句话

CMOS WiFi 7(802.11be)直接变频收发器复基带行为模型 + 14 步校准算法套件,向通信算法团队交付带自验证重放闭环的校准状态包(最大 320 MHz / 4096-QAM,TX EVM ≤ −38 dB)。

> 本文件由 `cairn init` 生成,已填入本项目自身定位与 provider 配置;其他项目复用前应各自运行 init。

## Init configuration

- Graduation provider(s): 暂无(暂缓对接——首次毕业时再对接知识库)
- Knowledge base index: 尚未配置
- Graduation target: 尚未配置

## 进入项目后的阅读顺序

1. 先读本文件(AGENTS.md)。
2. 如存在 `cairn/ROADMAP.md`,读它了解路线图、当前焦点与开放问题(ROADMAP 可选;最小初始化的项目可能没有)。
3. 读 `cairn/LOG.md` 最新几条(新条目在顶部)了解近期进展与关键决策。
4. 按任务需要读相关 `cairn/` 知识专题文档。

## 文档职责

| 文件 | 角色 | 维护 |
|---|---|---|
| `AGENTS.md`(根) | 规则与导航 | 很少变动 |
| `CLAUDE.md`(根) | 一行 `@AGENTS.md` 桩 | 写一次,不再动 |
| `cairn/ROADMAP.md` | 路线图与进展 | 原地更新,保持精炼 |
| `cairn/LOG.md` | 编年日志 | 新条目加在顶部(最新在前),每条 ≤ 20 行,只写摘要+指针 |
| `cairn/<topic>.md` | 知识专题文档(当前真相) | 原地更新;坑点写入正文小节,经 `contains` 标注;修订加 LOG 指针 |
| `cairn/Reference/` | 外部原始输入 | 按需创建;只增不改 |
| `cairn/Cited.md` | 知识库引用清单 | 只存指针,绝不复制原文 |

> 其余文件只在具体信号出现时创建(需要记录的决策、解决掉的坑、跨会话的目标),不预建空壳。工程资产(代码或流程消费的契约/配置/规格)不归本系统管:它们留在代码树,不进 `cairn/`。本项目的工程待办与决策记录的唯一权威来源仍是 `docs/backlog_zh.md`;`cairn/ROADMAP.md` 只做粗粒度镜像。

## 冲突仲裁规则

- 优先级:**知识专题文档 > LOG 历史**;规则层面的冲突由本文件裁决。
- 业务/设计结论以 `cairn/` 知识专题文档的最新记录为准,不以更旧的 LOG 条目为准。

## 知识库消费反射

- 开始"可复用内核(其产出或依赖的任何结论)够格毕业"的工作前,先查本项目自身的 `cairn/` 知识专题文档;外部知识库尚未对接(provider 暂缓对接,见上文 Init configuration),对接后再启用外部 index 检查与 `cairn/Cited.md` 引用。

## 文档协作规则

- 动手改文档前,先判断用户要的是"讨论/建议"还是"直接改";用户说"先看看/先评估"时,先给分析,不要直接重写正式文档。
- 纠正过往判断时,追加更正记录;不要悄悄覆盖。
- 未经确认的判断不要写成定论。

## 知识沉淀规则

- 每个实质性进展之后,在 `cairn/LOG.md` 顶部加一条(摘要+指针);结论沉淀进 `cairn/` 知识专题文档。
- **完成答复门槛:** 在做出任何完成性声明之前——包括但不限于工作已完成/已实现、已定稿、已更新、已同步、已验证或测试通过;问题已修复或已解决;交付物可以使用;声明工作结束;以及语义等价的表述——先执行 project-cairn 技能 `references/maintenance.md` 中的 Cairn 检查点;只更新其触发矩阵要求的记录,核实后再答复。用户明确要求只读/不改动时,禁止任何 Cairn 写入。
- 跨项目可复用的经验,待知识库对接后经毕业机制沉淀(provider 暂缓对接,见上文 Init configuration)。

---

# 项目约定(原 CLAUDE.md,2026-08-16 并入)

## 语言

- 对用户的聊天回复与 Markdown 文档(README、docs/*_zh.md)用中文;`docs/units.md` 用英文。
- 所有代码注释、docstring、提交信息,以及 matplotlib 图内 / Qt GUI 内渲染的文字必须是英文(默认字体没有 CJK 字形;ruff 因 CJK 字符串报行超长,本身就是中文写错了地方的症状)。
- `tools/tutorial/content/` 的教程/开发指南内容经 `T(zh, en)` 成对双语——两半都要填。

## 结构

- `src/wifitrx/` 分层由 `tests/test_import_layering.py` 强制(AST 解析邻接表):`link` 可 import `chain`,反向禁止;`handoff/replay.py` 不得 import `wifitrx.chain` 或 `wifitrx.cal`——重放闭环证明的是交付残差解释交付 EVM,复用模型即失去意义。
- `app/` 是 PySide6 工作台,声明式注册表在 `app/specs.py`。worker 线程分析代码绝不碰 pyplot;在裸 `matplotlib.figure.Figure` 上作图。结果画布配 `NavigationToolbar2QT`,翻页时随画布一起重建。
- 新增 GUI 分析 = `app/specs.py` 一个 `AnalysisSpec` + `FAST_PARAMS` 一条对应记录(`tests/test_gui_specs.py` 断言参数集精确匹配——不得跳过)。
- `fs` 由 `bandwidth × oversampling` 导出;绝不做成逐分析参数。

## 计量学纪律(违反即 bug,不是风格问题)

- EVM 贡献拆分用**隔离法**(只开该损伤、直接读数),绝不用全量减一——确定性源的交叉项 2·Re⟨e_src, e_rest⟩ 不小。隔离曲线不满足功率相加。IQ/DC/LPF 校正在每条曲线中保持开启;剩下的是隔离底板,距底板 3 dB 内的占比必须掩码,不得归因。
- 基带密度旋钮(`bb_noise_nv`)只扫基带级本身:RF-only 前端永远在固定 6 nV 参考下反嵌(`deembed_states` + 默认 `BasebandStage`),绝不用被扫的密度反嵌。
- cal-state 交付的每个 `step.metric` 必须有 `RESIDUAL_SPEC` 条目(unit/meaning/better/role/apply/plane)——否则 `tests/test_residual_replay.py` 的防漂移守卫使构建失败。`role="total"` 的指标永不回注;重复项在 `DUPLICATES` 里作为数据声明,不从文字描述里探测。
- 重放闭环内的任何项不得由闭环目标解出。
- 复包络非线性注入器用包络约定(双音 IM3 组合系数 1,不是实通带的 3/4),立方在 2× 过采样下施加后再带限(见 backlog B13)。
- 随测量配置漂移的结论,在证明之前都是测量伪影——先校准仪器。

## 验证

- 提交前:`QT_QPA_PLATFORM=offscreen python -m pytest tests/ -q`(快速门禁 `scripts/ci_fast.sh`)与 `ruff check src/ app/ tests/ tools/ examples/`。
- 教程/开发指南内容或其引用对象变化时重建:`QT_QPA_PLATFORM=offscreen MPLBACKEND=Agg python tools/build_docs.py --out docs/`,并提交重建的 HTML。
- 每个值得发布的变更配 `CHANGELOG.md` 条目(schema 或公开签名变化显式标注)+ `pyproject.toml` 与 `src/wifitrx/__init__.py` 版本号。
- 决策与被推翻的假设记入 `docs/backlog_zh.md`——错误的转弯也要记,不只记修正。
