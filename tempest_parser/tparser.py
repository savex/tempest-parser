import os
import sys
import argparse

from tempest_parser.reports import reporter
from tempest_parser.reports.csv_reporter import CSVReporter
from tempest_parser.manager.test_manager import TestsManager
from tempest_parser.parser.tempest_log_parser import TempestLogParser
from tempest_parser.manager.importers import XMLImporter, JSONImporter, CSVImporter
from tempest_parser.utils.config import ParserConfigFile

pkg_dir = os.path.dirname(__file__)
pkg_dir = os.path.normpath(pkg_dir)


class MyParser(argparse.ArgumentParser):
    def error(self, message):
        sys.stderr.write('Error: {0}\n\n'.format(message))
        self.print_help()
        sys.exit(2)


def help_message():
    print"Please, supply raw tempest cli LOG ('run_tempest.sh') file as an only parameter. \n" \
         " ...or previously exported CSV file \n" \
         " ...or rally's tool exported JSON file \n" \
         " ...or PyCharm's exported XML file \n" \
         " ...or folder full of files with types mentioned.\n" \

    return


def do_parse_file(filename, tm, log_parser):
    if filename.endswith(".json"):
        # this is Rally's json file
        json_importer = JSONImporter(
            tm,
            filename
        )
        json_importer.parse()
        print("Imported {}".format(filename))
    if filename.endswith(".csv"):
        # this is simple csv file
        csv_importer = CSVImporter(
            tm,
            filename
        )
        csv_importer.parse()
        print("Imported {}".format(filename))
    elif filename.endswith(".xml"):
        # this is an xml file, parse it using specific importer
        xml_importer = XMLImporter(
            tm,
            filename
        )
        xml_importer.parse()
        print("Imported {}".format(filename))
    elif filename.endswith(".log"):
        # ..it is not a json file, let us pass it to parser right away
        log_parser.object_parser(
            log_parser.cli_parser(filename)
        )


# main
def tempest_cli_parser_main():
    parser = MyParser(prog="Tempest CLI Parser")

    parser.add_argument(
        "filepath",
        help="file with tempest results (CSV/LOG/XML/JSON) or folder full of these files"
    )

    parser.add_argument(
        "-d",
        "--detailed",
        action="store_true",
        help="Include messages column with tracebacks and other messages. "
             "Default comes from config"
    )

    parser.add_argument(
        "-i",
        "--include-required",
        action="store_true", default=False,
        help="initialise first column as baseline test list. I.e. required"
    )

    parser.add_argument(
        "-c",
        "--csv-file",
        help="Force output to CSV"
    )

    parser.add_argument(
        "--config-file",
        help="Use specific configuration file instead of standard. Use absolute path, please."
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

    # Check for supplied folder/file to be exists
    if not os.path.exists(args.filepath):
        print("Error: Supplied path/file not exists, '{}'".format(args.filepath))
        sys.exit(1)

    # Check if errors report is set and file is supplied
    if not os.path.isfile(args.filepath):
        if args.html_errors_filename:
            print("Error: Errors report require single file, "
                  "folder given: '{}'".format(args.filepath))
            sys.exit(1)

    # At this point we must load tests to combine executions with
    # for now it will be all tests
    print("Pre-loading tests...")
    tests_manager = TestsManager()
    if args.include_required:
        tests_manager.add_required(config.get_all_tests_list_filepath())
    log_parser = TempestLogParser(tests_manager)

    # # Parse objects from raw file
    # # and Collect / sort objects into executions and parse them
    if os.path.isfile(args.filepath):
        # this is a file, parse it
        do_parse_file(
            args.filepath,
            tests_manager,
            log_parser
        )
    else:
        # this is a folder, get files one by one
        _folder_content = os.listdir(args.filepath)

        for _file in _folder_content:
            # parse log files
            do_parse_file(
                os.path.join(
                    args.filepath,
                    _file
                ),
                tests_manager,
                log_parser
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
        # prepare the reporting subsystem
