"""A stand-in for a llama.cpp server, for tests only.

It follows the two rules read from the pinned source: reuse is the longest common token prefix with
what the single slot holds, and a prompt that is wholly held still has its last token processed. The
other modes break one of those on purpose, so a test can show the controls going red.
"""
import json
import re
import threading
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

MODES = ("faithful", "no_cache", "sticky", "no_fields", "clock")
_PIECE = re.compile(r"\s+|\w+|[^\w\s]")


class Engine:
    def __init__(self, mode: str = "faithful", build_info: str = "b11235-6c7a87f"):
        assert mode in MODES, mode
        self.mode, self.build_info = mode, build_info
        self.slot: list[int] = []
        self.ids: dict[str, int] = {}
        self.renders = 0

    def render(self, body: dict) -> str:
        self.renders += 1
        clock = f"tick {self.renders}\n" if self.mode == "clock" else ""
        system = "".join(m["content"] for m in body["messages"] if m["role"] == "system")
        user = "".join(m["content"] for m in body["messages"] if m["role"] == "user")
        tools = "\n".join(json.dumps(t) for t in body.get("tools") or [])
        return f"<|system|>\n{clock}{system}\n<tools>\n{tools}\n</tools>\n<|user|>\n{user}\n<|assistant|>\n"

    def tokenize(self, text: str) -> list[dict]:
        return [{"id": self.ids.setdefault(p, len(self.ids) + 1), "piece": p} for p in _PIECE.findall(text)]

    def chat(self, body: dict) -> dict:
        ids = [t["id"] for t in self.tokenize(self.render(body))]
        n, reuse = len(ids), 0
        while reuse < min(n, len(self.slot)) and ids[reuse] == self.slot[reuse]:
            reuse += 1
        if reuse == n and n > 0:
            reuse -= 1
        if self.mode == "no_cache":
            reuse = 0
        if self.mode == "sticky":
            reuse = n - 1
        self.slot = ids
        out = {"choices": [{"message": {"role": "assistant", "content": "ok"}}],
               "usage": {"prompt_tokens": n, "completion_tokens": 1, "total_tokens": n + 1,
                         "prompt_tokens_details": {"cached_tokens": reuse}},
               "timings": {"cache_n": reuse, "prompt_n": n - reuse, "predicted_n": 1}}
        if self.mode == "no_fields":
            del out["timings"], out["usage"]["prompt_tokens_details"]
        return out


def _handler(engine: Engine):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def _reply(self, payload: dict):
            data = json.dumps(payload).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            self._reply({"build_info": engine.build_info, "total_slots": 1,
                         "default_generation_settings": {"n_ctx": 8192}})

        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])).decode("utf-8"))
            if self.path == "/apply-template":
                self._reply({"prompt": engine.render(body)})
            elif self.path == "/tokenize":
                self._reply({"tokens": engine.tokenize(body["content"])})
            else:
                self._reply(engine.chat(body))
    return Handler


@contextmanager
def serve(mode: str = "faithful", build_info: str = "b11235-6c7a87f"):
    engine = Engine(mode, build_info)
    server = ThreadingHTTPServer(("127.0.0.1", 0), _handler(engine))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}", engine
    finally:
        server.shutdown()
        server.server_close()
