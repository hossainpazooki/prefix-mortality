"""Eviction by intervening requests: the cliff falls where the registered cache fills on a stand-in
that follows the reading, a stand-in with another cache size is a mismatch reported as a bracket, a
run goes red on a stand-in that breaks a rule, and a prompt that does not fit the slot context is
refused, not read."""
import json

import pytest

from prefix_mortality.config import load_controls_config, load_engines_config, load_m7_config
from prefix_mortality.controls import Refusal, build_body
from prefix_mortality.hashing import sha256_file_bytes
from prefix_mortality.llamacpp import Client
from prefix_mortality.m7 import probe, run
from prefix_mortality.record import read
from prefix_mortality.summarize_m7 import bound_by, evaluate, prediction, summarize, token_pass
from tests.fake_llamacpp import Engine, serve

SYSTEM = " ".join(f"Rule {i}: an agent must check the booking before it changes flight {i * 7}." for i in range(60))
TOOLS = [{"type": "function", "function": {"name": f"tool_{i}", "description": f"Look booking {i} up.",
                                           "parameters": {"type": "object", "properties": {"id": {"type": "string"}}}}}
         for i in range(3)]
BPT = 4 * 2 * 1 * 512 * 1                 # the test geometry below: 4 layers, 1 KV head, width 512, 1 byte
SCHEDULE = [0, 1, 3, 4, 5, 6, 8]
CAPACITY = 4                              # entries the registered cache holds; the cliff is at K = 5

CONTROLS = '''
[controls]
repetitions = 2
length_tolerance_tokens = 16
max_tokens = 1
temperature = 0.0
nonce_bytes = 16
seed = 0
request_timeout_seconds = 30.0
user_message = "Hello."
corpus_dir = "corpus/live/controls"
results_dir = "results/controls"
registered_by = "0002"
'''


def _prompt_tokens(controls) -> int:
    """The stand-in's token count of the base request; a nonce is one word, so it is the same for every nonce."""
    e = Engine()
    return len(e.tokenize(e.render(json.loads(build_body(controls, SYSTEM, TOOLS, "0" * 32)))))


def _world(tmp_path, *, registered="0012", repetitions=2):
    root = tmp_path / "repo"
    for d in ("config", "corpus/live/m7", "corpus/requests", "results", "fixture"):
        (root / d).mkdir(parents=True)
    model = root / "model.gguf"
    model.write_bytes(b"not a model, only bytes to hash")
    (root / "fixture" / "system.txt").write_text(SYSTEM, encoding="utf-8")
    (root / "fixture" / "tools.json").write_text(json.dumps(TOOLS), encoding="utf-8")
    (root / "config" / "controls.toml").write_text(CONTROLS, encoding="utf-8")
    controls = load_controls_config(root / "config" / "controls.toml", root)
    n = _prompt_tokens(controls)
    state = n * BPT
    mib = int((CAPACITY + 0.5) * state) // 2**20
    assert CAPACITY * state <= mib * 2**20 < (CAPACITY + 1) * state, "the registered cache must hold exactly CAPACITY prompts"
    (root / "config" / "m7.toml").write_text(f'''
[m7]
repetitions = {repetitions}
k_schedule = {SCHEDULE}
cache_ram_mib = {mib}
corpus_dir = "corpus/live/m7"
results_dir = "results/m7"
registered_by = "{registered}"
[m7.kv_geometry.qwen]
n_layer = 4
n_head_kv = 1
head_dim = 512
bytes_per_value = 1
[m7.hypotheses.H-M7LD]
slots = 4
''', encoding="utf-8")
    (root / "config" / "engines.toml").write_text(f'''
[engine.llamacpp]
repo = "https://github.com/ggml-org/llama.cpp"
release = "b11235"
commit = "6c7a87f7e5e5cd75b8a641c3471f2dee84a6ed17"
download = "llama-b11235-bin-macos-arm64.tar.gz"
download_sha256 = "{"d" * 64}"
registered_by = "0002"
[[engine.llamacpp.models]]
family = "qwen"
hf_repo = "example/model"
file = "model.gguf"
sha256 = "{sha256_file_bytes(model)}"
''', encoding="utf-8")
    return {"root": root, "model": model, "n": n, "state": state, "limit": mib * 2**20, "controls": controls,
            "m7": load_m7_config(root / "config" / "m7.toml", root),
            "engine": load_engines_config(root / "config" / "engines.toml")["llamacpp"]}


def _run(tmp_path, *, mode="faithful", slots=4, limit=None, n_ctx=8192, report_n_ctx=True, **kw):
    w = _world(tmp_path, **kw)
    with serve(mode, slots=slots, cache_limit_bytes=w["limit"] if limit is None else limit(w), bytes_per_token=BPT,
               n_ctx=n_ctx, report_n_ctx=report_n_ctx) as (url, engine):
        report = run(w["m7"], w["controls"], w["engine"], "qwen", "H-M7LD", Client(url, 30.0), w["model"],
                     repo_root=w["root"], fixture=w["root"] / "fixture")
    return w, report, engine


def test_the_cliff_falls_where_the_registered_cache_fills(tmp_path):
    w, report, engine = _run(tmp_path)
    assert report["outcome"] == "ALL MATCH", report["mismatches"] + report["failures"] + report["unmeasurable"]
    assert [t["k"] for t in report["trials"]] == SCHEDULE * 2 and engine.evictions > 0
    for t in report["trials"]:
        s = t["resend"]
        assert t["anchor"]["cache_n"] == 0 and all(f["cache_n"] == 0 for f in t["foreign"]) and len(t["foreign"]) == t["k"]
        assert s["n"] == w["n"] and s["modelled_cache_tokens"] == w["n"] * max(t["k"], 1)
        assert s["fits_size_limit"] is (t["k"] <= CAPACITY)
        assert s["cache_n"] == s["predicted_reuse"] == (w["n"] - 1 if t["k"] <= CAPACITY else 0)
        assert t["bound_by"] == ("neither" if t["k"] <= CAPACITY else "size and tokens")
    assert report["bracket"] == {"largest_k_kept": CAPACITY, "smallest_k_lost": CAPACITY + 1, "other_readings": []}
    records = read(w["m7"].corpus_dir / f"{report['run_id']}.jsonl")
    assert len(records) == 2 * sum(k + 2 for k in SCHEDULE)
    assert [r["role"] for r in records][:5] == ["anchor", "resend", "anchor", "foreign", "resend"]
    first = [r for r in records if r["repetition"] == 1 and r["k"] == 3]
    assert [r["role"] for r in first] == ["anchor", "foreign", "foreign", "foreign", "resend"]
    assert first[0]["request_sha256"] == first[-1]["request_sha256"] and first[0]["nonce"] == first[-1]["nonce"]
    assert len({r["nonce"] for r in first}) == 4 and [r["index"] for r in first] == [None, 1, 2, 3, None]
    assert all(r["predicted_reuse"] == 0 for r in records if r["role"] != "resend")
    assert all("fits_size_limit" in r for r in records if r["role"] == "resend")
    assert all("fits_size_limit" not in r for r in records if r["role"] != "resend")
    assert report["run_id"].endswith("-qwen-H-M7LD") and {r["server"]["n_ctx"] for r in records} == {8192}
    recomputed, text = summarize(report["run_id"], w["root"])
    assert recomputed == report and "ALL MATCH" in text and f"largest K kept: {CAPACITY}; smallest K lost: {CAPACITY + 1}" in text


def test_a_cache_smaller_than_registered_is_a_mismatch_reported_as_a_bracket(tmp_path):
    w, report, _ = _run(tmp_path, limit=lambda w: int(2.5 * w["state"]))     # the stand-in holds two prompts
    assert report["outcome"] == "MISMATCH" and not report["failures"]
    assert {t["k"] for t in report["trials"] if not t["match"]} == {3, 4}, "predicted to survive, evicted"
    assert len(report["trials"]) == 2 * len(SCHEDULE), "a prediction that is not met does not stop the run"
    assert report["bracket"] == {"largest_k_kept": 1, "smallest_k_lost": 3, "other_readings": []}
    assert summarize(report["run_id"], w["root"])[0]["outcome"] == "MISMATCH"


@pytest.mark.parametrize("mode, outcome, reason, records", [
    ("no_cache", "MISMATCH", "predicted", 2 * sum(k + 2 for k in SCHEDULE)),
    ("sticky", "FAILED CONTROL", "anchor_reuses_0 is false", 2),
    ("no_fields", "NOT MEASURABLE", "the server reported no cache_n, prompt_n, usage_cached_tokens", 2),
])
def test_a_run_goes_red_on_an_engine_that_breaks_a_rule(tmp_path, mode, outcome, reason, records):
    w, report, _ = _run(tmp_path, mode=mode)
    assert report["outcome"] == outcome
    assert any(reason in x for x in report["mismatches"] + report["failures"] + report["unmeasurable"]), report
    assert len(read(w["m7"].corpus_dir / f"{report['run_id']}.jsonl")) == records
    assert summarize(report["run_id"], w["root"])[0]["outcome"] == outcome


def test_run_refuses_unregistered_wrong_slots_and_a_context_the_anchor_does_not_fit(tmp_path):
    def go(w, url):
        return run(w["m7"], w["controls"], w["engine"], "qwen", "H-M7LD", Client(url, 30.0), w["model"],
                   repo_root=w["root"], fixture=w["root"] / "fixture")
    w = _world(tmp_path / "a", registered="")
    with serve(slots=4) as (url, _):
        with pytest.raises(Refusal, match="m7.toml is UNREGISTERED"):
            go(w, url)
    w = _world(tmp_path / "b")
    with serve(slots=1) as (url, _):
        with pytest.raises(Refusal, match="requires a server reporting 4 slot"):
            go(w, url)
    with serve(slots=4, n_ctx=w["n"]) as (url, engine):               # the anchor is exactly the context: refused
        with pytest.raises(Refusal, match=f"anchor \\({w['n']} tokens\\) does not fit the slot context \\({w['n']} tokens\\)"):
            go(w, url)
        assert engine.requests == 0, "nothing was sent"
    with serve(slots=4, report_n_ctx=False) as (url, _):
        with pytest.raises(Refusal, match="reports no slot context"):
            go(w, url)
    with serve(slots=4) as (url, _):
        with pytest.raises(ValueError, match="registers no hypothesis"):
            run(w["m7"], w["controls"], w["engine"], "qwen", "H-M7LX", Client(url, 30.0), w["model"],
                repo_root=w["root"], fixture=w["root"] / "fixture")
        with pytest.raises(ValueError, match="no kv_geometry for family"):
            run(w["m7"], w["controls"], w["engine"], "llama", "H-M7LD", Client(url, 30.0), w["model"],
                repo_root=w["root"], fixture=w["root"] / "fixture")
    assert not list((w["root"] / "corpus" / "live" / "m7").iterdir()), "a refused run records nothing"
    assert not list((w["root"] / "corpus" / "requests").iterdir())


def test_the_summarizer_reads_the_slot_context_and_the_date_from_the_records(tmp_path):
    w, report, _ = _run(tmp_path, repetitions=1)
    log = w["m7"].corpus_dir / f"{report['run_id']}.jsonl"
    requests_dir = w["root"] / "corpus" / "requests"

    def changed(change):
        records = read(log)
        change(records)
        return evaluate(records, requests_dir, w["m7"])

    small = changed(lambda rs: [r["server"].update(n_ctx=w["n"]) for r in rs])
    assert small["outcome"] == "NOT MEASURABLE"
    assert all(f"a request of {w['n']} tokens does not fit the slot context of {w['n']} tokens" in x
               for x in small["unmeasurable"]) and len(small["unmeasurable"]) == sum(k + 2 for k in SCHEDULE)
    gone = changed(lambda rs: [r["server"].pop("n_ctx") for r in rs])
    assert gone["outcome"] == "NOT MEASURABLE" and all("reported no slot context" in x for x in gone["unmeasurable"])
    assert all(t["bound_by"] is None for t in gone["trials"])
    with pytest.raises(ValueError, match="mix slot contexts"):
        changed(lambda rs: rs[0]["server"].update(n_ctx=4096))
    dated = changed(lambda rs: rs[-1].update(local_date="1999-12-31"))
    assert dated["outcome"] == "NOT MEASURABLE" and len(dated["unmeasurable"]) == 1
    assert "the local date changed during the trial" in dated["unmeasurable"][0]
    with pytest.raises(ValueError, match="This run is not that experiment"):
        changed(lambda rs: [r["server"].update(total_slots=1) for r in rs])
    with pytest.raises(ValueError, match="not in the registered schedule"):
        changed(lambda rs: rs[0].update(k=2))
    assert changed(lambda rs: None) == report, "untouched records reproduce the report"


def test_summarize_refuses_a_changed_record_a_changed_prediction_and_a_changed_config(tmp_path):
    w, report, _ = _run(tmp_path, repetitions=1)
    log = w["m7"].corpus_dir / f"{report['run_id']}.jsonl"
    original = log.read_text(encoding="utf-8")

    def rewrite(change):
        records = read(log)
        change(records)
        log.write_text("".join(json.dumps(r, sort_keys=True) + "\n" for r in records), encoding="utf-8")

    rewrite(lambda rs: rs[1]["observed"].update(cache_n=rs[1]["observed"]["cache_n"] - 1))
    with pytest.raises(ValueError, match="do not reproduce the driver's report"):
        summarize(report["run_id"], w["root"])
    log.write_text(original, encoding="utf-8")
    rewrite(lambda rs: rs[1].update(predicted_reuse=0))                                  # a prediction moved after the fact
    with pytest.raises(ValueError, match="do not reproduce the driver's report"):
        summarize(report["run_id"], w["root"])
    log.write_text(original, encoding="utf-8")
    assert summarize(report["run_id"], w["root"])[0] == report
    toml = w["root"] / "config" / "m7.toml"
    toml.write_text(toml.read_text(encoding="utf-8").replace("cache_ram_mib = ", "cache_ram_mib = 1"), encoding="utf-8")
    with pytest.raises(ValueError, match="different config"):
        summarize(report["run_id"], w["root"])


def test_probe_reports_each_k_and_records_nothing(tmp_path):
    w = _world(tmp_path, registered="")
    with serve(slots=4, cache_limit_bytes=w["limit"], bytes_per_token=BPT) as (url, _):
        out = probe(w["m7"], w["controls"], "H-M7LD", "qwen", [1, CAPACITY + 1], Client(url, 30.0),
                    fixture=w["root"] / "fixture")
        with pytest.raises(Refusal, match="K must be 0 or more"):
            probe(w["m7"], w["controls"], "H-M7LD", "qwen", [-1], Client(url, 30.0), fixture=w["root"] / "fixture")
    kept, lost = out["trials"]
    assert out["server"]["total_slots"] == 4 and out["bytes_per_token"] == BPT and out["slots_required"] == 4
    assert kept["predicted_reuse"] == kept["resend"]["cache_n"] == w["n"] - 1 and kept["match"]
    assert lost["predicted_reuse"] == lost["resend"]["cache_n"] == 0 and lost["match"] and len(lost["foreign_reuse"]) == CAPACITY + 1
    assert kept["anchor_reuse"] == 0 and set(lost["foreign_reuse"]) == {0}
    assert not list((w["root"] / "corpus" / "requests").iterdir()) and not list((w["root"] / "corpus" / "live" / "m7").iterdir())


def test_the_rule_on_the_pinned_servers_numbers(tmp_path):
    """Qwen3-8B at 4,870 tokens a prompt, 147,456 bytes a token, 8192 MiB: eleven prompts fit, twelve do not."""
    (tmp_path / "m7.toml").write_text('''
[m7]
repetitions = 1
k_schedule = [11, 12]
cache_ram_mib = 8192
corpus_dir = "c"
results_dir = "r"
registered_by = ""
[m7.kv_geometry.qwen]
n_layer = 36
n_head_kv = 8
head_dim = 128
bytes_per_value = 2
[m7.hypotheses.H-M7LD]
slots = 4
''', encoding="utf-8")
    cfg = load_m7_config(tmp_path / "m7.toml", tmp_path)
    assert cfg.bytes_per_token("qwen") == 147456 and cfg.cache_limit_bytes == 8192 * 2**20
    eleven, twelve = prediction(cfg, "qwen", 4870, [4870] * 11), prediction(cfg, "qwen", 4870, [4870] * 12)
    assert eleven["predicted_reuse"] == 4869 and eleven["fits_size_limit"] and eleven["modelled_cache_tokens"] == 11 * 4870
    assert twelve["predicted_reuse"] == 0 and not twelve["fits_size_limit"] and twelve["modelled_cache_bytes"] == 12 * 4870 * 147456
    assert prediction(cfg, "qwen", 4870, [])["predicted_reuse"] == 4869, "K = 0: the anchor alone fits"
    assert prediction(cfg, "qwen", 4870, [4870])["modelled_cache_tokens"] == 4870, "K = 1: the foreign prompt is in its slot"
    tp = token_pass(cfg, "qwen", twelve["modelled_cache_tokens"], 40960)
    assert tp["token_limit"] == 58254 and not tp["fits_token_limit"]
    assert bound_by(twelve["fits_size_limit"], tp["fits_token_limit"]) == "size and tokens"
    assert bound_by(False, token_pass(cfg, "qwen", twelve["modelled_cache_tokens"], 10**6)["fits_token_limit"]) == "size"
    assert bound_by(True, True) == "neither" and bound_by(True, False) == "tokens"
