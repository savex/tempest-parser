import io
import os
import shutil
from datetime import UTC, datetime

import pytest

from tempest_parser.const import REQUIRED_RUN
from tempest_parser.manager import importers
from tempest_parser.manager.importers import CSVImporter, JSONImporter, SubunitImporter, XMLImporter
from tempest_parser.manager.models import file_date, format_seconds, parse_seconds
from tempest_parser.manager.test_manager import TestsManager
from tempest_parser.parser.tempest_log_parser import TempestLogParser
from tempest_parser.reports.csv_reporter import CSVReporter

from ..conftest import DATA_DIR, PORTS, SERVERS


def _import(cls, path, mode="rt", **kw):
    tm = TestsManager()
    with open(path, mode) as source:
        cls(tm, source, **kw).parse()
    return tm


def _results(tm, run):
    """{(class, test): Result} for one run."""
    return {
        (cls, t.test_name): t.results[run]
        for cls, tests in tm.tests.items()
        for t in tests if run in t.results
    }


def _statuses(tm, run):
    return {key: r.result for key, r in _results(tm, run).items()}


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
    assert "AssertionError: 1 != 2 <server>" in results[(SERVERS, "test_delete_server")].trace
    assert "<ports>" in results[(PORTS, "test_list_ports")].message
    assert results[(SERVERS, "test_create_server")].time == 1.5
    test = tm.get_tests_for_class(SERVERS)[0]
    assert (test.uuid, test.tags) == ("id-1111", ["smoke"])
    assert path in tm.get_executions()
    assert tm.executions[path].date == file_date(path)


def test_xml_status_filter(data_file):
    path = data_file("tempest.xml")
    tm = _import(XMLImporter, path, status_filters=["OK"])
    assert set(_statuses(tm, path).values()) == {"FAIL", "SKIP"}


@pytest.mark.parametrize("times, expected", [
    # any decimal point: seconds
    (("1.5", "2"), 1.5),
    # whole numbers only: milliseconds
    (("1500", "2000"), 1.5),
])
def test_xml_time_unit(tmp_path, times, expected):
    path = tmp_path / "times.xml"
    path.write_text(
        '<testsuite>'
        f'<testcase classname="{SERVERS}" name="test_create_server" time="{times[0]}"/>'
        f'<testcase classname="{SERVERS}" name="test_delete_server" time="{times[1]}"/>'
        '</testsuite>')
    tm = _import(XMLImporter, str(path))
    assert _results(tm, str(path))[(SERVERS, "test_create_server")].time == expected


def test_xml_run_name_and_date(data_file):
    date = datetime(2026, 1, 2, tzinfo=UTC)
    tm = _import(XMLImporter, data_file("tempest.xml"), run_name="nightly", run_date=date)
    assert list(tm.get_executions()) == ["nightly"]
    assert tm.executions["nightly"].date == date


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
    assert dns.result == "FAIL"
    assert "timed out waiting for the condition" in dns.message
    storage = "[sig-storage] PersistentVolumes should be mountable [Slow]"
    assert results[(suite, storage)].result == "SKIP"
    assert len(results) == 3


def test_k8s_slow_extract():
    reason = ('Unexpected error:\n    <*errors.errorString | 0xc0>: {\n'
              '        s: "timed out",\n    }\n')
    assert importers.k8s_slow_extract(reason) == ("timed out", "")
    assert importers.k8s_slow_extract("plain text\nline") == ("", "plain text\nline")


def test_k8s_slow_extract_not_to_have_occurred():
    # the line before "not to have occurred" is the message (it was added as bytes and broke
    # the join with a TypeError)
    reason = "Expected error:\n    <*errors.StatusError | 0xc1>: pods not ready\n" \
             "    not to have occurred\n"
    message = "<*errors.StatusError | 0xc1>: pods not ready"
    assert importers.k8s_slow_extract(reason) == (message, "")


def test_remove_control_chars():
    assert importers.remove_control_chars("a\x00b\x1fc\x7fd\te") == "abcde"


def test_file_date(data_file):
    path = data_file("tempest.xml")
    os.utime(path, (0, 86400))
    assert file_date(path) == datetime(1970, 1, 2, tzinfo=UTC)
    with open(path) as f:
        assert file_date(f) == datetime(1970, 1, 2, tzinfo=UTC)
    # a stream with no file behind it is dated now
    assert file_date(io.StringIO("x")).tzinfo is UTC


@pytest.mark.parametrize("value, expected", [
    ("1.5", 1.5), ("1.50s", 1.5), (" 2 s ", 2.0), (3, 3.0), (0.25, 0.25),
    ("", None), ("n/a", None), (None, None),
])
def test_parse_seconds(value, expected):
    assert parse_seconds(value) == expected


@pytest.mark.parametrize("seconds, expected", [
    (None, ""), (0.0, "0.00s"), (1.5, "1.50s"), (59.994, "59.99s"), (60.0, "1m 00s"),
    (125.4, "2m 05s"), (3599.6, "1h 00m"), (3725.0, "1h 02m"),
])
def test_format_seconds(seconds, expected):
    assert format_seconds(seconds) == expected


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
    assert fail.message == "AssertionError: 1 != 2"
    assert fail.trace.startswith("Traceback")
    assert fail.time == 0.5


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
    assert _import(CSVImporter, str(path)).tests == {}


# Subunit

def test_subunit(subunit_file):
    tm = _import(SubunitImporter, subunit_file, mode="rb")
    run = next(iter(tm.get_executions()))
    # named after the file only; the date is kept apart
    assert run == subunit_file
    assert tm.executions[run].date == file_date(subunit_file)
    assert _statuses(tm, run) == {
        (SERVERS, "test_create_server"): "OK",
        (SERVERS, "test_delete_server"): "FAIL",
        (SERVERS, "test_reboot_server"): "FAIL",
        (PORTS, "test_list_ports"): "SKIP",
        (PORTS, "test_update_port"): "X_FAIL",
        (PORTS, "test_create_port"): "OK",
    }
    results = _results(tm, run)
    assert results[(SERVERS, "test_delete_server")].trace == "Traceback: boom"
    assert results[(PORTS, "test_list_ports")].message == "ports <disabled>"
    assert results[(SERVERS, "test_create_server")].time == pytest.approx(1.5)


def test_subunit_status_filter(subunit_file):
    tm = _import(SubunitImporter, subunit_file, mode="rb", status_filters=["OK", "FAIL"])
    run = next(iter(tm.get_executions()))
    assert sorted(_statuses(tm, run).values()) == ["SKIP", "X_FAIL"]


def test_subunit_run_name_and_date(subunit_file):
    date = datetime(2026, 1, 2, tzinfo=UTC)
    tm = _import(SubunitImporter, subunit_file, mode="rb", run_name="nightly", run_date=date)
    assert tm.executions["nightly"].date == date
    assert len(_statuses(tm, "nightly")) == 6


@pytest.mark.parametrize("status, expected", [
    ("success", "OK"), ("failure", "FAIL"), ("error", "ERROR"), ("skip", "SKIP"),
    ("xfail", "X_FAIL"), ("uxsuccess", "X_OK"),
])
def test_subunit_status_map(status, expected):
    assert importers.TParserResult._parse_status(status) == expected


def _trending(tmp_path, required=None):
    """The four trending sample runs (and a baseline list) in one TestsManager."""
    tm = TestsManager()
    if required:
        tm.add_required(required)
    for number in range(1, 5):
        target = tmp_path / f"run_{number}.log"
        shutil.copy(os.path.join(DATA_DIR, "trending", f"run_{number}.log"), target)
        os.utime(target, (0, 86400 * number))
        with open(target, encoding="utf-8") as source:
            TempestLogParser(tm, source).parse()
    return tm


def _by_file_name(tm):
    """{(file name, class, test, options): (status, message)}, plus each run's date."""
    results = {(os.path.basename(run), cls, t.test_name, t.test_options): (r.result, r.message)
               for cls, tests in tm.tests.items() for t in tests
               for run, r in t.results.items()}
    dates = {os.path.basename(e.name): e.date for e in tm.executions.values()}
    return results, dates


@pytest.mark.parametrize("detailed", [False, True])
def test_csv_own_all_runs(tmp_path, detailed):
    tm = _trending(tmp_path)
    exported = str(tmp_path / "export.csv")
    CSVReporter(tm).generate_to_file(exported, detailed=detailed)
    imported = _import(CSVImporter, exported)

    names = [e.name for e in imported.get_sorted_executions()]
    if detailed:
        # the file name column names the runs
        assert names == ["run_1.log", "run_2.log", "run_3.log", "run_4.log"]
    else:
        assert names == [f"{exported} #{n}" for n in range(1, 5)]
    # dates come from the header
    assert [e.date for e in imported.get_sorted_executions()] == \
        [e.date for e in tm.get_sorted_executions()]
    assert [imported.get_summary_for_execution(n).total for n in names] == [26, 24, 29, 32]
    if detailed:
        expected, _ = _by_file_name(tm)
        got, _ = _by_file_name(imported)
        # messages of failures also hold the trace; statuses match exactly
        assert {k: v[0] for k, v in got.items()} == {k: v[0] for k, v in expected.items()}
        skips = {k: v[1] for k, v in expected.items() if v[0] == "SKIP"}
        assert skips and all(got[k][1] == m for k, m in skips.items())


def test_csv_own_required_and_options(tmp_path, data_dir):
    tm = _trending(tmp_path, required=os.path.join(data_dir, "baseline.list"))
    tm.add_result_for_test(tm.get_sorted_executions()[1].name, SERVERS, "test_resize", "",
                           "(flavor)", "FAIL", 1.0, message='said "no", twice')
    exported = str(tmp_path / "export.csv")
    CSVReporter(tm).generate_to_file(exported, detailed=True)
    imported = _import(CSVImporter, exported)

    assert REQUIRED_RUN in imported.executions
    required = {(cls, t.test_name) for cls, tests in imported.tests.items() for t in tests
                if REQUIRED_RUN in t.results}
    assert required == {(SERVERS, "test_create_server"), (SERVERS, "test_delete_server"),
                        (PORTS, "test_list_ports"), (PORTS, "test_not_run")}
    resize = next(t for t in imported.tests[SERVERS] if t.test_name == "test_resize")
    assert resize.test_options == "(flavor)"
    assert next(iter(resize.results.values())).message.startswith('said "no", twice')
