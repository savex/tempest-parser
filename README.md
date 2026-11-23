# tempest-parser

[![Tests](https://github.com/savex/tempest-parser/actions/workflows/tests.yml/badge.svg)](https://github.com/savex/tempest-parser/actions/workflows/tests.yml)
[![Release](https://github.com/savex/tempest-parser/actions/workflows/release.yml/badge.svg)](https://github.com/savex/tempest-parser/actions/workflows/release.yml)
[![Version tracking](https://github.com/savex/tempest-parser/actions/workflows/version.yml/badge.svg)](https://github.com/savex/tempest-parser/actions/workflows/version.yml)
[![PyPI](https://img.shields.io/pypi/v/TempestParser.svg)](https://pypi.org/project/TempestParser/)
![Python 3.10–3.13](https://img.shields.io/badge/python-3.10%E2%80%933.13-blue.svg)
![Platforms](https://img.shields.io/badge/platforms-Linux%20%7C%20macOS-blue.svg)
[![License](https://img.shields.io/badge/license-Apache%202.0-green.svg)](https://github.com/savex/tempest-parser/blob/master/LICENSE)

Imports test results from many runs, matches the tests by class, name and options, and builds HTML and CSV
reports to track their statuses over time.

> **Status: maintained.** All six input formats and the three reports work and are covered by tests in CI.
> The latest release is [0.3.0](https://github.com/savex/tempest-parser/releases/tag/v0.3.0); PyPI still has 0.2.81.
> See [Project status](#project-status).

## Foreword

When you run tempest, you probably want to review the results in a human manner.

You run it once again... and again... and a couple more times the next day... and you end up with 20+ files
in the `.testrepository` folder. You start digging into how a specific tempest test ran yesterday and how its
result changed today. `grep`, `less`... Brain goes hot.

Honestly, Subunit's CLI output is good enough for reading the word PASSED at the end... and the summary.

So, there is a need to:
- import tempest test results
- match tests by class, test name and options
- produce a report to work with test statuses and track them over time
- have error messages added to the report

## Installing

The latest published version can be installed with pip:

```bash
pip install tempestparser
```

or from a cloned git repo:

```bash
pip install .
```

## Usage

The tool was originally made for an "import, match, export" flow: produce a CSV with tests matched by class
and name against the list of tests that was originally executed.

```bash
tparser -c matched.csv tempest.log
```

A folder can be used too:

```bash
tparser -c matched.csv folder1
```

HTML trending report:

```bash
tparser -f t_xml -r trending.html tempest.xml
```

or

```bash
tparser -f t_xml -r trending.html folder1
```

Add full traceback messages to the report with `-d`:

```bash
tparser -f t_xml -r trending.html -d folder1
```

To avoid scrolling the report back and forth, you can produce a unique errors report (see below).
Note that it needs a single test run file:

```bash
tparser -e errors.html single_run.json
```

This report groups FAILs and SKIPs by their main message to produce lists of unique errors and skips.
If there is no main message, it is taken from the trace: the line starting with `Details: ` becomes the main
message, and additional lines are those that:
- don't start with whitespace (regular expression `\s`)
- don't start with `Trace`

To parse k8s conformance reports, use the raw XML format:

```bash
tparser -f r_xml -r conformance.html conformance.xml
```

Conformance and other k8s tests are often spread across several files. They can be combined into a single
report:

```bash
tparser -d -r tests.html -f r_xml --force-single conformance_folder
```

You can also leave specific statuses out of the report, say 2k+ SKIPs. `--omit-status` can be used several
times:

```bash
tparser -d -r tests.html -f r_xml --force-single --omit-status OK conformance_folder
```

Results can be piped in as a subunit stream:

```bash
stestr last --subunit | tparser -r trending.html
```

### Options

| Option | Meaning |
|---|---|
| `-f, --input-format` | `log`, `t_xml`, `r_xml`, `json`, `csv` or `subunit`. Detected from the extension when omitted; stdin defaults to `subunit`. |
| `-r, --html-trending-filename` | Write the HTML trending report. |
| `-e, --html-errors-filename` | Write the HTML unique errors report (single file input only). |
| `-c, --csv-file` | Write the CSV report. |
| `-d, --detailed` | Include messages and tracebacks. |
| `-i, --include-required` | Add the baseline test list from the config as the first column. |
| `--omit-status` | Leave tests with this status (`OK`, `FAIL`, `ERROR`, `SKIP`, ...) out. Repeatable. |
| `--force-single` | Treat all files in a folder as a single run. |
| `--config-file` | Use this config file (absolute path) instead of the packaged one. |

## Imported formats

### .log files
Bare tempest output, captured with a redirect or by copying the numbered files from the `.testrepository`
folder. The LOG parser anchors on lines that start with specific strings, so remove leading environment
variables and worker report lines.

### .xml files
jUnit XML files exported from subunit (`t_xml`, the default for `.xml`), or raw jUnit XML from k8s
conformance and pytest (`r_xml`, test names used as is).

### .json files
[Rally](https://github.com/openstack/rally) tool export:

```bash
rally verify results --json --output-file result1.json
```

### .csv files
CSV files exported by tparser itself, or xunit CSV files.

### .subunit files
Subunit v2 streams saved to a file.

## Project status

| Part | State |
|---|---|
| Input: Tempest log, subunit, jUnit XML (Tempest and raw / k8s), Rally JSON, CSV | Done |
| Reports: HTML trending, HTML unique errors, CSV | Done |
| Tests (smoke, functional, integration) and CI on Linux and macOS, Python 3.10–3.13 | Done |
| Tag-based versioning, Bump version and Release workflows | Done; 0.3.0 was released through them |
| Upload to PyPI from CI | Planned (off until PyPI trusts the Release workflow) |
| Project rules for contributors (`CLAUDE.md`) | Next |

The plan is in [documents/plan.md](https://github.com/savex/tempest-parser/blob/master/documents/plan.md), the specification in
[documents/specs.md](https://github.com/savex/tempest-parser/blob/master/documents/specs.md) and the changes in [changelog.md](https://github.com/savex/tempest-parser/blob/master/changelog.md).

## Development

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt -r test-requirements.txt -e .
.venv/bin/pytest
.venv/bin/ruff check .
.venv/bin/python scripts/check-test-tags.py
```

Tests live in `tests/smoke`, `tests/functional` and `tests/integration`; the folder is the test's tag
(`pytest -m smoke` runs one tag). Sample inputs are in `tests/data`.

Versions come from `v*` git tags. `scripts/version.sh versions` shows the latest tag, the `setup.py`
version and the newest `changelog.md` release, and whether they agree; see the script's header for the
other commands. Don't edit the version in `setup.py` by hand.

CI (`.github/workflows`):
- **Tests** runs on pull requests and pushes to `master`: ruff, package build and `twine check`,
  version and test-tag checks, then the tests on ubuntu and macOS with Python 3.10–3.13.
- **Version tracking** reports the version on every push to `master`.
- **Bump version** (manual) picks the next version, updates `setup.py` and `changelog.md`, commits
  `Release vX.Y.Z`, tags it and starts **Release**.
- **Release** builds the sdist and wheel, smoke-tests them and publishes a GitHub release with the
  changelog section as notes. PyPI upload runs only when the repository variable `PYPI_PUBLISH` is
  `true`.

## Credits

Thanks to Dmitry Bogun, Alexey Diyan and Dmitriy Zapeka.
