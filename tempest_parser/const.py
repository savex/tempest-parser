# -*- coding:utf-8 -*-

from __future__ import print_function, absolute_import

import itertools


_cnt = itertools.count()
STATUS_PASS = next(_cnt)
STATUS_FAIL = next(_cnt)
STATUS_ERROR = next(_cnt)
STATUS_SKIP = next(_cnt)
STATUS_NA = next(_cnt)

ALL_KNOWN_STATUSES = {
    STATUS_PASS,
    STATUS_FAIL,
    STATUS_ERROR,
    STATUS_SKIP,
    STATUS_NA}

_cnt = itertools.count()
VERBOSE_GENERIC = next(_cnt)
VERBOSE_SHORT = next(_cnt)
VERBOSE_DETAILS = next(_cnt)

del _cnt
