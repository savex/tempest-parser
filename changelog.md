# Changelog

All notable changes to tempest-parser, newest first. Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

Versions come from `v*` git tags; `scripts/version.sh` keeps `setup.py` and this file in line with them.

Every commit that changes behaviour, configuration, interfaces, tooling or documents adds a line under
**Unreleased**. On release, **Bump version** turns that section into the new version.

Sections: **Added**, **Changed**, **Deprecated**, **Removed**, **Fixed**, **Security**.

## [Unreleased]

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

[Unreleased]: https://github.com/savex/tempest-parser/compare/v0.2.81...HEAD
[0.2.81]: https://github.com/savex/tempest-parser/releases/tag/v0.2.81
