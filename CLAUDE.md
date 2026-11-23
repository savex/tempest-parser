# tempest-parser

CLI (`tparser`) that imports test results (Tempest log, subunit, jUnit XML, Rally JSON, CSV) from many runs,
matches tests across them and writes HTML trending / errors reports and CSV. Usage in `README.md`; behaviour in
`documents/specs.md`; the CI plan in `documents/plan.md`; changes in `changelog.md`.

## Layout

- `tempest_parser/tparser.py`: CLI. `manager/importers.py`: XML, JSON, CSV and subunit importers.
  `parser/tempest_log_parser.py`: `.log` parser. `manager/test_manager.py`: the shared results
  (`TestsManager`), made of the dataclasses in `manager/models.py` (times in seconds, UTC dates).
  `const.py`: `Status`, `Column` and `InputFormat` enums. `reports/`: HTML (Jinja2 templates in
  `templates/`) and CSV reports; they take the `TestsManager`.
- Package data: `etc/tempest-parser.conf`, `res/*.list` (baseline test lists), `templates/*.html`.
- `tests/smoke`, `tests/functional`, `tests/integration`; sample inputs in `tests/data`
  (`tests/data/trending`: four `.log` runs for trending reports). `examples/`: reports rendered from
  them (commands in `examples/README.md`); regenerate them when report output changes.
- `pyproject.toml`: package metadata, dependencies, dependency groups (`test`, `lint`, `release`, `dev`)
  and tool settings; `uv.lock` pins the development environment.
- `scripts/version.sh` (versions), `scripts/check-test-tags.py` (test tags); `.github/workflows/` (CI),
  `.github/dependabot.yml`.

## Rules

- Python 3.11+ (`requires-python` in `pyproject.toml`, ruff `target-version`); CI tests 3.11–3.15 on
  ubuntu and macOS, and builds and releases on the newest. The minimum is the oldest CPython still supported upstream:
  raise it when that version reaches end of life (or earlier if a dependency needs it), add each new
  release to CI and the classifiers, and say why in the changelog.
- Every commit that changes behaviour, configuration, interfaces, tooling or documents adds a line to
  `changelog.md` under **Unreleased**, in the right section (Added, Changed, Fixed, ...).
- Dependencies live in `pyproject.toml` only. After changing them, run `uv lock` and commit `uv.lock`;
  CI installs with `uv sync --locked`.
- Before committing: `uv run ruff check .`, `uv run pytest`, `uv run python scripts/check-test-tags.py`.
  Workflow changes must pass `uv run actionlint`.
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
- Reports only read the `TestsManager` results they are given; they never change them.
  HTML escaping is Jinja2 autoescaping in the reporter and templates, never in stored results; mark
  trusted markup with `markupsafe.Markup`.
- The wheel holds only `tempest_parser`. New data file types need a `[tool.setuptools.package-data]`
  entry and a check in `tests/integration/test_wheel.py`.
- Versions come from `v*` git tags through setuptools-scm; there is no version in the source. Release with
  the **Bump version** workflow (it updates `changelog.md`, tags and starts **Release**), not by tagging
  by hand. Releases come from `master` only. PyPI upload runs only when the repository variable
  `PYPI_PUBLISH` is `true`.
- Scripts in `scripts/` run on the bash 3.2 that ships with macOS.
- `README.md` is also the PyPI page: use absolute links in it.
- Work on a branch and fast-forward `master`; `master` is the default branch.
