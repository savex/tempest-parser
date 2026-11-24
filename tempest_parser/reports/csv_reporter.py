import csv

from tempest_parser.const import REQUIRED_RUN, Status
from tempest_parser.manager.models import Case, Execution, Result
from tempest_parser.manager.test_manager import TestsManager


class CSVReporter:
    """Writes every run as columns, tests as rows.

    Header: "", "class/test name", required/added column, then per run its date
    (and file name with `detailed`).
    Class rows: "Class", <class name>, blanks.
    Test rows: <number>, <test name + options>, R or A, then per run its result
    (and the message, plus the trace for failures, with `detailed`).
    """

    REQUIRED = REQUIRED_RUN

    def __init__(self, test_manager: TestsManager) -> None:
        self.test_manager = test_manager
        executions = test_manager.executions
        self._required = executions.get(self.REQUIRED)
        self._runs = sorted(
            (execution for name, execution in executions.items() if name != self.REQUIRED),
            key=lambda execution: execution.name)

    @staticmethod
    def _date_cell(execution: Execution) -> str:
        # one date part per line keeps the columns narrow
        return execution.date_label.replace('/', '\n').replace(' ', '\n')

    def _header(self, detailed: bool) -> list[str]:
        if self._required is not None:
            header = ["", "class/test name", self._date_cell(self._required)]
        else:
            header = ["", "class/test name", "Required vs Added"]
        for run in self._runs:
            header.append(self._date_cell(run))
            if detailed:
                header.append(run.filename)
        return header

    @staticmethod
    def _details(result: Result) -> str:
        if result.result == Status.FAIL:
            return result.message + '\n' + result.trace
        if result.result == Status.SKIP:
            return result.message
        return ''

    def _test_row(self, number: int, test: Case, detailed: bool) -> list[str | int]:
        results = test.results
        row: list[str | int] = [number, test.test_name + test.test_options,
               results[self.REQUIRED].result if self.REQUIRED in results else Status.ADDED]
        for run in self._runs:
            result = results.get(run.name)
            row.append(result.result if result else '')
            if detailed:
                row.append(self._details(result) if result else '')
        return row

    def generate_to_file(self, filename: str, detailed: bool = False) -> None:
        header = self._header(detailed)
        tests = self.test_manager.tests
        with open(filename, 'w', newline='', encoding='utf-8') as target:
            writer = csv.writer(target, lineterminator='\n')
            writer.writerow(header)
            number = 0
            for class_name in sorted(tests):
                writer.writerow(
                    ["Class", class_name] + [""] * (len(header) - 2))
                for test in tests[class_name]:
                    number += 1
                    writer.writerow(self._test_row(number, test, detailed))
