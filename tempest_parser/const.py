# -*- coding:utf-8 -*-

from __future__ import print_function, absolute_import

import itertools


_cnt = itertools.count()
STATUS_PASS = next(_cnt)
STATUS_FAIL = next(_cnt)
STATUS_ERROR = next(_cnt)
STATUS_SKIP = next(_cnt)
STATUS_NA = next(_cnt)
STATUS_ADDED = next(_cnt)

ALL_KNOWN_STATUSES = {
    STATUS_PASS,
    STATUS_FAIL,
    STATUS_ERROR,
    STATUS_SKIP,
    STATUS_NA,
    STATUS_ADDED
}

_cnt = itertools.count()
VERBOSE_GENERIC = next(_cnt)
VERBOSE_SHORT = next(_cnt)
VERBOSE_DETAILS = next(_cnt)

_cnt = itertools.count()
FMT_SUBUNIT = next(_cnt)
FMT_CSV = next(_cnt)
FMT_RALLY_JSON = next(_cnt)
FMT_XML_TEMPEST = next(_cnt)
FMT_XML_RAW = next(_cnt)
FMT_PYTEST = next(_cnt)

ALL_INPUT_FORMATS = {
    "subunit": FMT_SUBUNIT,
    "csv": FMT_CSV,
    "json": FMT_RALLY_JSON,
    "t_xml": FMT_XML_TEMPEST,
    "r_xml": FMT_XML_RAW,
    "log": FMT_PYTEST
}

FORMAT_LABELS = {
    FMT_SUBUNIT: "subunit",
    FMT_CSV: "csv",
    FMT_RALLY_JSON: "json",
    FMT_XML_TEMPEST: "xml",
    FMT_XML_RAW: "xml",
    FMT_PYTEST: "log"
}

del _cnt
