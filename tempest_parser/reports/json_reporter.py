"""Machine-readable summary of the runs, for CI pipelines (`--json-file`, `--fail-on`)."""
import json
from collections import Counter

from tempest_parser.const import REQUIRED_RUN


def status_counts(test_manager):
    """{run name: Counter(status: tests)} for every run except the required list."""
    counts: dict[str, Counter[str]] = {
        name: Counter() for name in test_manager.executions if name != REQUIRED_RUN}
    for tests in test_manager.tests.values():
        for test in tests:
            for name, result in test.results.items():
                if name in counts:
                    counts[name][result.result] += 1
    return counts


def failing_results(test_manager, statuses):
    """[(run name, class, test name, status)] of the results whose status is in `statuses`."""
    statuses = set(statuses)
    found = []
    for class_name, tests in sorted(test_manager.tests.items()):
        for test in tests:
            for name, result in test.results.items():
                if name != REQUIRED_RUN and result.result in statuses:
                    found.append((name, class_name, test.test_name, result.result))
    return found


class JSONReporter:
    """Per run: name, file name, date (ISO 8601, UTC), test count, counts of the main
    statuses, total time in seconds and the count of every status found.

        {"runs": [{"name": "run_1.log", "file": "run_1.log", "date": "2026-11-23T22:08:00+00:00",
                   "total": 26, "ok": 22, "fail": 2, "error": 0, "skip": 2, "time": 41.5,
                   "statuses": {"OK": 22, "FAIL": 2, "SKIP": 2}}]}
    """

    def __init__(self, test_manager):
        self.test_manager = test_manager

    def summary(self):
        tm = self.test_manager
        counts = status_counts(tm)
        summaries = tm.summarize(list(counts))
        runs = []
        for execution in tm.get_sorted_executions():
            if execution.name == REQUIRED_RUN:
                continue
            summary = summaries[execution.name]
            runs.append({
                "name": execution.name,
                "file": execution.filename,
                "date": execution.date.isoformat(timespec="seconds"),
                "total": summary.total,
                "ok": summary.ok,
                "fail": summary.fail,
                "error": summary.error,
                "skip": summary.skip,
                "time": round(summary.time, 3),
                "statuses": dict(sorted(counts[execution.name].items())),
            })
        return {"runs": runs}

    def generate_to_file(self, path):
        with open(path, "w", encoding="utf-8") as target:
            json.dump(self.summary(), target, indent=2, ensure_ascii=False)
            target.write("\n")
