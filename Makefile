# Developer entry points.  Each target is the same command CI runs
# (scripts/ci_fast.sh, scripts/ci_nightly.sh) so a green `make fast`
# means a green push.
.PHONY: setup lint fast nightly test docs notes golden

setup:            ## install the package with every extra CI installs
	pip install -e ".[test,gui,docs,dev]"

lint:             ## pycodestyle + pyflakes over everything CI lints
	ruff check src/ app/ tests/ tools/ examples/ android/

fast:             ## the push gate: lint + suite minus slow cases + coverage
	scripts/ci_fast.sh

nightly:          ## the full lane: slow cases, coverage floor, docs/assets staleness
	scripts/ci_nightly.sh

test:             ## the whole suite, no coverage (~3.5 min)
	QT_QPA_PLATFORM=offscreen python -m pytest tests/ -q

docs:             ## rebuild the committed tutorial / developer guide
	QT_QPA_PLATFORM=offscreen MPLBACKEND=Agg python tools/build_docs.py --out docs/

notes:            ## rebuild the three phase-noise PDF notes under docs/
	MPLBACKEND=Agg python tools/build_pn_cpe_note.py --out docs/

golden:           ## regenerate the Android golden after a shipped-code change
	cd android/tools && QT_QPA_PLATFORM=offscreen MPLBACKEND=Agg python make_golden.py
