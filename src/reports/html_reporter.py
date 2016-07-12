__author__ = 'savex'

from xmlbuilder import XMLBuilder
import datetime

from src.utils.file import *

class HtmlReport:
    def __init__(self, test_manager):
        self.test_manager = test_manager
        self._tests = self.test_manager.get_tests_list()
        self._total_executions = self._tests["executions"].keys()
        self.html = XMLBuilder('html', xmlns='http://www.w3.org/1999/xhtml')
        # turn of that xml header
        self.html['xml_header'] = False
        return

    # this is deprecated now as xml option turning of was added to xmlbuilder
    def _cut_xml(self, html_as_string):
        _tmp = ""
        start = html_as_string.find('<?xml')
        end = html_as_string.find('?>')
        if start != -1 and end != -1:
            _tmp = html_as_string.replace(html_as_string[start + 1:end], "")
        return _tmp

    def _put_status(self, test, class_style):
        if test["test_name"] == 'test_list_servers_filtered_by_ip[gate]':
            a = 222
        with self.html.div(clas='time'):
            # _executions = test["results"].keys()
            for _execution in self._total_executions:
                with self.html.span:
                    if test['results'].has_key(_execution) and \
                        test['results'][_execution].has_key('time') and \
                            test['results'][_execution]['time'].__len__() > 1:
                                self.html.em('{0}'.format(
                                        test['results'][_execution]['time']
                                    ),
                                    clas='time'
                                )
                    else:
                        self.html.em('-', clas='time')

        with self.html.span:
            #_executions = test["results"].keys()
            for _execution in self._total_executions:
                if test['results'].has_key(_execution) and \
                        test['results'][_execution].has_key('result'):
                    # here we deal with colors of status

                    self.html.em(
                        test['results'][_execution]["result"],
                        clas='status'
                    )
                else:
                    self.html.em('N/A', clas='status')
            self.html.delete(test['test_name'])

        return

    # main function to generate report
    def render_report(self, test_run_list, filename):

        with self.html.body:
            with self.html.div(id='container'):

                # Summary
                _executions = self.test_manager.get_executions()

                with self.html.div(id='header'):
                    for execution in _executions:
                        (time_sec, total, ok, fail, skip) = self.test_manager.get_summary_for_execution(execution)
                        tt = datetime.timedelta(seconds=time_sec)
                        minutes = int(time_sec / 60)
                        seconds = int(time_sec % 60)
                        hours = int(minutes / 60)
                        minutes = int(minutes % 60)

                        self.html.div('{0} h {1} m {2} s'.format(
                            hours,
                            minutes,
                            seconds
                        ),
                                 clas='time'
                        )
                        with self.html.h1('Summary for "{0}"'.format(execution)):
                            with self.html.strong():
                                self.html.span('{0} total, '.format(total), clas='total')
                                self.html.span('{0} error, '.format(fail), clas='error')
                                self.html.span('{0} skipped, '.format(skip), clas='ignored')
                                self.html.span('{0} passed'.format(ok), clas='passed')

                        with self.html.div(id='treecontrol'):
                            with self.html.ul:
                                with self.html.li:
                                    self.html.a('Collapse', href='#', title='Collapse the entire tree below')
                                self.html.delete(' |')
                                with self.html.li:
                                    self.html.a('Expand', href="#", title='Expand the entire tree below')

                with self.html.div(id='content'):
                    with self.html.ul(id='tree'):

                        # get all classes
                        _classes = self.test_manager.get_test_classes()

                        # Class start
                        for test_class in _classes:

                            # we should lookup ahead if there is an error in this section to mark it as failed
                            # Lookup section
                            class_style = 'level top '

                            if self.test_manager.is_class_has_errors(test_class):
                                class_style += 'failed open'

                            # Generate header
                            with self.html.li(clas=class_style):
                                with self.html.div(clas='time'):
                                    with self.html.span:
                                        self.html.em(
                                            '{0}'.format(self.test_manager.get_time_for_class(test_class)),
                                            clas='time'
                                        )
                                self.html.span('{0}, summary (pass/fail): {1}'.format(
                                    test_class,
                                    self.test_manager.get_totals_as_string_for_class(test_class)
                                ))
                                with self.html.ul:
                                    ii = 0
                                    # Iterate tests
                                    _tests = self.test_manager.get_tests_for_class(test_class)
                                    for test in _tests:
                                        ii += 1
                                        # look up if there is a failed tests here
                                        class_style = 'level test '
                                        with self.html.li(clas=class_style):

                                            # status and time if OK or SKIP
                                            self._put_status(test, class_style)

                                            if self.test_manager.is_test_has_errors(test_class, test["test_name"]):
                                                # on error we should add style and skip time
                                                class_style += 'failed'

                                                # Collect all errors from tests

                                                # print all errors
                                                error = "Error"
                                                trace = "Trace"

                                                with self.html.ul:
                                                    with self.html.li(clas='text'):
                                                        self.html.span(
                                                            error + '<br />',
                                                            clas='stdout'
                                                        )
                                                    with self.html.li(clas='text'):
                                                        self.html.span('{0}: <br /> {1}'.format(
                                                                "some",
                                                                trace
                                                            ),
                                                            clas='stderr'
                                                        )

            # footer notice
            with self.html.div(id='footer'):
                self.html.p('Made with Mirantis Inc. parsing script and PyCharm HTML Template')

        # Yes! This is quick and dirty
        _html_page = str(self.html).replace('clas=', 'class=')
        _html_page = _html_page.replace('<delete>', '')
        _html_page = _html_page.replace('</delete>', '')
        _html_page = _html_page.replace('&lt;br /&gt;', '<br />')

        _header = read_file(os.path.join('res', '_header.html'))
        write_str_to_file(filename, _header + _html_page)
        return True
