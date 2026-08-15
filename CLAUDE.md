# Project Conventions

## Language

- Chat responses to the user and Markdown docs (README, docs/*_zh.md) are
  in Chinese; `docs/units.md` and this file are English.
- All code comments, docstrings, commit messages, and text rendered inside
  matplotlib figures or the Qt GUI must be in English (the default font
  has no CJK glyphs; ruff line-length breaks on CJK strings are a symptom
  of putting Chinese where it doesn't belong).
- The tutorial/devguide content in `tools/tutorial/content/` is bilingual
  via `T(zh, en)` pairs — always fill both halves.

## Structure

- `src/wifitrx/` layering is enforced by `tests/test_import_layering.py`
  (AST-parsed adjacency table): `link` may import `chain`, never the
  reverse; `handoff/replay.py` must not import `wifitrx.chain` or
  `wifitrx.cal` — the replay closure proves the delivered residuals
  explain the delivered EVM and is worthless if it reuses the model.
- `app/` is the PySide6 workbench over the declarative registry in
  `app/specs.py`. Worker-thread analysis code must never touch pyplot;
  draw on plain `matplotlib.figure.Figure` objects. Result canvases get a
  `NavigationToolbar2QT`, rebuilt together with the canvas on page change.
- Adding a GUI analysis = one `AnalysisSpec` in `app/specs.py` plus a
  matching entry in `FAST_PARAMS` (`tests/test_gui_specs.py` asserts the
  exact param-set match — do not skip it).
- `fs` is derived from `bandwidth × oversampling`; never make it a
  per-analysis parameter.

## Metrology doctrine (violations are bugs, not style)

- EVM contribution splits use **isolation** (only that impairment active,
  read directly), never full-minus-one subtraction — the cross term
  2·Re⟨e_src, e_rest⟩ is not small for deterministic sources. Isolated
  curves are not power-additive. IQ/DC/LPF corrections stay on in every
  curve; what remains is the isolation floor, and shares within 3 dB of
  the floor must be masked, not attributed.
- The baseband density knob (`bb_noise_nv`) sweeps the stage only: the
  RF-only front end is always de-embedded at the fixed 6 nV reference
  (`deembed_states` with the default `BasebandStage`), never at the
  swept density.
- Every `step.metric` shipped in a cal-state must have a
  `RESIDUAL_SPEC` entry (unit/meaning/better/role/apply/plane) — the
  anti-drift guard in `tests/test_residual_replay.py` fails the build
  otherwise. `role="total"` metrics are never re-injected; duplicates
  are declared in `DUPLICATES` as data, not detected from prose.
- No term inside a replay closure may be solved from the closure target.
- Complex-envelope nonlinearity injectors use the envelope convention
  (two-tone IM3 combinatorial factor 1, not the real-passband 3/4) and
  apply cubics at 2× oversampling before band-limiting (see backlog B13).
- Conclusions that drift with the measurement configuration are measured
  artifacts until proven otherwise — calibrate the instrument first.

## Verification

- Before committing: `QT_QPA_PLATFORM=offscreen python -m pytest tests/ -q`
  (fast gate: `scripts/ci_fast.sh`) and `ruff check src/ app/ tests/
  tools/ examples/`.
- When tutorial/devguide content or anything they cite changes, rebuild:
  `QT_QPA_PLATFORM=offscreen MPLBACKEND=Agg python tools/build_docs.py
  --out docs/` and commit the rebuilt HTML.
- Every release-worthy change gets a `CHANGELOG.md` entry (schema or
  public-signature changes explicitly flagged) and a version bump in
  `pyproject.toml` + `src/wifitrx/__init__.py`.
- Decisions and refuted hypotheses go to `docs/backlog_zh.md` — record
  the wrong turn too, not just the fix.
