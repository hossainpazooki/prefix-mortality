"""The stand-in does to a tool what the pinned server does before rendering, and its llama and qwen
modes follow the two templates' behaviours the templating experiment relies on."""
import json

import pytest

from prefix_mortality.llamacpp import Client, EngineError
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
