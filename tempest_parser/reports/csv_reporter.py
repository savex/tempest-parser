import csv
import os


class CSVReporter:
    """Writes every run as columns, tests as rows.

    Header: "", "class/test name", required/added column, then per run its date
    (and file name with `detailed`).
    Class rows: "Class", <class name>, blanks.
    Test rows: <number>, <test name + options>, R or A, then per run its result
    (and the message, plus the trace for failures, with `detailed`).
    """

    REQUIRED = 'required'

    def __init__(self, test_manager):
        self.test_manager = test_manager
        self._tests = self.test_manager.get_tests_list()
        self._runs = sorted(
            name for name in self._tests["executions"] if name != self.REQUIRED)

    @staticmethod
    def _date_cell(date):
        # one date part per line keeps the columns narrow
        return date.replace('/', '\n').replace(' ', '\n')

    def _header(self, detailed):
        executions = self._tests['executions']
        if self.REQUIRED in executions:
            header = ["", "class/test name",
                      self._date_cell(executions[self.REQUIRED][0])]
        else:
            header = ["", "class/test name", "Required vs Added"]
        for run in self._runs:
            header.append(self._date_cell(executions[run][0]))
            if detailed:
                header.append(os.path.basename(run))
        return header

    @staticmethod
    def _details(result):
        if result['result'] == 'FAIL':
            return result['message'] + '\n' + result['trace']
        if result['result'] == 'SKIP':
            return result['message']
        return ''

    def _test_row(self, number, test, detailed):
        results = test['results']
        row = [number, test['test_name'] + test['test_options'],
               results[self.REQUIRED]['result'] if self.REQUIRED in results else 'A']
        for run in self._runs:
            result = results.get(run)
            row.append(result['result'] if result else '')
            if detailed:
                row.append(self._details(result) if result else '')
        return row

    def generate_to_file(self, filename, detailed=False):
        header = self._header(detailed)
        with open(filename, 'w', newline='') as target:
            writer = csv.writer(target, lineterminator='\n')
            writer.writerow(header)
            number = 0
            for class_name in sorted(self._tests['tests']):
                writer.writerow(
                    ["Class", class_name] + [""] * (len(header) - 2))
                for test in self._tests['tests'][class_name]:
                    number += 1
                    writer.writerow(self._test_row(number, test, detailed))
