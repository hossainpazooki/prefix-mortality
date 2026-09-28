"""Client for a llama.cpp server: the four calls the controls need, and nothing else.

Read at the pinned commit (UPSTREAM.md), not assumed:
  * `POST /apply-template` parses its body exactly as `/v1/chat/completions` does and returns the
    rendered prompt, so tools and template arguments are rendered the way a real request renders them.
  * A chat prompt is tokenized with special tokens added and parsed; `tokenize` asks for the same.
  * A response reports reuse twice: `timings.cache_n` / `timings.prompt_n`, and
    `usage.prompt_tokens_details.cached_tokens`.

A field a response does not carry is returned as None. None is never turned into a number here.
"""
import json
import urllib.error
import urllib.request


class EngineError(RuntimeError):
    pass


def _piece(p) -> str:
    """A token piece is a string, or a list of byte values when the bytes are not valid text alone."""
    return p if isinstance(p, str) else bytes(p).decode("utf-8", "replace")


class Client:
    def __init__(self, base_url: str, timeout_seconds: float):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout_seconds

    def _call(self, path: str, body: bytes | None) -> dict:
        req = urllib.request.Request(self.base_url + path, data=body, method="GET" if body is None else "POST",
                                     headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as r:
                return json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            raise EngineError(f"{path} returned HTTP {e.code}: {e.read().decode('utf-8', 'replace')[:300]}") from e
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as e:
            raise EngineError(f"{path} failed: {e}") from e

    def props(self) -> dict:
        return self._call("/props", None)

    def render(self, body: bytes) -> str:
        out = self._call("/apply-template", body)
        if not isinstance(out.get("prompt"), str):
            raise EngineError("/apply-template returned no `prompt` string")
        return out["prompt"]

    def tokenize(self, text: str) -> list[dict]:
        """[{id, piece}] for `text`, tokenized the way the server tokenizes a chat prompt."""
        body = json.dumps({"content": text, "add_special": True, "parse_special": True, "with_pieces": True})
        toks = self._call("/tokenize", body.encode("utf-8")).get("tokens")
        if not isinstance(toks, list) or not all(isinstance(t, dict) and "id" in t and "piece" in t for t in toks):
            raise EngineError("/tokenize returned no list of {id, piece}")
        return [{"id": int(t["id"]), "piece": _piece(t["piece"])} for t in toks]

    def chat(self, body: bytes) -> dict:
        """Send exactly these bytes; the caller hashes the same bytes."""
        return self._call("/v1/chat/completions", body)


def _int_or_none(v) -> int | None:
    return v if isinstance(v, int) and not isinstance(v, bool) else None


def observed(response: dict) -> dict:
    """What the response reports about reuse. A missing field is None: NOT MEASURABLE, never 0."""
    timings = response.get("timings") if isinstance(response.get("timings"), dict) else {}
    usage = response.get("usage") if isinstance(response.get("usage"), dict) else {}
    details = usage.get("prompt_tokens_details") if isinstance(usage.get("prompt_tokens_details"), dict) else {}
    return {"cache_n": _int_or_none(timings.get("cache_n")),
            "prompt_n": _int_or_none(timings.get("prompt_n")),
            "usage_prompt_tokens": _int_or_none(usage.get("prompt_tokens")),
            "usage_cached_tokens": _int_or_none(details.get("cached_tokens"))}
