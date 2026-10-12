"""Rebuild: on the faithful stand-in the prefix cell reuses d for both compactions, the walk cell shifts
a trimmed tail and nothing past an inserted summary, the threshold cell reuses d above the threshold
and 0 below it; the gates refuse; a stand-in that breaks a rule turns the run red; the summarizer
reproduces the report and refuses a changed record, prediction, chunk list, config or corpus; the
probe records nothing."""
import json

import pytest

from prefix_mortality.config import load_controls_config, load_engines_config, load_m5_config
from prefix_mortality.controls import Refusal
from prefix_mortality.hashing import sha256_file_bytes
from prefix_mortality.llamacpp import Client
from prefix_mortality.m5 import probe, run
from prefix_mortality.recorded import extract
from prefix_mortality.summarize_m5 import summarize
from tests.fake_llamacpp import serve
from tests.test_m4 import CONTROLS, SYSTEM, TOOLS
from tests.test_m8 import SHORT_SYSTEM, _engines_toml

SUMMARY = "Summary so far: the customer asked about a booking and the agent checked it. Continue."


def _sim(task_id: str, turns: int, tail_words: int = 300) -> dict:
    """greeting, then `turns` rounds of user -> assistant(call) -> tool(long) -> assistant; distinct per task."""
    msgs = [{"role": "assistant", "content": "Hi! How can I help you today?", "tool_calls": None, "turn_idx": 0}]
    for i in range(turns):
        msgs.append({"role": "user", "content": f"question {i} of {task_id}", "tool_calls": None, "turn_idx": len(msgs)})
        msgs.append({"role": "assistant", "content": f"checking {i} of {task_id}", "turn_idx": len(msgs),
                     "tool_calls": [{"arguments": {"q": i}, "id": f"call_{task_id}_{i}", "name": "look", "requestor": "assistant"}]})
        msgs.append({"role": "tool", "content": " ".join(f"record{task_id}x{i}w{j}" for j in range(tail_words)),
                     "error": False, "id": f"call_{task_id}_{i}", "requestor": "assistant", "turn_idx": len(msgs)})
        msgs.append({"role": "assistant", "content": f"answer {i} of {task_id}", "tool_calls": None, "turn_idx": len(msgs)})
    return {"task_id": task_id, "trial": 0, "messages": msgs}


def _m5_toml(registered: str, conversations: int = 2) -> str:
    return f'''
[m5]
recorded_dir = "corpus/recorded/synthetic"
conversations = {conversations}
arms = ["trim", "summary"]
summary = "{SUMMARY}"
similarity_threshold = 0.10
threshold_margin = 0.002
cache_reuse_n = 256
corpus_dir = "corpus/live/m5"
results_dir = "results/m5"
registered_by = "{registered}"
[m5.template_kwargs.llama]
tools_in_user_message = false
[m5.template_kwargs.qwen]
[m5.hypotheses.H-M5L1]
slots = 1
rule = "prefix"
[m5.hypotheses.H-M5LD]
slots = 4
rule = "threshold"
[m5.hypotheses.H-M5LC]
slots = 1
rule = "walk"
'''


def _world(tmp_path, *, registered="0040", system=SYSTEM, tools=TOOLS, turns=(4, 3, 2), tail_words=300):
    root = tmp_path / "repo"
    for d in ("config", "corpus/live/m5", "corpus/requests", "corpus/recorded", "results", "fixture"):
        (root / d).mkdir(parents=True)
    model = root / "model.gguf"
    model.write_bytes(b"not a model, only bytes to hash")
    (root / "fixture" / "system.txt").write_text(system, encoding="utf-8")
    (root / "fixture" / "tools.json").write_text(json.dumps(tools), encoding="utf-8")
    (root / "config" / "controls.toml").write_text(CONTROLS, encoding="utf-8")
    (root / "config" / "engines.toml").write_text(_engines_toml(sha256_file_bytes(model)), encoding="utf-8")
    (root / "config" / "m5.toml").write_text(_m5_toml(registered), encoding="utf-8")
    source = {"info": {"agent_info": {"llm": "agent"}, "user_info": {"llm": "user"},
                       "environment_info": {"domain_name": "airline", "tool_defs": None},
                       "git_commit": "c" * 40, "num_trials": 1, "max_steps": 1, "max_errors": 1, "seed": 0},
              "simulations": [_sim(str(i), t, tail_words) for i, t in enumerate(turns)]}
    src = tmp_path / "source.json"
    src.write_text(json.dumps(source), encoding="utf-8")
    extract(src, root / "corpus" / "recorded" / "synthetic", source_repo="r", source_commit="c" * 40,
            source_rel_path="p.json")
    return {"root": root, "model": model, "fixture": root / "fixture",
            "controls": load_controls_config(root / "config" / "controls.toml", root),
            "engine": load_engines_config(root / "config" / "engines.toml")["llamacpp"],
            "m5": load_m5_config(root / "config" / "m5.toml", root)}


def _run(w, url, hid, family="qwen"):
    return run(w["m5"], w["controls"], w["engine"], family, hid, Client(url, 30.0), w["model"],
               repo_root=w["root"], fixture=w["fixture"])


def test_the_prefix_cell_reuses_d_for_both_compactions(tmp_path):
    w = _world(tmp_path)
    with serve(slots=1, n_ctx=100000) as (url, _):
        report = _run(w, url, "H-M5L1")
    assert report["outcome"] == "ALL MATCH" and report["counts"] == {"trials": 4, "counted": 4, "matching": 4}
    assert [(t["conversation"], t["arm"]) for t in report["trials"]] == [("0", "trim"), ("0", "summary"), ("1", "trim"), ("1", "summary")]
    for t in report["trials"]:
        c = t["compacted"]
        assert c["predicted_reuse"] == c["first_differing_token"] == c["cache_n"] and c["shifted"] == 0
        assert 0 < c["first_differing_token"] < c["n"] < t["full"]["n"]
        assert t["full"]["cache_n"] <= t["full"]["h"]


def test_the_walk_cell_shifts_a_trimmed_tail_and_nothing_past_a_summary(tmp_path):
    w = _world(tmp_path)
    with serve(slots=1, n_ctx=100000, cache_reuse_n=256) as (url, _):
        report = _run(w, url, "H-M5LC")
    assert report["outcome"] == "ALL MATCH" and report["counts"]["matching"] == 4
    by = {t["arm"]: t for t in report["trials"] if t["conversation"] == "0"}
    trim, summary = by["trim"]["compacted"], by["summary"]["compacted"]
    assert trim["shifted"] >= 256 and trim["predicted_reuse"] == trim["cache_n"] > trim["first_differing_token"]
    assert len(trim["chunks"]) >= 1 and all(len(c) == 3 for c in trim["chunks"])
    assert summary["shifted"] == 0 and summary["predicted_reuse"] == summary["first_differing_token"] == summary["cache_n"]
    assert report["by_arm"][0]["shifted_total"] > 0 and report["by_arm"][1]["shifted_total"] == 0


@pytest.mark.parametrize("system,tools,expect_zero", [(SYSTEM, TOOLS, False), (SHORT_SYSTEM, [], True)])
def test_the_threshold_cell_reuses_d_above_the_threshold_and_zero_below(tmp_path, system, tools, expect_zero):
    w = _world(tmp_path, system=system, tools=tools, turns=(6, 5), tail_words=400)
    with serve(slots=4, n_ctx=100000) as (url, _):
        report = _run(w, url, "H-M5LD")
    assert report["outcome"] == "ALL MATCH", report["mismatches"]
    for t in report["trials"]:
        c = t["compacted"]
        share = c["first_differing_token"] / c["n"]
        assert (share < 0.10) == expect_zero and not c["near_threshold"]
        assert c["predicted_reuse"] == (0 if expect_zero else c["first_differing_token"]) == c["cache_n"]


def test_run_refuses_unregistered_wrong_slots_and_a_context_too_small(tmp_path):
    w = _world(tmp_path, registered="")
    with serve(slots=1, n_ctx=100000) as (url, _):
        with pytest.raises(Refusal, match="UNREGISTERED"):
            _run(w, url, "H-M5L1")
    w = _world(tmp_path / "b")
    with serve(slots=1, n_ctx=100000) as (url, _):
        with pytest.raises(Refusal, match="requires a server reporting 4 slot"):
            _run(w, url, "H-M5LD")
    with serve(slots=1, n_ctx=200) as (url, _):
        with pytest.raises(Refusal, match="does not fit the slot context"):
            _run(w, url, "H-M5L1")
    assert not list((w["root"] / "corpus" / "live" / "m5").glob("*.jsonl"))


@pytest.mark.parametrize("mode,outcome,records", [("no_cache", "MISMATCH", 8), ("no_fields", "NOT MEASURABLE", 2)])
def test_a_run_goes_red_on_an_engine_that_breaks_a_rule(tmp_path, mode, outcome, records):
    w = _world(tmp_path)
    with serve(mode, slots=1, n_ctx=100000) as (url, _):
        report = _run(w, url, "H-M5L1")
    assert report["outcome"] == outcome and sum(1 for _ in open(w["m5"].corpus_dir / f"{report['run_id']}.jsonl")) == records


def test_summarize_reproduces_and_refuses_a_changed_record_prediction_chunks_config_or_corpus(tmp_path):
    w = _world(tmp_path)
    with serve(slots=1, n_ctx=100000, cache_reuse_n=256) as (url, _):
        report = _run(w, url, "H-M5LC")
    assert summarize(report["run_id"], repo_root=w["root"])[0] == report
    log = w["m5"].corpus_dir / f"{report['run_id']}.jsonl"
    original = log.read_text(encoding="utf-8")

    def rewrite(mutate, match):
        lines = [json.loads(l) for l in original.splitlines()]
        mutate(lines)
        log.write_text("".join(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n" for r in lines),
                       encoding="utf-8", newline="\n")
        with pytest.raises(ValueError, match=match):
            summarize(report["run_id"], repo_root=w["root"])

    def obs(lines):
        lines[1]["observed"]["cache_n"] += 1
    rewrite(obs, "do not reproduce")

    def pred(lines):
        lines[1]["predicted_reuse"] += 1
    rewrite(pred, "do not reproduce")                      # prediction_as_recorded fails: a FAILED CONTROL report

    def chunks(lines):
        lines[1]["chunks"] = []
    rewrite(chunks, "do not reproduce")

    def arm(lines):
        lines[1]["arm"] = "pretty"
    rewrite(arm, "unregistered arm")
    log.write_text(original, encoding="utf-8", newline="\n")

    cfg = w["root"] / "config" / "m5.toml"
    text = cfg.read_text(encoding="utf-8")
    cfg.write_text(text.replace("cache_reuse_n = 256", "cache_reuse_n = 255"), encoding="utf-8")
    with pytest.raises(ValueError, match="different config"):
        summarize(report["run_id"], repo_root=w["root"])
    cfg.write_text(text, encoding="utf-8")

    sims = w["root"] / "corpus" / "recorded" / "synthetic" / "simulations.json"
    body = sims.read_text(encoding="utf-8")
    sims.write_text(body.replace("question 0 of 0", "question X of 0", 1), encoding="utf-8")
    with pytest.raises(ValueError, match="does not hash to its provenance"):
        summarize(report["run_id"], repo_root=w["root"])


def test_probe_records_nothing(tmp_path):
    w = _world(tmp_path)
    with serve(slots=1, n_ctx=100000, cache_reuse_n=256) as (url, _):
        out = probe(w["m5"], w["controls"], "H-M5LC", "qwen", ["1"], Client(url, 30.0), fixture=w["fixture"])
    assert [t["arm"] for t in out["trials"]] == ["trim", "summary"] and all(t["match"] for t in out["trials"])
    assert out["trials"][0]["shifted"] > 0 and out["trials"][1]["shifted"] == 0
    assert not list((w["root"] / "corpus" / "live" / "m5").glob("*.jsonl"))
    assert not list((w["root"] / "corpus" / "requests").glob("*.json"))


@pytest.mark.parametrize("edit,message", [
    ('arms = ["trim", "summary"]', 'arms = ["trim", "pretty"]'),
    ('rule = "walk"', 'rule = "shift"'),
    (f'summary = "{SUMMARY}"', 'summary = "  "'),
    ("[m5.hypotheses.H-M5LC]", "[m5.hypotheses.H-M5V1]\nslots = 1\nrule = \"walk\"\n[m5.hypotheses.H-M5LC]"),
])
def test_m5_config_refuses_bad_values(tmp_path, edit, message):
    text = _m5_toml("0040")
    assert text.count(edit) == 1
    (tmp_path / "m5.toml").write_text(text.replace(edit, message), encoding="utf-8")
    with pytest.raises(ValueError):
        load_m5_config(tmp_path / "m5.toml", tmp_path)
