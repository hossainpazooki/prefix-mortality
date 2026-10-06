"""A clock whose time moves only when a driver sleeps or a test advances it. The stand-in server
reads `seconds()` for its idle timer; the driver reads stamps and the local date from the same
instant, so a recorded gap is exactly what the driver waited."""
from datetime import datetime, timedelta, timezone

from prefix_mortality.clock import STAMP, Clock


class FakeClock(Clock):
    def __init__(self, start: str = "2026-10-03T12:00:00.000000Z"):
        self.t0 = datetime.strptime(start, STAMP).replace(tzinfo=timezone.utc)
        self.elapsed = 0.0
        self.slept: list[float] = []

    def seconds(self) -> float:
        return self.elapsed

    def now_utc(self) -> datetime:
        return self.t0 + timedelta(seconds=self.elapsed)

    def today(self) -> str:
        return self.now_utc().strftime("%Y-%m-%d")

    def sleep(self, seconds: float) -> None:
        self.slept.append(seconds)
        self.elapsed += max(seconds, 0.0)

    def advance(self, seconds: float) -> None:
        self.elapsed += seconds
