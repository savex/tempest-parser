# Plan: CI workflows, tests and README status line

Bring tempest-parser in line with the scribe repository: GitHub workflows, a tagged test suite,
tag-based versioning, a README status line and project rules.

Status: **draft**, not started. Open decisions are listed at the end.

## 1. Review findings

The package is about 2.9k lines of Python 3. It has no tests, no CI and no changelog.

Bugs and risks found by reading the code (not yet confirmed by running it):

1. **CSV import crashes.** `tparser.py:77` calls `CSVImporter(tm, source, status_filters=filters)`,
   but `CSVImporter.__init__` (`manager/importers.py:424`) only accepts `(test_manager, source)`.
   This raises a `TypeError`, so `tparser x.csv` can't work.
2. **`--omit-status` is ignored** for `.log` and `.subunit` input. `TempestLogParser` and
   `SubunitImporter` are never given the filters.
3. **Fragile format checks.** `fmt is const.FMT_*` compares integers by identity. This works in
   CPython only because small integers are cached; it should use `==`.
4. **Mutable default arguments:** `filters=[]` in `tparser.py:60` and `status_filters=[]` in
   `manager/importers.py:89`.
5. **Versions don't line up.** `setup.py` says `0.2.81`, the newest tag is `v0.2.55`, there's an odd
   `v0.2.4RC` tag, and the latest commit says "2.80".
6. **Packaging leftovers.**
   - The `data_files` globs look for `etc/*`, `templates/*` and `res/*` at the repo root, which
     don't exist, so they're empty.
   - There are two READMEs: `README` feeds `long_description`, while `MANIFEST.in` lists only
     `README.md`.
   - The classifiers say Python 3.9 only, and 3.9 is end-of-life.

## 2. What scribe has, and what carries over

| scribe | For tempest-parser |
|---|---|
| `tests.yml`: lint, version check and a test matrix; manual only | **Keep**, adapted for Python: ruff, a package build check, and a pytest matrix |
| `version.yml`: runs on push to main and checks the version against tags | **Keep**, reading the version from `setup.py` |
| `bump-version.yml` and `release.yml`, driven by `scripts/version.sh` | **Keep**: build the sdist and wheel and publish a GitHub Release (PyPI optional) |
| `e2e.yml`: tests the installed packages | **Fold into tests** as one job that installs the built wheel and runs it |
| `fuzz.yml`, `sensors.yml`, `ui.yml` | **Drop**, there's nothing equivalent here |
| One tag per test (smoke / functional / integration / scenario) checked by `check-test-tags.sh` | **Keep** as pytest markers plus a small check script |
| README status line: badges, a "Status:" note and a "Project status" table | **Keep** |
| `CLAUDE.md` and `changelog.md` with an "Unreleased" section | **Keep** |

## 3. Phases

### Phase 1: tests and bug fixes

- Make a `tests/` folder with `smoke/`, `functional/` and `integration/`, plus `tests/data/` for
  small made-up input files.
- Write one small sample file per input format: `.log`, tempest XML, k8s/raw XML, Rally JSON, both
  CSV types, and `.subunit` (written by a script with python-subunit, not by hand).
- **Functional tests:**
  - test-name splitting and lookup in `TestsManager`
  - each importer, checked against expected statuses, times and messages
  - status filters, date extraction, control-character removal and slow-test extraction
  - the CSV reporter output, and the errors report grouping
  - HTML escaping in the trending report, as a regression test for the last hotfix
- **Smoke tests:** `tparser --help`, then each format turned into CSV and HTML, folder input,
  `--force-single`, and subunit piped in through stdin.
- **Integration test:** build the wheel, install it into a temporary venv, and run `tparser` there.
  This catches templates or resource files missing from the package.
- Fix bugs 1–4 from section 1, each with a test that fails before the fix.
- Configure pytest and ruff in a new `pyproject.toml`, and add `scripts/check-test-tags.py`.

### Phase 2: versioning

- Add `scripts/version.sh`, adapted from scribe's, so it reads and writes the version in `setup.py`.
- Pick one starting version and make `setup.py`, `changelog.md` and the git tag agree.

### Phase 3: workflows (`.github/workflows/`, on `master`)

- `tests.yml`: a lint job (ruff, `python -m build`, `twine check`, version check, test-tag check)
  and a test job across Python versions and ubuntu/macOS. It runs smoke tests first, then the
  rest, and uploads JUnit results. A separate job runs the integration test against the built wheel.
- `version.yml`: on push to master, checks the version against tags and writes a summary.
- `bump-version.yml`: manual. It works out the next version, updates `setup.py` and the changelog,
  commits, tags and starts the release.
- `release.yml`: on a tag push. It checks the tag, runs the tests, builds the sdist and wheel,
  generates checksums and publishes a GitHub Release. Uploading to PyPI with trusted publishing
  is optional.

### Phase 4: status line and docs

- Add the badge row (Tests, Release, Version tracking, Python versions, license, and PyPI if you
  publish there), a "Status:" note and a "Project status" table to `README.md`.
- Merge `README` into `README.md` and point `long_description` at it.
- Fix the classifiers and the `data_files` leftovers.

### Phase 5: project rules

- Add `CLAUDE.md` with rules like scribe's: add a changelog line for every change, run ruff and
  pytest before committing, give every test exactly one marker, use only made-up test data, and
  change versions only through `version.sh` or the Bump version workflow.

## 4. Open decisions

1. **When tests run:** scribe runs its tests only by hand. Recommendation: also run them on pull
   requests and pushes to `master`, since they'll take well under a minute.
2. **PyPI:** the README says `pip install tempestparser`. Should releases also upload to PyPI?
   That needs a trusted publisher set up on PyPI.
3. **Starting version:** tag the current code as `v0.2.81`, or jump to `v0.3.0` once the CI is in.
4. **Python versions:** suggested 3.10–3.13, dropping 3.9.
