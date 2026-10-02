"""Each registered re-serialization changes the tools' JSON text, leaves the input alone, and is
refused when it would change nothing or names a tool the request lacks."""
import copy
import json

import pytest

from prefix_mortality.serialize import CHANGES, apply, tools_text

TOOLS = [{"type": "function", "function": {"name": f"tool_{i}", "description": f"Look booking {i} up.",
                                           "parameters": {"type": "object",
                                                          "properties": {"id": {"type": "string"},
                                                                         "day": {"type": "string"}},
                                                          "required": ["id"]}}}
         for i in range(11)]


def _parsed(text):
    return json.loads(text)


def test_tools_text_is_the_compact_form_the_body_builder_uses():
    assert tools_text(TOOLS) == json.dumps(TOOLS, ensure_ascii=False, separators=(",", ":"))


def test_every_change_alters_the_text_and_not_the_input():
    before = copy.deepcopy(TOOLS)
    base = tools_text(TOOLS)
    for change in CHANGES:
        out = apply(change, TOOLS)
        assert out != base, change
        assert TOOLS == before, change


def test_s1_changes_only_whitespace():
    assert _parsed(apply("S1", TOOLS)) == TOOLS
    assert "\n  " in apply("S1", TOOLS)


def test_s2_swaps_type_and_function_in_tool_4_only():
    out = _parsed(apply("S2", TOOLS))
    assert list(out[4].keys()) == ["function", "type"]
    assert all(list(out[i].keys()) == ["type", "function"] for i in range(11) if i != 4)
    assert out[4]["function"] == TOOLS[4]["function"]


def test_s3_swaps_the_first_two_tools():
    out = _parsed(apply("S3", TOOLS))
    assert out[0] == TOOLS[1] and out[1] == TOOLS[0] and out[2:] == TOOLS[2:]


def test_s4_reverses_the_properties_of_tool_10():
    out = _parsed(apply("S4", TOOLS))
    assert list(out[10]["function"]["parameters"]["properties"].keys()) == ["day", "id"]
    assert out[10]["function"]["parameters"]["properties"] == TOOLS[10]["function"]["parameters"]["properties"]
    assert out[:10] == TOOLS[:10]


def test_s5_moves_description_after_parameters_in_every_tool():
    out = _parsed(apply("S5", TOOLS))
    for t in out:
        assert list(t["function"].keys()) == ["name", "parameters", "description"]
    assert [t["function"]["description"] for t in out] == [t["function"]["description"] for t in TOOLS]


def test_s6_adds_an_unknown_key_to_every_function():
    out = _parsed(apply("S6", TOOLS))
    for t in out:
        assert t["function"]["x-version"] == "2"
        assert list(t["function"].keys()) == ["name", "description", "parameters", "x-version"]


@pytest.mark.parametrize("change, tools, msg", [
    ("S9", TOOLS, "unknown change"),
    ("S2", TOOLS[:4], "carries 4 tools"),
    ("S3", TOOLS[:1], "carries 1 tools"),
    ("S4", [{"type": "function", "function": {"name": "a", "description": "d", "parameters": {"properties": {"x": {}}}}}] * 11,
     "fewer than two properties"),
])
def test_refusals(change, tools, msg):
    with pytest.raises(ValueError, match=msg):
        apply(change, tools)


def test_a_change_that_leaves_the_text_equal_is_refused():
    already = [{"function": t["function"], "type": t["type"]} if i == 4 else t for i, t in enumerate(TOOLS)]
    with pytest.raises(ValueError, match="would change nothing"):
        apply("S2", already)
