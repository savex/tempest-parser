import logging
import os
import re
from collections.abc import Iterable, KeysView
from dataclasses import dataclass, field
from datetime import datetime

from tempest_parser.const import REQUIRED_RUN, Status
from tempest_parser.manager.models import Case, Execution, Result, Summary, file_date

log = logging.getLogger(__name__)

pkg_dir = os.path.dirname(__file__)
pkg_dir = os.path.join(pkg_dir, os.pardir)
pkg_dir = os.path.normpath(pkg_dir)


@dataclass(slots=True)
class _ClassIndex:
    """Lookup tables for one class's tests (see TestsManager._class_index)."""
    tests: list[Case]
    length: int = 0
    # (test name, options) -> positions in `tests`
    by_key: dict[tuple[str, str], list[int]] = field(default_factory=dict)
    # test name -> first position
    by_name: dict[str, int] = field(default_factory=dict)


# (class, test name, uuid, options, tags)
SplitName = tuple[str, str, str, str, list[str]]

# a test id: "setUpClass (class)", or an optional unittest2 prefix of three parts, then
# class.test_name[tags](options) where the class is in a tempest, cvp_checks or tempest plugin
# package; the test name is the last dotted part before the first "[".
_TEST_ID_RE = re.compile(
    r"^(?:(?:setUpClass|tearDownClass)\s*\((?P<setup>[^)]*)\)"
    r"|(?:unittest2(?:\.[^.]+){2}\.)?"
    r"(?P<cls>(?:(?:tempest|cvp_checks)[^.\[]*|[^.\[]*_tempest_(?:plugin|tests))(?:\.[^.\[]+)*)"
    r"\.(?P<test>(?P<name>[^.\[]+)(?:\[(?P<tags>[^\]]*)\](?P<options>.*))?))$")


class TestsManager:
    """All runs and their results, matched by class, test name, options and UUID.

    `tests`: class name -> [Case]; `executions`: run name -> Execution.
    """

    def __init__(self) -> None:
        self.tests: dict[str, list[Case]] = {}
        self.executions: dict[str, Execution] = {}
        self.required_execution_name = REQUIRED_RUN
        # class name -> lookup tables; see _class_index
        self._index: dict[str, _ClassIndex] = {}

    def add_required(self, all_tests_filepath: str, use_raw_names: bool = False) -> None:
        """Preload the baseline test list (relative paths are under the package) as the
        `required` run. Replaces the tests loaded so far."""
        path = os.path.join(pkg_dir, "res", all_tests_filepath)
        self.tests = self._all_tests_file_preload(path, use_raw_names=use_raw_names)
        self.add_execution(REQUIRED_RUN, file_date(path))

    # In case we'll need to list all of the tests in tempest
    # and mark which ones was executed, we have list of all tests
    # It produced by ./tempest run --list-tests >all_tests_tag_<N>.list
    def _all_tests_file_preload(self, resource_file: str,
                                use_raw_names: bool = False) -> dict[str, list[Case]]:
        _tests: dict[str, list[Case]] = {}

        # load all tests file
        with open(resource_file, encoding="utf-8") as tests_file:
            for line in tests_file:
                _class_name, _test_name, _uuid, _test_options, _tags = \
                    self.split_test_name(
                        line.replace("\n", ""),
                        raw_names=use_raw_names
                    )

                _test_item = Case(_test_name, _uuid, _test_options, _tags)
                _test_item.results[REQUIRED_RUN] = Result(Status.REQUIRED, 0.0)
                _tests.setdefault(_class_name, []).append(_test_item)
        return _tests

    @staticmethod
    def split_test_name(full_test_name: str, raw_names: bool = False) -> SplitName:
        """(class, test name, uuid, options, tags) of a test id:
        "package.module.Class.test_name[id-x,tag](options)", "setUpClass (class)" or a unittest2
        failure id ("unittest2.a.b." then a test id). Only tempest, cvp_checks and tempest
        plugin packages are known; anything else gives empty parts. With `raw_names` the test
        name keeps its brackets and options, and no uuid, options or tags are split off."""
        match = _TEST_ID_RE.match(full_test_name)
        if match is None:
            return "", "", "", "", []
        if match.group("setup") is not None:
            return match.group("setup"), "", "", "", []
        if raw_names:
            return match.group("cls"), match.group("test"), "", "", []
        uuid = ""
        tags = []
        for tag in (match.group("tags") or "").split(","):
            if tag.startswith("id-"):
                uuid = tag
            elif tag:
                tags.append(tag)
        return match.group("cls"), match.group("name"), uuid, match.group("options") or "", tags

    def _class_index(self, class_name: str) -> _ClassIndex | None:
        """Lookup indexes for one class's tests, or None if the class is unknown.

        Kept up to date by _append_test; rebuilt when the class's list was replaced or
        changed elsewhere (add_required, code that edits `tests` directly).
        """
        tests = self.tests.get(class_name)
        if tests is None:
            return None
        cached = self._index.get(class_name)
        if cached is None or cached.tests is not tests or cached.length != len(tests):
            cached = _ClassIndex(tests, len(tests))
            for position, test in enumerate(tests):
                cached.by_key.setdefault((test.test_name, test.test_options), []).append(position)
                cached.by_name.setdefault(test.test_name, position)
            self._index[class_name] = cached
        return cached

    def _append_test(self, class_name: str, test_item: Case) -> None:
        tests = self.tests.setdefault(class_name, [])
        cached = self._class_index(class_name)
        assert cached is not None
        position = len(tests)
        tests.append(test_item)
        cached.length += 1
        cached.by_key.setdefault((test_item.test_name, test_item.test_options),
                                 []).append(position)
        cached.by_name.setdefault(test_item.test_name, position)

    def test_name_lookup(self, class_name: str, test_name: str, uuid: str | None,
                         test_options: str | None) -> int:
        """Position of the first test with this name and options whose UUID matches
        (either UUID empty counts as a match), or -1."""
        cached = self._class_index(class_name)
        # options None match no test: every test has them as a string
        if cached is None or test_options is None:
            return -1
        tests = cached.tests
        for position in cached.by_key.get((test_name, test_options), ()):
            _uuid = tests[position].uuid
            if uuid == '' or _uuid == '' or _uuid == uuid:
                return position
        return -1

    def test_name_lookup_bare(self, class_name: str, test_name: str) -> int:
        cached = self._class_index(class_name)
        if cached is None:
            return -1
        return cached.by_name.get(test_name, -1)

    def partial_class_name_lookup(self, class_name_short: str, test_name: str,
                                  uuid: str | None = None,
                                  test_options: str | None = None) -> str | None:
        _list = []
        for _class_name in self.tests:
            if _class_name.endswith(class_name_short):
                _index = self.test_name_lookup(_class_name, test_name,
                                               uuid, test_options)
                if _index > -1:
                    _full_class_name = _class_name
                    _list.append(_full_class_name)
        return _list[0] if _list else None

    def add_execution(self, name: str, date: datetime) -> None:
        """Record a run; `date` is a UTC datetime. A run of the same name is replaced."""
        self.executions[name] = Execution(name, date)

    def get_sorted_executions(self) -> list[Execution]:
        """Runs ordered by date; runs with the same date keep the order they were added in."""
        return sorted(self.executions.values(), key=lambda execution: execution.date)

    def mark_slowest_test_in_execution_by_name(self, execution_name: str, class_name: str,
                                               test_name: str, uuid: str | None = None,
                                               test_options: str | None = None) -> None:
        _index = self.test_name_lookup(class_name, test_name, uuid,
                                       test_options)
        if _index > -1:
            # mark slowest tests
            self.tests[class_name][_index].results[execution_name].slowest = True
        else:
            log.warning("Parsed slowest test not found in list: %s, %s, %s",
                        execution_name, class_name, test_name)

    def add_fail_data_for_test(self, execution_name: str, class_name: str, test_name: str,
                               test_options: str, trace: str, message: str,
                               class_name_short: bool = False,
                               uuid: str | None = None) -> None:
        if class_name == "setUpClass" or class_name == "tearDownClass":
            # if this is a setUpClass situation,
            # mark all tests with this result
            # only the first test of the class gets the data
            if self.tests.get(test_name):
                _result = self.tests[test_name][0].results[execution_name]
                _result.trace = trace
                _result.message = message
        else:
            # lookup test in the list
            if class_name_short:
                _full_class_name = self.partial_class_name_lookup(class_name,
                                                                  test_name)
                if _full_class_name is None:
                    _full_class_name = class_name
            else:
                _full_class_name = class_name
            _index = self.test_name_lookup(
                _full_class_name,
                test_name,
                uuid,
                test_options
            )
            if _index > -1:
                # this matches one already in the list, copy
                _result = self.tests[_full_class_name][_index].results[execution_name]
                _result.trace = trace
                _result.message = message
            else:
                log.warning("Test not found: %s, %s; for message: %s",
                            _full_class_name, test_name, message)

    def add_result_for_test(self, execution_name: str, class_name: str, test_name: str,
                            uuid: str, test_options: str, result: str,
                            running_time: float | None, message: str = '', trace: str = '',
                            tags: Iterable[str] | None = None, class_name_short: bool = False,
                            test_name_bare: bool = False) -> None:
        """Add or replace a test's result in a run; `running_time` is seconds or None.
        A second result for the same test and run keeps both messages."""
        _result = Result(result, running_time, message, trace)
        if class_name == "setUpClass" or class_name == "tearDownClass":
            # a class setup/teardown failure: only the first test of the class gets it
            if self.tests.get(test_name):
                _result.setup_fail = True
                self.tests[test_name][0].results[execution_name] = _result
        else:
            # if this is a normal class and test name -> look it up
            # lookup test in the list
            if class_name_short:
                _full_class_name = self.partial_class_name_lookup(class_name,
                                                                  test_name)
                if _full_class_name is None:
                    _full_class_name = class_name
            else:
                _full_class_name = class_name
            if test_name_bare:
                _index = self.test_name_lookup_bare(
                    _full_class_name,
                    test_name
                )
            else:
                _index = self.test_name_lookup(
                    _full_class_name,
                    test_name,
                    uuid,
                    test_options
                )
            if _index > -1:
                # this matches one already in the list, copy
                _rs = self.tests[_full_class_name][_index].results
                # the test already has a result in this run: keep both messages, old first
                if execution_name in _rs:
                    _old = _rs[execution_name]
                    _result.message = (f"{_old.result}: {_old.message}\n"
                                       f"\n{_result.result}: {_result.message}\n")
                _rs[execution_name] = _result
            else:
                # the test is not there, add it
                _test_item = Case(test_name, uuid, test_options,
                                  list(tags) if tags else [])
                _test_item.results[execution_name] = _result
                self._append_test(_full_class_name, _test_item)

    def get_tests_for_class(self, class_name: str) -> list[Case]:
        return self.tests.get(class_name, [])

    def get_executions(self) -> KeysView[str]:
        return self.executions.keys()

    def get_test_classes(self) -> KeysView[str]:
        return self.tests.keys()

    def class_has_errors(self, class_name: str) -> bool:
        """True if any test of the class failed in any run."""
        return any(result.result == Status.FAIL
                   for test in self.tests.get(class_name, ())
                   for result in test.results.values())

    def summarize(self, executions: Iterable[str] | None = None) -> dict[str, Summary]:
        """{run name: Summary} for the given runs (all by default), in one pass over the tests."""
        names = list(self.executions) if executions is None else list(executions)
        summaries = {name: Summary() for name in names}
        for tests in self.tests.values():
            for test in tests:
                for name, result in test.results.items():
                    summary = summaries.get(name)
                    if summary is None:
                        continue
                    summary.total += 1
                    if result.time:
                        summary.time += result.time
                    if result.result == Status.OK:
                        summary.ok += 1
                    elif result.result == Status.FAIL:
                        summary.fail += 1
                    elif result.result == Status.ERROR:
                        summary.error += 1
                    elif result.result == Status.SKIP:
                        summary.skip += 1
        return summaries

    def get_summary_for_execution(self, execution_name: str) -> Summary:
        return self.summarize([execution_name])[execution_name]

    def log_summaries(self, executions: Iterable[str]) -> None:
        """Log a one-line summary of each of the given runs."""
        for name, summary in self.summarize(executions).items():
            log.info("Tempest testrun %s: %s executed: %s passed, %s failed, %s skipped",
                     name, summary.total, summary.ok, summary.fail, summary.skip)
