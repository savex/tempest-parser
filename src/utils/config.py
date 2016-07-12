__author__ = 'savex'

import ConfigParser


"""
This is deprecated.
Google Spreadsheet update procedure takes too long to use it.
Approximated time to upload results for 3 testruns with 1200 tests each is 57 min (Yeeee!)
"""
class GoogleAccountConfigFile:

    def __init__(self, filepath):
        self.config_file_path = filepath

        self.section_name = 'GoogleAccount'

        self.config = ConfigParser.ConfigParser()
        self.config.read(self.config_file_path)

    def get_username(self):
        return self.config.get(self.section_name, 'username')

    def get_password(self):
        return self.config.get(self.section_name, 'password')

    def get_google_spreadsheet_key(self):
        return self.config.get(self.section_name, 'spreadsheet_key')

    def get_google_client_email(self):
        return self.config.get(self.section_name, 'client_email')

    def get_google_auth_p12key(self):
        return self.config.get(self.section_name, 'p12keyfile')
