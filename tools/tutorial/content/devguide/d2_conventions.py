"""Devguide chapter 2: conventions and the guard-test doctrine."""
from __future__ import annotations

from model import Chapter, Section, T, Table

_GUARDS = (
    ("test_import_layering.py", "undeclared inter-package imports",
     "ALLOWED adjacency table, AST-parsed; the table itself must be "
     "acyclic"),
    ("test_no_dead_knobs.py", "declared-but-unwired config fields",
     "every dataclass field must be Load-read in src/app/examples; a dead "
     "knob does not fail, it lies (tests deliberately don't count as "
     "readers). Found NoiseSource.unit and CalResult.corrections on its "
     "first run"),
    ("test_cal_deps.py", "calibration order violations",
     "STEP_REQUIRES with physical reasons; violations raise with the "
     "reason attached; reasons must be prose, not stubs"),
    ("test_observers.py", "measurement functions mutating the DUT",
     "readers must leave the full correction state untouched (AGC is the "
     "one declared exception); a premise test proves the comparison can "
     "fail"),
    ("test_gui_inspector.py", "the GUI restating verdicts/thresholds",
     "docstring-stripped AST scan: no verdict wording, no threshold; "
     "verdicts must arrive as data from handoff.inspector"),
    ("test_inspector.py", "the standalone inspector growing dependencies",
     "stdlib-only import check + runs under python -I in a bare "
     "directory"),
    ("test_docs_build.py", "tutorial content rotting",
     "bilingual completeness, unique anchors, formulas parse, {{key}} "
     "fields declared; the full build is the slow tier"),
)


CHAPTER = Chapter(
    id="d2", title=T("D2 约定与护栏测试", "D2 Conventions and guard tests"),
    sections=(
        Section(
            id="d2-conv", title=T("D2.1 核心约定", "D2.1 Core conventions"),
            body=(
                T("<b>真值注入模式</b>:每个损伤带 enabled 开关与 injected() "
                  "真值;每个校准的验收 = 注入已知真值 → 估计 → 校正 → 与真值"
                  "对拍。没有真值对拍的估计器不发数字。<b>单位</b>:模拟域 "
                  "$\\sqrt{mW}$、数字域满量程,见教程第 2 章。<b>fs</b> 是"
                  "数据集属性,由上层注入,分析函数不得自带缺省。"
                  "<b>CalResult 契约</b>:estimated / corrections / trace / "
                  "metrics_before/after / passed / <em>saturated</em>"
                  "(触轨是与达标独立的余量事实)/ <em>spec</em>(内嵌验收"
                  "规格,随文件走)/ cost(捕获预算)。<b>确定性</b>:全部"
                  "随机源显式播种;比较性测试必须显式命名它测的配置,"
                  "不许继承默认值。",
                  "<b>The injected-truth pattern</b>: every impairment has "
                  "an enabled switch and injected() truth; every "
                  "calibration's acceptance = inject known truth → "
                  "estimate → correct → verify against truth. No estimator "
                  "publishes a number without a truth cross-check. "
                  "<b>Units</b>: analog $\\sqrt{mW}$, digital full-scale "
                  "(tutorial ch. 2). <b>fs</b> is a dataset property "
                  "injected from above — analysis functions must not "
                  "default it. <b>The CalResult contract</b>: estimated / "
                  "corrections / trace / metrics_before/after / passed / "
                  "<em>saturated</em> (a railed trim is a margin fact "
                  "independent of passing) / <em>spec</em> (the embedded "
                  "acceptance limit that travels with the file) / cost "
                  "(capture budget). <b>Determinism</b>: every RNG "
                  "explicitly seeded; a comparative test must name the "
                  "configuration it prices instead of inheriting "
                  "defaults."),
            )),
        Section(
            id="d2-guards", title=T("D2.2 护栏测试:防的是哪类腐烂", "D2.2 Guard tests: which decay class each blocks"),
            body=(
                T("这些测试不验证功能,验证<em>工程不变量</em>——每条都对应一类"
                  "在姊妹项目事后分析里真实发生过的腐烂。改代码撞上护栏时,"
                  "先读护栏文件头的理由,再决定是登记豁免还是修正设计:",
                  "These tests verify <em>engineering invariants</em>, not "
                  "features — each blocks a decay class that actually "
                  "happened in a sibling project's post-mortem. When a "
                  "change trips one, read the rationale at the top of the "
                  "guard file first, then either register the exception or "
                  "fix the design:"),
                Table(header=(T("护栏", "guard"), T("防什么", "blocks"),
                              T("机制", "mechanism")),
                      rows=_GUARDS),
            )),
    ))
