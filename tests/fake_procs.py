"""A server process stand-in for tests: `start` builds a fresh engine from a factory and serves it on a
new port, `stop` shuts it down. A restart forgets everything the engine held, as a real process does;
what survives is only what the factory is given from outside — a save-file store, for slot save and
restore across a restart."""
from datetime import datetime, timezone

from tests.fake_llamacpp import _handler
from http.server import ThreadingHTTPServer
import threading


class FakeServerHandle:
    def __init__(self, factory, handler=_handler):
        """`factory()` returns a new engine (or router) each start; `handler(engine)` its HTTP handler."""
        self.factory, self.handler = factory, handler
        self.url = ""
        self.generation = 0
        self.engine = None
        self._server = None
        self._started = None
        self._port = 0

    def start(self) -> dict:
        if self._server is not None:
            raise RuntimeError("the server is already running; stop it first")
        self.generation += 1
        self.engine = self.factory()
        # a real process answers on the same address after a restart; so does the stand-in
        self._server = ThreadingHTTPServer(("127.0.0.1", self._port), self.handler(self.engine))
        self._port = self._server.server_address[1]
        threading.Thread(target=self._server.serve_forever, daemon=True).start()
        self.url = f"http://127.0.0.1:{self._port}"
        self._started = datetime.now(timezone.utc).isoformat()
        return self.info()

    def stop(self) -> None:
        if self._server is None:
            return
        self._server.shutdown()
        self._server.server_close()
        self._server = None

    def info(self) -> dict:
        running = self._server is not None
        return {"generation": self.generation, "pid": 1000 + self.generation if running else None,
                "started": self._started, "running": running}
