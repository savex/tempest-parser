"""scripts/version.sh, run in a throwaway git repository with its own setup.py and changelog.md."""
import os
import shutil
import subprocess

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
# /bin/bash (3.2 on macOS) and the bash on PATH, once each even when both are the same binary
SHELLS = {}
for _shell in ("/bin/bash", shutil.which("bash")):
    if _shell and os.path.exists(_shell):
        SHELLS.setdefault(os.path.realpath(_shell), _shell)
SHELLS = sorted(SHELLS.values())

SETUP_PY = '''from setuptools import setup

setup(
    name="TempestParser",
    version="{}",
    license="Apache Licence, version 2",
)
'''

CHANGELOG = '''# Changelog

## [Unreleased]

### Fixed
- Something.
'''


@pytest.fixture(params=SHELLS)
def repo(request, tmp_path):
    (tmp_path / "scripts").mkdir()
    shutil.copy(os.path.join(ROOT, "scripts", "version.sh"), tmp_path / "scripts")
    (tmp_path / "setup.py").write_text(SETUP_PY.format("0.2.81"))
    (tmp_path / "changelog.md").write_text(CHANGELOG)
    env = dict(os.environ, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@example.com",
               GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@example.com")

    def git(*args):
        subprocess.run(["git", *args], cwd=tmp_path, env=env, check=True, capture_output=True)

    def run(*args):
        result = subprocess.run([request.param, "scripts/version.sh", *args], cwd=tmp_path,
                                capture_output=True, text=True, timeout=30)
        return result.returncode, result.stdout.strip(), result.stderr.strip()

    git("init", "-q")
    git("add", "-A")
    git("commit", "-q", "-m", "init")
    run.git = git
    run.path = tmp_path
    return run


def test_reads_versions(repo):
    assert repo("setup")[1] == "0.2.81"
    assert repo("latest-tag")[1] == ""
    assert repo("changelog-version")[1] == ""
    assert repo("highest")[1] == "0.2.81"
    code, out, _ = repo("current")
    assert code == 0 and out.startswith("0.2.81+g")


def test_ignores_non_semver_tags(repo):
    repo.git("tag", "v0.1")
    repo.git("tag", "v0.2.4RC")
    repo.git("tag", "v0.2.55")
    assert repo("latest-tag")[1] == "v0.2.55"
    assert repo("nearest-tag")[1] == "v0.2.55"
    assert repo("current")[1] == "0.2.55"


def test_versions_out_of_sync(repo):
    repo.git("tag", "v0.2.55")
    code, out, _ = repo("versions")
    assert code == 1
    assert "out of sync: setup.py 0.2.81 is not the latest tag v0.2.55" in out


@pytest.mark.parametrize("a, b, expected", [
    ("0.3.0", "0.2.81", "1"), ("0.2.9", "0.2.10", "-1"), ("1.0.0", "1.0.0", "0"),
    ("1.0.0-rc.1", "1.0.0", "-1"), ("1.0.0-rc.2", "1.0.0-rc.10", "-1"),
    ("1.0.0-alpha", "1.0.0-1", "1"),
])
def test_compare(repo, a, b, expected):
    assert repo("compare", a, b)[1] == expected


@pytest.mark.parametrize("version, ok", [
    ("0.3.0", True), ("1.0.0-rc.1", True), ("0.2", False), ("v0.3.0", False), ("01.0.0", False),
])
def test_validate(repo, version, ok):
    assert (repo("validate", version)[0] == 0) is ok


def test_next(repo):
    assert repo("next", "patch")[1] == "0.2.82"
    assert repo("next", "minor")[1] == "0.3.0"
    assert repo("next", "major")[1] == "1.0.0"
    assert repo("next", "minor", "rc.1")[1] == "0.3.0-rc.1"


def test_next_after_prerelease_finalizes(repo):
    repo("set", "0.3.0-rc.1")
    assert repo("next", "minor")[1] == "0.3.0"
    assert repo("next", "patch")[1] == "0.3.0"


def test_newer(repo):
    assert repo("newer", "0.3.0")[0] == 0
    code, _, err = repo("newer", "0.2.81")
    assert code == 1 and "not newer" in err
    repo.git("tag", "v0.4.0")
    assert "already exists" in repo("newer", "0.4.0")[2]


def test_set_keeps_the_rest_of_setup_py(repo):
    assert repo("set", "0.3.0") == (0, "0.3.0", "")
    text = (repo.path / "setup.py").read_text()
    assert text == SETUP_PY.format("0.3.0")
    assert repo("set", "nope")[0] == 1


def test_changelog_release(repo):
    assert repo("changelog", "0.3.0", "2026-11-23")[1] == "0.3.0"
    text = (repo.path / "changelog.md").read_text()
    assert "## [Unreleased]\n\n## [0.3.0] - 2026-11-23\n\n### Fixed\n- Something." in text
    assert text.rstrip().endswith(
        "[Unreleased]: https://github.com/savex/tempest-parser/compare/v0.3.0...HEAD\n"
        "[0.3.0]: https://github.com/savex/tempest-parser/releases/tag/v0.3.0")
    assert repo("changelog-version")[1] == "0.3.0"
    assert "already has" in repo("changelog", "0.3.0")[2]

    repo("changelog", "0.3.1", "2026-12-01")
    text = (repo.path / "changelog.md").read_text()
    assert text.count("[Unreleased]: ") == 1
    assert "[Unreleased]: https://github.com/savex/tempest-parser/compare/v0.3.1...HEAD" in text
    assert "[0.3.0]: https://github.com/savex/tempest-parser/releases/tag/v0.3.0" in text


def test_check(repo):
    assert repo("check")[0] == 0
    assert repo("check", "v0.2.81")[0] == 0
    assert "does not match" in repo("check", "v0.3.0")[2]
    repo.git("tag", "v0.3.0")
    assert "older than latest tag" in repo("check")[2]


def test_in_sync_after_release(repo):
    repo("set", "0.3.0")
    repo("changelog", "0.3.0", "2026-11-23")
    repo.git("commit", "-qam", "Release v0.3.0")
    repo.git("tag", "v0.3.0")
    code, out, _ = repo("versions")
    assert code == 0 and out.endswith("in sync")
    assert repo("current")[1] == "0.3.0"
    (repo.path / "README").write_text("x")
    repo.git("add", "README")
    repo.git("commit", "-qm", "more")
    assert repo("current")[1].startswith("0.3.0+1.g")


def test_current_marks_dirty_tree(repo):
    repo.git("tag", "v0.2.81")
    (repo.path / "setup.py").write_text(SETUP_PY.format("0.2.81") + "# edit\n")
    assert repo("current")[1] == "0.2.81+dirty"


def test_notes(repo):
    repo("changelog", "0.3.0", "2026-11-23")
    (repo.path / "changelog.md").write_text(
        (repo.path / "changelog.md").read_text().replace(
            "## [Unreleased]\n", "## [Unreleased]\n\n### Added\n- Later.\n"))
    repo("changelog", "0.3.1", "2026-12-01")
    assert repo("notes", "0.3.0") == (0, "### Fixed\n- Something.", "")
    assert repo("notes", "0.3.1")[1] == "### Added\n- Later."
    code, _, err = repo("notes", "0.4.0")
    assert code == 1 and "no 0.4.0 section" in err
