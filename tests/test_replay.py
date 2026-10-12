"""Recorded conversations become chat requests: calls and results take the OpenAI shape, a request at
turn t holds exactly the messages before t, a compaction keeps the greeting and resumes at the chosen
turn, and the bytes are deterministic."""
import json

import pytest

from prefix_mortality.config import load_controls_config
from prefix_mortality.replay import (assistant_turns, body_at, compacted, last_turn, longest, messages_before,
                                     midpoint_cut, midpoint_turn, to_openai)
from tests.test_m4 import CONTROLS

GREETING = {"role": "assistant", "content": "Hi! How can I help you today?", "tool_calls": None, "turn_idx": 0,
            "timestamp": "2025-06-05T16:05:51.189310", "cost": 0.0, "usage": None}


def _sim(task_id="7", turns=3):
    """greeting, then `turns` rounds of user -> assistant(call) -> tool -> assistant."""
    msgs = [dict(GREETING)]
    for i in range(turns):
        msgs.append({"role": "user", "content": f"question {i} of {task_id}", "tool_calls": None, "turn_idx": len(msgs)})
        msgs.append({"role": "assistant", "content": f"checking {i} of {task_id}", "turn_idx": len(msgs),
                     "tool_calls": [{"arguments": {"z": i, "a": "x"}, "id": f"call_{i}", "name": "look", "requestor": "assistant"}]})
        msgs.append({"role": "tool", "content": json.dumps({"r": i}), "error": False, "id": f"call_{i}",
                     "requestor": "assistant", "turn_idx": len(msgs)})
        msgs.append({"role": "assistant", "content": f"answer {i} of {task_id}", "tool_calls": None, "turn_idx": len(msgs)})
    return {"task_id": task_id, "trial": 0, "messages": msgs}


def test_to_openai_shapes_calls_and_results():
    call = to_openai(_sim()["messages"][2])
    assert call == {"role": "assistant", "content": "checking 0 of 7",
                    "tool_calls": [{"id": "call_0", "type": "function",
                                    "function": {"name": "look", "arguments": '{"a": "x", "z": 0}'}}]}
    result = to_openai(_sim()["messages"][3])
    assert result == {"role": "tool", "tool_call_id": "call_0", "content": '{"r": 0}'}
    assert to_openai(GREETING) == {"role": "assistant", "content": "Hi! How can I help you today?"}


def test_body_at_turn_holds_exactly_the_messages_before_it(tmp_path):
    (tmp_path / "controls.toml").write_text(CONTROLS, encoding="utf-8")
    cfg = load_controls_config(tmp_path / "controls.toml", tmp_path)
    sim = _sim()
    assert assistant_turns(sim) == [0, 2, 4, 6, 8, 10, 12]
    body = json.loads(body_at(cfg, "SYS", [{"type": "function", "function": {"name": "look"}}], sim, 4))
    assert [m["role"] for m in body["messages"]] == ["system", "assistant", "user", "assistant", "tool"]
    assert body["messages"][0]["content"] == "SYS" and body["max_tokens"] == 1 and body["stream"] is False
    assert "model" not in body and "chat_template_kwargs" not in body
    only_system = json.loads(body_at(cfg, "SYS", [], sim, 0))
    assert [m["role"] for m in only_system["messages"]] == ["system"]
    with_extras = json.loads(body_at(cfg, "SYS", [], sim, 2, model="a", template_kwargs={"tools_in_user_message": False}))
    assert with_extras["model"] == "a" and with_extras["chat_template_kwargs"] == {"tools_in_user_message": False}
    with pytest.raises(ValueError, match="not an assistant turn"):
        messages_before(sim, 1)


def test_compacted_trims_or_summarises_from_the_first_user_message_to_the_cut(tmp_path):
    sim = _sim(turns=3)                       # 13 messages; assistant turns at 0,2,4,6,8,10,12; users at 1,5,9
    k, cut, t = midpoint_turn(sim), midpoint_cut(sim), last_turn(sim)
    assert (k, cut, t) == (6, 5, 12)
    out, new_t = compacted(sim, t, cut, "SUMMARY")
    roles = [m["role"] for m in out["messages"]]
    assert roles == ["assistant", "user", "user", "assistant", "tool", "assistant", "user", "assistant", "tool", "assistant"]
    assert out["messages"][1]["content"] == "SUMMARY" and out["messages"][2]["content"] == "question 1 of 7"
    assert new_t == 9 and out["messages"][new_t]["content"] == "answer 2 of 7"
    trimmed, new_t2 = compacted(sim, t, cut, None)
    assert [m["role"] for m in trimmed["messages"]] == roles[:1] + roles[2:]
    assert new_t2 == 8 and trimmed["messages"][new_t2]["content"] == "answer 2 of 7"
    assert out["task_id"] == sim["task_id"] and sim["messages"][1]["content"] == "question 0 of 7"   # the source is untouched
    with pytest.raises(ValueError, match="removes messages from"):
        compacted(sim, t, 0, "SUMMARY")
    with pytest.raises(ValueError, match="not a user message"):
        compacted(sim, t, 6, "SUMMARY")


def test_longest_orders_by_assistant_turns_then_task_id():
    sims = [_sim("10", 2), _sim("9", 3), _sim("3", 3), _sim("1", 1)]
    assert [s["task_id"] for s in longest(sims, 3)] == ["3", "9", "10"]


def test_body_bytes_are_deterministic(tmp_path):
    (tmp_path / "controls.toml").write_text(CONTROLS, encoding="utf-8")
    cfg = load_controls_config(tmp_path / "controls.toml", tmp_path)
    a = body_at(cfg, "SYS", [], _sim(), 4)
    b = body_at(cfg, "SYS", [], _sim(), 4)
    assert a == b and b"\n" not in a
