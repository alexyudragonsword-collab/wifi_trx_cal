"""Devguide chapter 4: process — CI, provenance, release."""
from __future__ import annotations

from model import Chapter, Code, Section, T

CHAPTER = Chapter(
    id="d4", title=T("D4 流程:CI、溯源与交付", "D4 Process: CI, provenance and release"),
    sections=(
        Section(
            id="d4-ci", title=T("D4.1 CI 双车道", "D4.1 The two CI lanes"),
            body=(
                T("push 车道跑 <code>pytest -m \"not slow\"</code>(护栏 + "
                  "单元 + offscreen GUI,约一分钟);每日车道跑全量(含慢速 "
                  "e2e 与本文档的完整构建)。单解释器、无 OS 矩阵——护栏测试"
                  "秒级就能抓住最重要的腐烂类别,矩阵只会稀释注意力。",
                  "The push lane runs <code>pytest -m \"not slow\"</code> "
                  "(guards + unit + offscreen GUI, ~a minute); the daily "
                  "lane runs everything including the slow e2e tests and "
                  "this document's full build. One interpreter, no OS "
                  "matrix — the guard tests catch the decay classes that "
                  "matter in seconds; a matrix only dilutes attention."),
            )),
        Section(
            id="d4-prov", title=T("D4.2 溯源纪律", "D4.2 The provenance discipline"),
            body=(
                T("每个生成的交付物(cal-state JSON、报告、handoff 输出、"
                  "本 HTML)都盖 <code>provenance()</code> 章:git commit、"
                  "dirty 标志(记录而非假设干净)、时间与关键库版本。检查器"
                  "对 dirty 产物给警告。生成物中只有交付级文档入库"
                  "(docx、本教程两份 HTML),运行产物(reports/、"
                  "__pycache__)一律 gitignore。",
                  "Every generated deliverable (cal-state JSON, report, "
                  "handoff outputs, this HTML) is stamped by "
                  "<code>provenance()</code>: git commit, a dirty flag "
                  "(recorded, never assumed clean), timestamp and key "
                  "library versions. The inspector warns on dirty-tree "
                  "artifacts. Only delivery-grade documents are committed "
                  "(the docx spec and these two HTML files); run products "
                  "(reports/, __pycache__) are gitignored."),
                Code("python tools/build_docs.py            # rebuild both"
                     " pages\n"
                     "python tools/build_docs.py --only tutorial "
                     "--cache /tmp/docs.pkl   # prose iteration"),
            )),
        Section(
            id="d4-release", title=T("D4.3 交付检查单", "D4.3 The release checklist"),
            body=(
                T("① 全量 pytest 绿(含 slow);② 重建两份 HTML 与校准报告,"
                  "确认 provenance 页脚为干净树;③ cal_state.json 过 "
                  "inspector 无 error;④ 交付四件套:包本体、"
                  "docs/interface_zh.md、docs/handoff_zh.md、独立 "
                  "inspector.py;⑤ 电路组三类 CSV 模板在 circuit_data/,"
                  "数字组 bit-true 向量由 deploy/vectors.py 导出;"
                  "⑥ 打 tag,commit 号进交接邮件。",
                  "① Full pytest green (slow included); ② rebuild both "
                  "HTML pages and the calibration report, confirm the "
                  "provenance footer shows a clean tree; ③ cal_state.json "
                  "passes the inspector with no errors; ④ deliver the "
                  "four-piece set: the package, docs/interface_zh.md, "
                  "docs/handoff_zh.md and the standalone inspector.py; "
                  "⑤ circuit-team CSV templates live in circuit_data/, "
                  "digital-team bit-true vectors come from "
                  "deploy/vectors.py; ⑥ tag the release and put the "
                  "commit id in the handoff mail."),
            )),
    ))
