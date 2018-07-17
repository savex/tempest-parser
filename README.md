## Foreword

When you running tempest, you probably want to review result in a human manner.

You running it once again... and again... and a couple times more the next day... you end up with 20+ files in '.testrepository' folder. Start digging how specific tempest test was executed yesterday, how changed result is today. 'grep', 'less'... Brain goes hot.
...
Honestly, Subunit's CLI output is good enough for reading the word PASSED at the end...and the summary.

So, there is a need to:
- import tempest tests results
- match tests by Class, test_name and options
- produce some sort of a report to work with test statuses and track them over time
- Have error messages be added to the report


## Installing

Latest published version can be obtained using pip:

```pip install tempestparser```

or using setup.py from cloned git repo

```python setup.py install```

## Usage

This util is originally intended for 'import-match-export' flow to produce CSV with tests matched by Class and name against the list of tests that was originally executed.

```tparser -c matched.csv tempest.log```

Folder also can be used:

```tparser -c matched.csv folder1```

And finally, here is HTML report

```tparser -r trending.html tempest.xml```

or

```tparser -r trending.html folder1```

also, you can add full traceback messages to report by adding -d switch

```tparser -r trending.html -d folder1```

In order to eliminate some time waste when scrolling report back and forth,
you can produce unique errors report (see below).
Please, note that here you must supply `single test run` file

```tparser -e errors.html single_run.json```

This report matches FAILs and SKIPs by main 'message' to produce unique errors and skips list. If main message is not there it tries to extract it from trace by matching strings started with 'Details: ' as main message and additional ones with a pair of logical statements:
- regular expression of r'\s' (no white spaces at string start)
- string not started with 'Trace'


## Imported Formats

### .log files
Bare tempest output captured with either redirection or by copying XX numbered files from `.testrepository` folder.
LOG parser anchors against lines started with specific strings. Make sure to remove leading environment variables and worker report stuff.

### .xml files
Files exported from subunit in XML format.

### .json files
[Rally](https://github.com/openstack/rally) tool export: 

```rally verify results --json --output-file result1.json```

## Credits

Thanks to Dmitry Bogun, Alexey Diyan and Dmitriy Zapeka.

