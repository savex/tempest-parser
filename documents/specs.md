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
| `--html-layout L` | Layout of the HTML reports (trending and errors): `table` (default) or `grid` (section 6). |
| `-e, --html-errors-filename F` | Write the errors report to `F`. Needs a single file as input, not a folder. |
| `-c, --csv-file F` | Write the CSV report to `F`. |
| `-j, --json-file F` | Write the JSON summary (section 6) to `F`. |
| `--fail-on S` | Exit with code `3` when a result in any run (not the `required` list) has status `S` (upper-cased). Can be repeated. Results left out with `--omit-status` don't count. The reports are written first; each matching result is logged as a warning. |
| `-d, --detailed` | Add a messages/traceback column. Default from config `default_detailed`. |
| `-i, --include-required` | Preload the baseline test list (config `default_test_list`) as a `required` column. Ignored with `-e`. |
| `--omit-status S` | Leave tests with status `S` out of the reports. Can be repeated. |
| `--force-single` | Treat every file in a folder as one run, named after the folder. |
| `--run-name NAME` | Name the run `NAME` instead of after its file. Single file or stdin only. |
| `--run-date DATE` | Date the run `DATE` (ISO 8601, e.g. `2026-11-23` or `2026-11-23T14:30+02:00`; UTC when no offset is given) instead of by the file's modification time. Single file or stdin only. |
| `--config-file F` | Use config file `F` (absolute path) instead of the packaged one. |
| `-q, --quiet` | Print errors only. |
| `-V, --version` | Print `tparser <version>` (the installed package's version) and exit. |

Progress goes to stdout through `logging`; errors start with `Error:`.

Exit codes: `0` on success; `1` for a missing path, an unsupported extension, a folder given with `-e`,
`--run-name` or `--run-date`, or an unexpected pipe; `2` for invalid arguments, including an unknown `-f`
value or a `--run-date` that is not ISO 8601 (usage is printed); `3` when `--fail-on` finds a result with
one of its statuses.

## 3. Input formats

| `-f` value | Extension | Source | Importer |
|---|---|---|---|
| `log` | `.log` | Tempest/testr console output (see below) | `TempestLogParser` |
| `t_xml` | `.xml` | subunit/Tempest jUnit XML (v4 schema supported); names split into class, test, UUID and options | `XMLImporter` |
| `r_xml` | — | Raw jUnit XML (k8s conformance, pytest); names used as is | `XMLImporter(use_raw_names=True)` |
| `json` | `.json` | Rally JSON export | `JSONImporter` |
| `csv` | `.csv` | Own CSV export (a `Class` row before the tests) or xunit CSV (rows starting with `tempest.`) | `CSVImporter` |
| `subunit` | `.subunit` | Subunit v2 stream | `SubunitImporter` |

- In a folder, files are read in name order. With `-f`, only files whose extension matches the format are
  read; without it, each file's format is detected from its extension. Other files are skipped with a message.
- Each file is one run. The run is named after the file (stdin: `<stdin>`), and its date is the file's
  modification time (UTC, shown as `dd/mm/YYYY HH:MM GMT`). The `log` format, stdin and the baseline list
  (`required` run) are dated the same way; a stream without a file is dated now. `--run-name` and
  `--run-date` replace both for a single input.
- XML `time` attributes are seconds when any test case's time in the file has a decimal point; a file with
  whole numbers only is read as milliseconds.
- The `log` parser reads the console log line by line (`parser/tempest_log_parser.py`): a dotted class name
  on its own line (`tempest.…`, plugin and other packages too), indented test lines
  `test_name[id-…,tags](options)  RESULT  time` with any upper-case status, `setUpClass (Class) RESULT`
  (the class name may wrap to the next line), a `Slowest N tests took …` block up to a blank line, failure
  blocks (`====` line, head with optional `FAIL: `/`ERROR: ` prefix, `----` line, trace up to the next
  `====` or `Ran N tests`) and the `Ran …` summary. The failure trace is stored as is; its `Details:` lines
  are the message. Other lines are ignored. Several runs in one log import as one run; a log without a
  `Ran` line is imported too.
- It also reads the stestr / subunit-trace layout that `tempest run` prints, mixed with the above if need
  be: `{N} class.test_name[tags](options) [1.5s] ... ok|FAILED|SKIPPED: reason` (`xfail` → `X_FAIL`,
  `uxsuccess` → `X_OK`, other words upper-cased), the `Captured traceback:` attachments under a failed
  test (the trace, without the 4-space indent; other attachments are dropped when there is a traceback),
  the `Failed N tests - output below:` list, the `Totals` summary (`Ran: N tests in …`) and the
  `Slowest Tests:` table of `stestr --slowest`. A skip reason becomes the message. Test ids are split
  into class (everything before the last dotted name), name, UUID (`id-…` tag) and options.
- A CI timestamp prefix on every line (`2026-01-01 10:00:00.123456 | `, with an optional `host | `, as in
  Zuul job output) is removed first.
- An own CSV export imports every run column. Each run is dated from its header cell (else the file's
  modification time) and named after the file name column of a `-d` export, else after the CSV file
  (`<csv> #N` when it holds several runs; a single run keeps the CSV's name). Repeated file names get
  ` #N`. When the third header cell is a date, the `R` rows become the `required` run. Test names
  `test_x(options)` are split back into name and options. The `-d` cell becomes the message (for `FAIL`
  it is the message and the trace together). `--run-name` names a single-run CSV; `--run-date` dates
  every run.
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

The statuses are `const.Status`; results keep the status as a plain string, so values from imported CSV
files that aren't listed still pass through. Each result also records the time (seconds, or none), the
slowest-test flag, a setup-failure flag, the message and the trace.

## 5. Data model

`TestsManager` holds the results as dataclasses (`manager/models.py`):

- `tests`: `{class_name: [Case]}`; a `Case` has `test_name`, `uuid`, `test_options`, `tags` and
  `results: {execution_name: Result}`. A `Result` has `result`, `time` (float seconds or `None`),
  `message`, `trace`, `slowest` and `setup_fail`.
- `executions`: `{execution_name: Execution}`; an `Execution` has the `name` and the `date` (UTC
  `datetime`). Runs are ordered by date; runs with the same date keep the order they were imported in.
- `summarize()` counts total, OK, FAIL, ERROR, SKIP and time for every run in one pass over the tests.

The baseline run is the execution named `required` (`const.REQUIRED_RUN`). Reports take the
`TestsManager` and only read it.

## 6. Reports

- **Trending** (`templates/tempest_trending_report.html`): classes and tests as rows, runs as columns ordered
  by date, with per-run totals. `-d` adds a notes column per run: the message, then the trace folded in a
  `<details>` element (`<pre>`, line breaks kept). The result cells of each row are built and escaped in
  the reporter (`markupsafe.escape`) and the page is written as it is rendered (`generate()`), so the
  whole report is never held in memory. A filter bar above the table (shown by an inline script; without
  scripts every test is listed) narrows the rows by words in the class and test name, and to tests that
  failed (`FAIL`/`ERROR`) in any run, failed in the last run, or changed status between the runs they ran
  in. Rows carry these as `data-flags` letters `f`, `l`, `c`, computed in the reporter; class rows hide
  when none of their tests show. The totals stay those of all tests.
- Each result cell shows the test's time under its status (`1.50s`, `2m 05s`, `1h 02m`; nothing when the
  input has no time), in bold for the run's slowest tests. Class rows show each run's total time of the
  class's tests. The filter bar's **Times** box hides and shows the times.
- **Trending, grid layout** (`--html-layout grid`, `templates/tempest_trending_grid.html`): the same
  rows, cells, filters and times as the table, built from `<div>` elements with ARIA roles (`table`,
  `rowgroup`, `row`, `columnheader`, `cell`). One column template (`--cols`, from the number of runs
  `--runs`, fixed track sizes) is shared by every row, and each row is a grid of it; each class is a
  `<section>` holding its class row and tests, with `content-visibility: auto`, so offscreen classes are
  not laid out. (Rows as a `subgrid` of one grid were tried: seconds to lay out thousands of tests, and
  `content-visibility` turns `subgrid` off.) The summary's label rows are a row `subgrid`. The column
  header row and the class rows stick to the top and the number and name columns to the left while scrolling. CSS `:has()` hides the classes whose tests are all filtered
  out and, with the **Times** box unticked, the times; the script only marks rows `hidden`. Colours follow
  the system light or dark scheme (`light-dark()`), or the theme switch next to the title: three icon
  radios (system, light, dark) that set `color-scheme` through CSS `:has()`, so they work without
  scripts; a script remembers the choice in the browser's `localStorage` (key `tparser-theme`) and
  restores it before the report is drawn. Needs a browser with `subgrid`, `:has()`, `light-dark()` and
  CSS nesting (browsers from 2024 on). Printing drops the scrolling, the sticky parts and the switch, in
  light colours.
- **Errors** (`templates/tempest_errors_report.html`): `FAIL` and `SKIP` results from one run, grouped by main
  message. The main message is the result message; if there is none, it is the `Details:` line of the
  trace; failing that, the trace lines that don't start with whitespace or `Trace`.
- **Errors, grid layout** (`--html-layout grid`, `templates/tempest_errors_grid.html`): the same groups.
  Under the run's file name and date, links jump to the fails and skips sections, whose titles stick
  to the top. Each message is a `<details>` group (closed at first) whose summary row shows the
  message and its number of tests; open, it lists each test (class, name and options, the `Details:`
  line and the other trace lines) with its time, in bold for the run's slowest tests. The groups
  open and close without scripts; a script adds a filter by words in the message and test name
  (matching groups open, groups with no match hide through CSS `:has()`) and **Expand all** /
  **Collapse all** buttons. A section without groups says `None`. Groups are laid out with
  `content-visibility: auto`. Colours, the theme switch and printing are those of the grid trending
  report; both extend `templates/grid_base.html`.
- **CSV** (`csv.writer`, quoted as needed): header `"", "class/test name"`, the required run's date or
  `Required vs Added`, then each run's date (plus its file name with `-d`). Each class has a
  `Class,<name>` row, followed by one row per test: number, name with options, `R`/`A` (or the required
  result), then per run its result (plus, with `-d`, the message, and the trace for `FAIL`).
- **JSON summary** (`reports/json_reporter.py`): `{"runs": [...]}`, runs ordered by date, each with `name`,
  `file`, `date` (ISO 8601, UTC), `total`, `ok`, `fail`, `error`, `skip`, `time` (seconds) and `statuses`
  (count of every status found). The `required` list is left out.
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

1. An XML file whose times are all whole numbers is read as milliseconds, even when they were seconds.

## 9. Requirements

- Python 3.11 or newer (`requires-python`); CI tests 3.11–3.15 on Linux, macOS and Windows.
- Input files, piped text (every format but subunit) and the config file are read as UTF-8, and reports
  are written as UTF-8, whatever the locale. Console output escapes characters the console can't show.
- Runtime dependencies (`pyproject.toml`): `jinja2>=3.1`, `markupsafe>=2.1`, `python-subunit>=1.4`,
  `testtools>=2.5`.
- Entry point: `tparser = tempest_parser.tparser:tempest_cli_parser_main`.
