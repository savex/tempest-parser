"""Run the tparser command end to end on each sample format."""
import csv
import os
import shutil
import subprocess
import sys

import pytest

from ..conftest import DATA_DIR, SERVERS, write_subunit

CLI = [sys.executable, "-c",
       "import sys; from tempest_parser.tparser import tempest_cli_parser_main as m; "
       "sys.exit(m())"]


def tparser(*args, stdin=None):
    return subprocess.run(CLI + [str(a) for a in args], input=stdin,
                          capture_output=True, timeout=60)


def _rows(path):
    with open(path) as f:
        return [r for r in csv.reader(f) if r and r[0].isdigit()]


def test_help():
    result = tparser("--help")
    assert result.returncode == 0
    assert b"--html-trending-filename" in result.stdout


@pytest.mark.parametrize("args, name, tests", [
    ([], "tempest.xml", 4),
    (["-f", "r_xml"], "k8s.xml", 3),
    ([], "rally.json", 3),
    ([], "xunit.csv", 3),
    ([], "tempest.log", 3),
])
def test_formats_to_reports(tmp_path, args, name, tests):
    source = tmp_path / name
    shutil.copy(os.path.join(DATA_DIR, name), source)
    html, out = tmp_path / "report.html", tmp_path / "out.csv"
    result = tparser(*args, "-d", "-r", html, "-c", out, source)
    assert result.returncode == 0, result.stdout + result.stderr
    assert len(_rows(out)) == tests
    assert name in html.read_text()


def test_subunit_file_and_pipe(tmp_path):
    path = write_subunit(str(tmp_path / "run.subunit"))
    out = tmp_path / "out.csv"
    assert tparser("-c", out, path).returncode == 0
    assert len(_rows(out)) == 6

    with open(path, "rb") as f:
        result = tparser("-c", out, stdin=f.read())
    assert result.returncode == 0, result.stderr
    assert len(_rows(out)) == 6


def test_errors_report(tmp_path):
    out = tmp_path / "errors.html"
    assert tparser("-e", out, os.path.join(DATA_DIR, "tempest.xml")).returncode == 0
    text = out.read_text()
    assert "AssertionError" in text and "&lt;ports&gt;" in text


def test_folder_without_format(tmp_path):
    for name in ("tempest.xml", "rally.json", "baseline.list"):
        shutil.copy(os.path.join(DATA_DIR, name), tmp_path / name)
    out = tmp_path / "out" / "r.html"
    out.parent.mkdir()
    result = tparser("-d", "-r", out, tmp_path)
    assert result.returncode == 0, result.stdout + result.stderr
    assert b"Skipped 'baseline.list'" in result.stdout
    text = out.read_text()
    assert "tempest.xml" in text and "rally.json" in text


def test_folder_force_single(tmp_path):
    folder = tmp_path / "runs"
    folder.mkdir()
    shutil.copy(os.path.join(DATA_DIR, "tempest.xml"), folder / "a.xml")
    shutil.copy(os.path.join(DATA_DIR, "k8s.xml"), folder / "b.xml")
    out = tmp_path / "out.csv"
    result = tparser("-f", "r_xml", "--force-single", "-c", out, folder)
    assert result.returncode == 0, result.stderr
    assert len(_rows(out)) == 7
    with open(out) as f:
        header = next(csv.reader(f))
    assert len(header) == 4  # number, name, required/added, one run


def test_folder_force_single_detected_xml(tmp_path):
    # without -f, .xml files are read as tempest XML; --force-single applies to them too
    folder = tmp_path / "runs"
    folder.mkdir()
    shutil.copy(os.path.join(DATA_DIR, "tempest.xml"), folder / "a.xml")
    shutil.copy(os.path.join(DATA_DIR, "tempest.xml"), folder / "b.xml")
    out = tmp_path / "out.csv"
    result = tparser("--force-single", "-c", out, folder)
    assert result.returncode == 0, result.stderr
    with open(out) as f:
        header = next(csv.reader(f))
    assert len(header) == 4  # number, name, required/added, one run


def test_omit_status(tmp_path):
    out = tmp_path / "out.csv"
    result = tparser("--omit-status", "OK", "--omit-status", "SKIP", "-c", out,
                     os.path.join(DATA_DIR, "tempest.xml"))
    assert result.returncode == 0
    assert [r[1] for r in _rows(out)] == ["test_delete_server"]


def test_include_required(tmp_path):
    conf = tmp_path / "c.conf"
    conf.write_text("[ParserConfig]\ndefault_test_list={}\ndefault_detailed=false\n".format(
        os.path.join(DATA_DIR, "baseline.list")))
    out, html = tmp_path / "out.csv", tmp_path / "r.html"
    result = tparser("--config-file", conf, "-i", "-c", out, "-r", html,
                     os.path.join(DATA_DIR, "tempest.xml"))
    assert result.returncode == 0, result.stderr
    names = {r[1]: r[2] for r in _rows(out)}
    assert names["test_not_run"] == "R"
    assert names["test_update_port"] == "A"
    assert SERVERS in html.read_text()


@pytest.mark.parametrize("args, message", [
    (["/no/such/path"], b"not exists"),
    (["-e", "x.html", DATA_DIR], b"require single file"),
    ([os.path.join(DATA_DIR, "baseline.list")], b"not supported"),
])
def test_errors_exit_1(tmp_path, args, message):
    result = tparser(*args)
    assert result.returncode == 1
    assert message in result.stdout


def test_unknown_format_exit_2():
    result = tparser("-f", "nope", os.path.join(DATA_DIR, "tempest.xml"))
    assert result.returncode == 2
    assert b"invalid choice: 'nope'" in result.stderr


def test_quiet_prints_nothing_on_success(tmp_path):
    out = tmp_path / "out.csv"
    result = tparser("-q", "-c", out, os.path.join(DATA_DIR, "tempest.xml"))
    assert result.returncode == 0, result.stderr
    assert result.stdout == b""
    assert _rows(out)


def test_quiet_still_prints_errors():
    result = tparser("-q", "/no/such/path")
    assert result.returncode == 1
    assert result.stdout.startswith(b"Error: Supplied path/file not exists")
