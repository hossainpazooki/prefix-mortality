"""The recorded-run corpus: one trial per task is extracted with its provenance and never overwritten,
a file that does not hash to its provenance is refused, the statistics are recomputed from the
simulations alone, and the vendored folder in the repository loads and reports."""
import json

import pytest

from prefix_mortality import REPO_ROOT
from prefix_mortality.hashing import sha256_hex
from prefix_mortality.recorded import PROVENANCE, SIMULATIONS, extract, load, render, stats

RECORDED = REPO_ROOT / "corpus" / "recorded" / "tau2-airline-claude-3-7-sonnet"


def _msg(role, t, content="x", **extra):
    return {"role": role, "content": content, "timestamp": f"2025-06-05T16:00:{t:02d}.000000", "raw_data": {"big": "x" * 50},
            **extra}


def _source():
    def sim(task, trial, times):
        msgs = []
        roles = ["assistant", "user", "assistant", "tool", "assistant"]
        for r, t in zip(roles, times):
            msgs.append(_msg(r, t, tool_calls=[{"name": "f"}] if r == "assistant" and t == times[2] else None))
        return {"id": f"{task}-{trial}", "task_id": task, "trial": trial, "termination_reason": "user_stop", "messages": msgs}
    return {"info": {"git_commit": "abc", "num_trials": 2, "max_steps": 200, "max_errors": 10, "seed": 300,
                     "agent_info": {"llm": "agent-x"}, "user_info": {"llm": "user-y"},
                     "environment_info": {"domain_name": "airline", "policy": "p", "tool_defs": None}},
            "simulations": [sim("0", 0, [0, 4, 10, 10, 12]), sim("0", 1, [0, 1, 2, 2, 3]),
                            sim("1", 0, [0, 9, 20, 20, 50]), sim("1", 1, [0, 1, 2, 2, 3])]}


def test_extract_keeps_one_trial_per_task_drops_raw_data_and_writes_provenance(tmp_path):
    src = tmp_path / "source.json"
    src.write_text(json.dumps(_source()), encoding="utf-8")
    out = tmp_path / "vendored"
    prov = extract(src, out, source_repo="https://example/repo", source_commit="b7ea9074", source_rel_path="data/x.json")
    sims, prov2 = load(out)
    assert prov2 == prov and [s["task_id"] for s in sims] == ["0", "1"] and all(s["trial"] == 0 for s in sims)
    assert all("raw_data" not in m for s in sims for m in s["messages"]) and all("tool_calls" in m for s in sims for m in s["messages"])
    assert prov["source_sha256"] == sha256_hex(src.read_bytes()) and prov["source_bytes"] == src.stat().st_size
    assert prov["source_simulations"] == 4 and prov["simulations"] == 2 and prov["tasks"] == ["0", "1"]
    assert prov["agent_llm"] == "agent-x" and prov["user_llm"] == "user-y" and prov["tool_defs_in_source"] is False
    assert prov["output"][SIMULATIONS]["sha256"] == sha256_hex((out / SIMULATIONS).read_bytes())
    with pytest.raises(ValueError, match="never overwrites"):
        extract(src, out, source_repo="r", source_commit="c", source_rel_path="p")
    st = stats(sims)
    assert st["simulations"] == 2 and st["tasks"] == 2 and st["termination_reasons"] == ["user_stop"]
    assert st["assistant_turns"] == {"min": 3, "median": 3, "max": 3, "total": 6}
    # idle after an assistant message = time to the next message: 4, 0, 9, 0 (the last assistant message has no successor)
    assert st["idle_to_next_message_s"] == {"n": 4, "p10": 0.0, "median": 2.0, "p90": 9.0, "max": 9.0}
    # assistant to assistant: 10, 2, 20, 30
    assert st["assistant_cycle_s"]["n"] == 4 and st["assistant_cycle_s"]["max"] == 30.0 and st["assistant_cycle_s"]["median"] == 15.0
    text = render(st, prov)
    assert "agent-x agent, user-y user simulator, domain airline" in text and "| 4 | 0.0 | 2.0 | 9.0 | 9.0 |" in text


def test_extract_refuses_a_trial_with_a_repeated_task_or_no_simulations(tmp_path):
    src = _source()
    src["simulations"][1]["trial"] = 0                       # task 0 twice under trial 0
    p = tmp_path / "s.json"
    p.write_text(json.dumps(src), encoding="utf-8")
    with pytest.raises(ValueError, match="not one per task"):
        extract(p, tmp_path / "a", source_repo="r", source_commit="c", source_rel_path="p")
    with pytest.raises(ValueError, match="no simulation has trial == 7"):
        extract(p, tmp_path / "b", source_repo="r", source_commit="c", source_rel_path="p", trial=7)


def test_load_refuses_a_file_that_does_not_hash_to_its_provenance(tmp_path):
    src = tmp_path / "source.json"
    src.write_text(json.dumps(_source()), encoding="utf-8")
    out = tmp_path / "vendored"
    extract(src, out, source_repo="r", source_commit="c", source_rel_path="p")
    sims_path = out / SIMULATIONS
    sims_path.write_text(sims_path.read_text(encoding="utf-8").replace("user_stop", "user_stopp"), encoding="utf-8")
    with pytest.raises(ValueError, match="does not hash to its provenance"):
        load(out)
    prov = json.loads((out / PROVENANCE).read_text(encoding="utf-8"))
    prov["output"][SIMULATIONS]["sha256"] = sha256_hex(sims_path.read_bytes())
    prov["simulations"] = 3
    (out / PROVENANCE).write_text(json.dumps(prov), encoding="utf-8")
    with pytest.raises(ValueError, match="provenance says 3 simulations, file holds 2"):
        load(out)


def test_repo_recorded_corpus_loads_and_is_one_trial_per_task():
    sims, prov = load(RECORDED)
    assert prov["source_repo"] == "https://github.com/sierra-research/tau2-bench"
    assert prov["source_commit"] == "b7ea9074c1cba482b30687fecdb5c8425fd6f619"
    assert prov["simulations"] == len(sims) == 50 and len({s["task_id"] for s in sims}) == 50
    assert all(s["trial"] == 0 for s in sims) and all("raw_data" not in m for s in sims for m in s["messages"])
    assert prov["tool_defs_in_source"] is False, "0001: the published files record no tool schemas"
    st = stats(sims)
    assert st["simulations"] == 50 and st["termination_reasons"] == ["user_stop"]
    assert st["idle_to_next_message_s"]["n"] > 0 and st["assistant_turns"]["total"] > 50
    assert render(st, prov).startswith("recorded runs: claude-3-7-sonnet-20250219 agent, gpt-4.1-2025-04-14 user simulator, domain airline")
