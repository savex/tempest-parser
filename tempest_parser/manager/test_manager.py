import logging
import os

from tempest_parser.const import REQUIRED_RUN, Status
from tempest_parser.manager.models import Case, Execution, Result, Summary, file_date

log = logging.getLogger(__name__)

pkg_dir = os.path.dirname(__file__)
pkg_dir = os.path.join(pkg_dir, os.pardir)
pkg_dir = os.path.normpath(pkg_dir)


class TestsManager:
    """All runs and their results, matched by class, test name, options and UUID.

    `tests`: class name -> [Case]; `executions`: run name -> Execution.
    """

    def __init__(self):
        self.tests = {}
        self.executions = {}
        self.required_execution_name = REQUIRED_RUN
        # class name -> (tests list, its length, {(name, options): [positions]}, {name: position});
        # see _class_index
        self._index = {}

    def add_required(self, all_tests_filepath, use_raw_names=False):
        """Preload the baseline test list (relative paths are under the package) as the
        `required` run. Replaces the tests loaded so far."""
        path = os.path.join(pkg_dir, "res", all_tests_filepath)
        self.tests = self._all_tests_file_preload(path, use_raw_names=use_raw_names)
        self.add_execution(REQUIRED_RUN, file_date(path))

    # In case we'll need to list all of the tests in tempest
    # and mark which ones was executed, we have list of all tests
    # It produced by ./tempest run --list-tests >all_tests_tag_<N>.list
    def _all_tests_file_preload(self, resource_file, use_raw_names=False):
        _tests = {}

        # load all tests file
        with open(resource_file) as tests_file:
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
    def split_test_name(full_test_name, raw_names=False):
        def _dig_guid(raw_trailing):
            _all_items = raw_trailing.split(']')[0].split(",")
            __guid = ""
            __tags = []
            for _tag in _all_items:
                if _tag.startswith("id-"):
                    __guid = _tag
                else:
                    __tags.append(_tag)
            return __guid, __tags

        def _dig_options(raw_options):
            __options = raw_options.split(']')[1:]
            if len(__options) >= 2:
                if len(__options[1]) > 0:
                    return __options[1]
            return "".join(__options)

        _first_name = full_test_name.split('.', 1)[0]
        _class = ""
        _test = ""
        _guid = ""
        _tags = []
        _options = ""
        if full_test_name.startswith("setUpClass") or \
                full_test_name.startswith("tearDownClass"):
            _class = full_test_name.split("(")[1][:-1]
        elif _first_name.startswith("unittest2"):
            # parse unittest fail
            _name = full_test_name.split(".", 3)[3].rsplit(".", 1)
            _tmp = _name[1]
            _class = _name[0]
            _test = _tmp.split('[')[0]
            if ']' in _tmp:
                _guid, _tags = _dig_guid(_tmp.split('[', 1)[1])
                _options = _dig_options(_tmp)
        elif _first_name.startswith("tempest") or \
                _first_name.startswith("cvp_checks") or \
                _first_name.endswith("_tempest_plugin") or \
                _first_name.endswith("_tempest_tests"):
            _class = full_test_name.rsplit(".", 1)[0]
            _raw_test = full_test_name.rsplit(".", 1)[1]
            if not raw_names:
                _test = _raw_test.split('[')[0]
                if '[' in _raw_test:
                    _trailing = _raw_test.split('[')[1]
                    _guid, _tags = _dig_guid(_trailing)
                    _options = _dig_options(_trailing)
            else:
                _test = _raw_test

        return _class, _test, _guid, _options, _tags

    @staticmethod
    def split_test_name_from_speed(full_test_name):
        _class = full_test_name.rsplit(".", 2)[0]
        _test = full_test_name.rsplit(".", 2)[1].split('[')[0]
        _tmp = full_test_name.split(" ")[0].rsplit(".", 1)[1].split(']')
        _options = ""
        if len(_tmp) >= 2:
            if len(_tmp[1]) > 0:
                _options = _tmp[1]
        return (
            _class,
            _test,
            _options
        )

    def _class_index(self, class_name):
        """Lookup indexes for one class's tests, or None if the class is unknown.

        Kept up to date by _append_test; rebuilt when the class's list was replaced or
        changed elsewhere (add_required, code that edits `tests` directly).
        """
        tests = self.tests.get(class_name)
        if tests is None:
            return None
        cached = self._index.get(class_name)
        if cached is None or cached[0] is not tests or cached[1] != len(tests):
            by_key, by_name = {}, {}
            for position, test in enumerate(tests):
                by_key.setdefault((test.test_name, test.test_options), []).append(position)
                by_name.setdefault(test.test_name, position)
            cached = [tests, len(tests), by_key, by_name]
            self._index[class_name] = cached
        return cached

    def _append_test(self, class_name, test_item):
        tests = self.tests.setdefault(class_name, [])
        cached = self._class_index(class_name)
        position = len(tests)
        tests.append(test_item)
        cached[1] += 1
        cached[2].setdefault((test_item.test_name, test_item.test_options), []).append(position)
        cached[3].setdefault(test_item.test_name, position)

    def test_name_lookup(self, class_name, test_name, uuid, test_options):
        """Position of the first test with this name and options whose UUID matches
        (either UUID empty counts as a match), or -1."""
        cached = self._class_index(class_name)
        if cached is None:
            return -1
        tests = cached[0]
        for position in cached[2].get((test_name, test_options), ()):
            _uuid = tests[position].uuid
            if uuid == '' or _uuid == '' or _uuid == uuid:
                return position
        return -1

    def test_name_lookup_bare(self, class_name, test_name):
        cached = self._class_index(class_name)
        if cached is None:
            return -1
        return cached[3].get(test_name, -1)

    def partial_class_name_lookup(self, class_name_short, test_name,
                                  uuid=None, test_options=None):
        _list = []
        for _class_name in self.tests:
            if _class_name.endswith(class_name_short):
                _index = self.test_name_lookup(_class_name, test_name,
                                               uuid, test_options)
                if _index > -1:
                    _full_class_name = _class_name
                    _list.append(_full_class_name)
        return _list[0] if _list else None

    def add_execution(self, name, date):
        """Record a run; `date` is a UTC datetime. A run of the same name is replaced."""
        self.executions[name] = Execution(name, date)

    def get_sorted_executions(self):
        """Runs ordered by date; runs with the same date keep the order they were added in."""
        return sorted(self.executions.values(), key=lambda execution: execution.date)

    def mark_slowest_test_in_execution_by_name(self, execution_name,
                                               class_name, test_name,
                                               uuid=None,
                                               test_options=None):
        _index = self.test_name_lookup(class_name, test_name, uuid,
                                       test_options)
        if _index > -1:
            # mark slowest tests
            self.tests[class_name][_index].results[execution_name].slowest = True
        else:
            log.warning("Parsed slowest test not found in list: %s, %s, %s",
                        execution_name, class_name, test_name)

    def add_fail_data_for_test(self, execution_name, class_name, test_name,
                               test_options, trace, message,
                               class_name_short=False, uuid=None):
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

    def add_result_for_test(self, execution_name, class_name, test_name, uuid,
                            test_options, result, running_time,
                            message='', trace='', tags=None,
                            class_name_short=False, test_name_bare=False):
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

    def get_tests_for_class(self, class_name):
        return self.tests.get(class_name, [])

    def get_executions(self):
        return self.executions.keys()

    def get_test_classes(self):
        return self.tests.keys()

    def class_has_errors(self, class_name):
        """True if any test of the class failed in any run."""
        return any(result.result == Status.FAIL
                   for test in self.tests.get(class_name, ())
                   for result in test.results.values())

    def summarize(self, executions=None):
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

    def get_summary_for_execution(self, execution_name):
        return self.summarize([execution_name])[execution_name]

    def log_summaries(self, executions):
        """Log a one-line summary of each of the given runs."""
        for name, summary in self.summarize(executions).items():
            log.info("Tempest testrun %s: %s executed: %s passed, %s failed, %s skipped",
                     name, summary.total, summary.ok, summary.fail, summary.skip)
