"""Recorded agent conversations as chat requests.

A vendored tau2-bench simulation (`prefix_mortality.recorded`) is a list of messages in tau2's own
shape. Replaying it against an engine means sending, for each assistant turn t, the fixture's system
text and tool schemas followed by every message before t, in the OpenAI chat shape the engines parse:
an assistant message's `tool_calls` become `{id, type, function: {name, arguments}}` with the arguments
as a JSON string, and a tool result becomes `{role: tool, tool_call_id, content}`. Timestamps, costs
and usage are tau2's bookkeeping and are dropped.

A compaction replaces the messages from the first user message up to a later assistant turn with one
summary message, as an agent harness does when its context grows; the turns after it are kept as
recorded. Nothing here talks to an engine; `body_at` returns the bytes a driver sends and hashes.
"""
import json

from prefix_mortality.config import ControlsConfig
from prefix_mortality.record import body_bytes

SUMMARY_ROLE = "user"


def to_openai(m: dict) -> dict:
    """One recorded message in the OpenAI chat shape."""
    role = m.get("role")
    content = m.get("content")
    if content is not None and not isinstance(content, str):
        content = json.dumps(content, ensure_ascii=False, sort_keys=True)
    if role == "tool":
        return {"role": "tool", "tool_call_id": m["id"], "content": content or ""}
    out = {"role": role, "content": content or ""}
    calls = m.get("tool_calls") or []
    if role == "assistant" and calls:
        out["tool_calls"] = [{"id": tc["id"], "type": "function",
                              "function": {"name": tc["name"],
                                           "arguments": json.dumps(tc.get("arguments") or {}, ensure_ascii=False,
                                                                   sort_keys=True)}}
                             for tc in calls]
    return out


def assistant_turns(sim: dict) -> list[int]:
    """Indexes of the assistant messages, in order."""
    return [i for i, m in enumerate(sim["messages"]) if m.get("role") == "assistant"]


def first_user(sim: dict) -> int:
    for i, m in enumerate(sim["messages"]):
        if m.get("role") == "user":
            return i
    raise ValueError(f"simulation {sim.get('task_id')!r} has no user message")


def messages_before(sim: dict, turn_index: int) -> list[dict]:
    """The OpenAI-shaped messages a request at assistant turn `turn_index` carries: everything before it."""
    msgs = sim["messages"]
    if not 0 <= turn_index < len(msgs) or msgs[turn_index].get("role") != "assistant":
        raise ValueError(f"message {turn_index} of simulation {sim.get('task_id')!r} is not an assistant turn")
    return [to_openai(m) for m in msgs[:turn_index]]


def body_at(cfg: ControlsConfig, system_text: str, tools: list, sim: dict, turn_index: int,
            model: str | None = None, template_kwargs: dict | None = None) -> bytes:
    body: dict = {"messages": [{"role": "system", "content": system_text}, *messages_before(sim, turn_index)],
                  "tools": tools, "max_tokens": cfg.max_tokens, "temperature": cfg.temperature, "stream": False}
    if model is not None:
        body["model"] = model
    if template_kwargs is not None:
        body["chat_template_kwargs"] = template_kwargs
    return body_bytes(body)


def compacted(sim: dict, turn_index: int, cut_index: int, summary: str | None) -> tuple[dict, int]:
    """The simulation with the messages from the first user message up to (not including) the user
    message at `cut_index` removed — a trim — or replaced by one summary message when `summary` is a
    string; and the index assistant turn `turn_index` has in the result. The greeting before the first
    user message is kept, and the kept tail begins with the user message at the cut."""
    msgs = sim["messages"]
    start = first_user(sim)
    if not start < cut_index <= turn_index:
        raise ValueError(f"a compaction removes messages from {start} up to the cut; got cut {cut_index}, turn {turn_index}")
    if msgs[cut_index].get("role") != "user":
        raise ValueError(f"message {cut_index} is not a user message; a compaction resumes at one")
    inserted = [] if summary is None else [{"role": SUMMARY_ROLE, "content": summary}]
    new_msgs = [*msgs[:start], *inserted, *msgs[cut_index:]]
    return {**sim, "messages": new_msgs}, turn_index - (cut_index - start) + len(inserted)


def midpoint_turn(sim: dict) -> int:
    """The assistant turn at the middle of the conversation: the (⌊T/2⌋ + 1)-th of T assistant turns."""
    turns = assistant_turns(sim)
    return turns[len(turns) // 2]


def midpoint_cut(sim: dict) -> int:
    """The user message a compaction resumes at: the last one before the midpoint assistant turn."""
    k = midpoint_turn(sim)
    for i in range(k, -1, -1):
        if sim["messages"][i].get("role") == "user":
            return i
    raise ValueError(f"simulation {sim.get('task_id')!r} has no user message before its midpoint turn")


def last_turn(sim: dict) -> int:
    return assistant_turns(sim)[-1]


def longest(sims: list[dict], count: int) -> list[dict]:
    """The `count` simulations with the most assistant turns; ties by task id, numerically where possible."""
    key = lambda s: (-len(assistant_turns(s)), (len(str(s["task_id"])), str(s["task_id"])))
    return sorted(sims, key=key)[:count]
