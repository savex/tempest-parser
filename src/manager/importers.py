from xml.etree.ElementTree import parse
import json
import csv


class ImporterBase(object):
    def __init__(self, test_manager, filename):
        self.filename = filename
        self.tm = test_manager


class XMLImporter(ImporterBase):
    @staticmethod
    def _parse_duration(duration):
        _time_in_sec = float(duration) / 1000.0
        return str(_time_in_sec) + 's'

    def _add_execution(self, name, duration):
        self.tm.add_execution(
            dict(
                execution_name=name,
                execution_date='',
                summary=dict(
                    time=self._parse_duration(duration)
                )
            )
        )

        # time = 0

    @staticmethod
    def _parse_status(status):
        return {
            'passed': 'OK',
            'failed': 'FAIL',
            'ignored': 'SKIP',
            'error': 'FAIL'
        }[status]

    def parse(self):
        tree = parse(self.filename)
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
                              _class_name[_symbol_index+2:]

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

        self._add_execution(_execution_name, root.attrib['duration'])

        return _execution_name


class JSONImporter(ImporterBase):
    def _add_execution(self, name, date, duration):
        self.tm.add_execution(
            dict(
                execution_name=name,
                execution_date=date,
                summary=dict(
                    time=duration+"s"
                )
            )
        )

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
        with open(self.filename, 'rt') as datafile:
            data = json.load(datafile)

        # Use filename as name for the execution
        _execution_name = self.filename
        _execution_date = '1/06/2016'

        # iterate through test cases and add up results
        for _test_key, _test_value in data['test_cases'].iteritems():
            _splitted_test_name = _test_value['name'].rsplit('.', 1)
            _class_name = _splitted_test_name[0]
            _test_name = _splitted_test_name[1]
            _status = self._parse_status(_test_value['status'])
            _duration = _test_value['time'] + 's'
            _message = _test_value['reason'] if 'reason' in _test_value else ''
            _trace = _test_value['traceback'] if 'traceback' in _test_value else ''

            # parsing tags
            if _test_value['tags'][0].find('(') > -1:
                _tag = _test_value['tags'][0].split(']')[0]
                _tags = '[{}]'.format(_tag)
                _option = _test_value['tags'][0].split('(')[1]
                _options = '({})'.format(_option)
            else:
                _tags = '[{}]'.format(','.join(_test_value['tags']))
                _options = ''

            self.tm.add_result_for_test(
                _execution_name,
                _class_name,
                _test_name,
                _tags,
                _options,
                _status,
                _duration,
                message=_message,
                trace=_trace
            )

        self._add_execution(_execution_name, _execution_date, data['time'])
        return _execution_name


class CSVImporter(ImporterBase):
    def _add_execution(self, name, date, duration):
        self.tm.add_execution(
            dict(
                execution_name=name,
                execution_date=date,
                summary=dict(
                    time=duration+"s"
                )
            )
        )

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
        _execution_name = self.filename
        _execution_date = '20/12/2015'

        with open(self.filename, 'rt') as csvfile:
            csvdata = csv.reader(csvfile, delimiter=',')

            for row in csvdata:
                # parse the data
                if csvdata.line_num == 1:
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

            self._add_execution(_execution_name, _execution_date, 'n/a')
            return _execution_name
