"""Statuses, report columns and input formats, each defined once."""
import os
from enum import Enum, StrEnum


class Status(StrEnum):
    """Result of one test in one run, as stored and shown in the reports.

    Results are kept as plain strings, so values read from files that aren't listed here
    still work; these are the ones the importers produce and the reports look for.
    """
    OK = "OK"
    FAIL = "FAIL"
    ERROR = "ERROR"
    SKIP = "SKIP"
    X_FAIL = "X_FAIL"   # expected failure
    X_OK = "X_OK"       # unexpected success
    REQUIRED = "R"      # listed in the baseline test list (the "required" run)
    ADDED = "A"         # not in the baseline test list (CSV reports)


class Column(Enum):
    """Summary columns of the HTML reports; the value is the label."""
    PASS = "Pass"
    FAIL = "Fail"
    ERROR = "Error"
    NA = "NA"
    SKIP = "Skip"
    ADDED = "Added"

    @property
    def css(self) -> str:
        return self.value.lower()


class InputFormat(StrEnum):
    """Input formats; the value is the `-f` option value."""
    SUBUNIT = "subunit"
    CSV = "csv"
    RALLY_JSON = "json"
    XML_TEMPEST = "t_xml"
    XML_RAW = "r_xml"
    LOG = "log"

    @property
    def label(self) -> str:
        """File extension without the dot, as shown in messages."""
        return "xml" if self in (InputFormat.XML_TEMPEST, InputFormat.XML_RAW) else self.value

    @property
    def extension(self) -> str:
        return "." + self.label

    @classmethod
    def from_filename(cls, filename: str) -> "InputFormat | None":
        """Format for a file name by its extension (`.xml` is tempest XML), or None."""
        extension = os.path.splitext(filename)[1]
        for fmt in (cls.SUBUNIT, cls.CSV, cls.RALLY_JSON, cls.XML_TEMPEST, cls.LOG):
            if fmt.extension == extension:
                return fmt
        return None


# name of the run that holds the baseline test list (-i)
REQUIRED_RUN = "required"
