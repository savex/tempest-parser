from __future__ import print_function

from xml.etree.ElementTree import parse
import json
import csv
import os
import time

from subunit import make_stream_binary
from subunit.test_results import TestByTestResult
from subunit.filters import run_tests_from_stream
from testtools import StreamToExtendedDecorator

CSV_OWN = 1
CSV_XUNIT = 2


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
        time.gmtime(ctime)
    )


class ImporterBase(object):
    def __init__(self, test_manager, source):
        self.source = source
        self.tm = test_manager

    def add_execution(self, name, date, duration):
        self.tm.add_execution(
            dict(
                execution_name=name,
                execution_date=date,
                summary={'time': duration}
            )
        )


class XMLImporter(ImporterBase):
    @staticmethod
    def _parse_duration(duration):
        _time_in_sec = float(duration) / 1000.0
        return str(_time_in_sec) + 's'

    @staticmethod
    def _parse_status(status):
        return {
            'passed': 'OK',
            'failed': 'FAIL',
            'ignored': 'SKIP',
            'error': 'FAIL'
        }[status]

    def parse(self):
        tree = parse(self.source)
        root = tree.getroot()

        _execution_name = root.attrib['name'].lower()

        # iterate through classes
        for _class_node in root.findall('suite'):
            # iterate through tests
            _class_name = _class_node.attrib['name']

            # remove any '%' symbols and following number
            _symbol_index = _class_name.find('%')
            if _symbol_index > 0:
                _class_name = _class_name[:_symbol_index] + \
                              _class_name[_symbol_index + 2:]

            for _test_node in _class_node.findall('test'):
                # get all attributes from xml
                _test_name = _test_node.attrib['name']
                _duration = "0s"
                try:
                    _duration = self._parse_duration(
                        _test_node.attrib['duration']
                    )
                except KeyError:
                    pass
                _status = self._parse_status(_test_node.attrib['status'])
                _options = ''

                # add this result to list
                self.tm.add_result_for_test(
                    _execution_name,
                    _class_name,
                    _test_name,
                    _options,
                    _status,
                    _duration,
                    class_name_short=True
                )
                for _output in _test_node.findall('output'):
                    _type = _output.attrib['type']
                    _trace = ""
                    _message = ""

                    if _type == 'stdout':
                        # no trace present
                        _message = _output.text
                    elif _type == 'stderr':
                        _trace = _output.text

                    self.tm.add_fail_data_for_test(
                        _execution_name,
                        _class_name,
                        _test_name,
                        _options,
                        _trace,
                        _message,
                        class_name_short=True
                    )

        self.add_execution(
            _execution_name,
            '',
            self._parse_duration(root.attrib['duration'])
        )

        return _execution_name


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
        _execution_date = get_date_from_source(self.source)

        verification = data['verifications'].keys()[0]

        # iterate through test cases and add up results
        for _test_name, _test_value in data['tests'].items():
            _class_name, _test_name, _uuid, _options = \
                self.tm.split_test_name(_test_name)

            _test_value_results = _test_value['by_verification'][verification]
            _status = self._parse_status(_test_value_results['status'])
            _duration = _test_value_results['duration'] + 's'
            _message = _test_value_results['details'] if 'details' in _test_value_results else ''
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
                trace=_trace
            )

        self.add_execution(
            _execution_name,
            _execution_date,
            '0s'
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
        _execution_date = get_date_from_source(self.source)

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
                    test_name_bare=True
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
            'n/a'
        )
        return _execution_name

    def parse_xunit_csv(self):
        _execution_name = self.source.name
        _execution_date = get_date_from_source(self.source)

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
            'n/a'
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
            _class_name, _, _, _ = self.tm.split_test_name(_id)
        else:
            _class_name, _test_name, _uuid, _test_options = \
                self.tm.split_test_name(_id)

        _status = self._parse_status(status)

        _message = ''
        _tb = ''

        if _status is 'FAIL':
            _tb = details['traceback'].as_text()
        elif _status is 'SKIP':
            _message = details['reason'].as_text()

        self.tm.add_result_for_test(
            self._execution_name,
            _class_name,
            _test_name,
            _uuid,
            _test_options,
            _status,
            stop_time - start_time,
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
        _execution_date = get_date_from_source(self.source)
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
            'n/a'
        )

        return
