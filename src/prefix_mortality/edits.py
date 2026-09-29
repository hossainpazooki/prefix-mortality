"""One registered change to the base request: a single word replaced at a named site.

A site names a part of the request and a place in it. It does not name a token: where the change
lands in the prompt is whatever the engine's own tokenizer says once the request is rendered
(ledger entry 0001, rules 3 and 4). Three kinds of site:

  system-0.250   the word at that fraction of the system text's length, in characters
  tool-04        the first word of that tool's description
  user           the first word of the user message

An edit that would leave the request unchanged is refused.
"""
import copy
import re

from prefix_mortality.config import M1Config

_WORD = re.compile(r"[A-Za-z]+")


def site_names(cfg: M1Config) -> list[str]:
    return ([f"system-{f:.3f}" for f in cfg.system_fractions] + [f"tool-{i:02d}" for i in cfg.tool_indexes]
            + (["user"] if cfg.edit_user_message else []))


def _replace_word(text: str, offset: int, replacement: str, site: str) -> str:
    """Replace the word that contains `offset` or is the first after it; failing that, the last word."""
    words = list(_WORD.finditer(text))
    if not words:
        raise ValueError(f"site {site}: there is no word to replace")
    m = next((w for w in words if w.end() > offset), words[-1])
    if m.group() == replacement:
        raise ValueError(f"site {site}: the word there is already {replacement!r}; the edit would change nothing")
    return text[:m.start()] + replacement + text[m.end():]


def apply(site: str, system_text: str, tools: list, user_message: str, replacement: str) -> tuple[str, list, str]:
    """The three parts of the request after the edit. The inputs are not modified."""
    kind, _, where = site.partition("-")
    if kind == "system" and where:
        offset = int(float(where) * (len(system_text) - 1))
        return _replace_word(system_text, offset, replacement, site), tools, user_message
    if kind == "tool" and where.isdigit():
        i = int(where)
        if i >= len(tools):
            raise ValueError(f"site {site}: the request carries {len(tools)} tools")
        edited = copy.deepcopy(tools)
        fn = edited[i].get("function") if isinstance(edited[i].get("function"), dict) else edited[i]
        if not isinstance(fn.get("description"), str):
            raise ValueError(f"site {site}: that tool has no description")
        fn["description"] = _replace_word(fn["description"], 0, replacement, site)
        return system_text, edited, user_message
    if site == "user":
        return system_text, tools, _replace_word(user_message, 0, replacement, site)
    raise ValueError(f"unknown site {site!r}")
