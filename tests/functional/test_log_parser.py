import os
import shutil

from tempest_parser.manager.test_manager import TestsManager
from tempest_parser.parser.tempest_log_parser import TempestLogParser

from ..conftest import DATA_DIR, PORTS, SERVERS


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


TRENDING_RUNS = ["run_1.log", "run_2.log", "run_3.log", "run_4.log"]
NETWORKS = "tempest.api.network.test_networks.NetworksTestJSON"
USERS = "tempest.api.identity.admin.test_users.UsersTestJSON"
QUOTAS = "tempest.api.compute.admin.test_quotas.QuotasAdminTestJSON"


def _parse_trending(tmp_path):
    tm = TestsManager()
    runs = []
    for name in TRENDING_RUNS:
        target = tmp_path / name
        shutil.copy(os.path.join(DATA_DIR, "trending", name), target)
        with open(target) as source:
            TempestLogParser(tm, source).parse()
        runs.append(str(target).lower())
    return tm, runs


def _runs_with(tm, cls, name, runs):
    test = next(t for t in tm.get_tests_for_class(cls) if t["test_name"] == name)
    return [runs.index(r) + 1 for r in runs if r in test["results"]]


def test_trending_runs(tmp_path):
    tm, runs = _parse_trending(tmp_path)
    assert sorted(tm.get_executions()) == runs
    assert [tm.get_summary_for_execution(r)[1] for r in runs] == [26, 24, 29, 32]
    # in every run
    assert _runs_with(tm, SERVERS, "test_update_server_name", runs) == [1, 2, 3, 4]
    # missing in one run
    assert _runs_with(tm, NETWORKS, "test_show_subnet", runs) == [1, 2, 4]
    assert _runs_with(tm, USERS, "test_list_users_for_tenant", runs) == [1, 3, 4]
    # new in runs 3 and 4
    assert _runs_with(tm, USERS, "test_user_authentication", runs) == [3, 4]
    assert len(tm.get_tests_for_class(QUOTAS)) == 4
    assert _runs_with(tm, QUOTAS, "test_delete_quota", runs) == [3, 4]
    # a failure fixed in run 3
    results = [_result(tm, SERVERS, "test_update_server_name_in_stop_state", r)["result"]
               for r in runs]
    assert results == ["FAIL", "FAIL", "OK", "OK"]
