# test_template
# result item list here consists of dicts with
# execution_name as a key and result
template_test_result = {
    "result": "",
    "time": "",
    "slowest": False,
    "setup_fail": False,
    "trace": "",
    "message": ""
}

template_test_item = {
    # class names will be as a key
    # "class_name": "",
    "test_name": "",
    "uuid": "",
    "test_options": "",
    "tags": "",
    "results": {}
}

template_slowest_item = {
    "time_total": "",
    "count": 0,
    "tests": []
}

template_summary_item = {
    "total": 0,
    "failed": 0,
    "outcome": "",
    "time": ""
}

# Execution dict template
execution_item_template = {
    "execution_name": "",
    "execution_date": "",
    "unixtime": 0,
    "slowest": template_slowest_item,
    "summary": template_summary_item,
    "raw": ""
}

tests_template = {
    # class names
    "tests": {},
    # parsed execution names
    "executions": {}
}
