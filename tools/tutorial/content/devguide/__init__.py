"""The developer-guide Doc tree."""
from __future__ import annotations

from model import Doc, T

from . import d1_architecture, d2_conventions, d3_extending, d4_process

DOC = Doc(
    id="devguide",
    title=T("wifitrx 开发说明", "wifitrx developer guide"),
    subtitle=T("架构、约定、护栏测试与扩展方法。分层表与依赖图在构建时"
               "直接从被测试强制执行的源头生成,不会与代码脱节。",
               "Architecture, conventions, guard tests and how to extend. "
               "The layering table and dependency graph are generated at "
               "build time from the test-enforced sources, so they cannot "
               "drift from the code."),
    chapters=(d1_architecture.CHAPTER, d2_conventions.CHAPTER,
              d3_extending.CHAPTER, d4_process.CHAPTER),
)
