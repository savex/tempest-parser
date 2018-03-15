import os
import sys
import argparse
from stat import S_ISFIFO

from tempest_parser import const
from tempest_parser.reports import reporter
from tempest_parser.reports.csv_reporter import CSVReporter
from tempest_parser.manager.test_manager import TestsManager
from tempest_parser.parser.tempest_log_parser import TempestLogParser
from tempest_parser.manager.importers import XMLImporter, JSONImporter, CSVImporter, SubunitImporter
from tempest_parser.utils.config import ParserConfigFile

pkg_dir = os.path.dirname(__file__)
pkg_dir = os.path.normpath(pkg_dir)


class MyParser(argparse.ArgumentParser):
    def error(self, message):
        sys.stderr.write('Error: {0}\n\n'.format(message))
        self.print_help()
        sys.exit(2)


def help_message():
    print"""
    Please, supply pytest output file as a parameter. \n
         " ...or previously exported CSV file \n
         " ...or rally's tool exported JSON file \n
         " ...or PyCharm's exported XML file \n
         " ...or saved subunit output \n
         " ...or folder full of files with types mentioned.\n
    """

    return


def detect_format_from_filename(filename):
    if filename.endswith(".json"):
        # this is Rally's json file
        return const.FMT_RALLY_JSON
    elif filename.endswith(".csv"):
        # this is simple csv file
        return const.FMT_CSV
    elif filename.endswith(".xml"):
        # this is an xml file, parse it using specific importer
        return const.FMT_PYCHARM_XML
    elif filename.endswith(".log"):
        # ..it is a bare testr output, parse it
        return const.FMT_PYTEST
    elif filename.endswith(".subunit"):
        # ..it is a subunit stream saved as a file, pass it along
        return const.FMT_SUBUNIT
    else:
        print("Error: Input filename's extension is not supported")
        sys.exit(1)


def do_parse_file(source, tm, fmt=None):
    close_source = False
    filename = "unknown/stdin"
    if not hasattr(source, "read"):
        if fmt is None:
            fmt = detect_format_from_filename(source)
        filename = source
        source = open(source, "rt")
        close_source = True

    importer = None

    if fmt is const.FMT_RALLY_JSON:
        # this is Rally's json file
        importer = JSONImporter(tm, source)
    elif fmt is const.FMT_CSV:
        # this is simple csv file
        importer = CSVImporter(tm, source)
    elif fmt is const.FMT_PYCHARM_XML:
        # this is an xml file, parse it using specific importer
        importer = XMLImporter(tm, source)
    elif fmt is const.FMT_PYTEST:
        # ..it is a bare testr output, parse it
        importer = TempestLogParser(tm, source)
    elif fmt is const.FMT_SUBUNIT:
        # ..it is a subunit stream saved as a file, pass it along
        importer = SubunitImporter(tm, source)

    importer.parse()
    print("Imported {}".format(filename))

    if close_source:
        source.close()


# main
def tempest_cli_parser_main():
    parser = MyParser(prog="Tempest CLI Parser")

    parser.add_argument(
        "inputfile", nargs="?", default=sys.stdin,
        help="""
    File with tempest results (CSV/LOG/XML/JSON) or folder full of these files
    """)

    parser.add_argument(
        "-f",
        "--input-format",
        help="""
    Input format. Defaults to SUBUNIT for pipe.
    Tries to detect from extension if filename is supplied
    """)

    parser.add_argument(
        "-d",
        "--detailed",
        action="store_true",
        help="""
    Include messages column with tracebacks and other messages.
    Default comes from config
    """)

    parser.add_argument(
        "-i",
        "--include-required",
        action="store_true", default=False,
        help="Initialise first column as baseline test list. I.e. required"
    )

    parser.add_argument(
        "-c",
        "--csv-file",
        help="Force output to CSV"
    )

    parser.add_argument(
        "--config-file",
        help="""
    Use specific configuration file instead of standard.
    Use absolute path, please.
    """
    )

    parser.add_argument(
        "-r",
        "--html-trending-filename",
        help="When set, creates HTML Trending Report"
    )

    parser.add_argument(
        "-e",
        "--html-errors-filename",
        help="When set, creates HTML Errors Report"
    )

    args = parser.parse_args()

    # Init Config
    _config_file_path = os.path.join(pkg_dir, 'etc', 'tempest-parser.conf')
    if args.config_file:
        _config_file_path = args.config_file
    config = ParserConfigFile(_config_file_path)

    # use config to set value for 'detailed' option
    _config_detailed_default = config.get_detailed_column_default_value()
    _args_detailed = args.detailed

    do_detailed = _args_detailed if _args_detailed \
        else _config_detailed_default

    pipe_fmt = None
    # Detect pipe input, prior to handle args
    # print("istty?={}, fifo?={}".format(
    #     sys.stdin.isatty(),
    #     S_ISFIFO(os.fstat(0).st_mode)
    # ))
    if S_ISFIFO(os.fstat(0).st_mode) and args.inputfile is "<stdin>":
        # TODO: handle pipe input here
        # if isinstance(argparse.inputfile, file):
        #     print("Error: No input file given")
        #     sys.exit(1)
        if args.input_format is None:
            pipe_fmt = const.FMT_SUBUNIT

    else:
        # Check for supplied folder/file to be exists
        if not os.path.exists(args.inputfile):
            print("Error: Supplied path/file not exists, '{}'".format(
                args.inputfile
            ))
            sys.exit(1)

        # Check if errors report is set and file is supplied
        if not os.path.isfile(args.inputfile):
            if args.html_errors_filename:
                print("Error: Errors report require single file, "
                      "folder given: '{}'".format(args.inputfile))
                sys.exit(1)

    # At this point we must load tests to combine executions with
    # for now it will be all tests
    tests_manager = TestsManager()
    if args.include_required:
        tests_manager.add_required(config.get_all_tests_list_filepath())

    # # Parse objects from raw file
    # # and Collect / sort objects into executions and parse them
    if pipe_fmt is not None:
        # this is a pipe input, pass file descriptor and format
        print("...waiting for tests ({})".format(args.inputfile.name))
        do_parse_file(
            args.inputfile,
            tests_manager,
            fmt=pipe_fmt
        )
    elif os.path.isfile(args.inputfile):
        print("Preloading tests from '{}'".format(args.inputfile))
        # this is a file, parse it using supplied input format
        do_parse_file(
            args.inputfile,
            tests_manager,
            fmt=args.input_format
        )
    else:
        print("Preloading tests from '{}'".format(args.inputfile))
        # this is a folder, get files one by one
        _folder_content = os.listdir(args.inputfile)

        for _file in _folder_content:
            # parse log files
            do_parse_file(
                os.path.join(
                    args.inputfile,
                    _file
                ),
                tests_manager,
            )

    if args.html_trending_filename:
        # prepare the reporting subsystem
        trending_report = reporter.ReportToFile(
            reporter.HTMLTrendingReport(),
            args.html_trending_filename
        )
        # call-n-render report
        print("Generating HTML Trending report...")
        trending_report(tests_manager.get_tests_list(), detailed=do_detailed)

    if args.html_errors_filename:
        errors_report = reporter.ReportToFile(
            reporter.HTMLErrorsReport(),
            args.html_errors_filename
        )
        # call-n-render report
        print("Generating HTML Errors report...")
        errors_report(tests_manager.get_tests_list())

    if args.csv_file is not None:
        print("Generating CSV report...")
        csv_reporter = CSVReporter(tests_manager)
        csv_reporter.generate_to_file(args.csv_file, detailed=do_detailed)


if __name__ == '__main__':
    tempest_cli_parser_main()
    sys.exit(0)
