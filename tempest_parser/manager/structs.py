# test_template
# result item list here consists of dicts with
# execution_name as a key and result
_template_test_result = {
    "result": "",
    "time": "",
    "slowest": False,
    "setup_fail": False,
    "trace": "",
    "message": ""
}

_template_test_item = {
    # class names will be as a key
    # "class_name": "",
    "test_name": "",
    "test_options": "",
    "set_name": "",
    "results": {}
}

_template_slowest_item = {
    "time_total": "",
    "count": 0,
    "tests": []
}

_template_summary_item = {
    "total": 0,
    "failed": 0,
    "outcome": "",
    "time": ""
}

# Execution dict template
_execution_item_template = {
    "execution_name": "",
    "execution_date": "",
    "slowest": _template_slowest_item,
    "summary": _template_summary_item,
    "raw": ""
}

_tests_template = {
    # class names
    "tests": {},
    # parsed execution names
    "executions": {}
}
