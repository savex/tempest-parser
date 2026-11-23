# Example reports

Rendered by `tparser` from the made-up runs in `tests/data/trending` (4 runs: tests in every run, tests
missing from one run, tests new in runs 3 and 4). Run from the project root to regenerate them:

```bash
tparser -d -r examples/trending_report.html tests/data/trending
```

```bash
tparser -r examples/trending_report_brief.html tests/data/trending
```

```bash
tparser -e examples/errors_report_run_4.html tests/data/trending/run_4.log
```

- `trending_report.html`: all 4 runs side by side, with messages and traces (`-d`).
- `trending_report_brief.html`: the same without messages and traces.
- `errors_report_run_4.html`: unique errors and skips of run 4.

The `log` format has no run date, so the dates shown are the files' modification times.
