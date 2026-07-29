"""Devguide chapter 3: how to extend the model."""
from __future__ import annotations

from model import Chapter, Code, Section, T

CHAPTER = Chapter(
    id="d3", title=T("D3 如何扩展", "D3 How to extend"),
    sections=(
        Section(
            id="d3-imp", title=T("D3.1 新增一个损伤", "D3.1 Adding an impairment"),
            body=(
                T("五步,每步都有护栏盯着:"
                  "① 在 <code>impairments/</code> 建 dataclass,带 "
                  "<code>enabled</code> 开关与 <code>injected()</code> 真值;"
                  "② 接进 <code>chain/params.py</code>(TxParams/RxParams "
                  "字段 + randomize() 工艺分布 + injected() 汇总)并在 "
                  "<code>chain/tx.py</code> 或 <code>rx.py</code> 的信号路径"
                  "上消费它——<em>死旋钮测试会强制每个字段真的被读取</em>;"
                  "③ 温度相关就加 tempco 字段并在 set_temperature() 里盖章;"
                  "④ 在 <code>tests/test_impairments.py</code> 加旁路恒等"
                  "(enabled=False 输出逐位不变)与真值效应测试;"
                  "⑤ 若引入新包依赖,去 test_import_layering.ALLOWED 登记。",
                  "Five steps, each watched by a guard: ① create the "
                  "dataclass in <code>impairments/</code> with an "
                  "<code>enabled</code> switch and <code>injected()</code> "
                  "truth; ② wire it into <code>chain/params.py</code> "
                  "(field + randomize() distribution + injected() rollup) "
                  "and consume it on the signal path in "
                  "<code>chain/tx.py</code>/<code>rx.py</code> — <em>the "
                  "dead-knob test enforces that every field is actually "
                  "read</em>; ③ if temperature-dependent, add the tempco "
                  "field and stamp it in set_temperature(); ④ add a "
                  "bypass-identity test (enabled=False leaves the signal "
                  "bit-identical) and a truth-effect test in "
                  "<code>tests/test_impairments.py</code>; ⑤ register any "
                  "new package edge in test_import_layering.ALLOWED."),
            )),
        Section(
            id="d3-cal", title=T("D3.2 新增一个校准", "D3.2 Adding a calibration"),
            body=(
                T("骨架:", "The skeleton:"),
                Code("def calibrate_thing(tx, rx, ...) -> CalResult:\n"
                     "    before = measure()          # metrics_before\n"
                     "    est = estimate()            # from captures\n"
                     "    program(est)                # onto the chain\n"
                     "    after = measure()\n"
                     "    return CalResult(\n"
                     "        name='thing', estimated={...},\n"
                     "        corrections={...},      # what was programmed"
                     "\n"
                     "        metrics_before=before, metrics_after=after,\n"
                     "        passed=after_meets_criterion,\n"
                     "        saturated=code in (0, code_max),\n"
                     "        spec={'metric': 'x_db', 'limit': -40.0,\n"
                     "              'sense': 'max'},\n"
                     "        cost={'captures': n, 'samples': n * length})"),
                T("接线清单:① <code>cal/deps.py</code> STEP_REQUIRES 登记"
                  "顺序约束(带物理理由——'为什么必须在谁之后'),"
                  "planned_steps() 加入名字;温度敏感则进 TEMP_SENSITIVE;"
                  "② <code>cal/sequence.py</code> run_full_cal 插入调用 + "
                  "PROFILES 加捕获档参数;③ <code>report/generator.py</code> "
                  "_PRINCIPLES 加中文原理段;④ 测试:≥3 种子 Monte-Carlo 收敛 "
                  "+ 真值对拍;⑤ 校正状态若含新的编程量,补进 "
                  "correction_state()/load_correction_state()(交付 JSON 必须"
                  "凭文件完整恢复芯片)。",
                  "The wiring checklist: ① register the ordering "
                  "constraint in <code>cal/deps.py</code> STEP_REQUIRES "
                  "(with the physical reason — why it must follow what), "
                  "add the name to planned_steps(); temperature-sensitive "
                  "steps also join TEMP_SENSITIVE; ② insert the call in "
                  "<code>cal/sequence.py</code> run_full_cal and add its "
                  "capture knobs to PROFILES; ③ add the Chinese principle "
                  "paragraph to _PRINCIPLES in "
                  "<code>report/generator.py</code>; ④ tests: ≥3-seed "
                  "Monte-Carlo convergence plus an injected-truth "
                  "cross-check; ⑤ if the step programs new state, extend "
                  "correction_state()/load_correction_state() — the "
                  "delivered JSON must restore the chip from the file "
                  "alone."),
            )),
        Section(
            id="d3-docs", title=T("D3.3 新增教程章节", "D3.3 Adding a tutorial section"),
            body=(
                T("本文档自托管:在 <code>tools/tutorial/content/</code> 对应"
                  "目录加 Section(双语 T、公式 F、图 Fig/Diagram),昂贵计算"
                  "进 RunContext 的 cached_property,正文数字一律经 "
                  "values()/value_keys 接线。快档测试(不跑校准)会检查双语"
                  "齐全、锚点唯一、公式可解析、{{key}} 已声明。",
                  "This document is self-hosting: add a Section (bilingual "
                  "T, formulas F, figures Fig/Diagram) under "
                  "<code>tools/tutorial/content/</code>; expensive "
                  "computation goes into a RunContext cached_property, and "
                  "every number in prose flows through "
                  "values()/value_keys. The fast test tier (no calibration "
                  "runs) checks bilingual completeness, unique anchors, "
                  "parsable formulas and declared {{key}} fields."),
            )),
    ))
