import random

import pytest

from tempest_parser.manager.test_manager import TestsManager

from ..conftest import PORTS, SERVERS


@pytest.mark.parametrize("name, expected", [
    (SERVERS + ".test_create_server[id-1111,smoke]",
     (SERVERS, "test_create_server", "id-1111", "", ["smoke"])),
    (SERVERS + ".test_delete_server[id-2222]",
     (SERVERS, "test_delete_server", "id-2222", "", [])),
    (SERVERS + ".test_ipv6[id-3333](ipv6)",
     (SERVERS, "test_ipv6", "id-3333", "(ipv6)", [])),
    (SERVERS + ".test_plain",
     (SERVERS, "test_plain", "", "", [])),
    ("setUpClass (" + SERVERS + ")",
     (SERVERS, "", "", "", [])),
    ("cvp_checks.tests.test_mtu.test_mtu",
     ("cvp_checks.tests.test_mtu", "test_mtu", "", "", [])),
    ("other.module.Class.test_x", ("", "", "", "", [])),
])
def test_split_test_name(name, expected):
    assert TestsManager.split_test_name(name) == expected


def test_split_test_name_raw_keeps_brackets():
    _, test, uuid, options, _ = TestsManager.split_test_name(
        SERVERS + ".test_create_server[id-1111,smoke]", raw_names=True)
    assert (test, uuid, options) == ("test_create_server[id-1111,smoke]", "", "")


def test_split_test_name_from_speed():
    assert TestsManager.split_test_name_from_speed(
        SERVERS + ".test_create_server[id-1111,smoke] 1.50"
    ) == (SERVERS, "test_create_server", "")


def _add(tm, run, test, result, uuid="", options="", time="1.0s", **kw):
    tm.add_result_for_test(run, SERVERS, test, uuid, options, result, time, **kw)


def test_new_test_keeps_uuid_and_options():
    tm = TestsManager()
    _add(tm, "run1", "test_ipv6", "OK", uuid="id-3333", options="(ipv6)")
    item = tm.get_tests_for_class(SERVERS)[0]
    assert item["uuid"] == "id-3333"
    assert item["test_options"] == "(ipv6)"


def test_same_test_from_two_runs_is_one_row():
    tm = TestsManager()
    _add(tm, "run1", "test_ipv6", "OK", uuid="id-3333", options="(ipv6)")
    _add(tm, "run2", "test_ipv6", "FAIL", uuid="id-3333", options="(ipv6)")
    tests = tm.get_tests_for_class(SERVERS)
    assert len(tests) == 1
    assert tests[0]["results"]["run1"]["result"] == "OK"
    assert tests[0]["results"]["run2"]["result"] == "FAIL"


def test_options_variants_are_separate_rows():
    tm = TestsManager()
    _add(tm, "run1", "test_ip", "OK", options="(ipv4)")
    _add(tm, "run1", "test_ip", "FAIL", options="(ipv6)")
    assert len(tm.get_tests_for_class(SERVERS)) == 2


def test_second_result_in_same_run_cascades_message():
    tm = TestsManager()
    _add(tm, "run1", "test_a", "FAIL", message="first")
    _add(tm, "run1", "test_a", "OK", message="second")
    result = tm.get_tests_for_class(SERVERS)[0]["results"]["run1"]
    assert result["result"] == "OK"
    assert "FAIL: first" in result["message"]
    assert "OK: second" in result["message"]


def test_setupclass_failure_marks_class():
    tm = TestsManager()
    _add(tm, "run1", "test_a", "OK")
    tm.add_result_for_test("run1", "setUpClass", SERVERS, "", "", "FAIL", "0s")
    result = tm.get_tests_for_class(SERVERS)[0]["results"]["run1"]
    assert result["result"] == "FAIL"
    assert result["setup_fail"] is True


def test_add_fail_data_for_test():
    tm = TestsManager()
    _add(tm, "run1", "test_a", "FAIL")
    tm.add_fail_data_for_test("run1", SERVERS, "test_a", "", "trace", "msg")
    result = tm.get_tests_for_class(SERVERS)[0]["results"]["run1"]
    assert (result["trace"], result["message"]) == ("trace", "msg")


def test_add_required_preloads_baseline(data_dir):
    tm = TestsManager()
    tm.add_required(data_dir + "/baseline.list")
    assert "required" in tm.get_executions()
    ports = tm.get_tests_for_class(PORTS)
    assert [t["test_name"] for t in ports] == ["test_list_ports", "test_not_run"]
    assert ports[0]["uuid"] == "id-3333"
    assert ports[0]["results"]["required"]["result"] == "R"


def test_summary_for_execution():
    tm = TestsManager()
    _add(tm, "run1", "test_a", "OK", time="1.5s")
    _add(tm, "run1", "test_b", "FAIL", time="0.5s")
    _add(tm, "run1", "test_c", "SKIP", time="0s")
    assert tm.get_summary_for_execution("run1") == (2.0, 3, 1, 1, 1)


def test_class_errors_and_totals():
    tm = TestsManager()
    tm.add_execution({"execution_name": "run1", "execution_date": "d"}, unixtime=1)
    _add(tm, "run1", "test_a", "OK")
    assert not tm.is_class_has_errors(SERVERS)
    _add(tm, "run1", "test_b", "FAIL")
    assert tm.is_class_has_errors(SERVERS)
    assert tm.get_totals_as_string_for_class(SERVERS) == "2/1, "


def _linear_lookup(tests, test_name, uuid, test_options):
    """The lookup rule as a plain scan, to check the index against."""
    for position, test in enumerate(tests):
        if test["test_name"] == test_name and test["test_options"] == test_options:
            if uuid == '' or test["uuid"] == '' or test["uuid"] == uuid:
                return position
    return -1


def test_lookup_index_matches_linear_scan():
    rng = random.Random(7)
    tm = TestsManager()
    names = ["test_%d" % i for i in range(30)]
    options = ["", "(ipv4)", "(ipv6)"]
    uuids = ["", "id-1", "id-2", None]
    for run in range(4):
        for _ in range(200):
            _add(tm, "run%d" % run, rng.choice(names), "OK",
                 uuid=rng.choice(uuids[:3]), options=rng.choice(options))
    tests = tm.get_tests_for_class(SERVERS)
    for name in names + ["test_missing"]:
        for option in options + [None]:
            for uuid in uuids:
                assert tm.test_name_lookup(SERVERS, name, uuid, option) == \
                    _linear_lookup(tests, name, uuid, option)
        bare = next((i for i, t in enumerate(tests) if t["test_name"] == name), -1)
        assert tm.test_name_lookup_bare(SERVERS, name) == bare
    assert tm.test_name_lookup("no.such.Class", "test_0", "", "") == -1
    assert tm.test_name_lookup_bare("no.such.Class", "test_0") == -1


def test_lookup_index_follows_outside_changes(data_dir):
    tm = TestsManager()
    _add(tm, "run1", "test_a", "OK")
    assert tm.test_name_lookup(SERVERS, "test_b", "", "") == -1
    # code that appends to tests_list directly
    tm.get_tests_list()["tests"][SERVERS].append(
        {"test_name": "test_b", "uuid": "", "test_options": "", "tags": [], "results": {}})
    assert tm.test_name_lookup(SERVERS, "test_b", "", "") == 1
    # add_required replaces the whole tests dict
    tm.add_required(data_dir + "/baseline.list")
    assert tm.test_name_lookup(SERVERS, "test_a", "", "") == -1
    assert tm.test_name_lookup(SERVERS, "test_delete_server", "id-2222", "") == 1
