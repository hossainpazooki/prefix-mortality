"""Client for a vLLM OpenAI-compatible server: the five calls the V controls need, and nothing else.

Read at the pinned commit (config/vllm.toml), not assumed:
  * there is no apply-template endpoint; `POST /tokenize` accepts the chat shape itself (messages,
    tools, add_generation_prompt, return_token_strs) and returns the prompt's token ids, their
    pieces and the count, through the same template path as `/v1/chat/completions`
    (`vllm/entrypoints/serve/tokenize/protocol.py`);
  * `POST /detokenize` turns ids back into the prompt text;
  * the pieces are the tokenizer's internal strings (byte-level BPE: a newline is a `Ċ`), so joining
    them does NOT rebuild the rendered text, unlike llama.cpp's pieces. Nothing here joins them.
  * reuse is reported only with --enable-prompt-tokens-details, as
    `usage.prompt_tokens_details.cached_tokens` beside `created_cache_tokens`
    (`vllm/entrypoints/openai/chat_completion/serving.py` 90-109).

A field a response does not carry is returned as None. None is never turned into a number here.
"""
import json
import urllib.error
import urllib.request


class EngineError(RuntimeError):
    pass


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

    def version(self) -> str:
        v = self._call("/version", None).get("version")
        if not isinstance(v, str) or not v:
            raise EngineError("/version returned no version string")
        return v

    def model_ids(self) -> list[str]:
        data = self._call("/v1/models", None).get("data")
        if not isinstance(data, list):
            raise EngineError("/v1/models returned no data list")
        return [m.get("id") for m in data if isinstance(m, dict)]

    def prepare(self, body: bytes) -> dict:
        """The prompt as the server renders this chat body: token ids with pieces (from the chat-shaped
        /tokenize, the same template path as a chat) and the text (from /detokenize). Only the keys the
        tokenize endpoint knows are forwarded; the body's sampling keys do not shape the prompt."""
        chat = json.loads(body.decode("utf-8"))
        payload: dict = {"messages": chat["messages"], "add_generation_prompt": True, "return_token_strs": True}
        for key in ("model", "tools", "chat_template_kwargs"):
            if key in chat:
                payload[key] = chat[key]
        out = self._call("/tokenize", json.dumps(payload, ensure_ascii=False).encode("utf-8"))
        ids, pieces = out.get("tokens"), out.get("token_strs")
        if not isinstance(ids, list) or not isinstance(pieces, list) or len(ids) != len(pieces):
            raise EngineError("/tokenize returned no matching tokens and token_strs lists")
        if out.get("count") != len(ids):
            raise EngineError(f"/tokenize count {out.get('count')!r} does not equal its own token list length {len(ids)}")
        det = self._call("/detokenize", json.dumps({"model": chat.get("model"), "tokens": ids}).encode("utf-8"))
        rendered = det.get("prompt")
        if not isinstance(rendered, str):
            raise EngineError("/detokenize returned no prompt string")
        return {"rendered": rendered, "tokens": [{"id": int(i), "piece": str(p)} for i, p in zip(ids, pieces)]}

    def count_text(self, text: str) -> int:
        """Token count of bare text with no special tokens added: for scramble length matching only."""
        out = self._call("/tokenize", json.dumps({"prompt": text, "add_special_tokens": False},
                                                 ensure_ascii=False).encode("utf-8"))
        count = out.get("count")
        if not isinstance(count, int):
            raise EngineError("/tokenize returned no count for a text prompt")
        return count

    def chat(self, body: bytes) -> dict:
        """Send exactly these bytes; the caller hashes the same bytes."""
        return self._call("/v1/chat/completions", body)


def _int_or_none(v) -> int | None:
    return v if isinstance(v, int) and not isinstance(v, bool) else None


def observed(response: dict) -> dict:
    """What a vLLM response reports about reuse. A missing field is None: NOT MEASURABLE, never 0."""
    usage = response.get("usage") if isinstance(response.get("usage"), dict) else {}
    details = usage.get("prompt_tokens_details") if isinstance(usage.get("prompt_tokens_details"), dict) else {}
    return {"usage_prompt_tokens": _int_or_none(usage.get("prompt_tokens")),
            "usage_cached_tokens": _int_or_none(details.get("cached_tokens")),
            "usage_created_cache_tokens": _int_or_none(details.get("created_cache_tokens"))}
