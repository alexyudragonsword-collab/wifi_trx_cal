"""Chapter 5: calibration ordering and the capture-time budget."""
from __future__ import annotations

import figures
from model import Chapter, Diagram, Section, T, Table


def _budget_values(ctx):
    fc = ctx.full_cal
    return {
        "ms_factory": f"{fc['capture_ms_factory']:.1f}",
        "ms_poweron": f"{fc['capture_ms_poweron']:.1f}",
        "cap_factory": str(fc["captures_factory"]),
        "cap_poweron": str(fc["captures_poweron"]),
        "evm_factory": f"{fc['evm_after']:.1f}",
        "evm_poweron": f"{fc['evm_after_poweron']:.1f}",
    }


def _order_rows(ctx):
    """The canonical sequence as a table: execution index, step, the
    prerequisites deps.py declares for it, and the acceptance spec the
    step itself reports.  Every cell is derived — nothing hand-typed.

    The derivation lives in the library (``wifitrx.cal.reference``) so
    the GUI's Reference tab shows the same rows."""
    from wifitrx.cal.reference import calibration_order

    specs = {r.name: r.spec for r in ctx.full_cal["results"]}
    return [[str(r["n"]), r["step"], r["requires"], r["spec"]]
            for r in calibration_order(specs_by_name=specs)]


def _dep_reason_rows(ctx):
    """Every ordering edge with the physical reason deps.py carries;
    the leading number is the badge on the corresponding line in the
    dependency figure (both come from the same walk in
    ``wifitrx.cal.reference``)."""
    from wifitrx.cal.reference import dependency_edges

    return [[str(r["n"]), r["edge"], r["reason"]]
            for r in dependency_edges()]


def _step_cost_rows(ctx):
    rows = []
    for r in ctx.full_cal["results"]:
        if not r.cost:
            continue
        rows.append([r.name, str(r.cost.get("captures", 0)),
                     f"{r.cost.get('samples', 0):,}"])
    return rows


CHAPTER = Chapter(
    id="ch5", title=T("5 校准顺序与耗时预算", "5 Ordering and the capture-time budget"),
    sections=(
        Section(
            id="seq-deps", title=T("5.1 顺序不是习惯,是物理", "5.1 The order is physics, not habit"),
            body=(
                T("排错顺序的校准不会失败——它会<em>收敛到错误答案</em>:"
                  "RX IQ 在 TX IQ 之前跑会把 TX 镜像吸收进 RX 校正器;IIP2 在 "
                  "LO 泄漏之前跑,测量 bin 被 PA 三阶积占据。因此顺序约束在 "
                  "<code>cal/deps.py</code> 里是<em>数据</em>(每条边带物理"
                  "理由),序列在第一次捕获之前校验计划,测试锁死违例。"
                  "本节的表与图都由构建脚本直接从该表生成,图和代码不可能"
                  "脱节。先看顺序本身:",
                  "A mis-ordered calibration does not fail — it "
                  "<em>converges on the wrong answer</em>: RX IQ before TX "
                  "IQ absorbs the TX image into the RX corrector; IIP2 "
                  "before the LO-leak cal measures a bin occupied by a PA "
                  "third-order product. So the ordering constraints are "
                  "<em>data</em> in <code>cal/deps.py</code> (every edge "
                  "carries its physical reason), the sequence validates "
                  "the plan before the first capture, and tests pin the "
                  "rules. The graph below is generated straight from that "
                  "table at build time — the figure cannot drift from the "
                  "code. First the sequence itself:"),
                Table(header=(T("#", "#"), T("步骤", "step"),
                              T("前置步骤", "prerequisites"),
                              T("验收规格", "acceptance spec")),
                      rows_from=_order_rows,
                      caption=T("factory 档完整校准顺序(生成自 "
                                "planned_steps + STEP_REQUIRES,验收列取自"
                                "各步自报的 spec)",
                                "The full factory-profile sequence "
                                "(generated from planned_steps + "
                                "STEP_REQUIRES; the acceptance column is "
                                "each step's self-reported spec)")),
                T("表中<b>前置为空的 8 步彼此不排序</b>;但其中 5 步是别人"
                  "的前置(必须先于自己的下游),只有 <code>tx_lo_leak_"
                  "envdet</code>、<code>agc_sweep</code>、"
                  "<code>final_loopback_evm</code> 三步完全不受约束——"
                  "下图把这两类分开画:分列(stage)的步骤按列先后执行,"
                  "同列内无依赖可并行;虚线框那一排随时可插。边上的编号"
                  "对应其后的理由表:",
                  "The <b>eight steps with no prerequisites are not ordered "
                  "among themselves</b>; five of them are still someone "
                  "else's prerequisite (they must precede their own "
                  "downstream steps), and only <code>tx_lo_leak_envdet</"
                  "code>, <code>agc_sweep</code> and <code>final_loopback_"
                  "evm</code> are unconstrained outright. The graph below "
                  "separates the two: the staged columns run left to right "
                  "(no dependencies inside a column, so a column may run in "
                  "parallel), while the dashed band can be scheduled "
                  "anywhere. Edge numbers index the reason table that "
                  "follows:"),
                Diagram(id="dg-deps", build=figures.depgraph_svg,
                        caption=T("校准依赖图(自动生成自 STEP_REQUIRES;"
                                  "边上的编号对应下表理由)",
                                  "Calibration dependency graph (generated "
                                  "from STEP_REQUIRES; the numbers on the "
                                  "edges index the reason table below)")),
                Table(header=(T("#", "#"), T("依赖边", "edge"),
                              T("物理理由", "reason")),
                      rows_from=_dep_reason_rows,
                      caption=T("每条边的物理理由(边号即上图线上的圆圈"
                                "编号;理由为 deps.py 原文)",
                                "The physical reason behind every edge "
                                "(the edge # is the badge on the line "
                                "above; reasons verbatim from deps.py)")),
            )),
        Section(
            id="seq-budget", title=T("5.2 捕获耗时预算:factory 与 poweron", "5.2 The capture budget: factory vs power-on"),
            values=_budget_values,
            value_keys=("ms_factory", "ms_poweron", "cap_factory",
                        "cap_poweron", "evm_factory", "evm_poweron"),
            body=(
                T("校准时间就是产测成本。每一步都上报捕获次数与样本数"
                  "(时间 = 样本数 / $f_s$,不含 DSP):",
                  "Calibration time is production-test cost. Every step "
                  "reports its capture count and sample count (time = "
                  "samples / $f_s$, DSP excluded):"),
                Table(header=(T("步骤", "step"), T("捕获次数", "captures"),
                              T("样本数", "samples")),
                      rows_from=_step_cost_rows,
                      caption=T("factory 档逐步捕获成本(本次构建运行)",
                                "Per-step capture cost, factory profile "
                                "(this build's run)")),
                T("两档策略:<b>factory</b>(全码扫描、长捕获、双轮 IQ)本次"
                  "共 {cap_factory} 次捕获、{ms_factory} ms;<b>poweron</b>"
                  "(二分码搜索、半长捕获、单轮 IQ、跳过 envdet 粗校)压缩到 "
                  "{cap_poweron} 次、{ms_poweron} ms,EVM 代价 "
                  "{evm_factory} → {evm_poweron} dB。上电预算还应计入 PLL "
                  "锁定时间(报告生成器的预算表内建此行,二阶环路包络估计)。",
                  "Two profiles: <b>factory</b> (full code sweeps, long "
                  "captures, two IQ iterations) took {cap_factory} "
                  "captures / {ms_factory} ms this run; <b>poweron</b> "
                  "(bisection code search, half-length captures, single IQ "
                  "iteration, envdet stage skipped) compresses that to "
                  "{cap_poweron} captures / {ms_poweron} ms at an EVM cost "
                  "of {evm_factory} → {evm_poweron} dB. A power-on budget "
                  "should also include PLL lock time (the report "
                  "generator's budget table has a built-in row for it, a "
                  "second-order loop-envelope estimate)."),
            )),
    ))
