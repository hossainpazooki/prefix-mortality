"""The process handle starts a real subprocess and waits for its health, stops it, and counts
generations; the stand-ins restart into a fresh engine with only the save store surviving, and the
router stand-in routes by model, lists what is loaded, and unloads the least recently used child past
models_max."""
import json
import sys
import urllib.request

import pytest

from prefix_mortality.llamacpp import Client
from prefix_mortality.procs import Subprocess, wait_healthy
from tests.fake_llamacpp import Engine
from tests.fake_procs import FakeServerHandle
from tests.fake_router import serve_router

HEALTH_SERVER = '''
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer
class H(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def do_GET(self):
        body = b'{"status":"ok"}' if self.path == "/health" else b'{}'
        self.send_response(200 if self.path == "/health" else 404)
        self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body)
HTTPServer(("127.0.0.1", int(sys.argv[1])), H).serve_forever()
'''


def _free_port():
    import socket
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def test_subprocess_handle_starts_waits_for_health_and_stops(tmp_path):
    script = tmp_path / "health.py"
    script.write_text(HEALTH_SERVER, encoding="utf-8")
    port = _free_port()
    h = Subprocess([sys.executable, str(script), str(port)], f"http://127.0.0.1:{port}", tmp_path / "server.log",
                   start_timeout_seconds=30)
    info = h.start()
    assert info["generation"] == 1 and info["running"] and isinstance(info["pid"], int)
    with urllib.request.urlopen(h.url + "/health", timeout=5) as r:
        assert r.status == 200
    with pytest.raises(RuntimeError, match="already running"):
        h.start()
    h.stop()
    assert h.info()["running"] is False and h.info()["pid"] is None
    assert h.start()["generation"] == 2
    h.stop()
    log = (tmp_path / "server.log").read_text(encoding="utf-8")
    assert log.count("=== generation") == 2


def test_wait_healthy_times_out_on_nothing(tmp_path):
    with pytest.raises(RuntimeError, match="did not answer"):
        wait_healthy(f"http://127.0.0.1:{_free_port()}", timeout_seconds=1.0, poll_seconds=0.2)


def test_a_restart_forgets_the_slots_and_the_save_store_survives():
    store = {}
    h = FakeServerHandle(lambda: Engine(slots=1, n_ctx=100000, save_store=store))
    h.start()
    c = Client(h.url, 10.0)
    body = json.dumps({"messages": [{"role": "system", "content": "s"}, {"role": "user", "content": "u " * 50}]}).encode()
    c.chat(body)
    assert c.chat(body)["timings"]["cache_n"] > 0
    saved = c._call("/slots/0?action=save", json.dumps({"filename": "a.bin"}).encode())
    assert saved["n_saved"] > 0
    h.stop()
    h.start()
    c = Client(h.url, 10.0)
    assert c.chat(body)["timings"]["cache_n"] == 0                       # a fresh process holds nothing
    c._call("/slots/0?action=restore", json.dumps({"filename": "a.bin"}).encode())
    assert c.chat(body)["timings"]["cache_n"] == saved["n_saved"] - 1   # the restored slot: identical resend
    assert h.info()["generation"] == 2
    h.stop()


def test_the_router_routes_by_model_lists_the_loaded_set_and_unloads_the_lru_child_past_models_max():
    factories = {"a": lambda: Engine(slots=4, n_ctx=100000), "b": lambda: Engine(slots=4, n_ctx=50000)}
    with serve_router(factories, models_max=1) as (url, router):
        c = Client(url, 10.0)
        props = c.props()
        assert props["role"] == "router" and props["default_generation_settings"]["n_ctx"] == 0
        assert [m["status"]["value"] for m in c._call("/models", None)["data"]] == ["unloaded", "unloaded"]
        body_a = json.dumps({"model": "a", "messages": [{"role": "system", "content": "s"}, {"role": "user", "content": "hello there friend"}]}).encode()
        body_b = json.dumps({"model": "b", "messages": [{"role": "system", "content": "s"}, {"role": "user", "content": "hello there friend"}]}).encode()
        assert c.chat(body_a)["model"] == "a" and router.loaded() == ["a"]
        assert c.chat(body_a)["timings"]["cache_n"] > 0
        assert c.chat(body_b)["model"] == "b" and router.loaded() == ["b"]            # a unloaded (models_max 1)
        assert c.chat(body_a)["timings"]["cache_n"] == 0 and router.loaded() == ["a"]  # a reloaded: nothing held
        assert c._call("/props?model=b", None)["default_generation_settings"]["n_ctx"] == 50000
        assert [t["piece"] for t in c.tokenize("hello there", model="a")] == ["hello", " ", "there"]
    with serve_router(factories, models_max=4) as (url, router):
        c = Client(url, 10.0)
        c._call("/models/load", json.dumps({"model": "a"}).encode())
        c._call("/models/load", json.dumps({"model": "b"}).encode())
        assert router.loaded() == ["a", "b"]
        c.chat(body_a)
        c.chat(body_b)
        assert c.chat(body_a)["timings"]["cache_n"] > 0                                # a kept its slot
