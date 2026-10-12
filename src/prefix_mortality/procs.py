"""A server process under the driver's control, for the experiments whose subject is the process.

`ServerHandle` is what a driver needs: start the server and wait until it answers GET /health with
200, stop it, and say how many times it has been started (the generation) and what it knows about the
current process. `Subprocess` runs a command line; the tests run a stand-in through the same
interface (tests/fake_procs.py). The handle never writes a record: the driver copies `info()` into
its records, and the records carry only what the handle reports — a generation number, a pid and a
start time — never the command line, which may name paths on the operator's machine.
"""
import subprocess
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Protocol


class ServerHandle(Protocol):
    url: str

    def start(self) -> dict: ...
    def stop(self) -> None: ...
    def info(self) -> dict: ...


def wait_healthy(url: str, timeout_seconds: float, poll_seconds: float = 0.5) -> None:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url.rstrip("/") + "/health", timeout=5) as r:
                if r.status == 200:
                    return
        except (urllib.error.URLError, TimeoutError, ConnectionError, OSError):
            pass
        time.sleep(poll_seconds)
    raise RuntimeError(f"{url} did not answer GET /health with 200 within {timeout_seconds} s")


class Subprocess:
    """A server started from a command line, its output appended to a log file."""

    def __init__(self, argv: list[str], url: str, log_path: Path, cwd: Path | None = None,
                 start_timeout_seconds: float = 300.0):
        if not argv:
            raise ValueError("an empty command line")
        self.argv, self.url, self.log_path, self.cwd = list(argv), url, Path(log_path), cwd
        self.start_timeout = start_timeout_seconds
        self.generation = 0
        self._proc: subprocess.Popen | None = None
        self._started: str | None = None

    def start(self) -> dict:
        if self._proc is not None and self._proc.poll() is None:
            raise RuntimeError("the server is already running; stop it first")
        self.generation += 1
        self._started = datetime.now(timezone.utc).isoformat()
        with open(self.log_path, "ab") as log:
            log.write(f"\n=== generation {self.generation} starting {self._started}\n".encode("utf-8"))
            self._proc = subprocess.Popen(self.argv, stdout=log, stderr=subprocess.STDOUT, cwd=self.cwd)
        try:
            wait_healthy(self.url, self.start_timeout)
        except RuntimeError:
            self.stop()
            raise
        return self.info()

    def stop(self) -> None:
        if self._proc is None:
            return
        if self._proc.poll() is None:
            self._proc.terminate()
            try:
                self._proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self._proc.kill()
                self._proc.wait(timeout=10)
        self._proc = None

    def info(self) -> dict:
        running = self._proc is not None and self._proc.poll() is None
        return {"generation": self.generation, "pid": self._proc.pid if running else None,
                "started": self._started, "running": running}
