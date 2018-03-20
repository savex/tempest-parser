import os


def remove_file(filename):
    os.remove(filename)
    # open('filename', 'w').close()


def write_str_to_file(filename, _str):
    with open(filename, 'w') as fo:
        fo.write(_str)


def append_str_to_file(filename, _str):
    with open(filename, 'a') as fa:
        fa.write(_str)


def append_line_to_file(filename, _str):
    with open(filename, 'a') as fa:
        fa.write(_str+'\n')


def read_file(filename):
    with open(filename, 'rb') as fr:
        _buf = fr.read()
    return _buf


def read_file_as_lines(filename):
    _list = []
    with open(filename, 'r') as fr:
        for line in fr:
            _list.append(line)
    return _list
