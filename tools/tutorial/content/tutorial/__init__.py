"""The tutorial Doc tree."""
from __future__ import annotations

from model import Doc, T

from . import ch1_overview, ch2_units

_CHAPTERS = [ch1_overview.CHAPTER, ch2_units.CHAPTER]

try:  # chapters land incrementally during authoring
    from . import ch3_impairments
    _CHAPTERS.append(ch3_impairments.CHAPTER)
except ImportError:
    pass
try:
    from . import ch4_algorithms
    _CHAPTERS.append(ch4_algorithms.CHAPTER)
except ImportError:
    pass
try:
    from . import ch5_sequence
    _CHAPTERS.append(ch5_sequence.CHAPTER)
except ImportError:
    pass
try:
    from . import ch6_results
    _CHAPTERS.append(ch6_results.CHAPTER)
except ImportError:
    pass
try:
    from . import ch7_insights, ch8_interfaces, ch9_boundaries
    _CHAPTERS += [ch7_insights.CHAPTER, ch8_interfaces.CHAPTER,
                  ch9_boundaries.CHAPTER]
except ImportError:
    pass

DOC = Doc(
    id="tutorial",
    title=T("wifitrx 教程:WiFi 7 收发器建模与校准",
            "wifitrx tutorial: WiFi 7 transceiver modeling & calibration"),
    subtitle=T("从射频链路建模原理到 14 步校准的推导、实现与实测验证;"
               "本页所有结果图与数字均由构建脚本现场运行模型生成。",
               "From RF chain modeling principles to the derivation, "
               "implementation and measured validation of all 14 "
               "calibration steps; every figure and number on this page "
               "was produced by the build script running the model."),
    chapters=tuple(_CHAPTERS),
)
