import ConfigParser


class ParserConfigFile:
    def __init__(self, filepath):
        self.config_file_path = filepath

        self.section_name = 'ParserConfig'

        self.config = ConfigParser.ConfigParser()
        self.config.read(self.config_file_path)

    def get_all_tests_list_filepath(self):
        return self.config.get(self.section_name, 'default_test_list')
