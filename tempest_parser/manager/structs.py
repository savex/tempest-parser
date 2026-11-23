"""Builders for the dicts that hold parsed results.

Each call returns a fresh dict, which is much cheaper than deep-copying a template.
"""


def new_test_result(result="", time="", message="", trace=""):
    """One test's result in one run."""
    return {
        "result": result,
        "time": time,
        "slowest": False,
        "setup_fail": False,
        "trace": trace,
        "message": message,
    }


def new_test_item(test_name="", uuid="", test_options="", tags=None):
    """One test; the class name is the key it is stored under."""
    return {
        "test_name": test_name,
        "uuid": uuid,
        "test_options": test_options,
        "tags": tags if tags is not None else [],
        # execution name -> result
        "results": {},
    }


def new_slowest_item():
    return {"time_total": "", "count": 0, "tests": []}


def new_summary_item():
    return {"total": 0, "failed": 0, "outcome": "", "time": ""}


def new_execution_item():
    return {
        "execution_name": "",
        "execution_date": "",
        "unixtime": 0,
        "slowest": new_slowest_item(),
        "summary": new_summary_item(),
        "raw": "",
    }


def new_tests_list():
    """The whole structure: class name -> [test items], execution name -> [date, unixtime]."""
    return {"tests": {}, "executions": {}}
