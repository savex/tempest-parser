import ConfigParser
import os

pkg_dir = os.path.dirname(__file__)
pkg_dir = os.path.join(pkg_dir, os.path.pardir)
pkg_dir = os.path.normpath(pkg_dir)


class ParserConfigFile:
    _truth = ['true', '1', 't', 'y', 'yes', 'yeah', 'yup',
              'certainly', 'uh-huh']

    def __init__(self, filepath):
        self.config_file_path = filepath

        self.section_name = 'ParserConfig'

        self.config = ConfigParser.ConfigParser()
        self.config.read(self.config_file_path)

    def get_all_tests_list_filepath(self):
        # get path
        _path = self.config.get(self.section_name, 'default_test_list')

        # make sure it is absolute
        if not os.path.isabs(_path):
            return os.path.join(pkg_dir, _path)
        else:
            return _path

    def get_detailed_column_default_value(self):
        # value
        _value = self.config.get(self.section_name, 'default_detailed')
        # parse if
        if _value.lower() in self._truth:
            return True
        else:
            return False
