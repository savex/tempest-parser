"""Build the wheel, install it into a temp dir and run it from there.
Catches templates, config or test lists missing from the package."""
import glob
import os
import shutil
import subprocess
import sys
import zipfile

import pytest

from ..conftest import DATA_DIR

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


@pytest.fixture(scope="module")
def installed(tmp_path_factory):
    pytest.importorskip("build")
    # build from a copy of the source files, so stale build/ or *.egg-info folders can't leak in
    src = tmp_path_factory.mktemp("src")
    files = subprocess.run(["git", "ls-files", "--cached", "--others", "--exclude-standard"],
                           cwd=ROOT, check=True, capture_output=True, text=True).stdout.split()
    for name in files:
        if os.path.isfile(os.path.join(ROOT, name)):
            os.makedirs(os.path.join(str(src), os.path.dirname(name)), exist_ok=True)
            shutil.copy2(os.path.join(ROOT, name), os.path.join(str(src), name))
    dist = tmp_path_factory.mktemp("dist")
    subprocess.run([sys.executable, "-m", "build", "--wheel", "--no-isolation",
                    "--outdir", str(dist), str(src)],
                   check=True, capture_output=True, timeout=300)
    wheel, = glob.glob(str(dist / "*.whl"))
    target = tmp_path_factory.mktemp("site")
    subprocess.run([sys.executable, "-m", "pip", "install", "--no-deps", "--no-index",
                    "--target", str(target), wheel],
                   check=True, capture_output=True, timeout=300)
    return wheel, str(target)


def test_wheel_contents(installed):
    wheel, _ = installed
    names = [n for n in zipfile.ZipFile(wheel).namelist() if ".dist-info/" not in n]
    meta = [n for n in zipfile.ZipFile(wheel).namelist() if ".dist-info/" in n]
    for path in ("tempest_parser/etc/tempest-parser.conf",
                 "tempest_parser/res/all_tests_tag_18.list",
                 "tempest_parser/templates/tempest_trending_report.html",
                 "tempest_parser/templates/tempest_errors_report.html"):
        assert path in names
    assert not [n for n in names if not n.startswith("tempest_parser")], \
        "only tempest_parser and its dist-info belong in the wheel"
    entry_points, = [n for n in meta if n.endswith("entry_points.txt")]
    assert "tparser = tempest_parser.tparser:tempest_cli_parser_main" in \
        zipfile.ZipFile(wheel).read(entry_points).decode()


def test_installed_package_runs(installed, tmp_path):
    _, target = installed
    env = dict(os.environ, PYTHONPATH=target)
    code = ("import sys, tempest_parser; "
            "assert tempest_parser.__file__.startswith(sys.argv[1]), tempest_parser.__file__; "
            "from tempest_parser.tparser import tempest_cli_parser_main as m; "
            "sys.argv = sys.argv[1:]; m()")
    html, errors = tmp_path / "r.html", tmp_path / "e.html"
    result = subprocess.run(
        [sys.executable, "-c", code, target, "-i", "-d", "-r", str(html),
         os.path.join(DATA_DIR, "tempest.xml")],
        cwd=str(tmp_path), env=env, capture_output=True, timeout=120)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "test_create_server" in html.read_text()

    result = subprocess.run(
        [sys.executable, "-c", code, target, "-e", str(errors),
         os.path.join(DATA_DIR, "tempest.xml")],
        cwd=str(tmp_path), env=env, capture_output=True, timeout=120)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "AssertionError" in errors.read_text()
