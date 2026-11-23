"""The parsed results: runs (executions), test cases and one case's result per run.

Times are seconds as floats (None when the input has none) and dates are timezone-aware
UTC datetimes; the reports format them.
"""
import os
from dataclasses import dataclass, field
from datetime import UTC, datetime

# how run dates are shown in reports and run names
DATE_FORMAT = "%d/%m/%Y %H:%M GMT"


@dataclass(slots=True)
class Result:
    """One test's result in one run."""
    result: str = ""
    time: float | None = None
    message: str = ""
    trace: str = ""
    slowest: bool = False
    setup_fail: bool = False


@dataclass(slots=True)
class Case:
    """One test; the class name is the key it is stored under in TestsManager.tests."""
    test_name: str = ""
    uuid: str = ""
    test_options: str = ""
    tags: list[str] = field(default_factory=list)
    # run (execution) name -> result
    results: dict[str, Result] = field(default_factory=dict)


@dataclass(slots=True)
class Execution:
    """One run, named after its source file (or folder with --force-single)."""
    name: str
    date: datetime

    @property
    def date_label(self):
        return self.date.strftime(DATE_FORMAT)

    @property
    def filename(self):
        return os.path.basename(self.name)


@dataclass(slots=True)
class Summary:
    """Counts and total time of one run's results."""
    total: int = 0
    ok: int = 0
    fail: int = 0
    error: int = 0
    skip: int = 0
    time: float = 0.0


def parse_seconds(value):
    """Seconds as a float from 1.5, "1.5", "1.5s" or "1.50 s"; None when empty or not a number."""
    if value is None or isinstance(value, float):
        return value
    if isinstance(value, int):
        return float(value)
    value = value.strip().removesuffix("s").strip()
    try:
        return float(value)
    except ValueError:
        return None


def file_date(source):
    """Modification time of a path or an open file, as a UTC datetime; now for streams
    without a file behind them (e.g. stdin)."""
    try:
        if hasattr(source, "fileno"):
            mtime = os.fstat(source.fileno()).st_mtime
        else:
            mtime = os.stat(source).st_mtime
    except (OSError, ValueError):
        return datetime.now(UTC)
    return datetime.fromtimestamp(mtime, UTC)
