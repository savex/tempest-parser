# tempest-parser

Imports test results from many runs, matches the tests by class, name and options, and builds HTML and CSV
reports to track their statuses over time.

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

## Credits

Thanks to Dmitry Bogun, Alexey Diyan and Dmitriy Zapeka.
