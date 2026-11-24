import dataclasses
import os
import re
from collections.abc import Iterable, Iterator
from typing import IO, Any

import jinja2
from markupsafe import Markup, escape

from tempest_parser.const import REQUIRED_RUN, Column, Status
from tempest_parser.manager.models import Case, Result, format_seconds
from tempest_parser.manager.test_manager import TestsManager

# a template's variables
Data = dict[str, Any]

pkg_dir = os.path.dirname(__file__)
pkg_dir = os.path.join(pkg_dir, os.pardir)
pkg_dir = os.path.normpath(pkg_dir)


def line_breaks(text: str) -> Markup:
    # escape the text, then turn python linebreaks into html breaks
    return Markup("<br />").join(escape(text).split("\n"))


# Cells are built as plain strings from escaped values and joined per row into one Markup:
# much faster than rendering each cell through the template or Markup.format().
_BLANK = '<td class="status blank"></td>'
_FAILED = {Status.FAIL, Status.ERROR}


def _class_times(cases: list[Case], runs: list[str]) -> list[str]:
    """Each run's total time of the class's tests, formatted; "" where none of them ran."""
    totals: dict[str, float | None] = dict.fromkeys(runs)
    for case in cases:
        for run in runs:
            result = case.results.get(run)
            if result is not None:
                totals[run] = (totals[run] or 0.0) + (result.time or 0.0)
    return [format_seconds(totals[run]) for run in runs]


def _status_cell(result: Result) -> str:
    """Status, then the time on a line of its own (bold for the run's slowest tests)."""
    time = format_seconds(result.time)
    if time:
        css = "time slowest" if result.slowest else "time"
        time = f'<span class="{css}">{time}</span>'
    status = result.result
    return f'<td class="status {escape(status.lower())}">{escape(status)}{time}</td>'


def _notes_cell(result: Result) -> str:
    """Message, then the trace folded in a <details> element."""
    message = "<br />".join(escape(result.message).split("\n"))
    if not result.trace:
        return f'<td class="tracemessage">{message}</td>'
    return (f'<td class="tracemessage">{message}<details><summary>Trace</summary>'
            f'<pre>{escape(result.trace)}</pre></details></td>')


class _HTMLReport:
    """An HTML report rendered from a Jinja2 template; subclasses name it in `tmpl` and add
    their template variables in `_extend_data`."""
    tmpl: str

    def __init__(self) -> None:
        # autoescape: every value from the results is escaped when rendered
        self.jinja2_env = jinja2.Environment(
            loader=jinja2.FileSystemLoader(os.path.join(pkg_dir, 'templates')),
            autoescape=True,
            trim_blocks=True,
            lstrip_blocks=True)
        self.jinja2_env.filters['linebreaks'] = line_breaks

    @staticmethod
    def _count_totals(data: Data) -> None:
        """{run name: {"total": n, Column: n}} in one pass over the tests."""
        names = [execution.name for execution in data['executions']]
        totals: dict[str, dict[str | Column, int]] = {
            name: {'total': 0, **{column: 0 for column in Column}} for name in names}
        by_status = {Status.OK: Column.PASS, Status.FAIL: Column.FAIL,
                     Status.ERROR: Column.ERROR, Status.SKIP: Column.SKIP}
        for tests in data['tests'].values():
            for test in tests:
                added = REQUIRED_RUN not in test.results
                for name in names:
                    result = test.results.get(name)
                    counts = totals[name]
                    if result is None:
                        counts[Column.NA] += 1
                        continue
                    counts['total'] += 1
                    column = by_status.get(result.result.upper())
                    if column is not None:
                        counts[column] += 1
                    if added:
                        counts[Column.ADDED] += 1
        data['totals'] = totals

    def __call__(self, tests_manager: TestsManager, detailed: bool = False) -> str:
        """The report for a TestsManager's results as a string; the results are only read."""
        return "".join(self.generate(tests_manager, detailed))

    def generate(self, tests_manager: TestsManager, detailed: bool = False) -> Iterator[str]:
        """The report as an iterator of text pieces, so it can be written as it is rendered."""
        data = self.common_data()
        data.update({
            "executions": tests_manager.get_sorted_executions(),
            "detailed": detailed,
            "tests": tests_manager.tests,
        })
        self._extend_data(data)
        self._count_totals(data)

        tmpl = self.jinja2_env.get_template(self.tmpl)
        return tmpl.generate(data)

    def common_data(self) -> Data:
        return {
            'report': self,
            'Column': Column,
            'REQUIRED_RUN': REQUIRED_RUN,
        }

    def _extend_data(self, data: Data) -> None:
        # extra data for a report's template
        pass


# (class name, each run's class time, rows); a row is (number, test, cells, flags)
Row = tuple[int, Case, Markup, str]
ClassRows = tuple[str, list[str], Iterator[Row]]


class HTMLTrendingReport(_HTMLReport):
    tmpl = "tempest_trending_report.html"

    def _extend_data(self, data: Data) -> None:
        data['runs'] = [e for e in data['executions'] if e.name != REQUIRED_RUN]
        data['classes'] = self._classes(data['tests'], [e.name for e in data['runs']],
                                        data['detailed'])

    @staticmethod
    def _classes(tests: dict[str, list[Case]], runs: list[str],
                 detailed: bool) -> Iterator[ClassRows]:
        """(class name, rows) for each class, sorted; rows are made as the template reads
        them. Each row's result cells are escaped here into one Markup string, which keeps
        the per-cell work out of the template.

        A row is (number, test, cells, flags); flags are the letters the report's filters
        look for: "f" failed (FAIL or ERROR) in some run, "l" failed in the last run (runs are
        ordered by date), "c" the status differs between the runs the test ran in."""
        blank = _BLANK + _BLANK if detailed else _BLANK
        number = 0

        def rows(cases: Iterable[Case]) -> Iterator[Row]:
            nonlocal number
            for case in sorted(cases, key=lambda c: c.test_name):
                number += 1
                required = case.results.get(REQUIRED_RUN)
                if required is None:
                    cells = ['<td class="status added">A</td>']
                else:
                    cells = [f'<td class="status required">{escape(required.result)}</td>']
                statuses: set[str] = set()
                result: Result | None = None
                for run in runs:
                    result = case.results.get(run)
                    if result is None:
                        cells.append(blank)
                        continue
                    statuses.add(result.result)
                    cells.append(_status_cell(result))
                    if detailed:
                        cells.append(_notes_cell(result))
                flags = ("f" if statuses & _FAILED else "") + \
                    ("l" if result is not None and result.result in _FAILED else "") + \
                    ("c" if len(statuses) > 1 else "")
                yield number, case, Markup("".join(cells)), flags

        for class_name in sorted(tests):
            yield class_name, _class_times(tests[class_name], runs), rows(tests[class_name])


class HTMLErrorsReport(_HTMLReport):
    tmpl = "tempest_errors_report.html"

    def _extend_data(self, data: Data) -> None:
        # list with unique messages
        skipped_messages: dict[str, list[Data]] = {}
        failed_messages: dict[str, list[Data]] = {}

        # Reverse source list and get unique errors
        for item in data['executions']:
            ex_name = item.name
            for test_class in data['tests']:
                for test in data['tests'][test_class]:
                    if ex_name not in test.results:
                        continue
                    result = test.results[ex_name]

                    _message = result.message
                    main_message = "" if _message is None else _message

                    if main_message.startswith("Trace"):
                        _trace = main_message
                        main_message = ""
                    else:
                        _trace = result.trace.rstrip()
                    # cut out unneeded text if present
                    _tindex = _trace.find("failure:")
                    _trace = _trace[_tindex+9:] if _tindex > 0 else _trace

                    _trace_details = ""
                    _trace_additional = []
                    for line in _trace.split('\n'):
                        if line.startswith("Details:"):
                            _trace_details = line[9:]
                        elif not line.startswith("Trace") \
                                and not re.match(r'\s', line):
                            _trace_additional.append(line)
                    _trace_messages = ", ".join(_trace_additional)

                    if not _trace_details and not main_message:
                        if _trace_messages:
                            main_message = _trace_messages.split(':')[0]
                        else:
                            main_message = "Fail message can't be extracted"
                    elif not main_message:
                        main_message = _trace_messages.split(':')[0]

                    _dict = {
                        'test_class': test_class,
                        'test_name': test.test_name,
                        'uuid': test.uuid,
                        'test_options': test.test_options,
                        'trace_details': _trace_details,
                        'trace_additional': _trace_messages,
                        **dataclasses.asdict(result),
                    }

                    if _dict['result'].upper() == Status.SKIP:
                        if main_message not in skipped_messages:
                            skipped_messages[main_message] = []
                        skipped_messages[main_message].append(_dict)

                    if _dict['result'].upper() == Status.FAIL:
                        if main_message not in failed_messages:
                            failed_messages[main_message] = []
                        failed_messages[main_message].append(_dict)

        data['unique_skips'] = skipped_messages
        data['uniqie_fails'] = failed_messages


class ReportToFile:
    def __init__(self, report: _HTMLReport, target: str | IO[str]) -> None:
        self.report = report
        self.target = target

    def __call__(self, tests_manager: TestsManager, detailed: bool = False) -> None:
        """Write the report to a path or an open file as it is rendered."""
        pieces = self.report.generate(tests_manager, detailed)
        if isinstance(self.target, str):
            with open(self.target, "w", encoding="utf-8") as target:
                target.writelines(pieces)
        else:
            self.target.writelines(pieces)
