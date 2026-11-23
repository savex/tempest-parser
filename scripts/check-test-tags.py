#!/usr/bin/env python3
"""Every test has exactly one tag: smoke, functional or integration.

The tag comes from the folder the test lives in (tests/smoke, tests/functional,
tests/integration); tests/conftest.py adds it as a pytest marker. Tests anywhere
else, or with more than one tag marker, fail this check. Prints the count per tag.
"""
import os
import subprocess
import sys

TAGS = ("smoke", "functional", "integration")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

PLUGIN = '''
import json, os
TAGS = %r
def pytest_collection_finish(session):
    rows = [[item.nodeid, [m.name for m in item.iter_markers() if m.name in TAGS]]
            for item in session.items]
    with open(os.environ["TAG_REPORT"], "w") as f:
        json.dump(rows, f)
''' % (TAGS,)


def main():
    import json
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        with open(os.path.join(tmp, "tag_report_plugin.py"), "w") as f:
            f.write(PLUGIN)
        report = os.path.join(tmp, "report.json")
        env = dict(os.environ, TAG_REPORT=report,
                   PYTHONPATH=os.pathsep.join(filter(None, [tmp, os.environ.get("PYTHONPATH")])))
        result = subprocess.run(
            [sys.executable, "-m", "pytest", "--collect-only", "-q", "-p", "tag_report_plugin"],
            cwd=ROOT, env=env, capture_output=True, text=True)
        if result.returncode != 0:
            sys.stderr.write(result.stdout + result.stderr)
            return 1
        with open(report) as f:
            rows = json.load(f)

    count = dict.fromkeys(TAGS, 0)
    bad = []
    for nodeid, tags in rows:
        folder = nodeid.split("/")[1] if nodeid.startswith("tests/") else ""
        if len(tags) != 1:
            bad.append("{}: {} tags {}, expected exactly 1".format(nodeid, len(tags), tags))
        elif folder != tags[0]:
            bad.append("{}: tag '{}' outside tests/{}/".format(nodeid, tags[0], tags[0]))
        else:
            count[tags[0]] += 1
    for line in bad:
        print("check-test-tags:", line, file=sys.stderr)
    for tag in TAGS:
        print("{:<12} {}".format(tag, count[tag]))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
