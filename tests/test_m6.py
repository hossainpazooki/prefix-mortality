"""Model switch and restart on the stand-ins: with --models-max 4 the switch to B and back finds A's
slot alive; with --models-max 1 the switch unloads A and the return reads 0; a bare restart loses the
prefix and a slot saved before it and restored after keeps it; a router that keeps A loaded under
--models-max 1 fails a control, as does a process that did not restart; the gates refuse; a stand-in
that breaks a rule turns the run red; the summarizer reproduces the report and refuses a changed
record, prediction or config; the probe records nothing."""
import json

import pytest

from prefix_mortality.config import load_controls_config, load_engines_config, load_m6_config
from prefix_mortality.controls import Refusal
from prefix_mortality.hashing import sha256_file_bytes
from prefix_mortality.m6 import probe, run
from prefix_mortality.summarize_m6 import summarize
from tests.fake_llamacpp import Engine, _handler as engine_handler
from tests.fake_procs import FakeServerHandle
from tests.fake_router import Router, _handler as router_handler
from tests.test_m4 import CONTROLS, SYSTEM, TOOLS
from tests.test_m8 import _engines_toml

CHILD_B = "qwen17q4"


def _m6_toml(registered: str, child_sha: str) -> str:
    return f'''
[m6]
repetitions = 2
child_context = 16384
corpus_dir = "corpus/live/m6"
results_dir = "results/m6"
registered_by = "{registered}"
[m6.child_b]
name = "{CHILD_B}"
hf_repo = "example/small"
file = "small.gguf"
sha256 = "{child_sha}"
[m6.hypotheses.H-M6LA]
mode = "router"
models_max = 4
slots = 4
[m6.hypotheses.H-M6LB]
mode = "router"
models_max = 1
slots = 4
[m6.hypotheses.H-M6LR]
mode = "restart"
models_max = 0
slots = 1
'''


def _world(tmp_path, *, registered="0042"):
    root = tmp_path / "repo"
    for d in ("config", "corpus/live/m6", "corpus/requests", "results", "fixture"):
        (root / d).mkdir(parents=True)
    model, small = root / "model.gguf", root / "small.gguf"
    model.write_bytes(b"not a model, only bytes to hash")
    small.write_bytes(b"a smaller not-a-model")
    (root / "fixture" / "system.txt").write_text(SYSTEM, encoding="utf-8")
    (root / "fixture" / "tools.json").write_text(json.dumps(TOOLS), encoding="utf-8")
    (root / "config" / "controls.toml").write_text(CONTROLS, encoding="utf-8")
    (root / "config" / "engines.toml").write_text(_engines_toml(sha256_file_bytes(model)), encoding="utf-8")
    (root / "config" / "m6.toml").write_text(_m6_toml(registered, sha256_file_bytes(small)), encoding="utf-8")
    return {"root": root, "model": model, "small": small, "fixture": root / "fixture",
            "controls": load_controls_config(root / "config" / "controls.toml", root),
            "engine": load_engines_config(root / "config" / "engines.toml")["llamacpp"],
            "m6": load_m6_config(root / "config" / "m6.toml", root)}


def _router_handle(models_max, *, mode="faithful", slots=4, sticky_max=None):
    factories = {"qwen": lambda: Engine(mode, slots=slots, n_ctx=16384),
                 CHILD_B: lambda: Engine(mode, slots=slots, n_ctx=16384, build_info="b11235-6c7a87f")}
    return FakeServerHandle(lambda: Router(factories, sticky_max if sticky_max is not None else models_max),
                            handler=router_handler)


def _restart_handle(*, mode="faithful", store=None, forgetful=True):
    store = {} if store is None else store
    vocab, kept = {}, {}                               # the tokenizer is the model's and survives a restart

    def factory():
        if not forgetful and "engine" in kept:
            return kept["engine"]                      # a "restart" that keeps the process: a broken handle
        kept["engine"] = Engine(mode, slots=1, n_ctx=16384, save_store=store, ids=vocab)
        return kept["engine"]
    return FakeServerHandle(factory, handler=engine_handler)


def _run(w, hid, handle, family="qwen", child_b=True):
    return run(w["m6"], w["controls"], w["engine"], family, hid, handle, w["model"],
               w["small"] if child_b else None, repo_root=w["root"], fixture=w["fixture"])


def test_with_four_children_allowed_the_switch_and_back_finds_the_slot_alive(tmp_path):
    w = _world(tmp_path)
    report = _run(w, "H-M6LA", _router_handle(4))
    assert report["outcome"] == "ALL MATCH" and report["counts"] == {"trials": 2, "counted": 2, "matching": 2}
    for t in report["trials"]:
        assert t["anchor"]["cache_n"] <= t["anchor"]["h"] and t["other"]["cache_n"] <= t["other"]["h"]
        assert t["resend"]["predicted_reuse"] == t["anchor"]["n"] - 1 == t["resend"]["cache_n"]
        assert sorted(t["resend"]["loaded_before"]) == ["qwen", CHILD_B]
        assert t["other"]["response_model"] == CHILD_B and t["resend"]["response_model"] == "qwen"


def test_with_one_child_allowed_the_switch_unloads_a_and_the_return_reads_zero(tmp_path):
    w = _world(tmp_path)
    report = _run(w, "H-M6LB", _router_handle(1))
    assert report["outcome"] == "ALL MATCH" and report["counts"]["matching"] == 2
    for t in report["trials"]:
        assert t["resend"]["predicted_reuse"] == 0 == t["resend"]["cache_n"]
        assert t["resend"]["loaded_before"] == [CHILD_B] and t["anchor"]["loaded_before"] in (["qwen"], [CHILD_B])


def test_a_router_that_keeps_a_loaded_under_models_max_one_fails_a_control(tmp_path):
    w = _world(tmp_path)
    report = _run(w, "H-M6LB", _router_handle(1, sticky_max=4))        # the server ignores its flag
    assert report["outcome"] == "FAILED CONTROL"
    assert any("loaded_set_as_the_cell_requires" in x for x in report["failures"])
    assert report["counts"]["trials"] == 1                              # the run stopped


def test_a_restart_loses_the_prefix_and_a_saved_slot_survives_it(tmp_path):
    w = _world(tmp_path)
    handle = _restart_handle()
    report = _run(w, "H-M6LR", handle, child_b=False)
    assert report["outcome"] == "ALL MATCH" and report["counts"] == {"trials": 4, "counted": 4, "matching": 4}
    parts = {(t["repetition"], t["part"]): t for t in report["trials"]}
    assert parts[(1, "restart")]["resend"]["predicted_reuse"] == 0 == parts[(1, "restart")]["resend"]["cache_n"]
    sr = parts[(1, "save-restore")]
    assert sr["resend"]["predicted_reuse"] == sr["anchor"]["n"] - 1 == sr["resend"]["cache_n"]
    gens = [(t["anchor"]["process"]["generation"], t["resend"]["process"]["generation"]) for t in report["trials"]]
    assert gens == [(1, 2), (2, 3), (3, 4), (4, 5)]
    assert handle.info()["running"] is False                            # the driver stopped the server


def test_a_process_that_kept_its_memory_across_a_restart_is_a_mismatch_the_instrument_reads(tmp_path):
    w = _world(tmp_path)
    report = _run(w, "H-M6LR", _restart_handle(forgetful=False), child_b=False)
    assert report["outcome"] == "MISMATCH"
    # the generation increments (the handle counts starts) but the prefix survived a bare restart:
    # the resend reads n - 1 against a prediction of 0
    assert report["trials"][0]["resend"]["cache_n"] == report["trials"][0]["anchor"]["n"] - 1


def test_a_handle_whose_generation_does_not_move_fails_a_control(tmp_path):
    w = _world(tmp_path)
    handle = _restart_handle()
    handle.info = lambda: {"generation": 1, "pid": 1, "started": "x", "running": True}
    report = _run(w, "H-M6LR", handle, child_b=False)
    assert report["outcome"] == "FAILED CONTROL" and any("process_restarted_once" in x for x in report["failures"])


def test_run_refuses_unregistered_a_wrong_child_b_hash_and_wrong_slots(tmp_path):
    w = _world(tmp_path, registered="")
    with pytest.raises(Refusal, match="UNREGISTERED"):
        _run(w, "H-M6LA", _router_handle(4))
    w = _world(tmp_path / "b")
    w["small"].write_bytes(b"other bytes")
    with pytest.raises(Refusal, match="config pins"):
        _run(w, "H-M6LA", _router_handle(4))
    w = _world(tmp_path / "c")
    with pytest.raises(Refusal, match="requires a server reporting 4 slot"):
        _run(w, "H-M6LA", _router_handle(4, slots=1))
    assert not list((w["root"] / "corpus" / "live" / "m6").glob("*.jsonl"))


@pytest.mark.parametrize("mode,outcome", [("no_cache", "MISMATCH"), ("no_fields", "NOT MEASURABLE")])
def test_a_run_goes_red_on_an_engine_that_breaks_a_rule(tmp_path, mode, outcome):
    w = _world(tmp_path)
    report = _run(w, "H-M6LA", _router_handle(4, mode=mode))
    assert report["outcome"] == outcome


def test_summarize_reproduces_and_refuses_a_changed_record_prediction_or_config(tmp_path):
    w = _world(tmp_path)
    report = _run(w, "H-M6LR", _restart_handle(), child_b=False)
    assert summarize(report["run_id"], repo_root=w["root"])[0] == report
    log = w["m6"].corpus_dir / f"{report['run_id']}.jsonl"
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
        lines[1]["predicted_reuse"] = 5
    rewrite(pred, "do not reproduce")

    def part(lines):
        lines[1]["part"] = "reboot"
    rewrite(part, "unregistered part")
    log.write_text(original, encoding="utf-8", newline="\n")
    cfg = w["root"] / "config" / "m6.toml"
    text = cfg.read_text(encoding="utf-8")
    cfg.write_text(text.replace("child_context = 16384", "child_context = 8192"), encoding="utf-8")
    with pytest.raises(ValueError, match="different config"):
        summarize(report["run_id"], repo_root=w["root"])


def test_probe_records_nothing(tmp_path):
    w = _world(tmp_path)
    out = probe(w["m6"], w["controls"], "H-M6LA", "qwen", _router_handle(4), fixture=w["fixture"])
    assert [r["role"] for r in out["requests"]] == ["anchor", "other", "resend"]
    assert out["requests"][2]["observed"]["cache_n"] == out["predicted_resend"]
    out = probe(w["m6"], w["controls"], "H-M6LR", "qwen", _restart_handle(), fixture=w["fixture"])
    assert [r["part"] for r in out["requests"]] == ["restart", "save-restore"]
    assert out["requests"][1]["resend"]["cache_n"] == out["requests"][1]["predicted_resend"]
    assert not list((w["root"] / "corpus" / "live" / "m6").glob("*.jsonl"))
    assert not list((w["root"] / "corpus" / "requests").glob("*.json"))


@pytest.mark.parametrize("edit,message", [
    ('mode = "restart"', 'mode = "reboot"'),
    ("[m6.hypotheses.H-M6LB]\nmode = \"router\"\nmodels_max = 1", "[m6.hypotheses.H-M6LB]\nmode = \"router\"\nmodels_max = 0"),
    ("[m6.hypotheses.H-M6LR]\nmode = \"restart\"\nmodels_max = 0", "[m6.hypotheses.H-M6LR]\nmode = \"restart\"\nmodels_max = 2"),
    ('name = "qwen17q4"', 'name = ""'),
])
def test_m6_config_refuses_bad_values(tmp_path, edit, message):
    text = _m6_toml("0042", "a" * 64)
    assert text.count(edit) == 1
    (tmp_path / "m6.toml").write_text(text.replace(edit, message), encoding="utf-8")
    with pytest.raises(ValueError):
        load_m6_config(tmp_path / "m6.toml", tmp_path)
