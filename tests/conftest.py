"""Shared fixtures. Every test gets exactly one tag from the folder it lives in:
tests/smoke, tests/functional or tests/integration (see scripts/check-test-tags.py)."""
import datetime
import os
import shutil

import pytest

TAGS = ("smoke", "functional", "integration")
DATA_DIR = os.path.join(os.path.dirname(__file__), "data")

SERVERS = "tempest.api.compute.servers.test_servers.ServersTestJSON"
PORTS = "tempest.api.network.test_ports.PortsTestJSON"


def pytest_collection_modifyitems(config, items):
    for item in items:
        parts = os.path.relpath(str(item.fspath), os.path.dirname(__file__)).split(os.sep)
        if parts[0] in TAGS:
            item.add_marker(getattr(pytest.mark, parts[0]))


@pytest.fixture
def data_dir():
    return DATA_DIR


@pytest.fixture
def data_file(tmp_path):
    """Copy a sample file into the test's own temp dir and return its path."""
    def _copy(name):
        target = tmp_path / name
        shutil.copy(os.path.join(DATA_DIR, name), target)
        return str(target)
    return _copy


def write_subunit(path):
    """Write a subunit v2 stream with one test of each status."""
    from subunit import StreamResultToBytes

    start = datetime.datetime(2026, 1, 1, tzinfo=datetime.UTC)
    stop = start + datetime.timedelta(seconds=1.5)
    tests = [
        (SERVERS + ".test_create_server[id-1111,smoke]", "success", None),
        (SERVERS + ".test_delete_server[id-2222]", "fail", ("traceback", "Traceback: boom")),
        (SERVERS + ".test_reboot_server[id-6666]", "fail", ("traceback", "Traceback: error")),
        (PORTS + ".test_list_ports[id-3333]", "skip", ("reason", "ports <disabled>")),
        (PORTS + ".test_update_port[id-4444]", "xfail", ("traceback", "expected")),
        (PORTS + ".test_create_port[id-7777]", "uxsuccess", None),
    ]
    with open(path, "wb") as f:
        out = StreamResultToBytes(f)
        for test_id, status, detail in tests:
            out.status(test_id=test_id, test_status="inprogress", timestamp=start)
            if detail:
                out.status(test_id=test_id, file_name=detail[0],
                           file_bytes=detail[1].encode(), mime_type="text/plain; charset=utf8",
                           eof=True)
            out.status(test_id=test_id, test_status=status, timestamp=stop)
    return path


@pytest.fixture
def subunit_file(tmp_path):
    return write_subunit(str(tmp_path / "run.subunit"))
