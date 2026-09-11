#!/usr/bin/env bash
# The nightly / on-demand full lane, exactly what ci.yml's `full` job runs:
# lint, the whole suite (slow 320 MHz / 4096-QAM cases included) with the
# coverage floor, and the two generated-artifact staleness checks.
#
# The example scripts are not run here: they are exercised by the tests
# that import them (tests/test_no_dead_knobs.py, test_gui_inspector.py)
# and by the tutorial build; running all nine end to end is a
# `scripts/ci_examples.sh` job of its own if it is ever wanted.
set -uo pipefail
cd "$(dirname "$0")/.."

# Every check below reports, and the lane exits non-zero if any of them
# failed.  It used to be `set -e` start to finish, which meant the first
# failure hid everything after it: a red docs-staleness check skipped the
# schematic check for three weeks, and one red test would have hidden
# both (CHANGELOG 0.7.26/0.7.28).  A check that does not run is
# indistinguishable in the log from a check that does not exist.
rc=0

ruff check src/ app/ tests/ tools/ examples/ android/ || rc=1
QT_QPA_PLATFORM=offscreen python -m pytest tests/ -q \
    --cov --cov-report=term:skip-covered --cov-report=xml --durations=10 || rc=1

# Cheapest generated-artefact check first: seconds, against the 27 s the
# tutorial rebuild below costs.
MPLBACKEND=Agg python tools/build_assets.py --check || rc=1

# The committed HTML is a deliverable, and nothing else notices when it
# falls behind the code it is generated from.  A rebuild is byte-identical
# apart from the provenance footer, which names the commit the build ran
# at and therefore can never match the commit that carries the file: the
# comparison that only normalised the timestamp inside it was red on
# every nightly run for three weeks, and took the schematic check (which
# used to sit after it) down with it.  tools/docs_staleness.py drops the
# footer instead, and neither check can mask the other any more.
if QT_QPA_PLATFORM=offscreen MPLBACKEND=Agg python tools/build_docs.py --out docs/
then
    python tools/docs_staleness.py || rc=1
else
    # say which conclusion is missing rather than let a build failure read
    # as a staleness verdict, in either direction
    echo "docs build failed: staleness NOT evaluated" >&2
    rc=1
fi

exit $rc
