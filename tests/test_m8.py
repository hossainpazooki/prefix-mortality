"""Lifespan on recorded runs: one slot replays every conversation in file order and every request
matches the policy on the faithful stand-in; interleaved conversations follow the registered round
robin and the simulator's reading of the shared head, the cache search and its restores agrees with the
stand-in's, with a generous cache and with one too small to hold a state; a near request is reported
and not counted; the gates refuse; a stand-in that breaks a rule turns the run red; the summarizer
reproduces the report and refuses a changed record, prediction, schedule, config or corpus; Llama's
template needs its argument; the probe records nothing."""
import json
import time

import pytest

from prefix_mortality.config import load_controls_config, load_engines_config, load_m8_config
from prefix_mortality.controls import Refusal
from prefix_mortality.hashing import sha256_file_bytes
from prefix_mortality.llamacpp import Client, EngineError
from prefix_mortality.m8 import probe, run
from prefix_mortality.record import load_request, read
from prefix_mortality.recorded import extract
from prefix_mortality.replay import assistant_turns
from prefix_mortality.summarize_m8 import evaluate, make_sim, schedule, summarize
from tests.fake_llamacpp import serve
from tests.test_m4 import CONTROLS, SYSTEM, TOOLS
from tests.test_replay import _sim

SHORT_SYSTEM = "Be brief."


def _m8_toml(registered: str, *, cache_ram_mib: int, bpt_geometry: str, interleave_ld: str) -> str:
    return f'''
[m8]
recorded_dir = "corpus/recorded/synthetic"
similarity_threshold = 0.10
cache_ram_mib = {cache_ram_mib}
corpus_dir = "corpus/live/m8"
results_dir = "results/m8"
registered_by = "{registered}"
[m8.kv_geometry.qwen]
{bpt_geometry}
[m8.kv_geometry.llama]
{bpt_geometry}
[m8.template_kwargs.llama]
tools_in_user_message = false
[m8.template_kwargs.qwen]
[m8.hypotheses.H-M8L1]
slots = 1
interleave = [1]
[m8.hypotheses.H-M8LD]
slots = 4
interleave = {interleave_ld}
'''


GEOMETRY_2 = "n_layer = 1\nn_head_kv = 1\nhead_dim = 1\nbytes_per_value = 1"          # 2 bytes per token
GEOMETRY_1000 = "n_layer = 125\nn_head_kv = 2\nhead_dim = 2\nbytes_per_value = 1"     # 1000 bytes per token
GEOMETRY_3000 = "n_layer = 125\nn_head_kv = 3\nhead_dim = 4\nbytes_per_value = 1"     # 3000: a 1 MiB cache holds two or three states


def _engines_toml(model_sha: str) -> str:
    models = "".join(f'''
[[engine.llamacpp.models]]
family = "{fam}"
hf_repo = "example/{fam}"
file = "model.gguf"
sha256 = "{model_sha}"
''' for fam in ("qwen", "llama"))
    return f'''
[engine.llamacpp]
repo = "https://github.com/ggml-org/llama.cpp"
release = "b11235"
commit = "6c7a87f7e5e5cd75b8a641c3471f2dee84a6ed17"
download = "llama-b11235-bin-macos-arm64.tar.gz"
download_sha256 = "{"d" * 64}"
registered_by = "0002"
''' + models


def _world(tmp_path, *, registered="0038", system=SYSTEM, tools=TOOLS, cache_ram_mib=1024, geometry=GEOMETRY_2,
           interleave_ld="[2, 3]", turns=(2, 4, 3, 1)):
    root = tmp_path / "repo"
    for d in ("config", "corpus/live/m8", "corpus/requests", "corpus/recorded", "results", "fixture"):
        (root / d).mkdir(parents=True)
    model = root / "model.gguf"
    model.write_bytes(b"not a model, only bytes to hash")
    (root / "fixture" / "system.txt").write_text(system, encoding="utf-8")
    (root / "fixture" / "tools.json").write_text(json.dumps(tools), encoding="utf-8")
    (root / "config" / "controls.toml").write_text(CONTROLS, encoding="utf-8")
    (root / "config" / "engines.toml").write_text(_engines_toml(sha256_file_bytes(model)), encoding="utf-8")
    (root / "config" / "m8.toml").write_text(
        _m8_toml(registered, cache_ram_mib=cache_ram_mib, bpt_geometry=geometry, interleave_ld=interleave_ld),
        encoding="utf-8")
    source = {"info": {"agent_info": {"llm": "agent"}, "user_info": {"llm": "user"},
                       "environment_info": {"domain_name": "airline", "tool_defs": None},
                       "git_commit": "c" * 40, "num_trials": 1, "max_steps": 1, "max_errors": 1, "seed": 0},
              "simulations": [_sim(str(i), t) for i, t in enumerate(turns)]}
    src = tmp_path / "source.json"
    src.write_text(json.dumps(source), encoding="utf-8")
    extract(src, root / "corpus" / "recorded" / "synthetic", source_repo="r", source_commit="c" * 40,
            source_rel_path="p.json")
    return {"root": root, "model": model, "fixture": root / "fixture",
            "controls": load_controls_config(root / "config" / "controls.toml", root),
            "engine": load_engines_config(root / "config" / "engines.toml")["llamacpp"],
            "m8": load_m8_config(root / "config" / "m8.toml", root)}


def _serve(w, *, slots, mode="faithful", family="qwen", **kw):
    return serve(mode, slots=slots, cache_limit_bytes=w["m8"].cache_limit_bytes,
                 bytes_per_token=w["m8"].bytes_per_token(family), n_ctx=kw.pop("n_ctx", 100000), **kw)


def _run(w, url, hid, c, family="qwen"):
    return run(w["m8"], w["controls"], w["engine"], family, hid, c, Client(url, 30.0), w["model"],
               repo_root=w["root"], fixture=w["fixture"])


def test_one_slot_replays_every_turn_in_file_order_and_matches(tmp_path):
    w = _world(tmp_path)
    with _serve(w, slots=1) as (url, _):
        report = _run(w, url, "H-M8L1", 1)
    assert report["outcome"] == "ALL MATCH"
    # the first request takes the LRU path on an empty server and searches the empty cache; no other does
    assert report["counts"] == {"requests": 24, "counted": 24, "matching": 24, "near": 0, "deaths": 0,
                                "cache_searched": 1, "restored": 0, "evicted": 0}
    convs = [r["conversation"] for r in report["requests"]]
    assert convs == ["0"] * 5 + ["1"] * 9 + ["2"] * 7 + ["3"] * 3           # file order, one after another
    firsts = [r for r in report["requests"] if r["own_previous_lcp"] is None]
    assert [r["conversation"] for r in firsts] == ["0", "1", "2", "3"]
    assert firsts[0]["cache_n"] == 0 and all(r["cache_n"] > 100 for r in firsts[1:])     # the shared head
    for r in report["requests"]:
        if r["own_previous_lcp"] is not None:
            assert r["predicted_reuse"] == r["own_previous_lcp"] == r["cache_n"]             # a strict extension
    assert [a["conversation"] for a in report["conversations"]] == ["0", "1", "2", "3"]
    assert all(a["share"] > 0.9 for a in report["conversations"][1:])


def test_interleaved_conversations_follow_the_round_robin_and_the_head_blocks_the_cache(tmp_path):
    w = _world(tmp_path)
    with _serve(w, slots=4) as (url, _):
        report = _run(w, url, "H-M8LD", 2)
    assert report["outcome"] == "ALL MATCH"
    order = [(r["conversation"], r["turn_number"]) for r in report["requests"]]
    assert order[:4] == [("1", 1), ("2", 1), ("1", 2), ("2", 2)] and order[-2:] == [("1", 8), ("1", 9)]
    # the long shared head keeps every request on the one held slot: the cache is never searched, and
    # each conversation loses its own last turn to the other's — the deaths the policy predicts
    assert report["counts"]["cache_searched"] == 1 and report["counts"]["deaths"] > 0
    assert all(d["predicted"] == d["reused"] for d in report["deaths"])


@pytest.mark.parametrize("geometry,expect_evicted", [(GEOMETRY_1000, False), (GEOMETRY_3000, True)])
def test_a_short_head_searches_the_cache_and_the_stand_in_agrees_with_the_simulator(tmp_path, geometry, expect_evicted):
    w = _world(tmp_path, system=SHORT_SYSTEM, tools=[], cache_ram_mib=1, geometry=geometry,
               interleave_ld="[2, 3]", turns=(6, 6, 5, 1))
    with _serve(w, slots=4) as (url, _):
        report = _run(w, url, "H-M8LD", 3)
    assert report["outcome"] == "ALL MATCH", report["mismatches"]
    assert report["counts"]["cache_searched"] > 0
    assert report["counts"]["restored"] > 0
    assert (report["counts"]["evicted"] > 0) == expect_evicted


def test_a_near_request_is_reported_and_not_counted(tmp_path, monkeypatch):
    import prefix_mortality.summarize_m8 as sm
    real = sm.make_sim

    def flagged(cfg, hyp, family):
        sim = real(cfg, hyp, family)
        inner = sim.predict

        def predict(new):
            p = inner(new)
            if sim.requests == 2:
                p.near.append("forced for the test")
            return p
        sim.predict = predict
        return sim
    monkeypatch.setattr(sm, "make_sim", flagged)
    monkeypatch.setattr("prefix_mortality.m8.make_sim", flagged)
    w = _world(tmp_path)
    with _serve(w, slots=1) as (url, _):
        report = _run(w, url, "H-M8L1", 1)
    assert report["outcome"] == "ALL MATCH"
    assert report["counts"]["near"] == 1 and report["counts"]["counted"] == 23
    assert report["requests"][2]["match"] is None and report["requests"][2]["near"] == ["forced for the test"]
    assert summarize(report["run_id"], repo_root=w["root"])[0] == report


def test_run_refuses_unregistered_wrong_slots_unknown_c_and_a_context_too_small(tmp_path):
    w = _world(tmp_path, registered="")
    with _serve(w, slots=1) as (url, _):
        with pytest.raises(Refusal, match="UNREGISTERED"):
            _run(w, url, "H-M8L1", 1)
    w = _world(tmp_path / "b")
    with _serve(w, slots=1) as (url, _):
        with pytest.raises(Refusal, match="requires a server reporting 4 slot"):
            _run(w, url, "H-M8LD", 2)
        with pytest.raises(Refusal, match="registers C in"):
            _run(w, url, "H-M8L1", 2)
    with _serve(w, slots=1, n_ctx=50) as (url, _):
        with pytest.raises(Refusal, match="does not fit the slot context"):
            _run(w, url, "H-M8L1", 1)
    assert not list((w["root"] / "corpus" / "live" / "m8").glob("*.jsonl"))


@pytest.mark.parametrize("mode,outcome,records", [("no_cache", "MISMATCH", 24), ("no_fields", "NOT MEASURABLE", 1)])
def test_a_run_goes_red_on_an_engine_that_breaks_a_rule(tmp_path, mode, outcome, records):
    w = _world(tmp_path)
    with _serve(w, slots=1, mode=mode) as (url, _):
        report = _run(w, url, "H-M8L1", 1)
    assert report["outcome"] == outcome and report["counts"]["requests"] == records


def test_summarize_reproduces_and_refuses_a_changed_record_prediction_schedule_config_or_corpus(tmp_path):
    w = _world(tmp_path)
    with _serve(w, slots=4) as (url, _):
        report = _run(w, url, "H-M8LD", 2)
    assert summarize(report["run_id"], repo_root=w["root"])[0] == report
    log = w["m8"].corpus_dir / f"{report['run_id']}.jsonl"
    original = log.read_text(encoding="utf-8")

    def rewrite(mutate):
        lines = [json.loads(l) for l in original.splitlines()]
        mutate(lines)
        log.write_text("".join(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n" for r in lines),
                       encoding="utf-8", newline="\n")

    def obs(lines):
        lines[3]["observed"]["cache_n"] += 1
    rewrite(obs)
    with pytest.raises(ValueError, match="do not reproduce"):
        summarize(report["run_id"], repo_root=w["root"])

    def pred(lines):
        lines[3]["predicted_reuse"] += 1
    rewrite(pred)
    with pytest.raises(ValueError, match="prediction other than the recomputation"):
        summarize(report["run_id"], repo_root=w["root"])

    def swap(lines):
        lines[2]["conversation"], lines[3]["conversation"] = lines[3]["conversation"], lines[2]["conversation"]
    rewrite(swap)
    with pytest.raises(ValueError, match="do not follow the schedule"):
        summarize(report["run_id"], repo_root=w["root"])
    log.write_text(original, encoding="utf-8", newline="\n")

    cfg = w["root"] / "config" / "m8.toml"
    text = cfg.read_text(encoding="utf-8")
    cfg.write_text(text.replace("cache_ram_mib = 1024", "cache_ram_mib = 1023"), encoding="utf-8")
    with pytest.raises(ValueError, match="different config"):
        summarize(report["run_id"], repo_root=w["root"])
    cfg.write_text(text, encoding="utf-8")

    sims = w["root"] / "corpus" / "recorded" / "synthetic" / "simulations.json"
    body = sims.read_text(encoding="utf-8")
    sims.write_text(body.replace("question 0", "question X", 1), encoding="utf-8")
    with pytest.raises(ValueError, match="does not hash to its provenance"):
        summarize(report["run_id"], repo_root=w["root"])


def test_llama_renders_only_with_its_registered_template_argument(tmp_path):
    w = _world(tmp_path)
    with _serve(w, slots=1, template="llama", family="llama") as (url, _):
        report = _run(w, url, "H-M8L1", 1, family="llama")
    assert report["outcome"] == "ALL MATCH" and report["counts"]["requests"] == 24
    plain = (w["root"] / "config" / "m8.toml").read_text(encoding="utf-8").replace("tools_in_user_message = false\n", "")
    (w["root"] / "config" / "m8.toml").write_text(plain, encoding="utf-8")
    w["m8"] = load_m8_config(w["root"] / "config" / "m8.toml", w["root"])
    _next_second()  # run ids carry seconds; a second run in the same second would be refused as a duplicate log
    with _serve(w, slots=1, template="llama", family="llama") as (url, _):
        with pytest.raises(EngineError, match="no first user message"):
            _run(w, url, "H-M8L1", 1, family="llama")


def _next_second() -> None:
    start = int(time.time())
    while int(time.time()) == start:
        time.sleep(0.05)


def test_schedule_and_probe_record_nothing(tmp_path):
    w = _world(tmp_path)
    sims = [_sim(str(i), t) for i, t in enumerate((2, 4, 3, 1))]
    plan = schedule(sims, 2)
    assert plan[:3] == [("1", 0, 1), ("2", 0, 1), ("1", 2, 2)] and len(plan) == 9 + 7
    assert len(schedule(sims, 1)) == sum(len(assistant_turns(s)) for s in sims)
    with _serve(w, slots=4) as (url, _):
        out = probe(w["m8"], w["controls"], "H-M8LD", "qwen", ["1", "2"], 3, Client(url, 30.0), fixture=w["fixture"])
    assert len(out["requests"]) == 6 and all(r["match"] for r in out["requests"])
    assert not list((w["root"] / "corpus" / "live" / "m8").glob("*.jsonl"))
    assert not list((w["root"] / "corpus" / "requests").glob("*.json"))


def test_a_sibling_config_is_named_in_the_records_and_read_by_the_summarizer(tmp_path):
    w = _world(tmp_path)
    text = (w["root"] / "config" / "m8.toml").read_text(encoding="utf-8")
    assert text.count("tools_in_user_message = false\n") == 1
    (w["root"] / "config" / "m8l.toml").write_text(
        text.replace("tools_in_user_message = false\n", "tools_in_user_message = false\ndate_string = \"11 Oct 2026\"\n"),
        encoding="utf-8")
    m8l = load_m8_config(w["root"] / "config" / "m8l.toml", w["root"])
    assert m8l.kwargs("llama") == {"tools_in_user_message": False, "date_string": "11 Oct 2026"}
    with _serve(w, slots=1, template="llama", family="llama") as (url, _):
        report = run(m8l, w["controls"], w["engine"], "llama", "H-M8L1", 1, Client(url, 30.0), w["model"],
                     repo_root=w["root"], fixture=w["fixture"])
    assert report["outcome"] == "ALL MATCH"
    recs = read(m8l.corpus_dir / f"{report['run_id']}.jsonl")
    assert all(r["config"] == "m8l" and set(r["config_sha256"]) == {"controls", "engines", "m8l"} for r in recs)
    stored = load_request(w["root"] / "corpus" / "requests", recs[0]["request_sha256"])
    assert "Today Date: 11 Oct 2026" in stored["rendered"]
    assert summarize(report["run_id"], repo_root=w["root"], config="m8l")[0] == report
    with pytest.raises(ValueError, match="names config 'm8l'"):
        summarize(report["run_id"], repo_root=w["root"])
