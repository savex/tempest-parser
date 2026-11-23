import os
import shutil
from datetime import UTC, datetime

from tempest_parser.manager.test_manager import TestsManager
from tempest_parser.parser.tempest_log_parser import TempestLogParser

from ..conftest import DATA_DIR, PORTS, SERVERS


def _parse(path):
    tm = TestsManager()
    with open(path) as source:
        TempestLogParser(tm, source).parse()
    return tm


def _result(tm, cls, name, run):
    test = next(t for t in tm.get_tests_for_class(cls) if t.test_name == name)
    return test.results[run]


def test_log_results(data_file):
    path = data_file("tempest.log")
    tm = _parse(path)
    run = path.lower()
    assert list(tm.get_executions()) == [run]
    assert _result(tm, SERVERS, "test_create_server", run).result == "OK"
    assert _result(tm, SERVERS, "test_create_server", run).time == 1.5
    assert _result(tm, SERVERS, "test_delete_server", run).result == "FAIL"
    assert _result(tm, PORTS, "test_list_ports", run).result == "SKIP"
    assert len(tm.get_tests_for_class(SERVERS)) == 2
    summary = tm.get_summary_for_execution(run)
    assert (summary.total, summary.ok, summary.fail, summary.skip) == (3, 1, 1, 1)
    assert summary.time == 2.0


def test_log_fail_message_and_slowest(data_file):
    path = data_file("tempest.log")
    tm = _parse(path)
    run = path.lower()
    fail = _result(tm, SERVERS, "test_delete_server", run)
    assert "Details: 1 != 2" in fail.message
    assert "Traceback (most recent call last):" in fail.trace
    assert _result(tm, SERVERS, "test_create_server", run).slowest is True


def test_log_status_filter(data_file):
    path = data_file("tempest.log")
    tm = TestsManager()
    with open(path) as source:
        TempestLogParser(tm, source, status_filters=["OK"]).parse()
    names = [t.test_name for t in tm.get_tests_for_class(SERVERS)]
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
    test = next(t for t in tm.get_tests_for_class(cls) if t.test_name == name)
    return [runs.index(r) + 1 for r in runs if r in test.results]


def test_trending_runs(tmp_path):
    tm, runs = _parse_trending(tmp_path)
    assert sorted(tm.get_executions()) == runs
    assert [tm.get_summary_for_execution(r).total for r in runs] == [26, 24, 29, 32]
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
    results = [_result(tm, SERVERS, "test_update_server_name_in_stop_state", r).result
               for r in runs]
    assert results == ["FAIL", "FAIL", "OK", "OK"]


def test_log_summary_only_for_its_own_run(tmp_path, caplog):
    tm = TestsManager()
    for name in TRENDING_RUNS[:2]:
        shutil.copy(os.path.join(DATA_DIR, "trending", name), tmp_path / name)
    with caplog.at_level("INFO", logger="tempest_parser"):
        for name in TRENDING_RUNS[:2]:
            with open(tmp_path / name) as source:
                TempestLogParser(tm, source).parse()
    lines = [r.getMessage() for r in caplog.records if r.getMessage().startswith("Tempest testrun")]
    assert len(lines) == 2
    assert "run_1.log: 26 executed" in lines[0]
    assert "run_2.log: 24 executed" in lines[1]


PLUGIN = "neutron_tempest_plugin.api.test_trunk.TrunkTestJSON"
# made-up log in a newer layout: plugin classes, ERROR results, "FAIL: " heads and no summary
NEW_LAYOUT_LOG = f"""\
{PLUGIN}
    test_create_trunk[id-5555]                        OK  0.20
    test_delete_trunk[id-6666]                        ERROR  0.30
    test_trunk_options[id-7777](vlan)                 FAIL  0.40
setUpClass ({PORTS})                                   FAIL  0.00
{PORTS}
    test_list_ports[id-3333]                          OK  0.10

======================================================================
FAIL: {PLUGIN}.test_trunk_options[id-7777](vlan)
----------------------------------------------------------------------
Traceback (most recent call last):
tempest.lib.exceptions.NotFound: Object not found
Details: {{"trunk": "missing, gone"}}

======================================================================
ERROR: setUpClass ({PORTS})
----------------------------------------------------------------------
Traceback (most recent call last):
Details: setup broke
"""


def _parse_text(tmp_path, text, **kw):
    path = tmp_path / "new.log"
    path.write_text(text)
    tm = TestsManager()
    with open(path) as source:
        TempestLogParser(tm, source, **kw).parse()
    return tm, str(path).lower()


def test_log_new_layout(tmp_path):
    tm, run = _parse_text(tmp_path, NEW_LAYOUT_LOG)
    # imported although the log has no "Ran ..." summary
    assert list(tm.get_executions()) == [run]
    assert _result(tm, PLUGIN, "test_create_trunk", run).result == "OK"
    assert _result(tm, PLUGIN, "test_delete_trunk", run).result == "ERROR"
    fail = _result(tm, PLUGIN, "test_trunk_options", run)
    assert fail.result == "FAIL"
    assert tm.get_tests_for_class(PLUGIN)[2].test_options == "(vlan)"
    # a traceback line that starts with "tempest." stays in the trace;
    # the message keeps its quotes and commas
    assert "tempest.lib.exceptions.NotFound: Object not found" in fail.trace
    assert fail.message == 'Details: {"trunk": "missing, gone"}\n'


def test_log_setup_class_failure_details(tmp_path):
    text = f"""\
{PORTS}
    test_list_ports[id-3333]                          OK  0.10
setUpClass ({PORTS})                                   FAIL  0.00

======================================================================
ERROR: setUpClass ({PORTS})
----------------------------------------------------------------------
Traceback (most recent call last):
Details: setup broke
"""
    tm, run = _parse_text(tmp_path, text)
    first = tm.get_tests_for_class(PORTS)[0].results[run]
    assert (first.result, first.setup_fail) == ("FAIL", True)
    assert first.message == "Details: setup broke\n"


def test_log_run_name_and_date(tmp_path):
    date = datetime(2026, 1, 2, 3, 4, tzinfo=UTC)
    tm, _ = _parse_text(tmp_path, NEW_LAYOUT_LOG, run_name="nightly", run_date=date)
    assert list(tm.get_executions()) == ["nightly"]
    assert tm.executions["nightly"].date == date
