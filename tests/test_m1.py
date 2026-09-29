"""Edit position: each rule holds on a stand-in that follows it, the two rules can be told apart,
and a run goes red on a stand-in that breaks a rule."""
import json

import pytest

from prefix_mortality.config import load_controls_config, load_engines_config, load_m1_config
from prefix_mortality.controls import Refusal
from prefix_mortality.hashing import sha256_file_bytes
from prefix_mortality.llamacpp import Client
from prefix_mortality.m1 import probe, run
from prefix_mortality.record import read
from prefix_mortality.summarize_m1 import common_prefix, near_threshold, predict, summarize
from tests.fake_llamacpp import serve

SYSTEM = " ".join(f"Rule {i}: an agent must check the booking before it changes flight {i * 7}." for i in range(60))
TOOLS = [{"type": "function", "function": {"name": f"tool_{i}", "description": f"Look booking {i} up.",
                                           "parameters": {"type": "object", "properties": {"id": {"type": "string"}}}}}
         for i in range(3)]
SITES = ["system-0.000", "system-0.050", "system-0.500", "system-0.900", "tool-00", "tool-02", "user"]


def _world(tmp_path, *, registered="0006", repetitions=2):
    root = tmp_path / "repo"
    for d in ("config", "corpus/live/m1", "corpus/requests", "results", "fixture"):
        (root / d).mkdir(parents=True)
    model = root / "model.gguf"
    model.write_bytes(b"not a model, only bytes to hash")
    (root / "fixture" / "system.txt").write_text(SYSTEM, encoding="utf-8")
    (root / "fixture" / "tools.json").write_text(json.dumps(TOOLS), encoding="utf-8")
    (root / "config" / "controls.toml").write_text('''
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
''', encoding="utf-8")
    (root / "config" / "m1.toml").write_text(f'''
[m1]
repetitions = {repetitions}
replacement = "zebra"
system_fractions = [0.0, 0.05, 0.5, 0.9]
tool_indexes = [0, 2]
edit_user_message = true
similarity_threshold = 0.10
threshold_margin = 0.002
corpus_dir = "corpus/live/m1"
results_dir = "results/m1"
registered_by = "{registered}"
[m1.hypotheses.H-M1L1]
slots = 1
rule = "prefix"
[m1.hypotheses.H-M1LD]
slots = 4
rule = "threshold"
[m1.hypotheses.H-M1LX]
slots = 4
rule = "prefix"
[m1.hypotheses.H-M1LY]
slots = 1
rule = "threshold"
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
    return {"root": root, "model": model,
            "m1": load_m1_config(root / "config" / "m1.toml", root),
            "controls": load_controls_config(root / "config" / "controls.toml", root),
            "engine": load_engines_config(root / "config" / "engines.toml")["llamacpp"]}


def _run(tmp_path, hid, *, mode="faithful", slots=1, **kw):
    w = _world(tmp_path, **kw)
    with serve(mode, slots=slots) as (url, _):
        report = run(w["m1"], w["controls"], w["engine"], "qwen", hid, Client(url, 30.0), w["model"],
                     repo_root=w["root"], fixture=w["root"] / "fixture")
    return w, report


def _below(report) -> set[str]:
    return {t["site"] for t in report["trials"]
            if t["edited"]["first_differing_token"] / t["edited"]["n"] <= report["similarity_threshold"]}


def test_the_prefix_rule_holds_on_one_slot(tmp_path):
    w, report = _run(tmp_path, "H-M1L1")
    assert report["outcome"] == "ALL MATCH" and not report["mismatches"] and not report["failures"]
    assert [t["site"] for t in report["trials"]] == SITES * 2
    for t in report["trials"]:
        b, e = t["base"], t["edited"]
        assert b["cache_n"] <= b["h"] < e["first_differing_token"] < e["n"]
        assert e["cache_n"] == e["predicted_reuse"] == e["first_differing_token"]
    first = [t["edited"]["first_differing_token"] for t in report["trials"][:len(SITES)]]
    assert first == sorted(first) and len(set(first)) == len(first), "sites are in prompt order and distinct"
    records = read(w["m1"].corpus_dir / f"{report['run_id']}.jsonl")
    assert [r["role"] for r in records] == ["base", "edited"] * (2 * len(SITES))
    assert len({r["nonce"] for r in records}) == 2 * len(SITES), "one nonce per trial, shared by its two requests"
    assert all("predicted_reuse" in r for r in records if r["role"] == "edited")
    assert all("predicted_reuse" not in r for r in records if r["role"] == "base")
    assert report["run_id"].endswith("-qwen-H-M1L1") and {r["server"]["total_slots"] for r in records} == {1}
    recomputed, text = summarize(report["run_id"], w["root"])
    assert recomputed == report and "ALL MATCH" in text and f"trials counted: {2 * len(SITES)}" in text


def test_the_threshold_rule_holds_at_the_defaults(tmp_path):
    w, report = _run(tmp_path, "H-M1LD", slots=4)
    assert report["outcome"] == "ALL MATCH", report["mismatches"] + report["failures"]
    below = _below(report)
    assert below == {"system-0.000", "system-0.050"}, "the test's sites must fall on both sides of the threshold"
    for t in report["trials"]:
        e = t["edited"]
        assert t["base"]["cache_n"] == 0
        assert e["cache_n"] == (0 if t["site"] in below else e["first_differing_token"])
    assert summarize(report["run_id"], w["root"])[0] == report


@pytest.mark.parametrize("hid, slots", [("H-M1LX", 4), ("H-M1LY", 1)])
def test_the_wrong_rule_for_a_configuration_is_a_mismatch_below_the_threshold_only(tmp_path, hid, slots):
    w, report = _run(tmp_path, hid, slots=slots)
    assert report["outcome"] == "MISMATCH" and not report["failures"]
    assert {m.split(":")[0].split()[-1] for m in report["mismatches"]} == _below(report) == {"system-0.000", "system-0.050"}
    assert len(report["trials"]) == 2 * len(SITES), "a prediction that is not met does not stop the run"
    assert summarize(report["run_id"], w["root"])[0]["outcome"] == "MISMATCH"


@pytest.mark.parametrize("mode, outcome, reason, records", [
    ("no_cache", "MISMATCH", "predicted", 4 * len(SITES)),
    ("sticky", "FAILED CONTROL", "base_reuses_at_most_header is false", 2),
    ("no_fields", "NOT MEASURABLE", "the server reported no cache_n, prompt_n, usage_cached_tokens", 2),
])
def test_a_run_goes_red_on_an_engine_that_breaks_a_rule(tmp_path, mode, outcome, reason, records):
    w, report = _run(tmp_path, "H-M1L1", mode=mode)
    assert report["outcome"] == outcome
    assert any(reason in x for x in report["mismatches"] + report["failures"] + report["unmeasurable"]), report
    assert len(read(w["m1"].corpus_dir / f"{report['run_id']}.jsonl")) == records
    assert summarize(report["run_id"], w["root"])[0]["outcome"] == outcome


def test_run_refuses_an_unregistered_config_and_a_server_with_the_wrong_number_of_slots(tmp_path):
    w = _world(tmp_path / "a", registered="")
    with serve() as (url, _):
        with pytest.raises(Refusal, match="m1.toml is UNREGISTERED"):
            run(w["m1"], w["controls"], w["engine"], "qwen", "H-M1L1", Client(url, 30.0), w["model"],
                repo_root=w["root"], fixture=w["root"] / "fixture")
    w = _world(tmp_path / "b")
    for hid, slots, msg in (("H-M1L1", 4, "requires a server reporting 1 slot"),
                            ("H-M1LD", 1, "requires a server reporting 4 slot")):
        with serve(slots=slots) as (url, _):
            with pytest.raises(Refusal, match=msg):
                run(w["m1"], w["controls"], w["engine"], "qwen", hid, Client(url, 30.0), w["model"],
                    repo_root=w["root"], fixture=w["root"] / "fixture")
    with serve() as (url, _):
        with pytest.raises(ValueError, match="registers no hypothesis"):
            run(w["m1"], w["controls"], w["engine"], "qwen", "H-M1LZ", Client(url, 30.0), w["model"],
                repo_root=w["root"], fixture=w["root"] / "fixture")
    assert not list((w["root"] / "corpus" / "live" / "m1").iterdir()), "a refused run records nothing"
    assert not list((w["root"] / "corpus" / "requests").iterdir())


def test_summarize_refuses_a_changed_record_a_changed_prediction_wrong_slots_and_a_changed_config(tmp_path):
    w, report = _run(tmp_path, "H-M1L1")
    log = w["m1"].corpus_dir / f"{report['run_id']}.jsonl"
    original = log.read_text(encoding="utf-8")

    def rewrite(change):
        records = read(log)
        change(records)
        log.write_text("".join(json.dumps(r, sort_keys=True) + "\n" for r in records), encoding="utf-8")

    rewrite(lambda rs: rs[1]["observed"].update(cache_n=rs[1]["observed"]["cache_n"] - 1))
    with pytest.raises(ValueError, match="do not reproduce the driver's report"):
        summarize(report["run_id"], w["root"])

    log.write_text(original, encoding="utf-8")
    rewrite(lambda rs: rs[1].update(predicted_reuse=rs[1]["predicted_reuse"] + 1))   # a prediction moved after the fact
    with pytest.raises(ValueError, match="do not reproduce the driver's report"):
        summarize(report["run_id"], w["root"])

    log.write_text(original, encoding="utf-8")
    rewrite(lambda rs: [r["server"].update(total_slots=4) for r in rs])
    with pytest.raises(ValueError, match="This run is not that experiment"):
        summarize(report["run_id"], w["root"])

    log.write_text(original, encoding="utf-8")
    assert summarize(report["run_id"], w["root"])[0] == report                        # restored: accepted again
    toml = w["root"] / "config" / "m1.toml"
    toml.write_text(toml.read_text(encoding="utf-8").replace("similarity_threshold = 0.10",
                                                              "similarity_threshold = 0.01"), encoding="utf-8")
    with pytest.raises(ValueError, match="different config"):
        summarize(report["run_id"], w["root"])


def test_probe_reports_each_site_and_records_nothing(tmp_path):
    w = _world(tmp_path, registered="")
    with serve(slots=4) as (url, _):
        out = probe(w["m1"], w["controls"], "H-M1LD", ["system-0.050", "system-0.500"], Client(url, 30.0),
                    fixture=w["root"] / "fixture")
        with pytest.raises(Refusal, match="unknown site"):
            probe(w["m1"], w["controls"], "H-M1LD", ["system-0.123"], Client(url, 30.0), fixture=w["root"] / "fixture")
    low, high = out["trials"]
    assert out["server"]["total_slots"] == 4 and out["rule"] == "threshold"
    assert low["predicted_reuse"] == 0 < low["first_differing_token"] and low["match"]
    assert high["predicted_reuse"] == high["first_differing_token"] == high["edited"]["observed"]["cache_n"] and high["match"]
    assert not list((w["root"] / "corpus" / "requests").iterdir()) and not list((w["root"] / "corpus" / "live" / "m1").iterdir())


def test_the_rules_and_the_margin():
    assert common_prefix([1, 2, 3, 4], [1, 2, 9, 4]) == 2 and common_prefix([], [1]) == 0
    assert common_prefix([1, 2], [1, 2, 3]) == 2
    assert predict("prefix", 5, 1000, 0.10) == 5
    assert predict("threshold", 100, 1000, 0.10) == 0, "the server's comparison is strict"
    assert predict("threshold", 101, 1000, 0.10) == 101 and predict("threshold", 99, 1000, 0.10) == 0
    with pytest.raises(ValueError, match="unknown rule"):
        predict("nearest", 1, 2, 0.10)
    assert near_threshold("threshold", 101, 1000, 0.10, 0.002) and near_threshold("threshold", 99, 1000, 0.10, 0.002)
    assert not near_threshold("threshold", 103, 1000, 0.10, 0.002)
    assert not near_threshold("prefix", 100, 1000, 0.10, 0.002), "the prefix rule has no threshold"
