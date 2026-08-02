"""Devguide chapter 1: architecture and enforced layering."""
from __future__ import annotations

import importlib.util
from pathlib import Path

import figures
from model import Chapter, Diagram, Section, T, Table

_ROOT = Path(__file__).resolve().parents[4]


def _allowed():
    """Import the normative layering table from the test that enforces it
    (tests/ is not a package, hence the spec loading)."""
    spec = importlib.util.spec_from_file_location(
        "dev_layering", _ROOT / "tests" / "test_import_layering.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.ALLOWED


def _layering_rows(ctx):
    return [[pkg, ", ".join(sorted(deps)) if deps else "—"]
            for pkg, deps in sorted(_allowed().items())]


_ROLES = (
    ("units / dsp / provenance", "leaf utilities: dB/power, filters, "
     "run stamping"),
    ("waveform", "OFDM/QAM/preamble generation and demodulation"),
    ("metrics", "EVM / PSD / ACLR / IRR measurement"),
    ("pa, dpd", "PA models (Saleh/GMP/memory/drift) and the ILA "
     "predistorter"),
    ("impairments", "every analog imperfection, each with enabled + "
     "injected() truth"),
    ("chain", "TxChain/RxChain/loopback/MIMO: impairments composed into "
     "signal paths, plus the programmed correction state"),
    ("cal", "the calibration algorithms and their ordering rules "
     "(deps.py)"),
    ("link", "system studies: budget, MCS, spurs, temperature hold, "
     "sensitivity, beamforming"),
    ("handoff", "waveform I/O, runner, batch regression, the stdlib-only "
     "inspector"),
    ("deploy / report / circuit_import", "fixed-point export & vectors / "
     "Markdown report / CSV importers"),
)


CHAPTER = Chapter(
    id="d1", title=T("D1 架构与分层", "D1 Architecture and layering"),
    sections=(
        Section(
            id="d1-layers",
            title=T("D1.1 包分层(测试强制)", "D1.1 Package layering (test-enforced)"),
            body=(
                T("下表在构建时直接 import 自 "
                  "<code>tests/test_import_layering.py</code> 的 ALLOWED "
                  "邻接表——那份文件是规范来源:每个包允许 import 的对象在表里"
                  "声明,AST 解析全部模块逐条比对,新增依赖边必须去那里登记"
                  "理由。任何未声明的 import 都会挂测试。",
                  "This table is imported at build time from the ALLOWED "
                  "adjacency table in "
                  "<code>tests/test_import_layering.py</code> — that file "
                  "is the normative source: what each package may import "
                  "is declared there, every module is AST-parsed against "
                  "it, and a new dependency edge must be registered there "
                  "with a reason. Any undeclared import fails the test."),
                Table(header=(T("包", "package"),
                              T("允许 import", "may import")),
                      rows_from=_layering_rows,
                      caption=T("ALLOWED(构建时导入,不可能过期)",
                                "ALLOWED (imported at build time — cannot "
                                "go stale)")),
                Table(header=(T("包", "package"), T("职责", "role")),
                      rows=_ROLES),
            )),
        Section(
            id="d1-deps", title=T("D1.2 校准依赖图", "D1.2 The calibration dependency graph"),
            body=(
                T("校准顺序约束同样是数据(<code>cal/deps.py</code> 的 "
                  "STEP_REQUIRES),run_full_cal 在第一次捕获前校验计划,"
                  "结束后核对实际执行序列;TEMP_SENSITIVE 表 + requires 闭包"
                  "派生温度触发的最小重校计划。图为构建时自动生成:",
                  "The calibration ordering constraints are data too "
                  "(STEP_REQUIRES in <code>cal/deps.py</code>); "
                  "run_full_cal validates the plan before the first "
                  "capture and cross-checks the executed sequence after. "
                  "The TEMP_SENSITIVE table plus the requires-closure "
                  "derives the temperature-triggered minimal recal plan. "
                  "Generated at build time:"),
                Diagram(id="dg-deps-dev", build=figures.depgraph_svg,
                        caption=T("STEP_REQUIRES(悬停边看理由)",
                                  "STEP_REQUIRES (hover an edge for the "
                                  "reason)")),
            )),
    ))
