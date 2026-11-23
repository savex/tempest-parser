# tempest-parser

CLI (`tparser`) that imports test results (Tempest log, subunit, jUnit XML, Rally JSON, CSV) from many runs,
matches tests across them and writes HTML trending / errors reports and CSV. Usage in `README.md`; behaviour in
`documents/specs.md`; the CI plan in `documents/plan.md`; changes in `changelog.md`.

## Layout

- `tempest_parser/tparser.py`: CLI. `manager/importers.py`: XML, JSON, CSV and subunit importers.
  `parser/tempest_log_parser.py`: `.log` parser. `manager/test_manager.py`: the shared results structure
  (`TestsManager`). `reports/`: HTML (Jinja2 templates in `templates/`) and CSV reports.
- Package data: `etc/tempest-parser.conf`, `res/*.list` (baseline test lists), `templates/*.html`.
- `tests/smoke`, `tests/functional`, `tests/integration`; sample inputs in `tests/data`
  (`tests/data/trending`: four `.log` runs for trending reports). `examples/`: reports rendered from
  them (commands in `examples/README.md`); regenerate them when report output changes.
- `scripts/version.sh` (versions), `scripts/check-test-tags.py` (test tags); `.github/workflows/` (CI).

## Rules

- Python 3.11+ (`python_requires` in `setup.py`, ruff `target-version`); CI tests 3.11–3.15 on ubuntu and
  macOS, and builds and releases on the newest. The minimum is the oldest CPython still supported upstream:
  raise it when that version reaches end of life (or earlier if a dependency needs it), add each new
  release to CI and the classifiers, and say why in the changelog.
- Every commit that changes behaviour, configuration, interfaces, tooling or documents adds a line to
  `changelog.md` under **Unreleased**, in the right section (Added, Changed, Fixed, ...).
- Before committing: `ruff check .`, `pytest`, `python scripts/check-test-tags.py`. Workflow changes must
  pass `actionlint`.
- Every test has exactly one tag, given by its folder: `smoke` (the `tparser` command end to end, in a
  subprocess), `functional` (one module or class), `integration` (the built and installed wheel). No tests
  outside these folders.
- A bug fix comes with a test that fails before the fix. Behaviour that isn't fixed yet goes into
  `documents/specs.md` section 8 (known limitations), not into a test that expects it.
- Tests work in their own temp dir (`tmp_path`, the `data_file` fixture) and never write into `tests/data`
  or the repo.
- Test data is made up: sample test names and messages only, never real results, hostnames, credentials or
  customer data. Subunit streams are generated in `tests/conftest.py`, not committed.
- Keep `documents/specs.md` in step with the code when CLI options, input formats, statuses, reports or
  config keys change.
- Reports never change the `TestsManager` results they are given: copy first (see `_TMPLBase.__call__`).
  HTML escaping is Jinja2 autoescaping in the reporter and templates, never in stored results; mark
  trusted markup with `markupsafe.Markup`.
- The wheel holds only `tempest_parser`. New data folders need `package_data` / `MANIFEST.in` entries and a
  check in `tests/integration/test_wheel.py`.
- Versions come from `v*` git tags. Don't edit the version in `setup.py` by hand: use
  `scripts/version.sh` or the **Bump version** workflow, which also starts **Release**. Releases come from
  `master` only. PyPI upload runs only when the repository variable `PYPI_PUBLISH` is `true`.
- Scripts in `scripts/` run on the bash 3.2 that ships with macOS.
- `README.md` is also the PyPI page: use absolute links in it.
- Work on a branch and fast-forward `master`; `master` is the default branch.
