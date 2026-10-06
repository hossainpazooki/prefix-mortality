"""The real clock does what the drivers ask of it, and the test clock offers nothing the real one
lacks: a driver that called a method only the fake has would pass every stand-in test and fail on
the engine."""
import inspect
import re

from prefix_mortality.clock import REAL, STAMP, Clock, seconds_between
from tests.fake_clock import FakeClock

TEST_ONLY = {"seconds", "advance"}          # the stand-in's timer and the tests' hand on the clock


def _public_methods(cls) -> set[str]:
    return {name for name, v in inspect.getmembers(cls, inspect.isfunction) if not name.startswith("_")}


def test_the_fake_clock_overrides_only_what_the_real_one_has():
    assert _public_methods(FakeClock) - TEST_ONLY == _public_methods(Clock) == {"now_utc", "stamp", "today", "sleep"}
    for name in _public_methods(Clock):
        assert inspect.signature(getattr(FakeClock, name)) == inspect.signature(getattr(Clock, name)), name


def test_the_real_clock_stamps_dates_and_waits():
    a = REAL.stamp()
    REAL.sleep(0)
    REAL.sleep(-1)                           # a negative wait is no wait, not an error
    b = REAL.stamp()
    assert 0 <= seconds_between(a, b) < 5
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{6}Z", a) and STAMP.endswith("Z")
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", REAL.today())
    assert REAL.now_utc().utcoffset().total_seconds() == 0
