#!/usr/bin/env bash
# Fast CI gate: full test suite minus the slow 320 MHz end-to-end cases.
set -euo pipefail
cd "$(dirname "$0")/.."
python -m pytest tests/ -q -m "not slow" --durations=5
