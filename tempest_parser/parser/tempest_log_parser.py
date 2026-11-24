"""Parser for the tempest / testr console log (`.log` input).

The log is read line by line. Its parts, in the order they appear:

    tempest.api.compute.servers.test_servers.ServersTestJSON        <- class line
        test_create_server[id-1111,smoke]            OK  1.50       <- test line
        test_ipv6[id-3333](ipv6)                     FAIL  0.50     <- options in brackets
    setUpClass (tempest.api.network.test_ports                      <- class setup failed,
        PortsTestJSON)                               FAIL  0.00        name wrapped or not

    Slowest 2 tests took 2.00 secs:                                 <- slowest tests,
    tempest.api.compute.servers.test_servers.ServersTestJSON           up to a blank line
        test_create_server[id-1111,smoke]   1.50

    ======================================================================
    FAIL: tempest.api.compute.servers.test_servers.ServersTestJSON.test_x[id-2222]
    ----------------------------------------------------------------------  <- failure head
    Traceback (most recent call last):                              <- trace, up to the next
      ...                                                              head or the summary
    Details: 1 != 2                                                 <- also the message

    Ran 3 tests in 2.000s                                           <- summary
    FAILED (failures=1)

A log can hold several runs one after another; they all import into one run named after
the file. The log has no date, so the run is dated by the file's modification time.
"""
import logging
import re

from tempest_parser.manager.models import file_date, parse_seconds

log = logging.getLogger(__name__)

# a dotted name on a line of its own: tempest.api.compute.servers.test_servers.ServersTestJSON
_CLASS_RE = re.compile(r"^[A-Za-z_]\w*(\.\w+)+$")
# test_name[tags](options) RESULT time; the result and time are optional
_TEST_RE = re.compile(
    r"^(?P<name>test_[^\s\[(]*)(?P<tags>\[[^\]]*\])?(?P<options>\([^)]*\))?"
    r"\s*(?P<result>[A-Z][A-Z_]*)?\s*(?P<time>\d+(\.\d+)?s?)?\s*$")
# setUpClass (tempest.api.x.Class) FAIL 0.00, or with the class name wrapped to the next line
_SETUP_RE = re.compile(r"^(?P<kind>setUpClass|tearDownClass) \((?P<prefix>[^)\s]*)(?P<rest>.*)$")
_SLOWEST_RE = re.compile(r"^Slowest \d+ tests? took")
_SUMMARY_RE = re.compile(r"^Ran \d+ tests? in ")
# failure head prefixes written by some runners: "FAIL: tempest...."
_HEAD_PREFIX_RE = re.compile(r"^(FAIL|ERROR): ")

FLOW, SLOWEST, FAIL_HEAD, FAIL_BODY = range(4)


def _is_rule(line, char):
    return len(line) >= 20 and line == char * len(line)


class TempestLogParser:
    def __init__(self, test_manager, source, status_filters=None, run_name=None, run_date=None):
        self.test_mgr = test_manager
        self.source = source
        self.status_filters = status_filters or []
        self.run_name = run_name or getattr(source, "name", "<stdin>").lower()
        self.run_date = run_date or file_date(source)

        self._state = FLOW
        self._class_name = ""
        # wrapped "setUpClass (prefix" line waiting for "ClassName) RESULT time"
        self._setup_prefix = None
        # tests left out by the status filters: their slowest and failure entries are ignored
        self._filtered = set()
        self._head: str | None = None
        self._trace: list[str] = []

    def parse(self):
        for line in self.source:
            self._feed(line.rstrip("\r\n"))
        self._end_failure()
        self.test_mgr.add_execution(self.run_name, self.run_date)
        self.test_mgr.log_summaries([self.run_name])

    def _feed(self, line):
        stripped = line.strip()
        if _is_rule(stripped, "="):
            self._end_failure()
            self._state = FAIL_HEAD
            return
        if _SUMMARY_RE.match(stripped):
            self._end_failure()
            self._state = FLOW
            return
        if self._state == FAIL_HEAD:
            if _is_rule(stripped, "-"):
                self._state = FAIL_BODY
            elif stripped and self._head is None:
                self._head = _HEAD_PREFIX_RE.sub("", stripped)
            return
        if self._state == FAIL_BODY:
            self._trace.append(line)
            return
        if self._state == SLOWEST:
            if stripped:
                self._slowest_line(re.sub(" +", " ", stripped))
            else:
                self._state = FLOW
            return
        if _SLOWEST_RE.match(stripped):
            self._state = SLOWEST
            self._class_name = ""
            return
        if stripped:
            self._flow_line(re.sub(" +", " ", stripped))

    # results

    def _flow_line(self, line):
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
            self._add_result(self._class_name, test.group("name"), test.group("options") or "",
                             test.group("result"), test.group("time"))
            return
        log.debug("Unknown text in line: %s", line)

    def _setup_result(self, kind, class_name, rest):
        # "FAIL 0.00": the class setup or teardown failed
        parts = rest.split()
        if parts:
            self._add_result(kind, class_name, "", parts[0], parts[1] if len(parts) > 1 else None)

    def _add_result(self, class_name, test_name, options, result, time):
        if result in self.status_filters:
            self._filtered.add((class_name, test_name, options))
            return
        self.test_mgr.add_result_for_test(
            self.run_name, class_name, test_name, "", options, result, parse_seconds(time))

    # slowest tests

    def _slowest_line(self, line):
        if _CLASS_RE.match(line):
            self._class_name = line
            return
        if _SETUP_RE.match(line):
            self._class_name = ""
            return
        test = _TEST_RE.match(line)
        if test is None or not self._class_name:
            return
        key = (self._class_name, test.group("name"), test.group("options") or "")
        if key in self._filtered:
            return
        self.test_mgr.mark_slowest_test_in_execution_by_name(
            self.run_name, key[0], key[1], test_options=key[2])

    # failures

    def _end_failure(self):
        """Store the failure collected so far (head and trace) on its test."""
        head, lines = self._head, self._trace
        self._head, self._trace = None, []
        if head is None:
            return
        while lines and not lines[-1].strip():
            lines.pop()
        message = "".join(line.lstrip() + "\n" for line in lines
                          if line.lstrip().startswith("Details: "))
        trace = "".join(line + "\n" for line in lines)

        setup = _SETUP_RE.match(head)
        if setup and setup.group("rest").startswith(")"):
            class_name, test_name, options = setup.group("kind"), setup.group("prefix"), ""
        else:
            class_name, test_name, _, options, _ = \
                self.test_mgr.split_test_name(head.split()[0])
        if (class_name, test_name, options) in self._filtered:
            return
        self.test_mgr.add_fail_data_for_test(
            self.run_name, class_name, test_name, options, trace, message)
