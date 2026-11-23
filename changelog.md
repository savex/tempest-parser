# Changelog

All notable changes to tempest-parser, newest first. Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

Every commit that changes behaviour, configuration, interfaces, tooling or documents adds a line under
**Unreleased**.

Sections: **Added**, **Changed**, **Deprecated**, **Removed**, **Fixed**, **Security**.

## [Unreleased]

### Added
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
