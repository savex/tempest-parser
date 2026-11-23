from tempest_parser.manager.test_manager import TestsManager
from tempest_parser.parser.tempest_log_parser import TempestLogParser

from ..conftest import PORTS, SERVERS


def _parse(path):
    tm = TestsManager()
    with open(path) as source:
        TempestLogParser(tm, source).parse()
    return tm


def _result(tm, cls, name, run):
    test = next(t for t in tm.get_tests_for_class(cls) if t["test_name"] == name)
    return test["results"][run]


def test_log_results(data_file):
    path = data_file("tempest.log")
    tm = _parse(path)
    run = path.lower()
    assert list(tm.get_executions()) == [run]
    assert _result(tm, SERVERS, "test_create_server", run)["result"] == "OK"
    assert _result(tm, SERVERS, "test_create_server", run)["time"] == "1.50s"
    assert _result(tm, SERVERS, "test_delete_server", run)["result"] == "FAIL"
    assert _result(tm, PORTS, "test_list_ports", run)["result"] == "SKIP"
    assert len(tm.get_tests_for_class(SERVERS)) == 2
    assert tm.get_summary_for_execution(run)[1:] == (3, 1, 1, 1)


def test_log_fail_message_and_slowest(data_file):
    path = data_file("tempest.log")
    tm = _parse(path)
    run = path.lower()
    fail = _result(tm, SERVERS, "test_delete_server", run)
    assert "Details: 1 != 2" in fail["message"]
    assert "Traceback (most recent call last):" in fail["trace"]
    assert _result(tm, SERVERS, "test_create_server", run)["slowest"] is True


def test_log_status_filter(data_file):
    path = data_file("tempest.log")
    tm = TestsManager()
    with open(path) as source:
        TempestLogParser(tm, source, status_filters=["OK"]).parse()
    names = [t["test_name"] for t in tm.get_tests_for_class(SERVERS)]
    assert names == ["test_delete_server"]
