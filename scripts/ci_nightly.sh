#!/usr/bin/env bash
# Nightly: everything including the 320 MHz / 4096-QAM end-to-end sequence,
# the example scripts (report/figure generation) and a small yield run.
set -euo pipefail
cd "$(dirname "$0")/.."
python -m pytest tests/ -q --durations=10
python examples/run_impairment_study.py --out reports/nightly
python examples/run_full_calibration.py --out reports/nightly
python examples/run_link_budget.py --out reports/nightly
python examples/run_blocker_study.py --out reports/nightly
python examples/run_pa_drift_tracking.py --out reports/nightly
python examples/run_mimo_2x2.py --out reports/nightly
python examples/run_yield.py --runs 10 --out reports/nightly
