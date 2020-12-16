from __future__ import print_function

from xml.etree.ElementTree import parse
import json
import csv
import os
import re
import six
import time


from subunit import make_stream_binary
from subunit.test_results import TestByTestResult
from subunit.filters import run_tests_from_stream
from testtools import StreamToExtendedDecorator

CSV_OWN = 1
CSV_XUNIT = 2


def remove_control_chars(s):
    # import unicodedata
    # all_chars = (unichr(i) for i in xrange(0x110000))
    # control_chars = ''.join(
    #   c for c in all_chars if unicodedata.category(c) == 'Cc'
    # )
    control_chars = ''.join(map(unichr, range(0, 32) + range(127, 160)))
    control_char_re = re.compile('[%s]' % re.escape(control_chars))
    return control_char_re.sub('', s)


def get_date_from_source(source):
    # filename handling
    _fd = source
    _stat = os.stat
    # opened already, get descriptor
    if hasattr(source, 'read'):
        _stat = os.fstat
        _fd = source.fileno()

    (mode, ino, dev, nlink, uid, gid, size, atime, mtime, ctime) = _stat(_fd)
    # we need to be closer to creation, so ctime is for us.
    # Just leaving those here, in case needed
    # _atime = time.strftime("%d/%m/%Y %H:%M", time.gmtime(atime))
    # _mtime = time.strftime("%d/%m/%Y %H:%M", time.gmtime(mtime))
    # _ctime = time.strftime("%d/%m/%Y %H:%M", time.gmtime(ctime))
    return time.strftime(
        "%d/%m/%Y %H:%M GMT",
        time.gmtime(mtime)
    ), time.gmtime(mtime)


class ImporterBase(object):
    def __init__(
        self,
        test_manager,
        source,
        use_raw_names=False,
        status_filters=[],
        force_single_execution=None
    ):
        self.source = source
        self.tm = test_manager
        self.use_raw_names = use_raw_names
        self.forced_execution_name = force_single_execution
        self.status_filters = status_filters

    def add_execution(self, name, date, duration, unixtime):
        self.tm.add_execution(
            dict(
                execution_name=name,
                execution_date=date,
                summary={'time': duration},
            ),
            unixtime=unixtime
        )


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
    'skipped': 'SKIP',
    'failure': 'FAIL',
    'error': 'ERROR',
    'system-err': 'ERROR'
}


class XMLImporter(ImporterBase):
    @staticmethod
    def _parse_duration(duration):
        _time_in_sec = float(duration) / 1000.0
        return str(_time_in_sec) + 's'

    @staticmethod
    def _parse_status(status):
        # XML has one child node for status and text as a reason
        if not len(status):
            return 'OK', "Test passed"
        else:
            _status = ""
            _reason = ""
            _idx = 0
            # cut system-out
            while len(status) > 0 and _idx < len(status):
                if status[_idx].tag == 'system-out':
                    _status = "OK"
                    _reason = "{}:\n{}\n{}".format(
                        status[_idx].tag,
                        status[_idx].text,
                        _reason
                    )
                    _ = status.pop(_idx)
                else:
                    _idx += 1

            # iterate others
            while len(status) > 0:
                # last encountered node will be the status
                _s = status.pop()
                _status = _error_status_map[_s.tag]
                _reason = "{}:\n{}\n{}".format(
                    _s.tag,
                    _s.text,
                    _reason
                )
            return _status, _reason

    def _is_k8s_error(self, reason):
        _errs = reason.count('errors.errorString')
        _k8s = reason.count('k8s.io')

        return True if _errs > 0 and _k8s > 0 else False

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

        _execution_date, _unixtime = get_date_from_source(self.source)
        _all_testsuites = []
        # We should be ready for multiple test suites in one xml
        if root.tag == 'testsuite':
            _all_testsuites.append(root)
        else:
            _all_testsuites += root.findall('testsuite')

        for _testsuite in _all_testsuites:

            # _execution_name = _testsuite.attrib['id']
            if self.forced_execution_name is None:
                _execution_name = self.source.name
            else:
                _execution_name = self.forced_execution_name

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
                _duration = "0s"
                try:
                    _duration = self._parse_duration(
                        _test_node.attrib['time']
                    )
                except KeyError:
                    pass

                _status, _reason = self._parse_status(list(_test_node))
                # _options = ''
                _message = ""
                _trace = ""
                if _status == 'SKIP':
                    # no trace present
                    _message = _reason if _reason else ""
                elif _status == 'FAIL':
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
                                    _next_line.startswith('File'):
                                _tmp = "\n".join(_lines[idx:])
                                break
                        _trace = _tmp
                    elif self._is_k8s_error(_reason):
                        # This is a k8s-conformance error
                        # Parse the error message
                        _tmp = []
                        _lines = _reason.splitlines()
                        for idx in range(len(_lines)-1):
                            _line = _lines[idx].strip()
                            _next_line = _lines[idx+1].strip()
                            if _line.startswith("<*errors.errorString") and \
                                    _next_line.startswith("s: \""):
                                err = _next_line.split('"')[1]
                                err = err.encode('ascii', 'ignore')
                                if err.count("\\x00") > 1:
                                    err = err.replace("\\x00", "")
                                err = remove_control_chars(err)
                                _tmp.append(err)
                            elif _next_line.startswith("not to have occurred"):
                                _tmp.append(_line.encode('ascii', 'ignore'))
                        if len(_tmp) > 0:
                            _message = "\n".join(_tmp)
                        else:
                            _trace = _reason
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

            self.add_execution(
                _execution_name,
                _execution_date,
                self._parse_duration(_testsuite.attrib['time']),
                _unixtime
            )

        return True


class JSONImporter(ImporterBase):
    @staticmethod
    def _parse_status(status):
        return {
            'success': 'OK',
            'fail': 'FAIL',
            'skip': 'SKIP',
            'xfail': 'X_FAIL',
            'usuccess': 'X_OK'
        }[status]

    def parse(self):
        data = json.load(self.source)

        # Use filename as name for the execution
        _execution_name = self.source.name
        _execution_date, _unixtime = get_date_from_source(self.source)

        verification = data['verifications'].keys()[0]

        # iterate through test cases and add up results
        for _test_name, _test_value in data['tests'].items():
            if isinstance(_test_name, six.text_type):
                _test_name = _test_name.encode("utf-8")
            _class_name, _test_name, _uuid, _options, _tags = \
                self.tm.split_test_name(_test_name)
            _test_value_results = _test_value['by_verification'][verification]
            _status = self._parse_status(_test_value_results['status'])
            _duration = _test_value_results['duration'] + 's'
            if 'details' in _test_value_results:
                _message = _test_value_results['details']
            else:
                _message = ''
            _trace = _test_value_results[
                'traceback'] if 'traceback' in _test_value_results else ''

            # parsing tags
            # if _test_value['tags'][0].find('(') > -1:
            #     _tag = _test_value['tags'][0].split(']')[0]
            #     _tags = '[{}]'.format(_tag)
            #     _option = _test_value['tags'][0].split('(')[1]
            #     _options = '({})'.format(_option)
            # else:
            #     _tags = '[{}]'.format(','.join(_test_value['tags']))
            #     _options = ''

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

        self.add_execution(
            _execution_name,
            _execution_date,
            '0s',
            _unixtime
        )
        return _execution_name


class CSVImporter(ImporterBase):
    subtype = None

    @staticmethod
    def _fix_message(string):
        _string = string.replace('"', '\'')
        _string = _string.replace(',', ' ')
        return _string

    def __init__(self, test_manager, source):
        super(CSVImporter, self).__init__(test_manager, source)

        # detect file sub-type
        self.csvdata = csv.reader(self.source, delimiter=',')

        for row in self.csvdata:
            # detect if line starts with 'Class'
            if row[0] == 'Class':
                self.subtype = CSV_OWN
                break
            if row[0].startswith("tempest."):
                self.subtype = CSV_XUNIT
                break

    @staticmethod
    def _parse_status(status):
        return {
            'success': 'OK',
            'fail': 'FAIL',
            'skip': 'SKIP',
            'xfail': 'X_FAIL',
            'usuccess': 'X_OK'
        }[status]

    def parse(self):
        if self.subtype == CSV_OWN:
            self.parse_own_csv()
        elif self.subtype == CSV_XUNIT:
            self.parse_xunit_csv()

    def parse_own_csv(self):
        _execution_name = self.source.name
        _execution_date, _unixtime = get_date_from_source(self.source)

        _class_name = ''

        _status_index = 2
        for row in self.csvdata:
            # parse the data
            if self.csvdata.line_num == 1:
                continue
            elif row[0].lower() == 'class':
                _class_name = row[1]
                continue
            elif int(row[0].lower()) > 0:
                _test_name = row[1]
                if row[2] in ['R', 'A']:
                    _status_index = 3
                _status = row[_status_index]
                _message = self._fix_message(row[_status_index+1])
                self.tm.add_result_for_test(
                    _execution_name,
                    _class_name,
                    _test_name,
                    '',
                    '',
                    _status,
                    '',
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

        self.add_execution(
            _execution_name,
            _execution_date,
            'n/a',
            _unixtime
        )
        return _execution_name

    def parse_xunit_csv(self):
        _execution_name = self.source.name
        _execution_date, _unixtime = get_date_from_source(self.source)

        for row in self.csvdata:
            # parse the data
            if self.csvdata.line_num == 1:
                continue
            _splitted_test_name = row[0].rsplit('.', 1)
            _class_name = _splitted_test_name[0]
            _test_name = _splitted_test_name[1]
            _status = self._parse_status(row[1])
            _message = row[2]

            self.tm.add_result_for_test(
                _execution_name,
                _class_name,
                _test_name,
                '',
                '',
                _status,
                '',
                message=_message,
                test_name_bare=True
            )

        self.add_execution(
            _execution_name,
            _execution_date,
            'n/a',
            _unixtime
        )
        return _execution_name


class TParserResult(TestByTestResult):
    @staticmethod
    def _parse_status(status):
        return {
            'success': 'OK',
            'failure': 'FAIL',
            'skip': 'SKIP',
            'xfail': 'X_FAIL',
            'usuccess': 'X_OK'
        }[status]

    def __init__(self, name, tm):
        super(TParserResult, self).__init__(self._on_test)
        self._execution_name = name
        self.tm = tm
        self.counter = 0

    def _on_test(self, test, status, start_time, stop_time, tags, details):
        print(' '*6, end='\r')
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

        if _status == 'FAIL':
            _tb = details['traceback'].as_text()
        elif _status == 'SKIP':
            _message = details['reason'].as_text()

        self.tm.add_result_for_test(
            self._execution_name,
            _class_name,
            _test_name,
            _uuid,
            _test_options,
            _status,
            stop_time - start_time,
            tags=tags,
            message=_message,
            trace=_tb
        )

        print("{:>5}".format(self.counter), end='')
        self.counter += 1


class SubunitImporter(ImporterBase):

    def __init__(self, test_manager, source):
        super(SubunitImporter, self).__init__(test_manager, source)
        self.source = make_stream_binary(source)

    def parse(self):
        _execution_date, _unixtime = get_date_from_source(self.source)
        _execution_name = self.source.name + _execution_date

        run_tests_from_stream(
            self.source,
            StreamToExtendedDecorator(TParserResult(_execution_name, self.tm)),
            protocol_version=2,
            passthrough_subunit=False
        )
        print("\n...done")

        self.add_execution(
            _execution_name,
            _execution_date,
            'n/a',
            _unixtime
        )

        return
