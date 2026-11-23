import abc
import dataclasses
import os
import re

import jinja2
from markupsafe import Markup, escape

from tempest_parser.const import REQUIRED_RUN, Column, Status

pkg_dir = os.path.dirname(__file__)
pkg_dir = os.path.join(pkg_dir, os.pardir)
pkg_dir = os.path.normpath(pkg_dir)


def line_breaks(text):
    # escape the text, then turn python linebreaks into html breaks
    return Markup("<br />").join(escape(text).split("\n"))


class _Base(abc.ABC):
    def __init__(self):
        self.jinja2_env = self.init_jinja2_env()

    @abc.abstractmethod
    def __call__(self, payload):
        pass

    @staticmethod
    def init_jinja2_env():
        # autoescape: every value from the results is escaped when rendered
        return jinja2.Environment(
            loader=jinja2.FileSystemLoader(os.path.join(pkg_dir, 'templates')),
            autoescape=True,
            trim_blocks=True,
            lstrip_blocks=True)


class _TMPLBase(_Base):
    @property
    @abc.abstractmethod
    def tmpl(self):
        pass

    @staticmethod
    def _count_totals(data):
        """{run name: {"total": n, Column: n}} in one pass over the tests."""
        names = [execution.name for execution in data['executions']]
        totals = {name: {'total': 0, **{column: 0 for column in Column}} for name in names}
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

    def __call__(self, tests_manager, detailed=False):
        """Render the report for a TestsManager's results; the results are only read."""
        data = self.common_data()
        data.update({
            "executions": tests_manager.get_sorted_executions(),
            "detailed": detailed,
            "tests": tests_manager.tests,
        })
        self._extend_data(data)
        self._count_totals(data)

        self.jinja2_env.filters['linebreaks'] = line_breaks

        tmpl = self.jinja2_env.get_template(self.tmpl)
        return tmpl.render(data)

    def common_data(self):
        return {
            'report': self,
            'counters': {'all_count': 1},
            'Column': Column,
            'REQUIRED_RUN': REQUIRED_RUN,
        }

    def _extend_data(self, data):
        # extra data for a report's template
        pass


# Trending report
class HTMLTrendingReport(_TMPLBase):
    tmpl = "tempest_trending_report.html"


class HTMLErrorsReport(_TMPLBase):
    tmpl = "tempest_errors_report.html"

    def _extend_data(self, data):
        # list with unique messages
        skipped_messages = {}
        failed_messages = {}

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
    def __init__(self, report, target):
        self.report = report
        self.target = target

    def __call__(self, tests_manager, detailed=False):
        payload = self.report(tests_manager, detailed)

        if isinstance(self.target, str):
            self._wrapped_dump(payload)
        else:
            self._dump(payload, self.target)

    def _wrapped_dump(self, payload):
        with open(self.target, "w") as target:
            self._dump(payload, target)

    @staticmethod
    def _dump(payload, target):
        target.write(payload)
