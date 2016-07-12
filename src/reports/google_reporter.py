__author__ = 'savex'

import os
import httplib2
from oauth2client.client import SignedJwtAssertionCredentials
import gdata.spreadsheets.client
import gdata.spreadsheets.data
import gdata.spreadsheet.service
import gdata.gauth

from src.utils.config import GoogleAccountConfigFile


class GoogleReporter:

    def __init__(self, config_file, test_manager):
        self.config_file = config_file

        self.test_manager = test_manager
        self._tests = self.test_manager.get_tests_list()
        self._total_executions = sorted(self._tests["executions"].keys())

        conf = GoogleAccountConfigFile(self.config_file)
        # AppAssertionCredentials is not supported in gdata python client library,
        # so we use SignedJwtAssertionCredentials with the credential
        # file of this service account.
        # Load the key in PKCS 12 format that you downloaded from the Google API
        # Console when you created your Service account.
        path = os.path.join('googleAuth', conf.get_google_auth_p12key())

        with open(path) as f:
            private_key_buffer = f.read()
            f.close()

        # Getting credentials with AppAssertionCredentials only worked successfully
        # for Google API Client Library for Python, e.g. accessing file's meta-data.
        # So we use SignedJwtAssertionCredentials, as suggested in
        # http://stackoverflow.com/questions/16026286/using-oauth2-with-service-account-on-gdata-in-python
        # but with-out the sub parameter!
        credentials = SignedJwtAssertionCredentials(
            conf.get_google_client_email(),
            private_key_buffer,
            scope=(
                'https://www.googleapis.com/auth/drive.file ',
                # added the scope above as suggested somewhere else,
                # but error occurs with and with-out this scope
                'https://www.googleapis.com/auth/drive',
                'https://spreadsheets.google.com/feeds',
                'https://docs.google.com/feeds'
            )
        )

        http = httplib2.Http()
        http = credentials.authorize(http)

        auth2token = gdata.gauth.OAuth2TokenFromCredentials(credentials)
        # this pattern would eventually also work using SpreadsheetsService()
        # SpreadsheetsService methods are different from SpreadsheetsClient, though
        # srv = gdata.spreadsheet.service.SpreadsheetsService()
        # srv = auth2token.authorize(srv)

        clt = gdata.spreadsheets.client.SpreadsheetsClient()
        clt = auth2token.authorize(clt)

        self.client = clt
        self.spreadsheet_key = conf.get_google_spreadsheet_key()

        worksheets = self.client.get_worksheets(self.spreadsheet_key)
        _wksht_id = worksheets.entry[0].id.text
        _tmp = _wksht_id.split("/")
        _tmp.reverse()
        self.worksheet_id = _tmp[0]


        self.data_list = []
        # Just a forwards for future query of the spreadsheet size
        self.max_columns = 14
        self.max_rows = 0

        self.batch_size = 500
        return

    def _prepare_data(self):
        # we need to prepare data list for update
        _data_list = []

        # Header
        _data_list.append("")
        _data_list.append("class/test name")

        _result_columns = 2
        ## execution dates for header
        for _execution in self._total_executions:
            #execution name
            #csv_header += _execution + ','
            _date_prepared = self._tests['executions'][_execution]
            _date_prepared = _date_prepared.replace('/','\n')
            _date_prepared = _date_prepared.replace(' ','\n')

            _data_list.append(_date_prepared)
            _result_columns += 1

        # Align array to size of spreadsheet
        for i in range(0 , self.max_columns-_result_columns, 1):
            _data_list.append("")

        # Data block

        _tests_counter = 0
        ## lines
        for class_name in sorted(self._tests['tests'].keys()):
            # printing out class line
            _data_list.append("Class")
            _data_list.append(class_name)

            # Align array to size of spreadsheet
            for i in range(0 , self.max_columns-2, 1):
                _data_list.append("")

            # iterate tests
            for _test in self._tests['tests'][class_name]:
                _tests_counter += 1
                _data_list.append(str(_tests_counter))
                _data_list.append(_test['test_name'] + _test['test_options'])

                #Add a Required/Added mark to results
                if _test['results'].has_key('required'):
                    _data_list.append(_test['results']['required']['result'])
                else:
                    _data_list.append('A')

                #Iterate other results
                for _execution in self._total_executions:
                    if _execution != 'required':
                        if _test['results'].has_key(_execution):
                            # new template has no 'time' mark, just comment it out
                            _data_list.append(_test['results'][_execution]['result'])
                        else:
                            #_results += ',' + ','
                            _data_list.append("")

                # Align array to size of spreadsheet
                for i in range(0 , self.max_columns-_result_columns, 1):
                    _data_list.append("")
        # This is the number of rows we need in target spreadsheet
        self.max_rows = _data_list.__len__() / self.max_columns
        return _data_list


    def prepare_batch(self, data_list, data_position, num_row_start, num_row_end, char_col_start, char_col_end):

        tmp_range = char_col_start + str(num_row_start) + ':' + char_col_end + str(num_row_end)

        # Prepare batches
        cell_query = gdata.spreadsheets.client.CellQuery(
            range=tmp_range,
            return_empty=True
        )
        print("...preloading cells range: {0}".format(tmp_range))
        cells = self.client.GetCells(
            self.spreadsheet_key,
            self.worksheet_id,
            q=cell_query
        )
        print("...building batch")
        _batch = gdata.spreadsheets.data.BuildBatchCellsUpdate(
            self.spreadsheet_key,
            self.worksheet_id
        )

        i = data_position
        for cell in cells.entry:

            cell.cell.input_value = data_list[i]

            _batch.add_batch_entry(
                cell,
                cell.id.text,
                batch_id_string=cell.title.text,
                operation_string='update'
            )

            i += 1

        return i, _batch


    def update_worksheet(self):

        print("Preparing tests data")
        data_list = self._prepare_data()

        print("Sizing spreadsheet dimensions...")

        # Add remove rows and columns

        # TBD

        #Get worksheet dimensions and add columns and rows if needed
        print("Cells to update: {0}".format(data_list.__len__()))
        _max_rows = self.max_rows
        _max_cols = self.max_columns

        # TBD

        # Divide updating into batches and do re-try if not successfull
        starting_row = 5
        end_row = self.max_rows + starting_row - 1

        # first batch
        _tmp_row_start = 4
        _tmp_row_end = 4
        _tmp_pos = 0

        # calculate how much rows left
        _tmp_rows_until_end = end_row - _tmp_row_end

        # if there is more than batch size left, process it
        while _tmp_rows_until_end > self.batch_size:
            # Whole range to update
            # _range="A5:N3795"

            # proceed to next portion
            _tmp_row_start = _tmp_row_end + 1
            _tmp_row_end += self.batch_size
            _tmp_rows_until_end = end_row - _tmp_row_end

            # build batch
            _tmp_pos, current_batch = self.prepare_batch(
                data_list,
                _tmp_pos,
                _tmp_row_start,
                _tmp_row_end,
                "A",
                "N"
            )

            # update it

            print("...updating")
            self.client.batch(
                current_batch,
                force=True
            )


        # we need to update last one
        _tmp_pos, remaining_batch = self.prepare_batch(
            data_list,
            _tmp_pos,
            _tmp_row_end + 1,
            #_tmp_row_start + _tmp_rows_until_end,
            _tmp_row_end + _tmp_rows_until_end,
            "A",
            "N"
        )
        print("...updating")
        self.client.batch(
            remaining_batch,
            force=True
        )

        '''
            range = "A6:D1113"
            cellq = gdata.spreadsheets.client.CellQuery(range=range, return_empty='true')
            cells = gd_client.GetCells(sprd_key, wrksht_key, q=cellq)
            batch = gdata.spreadsheets.data.BuildBatchCellsUpdate(sprd_key, wrksht_key)
            n = 1
            for cell in cells.entry:
                cell.cell.input_value = str(n)
                batch.add_batch_entry(cell, cell.id.text, batch_id_string=cell.title.text, operation_string='update')
                n = n + 1
            gd_client.batch(batch, force=True) # A single call to Google Server to update all cells.
        '''

        return