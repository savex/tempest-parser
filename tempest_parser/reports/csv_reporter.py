import os
import tempest_parser.utils.file as futils
from copy import copy


class CSVReporter:
    # csv file will list all of the test runs
    # ##, name, testrun1, , testrun2, , ...
    # ,class_announce,,,,,
    # ##, test_name,result1,result2,...

    def __init__(self, test_manager):
        self.test_manager = test_manager
        self._tests = self.test_manager.get_tests_list()
        self._total_executions = sorted(self._tests["executions"].keys())
        return

    def generate_to_file(self, filename, detailed=False):
        # clear file content if any
        try:
            futils.remove_file(filename)
        except OSError:
            pass

        # header
        csv_header = ", class/test name,"
        _result_columns = 0
        # execution names for header
        if 'required' in self._total_executions:
            _date_prepared = self._tests['executions']['required']
            _date_prepared = _date_prepared.replace('/', '\n')
            _date_prepared = _date_prepared.replace(' ', '\n')
            csv_header += '"' + _date_prepared + '",'
            _result_columns += 1

        for _execution in self._total_executions:
            if _execution != 'required':
                # execution name
                # csv_header += _execution + ','
                _date_prepared = self._tests['executions'][_execution]
                _date_prepared = _date_prepared.replace('/', '\n')
                _date_prepared = _date_prepared.replace(' ', '\n')
                csv_header += '"' + _date_prepared + '",'
                if detailed:
                    csv_header += '"' + os.path.basename(_execution) + '",'
                    _result_columns += 2
                else:
                    _result_columns += 1

        futils.append_line_to_file(filename, csv_header)
        _tests_counter = 0

        # lines
        for class_name in sorted(self._tests['tests'].keys()):
            # printing out class line
            _class_line = 'Class' + \
                          ',' + \
                          class_name + \
                          ','
            for i in range(0, _result_columns):
                _class_line += ',' + ','
            # write class line
            futils.append_line_to_file(filename, _class_line)

            # iterate tests
            for _test in self._tests['tests'][class_name]:
                _tests_counter += 1
                _test_line = str(_tests_counter) + \
                    ',' + \
                    _test['test_name'] + \
                    _test['test_options'] + \
                    ','
                # iterate results
                _results = ""

                # Add a Required/Added mark to results
                if 'required' in _test['results']:
                    _results += _test['results']['required']['result'] + ','
                else:
                    _results += 'A' + ','

                # Iterate other results
                for _execution in self._total_executions:
                    if _execution != 'required':
                        if _execution in _test['results']:
                            _results += _test['results'][_execution][
                                            'result'] + ','
                            if detailed:
                                # new template has no 'time' mark,
                                # just comment it out
                                # _results += _
                                #   test['results'][_execution]['time'] + ','

                                # check if there is a fail
                                _tmp_result = _test['results'][_execution][
                                    'result']
                                if _tmp_result == 'FAIL':
                                    _trace = copy(
                                        _test['results'][_execution]['trace'])
                                    _trace = _trace.replace('"', '\'')
                                    _results += \
                                        '\"' + _test['results'][_execution][
                                            'message'] + '\x0a' + _trace + \
                                        '\"' + ','
                                elif _tmp_result == 'SKIP':
                                    _message = \
                                        copy(_test['results'][_execution]
                                             ['message']).replace("\'", '\'')
                                    _results += '\"' + _message + '\"' + ','
                                else:
                                    _results += ','
                        else:
                            if detailed:
                                _results += ',' + ','
                            else:
                                _results += ','
                futils.append_line_to_file(filename, _test_line + _results)
