"""The stand-in does to a tool what the pinned server does before rendering, and its llama and qwen
modes follow the two templates' behaviours the templating experiment relies on."""
import json

import pytest

from prefix_mortality.clock import seconds_between
from prefix_mortality.llamacpp import Client, EngineError
from prefix_mortality.record import utc_now
from tests.fake_clock import FakeClock
from tests.fake_llamacpp import Engine, serve

TOOL = {"type": "function", "function": {"name": "a", "description": "Look it up.",
                                         "parameters": {"properties": {"id": {}, "day": {}}, "type": "object"}}}


def _body(tools, messages=None, kwargs=None):
    b = {"messages": messages or [{"role": "system", "content": "sys"}, {"role": "user", "content": "Hello."}],
         "tools": tools, "max_tokens": 1, "temperature": 0.0, "stream": False}
    if kwargs is not None:
        b["chat_template_kwargs"] = kwargs
    return b


def test_generic_render_is_unchanged_for_a_tool_already_in_the_servers_order():
    e = Engine()
    assert e.render(_body([TOOL])) == f"<|system|>\nsys\n<tools>\n{json.dumps(TOOL)}\n</tools>\n<|user|>\nHello.\n<|assistant|>\n"


def test_tool_rebuild_fixes_top_level_order_drops_unknown_keys_and_keeps_parameter_order():
    e = Engine()
    swapped = {"function": {"name": "a", "parameters": TOOL["function"]["parameters"], "description": "Look it up.",
                            "x-version": "2"}, "type": "function"}
    assert e.render(_body([swapped])) == e.render(_body([TOOL]))
    reordered = json.loads(json.dumps(TOOL))
    reordered["function"]["parameters"]["properties"] = {"day": {}, "id": {}}
    assert e.render(_body([reordered])) != e.render(_body([TOOL]))
    missing = {"type": "function", "function": {"name": "a"}}
    assert '"description": ""' in e.render(_body([missing])) and '"parameters": {}' in e.render(_body([missing]))


def test_llama_mode_prints_the_date_before_the_system_text_and_honours_the_override():
    e = Engine(template="llama")
    default = e.render(_body([TOOL]))
    assert default.startswith("<|system|>\nToday Date: 26 Jul 2024\n\nsys\n")
    changed = e.render(_body([TOOL], kwargs={"date_string": "02 Oct 2026"}))
    assert changed.startswith("<|system|>\nToday Date: 02 Oct 2026\n\nsys\n")
    assert default[len("<|system|>\nToday Date: 26 Jul 2024"):] == changed[len("<|system|>\nToday Date: 02 Oct 2026"):]


def test_llama_mode_puts_tools_in_the_first_user_message_by_default_and_in_the_system_block_when_told():
    e = Engine(template="llama")
    default = e.render(_body([TOOL]))
    assert "<|user|>\n" + json.dumps(TOOL) + "\nHello.\n" in default and "<tools>" not in default
    in_system = e.render(_body([TOOL], kwargs={"tools_in_user_message": False}))
    assert "<tools>\n" + json.dumps(TOOL) + "\n</tools>\n" in in_system and in_system.index("</tools>") < in_system.index("<|user|>")
    with pytest.raises(ValueError, match="no first user message"):
        e.render(_body([TOOL], messages=[{"role": "system", "content": "sys"}]))


def test_llama_mode_ignores_enable_thinking_and_qwen_mode_ignores_the_date():
    llama, qwen = Engine(template="llama"), Engine(template="qwen")
    assert llama.render(_body([TOOL], kwargs={"enable_thinking": False})) == llama.render(_body([TOOL], kwargs={}))
    assert qwen.render(_body([TOOL], kwargs={"date_string": "02 Oct 2026"})) == qwen.render(_body([TOOL], kwargs={}))


def test_qwen_mode_changes_only_the_tail_when_thinking_is_off():
    e = Engine(template="qwen")
    on, off = e.render(_body([TOOL], kwargs={"enable_thinking": True})), e.render(_body([TOOL], kwargs={"enable_thinking": False}))
    assert off.startswith(on) and off[len(on):] == "<think>\n\n</think>\n\n"


def test_the_handler_turns_a_template_error_into_http_400():
    with serve(template="llama") as (url, _):
        client = Client(url, 30.0)
        with pytest.raises(EngineError, match="HTTP 400"):
            client.render(json.dumps(_body([TOOL], messages=[{"role": "system", "content": "sys"}])).encode("utf-8"))


BODY = {"messages": [{"role": "system", "content": "run abc rules of the house"}, {"role": "user", "content": "Hello."}]}


def test_the_stand_in_sleeps_after_the_idle_seconds_and_forgets_on_reload():
    clock = FakeClock()
    e = Engine(slots=4, sleep_idle_seconds=60, clock=clock.seconds)
    n = e.chat(BODY)["usage"]["prompt_tokens"]
    clock.advance(30)
    assert e.is_sleeping() is False
    assert e.chat(BODY)["timings"]["cache_n"] == n - 1, "the held slot answers an identical resend"
    clock.advance(59)
    assert e.is_sleeping() is False
    clock.advance(1)
    assert e.is_sleeping() is True and e.reloads == 0, "asleep at exactly the threshold, nothing reloaded yet"
    assert e.chat(BODY)["timings"]["cache_n"] == 0 and e.reloads == 1 and e.is_sleeping() is False


def test_props_does_not_move_the_timer_but_a_render_wakes_the_server():
    clock = FakeClock()
    e = Engine(sleep_idle_seconds=60, clock=clock.seconds)
    e.chat(BODY)
    clock.advance(40)
    assert e.is_sleeping() is False                       # a props read at 40 s
    clock.advance(25)
    assert e.is_sleeping() is True, "the read at 40 s did not restart the 60 s"
    e.render(BODY)
    assert e.is_sleeping() is False and e.reloads == 1, "a render wakes a sleeping server"
    clock.advance(59)
    e.render(BODY)                                        # awake: a render is not a task
    clock.advance(1)
    assert e.is_sleeping() is True, "and does not move the timer"


def test_without_a_timer_the_stand_in_never_sleeps_and_an_expiring_one_forgets_without_sleeping():
    clock = FakeClock()
    e = Engine(clock=clock.seconds)
    n = e.chat(BODY)["usage"]["prompt_tokens"]
    clock.advance(10_000)
    assert e.is_sleeping() is False and e.chat(BODY)["timings"]["cache_n"] == n - 1
    x = Engine(clock=clock.seconds, expire_after_seconds=100)
    x.chat(BODY)
    clock.advance(99)
    assert x.chat(BODY)["timings"]["cache_n"] == n - 1
    clock.advance(100)
    assert x.is_sleeping() is False and x.chat(BODY)["timings"]["cache_n"] == 0 and x.reloads == 0


def test_the_fake_clock_moves_only_when_asked_and_stamps_like_the_records():
    clock = FakeClock("2026-10-03T23:59:50.000000Z")
    a = clock.stamp()
    clock.sleep(600)
    b = clock.stamp()
    assert seconds_between(a, b) == 600.0 and clock.slept == [600]
    assert clock.today() == "2026-10-04", "the fake's local date is its UTC date"
    assert a == "2026-10-03T23:59:50.000000Z" and b == "2026-10-04T00:09:50.000000Z"
    assert len(a) == len(utc_now()), "the same shape the records carry"
