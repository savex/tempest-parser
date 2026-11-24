"""Parser for tempest / testr / stestr console logs (`.log` input).

The log is read line by line. Two layouts are understood, also mixed in one file.

The testr layout, a class line followed by its tests:

    tempest.api.compute.servers.test_servers.ServersTestJSON        <- class line
        test_create_server[id-1111,smoke]            OK  1.50       <- test line
        test_ipv6[id-3333](ipv6)                     FAIL  0.50     <- options in brackets
    setUpClass (tempest.api.network.test_ports                      <- class setup failed,
        PortsTestJSON)                               FAIL  0.00        name wrapped or not

    Slowest 2 tests took 2.00 secs:                                 <- slowest tests,
    tempest.api.compute.servers.test_servers.ServersTestJSON           up to a blank line
        test_create_server[id-1111,smoke]   1.50

The stestr / subunit-trace layout (`tempest run`), one line per test with its worker:

    {0} tempest.api.compute.servers.test_servers.ServersTestJSON.test_create [1.500000s] ... ok
    {1} tempest.api.network.test_ports.PortsTestJSON.test_list_ports ... SKIPPED: reason
    {0} tempest.api.compute.servers.test_servers.ServersTestJSON.test_x [0.5s] ... FAILED

    Captured traceback:                                             <- attachments of the
    ~~~~~~~~~~~~~~~~~~~                                                test above, indented
        Traceback (most recent call last):
        ...

    Slowest Tests:                                                  <- `stestr --slowest`
    Test id                                       Runtime (s)
    --------------------------------------------  -----------
    tempest.api.compute....test_create_server[id-1111,smoke]  1.500

Failure blocks, in both layouts, and the summary:

    ======================================================================
    FAIL: tempest.api.compute.servers.test_servers.ServersTestJSON.test_x[id-2222]
    ----------------------------------------------------------------------  <- failure head
    Traceback (most recent call last):                              <- trace (or Captured
      ...                                                              attachments) up to the
    Details: 1 != 2                                                    next head or summary;
                                                                       Details: lines are
    Ran 3 tests in 2.000s           (stestr: "Ran: 3 tests in ...")    the message

Lines may carry a CI timestamp prefix (`2026-01-01 10:00:00.123456 | `, optionally with a host
`| controller | `), which is removed. A log can hold several runs; they all import into one run
named after the file. The log has no date, so the run is dated by the file's modification time.
"""
import logging
import re
from collections.abc import Iterable
from datetime import datetime
from typing import IO

from tempest_parser.manager.models import file_date, parse_seconds
from tempest_parser.manager.test_manager import TestsManager

# (class, test name, uuid, options)
TestId = tuple[str, str, str, str]

log = logging.getLogger(__name__)

# CI job output: "2026-01-01 10:00:00.123456 | " and an optional "host | "
_PREFIX_RE = re.compile(
    r"^\d{4}-\d\d-\d\d[ T]\d\d:\d\d:\d\d(?:[.,]\d+)?(?:Z|[+-]\d\d:?\d\d)? \|(?: [\w.-]+ \|)? ?")
# a dotted name on a line of its own: tempest.api.compute.servers.test_servers.ServersTestJSON
_CLASS_RE = re.compile(r"^[A-Za-z_]\w*(\.\w+)+$")
# test_name[tags](options) RESULT time; the result and time are optional
_TEST_RE = re.compile(
    r"^(?P<name>test_[^\s\[(]*)(?P<tags>\[[^\]]*\])?(?P<options>\([^)]*\))?"
    r"\s*(?P<result>[A-Z][A-Z_]*)?\s*(?P<time>\d+(\.\d+)?s?)?\s*$")
# setUpClass (tempest.api.x.Class) FAIL 0.00, or with the class name wrapped to the next line
_SETUP_RE = re.compile(r"^(?P<kind>setUpClass|tearDownClass) \((?P<prefix>[^)\s]*)(?P<rest>.*)$")
# stestr: {0} full.test.id [1.500000s] ... ok   /   {1} full.test.id ... SKIPPED: reason
_RESULT_RE = re.compile(
    r"^\{\d+\}\s+(?P<id>(?:setUpClass|tearDownClass) \([^)]*\)|\S+)"
    r"(?:\s+\[(?P<time>\d+(?:\.\d+)?)s[^\]]*\])?\s+\.\.\.\s+(?P<status>[A-Za-z_]+)"
    r"(?::\s*(?P<reason>.*))?$")
# a full test id: class.test_name[tags](options)
_ID_RE = re.compile(
    r"^(?P<cls>[A-Za-z_][\w.]*?)\.(?P<name>[^.\[\]()\s]+)(?P<tags>\[[^\]]*\])?(?P<options>\(.*\))?$")
_SLOWEST_RE = re.compile(r"^Slowest \d+ tests? took")
_SLOWEST_TABLE_ROW_RE = re.compile(r"^(?P<id>\S+)\s+\d+(?:\.\d+)?$")
_SUMMARY_RE = re.compile(r"^Ran:? \d+ tests? in ")
# failure head prefixes written by some runners: "FAIL: tempest...."
_HEAD_PREFIX_RE = re.compile(r"^(FAIL|ERROR): ")
_CAPTURED_RE = re.compile(r"^Captured (?P<name>[\w-]+):$")

# stestr result words; anything else is upper-cased
_STATUS = {"ok": "OK", "success": "OK", "failed": "FAIL", "fail": "FAIL", "skipped": "SKIP",
           "skip": "SKIP", "error": "ERROR", "xfail": "X_FAIL", "uxsuccess": "X_OK"}

FLOW, SLOWEST, SLOWEST_TABLE, FAIL_HEAD, FAIL_BODY = range(5)


def _is_rule(line: str, char: str, length: int = 20) -> bool:
    return len(line) >= length and line == char * len(line)


def split_test_id(test_id: str) -> TestId | None:
    """(class, test name, uuid, options) of "class.test_name[id-x,tags](options)" or
    "setUpClass (class)"; None when it isn't a test id."""
    setup = _SETUP_RE.match(test_id)
    if setup:
        if setup.group("rest") != ")":
            return None
        return setup.group("kind"), setup.group("prefix"), "", ""
    match = _ID_RE.match(test_id)
    if match is None:
        return None
    uuid = ""
    for tag in (match.group("tags") or "[]")[1:-1].split(","):
        if tag.startswith("id-"):
            uuid = tag
    return match.group("cls"), match.group("name"), uuid, match.group("options") or ""


def _attachment_trace(lines: list[str]) -> list[str]:
    """The trace lines of a failure: the "Captured traceback:" attachment (stestr) without its
    indent when there is one, else the lines as they are."""
    sections: dict[str, list[str]] = {}
    current = None
    skip_rule = False
    for index, line in enumerate(lines):
        if skip_rule:
            skip_rule = False
            continue
        captured = _CAPTURED_RE.match(line)
        if captured and index + 1 < len(lines) and _is_rule(lines[index + 1], "~", 3):
            current = sections.setdefault(captured.group("name"), [])
            skip_rule = True
        elif current is not None:
            current.append(line[4:] if line.startswith("    ") else line)
    # attachments but no traceback: keep them all
    body = list(sections.get("traceback", lines) if sections else lines)
    while body and not body[-1].strip():
        body.pop()
    return body


class TempestLogParser:
    def __init__(self, test_manager: TestsManager, source: IO[str],
                 status_filters: Iterable[str] | None = None, run_name: str | None = None,
                 run_date: datetime | None = None) -> None:
        self.test_mgr = test_manager
        self.source = source
        self.status_filters = list(status_filters or [])
        self.run_name = run_name or getattr(source, "name", "<stdin>").lower()
        self.run_date = run_date or file_date(source)

        self._state = FLOW
        self._class_name = ""
        # wrapped "setUpClass (prefix" line waiting for "ClassName) RESULT time"
        self._setup_prefix: tuple[str, str] | None = None
        # tests left out by the status filters: their slowest and failure entries are ignored
        self._filtered: set[tuple[str, str, str]] = set()
        # the failure being collected: its head (test id) and trace lines
        self._head: str | None = None
        self._trace: list[str] = []
        self._slowest_rows = False

    def parse(self) -> None:
        for line in self.source:
            self._feed(_PREFIX_RE.sub("", line.rstrip("\r\n")))
        self._end_failure()
        self.test_mgr.add_execution(self.run_name, self.run_date)
        self.test_mgr.log_summaries([self.run_name])

    def _feed(self, line: str) -> None:
        stripped = line.strip()
        if _is_rule(stripped, "=", 6):
            self._end_failure()
            self._state = FAIL_HEAD
            return
        if _SUMMARY_RE.match(stripped):
            self._end_failure()
            self._state = FLOW
            return
        result = _RESULT_RE.match(stripped)
        if result:
            self._end_failure()
            self._result_line(result)
            return
        if self._state == FAIL_HEAD:
            if _is_rule(stripped, "-"):
                self._state = FAIL_BODY
                return
            if not stripped:
                return
            if self._head is None:
                self._head = _HEAD_PREFIX_RE.sub("", stripped)
                return
            # not a failure block ("Worker Balance" lines and the like)
            self._head = None
            self._state = FLOW
        if self._state == FAIL_BODY:
            self._body_line(line, stripped)
            return
        if self._state == SLOWEST:
            if stripped:
                self._slowest_line(re.sub(" +", " ", stripped))
            else:
                self._state = FLOW
            return
        if self._state == SLOWEST_TABLE:
            self._slowest_table_line(stripped)
            return
        if _SLOWEST_RE.match(stripped):
            self._state = SLOWEST
            self._class_name = ""
            return
        if stripped == "Slowest Tests:":
            self._state = SLOWEST_TABLE
            self._slowest_rows = False
            return
        if stripped:
            self._flow_line(re.sub(" +", " ", stripped))

    # results: testr layout

    def _flow_line(self, line: str) -> None:
        setup = _SETUP_RE.match(line)
        if setup:
            self._class_name = ""
            rest = setup.group("rest")
            if rest.startswith(")"):
                # the whole class name on one line
                self._setup_result(setup.group("kind"), setup.group("prefix"), rest[1:])
                self._setup_prefix = None
            else:
                self._setup_prefix = (setup.group("kind"), setup.group("prefix"))
            return
        if self._setup_prefix is not None and ")" in line:
            kind, prefix = self._setup_prefix
            self._setup_prefix = None
            name, _, rest = line.partition(")")
            self._setup_result(kind, prefix + "." + name.strip(), rest)
            return
        if _CLASS_RE.match(line):
            self._class_name = line
            self._setup_prefix = None
            return
        test = _TEST_RE.match(line)
        if test and test.group("result") and self._class_name:
            self._add_result(self._class_name, test.group("name"), "", test.group("options") or "",
                             test.group("result"), test.group("time"))
            return
        log.debug("Unknown text in line: %s", line)

    def _setup_result(self, kind: str, class_name: str, rest: str) -> None:
        # "FAIL 0.00": the class setup or teardown failed
        parts = rest.split()
        if parts:
            self._add_result(kind, class_name, "", "", parts[0],
                             parts[1] if len(parts) > 1 else None)

    def _add_result(self, class_name: str, test_name: str, uuid: str, options: str, result: str,
                    time: str | None, message: str = "") -> None:
        if result in self.status_filters:
            self._filtered.add((class_name, test_name, options))
            return
        self.test_mgr.add_result_for_test(
            self.run_name, class_name, test_name, uuid, options, result, parse_seconds(time),
            message=message)

    # results: stestr layout

    def _result_line(self, match: re.Match[str]) -> None:
        test = split_test_id(match.group("id"))
        self._state = FLOW
        if test is None:
            log.debug("Unknown test id in line: %s", match.group(0))
            return
        status = _STATUS.get(match.group("status").lower(), match.group("status").upper())
        class_name, test_name, uuid, options = test
        reason = match.group("reason") or ""
        self._add_result(class_name, test_name, uuid, options, status, match.group("time"),
                         message=reason if status == "SKIP" else "")
        # the attachments printed under the line: kept for failures, dropped otherwise
        self._state = FAIL_BODY
        self._head = match.group("id") if status not in ("OK", "SKIP", "X_FAIL") else None
        self._trace = []

    # slowest tests

    def _slowest_line(self, line: str) -> None:
        if _CLASS_RE.match(line):
            self._class_name = line
            return
        if _SETUP_RE.match(line):
            self._class_name = ""
            return
        test = _TEST_RE.match(line)
        if test is None or not self._class_name:
            return
        self._mark_slowest(self._class_name, test.group("name"), "", test.group("options") or "")

    def _slowest_table_line(self, line: str) -> None:
        row = _SLOWEST_TABLE_ROW_RE.match(line)
        test = split_test_id(row.group("id")) if row else None
        if test is not None:
            self._slowest_rows = True
            self._mark_slowest(*test)
        elif self._slowest_rows and not line:
            self._state = FLOW

    def _mark_slowest(self, class_name: str, test_name: str, uuid: str, options: str) -> None:
        if (class_name, test_name, options) in self._filtered:
            return
        self.test_mgr.mark_slowest_test_in_execution_by_name(
            self.run_name, class_name, test_name, uuid=uuid, test_options=options)

    # failures

    def _body_line(self, line: str, stripped: str) -> None:
        if _is_rule(stripped, "-") and self._trace and not line.startswith(" "):
            # stestr's failure list: a test id over a line of dashes starts the next failure
            previous = self._trace[-1]
            before = self._trace[-2] if len(self._trace) > 1 else ""
            if split_test_id(previous) and not before.strip():
                self._trace.pop()
                self._end_failure()
                self._head = previous
                self._state = FAIL_BODY
                return
        self._trace.append(line)

    def _end_failure(self) -> None:
        """Store the failure collected so far (head and trace) on its test."""
        head, lines = self._head, self._trace
        self._head, self._trace = None, []
        if head is None:
            return
        test = split_test_id(head if head.startswith(("setUpClass", "tearDownClass"))
                             else head.split()[0])
        if test is None:
            # a section title such as "Totals", not a test
            return
        class_name, test_name, uuid, options = test
        if (class_name, test_name, options) in self._filtered:
            return
        lines = _attachment_trace(lines)
        message = "".join(line.lstrip() + "\n" for line in lines
                          if line.lstrip().startswith("Details: "))
        trace = "".join(line + "\n" for line in lines)
        self.test_mgr.add_fail_data_for_test(
            self.run_name, class_name, test_name, options, trace, message, uuid=uuid or None)
