import os
import sys
import argparse

from tempest_parser import const
from tempest_parser.reports import reporter
from tempest_parser.reports.csv_reporter import CSVReporter
from tempest_parser.manager.test_manager import TestsManager
from tempest_parser.parser.tempest_log_parser import TempestLogParser
from tempest_parser.manager.importers import XMLImporter, JSONImporter, \
    CSVImporter, SubunitImporter
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
         " ...or subunit's exported XML file \n
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
        # default to tempest type
        return const.FMT_XML_TEMPEST
    elif filename.endswith(".log"):
        # ..it is a bare testr output, parse it
        return const.FMT_PYTEST
    elif filename.endswith(".subunit"):
        # ..it is a subunit stream saved as a file, pass it along
        return const.FMT_SUBUNIT
    else:
        print("Error: Input filename's extension is not supported")
        sys.exit(1)


def do_parse_file(source, tm, fmt=None, force_single=None, filters=None):
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
        importer = JSONImporter(tm, source, status_filters=filters)
    elif fmt is const.FMT_CSV:
        # this is simple csv file
        importer = CSVImporter(tm, source, status_filters=filters)
    elif fmt is const.FMT_XML_TEMPEST:
        # this is an xml file from tempest
        # parse it using specific importer
        importer = XMLImporter(tm, source, status_filters=filters)
    elif fmt is const.FMT_XML_RAW:
        # this is a raw xml file
        # parse it and use test names as is
        importer = XMLImporter(
            tm,
            source,
            use_raw_names=True,
            force_single_execution=force_single,
            status_filters=filters
        )
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
        "--omit-status",
        action="append",
        help="Do not include tests with target status in final report. "
             "Option can be used multiple times."
    )

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
        "--force-single",
        action="store_true", default=False,
        help="All files in folder treated as single execution"
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

    # prepare format
    input_fmt = None
    if args.input_format is None:
        pass
    else:
        _fmt = args.input_format.strip()
        if _fmt in const.ALL_INPUT_FORMATS:
            input_fmt = const.ALL_INPUT_FORMATS[_fmt]
        else:
            print("Supplied format is not supported: '{}'".format(
                args.input_format
            ))

    # prepare filter
    status_filters = args.omit_status

    pipe_fmt = None
    # Detect pipe input, prior to handle args
    # print("istty?={}, fifo?={}, fd?={}".format(
    #     sys.stdin.isatty(),
    #     S_ISFIFO(os.fstat(0).st_mode),
    #     args.inputfile
    # ))
    if hasattr(args.inputfile, "name"):
        if args.inputfile.name == "<stdin>":
            if input_fmt is None:
                pipe_fmt = const.FMT_SUBUNIT
                print("No PIPE format set, defaulted to: '{}'".format(
                    const.FORMAT_LABELS[pipe_fmt]
                ))
            else:
                pipe_fmt = input_fmt
        else:
            print("Error: Unknown PIPE: '{}', '<stdin>' expected".format(
                args.inputfile.name
            ))
            sys.exit(1)
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

    if hasattr(args.inputfile, "name"):
        print("Reading '{}' from '{}'".format(
            const.FORMAT_LABELS[pipe_fmt],
            args.inputfile.name
        ))

    # At this point we must load tests to combine executions with
    # for now it will be all tests
    tests_manager = TestsManager()
    if args.include_required and args.html_errors_filename is None:
        _all_tests_filename = config.get_all_tests_list_filepath()
        print("Preloading all tests from '{}'".format(
            _all_tests_filename
        ))
        tests_manager.add_required(_all_tests_filename)
    # # Parse objects from raw file
    # # and Collect / sort objects into executions and parse them
    if pipe_fmt is not None:
        # this is a pipe input, pass file descriptor and format
        do_parse_file(
            args.inputfile,
            tests_manager,
            fmt=pipe_fmt,
            filters=status_filters
        )
    elif os.path.isfile(args.inputfile):
        # this is a file, parse it using supplied input format
        do_parse_file(
            args.inputfile,
            tests_manager,
            fmt=input_fmt,
            filters=status_filters
        )
    else:
        print("Importing tests from folder '{}'".format(args.inputfile))
        # this is a folder, get files one by one
        _folder_content = os.listdir(args.inputfile)

        for _file in _folder_content:
            # parse files according to format
            _target_extension = const.FORMAT_LABELS[input_fmt]
            if input_fmt is not None and not _file.endswith(_target_extension):
                print(
                    "Skipped '{}', "
                    "extension not corresponds to given format ({})".format(
                        _file,
                        _target_extension
                    ))
                continue
            # if extension fits - process file
            if args.force_single:
                do_parse_file(
                    os.path.join(
                        args.inputfile,
                        _file
                    ),
                    tests_manager,
                    fmt=input_fmt,
                    force_single=args.inputfile,
                    filters=status_filters
                )
            else:
                do_parse_file(
                    os.path.join(
                        args.inputfile,
                        _file
                    ),
                    tests_manager,
                    fmt=input_fmt,
                    filters=status_filters
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
