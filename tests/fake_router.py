"""A stand-in for llama.cpp's router mode, for tests only.

It follows what was read at the pinned commit (tools/server/server.cpp 205-248, server-models.cpp
264-384, 1074-1090, 1931-1960): POST /v1/chat/completions, /apply-template, /tokenize and /slots/* are
forwarded to the child named by the body's `model`, loading it first when it is not running
(autoload); GET /props?model=NAME is forwarded, bare GET /props is the router's own (`role: router`,
no slot context); GET /models lists every child with its status; POST /models/load loads one. Loading
beyond `models_max` unloads the least recently used idle child, whose process — and every prompt it
held — is gone; a child loaded again is a fresh process with nothing held. Each child is a
`fake_llamacpp.Engine` built by its factory, so a child's slots and cache behave as the single-server
stand-in's do.
"""
import json
import threading
import time
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from tests.fake_llamacpp import ContextExceeded, NotSupported, TemplateError


class Router:
    def __init__(self, factories: dict, models_max: int, build_info: str = "b11235-6c7a87f"):
        self.factories, self.models_max, self.build_info = dict(factories), models_max, build_info
        self.children: dict = {}            # name -> Engine (loaded)
        self.last_used: dict = {}           # name -> monotonic
        self.loads = 0

    def loaded(self) -> list[str]:
        return sorted(self.children)

    def load(self, name: str) -> None:
        if name not in self.factories:
            raise KeyError(name)
        if name in self.children:
            return
        while len(self.children) >= self.models_max:
            victim = min(self.children, key=lambda n: self.last_used.get(n, -1.0))
            del self.children[victim]                                 # the process and its prompts are gone
        self.children[name] = self.factories[name]()
        self.children[name].model_name = name
        self.last_used[name] = time.monotonic()
        self.loads += 1

    def child(self, name: str, autoload: bool = True):
        if name not in self.children:
            if not autoload:
                raise KeyError(name)
            self.load(name)
        self.last_used[name] = time.monotonic()
        return self.children[name]

    def models_json(self) -> dict:
        return {"object": "list", "data": [{"id": n, "object": "model", "status": {"value": "loaded" if n in self.children else "unloaded"}}
                                            for n in sorted(self.factories)]}


def _handler(router: Router):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def _reply(self, payload: dict, status: int = 200):
            data = json.dumps(payload).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def _child_props(self, engine) -> dict:
            settings = {"n_ctx": engine.n_ctx} if engine.report_n_ctx else {}
            return {"build_info": engine.build_info, "total_slots": len(engine.slots), "model_alias": engine.model_name,
                    "default_generation_settings": settings, "is_sleeping": engine.is_sleeping()}

        def do_GET(self):
            u = urlparse(self.path)
            q = {k: v[0] for k, v in parse_qs(u.query).items()}
            if u.path == "/health":
                self._reply({"status": "ok"})
            elif u.path == "/props":
                name = q.get("model", "")
                if not name:
                    self._reply({"role": "router", "max_instances": router.models_max, "build_info": router.build_info,
                                 "model_alias": "llama-server", "default_generation_settings": {"n_ctx": 0}})
                else:
                    try:
                        self._reply(self._child_props(router.child(name)))
                    except KeyError:
                        self._reply({"error": {"code": 404, "message": "model is not found", "type": "not_found_error"}}, 404)
            elif u.path in ("/models", "/v1/models"):
                self._reply(router.models_json())
            else:
                self._reply({"error": {"code": 404, "message": "not found", "type": "not_found_error"}}, 404)

        def do_POST(self):
            u = urlparse(self.path)
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])).decode("utf-8"))
            try:
                if u.path == "/models/load":
                    name = body.get("model", "")
                    if name in router.children:
                        self._reply({"error": {"code": 400, "message": "model is already running", "type": "invalid_request_error"}}, 400)
                        return
                    router.load(name)
                    self._reply({"success": True})
                    return
                name = body.get("model", "")
                engine = router.child(name)
                if u.path == "/apply-template":
                    self._reply({"prompt": engine.render(body)})
                elif u.path == "/tokenize":
                    self._reply({"tokens": engine.tokenize(body["content"])})
                elif u.path.startswith("/slots/"):
                    action = {k: v[0] for k, v in parse_qs(u.query).items()}.get("action", "")
                    self._reply(engine.slot_action(int(u.path.rsplit("/", 1)[1]), action, body.get("filename", "")))
                else:
                    self._reply(engine.chat(body))
            except KeyError:
                self._reply({"error": {"code": 404, "message": "model is not found", "type": "not_found_error"}}, 404)
            except ContextExceeded as e:
                self._reply({"error": {"code": 400, "message": str(e), "type": "exceed_context_size_error"}}, 400)
            except NotSupported as e:
                self._reply({"error": {"code": 501, "message": str(e), "type": "not_supported_error"}}, 501)
            except TemplateError as e:
                self._reply({"error": {"code": 400, "message": str(e), "type": "invalid_request_error"}}, 400)
    return Handler


@contextmanager
def serve_router(factories: dict, models_max: int):
    router = Router(factories, models_max)
    server = ThreadingHTTPServer(("127.0.0.1", 0), _handler(router))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}", router
    finally:
        server.shutdown()
        server.server_close()
