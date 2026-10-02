"""One registered re-serialization of the tools array: the same schemas written differently.

The change is to the request's bytes. Whether the engine renders them differently is the question:
the server parses each tool into three fields and rebuilds it in a fixed key order (read at the pin in
common/chat.cpp, common_chat_tools_parse_oaicompat / _to_json_oaicompat), so a change the parser
normalises away ends nothing, and one it keeps ends the prefix where it lands. The prediction is
computed from the two rendered prompts (ledger 0001, rule 4), never from this module's reading.

  S1  indentation and spacing only (the parsed value is equal)
  S2  `type` and `function` swapped at the top of tool 4
  S3  tools 0 and 1 swapped in the array
  S4  the keys of `properties` reversed inside tool 10's parameters
  S5  `description` moved after `parameters` in every tool
  S6  an unknown key added to every tool's `function`

A change that would leave the text equal is refused.
"""
import copy
import json

CHANGES = ("S1", "S2", "S3", "S4", "S5", "S6")
_EXTRA_KEY, _EXTRA_VALUE = "x-version", "2"


def tools_text(tools: list) -> str:
    """The compact text `record.body_bytes` embeds for a `tools` value: no spaces, keys as given."""
    return json.dumps(tools, ensure_ascii=False, separators=(",", ":"))


def _require_tool(tools: list, index: int, change: str) -> None:
    if index >= len(tools):
        raise ValueError(f"change {change}: the request carries {len(tools)} tools, tool {index} does not exist")


def _function(tool: dict, change: str) -> dict:
    fn = tool.get("function")
    if not isinstance(fn, dict):
        raise ValueError(f"change {change}: a tool has no `function` object")
    return fn


def _reordered(d: dict, first: list[str]) -> dict:
    return {**{k: d[k] for k in first if k in d}, **{k: v for k, v in d.items() if k not in first}}


def apply(change: str, tools: list) -> str:
    """The tools after the change, as the JSON text to embed in the request. The input is not modified."""
    if change not in CHANGES:
        raise ValueError(f"unknown change {change!r}; known: {list(CHANGES)}")
    t = copy.deepcopy(tools)
    if change == "S1":
        out = json.dumps(t, ensure_ascii=False, indent=2)
    else:
        if change == "S2":
            _require_tool(t, 4, change)
            t[4] = _reordered(t[4], ["function", "type"])
        elif change == "S3":
            _require_tool(t, 1, change)
            t[0], t[1] = t[1], t[0]
        elif change == "S4":
            _require_tool(t, 10, change)
            params = _function(t[10], change).get("parameters")
            props = params.get("properties") if isinstance(params, dict) else None
            if not isinstance(props, dict) or len(props) < 2:
                raise ValueError(f"change {change}: tool 10 has fewer than two properties to reorder")
            params["properties"] = dict(reversed(list(props.items())))
        elif change == "S5":
            for tool in t:
                tool["function"] = _reordered(_function(tool, change), ["name", "parameters", "description"])
        elif change == "S6":
            for tool in t:
                _function(tool, change)[_EXTRA_KEY] = _EXTRA_VALUE
        out = tools_text(t)
    if out == tools_text(tools):
        raise ValueError(f"change {change}: the tools are already written that way; the change would change nothing")
    return out
