"""A stand-in for a vLLM OpenAI-compatible server, for tests only.

It follows what was read at the pinned commit (config/vllm.toml):
  * the prefix cache is a store of hashed FULL blocks of `block_size` tokens; a request's hit is the
    longest chain of stored blocks that prefixes its prompt, capped at the prompt length minus one
    ("we must recompute the last token to obtain logits", vllm/v1/core/kv_cache_manager.py 290-295),
    so the hit is the largest block multiple strictly below n when everything matches;
  * after a request finishes, every full block of its sequence INCLUDING the generated tokens is
    stored; `created_cache_tokens` = max(0, min(hashed_total, n) - hit), with hashed_total the
    largest full-block boundary of the finished sequence (PrefillStats.finalize over
    estimate_cached_tokens, scheduler.py 2184-2188);
  * `cached_tokens` and `created_cache_tokens` ride in `usage.prompt_tokens_details` only when the
    server enables prompt-token details; without the flag the key is absent;
  * `POST /tokenize` takes the chat shape and returns ids, BPE-internal pieces and the count;
    `POST /detokenize` returns the text; `GET /version` and `GET /v1/models` identify the server.
  * the pieces do not join back to the rendered text (byte-level BPE); the fake fakes that too, by
    emitting a marker piece for whitespace.

Modes beyond "faithful" break a rule on purpose so a driver can be shown going red: "no_details"
omits prompt_tokens_details; "no_cache" serves with the prefix cache off (hit 0, nothing stored);
"sticky" reports a full-looking hit for every request. This file is written from the same reading as
the drivers it tests: a pass shows they agree with the reading, not that the reading is right.
"""
import json
import re
import threading
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

MODES = ("faithful", "no_details", "no_cache", "sticky")
_SPECIAL = re.compile(r"(<\|im_start\|>|<\|im_end\|>)")
_PIECE = re.compile(r"\s+|\w+|[^\w\s]")
GEN_TOKENS = 1                              # the controls generate one token


class Engine:
    def __init__(self, mode: str = "faithful", version: str = "0.31.1rc1.dev8+gb6d8e8afd",
                 served: str = "qwen3-1.7b", block_size: int = 16):
        assert mode in MODES, mode
        self.mode, self.version, self.served, self.block_size = mode, version, served, block_size
        self.ids: dict[str, int] = {}
        self.blocks: set[tuple] = set()      # a stored full block: (index, token ids of blocks 0..index)
        self.requests = 0

    def render(self, messages: list, tools: list | None) -> str:
        out = ""
        for m in messages:
            out += f"<|im_start|>{m['role']}\n{m['content']}"
            if m["role"] == "system" and tools:
                out += "\n<tools>" + json.dumps(tools) + "</tools>"
            out += "<|im_end|>\n"
        return out + "<|im_start|>assistant\n"

    def tokenize(self, text: str) -> list[dict]:
        """Chat markers are single tokens, as the real tokenizer's special tokens are; whitespace
        pieces get a marker string, as byte-level BPE pieces are not the text itself."""
        toks = []
        for part in _SPECIAL.split(text):
            pieces = [part] if _SPECIAL.fullmatch(part) else _PIECE.findall(part)
            for p in pieces:
                piece = "Ċ" if p.isspace() else p
                toks.append({"id": self.ids.setdefault(p, len(self.ids) + 1), "piece": piece})
        return toks

    def _chain(self, ids: list[int], k: int) -> tuple:
        b = self.block_size
        return (k, tuple(ids[: k * b]))

    def _hit(self, ids: list[int]) -> int:
        if self.mode == "no_cache":
            return 0
        n, b = len(ids), self.block_size
        k_cap = (n - 1) // b                                      # the hit is capped at n - 1, block-aligned
        if self.mode == "sticky":
            return k_cap * b
        k = 0
        while k + 1 <= k_cap and self._chain(ids, k + 1) in self.blocks:
            k += 1
        return k * b

    def chat(self, body: dict) -> dict:
        ids = [t["id"] for t in self.tokenize(self.render(body["messages"], body.get("tools")))]
        n = len(ids)
        cached = self._hit(ids)
        self.requests += 1
        gen = [-self.requests] * GEN_TOKENS                       # generated ids never collide with prompt ids
        seq = ids + gen
        hashed_total = (len(seq) // self.block_size) * self.block_size
        if self.mode != "no_cache":
            for k in range(1, len(seq) // self.block_size + 1):
                self.blocks.add(self._chain(seq, k))
        created = max(0, min(hashed_total, n) - cached)
        out = {"choices": [{"message": {"role": "assistant", "content": "ok"}}],
               "usage": {"prompt_tokens": n, "completion_tokens": GEN_TOKENS, "total_tokens": n + GEN_TOKENS,
                         "prompt_tokens_details": {"cached_tokens": cached, "created_cache_tokens": created}}}
        if self.mode == "no_details":
            del out["usage"]["prompt_tokens_details"]
        return out


def _handler(engine: Engine):
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

        def do_GET(self):
            if self.path == "/version":
                self._reply({"version": engine.version})
            elif self.path == "/v1/models":
                self._reply({"object": "list", "data": [{"id": engine.served, "object": "model"}]})
            else:
                self._reply({"status": "ok"})

        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])).decode("utf-8"))
            if self.path == "/tokenize":
                if "prompt" in body:
                    toks = engine.tokenize(body["prompt"])
                else:
                    toks = engine.tokenize(engine.render(body["messages"], body.get("tools")))
                self._reply({"count": len(toks), "max_model_len": 16384, "tokens": [t["id"] for t in toks],
                             "token_strs": [t["piece"] for t in toks]})
            elif self.path == "/detokenize":
                back = {v: k for k, v in engine.ids.items()}
                self._reply({"prompt": "".join(back[i] for i in body["tokens"])})
            else:
                self._reply(engine.chat(body))
    return Handler


@contextmanager
def serve(mode: str = "faithful", **engine_kw):
    engine = Engine(mode, **engine_kw)
    server = ThreadingHTTPServer(("127.0.0.1", 0), _handler(engine))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}", engine
    finally:
        server.shutdown()
        server.server_close()
