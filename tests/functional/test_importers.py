import os
import re
import time

import pytest

from tempest_parser.manager import importers
from tempest_parser.manager.importers import (
    CSVImporter, JSONImporter, SubunitImporter, XMLImporter)
from tempest_parser.manager.test_manager import TestsManager
from tempest_parser.reports.csv_reporter import CSVReporter

from ..conftest import PORTS, SERVERS


def _import(cls, path, mode="rt", **kw):
    tm = TestsManager()
    with open(path, mode) as source:
        cls(tm, source, **kw).parse()
    return tm


def _results(tm, run):
    """{(class, test): result dict} for one run."""
    return {
        (cls, t["test_name"]): t["results"][run]
        for cls, tests in tm.get_tests_list()["tests"].items()
        for t in tests if run in t["results"]
    }


def _statuses(tm, run):
    return {key: r["result"] for key, r in _results(tm, run).items()}


# XML (tempest)

def test_xml_tempest(data_file):
    path = data_file("tempest.xml")
    tm = _import(XMLImporter, path)
    assert _statuses(tm, path) == {
        (SERVERS, "test_create_server"): "OK",
        (SERVERS, "test_delete_server"): "FAIL",
        (PORTS, "test_list_ports"): "SKIP",
        (PORTS, "test_update_port"): "OK",
    }
    results = _results(tm, path)
    assert "AssertionError: 1 != 2 <server>" in results[(SERVERS, "test_delete_server")]["trace"]
    assert "<ports>" in results[(PORTS, "test_list_ports")]["message"]
    assert results[(SERVERS, "test_create_server")]["time"] == "1.5s"
    test = tm.get_tests_for_class(SERVERS)[0]
    assert (test["uuid"], test["tags"]) == ("id-1111", ["smoke"])
    assert path in tm.get_executions()


def test_xml_status_filter(data_file):
    path = data_file("tempest.xml")
    tm = _import(XMLImporter, path, status_filters=["OK"])
    assert set(_statuses(tm, path).values()) == {"FAIL", "SKIP"}


def test_xml_force_single_names_run(data_file):
    tm = _import(XMLImporter, data_file("tempest.xml"), force_single_execution="folder")
    assert list(tm.get_executions()) == ["folder"]


# XML (raw, k8s)

def test_xml_raw_k8s(data_file):
    path = data_file("k8s.xml")
    tm = _import(XMLImporter, path, use_raw_names=True)
    results = _results(tm, path)
    suite = "Kubernetes e2e suite"
    dns = results[(suite, "[sig-network] DNS should provide DNS for services [Conformance]")]
    assert dns["result"] == "FAIL"
    assert "timed out waiting for the condition" in dns["message"]
    storage = "[sig-storage] PersistentVolumes should be mountable [Slow]"
    assert results[(suite, storage)]["result"] == "SKIP"
    assert len(results) == 3


def test_k8s_slow_extract():
    reason = ('Unexpected error:\n    <*errors.errorString | 0xc0>: {\n'
              '        s: "timed out",\n    }\n')
    assert importers.k8s_slow_extract(reason) == ("timed out", "")
    assert importers.k8s_slow_extract("plain text\nline") == ("", "plain text\nline")


def test_remove_control_chars():
    assert importers.remove_control_chars("a\x00b\x1fc\x7fd\te") == "abcde"


def test_get_date_from_source(data_file):
    path = data_file("tempest.xml")
    os.utime(path, (0, 86400))
    date, struct = importers.get_date_from_source(path)
    assert date == "02/01/1970 00:00 GMT"
    assert time.mktime(struct) - time.mktime(time.gmtime(0)) == 86400
    with open(path) as f:
        assert importers.get_date_from_source(f)[0] == date


# JSON (Rally)

def test_json_rally(data_file):
    path = data_file("rally.json")
    tm = _import(JSONImporter, path)
    assert _statuses(tm, path) == {
        (SERVERS, "test_create_server"): "OK",
        (SERVERS, "test_delete_server"): "FAIL",
        (PORTS, "test_list_ports"): "SKIP",
    }
    fail = _results(tm, path)[(SERVERS, "test_delete_server")]
    assert fail["message"] == "AssertionError: 1 != 2"
    assert fail["trace"].startswith("Traceback")
    assert fail["time"] == "0.500s"


def test_json_status_filter(data_file):
    path = data_file("rally.json")
    tm = _import(JSONImporter, path, status_filters=["SKIP"])
    assert "SKIP" not in _statuses(tm, path).values()


# CSV

def test_csv_xunit(data_file):
    path = data_file("xunit.csv")
    tm = _import(CSVImporter, path)
    assert _statuses(tm, path) == {
        (SERVERS, "test_create_server"): "OK",
        (SERVERS, "test_delete_server"): "FAIL",
        (PORTS, "test_list_ports"): "SKIP",
    }


def test_csv_status_filter(data_file):
    path = data_file("xunit.csv")
    tm = _import(CSVImporter, path, status_filters=["OK", "SKIP"])
    assert list(_statuses(tm, path).values()) == ["FAIL"]


def test_csv_own_round_trip(data_file, tmp_path):
    source = data_file("tempest.xml")
    exported = str(tmp_path / "export.csv")
    CSVReporter(_import(XMLImporter, source)).generate_to_file(exported)

    tm = _import(CSVImporter, exported)
    assert _statuses(tm, exported) == {
        (SERVERS, "test_create_server"): "OK",
        (SERVERS, "test_delete_server"): "FAIL",
        (PORTS, "test_list_ports"): "SKIP",
        (PORTS, "test_update_port"): "OK",
    }


def test_csv_unknown_layout_imports_nothing(tmp_path):
    path = tmp_path / "other.csv"
    path.write_text("a,b\nc,d\n")
    assert _import(CSVImporter, str(path)).get_tests_list()["tests"] == {}


# Subunit

def test_subunit(subunit_file):
    tm = _import(SubunitImporter, subunit_file, mode="rb")
    run = next(iter(tm.get_executions()))
    assert run.startswith(subunit_file)
    assert _statuses(tm, run) == {
        (SERVERS, "test_create_server"): "OK",
        (SERVERS, "test_delete_server"): "FAIL",
        (SERVERS, "test_reboot_server"): "FAIL",
        (PORTS, "test_list_ports"): "SKIP",
        (PORTS, "test_update_port"): "X_FAIL",
        (PORTS, "test_create_port"): "OK",
    }
    results = _results(tm, run)
    assert results[(SERVERS, "test_delete_server")]["trace"] == "Traceback: boom"
    assert results[(PORTS, "test_list_ports")]["message"] == "ports <disabled>"
    assert re.fullmatch(r"1\.5\d*s", results[(SERVERS, "test_create_server")]["time"])


def test_subunit_status_filter(subunit_file):
    tm = _import(SubunitImporter, subunit_file, mode="rb", status_filters=["OK", "FAIL"])
    run = next(iter(tm.get_executions()))
    assert sorted(_statuses(tm, run).values()) == ["SKIP", "X_FAIL"]


@pytest.mark.parametrize("status, expected", [
    ("success", "OK"), ("failure", "FAIL"), ("error", "ERROR"), ("skip", "SKIP"),
    ("xfail", "X_FAIL"), ("uxsuccess", "X_OK"),
])
def test_subunit_status_map(status, expected):
    assert importers.TParserResult._parse_status(status) == expected
