"""Run the tparser command end to end on each sample format."""
import csv
import json
import os
import re
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


def test_version():
    result = tparser("--version")
    assert result.returncode == 0
    assert re.fullmatch(rb"tparser \d+\.\d+\S*\r?\n", result.stdout), result.stdout


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
    ([], "stestr.log", 5),
])
def test_formats_to_reports(tmp_path, args, name, tests):
    source = tmp_path / name
    shutil.copy(os.path.join(DATA_DIR, name), source)
    html, out = tmp_path / "report.html", tmp_path / "out.csv"
    result = tparser(*args, "-d", "-r", html, "-c", out, source)
    assert result.returncode == 0, result.stdout + result.stderr
    assert len(_rows(out)) == tests
    assert name in html.read_text()


@pytest.mark.parametrize("layout, marker", [
    (None, '<table class="report">'),
    ("table", '<table class="report">'),
    ("grid", 'role="table"'),
])
def test_html_layout(tmp_path, layout, marker):
    html = tmp_path / "report.html"
    args = ["--html-layout", layout] if layout else []
    result = tparser(*args, "-r", html, os.path.join(DATA_DIR, "trending"))
    assert result.returncode == 0, result.stdout + result.stderr
    text = html.read_text(encoding="utf-8")
    assert marker in text
    assert "test_create_server_with_admin_password" in text


@pytest.mark.parametrize("layout, marker", [
    (None, '<table class="report">'),
    ("grid", '<details class="group">'),
])
def test_errors_report_layout(tmp_path, layout, marker):
    out = tmp_path / "errors.html"
    args = ["--html-layout", layout] if layout else []
    result = tparser(*args, "-e", out, os.path.join(DATA_DIR, "tempest.xml"))
    assert result.returncode == 0, result.stdout + result.stderr
    text = out.read_text(encoding="utf-8")
    assert marker in text
    assert "AssertionError" in text and "&lt;ports&gt;" in text


@pytest.mark.parametrize("args, seconds", [([], 0.003), (["--xml-time-unit", "s"], 3.0)])
def test_xml_time_unit(tmp_path, args, seconds):
    source = tmp_path / "whole.xml"
    source.write_text(f'<testsuite><testcase classname="{SERVERS}" name="test_a" time="3"/>'
                      '</testsuite>', encoding="utf-8")
    js = tmp_path / "summary.json"
    result = tparser(*args, "-j", js, source)
    assert result.returncode == 0, result.stdout + result.stderr
    (run,) = json.loads(js.read_text(encoding="utf-8"))["runs"]
    assert run["time"] == seconds


def test_html_layout_unknown(tmp_path):
    result = tparser("--html-layout", "cards", "-r", tmp_path / "r.html",
                     os.path.join(DATA_DIR, "tempest.xml"))
    assert result.returncode != 0
    assert b"invalid choice" in result.stderr
    assert not (tmp_path / "r.html").exists()


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


def test_run_name_and_date(tmp_path):
    out = tmp_path / "r.html"
    result = tparser("--run-name", "nightly", "--run-date", "2026-01-02T03:04",
                     "-d", "-r", out, os.path.join(DATA_DIR, "tempest.xml"))
    assert result.returncode == 0, result.stdout + result.stderr
    text = out.read_text()
    assert "nightly" in text and "02/01/2026 03:04 GMT" in text
    assert "tempest.xml" not in text


def test_run_name_needs_single_file(tmp_path):
    shutil.copy(os.path.join(DATA_DIR, "tempest.xml"), tmp_path / "tempest.xml")
    result = tparser("--run-name", "nightly", "-c", tmp_path / "out.csv", tmp_path)
    assert result.returncode == 1
    assert b"--run-name and --run-date need a single file" in result.stdout


def test_run_date_invalid():
    result = tparser("--run-date", "yesterday", os.path.join(DATA_DIR, "tempest.xml"))
    assert result.returncode == 2
    assert b"not an ISO 8601 date" in result.stderr


def test_json_summary_and_fail_on(tmp_path):
    out = tmp_path / "summary.json"
    source = os.path.join(DATA_DIR, "tempest.xml")
    result = tparser("-j", out, "--fail-on", "fail", source)
    assert result.returncode == 3, result.stdout + result.stderr
    assert b"1 test result(s) with status FAIL" in result.stdout
    assert b"test_delete_server FAIL" in result.stdout
    (run,) = json.loads(out.read_text())["runs"]
    assert (run["total"], run["fail"]) == (4, 1)

    assert tparser("--fail-on", "ERROR", source).returncode == 0
    # left out with --omit-status, so not counted
    assert tparser("--omit-status", "FAIL", "--fail-on", "FAIL", source).returncode == 0


# Windows before Python 3.15 opens files in the locale's code page unless told otherwise;
# an ASCII locale without UTF-8 mode stands in for it on Linux and macOS
ASCII_LOCALE = {"PYTHONUTF8": "0", "PYTHONCOERCECLOCALE": "0", "LC_ALL": "C", "LANG": "C"}


@pytest.mark.parametrize("args, name", [([], "unicode.log"), (["-f", "log"], None)])
def test_non_ascii_results_without_utf8_locale(tmp_path, args, name):
    log = (f"{SERVERS}\n"
           "    test_naïve_ünïcode[id-1111]                   FAIL  0.50\n"
           "\n" + "=" * 70 + "\n"
           f"{SERVERS}.test_naïve_ünïcode[id-1111]\n" + "-" * 70 + "\n"
           "Details: ожидалось 1 → получено 2\n")
    html, out, js = tmp_path / "r.html", tmp_path / "out.csv", tmp_path / "s.json"
    command = CLI + args + ["-d", "-r", str(html), "-c", str(out), "-j", str(js),
                            "--fail-on", "FAIL"]
    if name:
        source = tmp_path / name
        source.write_text(log, encoding="utf-8")
        command.append(str(source))
    result = subprocess.run(command, input=None if name else log.encode(),
                            env=dict(os.environ, **ASCII_LOCALE), capture_output=True,
                            timeout=60)
    assert result.returncode == 3, result.stdout + result.stderr
    assert b"Traceback" not in result.stderr
    assert "ожидалось 1 → получено 2" in html.read_text(encoding="utf-8")
    assert "test_naïve_ünïcode" in out.read_text(encoding="utf-8")
    assert json.loads(js.read_text(encoding="utf-8"))["runs"][0]["fail"] == 1
