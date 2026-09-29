"""A site changes exactly one word of exactly one part of the request, or is refused."""
import copy
import json

import pytest

from prefix_mortality import REPO_ROOT
from prefix_mortality.config import load_m1_config
from prefix_mortality.edits import apply, site_names

SYSTEM = "Alpha beta gamma. Delta epsilon, zeta eta theta!"
TOOLS = [{"type": "function", "function": {"name": "a", "description": "Look a booking up."}},
         {"name": "b", "description": "  Cancel it."}]


def test_system_site_replaces_the_word_at_or_after_the_offset():
    assert apply("system-0.000", SYSTEM, TOOLS, "Hello.", "zebra")[0] == "zebra beta gamma. Delta epsilon, zeta eta theta!"
    # offset 23 of 47 falls inside "epsilon"
    assert apply("system-0.500", SYSTEM, TOOLS, "Hello.", "zebra")[0] == "Alpha beta gamma. Delta zebra, zeta eta theta!"
    # the last character is punctuation: no word follows, so the last word is taken
    assert apply("system-1.000", SYSTEM, TOOLS, "Hello.", "zebra")[0] == "Alpha beta gamma. Delta epsilon, zeta eta zebra!"


def test_tool_site_replaces_the_first_word_of_that_description_and_leaves_the_input_alone():
    before = copy.deepcopy(TOOLS)
    s, tools, u = apply("tool-00", SYSTEM, TOOLS, "Hello.", "zebra")
    assert (s, u) == (SYSTEM, "Hello.") and TOOLS == before
    assert tools[0]["function"]["description"] == "zebra a booking up." and tools[1] == TOOLS[1]
    assert apply("tool-01", SYSTEM, TOOLS, "Hello.", "zebra")[1][1]["description"] == "  zebra it."


def test_user_site_replaces_the_first_word_of_the_user_message():
    assert apply("user", SYSTEM, TOOLS, "Hello.", "zebra") == (SYSTEM, TOOLS, "zebra.")


@pytest.mark.parametrize("site, system, msg", [
    ("system-0.000", "zebra beta", "would change nothing"),
    ("system-0.500", "... 123 ...", "no word to replace"),
    ("tool-02", SYSTEM, "carries 2 tools"),
    ("tool-xx", SYSTEM, "unknown site"),
    ("header", SYSTEM, "unknown site"),
])
def test_an_edit_that_cannot_be_made_is_refused(site, system, msg):
    with pytest.raises(ValueError, match=msg):
        apply(site, system, TOOLS, "Hello.", "zebra")


def test_a_tool_without_a_description_is_refused():
    with pytest.raises(ValueError, match="no description"):
        apply("tool-00", SYSTEM, [{"name": "a"}], "Hello.", "zebra")


def test_every_registered_site_applies_to_the_base_prefix_and_changes_one_part():
    cfg = load_m1_config(REPO_ROOT / "config" / "m1.toml", REPO_ROOT)
    fixture = REPO_ROOT / "corpus" / "base_prefix" / "tau2-airline"
    system = (fixture / "system.txt").read_bytes().decode("utf-8")
    tools = json.loads((fixture / "tools.json").read_text(encoding="utf-8"))
    assert cfg.replacement not in system.lower() and cfg.replacement not in json.dumps(tools).lower()
    names = site_names(cfg)
    assert len(names) == len(set(names)) == len(cfg.system_fractions) + len(cfg.tool_indexes) + 1
    assert names[0] == "system-0.000" and names[-1] == "user" and "tool-04" in names
    seen = set()
    for site in names:
        s, t, u = apply(site, system, tools, "Hello.", cfg.replacement)
        changed = [s != system, t != tools, u != "Hello."]
        assert sum(changed) == 1, site
        assert (s + json.dumps(t) + u).count(cfg.replacement) == 1, site
        seen.add((s, json.dumps(t), u))
    assert len(seen) == len(names), "two sites made the same edit"
