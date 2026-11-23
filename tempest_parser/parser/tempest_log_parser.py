import logging
import re

import tempest_parser.parser.parser_strings as strings
from tempest_parser.manager.models import file_date, parse_seconds

log = logging.getLogger(__name__)


# the parser's own notes about one run in the log, used while parsing
def _new_execution_item():
    return {
        "execution_name": "",
        "execution_date": None,
        "slowest": {"time_total": "", "count": 0, "tests": []},
        "summary": {"total": 0, "failed": 0, "outcome": "", "time": ""},
        "raw": "",
    }


class TempestLogParser:
    def __init__(self, test_manager, source, status_filters=None):
        self.test_mgr = test_manager
        self.source = source
        self.status_filters = status_filters or []

    @staticmethod
    def _split_options_from_test_name(_test_name_with_options):
        # sample: "_test_some_func[gate,smoke](options)"
        _options = ""

        if _test_name_with_options.find("(") != -1:
            # There is an option present
            _test_name = _test_name_with_options.partition('[')[0]
            _options = _test_name_with_options.partition(']')[2]
        else:
            # no options, just cut the '[]' part
            _test_name = _test_name_with_options.partition('[')[0]

        return _test_name, _options

    @staticmethod
    def _split_options_from_result(_options_with_result):
        # sample: "(options)OK"
        # detect if there is an option present
        _optons = ""
        if _options_with_result.find(")") != -1:
            _tmp = _options_with_result.partition(')')
            _optons = _tmp[0] + _tmp[1]
            _result = _tmp[2]
        else:
            _result = _options_with_result
        return _optons, _result

    # method to do the first parsing of the cli log
    # divide it into objects
    def cli_parser(self):
        cli_objects_list = []
        # the log has no date: the run is dated by the file's modification time
        _file_date = file_date(self.source)

        # load lines into list and pre-parse it by dividing into sections
        # each section is between double next line character: '\n'
        _raw_data = self.source.read()
        _search_criteria = "\n\n"

        # Search for criteria and split
        _data_list = _raw_data.split(_search_criteria)

        _index = 0
        # remove heading newlines
        while _index < len(_data_list):
            if len(_data_list[_index]) > 0:
                while _data_list[_index][0] == '\n':
                    _data_list[_index] = _data_list[_index].replace(
                        "\n",
                        "",
                        1
                    )
            _index += 1

        # Cut to separate lines or combine them
        _fail_count = 0
        _unknown_count = 0
        _summary_count = 0
        # _data = ""
        _index = 0
        while _index < len(_data_list):
            # safety first, clear out and load data
            _data = " "
            _type = "empty"
            _section = _data_list[_index]

            # Detect what is it

            # For summary we must cut OK\FAIL to previous line
            if _section.startswith(strings.summary_ran_string):
                # this is Summary, combine this with next one
                # load test result in next section
                _cutted_result = \
                    _data_list[_index + 1][
                        :_data_list[_index + 1].find("\n") + 1
                    ]
                # cut it from there
                _data_list[_index + 1] = _data_list[_index + 1].replace(
                    _cutted_result,
                    ""
                )
                # form summary section
                _data = _section + "\n" + _cutted_result
                # set type
                _type = strings.TEMPEST_EXECUTION_SUMMARY

                _summary_count += 1
            elif _section.startswith(strings.summary_ok_string) or \
                    _section.startswith(strings.summary_fail_string):
                # this one was combined with previous one
                # should not be entering here actually :)
                pass
            # Fail section
            elif _section.startswith(strings.fail_head_start_string):
                # this is a fail reporting section
                # search for next fail or end of section
                (_fail_sec, _index) = self._fail_section_end_lookup(
                    _index,
                    _data_list
                )
                _data = _section + '\n\n' + _fail_sec

                # _data = _section
                _type = strings.TEMPEST_FAIL_MESSAGE

                _fail_count += 1
            # execution section
            elif _section.startswith(strings.setupclass_start_string) or \
                    _section.startswith(strings.test_start_string):
                _data = _section
                _type = strings.TEMPEST_EXECUTION_FLOW
            elif _section.startswith(strings.speed_start_string):
                _data = _section
                _type = strings.TEMPEST_SPEED_SUMMARY
            else:
                # this is an unknown section,
                # we should add it to previous one as a trace
                cli_objects_list[len(cli_objects_list) - 1]["data"] += _section
                _index += 1
                continue

            # Add to dictionary
            cli_objects_list.append(
                {
                    "source": self.source.name,
                    "created_date": _file_date,
                    "data": _data,
                    "type": _type,
                }
            )
            _index += 1
        log.debug("Found: %d obj, %d fails, %d summary, %d unknown",
                  len(cli_objects_list), _fail_count, _summary_count, _unknown_count)

        # breaking list into sections
        # at this point objects (no matter of their type: flow, fail, etc)
        # followed by each other.
        # They are NOT logically connected to each other

        # Normally, we should have this order: execution, speed, fail, summary
        # So, break up...
        execution_list_raw = []

        _execution_section = []
        _section_start_index = 0
        for _index in range(0, len(cli_objects_list)):
            # if _section_start_index == _index:
            # continue

            if cli_objects_list[_index]["type"] == \
                    strings.TEMPEST_EXECUTION_SUMMARY:
                # we passed through items and sound end of the section
                # save it
                for _section_index in range(_section_start_index, _index):
                    _execution_section.append(cli_objects_list[_section_index])
                _execution_section.append(cli_objects_list[_index])
                _section_start_index = _index + 1
                execution_list_raw.append(_execution_section)
                _execution_section = []

        return execution_list_raw

    # Parse object list with specifics about it's content
    def parse_execution_list(self, _object_list):
        # fill items
        _execution_item = _new_execution_item()
        for _object in _object_list:
            _execution_item["execution_name"] = _object["source"].lower()
            _execution_item["execution_date"] = _object["created_date"]
            _execution_item["raw"] += _object["data"]
            if _object["type"] == strings.TEMPEST_EXECUTION_FLOW:
                # do some specific parsing
                _lines = _object["data"].splitlines()

                _class_name = ""
                _test_class_prefix = ""
                _setUp_tearDown_class_failed = False

                for _line in _lines:
                    _line = _line.lstrip()
                    # split into "words"
                    # and remove multiple spaces in the process
                    _line_s = re.sub(" +", " ", _line)


                    # forwards for the data found,
                    # class_name already found at this point
                    _test_name = ""
                    _test_options = ""
                    _result = ""
                    _time = ""

                    _test = _line_s.split(" ")

                    if _line.startswith(strings.test_start_string):
                        _class_name = _line.strip()
                        _setUp_tearDown_class_failed = False
                        continue
                    elif _line.startswith(strings.setupclass_start_string) or \
                            _line.startswith(strings.teardown_start_string):
                        _class_name = _line_s.split(" ")[0].strip()
                        _test_class_prefix = _line_s.split("(")[1].strip()
                        _setUp_tearDown_class_failed = True
                        continue
                    elif _line.startswith("test_"):
                        if len(_test) == 1:
                            # test name and result with no space, no time
                            _test_name = _test[0].split("[")[0].strip()
                            _test_options, _result = \
                                self._split_options_from_result(
                                    _test[0].split("]")[1].strip()
                                )
                        elif len(_test) == 2 and \
                                _test[1][0].isdigit():
                            # test name and result with no space,
                            # followed by time
                            _test_name = _test[0].split("[")[0].strip()
                            _test_options, _result = \
                                self._split_options_from_result(
                                    _test[0].split("]")[1].strip()
                                )
                            _time = _test[1].strip()
                        elif len(_test) == 2 and \
                                (
                                    _test[1].startswith("OK") or
                                    _test[1].startswith("FAIL") or
                                    _test[1].startswith("SKIP")
                                ):
                            # test name and result with a space between em',
                            # no time
                            _test_name, _test_options = \
                                self._split_options_from_test_name(_test[0])
                            _result = _test[1].strip()
                        elif len(_test) > 2:
                            # test name, result and time separated by space
                            _test_name, _test_options = \
                                self._split_options_from_test_name(_test[0])
                            _result = _test[1].strip()
                            _time = _test[2].strip()
                    # if this is not a start of a subsection,
                    # or start of a test, then, if class fail flag is set
                    # we should load the result value
                    # and do test name combining
                    elif len(_line_s.split(")")) > 1 and \
                            _setUp_tearDown_class_failed:
                        # class name fail,
                        # test class name remainder with a SKIP
                        # as a result with a space between
                        _test = _line_s.split(" ")
                        # _class_name = "setupClass"
                        _test_name = \
                            _test_class_prefix + '.' + _test[0].strip()[:-1]
                        _result = _test[1].strip()
                        if len(_test) > 2:
                            _time = _test[2].strip()
                    else:
                        # Unknown
                        log.debug("Unknown text in line: %s", _line)
                        continue

                    if not _test_name or _result in self.status_filters:
                        continue

                    # we have a test_name and all of the results now,
                    # it is time to add this tests result
                    # lookup test in the list
                    self.test_mgr.add_result_for_test(
                        _execution_item["execution_name"],
                        _class_name,
                        _test_name,
                        "",
                        _test_options,
                        _result,
                        parse_seconds(_time)
                    )
            elif _object["type"] == strings.TEMPEST_FAIL_MESSAGE:
                # do some specific parsing fail messages object
                _lines = _object["data"].splitlines()

                _class_name = ""
                _test_name = ""
                _test_options = ""
                _message = ""
                _trace = ""

                # flag for extracting test fail message
                _test_fail_head_found = False

                for _line in _lines:
                    _line_s = _line.lstrip()

                    if _line_s.startswith(strings.fail_head_start_string) or \
                            _line_s.startswith("----------------------------"):
                        continue
                    elif _line_s.startswith(strings.test_start_string):
                        # this is a start of a new test fail,
                        # we should save the old one
                        if _test_fail_head_found:
                            self.test_mgr.add_fail_data_for_test(
                                _execution_item["execution_name"],
                                _class_name,
                                _test_name,
                                _test_options,
                                _trace,
                                _message
                            )
                            _trace = ''
                            _message = ''
                        # extract nest one
                        try:
                            _full_name = _line_s.split(" ", 1)[1]
                        except IndexError:
                            _full_name = _line_s

                        (_class_name, _test_name, _uuid, _test_options, _tags) = \
                            self.test_mgr.split_test_name(_full_name)
                        _test_fail_head_found = True
                    elif _line_s.startswith("Details: "):
                        _line_s = _line_s.replace('"', '\'')
                        _line_s = _line_s.replace(',', ' ')

                        _message += _line_s + '\n'
                        _trace += _line + "\n"
                    else:
                        _trace += _line + "\n"

                self.test_mgr.add_fail_data_for_test(
                    _execution_item["execution_name"],
                    _class_name,
                    _test_name,
                    _test_options,
                    _trace,
                    _message
                )
            elif _object["type"] == strings.TEMPEST_SPEED_SUMMARY:
                # do some specific parsing for Slowest timings object
                _lines = _object["data"].splitlines()

                _class_name = ""
                _slowest_item = {"time_total": "", "count": 0, "tests": []}

                for _line in _lines:
                    _line = _line.lstrip()
                    _line_s = re.sub(" +", " ", _line)

                    if _line.startswith(strings.speed_start_string):
                        # parse timing header
                        _slowest = _line.split(" ")
                        _slowest_item["count"] = _slowest[1]
                        _slowest_item["time_total"] = _slowest[4]
                        continue
                    elif _line.startswith(strings.test_start_string) or \
                            _line.startswith(
                                strings.setupclass_start_string
                            ) or \
                            _line.startswith(strings.teardown_start_string):
                        _class_name = _line.strip()
                        continue
                    elif _line.startswith("test_"):
                        _class_name, _test_name, _test_options = \
                            self.test_mgr.split_test_name_from_speed(
                                _class_name + '.' + _line_s
                            )

                        self.test_mgr.mark_slowest_test_in_execution_by_name(
                            _execution_item["execution_name"],
                            _class_name,
                            _test_name,
                            test_options=_test_options
                        )
                _execution_item["slowest"] = _slowest_item
            elif _object["type"] == strings.TEMPEST_EXECUTION_SUMMARY:
                # do some specific parsing for summary section
                _lines = _object["data"].splitlines()

                _summary_item = {"total": 0, "failed": 0, "outcome": "", "time": ""}
                for _line in _lines:
                    if _line.startswith(strings.summary_ran_string):
                        _summary_list = _line.split(" ")

                        _summary_item["total"] = _summary_list[1]
                        _summary_item["time"] = _summary_list[4]
                    elif _line.startswith(strings.summary_ok_string):
                        _summary_item["outcome"] = _line.strip()
                    elif _line.startswith(strings.summary_fail_string):
                        _summary_list = _line.split(" ")

                        _summary_item["outcome"] = _summary_list[0]
                        _summary_item["failed"] = \
                            _summary_list[1].split("=")[1][:-1]

                _execution_item["summary"] = _summary_item
            else:
                log.debug("Empty or unknown section found:\n%s", _object["data"])

        # We're done
        return _execution_item

    @staticmethod
    def _fail_section_end_lookup(_index, _data_list):
        """
        Search for the end of FAIL section
        :param _index:
        :param _data_list:
        :return:
        """
        _fail_section = ""
        _local_index = _index + 1
        for _fail_end_search_index in range(_index + 1, len(_data_list)):
            _tmp = _data_list[_fail_end_search_index]

            if _tmp.startswith(strings.fail_head_start_string) or \
                    _tmp.startswith(strings.summary_ran_string):
                _local_index = _fail_end_search_index - 1
                break
            else:
                _fail_section += '\n\n' + _tmp
        # return _fail_section
        return _fail_section, _local_index

    # apply parsing per object type
    # On return, we should have scenario
    # or scenarios dict with: execution, speed, fail and summary sections
    def object_parser(self, executions_list_raw):
        names = []
        for _execution_raw in executions_list_raw:
            _execution_item = self.parse_execution_list(_execution_raw)
            name = _execution_item["execution_name"]
            self.test_mgr.add_execution(name, _execution_item["execution_date"])
            names.append(name)

        # only the runs from this log
        self.test_mgr.log_summaries(names)

    def parse(self):
        self.object_parser(self.cli_parser())
