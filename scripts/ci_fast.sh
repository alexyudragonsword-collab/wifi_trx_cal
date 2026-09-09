#!/usr/bin/env bash
# The push gate, exactly what .github/workflows/ci.yml's `fast` job runs:
# lint, then the suite minus the slow 320 MHz end-to-end cases, with
# coverage over the library and the shipped GUI/Android data layer (app/).
# The workflow calls this script so the two cannot drift — they had:
# this file lacked the ruff step CI ran, and ci_nightly.sh ran examples
# CI never did (health check, 2026-09-08).
set -euo pipefail
cd "$(dirname "$0")/.."
ruff check src/ app/ tests/ tools/ examples/ android/
QT_QPA_PLATFORM=offscreen python -m pytest tests/ -q -m "not slow" \
    --cov --cov-report=term:skip-covered --durations=5
