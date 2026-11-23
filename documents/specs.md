# tempest-parser: specification

Describes how the tool behaves (written for version 0.2.81 with the phase 1 fixes from
[plan.md](plan.md), kept up to date since). Known limitations are listed in section 8. The tests in `tests/` check this behaviour.

## 1. Purpose

`tparser` imports test results from one or more runs (OpenStack Tempest, pytest, Rally, k8s conformance,
subunit), matches the tests by class, name and options across runs, and writes reports to follow results over
time:

- **Trending report** (HTML): every test against every run.
- **Errors report** (HTML): unique failure and skip messages from a single run.
- **CSV**: the same matrix as the trending report.

## 2. Command line

```
tparser [options] [inputfile]
```

`inputfile` is a file, a folder or, when omitted, stdin.

| Option | Meaning |
|---|---|
| `-f, --input-format FMT` | Input format (section 3). Detected from the file extension when not set; stdin defaults to `subunit`. |
| `-r, --html-trending-filename F` | Write the trending report to `F`. |
| `-e, --html-errors-filename F` | Write the errors report to `F`. Needs a single file as input, not a folder. |
| `-c, --csv-file F` | Write the CSV report to `F`. |
| `-d, --detailed` | Add a messages/traceback column. Default from config `default_detailed`. |
| `-i, --include-required` | Preload the baseline test list (config `default_test_list`) as a `required` column. Ignored with `-e`. |
| `--omit-status S` | Leave tests with status `S` out of the reports. Can be repeated. |
| `--force-single` | Treat every file in a folder as one run, named after the folder. |
| `--config-file F` | Use config file `F` (absolute path) instead of the packaged one. |
| `-q, --quiet` | Print errors only. |

Progress goes to stdout through `logging`; errors start with `Error:`.

Exit codes: `0` on success; `1` for a missing path, an unsupported extension, a folder given with `-e`, or
an unexpected pipe; `2` for invalid arguments, including an unknown `-f` value (usage is printed).

## 3. Input formats

| `-f` value | Extension | Source | Importer |
|---|---|---|---|
| `log` | `.log` | Tempest/testr console output (lines starting with known markers; strip leading env vars and worker prefixes) | `TempestLogParser` |
| `t_xml` | `.xml` | subunit/Tempest jUnit XML (v4 schema supported); names split into class, test, UUID and options | `XMLImporter` |
| `r_xml` | — | Raw jUnit XML (k8s conformance, pytest); names used as is | `XMLImporter(use_raw_names=True)` |
| `json` | `.json` | Rally JSON export | `JSONImporter` |
| `csv` | `.csv` | Own CSV export (first column `Class`) or xunit CSV (rows starting with `tempest.`) | `CSVImporter` |
| `subunit` | `.subunit` | Subunit v2 stream | `SubunitImporter` |

- In a folder, files are read in name order. With `-f`, only files whose extension matches the format are
  read; without it, each file's format is detected from its extension. Other files are skipped with a message.
- Each file is one run. The run is named after the file, and its date is the file's modification time (GMT).
- XML failures are recognised as k8s errors (Go error types, `k8s.io`, klog timestamps) or pytest errors
  (`E ` lines), and the main message is taken out of the traceback.

## 4. Test identity and statuses

A test is identified by **class name**, **test name**, **UUID** (`[id-...]`) and **options** (tags in
brackets). With raw names (`r_xml`) the full name is used as is.

| Status | Meaning |
|---|---|
| `OK` | Passed |
| `FAIL` | Failed |
| `ERROR` | Error (`error`, `system-err` in XML) |
| `SKIP` | Skipped |
| `X_FAIL` / `X_OK` | Expected failure / unexpected success (Rally, CSV) |
| `R` | Listed in the baseline (`required`) but not run |

Each result also records the time, the slowest-test flag, a setup-failure flag, the message and the trace.

## 5. Data model

`TestsManager` holds one structure (`manager/structs.py`):

- `tests`: `{class_name: [test_item]}`; each test item has `test_name`, `uuid`, `test_options`, `tags` and
  `results: {execution_name: result}`.
- `executions`: `{execution_name: (date, unixtime, summary, ...)}`; the summary has total, failed, outcome and
  time.

The baseline run is the execution named `required`.

## 6. Reports

- **Trending** (`templates/tempest_trending_report.html`): classes and tests as rows, runs as columns ordered
  by date, with per-class totals and times. `-d` adds the traces.
- **Errors** (`templates/tempest_errors_report.html`): `FAIL` and `SKIP` results from one run, grouped by main
  message. The main message is the result message; if there is none, it is the `Details:` line of the
  trace; failing that, the trace lines that don't start with whitespace or `Trace`.
- **CSV** (`csv.writer`, quoted as needed): header `"", "class/test name"`, the required run's date or
  `Required vs Added`, then each run's date (plus its file name with `-d`). Each class has a
  `Class,<name>` row, followed by one row per test: number, name with options, `R`/`A` (or the required
  result), then per run its result (plus, with `-d`, the message, and the trace for `FAIL`).
- HTML reports are rendered with Jinja2 autoescaping; every field from the results is escaped, and line
  breaks in messages become `<br />`. Reports never change the results they are given.

## 7. Configuration

INI file, section `[ParserConfig]`, packaged as `tempest_parser/etc/tempest-parser.conf`:

| Key | Default | Meaning |
|---|---|---|
| `default_test_list` | `res/all_tests_tag_18.list` | Baseline test list for `-i`; relative paths are resolved against the package folder. |
| `default_detailed` | `false` | Default for `-d`. |

The packaged resources are `res/*.list` (baseline lists) and `templates/*.html` (Jinja2 templates).

## 8. Known limitations

1. XML `time` attributes are divided by 1000, i.e. read as milliseconds; jUnit writes seconds.
2. A subunit run is named after the file path and the date joined without a separator.
3. Importing an own CSV export reads only the first result column.
4. The `log` parser expects the old testr console layout (class line, indented test lines, blank-line
   separated sections, `Slowest`, `====` failure blocks, `Ran N tests`).

## 9. Requirements

- Python 3.11 or newer (`requires-python`); CI tests 3.11–3.15 on Linux and macOS.
- Runtime dependencies (`pyproject.toml`): `jinja2>=3.1`, `markupsafe>=2.1`, `python-subunit>=1.4`,
  `testtools>=2.5`.
- Entry point: `tparser = tempest_parser.tparser:tempest_cli_parser_main`.
