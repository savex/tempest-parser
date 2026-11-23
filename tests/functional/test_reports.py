import csv
import os

import pytest

from tempest_parser.manager.importers import JSONImporter, XMLImporter
from tempest_parser.manager.test_manager import TestsManager
from tempest_parser.reports import reporter
from tempest_parser.reports.csv_reporter import CSVReporter
from tempest_parser.utils.config import ParserConfigFile

from ..conftest import PORTS, SERVERS


def _manager(path, required=None):
    tm = TestsManager()
    if required:
        tm.add_required(required)
    with open(path) as source:
        XMLImporter(tm, source).parse()
    return tm


def test_trending_report(data_file):
    tm = _manager(data_file("tempest.xml"))
    html = reporter.HTMLTrendingReport()(tm.get_tests_list(), detailed=True)
    assert SERVERS in html
    assert "test_delete_server" in html
    assert "tempest.xml" in html


def test_trending_report_escapes_messages(data_file):
    tm = _manager(data_file("tempest.xml"))
    html = reporter.HTMLTrendingReport()(tm.get_tests_list(), detailed=True)
    assert "&lt;ports&gt;" in html
    assert "<ports>" not in html


def test_reports_do_not_change_results(data_file):
    tm = _manager(data_file("tempest.xml"))
    reporter.HTMLTrendingReport()(tm.get_tests_list())
    reporter.HTMLTrendingReport()(tm.get_tests_list())
    skip = next(t for t in tm.get_tests_list()["tests"][PORTS]
                if t["test_name"] == "test_list_ports")
    message = next(iter(skip["results"].values()))["message"]
    assert "<ports>" in message


def test_errors_report_groups_messages(data_file):
    tm = _manager(data_file("tempest.xml"))
    html = reporter.HTMLErrorsReport()(tm.get_tests_list())
    assert "AssertionError" in html
    assert "&lt;ports&gt;" in html


def test_errors_report_details_line():
    report = reporter.HTMLErrorsReport()
    data = {
        "executions": [{"name": "run1"}],
        "tests": {SERVERS: [{
            "test_name": "test_a", "uuid": "", "test_options": "",
            "results": {"run1": {
                "result": "FAIL", "message": "",
                "trace": "Traceback:\n  File x\nDetails: <boom>\nValueError: bad"}},
        }]},
    }
    report._extend_data(data)
    (message, tests), = data["uniqie_fails"].items()
    assert message == "ValueError"
    assert tests[0]["trace_details"] == "<boom>"


def test_report_to_file(data_file, tmp_path):
    target = str(tmp_path / "report.html")
    tm = _manager(data_file("tempest.xml"))
    reporter.ReportToFile(reporter.HTMLTrendingReport(), target)(tm.get_tests_list())
    with open(target) as f:
        assert "test_create_server" in f.read()


def test_csv_report(data_file, data_dir, tmp_path):
    target = str(tmp_path / "out.csv")
    tm = _manager(data_file("tempest.xml"), required=os.path.join(data_dir, "baseline.list"))
    CSVReporter(tm).generate_to_file(target)
    with open(target) as f:
        rows = list(csv.reader(f))
    assert ["Class", SERVERS] == rows[1][:2]
    rows = [r for r in rows if r[0].isdigit()]
    by_name = {r[1]: r for r in rows}
    assert by_name["test_create_server"][2:4] == ["R", "OK"]
    assert by_name["test_not_run"][2] == "R"
    assert by_name["test_update_port"][2:4] == ["A", "OK"]


def test_csv_report_keeps_raw_messages(data_file, tmp_path):
    target = str(tmp_path / "out.csv")
    tm = _manager(data_file("tempest.xml"))
    reporter.HTMLTrendingReport()(tm.get_tests_list())
    CSVReporter(tm).generate_to_file(target, detailed=True)
    with open(target) as f:
        text = f.read()
    assert "<ports>" in text
    assert "&lt;" not in text


def test_config_defaults():
    config = ParserConfigFile(os.path.join(reporter.pkg_dir, "etc", "tempest-parser.conf"))
    assert config.get_detailed_column_default_value() is False
    path = config.get_all_tests_list_filepath()
    assert os.path.isabs(path) and os.path.isfile(path)


def test_config_custom(tmp_path):
    conf = tmp_path / "c.conf"
    conf.write_text("[ParserConfig]\ndefault_test_list=/abs/list\ndefault_detailed=yes\n")
    config = ParserConfigFile(str(conf))
    assert config.get_detailed_column_default_value() is True
    assert config.get_all_tests_list_filepath() == "/abs/list"


def test_trending_report_with_baseline_orders_runs(data_file, data_dir):
    tm = _manager(data_file("tempest.xml"), required=os.path.join(data_dir, "baseline.list"))
    with open(data_file("rally.json")) as source:
        JSONImporter(tm, source).parse()
    html = reporter.HTMLTrendingReport()(tm.get_tests_list())
    assert "test_not_run" in html
    assert all(isinstance(v[1], (int, float)) for v in tm.get_tests_list()["executions"].values())


def test_csv_report_quotes_in_messages(tmp_path):
    tm = TestsManager()
    tm.add_execution({"execution_name": "run1", "execution_date": "d"}, unixtime=1)
    tm.add_result_for_test("run1", SERVERS, "test_a", "", "", "FAIL", "1s",
                           message='said "no"', trace='file "x"')
    tm.add_result_for_test("run1", SERVERS, "test_b", "", "", "SKIP", "1s", message='"why"')
    target = str(tmp_path / "out.csv")
    CSVReporter(tm).generate_to_file(target, detailed=True)
    with open(target) as f:
        rows = [r for r in csv.reader(f) if r and r[0].isdigit()]
    assert [r[1] for r in rows] == ["test_a", "test_b"]
    assert rows[0][4] == 'said "no"\nfile "x"'
    assert rows[1][4] == '"why"'


@pytest.mark.parametrize("required", [False, True])
@pytest.mark.parametrize("detailed", [False, True])
def test_csv_report_header_matches_rows(data_file, data_dir, tmp_path, required, detailed):
    target = str(tmp_path / "out.csv")
    tm = _manager(data_file("tempest.xml"),
                  required=os.path.join(data_dir, "baseline.list") if required else None)
    with open(data_file("rally.json")) as source:
        JSONImporter(tm, source).parse()
    CSVReporter(tm).generate_to_file(target, detailed=detailed)
    with open(target) as f:
        rows = list(csv.reader(f))
    assert {len(r) for r in rows} == {3 + 2 * (2 if detailed else 1)}
    assert rows[0][1] == "class/test name"
    if not required:
        assert rows[0][2] == "Required vs Added"


def test_csv_report_overwrites_file(data_file, tmp_path):
    target = tmp_path / "out.csv"
    target.write_text("old content\n" * 100)
    CSVReporter(_manager(data_file("tempest.xml"))).generate_to_file(str(target))
    assert "old content" not in target.read_text()


INJECTED = '<img src=x onerror="alert(1)">'


def _injected_manager():
    tm = TestsManager()
    run = "/runs/" + INJECTED
    tm.add_execution({"execution_name": run, "execution_date": INJECTED}, unixtime=1)
    for name, result in (("test_fail", "FAIL"), ("test_skip", "SKIP")):
        tm.add_result_for_test(run, "pkg." + INJECTED, name + INJECTED, "", INJECTED, result, "1s",
                               message=INJECTED + "\nline2", trace=INJECTED)
    return tm


@pytest.mark.parametrize("report", [reporter.HTMLTrendingReport, reporter.HTMLErrorsReport])
def test_reports_escape_every_field(report):
    html = report()(_injected_manager().get_tests_list(), detailed=True)
    assert "<img" not in html
    assert "&lt;img src=x onerror=&#34;alert(1)&#34;&gt;" in html


def test_trending_report_keeps_line_breaks_in_messages():
    html = reporter.HTMLTrendingReport()(_injected_manager().get_tests_list(), detailed=True)
    assert "&gt;<br />line2" in html
