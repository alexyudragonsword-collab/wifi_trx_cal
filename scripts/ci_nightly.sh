#!/usr/bin/env bash
# The nightly / on-demand full lane, exactly what ci.yml's `full` job runs:
# lint, the whole suite (slow 320 MHz / 4096-QAM cases included) with the
# coverage floor, and the two generated-artifact staleness checks.
#
# The example scripts are not run here: they are exercised by the tests
# that import them (tests/test_no_dead_knobs.py, test_gui_inspector.py)
# and by the tutorial build; running all nine end to end is a
# `scripts/ci_examples.sh` job of its own if it is ever wanted.
set -euo pipefail
cd "$(dirname "$0")/.."
ruff check src/ app/ tests/ tools/ examples/ android/
QT_QPA_PLATFORM=offscreen python -m pytest tests/ -q \
    --cov --cov-report=term:skip-covered --cov-report=xml --durations=10

# The committed HTML is a deliverable, and nothing else notices when it
# falls behind the code it is generated from.  A rebuild is byte-identical
# apart from the provenance footer, which names the commit the build ran
# at and therefore can never match the commit that carries the file: the
# comparison that only normalised the timestamp inside it was red on
# every nightly run for three weeks, and took the schematic check below
# down with it.  tools/docs_staleness.py drops the footer instead.
QT_QPA_PLATFORM=offscreen MPLBACKEND=Agg python tools/build_docs.py --out docs/
python tools/docs_staleness.py
MPLBACKEND=Agg python tools/build_assets.py --check
