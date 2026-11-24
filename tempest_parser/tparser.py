import argparse
import logging
import os
import sys
from collections.abc import Iterable, Sequence
from datetime import UTC, datetime
from importlib import metadata
from typing import IO, Any, NoReturn, Protocol

from tempest_parser.const import InputFormat
from tempest_parser.manager.importers import (
    XML_TIME_UNITS,
    CSVImporter,
    JSONImporter,
    SubunitImporter,
    XMLImporter,
)
from tempest_parser.manager.test_manager import TestsManager
from tempest_parser.parser.tempest_log_parser import TempestLogParser
from tempest_parser.reports import reporter
from tempest_parser.reports.csv_reporter import CSVReporter
from tempest_parser.reports.json_reporter import JSONReporter, failing_results
from tempest_parser.utils.config import ParserConfigFile

pkg_dir = os.path.normpath(os.path.dirname(__file__))

log = logging.getLogger("tempest_parser")

# exit code when --fail-on finds results with the given statuses
EXIT_FAILED_TESTS = 3


class CLIError(Exception):
    """Stops the run with an error message and exit code 1."""


class Importer(Protocol):
    """What every input format's importer provides."""

    def parse(self) -> None: ...


# (source: a path or an open stream, its format if known, the --force-single run name)
Input = tuple[str | IO[Any], InputFormat | None, str | None]


class MyParser(argparse.ArgumentParser):
    def error(self, message: str) -> NoReturn:
        sys.stderr.write(f'Error: {message}\n\n')
        self.print_help()
        sys.exit(2)


class _Formatter(logging.Formatter):
    """Plain messages; errors and warnings get a prefix."""

    def format(self, record: logging.LogRecord) -> str:
        message = super().format(record)
        if record.levelno >= logging.ERROR:
            return "Error: " + message
        if record.levelno >= logging.WARNING:
            return "Warning: " + message
        return message


def setup_logging(quiet: bool = False) -> None:
    # test names and messages can hold any character; a console that can't show one
    # (Windows code pages, an ASCII locale) gets an escape instead of an error
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="backslashreplace")
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(_Formatter("%(message)s"))
    log.handlers[:] = [handler]
    log.setLevel(logging.ERROR if quiet else logging.INFO)
    log.propagate = False


def detect_format_from_filename(filename: str) -> InputFormat | None:
    """Input format for a file name, or None when the extension is not known."""
    return InputFormat.from_filename(filename)


def parse_run_date(value: str) -> datetime:
    """--run-date: an ISO 8601 date or date and time; without a time zone it is UTC."""
    try:
        date = datetime.fromisoformat(value)
    except ValueError:
        raise argparse.ArgumentTypeError(
            f"not an ISO 8601 date: '{value}' (e.g. 2026-11-23 or 2026-11-23T14:30)") from None
    if date.tzinfo is None:
        return date.replace(tzinfo=UTC)
    return date.astimezone(UTC)


def make_importer(fmt: InputFormat | None, tm: TestsManager, source: IO[Any],
                  force_single: str | None = None, filters: Iterable[str] | None = None,
                  run_name: str | None = None, run_date: datetime | None = None,
                  xml_time_unit: str | None = None) -> Importer:
    kw: dict[str, Any] = {
        "status_filters": filters or [], "run_name": run_name, "run_date": run_date}
    if fmt == InputFormat.RALLY_JSON:
        return JSONImporter(tm, source, **kw)
    if fmt == InputFormat.CSV:
        return CSVImporter(tm, source, **kw)
    if fmt in (InputFormat.XML_TEMPEST, InputFormat.XML_RAW):
        # raw XML keeps the test names as they are
        return XMLImporter(tm, source,
                           use_raw_names=fmt == InputFormat.XML_RAW,
                           force_single_execution=force_single, time_unit=xml_time_unit,
                           **kw)
    if fmt == InputFormat.LOG:
        return TempestLogParser(tm, source, **kw)
    if fmt == InputFormat.SUBUNIT:
        return SubunitImporter(tm, source, **kw)
    raise CLIError(f"Unknown input format: {fmt}")


def do_parse_file(source: str | IO[Any], tm: TestsManager, fmt: InputFormat | None = None,
                  force_single: str | None = None, filters: Iterable[str] | None = None,
                  run_name: str | None = None, run_date: datetime | None = None,
                  xml_time_unit: str | None = None) -> None:
    """Import one file (a path) or stream (an open file, e.g. stdin)."""
    if not isinstance(source, str):
        if fmt != InputFormat.SUBUNIT and hasattr(source, "reconfigure"):
            # text piped in is read as UTF-8 whatever the locale (subunit reads bytes)
            source.reconfigure(encoding="utf-8")
        make_importer(fmt, tm, source, force_single, filters, run_name, run_date,
                      xml_time_unit).parse()
        log.info("Imported %s", getattr(source, "name", "unknown/stdin"))
        return
    if fmt is None:
        fmt = detect_format_from_filename(source)
        if fmt is None:
            raise CLIError(
                f"Input filename's extension is not supported: '{source}'")
    # input files are UTF-8 (not the locale's code page, as on Windows before Python 3.15)
    with open(source, encoding="utf-8") as stream:
        make_importer(fmt, tm, stream, force_single, filters, run_name, run_date,
                      xml_time_unit).parse()
    log.info("Imported %s", source)


def package_version() -> str:
    """The installed package's version (from the git tag at build time)."""
    try:
        return metadata.version("TempestParser")
    except metadata.PackageNotFoundError:
        return "unknown (not installed)"


# --html-layout: the (trending, errors) report classes for each layout
HTML_LAYOUTS: dict[str, tuple[type[reporter.HTMLTrendingReport],
                              type[reporter.HTMLErrorsReport]]] = {
    "table": (reporter.HTMLTrendingReport, reporter.HTMLErrorsReport),
    "grid": (reporter.HTMLTrendingGridReport, reporter.HTMLErrorsGridReport),
}


def build_parser() -> MyParser:
    parser = MyParser(prog="Tempest CLI Parser")
    parser.add_argument(
        "-V", "--version", action="version", version=f"tparser {package_version()}")
    parser.add_argument(
        "inputfile", nargs="?", default=sys.stdin,
        help="File with test results or a folder of them; stdin when omitted")
    parser.add_argument(
        "-f", "--input-format", choices=sorted(InputFormat),
        help="Input format. Detected from the file extension when not set; "
             "stdin defaults to subunit")
    parser.add_argument(
        "--omit-status", action="append", default=[], metavar="STATUS",
        help="Leave tests with this status (OK, FAIL, ERROR, SKIP, ...) out of "
             "the reports. Can be used several times")
    parser.add_argument(
        "-d", "--detailed", action="store_true",
        help="Include a messages column with tracebacks. Default comes from config")
    parser.add_argument(
        "-i", "--include-required", action="store_true",
        help="Add the baseline test list from the config as the first column")
    parser.add_argument("-c", "--csv-file", help="Write the CSV report")
    parser.add_argument(
        "-j", "--json-file", help="Write a JSON summary of the runs (counts, times, dates)")
    parser.add_argument(
        "--fail-on", action="append", default=[], metavar="STATUS", type=str.upper,
        help=f"Exit with code {EXIT_FAILED_TESTS} when any run has a test with this status "
             "(FAIL, ERROR, ...). Can be used several times")
    parser.add_argument(
        "--config-file",
        help="Use this configuration file (absolute path) instead of the packaged one")
    parser.add_argument(
        "--force-single", action="store_true",
        help="Treat all files in a folder as a single run (XML input)")
    parser.add_argument(
        "--run-name", metavar="NAME",
        help="Name of the run in the reports instead of the file name (single input only)")
    parser.add_argument(
        "--run-date", metavar="DATE", type=parse_run_date,
        help="Date of the run, ISO 8601 (2026-11-23 or 2026-11-23T14:30, UTC unless an "
             "offset is given), instead of the file's modification time (single input only)")
    parser.add_argument(
        "--xml-time-unit", choices=sorted(XML_TIME_UNITS),
        help="Unit of the XML time attributes: s or ms. Default: seconds when any time in the "
             "file has a decimal point, else milliseconds")
    parser.add_argument(
        "-r", "--html-trending-filename", help="Write the HTML trending report")
    parser.add_argument(
        "--html-layout", choices=sorted(HTML_LAYOUTS), default="table",
        help="Layout of the HTML reports: tables (default) or CSS grid (sticky headers, "
             "light/dark switch, collapsible error groups)")
    parser.add_argument(
        "-e", "--html-errors-filename",
        help="Write the HTML unique errors report (single file input only)")
    parser.add_argument(
        "-q", "--quiet", action="store_true", help="Print errors only")
    return parser


def load_config(args: argparse.Namespace) -> ParserConfigFile:
    path = args.config_file or os.path.join(pkg_dir, 'etc', 'tempest-parser.conf')
    return ParserConfigFile(path)


def collect_inputs(args: argparse.Namespace, input_fmt: InputFormat | None) -> list[Input]:
    """[(source, format, force_single)] to import, in order."""
    source = args.inputfile
    if hasattr(source, "name"):
        if source.name != "<stdin>":
            raise CLIError(f"Unknown PIPE: '{source.name}', '<stdin>' expected")
        fmt = input_fmt if input_fmt is not None else InputFormat.SUBUNIT
        if input_fmt is None:
            log.info("No PIPE format set, defaulted to: '%s'", fmt.label)
        log.info("Reading '%s' from '%s'", fmt.label, source.name)
        return [(source, fmt, None)]

    if not os.path.exists(source):
        raise CLIError(f"Supplied path/file not exists, '{source}'")
    if os.path.isfile(source):
        return [(source, input_fmt, None)]
    if args.html_errors_filename:
        raise CLIError(
            f"Errors report require single file, folder given: '{source}'")
    if args.run_name or args.run_date:
        raise CLIError(
            f"--run-name and --run-date need a single file, folder given: '{source}'")

    log.info("Importing tests from folder '%s'", source)
    inputs = []
    for name in sorted(os.listdir(source)):
        if input_fmt is None:
            if detect_format_from_filename(name) is None:
                log.info("Skipped '%s', extension is not supported", name)
                continue
        elif not name.endswith(input_fmt.label):
            log.info("Skipped '%s', extension not corresponds to given format (%s)",
                     name, input_fmt.label)
            continue
        inputs.append((os.path.join(source, name), input_fmt,
                       source if args.force_single else None))
    return inputs


def write_reports(args: argparse.Namespace, tests_manager: TestsManager,
                  detailed: bool) -> None:
    if args.html_trending_filename:
        log.info("Generating HTML Trending report...")
        trending = HTML_LAYOUTS[args.html_layout][0]()
        reporter.ReportToFile(trending, args.html_trending_filename)(
            tests_manager, detailed=detailed)
    if args.html_errors_filename:
        log.info("Generating HTML Errors report...")
        errors = HTML_LAYOUTS[args.html_layout][1]()
        reporter.ReportToFile(errors, args.html_errors_filename)(tests_manager)
    if args.csv_file is not None:
        log.info("Generating CSV report...")
        CSVReporter(tests_manager).generate_to_file(args.csv_file, detailed=detailed)
    if args.json_file is not None:
        log.info("Generating JSON summary...")
        JSONReporter(tests_manager).generate_to_file(args.json_file)


def check_fail_on(statuses: Iterable[str], tests_manager: TestsManager) -> int:
    """Exit code for --fail-on: EXIT_FAILED_TESTS when a result has one of the statuses."""
    found = failing_results(tests_manager, statuses)
    if not found:
        return 0
    for run, class_name, test_name, status in found:
        log.warning("%s: %s.%s %s", run, class_name, test_name, status)
    log.error("%d test result(s) with status %s", len(found), ", ".join(sorted(set(statuses))))
    return EXIT_FAILED_TESTS


def run(args: argparse.Namespace) -> int:
    config = load_config(args)
    detailed = args.detailed or config.get_detailed_column_default_value()
    input_fmt = InputFormat(args.input_format) if args.input_format else None

    inputs = collect_inputs(args, input_fmt)

    tests_manager = TestsManager()
    if args.include_required and args.html_errors_filename is None:
        baseline = config.get_all_tests_list_filepath()
        log.info("Preloading all tests from '%s'", baseline)
        tests_manager.add_required(
            baseline, use_raw_names=input_fmt == InputFormat.XML_RAW)

    for source, fmt, force_single in inputs:
        do_parse_file(source, tests_manager, fmt=fmt, force_single=force_single,
                      filters=args.omit_status, run_name=args.run_name,
                      run_date=args.run_date, xml_time_unit=args.xml_time_unit)

    write_reports(args, tests_manager, detailed)
    return check_fail_on(args.fail_on, tests_manager) if args.fail_on else 0


def tempest_cli_parser_main(argv: Sequence[str] | None = None) -> int:
    """Console entry point; returns the exit code."""
    args = build_parser().parse_args(argv)
    setup_logging(args.quiet)
    try:
        return run(args)
    except CLIError as e:
        log.error("%s", e)
        return 1


if __name__ == '__main__':
    sys.exit(tempest_cli_parser_main())
