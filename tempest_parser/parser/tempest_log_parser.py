import re
import os.path
import time
from copy import deepcopy

import tempest_parser.manager.structs as structs
import tempest_parser.parser.parser_strings as strings


class TempestLogParser:
    def __init__(self, test_manager, source):
        self.test_mgr = test_manager
        self.source = source

        pass

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
        _file_m_date = time.strftime(
            "%d/%m/%Y %H:%M",
            time.gmtime(os.path.getmtime(self.source.name))
        )
        _file_c_date = time.strftime(
            "%d/%m/%Y %H:%M",
            time.gmtime(os.path.getctime(self.source.name))
        )
        _unixtime = time.gmtime(os.path.getctime(self.source.name))
        print("\tcreated: {0}".format(_file_c_date))
        print("\tlast modified: {0}".format(_file_m_date))

        # load lines into list and pre-parse it by dividing into sections
        # each section is between double next line character: '\n'
        _raw_data = self.source.read()
        _search_criteria = "\n\n"

        # Search for criteria and split
        _data_list = _raw_data.split(_search_criteria)

        _index = 0
        # remove heading newlines
        while _index < _data_list.__len__():
            if _data_list[_index].__len__() > 0:
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
        while _index < _data_list.__len__():
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
                # print("{0} summary sections found".format(_count))
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
                    "created_date": _file_m_date,
                    "data": _data,
                    "type": _type,
                    "unixtime": _unixtime
                }
            )
            _index += 1
        # debug
        # for object in cli_objects_list:
        # if object["type"] == TEMPEST_EXECUTION_SUMMARY:
        # print("{0}".format(object["data"]))
        # debug
        # for object in cli_objects_list:
        # if object["type"] == TEMPEST_FAIL_MESSAGE:
        # print("{0}".format(object["data"]))

        print("Found: {0} obj, {1} fails, {2} summary, {3} unknown".format(
            cli_objects_list.__len__(),
            _fail_count,
            _summary_count,
            _unknown_count
        ))

        # breaking list into sections
        # at this point objects (no matter of their type: flow, fail, etc)
        # followed by each other.
        # They are NOT logically connected to each other

        # Normally, we should have this order: execution, speed, fail, summary
        # So, break up...
        execution_list_raw = []

        _execution_section = []
        _section_start_index = 0
        for _index in range(0, cli_objects_list.__len__()):
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
        _execution_item = deepcopy(structs.execution_item_template)
        for _object in _object_list:
            _execution_item["execution_name"] = _object["source"].lower()
            _execution_item["execution_date"] = _object["created_date"]
            _execution_item["unixtime"] = _object["unixtime"]
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

                    # preload_template in case we will not found it in the list
                    # _test_item = deepcopy(structs._template_test_item)

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
                        if _test.__len__() == 1:
                            # test name and result with no space, no time
                            _test_name = _test[0].split("[")[0].strip()
                            _test_options, _result = \
                                self._split_options_from_result(
                                    _test[0].split("]")[1].strip()
                                )
                        elif _test.__len__() == 2 and \
                                _test[1][0].isdigit():
                            # test name and result with no space,
                            # followed by time
                            _test_name = _test[0].split("[")[0].strip()
                            _test_options, _result = \
                                self._split_options_from_result(
                                    _test[0].split("]")[1].strip()
                                )
                            _time = _test[1].strip()
                        elif _test.__len__() == 2 and \
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
                        elif _test.__len__() > 2:
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
                        if _test.__len__() > 2:
                            _time = _test[2].strip()
                    else:
                        # Unknown
                        print("Unknown text in line: \n {0}".format(_line))

                    # we have a test_name and all of the results now,
                    # it is time to add this tests result
                    # lookup test in the list
                    self.test_mgr.add_result_for_test(
                        _execution_item["execution_name"],
                        _class_name,
                        _test_name,
                        _test_options,
                        _result,
                        _time
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

                        (_class_name, _test_name, _uuid, _test_options) = \
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
                _slowest_item = deepcopy(structs.template_slowest_item)

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
                            _test_options
                        )
                _execution_item["slowest"] = _slowest_item
            elif _object["type"] == strings.TEMPEST_EXECUTION_SUMMARY:
                # do some specific parsing for summary section
                _lines = _object["data"].splitlines()

                _summary_item = deepcopy(structs.template_summary_item)
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
                print("Empty or unknown section found:\n{0}".format(
                    _object["data"]
                ))

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
        for _fail_end_search_index in range(_index + 1, _data_list.__len__()):
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
        print("Performing per-object parsing")

        for _execution_raw in executions_list_raw:
            _execution_item = self.parse_execution_list(_execution_raw)
            self.test_mgr.add_execution(_execution_item)

        executions = self.test_mgr.get_executions()
        executions.sort()

        print("""
Current executions sets list:\n
--------------------------------------------------
""")
        for execution in executions:
            # throw a quick summary
            running_time, total, ok, fail, skip = \
                self.test_mgr.get_summary_for_execution(execution)

            print("""
Tempest testrun {0}: {1} executed: {2} passed, {3} failed, {4} skipped
""".format(
                execution,
                total,
                ok,
                fail,
                skip
            ))
        print("--------------------------------------------------")

        return self.test_mgr.get_tests_list()

    def parse(self):
        self.object_parser(self.cli_parser())
