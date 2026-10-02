"""Serialization drift: on a stand-in that rebuilds tools as the server does, the four normalised
changes reuse n - 1 and the two kept changes reuse the common prefix; the readings are reported; a run
goes red on a stand-in that breaks a rule; the summarizer recomputes from disk."""
import json

import pytest

from prefix_mortality.config import load_controls_config, load_engines_config, load_m2_config
from prefix_mortality.controls import Refusal
from prefix_mortality.hashing import sha256_file_bytes
from prefix_mortality.llamacpp import Client
from prefix_mortality.m2 import probe, run
from prefix_mortality.record import read
from prefix_mortality.summarize_m2 import evaluate, summarize
from tests.fake_llamacpp import serve

SYSTEM = " ".join(f"Rule {i}: an agent must check the booking before it changes flight {i * 7}." for i in range(60))
TOOLS = [{"type": "function", "function": {"name": f"tool_{i}", "description": f"Look booking {i} up.",
                                           "parameters": {"type": "object",
                                                          "properties": {"id": {"type": "string"}, "day": {"type": "string"}},
                                                          "required": ["id"]}}}
         for i in range(11)]
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
ENGINES = '''
[engine.llamacpp]
repo = "https://github.com/ggml-org/llama.cpp"
release = "b11235"
commit = "6c7a87f7e5e5cd75b8a641c3471f2dee84a6ed17"
download = "llama-b11235-bin-macos-arm64.tar.gz"
download_sha256 = "{dl}"
registered_by = "0002"
[[engine.llamacpp.models]]
family = "qwen"
hf_repo = "example/model"
file = "model.gguf"
sha256 = "{sha}"
'''


def _world(tmp_path, *, registered="0015", repetitions=2):
    root = tmp_path / "repo"
    for d in ("config", "corpus/live/m2", "corpus/requests", "results", "fixture"):
        (root / d).mkdir(parents=True)
    model = root / "model.gguf"
    model.write_bytes(b"not a model, only bytes to hash")
    (root / "fixture" / "system.txt").write_text(SYSTEM, encoding="utf-8")
    (root / "fixture" / "tools.json").write_text(json.dumps(TOOLS), encoding="utf-8")
    (root / "config" / "controls.toml").write_text(CONTROLS, encoding="utf-8")
    (root / "config" / "m2.toml").write_text(f'''
[m2]
repetitions = {repetitions}
corpus_dir = "corpus/live/m2"
results_dir = "results/m2"
registered_by = "{registered}"
[m2.changes.S1]
reading = "identical"
[m2.changes.S2]
reading = "identical"
[m2.changes.S3]
reading = "differs"
[m2.changes.S4]
reading = "differs"
[m2.changes.S5]
reading = "identical"
[m2.changes.S6]
reading = "identical"
[m2.hypotheses.H-M2L1]
slots = 1
rule = "prefix"
''', encoding="utf-8")
    (root / "config" / "engines.toml").write_text(ENGINES.format(dl="d" * 64, sha=sha256_file_bytes(model)), encoding="utf-8")
    return {"root": root, "model": model,
            "m2": load_m2_config(root / "config" / "m2.toml", root),
            "controls": load_controls_config(root / "config" / "controls.toml", root),
            "engine": load_engines_config(root / "config" / "engines.toml")["llamacpp"]}


def _run(tmp_path, *, mode="faithful", slots=1, **kw):
    w = _world(tmp_path, **kw)
    with serve(mode, slots=slots) as (url, _):
        report = run(w["m2"], w["controls"], w["engine"], "qwen", "H-M2L1", Client(url, 30.0), w["model"],
                     repo_root=w["root"], fixture=w["root"] / "fixture")
    return w, report


def test_normalised_changes_reuse_n_minus_1_and_kept_changes_reuse_the_common_prefix(tmp_path):
    w, report = _run(tmp_path)
    assert report["outcome"] == "ALL MATCH", report["mismatches"] + report["failures"] + report["unmeasurable"]
    assert [t["change"] for t in report["trials"]] == ["S1", "S2", "S3", "S4", "S5", "S6"] * 2
    for t in report["trials"]:
        c = t["changed"]
        if t["change"] in ("S1", "S2", "S5", "S6"):
            assert t["render_diff"] is None and c["predicted_reuse"] == c["n"] - 1 == c["cache_n"]
        else:
            assert t["render_diff"] is not None and 0 < c["first_differing_token"] < c["n"] - 1
            assert c["cache_n"] == c["predicted_reuse"] == c["first_differing_token"]
        assert t["reading_agrees"] is True
        assert t["base"]["cache_n"] <= t["base"]["h"]
    s3, s4 = (next(t for t in report["trials"] if t["change"] == x) for x in ("S3", "S4"))
    assert s3["changed"]["first_differing_token"] < s4["changed"]["first_differing_token"], "tool 0 precedes tool 10"
    records = read(w["m2"].corpus_dir / f"{report['run_id']}.jsonl")
    assert len(records) == 24 and [r["role"] for r in records][:4] == ["base", "changed", "base", "changed"]
    assert all(r["experiment"] == "m2" and r["change"] in ("S1", "S2", "S3", "S4", "S5", "S6") for r in records)
    assert all("predicted_reuse" in r for r in records if r["role"] == "changed")
    assert all("predicted_reuse" not in r for r in records if r["role"] == "base")
    assert {r["server"]["total_slots"] for r in records} == {1}
    recomputed, text = summarize(report["run_id"], w["root"])
    assert recomputed == report and "ALL MATCH" in text and "readings disagreeing: 0" in text


def test_a_wrong_reading_is_reported_and_does_not_change_the_outcome(tmp_path):
    w = _world(tmp_path)
    toml = w["root"] / "config" / "m2.toml"
    toml.write_text(toml.read_text(encoding="utf-8").replace('[m2.changes.S1]\nreading = "identical"',
                                                              '[m2.changes.S1]\nreading = "differs"'), encoding="utf-8")
    w["m2"] = load_m2_config(toml, w["root"])
    with serve(slots=1) as (url, _):
        report = run(w["m2"], w["controls"], w["engine"], "qwen", "H-M2L1", Client(url, 30.0), w["model"],
                     repo_root=w["root"], fixture=w["root"] / "fixture")
    assert report["outcome"] == "ALL MATCH"
    assert [t["reading_agrees"] for t in report["trials"] if t["change"] == "S1"] == [False, False]
    assert report["readings_disagreeing"] == ["repetition 1 S1", "repetition 2 S1"]
    assert "readings disagreeing: 2" in summarize(report["run_id"], w["root"])[1]


@pytest.mark.parametrize("mode, outcome, reason, records", [
    ("no_cache", "MISMATCH", "predicted", 24),
    ("sticky", "FAILED CONTROL", "base_reuses_at_most_header is false", 2),
    ("no_fields", "NOT MEASURABLE", "the server reported no cache_n, prompt_n, usage_cached_tokens", 2),
])
def test_a_run_goes_red_on_an_engine_that_breaks_a_rule(tmp_path, mode, outcome, reason, records):
    w, report = _run(tmp_path, mode=mode)
    assert report["outcome"] == outcome
    assert any(reason in x for x in report["mismatches"] + report["failures"] + report["unmeasurable"]), report
    assert len(read(w["m2"].corpus_dir / f"{report['run_id']}.jsonl")) == records
    assert summarize(report["run_id"], w["root"])[0]["outcome"] == outcome


def test_run_refuses_unregistered_wrong_slots_and_unknown_hypothesis(tmp_path):
    w = _world(tmp_path / "a", registered="")
    with serve(slots=1) as (url, _):
        with pytest.raises(Refusal, match="m2.toml is UNREGISTERED"):
            run(w["m2"], w["controls"], w["engine"], "qwen", "H-M2L1", Client(url, 30.0), w["model"],
                repo_root=w["root"], fixture=w["root"] / "fixture")
    w = _world(tmp_path / "b")
    with serve(slots=4) as (url, _):
        with pytest.raises(Refusal, match="requires a server reporting 1 slot"):
            run(w["m2"], w["controls"], w["engine"], "qwen", "H-M2L1", Client(url, 30.0), w["model"],
                repo_root=w["root"], fixture=w["root"] / "fixture")
    with serve(slots=1) as (url, _):
        with pytest.raises(ValueError, match="registers no hypothesis"):
            run(w["m2"], w["controls"], w["engine"], "qwen", "H-M2LD", Client(url, 30.0), w["model"],
                repo_root=w["root"], fixture=w["root"] / "fixture")
    assert not list((w["root"] / "corpus" / "live" / "m2").iterdir()) and not list((w["root"] / "corpus" / "requests").iterdir())


def test_summarize_refuses_a_changed_record_wrong_slots_and_a_changed_config(tmp_path):
    w, report = _run(tmp_path, repetitions=1)
    log = w["m2"].corpus_dir / f"{report['run_id']}.jsonl"
    original = log.read_text(encoding="utf-8")

    def rewrite(change):
        records = read(log)
        change(records)
        log.write_text("".join(json.dumps(r, sort_keys=True) + "\n" for r in records), encoding="utf-8")

    rewrite(lambda rs: rs[1]["observed"].update(cache_n=rs[1]["observed"]["cache_n"] - 1))
    with pytest.raises(ValueError, match="do not reproduce the driver's report"):
        summarize(report["run_id"], w["root"])
    log.write_text(original, encoding="utf-8")
    rewrite(lambda rs: [r["server"].update(total_slots=4) for r in rs])
    with pytest.raises(ValueError, match="This run is not that experiment"):
        summarize(report["run_id"], w["root"])
    log.write_text(original, encoding="utf-8")
    assert summarize(report["run_id"], w["root"])[0] == report
    toml = w["root"] / "config" / "m2.toml"
    toml.write_text(toml.read_text(encoding="utf-8").replace("repetitions = 1", "repetitions = 2"), encoding="utf-8")
    with pytest.raises(ValueError, match="different config"):
        summarize(report["run_id"], w["root"])


def test_the_summarizer_checks_that_only_the_tools_text_changed(tmp_path):
    w, report = _run(tmp_path, repetitions=1)
    requests_dir = w["root"] / "corpus" / "requests"
    records = read(w["m2"].corpus_dir / f"{report['run_id']}.jsonl")
    # a request under S3's nonce whose user message differs too: stored as the engine would have, then pointed at
    from prefix_mortality.record import load_request, store_request
    from tests.fake_llamacpp import Engine
    s3 = next(r for r in records if r["change"] == "S3" and r["role"] == "changed")
    body = json.loads(load_request(requests_dir, s3["request_sha256"])["body"])
    body["messages"][-1]["content"] = "Goodbye."
    raw = json.dumps(body, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    e = Engine()
    rendered = e.render(body)
    s3["request_sha256"] = store_request(requests_dir, raw, rendered, e.tokenize(rendered))
    out = evaluate(records, requests_dir, w["m2"])
    assert out["outcome"] == "FAILED CONTROL"
    assert any("only_the_tools_changed is false" in f for f in out["failures"])
    # a record pointed at a request under another nonce is not a failed control but corrupt data: refused
    s4 = next(r for r in records if r["change"] == "S4" and r["role"] == "changed")
    s3["request_sha256"] = s4["request_sha256"]
    with pytest.raises(ValueError, match="not isolated"):
        evaluate(records, requests_dir, w["m2"])


def test_probe_reports_each_change_and_records_nothing(tmp_path):
    w = _world(tmp_path, registered="")
    with serve(slots=1) as (url, _):
        out = probe(w["m2"], w["controls"], "H-M2L1", ["S1", "S3"], Client(url, 30.0), fixture=w["root"] / "fixture")
        with pytest.raises(Refusal, match="unknown change"):
            probe(w["m2"], w["controls"], "H-M2L1", ["S9"], Client(url, 30.0), fixture=w["root"] / "fixture")
    s1, s3 = out["trials"]
    assert s1["render_diff"] is None and s1["predicted_reuse"] == s1["prompt_tokens"] - 1 and s1["match"]
    assert s3["render_diff"] is not None and s3["predicted_reuse"] == s3["first_differing_token"] and s3["match"]
    assert out["server"]["total_slots"] == 1 and out["slots_required"] == 1
    assert not list((w["root"] / "corpus" / "requests").iterdir()) and not list((w["root"] / "corpus" / "live" / "m2").iterdir())
