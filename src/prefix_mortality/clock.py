"""Time as the drivers see it: one object that tells the time, the local date and waits.

The real one wraps the standard library. A test passes one whose time moves only when a driver
sleeps, so a 600-second gap costs nothing and the stand-in server's idle timer, the records'
timestamps and the driver's waits all read one clock. `STAMP` is the format `record.utc_now` writes.
"""
import time
from datetime import datetime, timezone

STAMP = "%Y-%m-%dT%H:%M:%S.%fZ"


class Clock:
    def now_utc(self) -> datetime:
        return datetime.now(timezone.utc)

    def stamp(self) -> str:
        return self.now_utc().strftime(STAMP)

    def today(self) -> str:
        return datetime.now().strftime("%Y-%m-%d")

    def sleep(self, seconds: float) -> None:
        if seconds > 0:
            time.sleep(seconds)


REAL = Clock()


def seconds_between(earlier: str, later: str) -> float:
    """Seconds from one stamp to another. Raises ValueError on a stamp that is not in STAMP."""
    a = datetime.strptime(earlier, STAMP).replace(tzinfo=timezone.utc)
    b = datetime.strptime(later, STAMP).replace(tzinfo=timezone.utc)
    return (b - a).total_seconds()
