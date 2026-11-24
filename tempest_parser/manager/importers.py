import csv
import json
import logging
import re
from xml.etree.ElementTree import parse

from subunit import make_stream_binary
from subunit.filters import run_tests_from_stream
from subunit.test_results import TestByTestResult
from testtools import StreamToExtendedDecorator

from tempest_parser.const import Status
from tempest_parser.manager.models import file_date, parse_seconds

log = logging.getLogger(__name__)

CSV_OWN = 1
CSV_XUNIT = 2


# C0 and C1 control characters, DEL included
_CONTROL_CHARS = ''.join(map(chr, [*range(0, 32), *range(127, 160)]))
_CONTROL_CHARS_RE = re.compile(f'[{re.escape(_CONTROL_CHARS)}]')


def remove_control_chars(s):
    return _CONTROL_CHARS_RE.sub('', s)


def k8s_slow_extract(_reason):
    _tmp = []
    _m = ""
    _t = ""
    _lines = _reason.splitlines()
    for idx in range(len(_lines)-1):
        _line = _lines[idx].strip()
        _next_line = _lines[idx+1].strip()
        if _line.startswith("<*errors.errorString") and \
                _next_line.startswith("s: \""):
            err = _next_line.split('"')[1]
            err = err.encode('ascii', 'ignore')
            if err.count(b"\\x00") > 1:
                err = err.replace(b"\\x00", b"")
            err = remove_control_chars(err.decode('utf-8'))
            _tmp.append(err)
        elif _next_line.startswith("not to have occurred"):
            _tmp.append(_line.encode('ascii', 'ignore'))
    if len(_tmp) > 0:
        _m = "\n".join(_tmp)
    else:
        _t = _reason
    return _m, _t


class ImporterBase:
    def __init__(
        self,
        test_manager,
        source,
        use_raw_names=False,
        status_filters=None,
        force_single_execution=None,
        run_name=None,
        run_date=None,
    ):
        self.source = source
        self.tm = test_manager
        self.use_raw_names = use_raw_names
        self.forced_execution_name = force_single_execution
        self.status_filters = status_filters or []
        # --run-name / --run-date: replace the name and date taken from the file
        self.run_name = run_name
        self.run_date = run_date

    def execution_name(self, default):
        return self.run_name or default

    def execution_date(self):
        return self.run_date or file_date(self.source)

    def add_execution(self, name, date):
        self.tm.add_execution(name, date)


# Example of pytest4 xml structure
"""<?xml version="1.0" encoding="UTF-8"?>
<testsuites disabled="" errors="" failures="" name="" tests="" time="">
    <testsuite disabled="" errors="" failures="" hostname="" id=""
               name="" package="" skipped="" tests="" time="" timestamp="">
        <properties>
            <property name="" value=""/>
        </properties>
        <testcase assertions="" classname="" name="" status="" time="">
            <skipped/>
            <error message="" type=""/>
            <failure message="" type=""/>
            <system-out/>
            <system-err/>
        </testcase>
        <system-out/>
        <system-err/>
    </testsuite>
</testsuites>
"""


_error_status_map = {
    'skipped': Status.SKIP,
    'failure': Status.FAIL,
    'error': Status.ERROR,
    'system-err': Status.ERROR
}


class XMLImporter(ImporterBase):
    # time attributes are seconds in jUnit XML, but some tools write whole milliseconds
    time_scale = 1.0

    @staticmethod
    def _detect_time_scale(root):
        """1.0 (seconds) when any testcase time has a decimal point, else 1000.0: a file
        of whole numbers only is read as milliseconds."""
        times = [tc.get('time', '') for tc in root.iter('testcase')]
        if any('.' in t for t in times) or not any(t.strip() for t in times):
            return 1.0
        return 1000.0

    def _parse_duration(self, duration):
        seconds = parse_seconds(duration)
        return None if seconds is None else seconds / self.time_scale

    @staticmethod
    def _parse_status(status):
        # XML has one child node for status and text as a reason
        if not len(status):
            return Status.OK, "Test passed", ""
        else:
            _status = ""
            _reason = ""
            _sysout = ""
            _idx = 0
            # cut system-out
            while len(status) > 0 and _idx < len(status):
                if status[_idx].tag == 'system-out':
                    _status = Status.OK
                    _sysout = f"{status[_idx].tag}:\n{status[_idx].text}"
                    _ = status.pop(_idx)
                else:
                    _idx += 1

            # iterate others
            while len(status) > 0:
                # last encountered node will be the status
                _s = status.pop()
                _status = _error_status_map[_s.tag]
                _reason = f"{_s.tag}:\n{_s.text}\n{_reason}"
            return _status, _reason, _sysout

    def _is_k8s_error(self, reason):
        _e1 = reason.count('errors.errorString')
        _e2 = reason.count('errors.StatusError')
        _k8s = reason.count('k8s.io')
        _m = re.findall(
            r"^.{0,3}\s+\d{1,2}\s\d{1,2}:\d{1,2}:\d{1,2}\.\d{0,3}:.*$",
            reason,
            re.MULTILINE
        )
        return bool(_e1 or _e2 or _k8s or _m)

    def _detect_pytest_errors(self, reason):
        _lines = re.findall(r"^[E]\s+.*$", reason, re.MULTILINE)
        return _lines if len(_lines) > 0 else []

    def _parse_pytest_error(self, lines):
        # Extract message
        _msg = ""
        _trace = ""
        for line in lines:
            line = line[1:].strip()
            # Save all message in the traceback
            # detect message
            m = re.search(r"^[a-z,A-Z]+\:\s.*$", line, re.MULTILINE)
            if m:
                _msg = m.group(0)
            else:
                _trace += line + '\n'
        return _msg, _trace

    def parse(self):
        tree = parse(self.source)
        root = tree.getroot()

        _execution_date = self.execution_date()
        self.time_scale = self._detect_time_scale(root)
        _all_testsuites = []
        # We should be ready for multiple test suites in one xml
        if root.tag == 'testsuite':
            _all_testsuites.append(root)
        else:
            _all_testsuites += root.findall('testsuite')

        for _testsuite in _all_testsuites:

            # _execution_name = _testsuite.attrib['id']
            _execution_name = self.execution_name(
                self.forced_execution_name or self.source.name)

            # iterate through tests
            for _test_node in _testsuite.findall('testcase'):
                _class_name = _test_node.attrib['classname']
                # remove any '%' symbols and following number
                _symbol_index = _class_name.find('%')
                if _symbol_index > 0:
                    _class_name = _class_name[:_symbol_index] + \
                                _class_name[_symbol_index + 2:]

                # get all attributes from xml
                # _uuid = _test_node.attrib['id']
                _test_name = _test_node.attrib['name']
                if self.use_raw_names:
                    _options = ''
                    _uuid = ''
                    _tags = ''
                else:
                    _, _test_name, _uuid, _options, _tags = \
                        self.tm.split_test_name(
                            _class_name + "." + _test_name
                        )
                _duration = self._parse_duration(_test_node.attrib.get('time', '0'))

                _status, _reason, _sysout = self._parse_status(
                    list(_test_node)
                )
                # _options = ''
                _message = ""
                _trace = ""
                if _status == Status.SKIP:
                    # no trace present
                    _message = _reason if _reason else ""
                elif _status == Status.FAIL:
                    # Check if there is a inner Traceback present
                    # and prior to save the message, try to detect error type
                    _pytest_lines = self._detect_pytest_errors(_reason)
                    if _reason.count('Traceback') > 1:
                        # There is multiple tracebacks present
                        # correct one has line after Trace as 'File'
                        _tmp = ""
                        _lines = _reason.splitlines()
                        for idx in range(len(_lines)-1):
                            _line = _lines[idx].strip()
                            _next_line = _lines[idx+1].strip()
                            if _line.startswith("Traceback") and \
                                    (_next_line.startswith('File') or \
                                    _next_line.find('Traceback (') >= 0):
                                _tmp = "\n".join(_lines[idx:])
                                break
                        _trace = _tmp
                    elif self._is_k8s_error(_reason):
                        # This is a k8s-conformance error
                        # Try to extract with regex

                        # This is not good, error messages can be multilined
                        # _errs = re.findall(
                        #     r"^.{0,3}\s+\d{1,2}\s\d{1,2}:\d{1,2}:\d{1,2}\.\d{0,3}:.*$",
                        #     _reason,
                        #     re.MULTILINE
                        # )

                        # All between "<digit>\n" and "\n/go"
                        _errs = re.findall(
                            r"(?s)(?<=\d\n)(.*?)(?=\n\/go)",
                            _reason,
                            re.MULTILINE
                        )
                        if not _errs:
                            # Parse the error message line by line
                            _message, _trace = k8s_slow_extract(_reason)
                        else:
                            _message = "\n".join(_errs)
                    elif _pytest_lines:
                        # This is a pytest error
                        _message, _trace = self._parse_pytest_error(
                            _pytest_lines
                        )
                    else:
                        _trace = _reason

                if _status in self.status_filters:
                    continue

                # add this result to list
                self.tm.add_result_for_test(
                    _execution_name,
                    _class_name,
                    _test_name,
                    _uuid,
                    _options,
                    _status,
                    _duration,
                    message=_message,
                    trace=_trace,
                    tags=_tags
                )

            self.add_execution(_execution_name, _execution_date)

        return True


# Rally and xunit CSV statuses
_rally_status_map = {
    'success': Status.OK,
    'fail': Status.FAIL,
    'skip': Status.SKIP,
    'xfail': Status.X_FAIL,
    'usuccess': Status.X_OK
}


class JSONImporter(ImporterBase):
    @staticmethod
    def _parse_status(status):
        return _rally_status_map[status]

    def parse(self):
        data = json.load(self.source)

        # Use filename as name for the execution
        _execution_name = self.execution_name(self.source.name)
        _execution_date = self.execution_date()

        verification = next(iter(data['verifications']))

        # iterate through test cases and add up results
        for _test_name, _test_value in data['tests'].items():
            _class_name, _test_name, _uuid, _options, _tags = \
                self.tm.split_test_name(_test_name)
            _test_value_results = _test_value['by_verification'][verification]
            _status = self._parse_status(_test_value_results['status'])
            _duration = parse_seconds(_test_value_results['duration'])
            _message = _test_value_results.get('details', '')
            _trace = _test_value_results.get('traceback', '')
            if _status in self.status_filters:
                continue

            self.tm.add_result_for_test(
                _execution_name,
                _class_name,
                _test_name,
                _uuid,
                _options,
                _status,
                _duration,
                message=_message,
                trace=_trace,
                tags=_tags
            )

        self.add_execution(_execution_name, _execution_date)
        return _execution_name


class CSVImporter(ImporterBase):
    subtype = None

    @staticmethod
    def _fix_message(string):
        _string = string.replace('"', '\'')
        _string = _string.replace(',', ' ')
        return _string

    def __init__(self, test_manager, source, **kwargs):
        super().__init__(test_manager, source, **kwargs)

        # read all rows, then detect file sub-type
        # by the first row that starts with 'Class' or a tempest test name
        self.rows = [row for row in csv.reader(self.source, delimiter=',')
                     if row]

        for row in self.rows:
            if row[0] == 'Class':
                self.subtype = CSV_OWN
                break
            if row[0].startswith("tempest."):
                self.subtype = CSV_XUNIT
                break

    @staticmethod
    def _parse_status(status):
        return _rally_status_map[status]

    def parse(self):
        if self.subtype == CSV_OWN:
            self.parse_own_csv()
        elif self.subtype == CSV_XUNIT:
            self.parse_xunit_csv()

    def parse_own_csv(self):
        _execution_name = self.execution_name(self.source.name)
        _execution_date = self.execution_date()

        _class_name = ''

        _status_index = 2
        for _row_index, row in enumerate(self.rows):
            # parse the data, first row is the header
            if _row_index == 0:
                continue
            elif row[0].lower() == 'class':
                _class_name = row[1]
                continue
            elif int(row[0].lower()) > 0:
                _test_name = row[1]
                if row[2] in (Status.REQUIRED, Status.ADDED):
                    _status_index = 3
                _status = row[_status_index]
                _message = self._fix_message(
                    row[_status_index + 1] if len(row) > _status_index + 1
                    else '')
                if _status in self.status_filters:
                    continue
                self.tm.add_result_for_test(
                    _execution_name,
                    _class_name,
                    _test_name,
                    '',
                    '',
                    _status,
                    None,
                    message=_message,
                    test_name_bare=True,
                )

                continue
            else:
                raise (
                    Exception(
                        "ERROR: Invalid CSV structure. \n"
                        "\tPlease, follow format:\n"
                        "\t\tClass,<class name>,,"
                        "\t\t<number>,<test_name>,<status>,<message>")
                )

        self.add_execution(_execution_name, _execution_date)
        return _execution_name

    def parse_xunit_csv(self):
        _execution_name = self.execution_name(self.source.name)
        _execution_date = self.execution_date()

        for row in self.rows:
            # parse the data, skip the header and other non-test rows
            if not row[0].startswith("tempest."):
                continue
            _splitted_test_name = row[0].rsplit('.', 1)
            _class_name = _splitted_test_name[0]
            _test_name = _splitted_test_name[1]
            _status = self._parse_status(row[1])
            _message = row[2]
            if _status in self.status_filters:
                continue

            self.tm.add_result_for_test(
                _execution_name,
                _class_name,
                _test_name,
                '',
                '',
                _status,
                None,
                message=_message,
                test_name_bare=True
            )

        self.add_execution(_execution_name, _execution_date)
        return _execution_name


class TParserResult(TestByTestResult):
    @staticmethod
    def _parse_status(status):
        return {
            'success': Status.OK,
            'failure': Status.FAIL,
            'error': Status.ERROR,
            'skip': Status.SKIP,
            'xfail': Status.X_FAIL,
            'uxsuccess': Status.X_OK
        }[status]

    def __init__(self, name, tm, status_filters=None):
        super().__init__(self._on_test)
        self._execution_name = name
        self.tm = tm
        self.status_filters = status_filters or []
        self.counter = 0

    def _on_test(self, test, status, start_time, stop_time, tags, details):
        _test_name = "none"
        _uuid = ""
        _test_options = ""
        _id = test.id()
        if _id.startswith("setUpClass"):
            _class_name, _, _, _, _ = self.tm.split_test_name(_id)
        else:
            _class_name, _test_name, _uuid, _test_options, _tags = \
                self.tm.split_test_name(_id)

        _status = self._parse_status(status)

        _message = ''
        _tb = ''

        if _status in self.status_filters:
            return

        if _status in (Status.FAIL, Status.ERROR) and 'traceback' in details:
            _tb = details['traceback'].as_text()
        elif _status == Status.SKIP and 'reason' in details:
            _message = details['reason'].as_text()

        _time = None
        if start_time is not None and stop_time is not None:
            _time = (stop_time - start_time).total_seconds()

        self.tm.add_result_for_test(
            self._execution_name,
            _class_name,
            _test_name,
            _uuid,
            _test_options,
            _status,
            _time,
            tags=tags,
            message=_message,
            trace=_tb
        )

        self.counter += 1


class SubunitImporter(ImporterBase):

    def __init__(self, test_manager, source, **kwargs):
        super().__init__(test_manager, source, **kwargs)
        self.source = make_stream_binary(source)

    def parse(self):
        _execution_date = self.execution_date()
        _execution_name = self.execution_name(getattr(self.source, "name", "<stdin>"))

        _result = TParserResult(
            _execution_name, self.tm, status_filters=self.status_filters)
        run_tests_from_stream(
            self.source,
            StreamToExtendedDecorator(_result),
            protocol_version=2,
            passthrough_subunit=False
        )
        log.debug("%s: %d tests", _execution_name, _result.counter)

        self.add_execution(_execution_name, _execution_date)
