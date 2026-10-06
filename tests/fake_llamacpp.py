"""A stand-in for a llama.cpp server, for tests only.

It follows what was read in the pinned source (ledger entries 0002 and 0005):
  * reuse is the longest common token prefix with what the chosen slot holds, and a prompt that is
    wholly held still has its last token processed;
  * a request is given the slot whose prompt it resembles by more than `similarity` of its own
    length, else the least recently used slot;
  * a slot about to lose more than half of its prompt is copied to a cache first, and a cached
    prompt is restored only if at least a quarter of it would be kept;
  * when a request starts, every other slot is copied to the cache and cleared;
  * the cache keeps entries in arrival order and, given a byte limit, drops the oldest until a new
    entry fits; an entry is tokens x bytes per token (ledger entry 0011's successor reads this);
  * a request of at least the slot context in tokens is refused, as the server refuses it;
  * with `sleep_idle_seconds` >= 1, a server idle for that long (checked whenever it is asked
    anything, as the real one checks once a second) enters sleep: slots and cache are gone, and the
    next request that needs the model reloads it, with a new cache. GET /props is not a request of
    that kind: it reports `is_sleeping` and moves nothing. /apply-template and /tokenize wake a
    sleeping server but do not move an awake one's timer; a chat does both;
  * `expire_after_seconds` is a death no server at the pin has: a slot that forgets by time without
    sleeping. It exists so a test can show the driver reading one.

  * before rendering, a tool is rebuilt as the server does: `type`, then `function` with `name`,
    `description` (default empty) and `parameters` (default empty object), other keys dropped, the
    order inside `parameters` kept;
  * two template modes beyond `generic`: `llama` prints a date line first (`date_string`, default
    "26 Jul 2024") and puts the tools in the first non-system message unless `tools_in_user_message`
    is false, refusing when there is none; `qwen` appends an empty think block to the generation
    prompt when `enable_thinking` is false. Each ignores the other's arguments.

With one slot the clearing rule has nothing to clear. The other modes break a rule on purpose, so a test
can show a driver going red. This file is written from the same reading as the drivers it tests: a
pass shows they agree with the reading, not that the reading is right.
"""
import json
import re
import threading
import time
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

MODES = ("faithful", "no_cache", "sticky", "no_fields", "clock")
_PIECE = re.compile(r"\s+|\w+|[^\w\s]")


def _lcp(a: list[int], b: list[int]) -> int:
    n = 0
    while n < min(len(a), len(b)) and a[n] == b[n]:
        n += 1
    return n


class ContextExceeded(ValueError):
    pass


class TemplateError(ValueError):
    pass


TEMPLATES = ("generic", "llama", "qwen")


def _rebuild_tool(t: dict) -> dict:
    """What common_chat_tools_parse_oaicompat + _to_json_oaicompat do at the pin."""
    fn = t.get("function")
    if not isinstance(fn, dict) or "name" not in fn:
        raise TemplateError(f"Missing tool function: {json.dumps(t)}")
    return {"type": "function", "function": {"name": fn["name"], "description": fn.get("description", ""),
                                             "parameters": fn.get("parameters", {})}}


class Engine:
    def __init__(self, mode: str = "faithful", build_info: str = "b11235-6c7a87f", slots: int = 1,
                 similarity: float = 0.10, cache_limit_bytes: int | None = None, bytes_per_token: int = 1,
                 n_ctx: int = 8192, report_n_ctx: bool = True, template: str = "generic",
                 sleep_idle_seconds: int = -1, clock=time.monotonic, expire_after_seconds: float | None = None):
        assert mode in MODES, mode
        self.mode, self.build_info, self.similarity = mode, build_info, similarity
        self.cache_limit_bytes, self.bytes_per_token = cache_limit_bytes, bytes_per_token
        self.n_ctx, self.report_n_ctx = n_ctx, report_n_ctx
        assert template in TEMPLATES, template
        self.template = template
        self.sleep_idle_seconds, self.clock, self.expire_after_seconds = sleep_idle_seconds, clock, expire_after_seconds
        self.sleeping, self.reloads = False, 0
        self.last_task = clock()
        self.slots: list[list[int]] = [[] for _ in range(slots)]
        self.last_used = [-1] * slots
        self.cache: list[list[int]] = []
        self.ids: dict[str, int] = {}
        self.renders = self.requests = self.evictions = self.props_reads = 0

    def _forget(self) -> None:
        self.slots = [[] for _ in self.slots]
        self.cache = []

    def _tick(self) -> None:
        """What the server's loop does once a second, done whenever the stand-in is asked anything."""
        idle = self.clock() - self.last_task
        if self.sleep_idle_seconds >= 1 and not self.sleeping and idle >= self.sleep_idle_seconds:
            self.sleeping = True
            self._forget()
        if self.expire_after_seconds is not None and idle >= self.expire_after_seconds:
            self._forget()

    def _wake(self) -> None:
        """A call that needs the model: a sleeping server reloads it, with new slots and a new cache,
        and its timer restarts."""
        if self.sleeping:
            self.sleeping = False
            self.reloads += 1
            self.last_task = self.clock()

    def is_sleeping(self) -> bool:
        self._tick()
        return self.sleeping

    def _cache_add(self, ids: list[int]) -> None:
        """Arrival order; with a limit, the oldest entries go until the new one fits."""
        if self.cache_limit_bytes is not None:
            new = len(ids) * self.bytes_per_token
            while self.cache and sum(len(c) for c in self.cache) * self.bytes_per_token + new > self.cache_limit_bytes:
                self.cache.pop(0)
                self.evictions += 1
        self.cache.append(ids)

    def render(self, body: dict) -> str:
        self._tick()
        self._wake()
        self.renders += 1
        clock = f"tick {self.renders}\n" if self.mode == "clock" else ""
        kwargs = body.get("chat_template_kwargs") or {}
        system = "".join(m["content"] for m in body["messages"] if m["role"] == "system")
        rest = [m for m in body["messages"] if m["role"] != "system"]
        tools = [json.dumps(_rebuild_tool(t)) for t in body.get("tools") or []]
        tools_block = "<tools>\n" + "\n".join(tools) + "\n</tools>\n"
        if self.template == "llama":
            date = kwargs.get("date_string", "26 Jul 2024")
            out = f"<|system|>\nToday Date: {date}\n\n{clock}{system}\n"
            if tools and kwargs.get("tools_in_user_message", True):
                if not rest:
                    raise TemplateError("Cannot put tools in the first user message when there's no first user message!")
                first, rest = rest[0], rest[1:]
                out += "<|user|>\n" + "\n".join(tools) + "\n" + first["content"] + "\n"
            else:
                out += tools_block
            return out + "".join(f"<|{m['role']}|>\n{m['content']}\n" for m in rest) + "<|assistant|>\n"
        out = f"<|system|>\n{clock}{system}\n{tools_block}" + "".join(f"<|{m['role']}|>\n{m['content']}\n" for m in rest)
        out += "<|assistant|>\n"
        if self.template == "qwen" and kwargs.get("enable_thinking", True) is False:
            out += "<think>\n\n</think>\n\n"
        return out

    def tokenize(self, text: str) -> list[dict]:
        self._tick()
        self._wake()
        return [{"id": self.ids.setdefault(p, len(self.ids) + 1), "piece": p} for p in _PIECE.findall(text)]

    def _choose(self, ids: list[int]) -> int:
        """The slot for this prompt, after the cache has been given and asked what the source says."""
        best, where = 0.0, None
        for i, held in enumerate(self.slots):
            sim = _lcp(held, ids) / len(ids) if held else 0.0
            if sim > best and sim > self.similarity:
                best, where = sim, i
        if where is None:
            where, save = min(range(len(self.slots)), key=lambda i: self.last_used[i]), True
        else:
            save = _lcp(self.slots[where], ids) / len(self.slots[where]) < 0.5
        if save:
            held = self.slots[where]
            if held:
                self._cache_add(list(held))
            keep = _lcp(held, ids) / len(held) if held else -1.0
            sim, found = _lcp(held, ids) / len(ids), None
            for c in self.cache:
                k, s = _lcp(c, ids) / len(c), _lcp(c, ids) / len(ids)
                if k >= 0.25 and keep < k and sim < s:
                    keep, sim, found = k, s, c
            if found is not None:
                self.cache.remove(found)
                self.slots[where] = found
        return where

    def chat(self, body: dict) -> dict:
        self._tick()
        self._wake()
        ids = [t["id"] for t in self.tokenize(self.render(body))]
        n = len(ids)
        if n >= self.n_ctx:
            raise ContextExceeded(f"request ({n} tokens) exceeds the available context size ({self.n_ctx} tokens), "
                                  "try increasing it")
        where = self._choose(ids)
        reuse = _lcp(self.slots[where], ids)
        if reuse == n and n > 0:
            reuse -= 1
        if self.mode == "no_cache":
            reuse = 0
        if self.mode == "sticky":
            reuse = n - 1
        self.requests += 1
        self.last_task = self.clock()                    # a chat is a task: it restarts the idle timer
        self.slots[where], self.last_used[where] = ids, self.requests
        for i, held in enumerate(self.slots):           # every idle slot is copied to the cache and cleared
            if i != where and held:
                self._cache_add(held)
                self.slots[i] = []
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

        def _reply(self, payload: dict, status: int = 200):
            data = json.dumps(payload).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            engine.props_reads += 1
            settings = {"n_ctx": engine.n_ctx} if engine.report_n_ctx else {}
            self._reply({"build_info": engine.build_info, "total_slots": len(engine.slots),
                         "default_generation_settings": settings, "is_sleeping": engine.is_sleeping()})

        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])).decode("utf-8"))
            try:
                if self.path == "/apply-template":
                    self._reply({"prompt": engine.render(body)})
                elif self.path == "/tokenize":
                    self._reply({"tokens": engine.tokenize(body["content"])})
                else:
                    self._reply(engine.chat(body))
            except ContextExceeded as e:
                self._reply({"error": {"code": 400, "message": str(e), "type": "exceed_context_size_error"}}, 400)
            except TemplateError as e:
                self._reply({"error": {"code": 400, "message": str(e), "type": "invalid_request_error"}}, 400)
    return Handler


@contextmanager
def serve(mode: str = "faithful", build_info: str = "b11235-6c7a87f", slots: int = 1, **engine_kw):
    engine = Engine(mode, build_info, slots, **engine_kw)
    server = ThreadingHTTPServer(("127.0.0.1", 0), _handler(engine))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}", engine
    finally:
        server.shutdown()
        server.server_close()
