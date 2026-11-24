# Changelog

All notable changes to tempest-parser, newest first. Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

Versions come from `v*` git tags; `scripts/version.sh` keeps `setup.py` and this file in line with them.

Every commit that changes behaviour, configuration, interfaces, tooling or documents adds a line under
**Unreleased**. On release, **Bump version** turns that section into the new version.

Sections: **Added**, **Changed**, **Deprecated**, **Removed**, **Fixed**, **Security**.

## [Unreleased]

### Added
- `CLAUDE.md` with the project layout and rules (changelog, checks before committing, test tags and
  data, specs, packaging, versioning).
- `-q, --quiet`: print errors only.
- `tests/data/trending/run_{1..4}.log`: four made-up tempest console runs for trending reports (tests in
  every run, tests missing from one run, tests new in runs 3 and 4), with a parser test.
- `examples/`: trending reports of those four runs (detailed and brief) and an errors report of run 4,
  made with `tparser`.
- Dependabot (`.github/dependabot.yml`): weekly grouped updates for GitHub Actions and `uv.lock`.
- The `log` format reads the stestr / subunit-trace console layout of `tempest run`
  (`{0} tempest....test_x [1.5s] ... ok`): statuses, times, skip reasons, `Captured traceback:` sections,
  the `-f` failure list, `Totals` and the `stestr --slowest` table. CI timestamp prefixes
  (`2026-01-01 10:00:00.123456 | host | `) are removed from every line. Sample: `tests/data/stestr.log`.
- An own CSV export imports every run, not only the first column: runs are dated from the header,
  named after their files (`-d` exports) and the baseline column comes back as the `required` run.
  Options are split back from the test name, and messages keep their quotes and commas.
- Type annotations on the whole package, checked with `mypy --strict`; the wheel ships `py.typed`, so
  code that imports `tempest_parser` gets the types.
- Trending report: test times under each status (the run's slowest in bold) and each class's total
  time per run in the class rows; a **Times** box hides them.
- Trending report: a filter bar to search class and test names and to show only tests that failed in
  any run, failed in the last run, or changed status (inline script, no external files).
- `-V, --version`: prints the installed version.
- CI runs the tests on Windows too (Python 3.11–3.15), so the "OS Independent" classifier is checked.
- Checks: ruff import order, bugbear and simplify rules (`I`, `B`, `SIM`); mypy on `tempest_parser`
  (`uv run mypy`, in the lint job); coverage of the smoke and functional tests together, failing CI
  under 90% (`pytest-cov`, `fail_under` in `pyproject.toml`).
- `-j, --json-file`: a JSON summary of the runs (name, file, ISO date, counts per status, time) for CI
  pipelines.
- `--fail-on STATUS` (repeatable): exit with code 3 when any run has a test with that status, after the
  reports are written; the matching tests are logged.
- `--run-name NAME` and `--run-date DATE` (ISO 8601, UTC unless an offset is given) name and date the run
  of a single file or stdin instead of the file name and modification time.

### Changed
- Importers' `parse()` methods all return `None` (the XML importer returned `True`, the JSON and CSV
  ones the number of tests); the HTML report base classes are merged into one `_HTMLReport`.
- `setup.py`: requires Python 3.10+, classifiers for 3.10–3.13, `Apache-2.0` license expression, project
  URLs and a description that lists every input format; the empty `data_files` are gone.
- `README.md`: CI badges, a status note and a Project status table; links are absolute for PyPI.
- `-f` takes only the known formats; an unknown value now exits with code 2 and the argparse usage message
  (was 1).
- Progress and summaries go through `logging` (stdout, `Error:`/`Warning:` prefixes) instead of `print`;
  the `log` parser's debug dump of parsed objects is gone from the normal output.
- CSV report is written with `csv.writer`: fields are quoted as needed, so `"`, commas and line breaks in
  messages survive (they used to be replaced with `'`). The header always has a required/added column, so
  it lines up with the rows.
- Test lookup in `TestsManager` uses an index per class instead of a linear scan; importing many large runs
  of one class is about 10× faster. Result dicts are built directly instead of deep-copied from templates.
- Python 2 leftovers removed (`six` dependency, `__future__` imports, `utils/file.py`).
- GitHub Actions bumped by Dependabot: `actions/checkout` v7, `actions/setup-python` v7,
  `astral-sh/setup-uv` v10.4.0, `actions/upload-artifact` v7 and `actions/download-artifact` v8 (an
  artifact whose hash doesn't match now fails the release instead of a warning).
- Requires Python 3.11+ (was 3.10+): Python 3.10 reached end of life in October 2026 and gets no more
  security fixes. CI tests 3.11–3.15 and builds, bumps and releases on 3.15; classifiers list 3.11–3.15.
- ruff checks pyupgrade rules (`UP`) against Python 3.11: f-strings, `super()`, `datetime.UTC`.
- Packaging moved from `setup.py`, `MANIFEST.in` and the requirements files to `pyproject.toml` (PEP 621
  metadata, PEP 639 license, PEP 735 dependency groups `test`, `lint`, `release`, `dev`). The version is
  read from the `v*` git tag by setuptools-scm; untagged commits build as `X.Y.Z.devN+g<sha>`.
- `scripts/version.sh` compares tags with `changelog.md` only; `setup` and `set` are gone, and
  `check <tag>` now needs a `changelog.md` section for the tag. **Bump version** no longer commits a
  version into the source; **Release** compares the built package's version with the tag (PEP 440 form).
- CI installs with uv from the new `uv.lock` (`uv sync --locked`) instead of pip, and the lint job runs
  actionlint.
- Results are dataclasses (`manager/models.py`: `Result`, `Case`, `Execution`, `Summary`) instead of
  dicts; `manager/structs.py` is gone. Times are stored as float seconds and run dates as UTC
  `datetime`s; the reports format them. Reports (`HTMLTrendingReport`, `HTMLErrorsReport`,
  `ReportToFile`) now take the `TestsManager` instead of `get_tests_list()`, which is removed.
- `const.py` defines `Status`, `Column` (report summary columns) and `InputFormat` enums instead of
  numbered constants and label dicts.
- Every run is dated by its file's modification time in UTC and shown as `dd/mm/YYYY HH:MM GMT`. `log`
  runs had no `GMT` and were ordered by the file's change time; the `required` column used the baseline
  list's change time.
- Summaries are counted in one pass over the tests (`TestsManager.summarize()`, report totals); the
  `log` parser prints the summary of its own run only, not of every run imported so far. Unused helpers
  (`get_time_for_class`, `get_totals_as_string_for_class`, `is_test_has_errors`) are removed and
  `is_class_has_errors` is now `class_has_errors`.
- Trending report: result cells are built and escaped in the reporter instead of cell by cell in the
  template, and reports are written to the file as they are rendered. For 10 runs × 3000 tests rendering
  takes 0.33 s instead of 0.72 s (detailed) and 0.20 s instead of 0.48 s, the files are about 18% smaller
  and the page is no longer held in memory. Traces in detailed reports are folded in `<details>`
  elements and keep their line breaks (they ran together in one block).
- The `log` parser reads the log line by line with regular expressions instead of splitting it into
  blank-line separated sections (`parser_strings.py` and `TestsManager.split_test_name_from_speed` are
  gone). It accepts any dotted class name (plugins), any upper-case status (`ERROR`), `FAIL: `/`ERROR: `
  failure heads and logs without a `Ran N tests` line. Failure messages keep their `"` and commas (they
  were replaced with `'` and spaces), and traces no longer end with an extra blank line.
- XML `time` attributes are read as seconds when any of them in the file has a decimal point, as jUnit
  writes them; files with whole numbers only are still read as milliseconds (they were always divided
  by 1000).

### Fixed
- `k8s_slow_extract` (raw XML from k8s): a "not to have occurred" failure no longer raises `TypeError`
  (the line was added as bytes); found by the type check.
- Input files, piped text and the config file are read as UTF-8, and reports are written as UTF-8. With
  a non-UTF-8 locale (Windows before Python 3.15, an ASCII locale) a non-ASCII test name or message
  stopped the import with `UnicodeDecodeError`, or the report with `UnicodeEncodeError`. Console output
  escapes characters the console can't show instead of failing.
- A subunit run is named after its file (`<stdin>` for a pipe); the date was appended to the name
  without a separator, so the detailed reports showed only the date's tail as the file name.
- `log`: a failure trace line starting with `tempest.` (an exception name) no longer starts a new failure
  block, and `setUpClass` failure details are stored on the class's first test (they were dropped with a
  "Test not found" warning).
- The wheel no longer installs a top-level `tests` package (the 0.3.0 wheel on the GitHub release does).
- `--force-single` also works for `.xml` files read as tempest XML (it applied only to `-f r_xml`).
- **Release** checksums use `sha256sum -- *` (shellcheck SC2035), which failed the actionlint step in CI.
  The `lint` group installs `shellcheck-py`, so `uv run actionlint` checks workflow scripts locally too.
- `markupsafe`, imported by the reports, is now a declared dependency (it came only through Jinja2), and
  every dependency has a minimum version. Unused test tools (`mock`, `pytest-html`, `coverage`,
  `pytest-cov`) are no longer installed.

### Security
- HTML reports use Jinja2 autoescaping: test names, classes, run names, messages and traces can no longer
  inject markup. Escaping no longer copies the whole result set first.

## [0.3.0] - 2026-11-23

### Added
- GitHub workflows: **Tests** (lint, package and version checks, smoke and functional tests on
  ubuntu/macOS with Python 3.10–3.13, integration against the built wheel), **Version tracking**,
  **Bump version** and **Release** (GitHub release with changelog notes; optional PyPI upload behind the
  `PYPI_PUBLISH` repository variable).
- `scripts/version.sh notes <version>` prints a changelog section for release notes.
- `scripts/version.sh`: tag-based versioning helper (current, next and highest version, SemVer compare,
  writes `setup.py` and releases the changelog's Unreleased section), with tests. Tag `v0.2.81` back-filled
  on the commit that was published to PyPI as 0.2.81.
- Test suite in `tests/` with one tag per test from its folder: `smoke` (the `tparser` command end to end),
  `functional` (importers, log parser, test manager, reports, config) and `integration` (the built wheel,
  installed and run). Made-up sample inputs for every format in `tests/data/`.
- `pyproject.toml` with pytest and ruff settings; `scripts/check-test-tags.py`.
- `documents/` with the CI plan (`plan.md`) and the specification (`specs.md`).

### Changed
- A folder given without `-f` detects each file's format from its extension and skips unsupported files.
- An unsupported `-f` value stops the run with exit code 1.
- `README.md` is the only README and the package's long description.

### Fixed
- CSV input crashed (`status_filters` argument) and dropped the first test row.
- Rally JSON and `.log` input crashed on Python 3.
- `--omit-status` had no effect for `.log` and subunit input.
- Subunit `error` and `uxsuccess` statuses crashed the import; test times are now stored as `"<seconds>s"`.
- `-i` together with `-r` crashed (baseline results had no message; run times of mixed types).
- Tests first seen in a run lost their UUID and options, so the same test from two runs became two rows.
- Test tags were never stored.
- HTML reports escaped messages in the shared results: a second report double-escaped them and the CSV
  report got HTML entities.
- Double quotes in failure and skip messages broke the CSV report.
- `import cgi` in the reporter, which fails on Python 3.13.

## [0.2.81] - 2021-04-27

### Fixed
- Escaping in the trending report.

[Unreleased]: https://github.com/savex/tempest-parser/compare/v0.3.0...HEAD
[0.3.0]: https://github.com/savex/tempest-parser/releases/tag/v0.3.0
[0.2.81]: https://github.com/savex/tempest-parser/releases/tag/v0.2.81
