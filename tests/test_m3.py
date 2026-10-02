"""Templating: on a llama-like stand-in a date change ends the prefix at the head (one slot: a few
tokens; defaults: nothing), and a thinking switch changes nothing; on a qwen-like stand-in the
reverse, and the thinking switch ends only the tail. The summarizer recomputes from disk."""
import json

import pytest

from prefix_mortality.config import load_controls_config, load_engines_config, load_m3_config
from prefix_mortality.controls import Refusal
from prefix_mortality.hashing import sha256_file_bytes
from prefix_mortality.llamacpp import Client
from prefix_mortality.m3 import probe, run
from prefix_mortality.record import load_request, read
from prefix_mortality.summarize_m3 import evaluate, summarize
from tests.fake_llamacpp import serve
from tests.test_m2 import CONTROLS, ENGINES, SYSTEM, TOOLS


def _world(tmp_path, *, registered="0015", repetitions=2):
    root = tmp_path / "repo"
    for d in ("config", "corpus/live/m3", "corpus/requests", "results", "fixture"):
        (root / d).mkdir(parents=True)
    model = root / "model.gguf"
    model.write_bytes(b"not a model, only bytes to hash")
    (root / "fixture" / "system.txt").write_text(SYSTEM, encoding="utf-8")
    (root / "fixture" / "tools.json").write_text(json.dumps(TOOLS), encoding="utf-8")
    (root / "config" / "controls.toml").write_text(CONTROLS, encoding="utf-8")
    (root / "config" / "m3.toml").write_text(f'''
[m3]
repetitions = {repetitions}
similarity_threshold = 0.10
threshold_margin = 0.002
corpus_dir = "corpus/live/m3"
results_dir = "results/m3"
registered_by = "{registered}"
[m3.base_kwargs]
date_string = "01 Oct 2026"
enable_thinking = true
[m3.changes.T1]
key = "date_string"
value = "02 Oct 2026"
[m3.changes.T2]
key = "enable_thinking"
value = false
[m3.hypotheses.H-M3L1]
slots = 1
rule = "prefix"
[m3.hypotheses.H-M3LD]
slots = 4
rule = "threshold"
''', encoding="utf-8")
    (root / "config" / "engines.toml").write_text(ENGINES.format(dl="d" * 64, sha=sha256_file_bytes(model)), encoding="utf-8")
    return {"root": root, "model": model,
            "m3": load_m3_config(root / "config" / "m3.toml", root),
            "controls": load_controls_config(root / "config" / "controls.toml", root),
            "engine": load_engines_config(root / "config" / "engines.toml")["llamacpp"]}


def _run(tmp_path, hid, template, *, mode="faithful", slots=1, **kw):
    w = _world(tmp_path, **kw)
    with serve(mode, slots=slots, template=template) as (url, _):
        report = run(w["m3"], w["controls"], w["engine"], "qwen", hid, Client(url, 30.0), w["model"],
                     repo_root=w["root"], fixture=w["root"] / "fixture")
    return w, report


def _by_change(report):
    return {c: [t for t in report["trials"] if t["change"] == c] for c in ("T1", "T2")}


def test_llama_like_one_slot_the_date_kills_the_head_and_thinking_changes_nothing(tmp_path):
    w, report = _run(tmp_path, "H-M3L1", "llama")
    assert report["outcome"] == "ALL MATCH", report["mismatches"] + report["failures"] + report["unmeasurable"]
    by = _by_change(report)
    for t in by["T1"]:
        c = t["changed"]
        assert t["render_diff"] == len("<|system|>\nToday Date: 0") and 0 < c["first_differing_token"] < 16
        assert c["cache_n"] == c["predicted_reuse"] == c["first_differing_token"]
    for t in by["T2"]:
        c = t["changed"]
        assert t["render_diff"] is None and c["cache_n"] == c["predicted_reuse"] == c["n"] - 1
    assert summarize(report["run_id"], w["root"])[0] == report


def test_llama_like_defaults_the_date_kills_everything(tmp_path):
    w, report = _run(tmp_path, "H-M3LD", "llama", slots=4)
    assert report["outcome"] == "ALL MATCH", report["mismatches"] + report["failures"]
    by = _by_change(report)
    assert all(t["changed"]["predicted_reuse"] == 0 == t["changed"]["cache_n"] for t in by["T1"])
    assert all(t["changed"]["first_differing_token"] / t["changed"]["n"] < 0.10 for t in by["T1"])
    assert all(t["changed"]["cache_n"] == t["changed"]["n"] - 1 for t in by["T2"])
    assert all(t["base"]["cache_n"] == 0 for t in report["trials"])


def test_qwen_like_the_date_changes_nothing_and_thinking_ends_only_the_tail(tmp_path):
    for hid, slots in (("H-M3L1", 1), ("H-M3LD", 4)):
        w, report = _run(tmp_path / hid, hid, "qwen", slots=slots)
        assert report["outcome"] == "ALL MATCH", report["mismatches"] + report["failures"]
        by = _by_change(report)
        assert all(t["render_diff"] is None and t["changed"]["cache_n"] == t["changed"]["n"] - 1 for t in by["T1"])
        for t in by["T2"]:
            c = t["changed"]
            assert t["render_diff"] is not None and c["first_differing_token"] >= c["n"] - 12
            assert c["cache_n"] == c["predicted_reuse"] == c["first_differing_token"]
            assert c["first_differing_token"] / c["n"] > 0.10
        assert summarize(report["run_id"], w["root"])[0] == report


def test_records_carry_the_change_and_the_summarizer_checks_only_kwargs_changed(tmp_path):
    w, report = _run(tmp_path, "H-M3L1", "llama", repetitions=1)
    requests_dir = w["root"] / "corpus" / "requests"
    records = read(w["m3"].corpus_dir / f"{report['run_id']}.jsonl")
    assert [(r["change"], r["role"]) for r in records] == [("T1", "base"), ("T1", "changed"), ("T2", "base"), ("T2", "changed")]
    assert all(r["experiment"] == "m3" for r in records)
    for r in records:
        body = json.loads(load_request(requests_dir, r["request_sha256"])["body"])
        assert set(body["chat_template_kwargs"]) == {"date_string", "enable_thinking"}
    t1 = [r for r in records if r["change"] == "T1"]
    base_body = json.loads(load_request(requests_dir, t1[0]["request_sha256"])["body"])
    changed_body = json.loads(load_request(requests_dir, t1[1]["request_sha256"])["body"])
    assert base_body["chat_template_kwargs"]["date_string"] == "01 Oct 2026"
    assert changed_body["chat_template_kwargs"]["date_string"] == "02 Oct 2026"
    assert ({k: v for k, v in base_body.items() if k != "chat_template_kwargs"}
            == {k: v for k, v in changed_body.items() if k != "chat_template_kwargs"})
    # a changed request under T1's nonce that also changes the user message: only_kwargs_changed fails
    from prefix_mortality.record import store_request
    from tests.fake_llamacpp import Engine
    changed_body["messages"][-1]["content"] = "Goodbye."
    raw = json.dumps(changed_body, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    e = Engine(template="llama")
    rendered = e.render(changed_body)
    records[1]["request_sha256"] = store_request(requests_dir, raw, rendered, e.tokenize(rendered))
    out = evaluate(records, requests_dir, w["m3"])
    assert out["outcome"] == "FAILED CONTROL" and any("only_kwargs_changed is false" in f for f in out["failures"])


@pytest.mark.parametrize("mode, outcome, reason", [
    ("no_cache", "MISMATCH", "predicted"),
    ("sticky", "FAILED CONTROL", "base_reuses_at_most_header is false"),
    ("no_fields", "NOT MEASURABLE", "the server reported no cache_n, prompt_n, usage_cached_tokens"),
])
def test_a_run_goes_red_on_an_engine_that_breaks_a_rule(tmp_path, mode, outcome, reason):
    w, report = _run(tmp_path, "H-M3L1", "llama", mode=mode)
    assert report["outcome"] == outcome
    assert any(reason in x for x in report["mismatches"] + report["failures"] + report["unmeasurable"]), report
    assert summarize(report["run_id"], w["root"])[0]["outcome"] == outcome


def test_run_refuses_unregistered_and_wrong_slots(tmp_path):
    w = _world(tmp_path / "a", registered="")
    with serve(slots=1, template="llama") as (url, _):
        with pytest.raises(Refusal, match="m3.toml is UNREGISTERED"):
            run(w["m3"], w["controls"], w["engine"], "qwen", "H-M3L1", Client(url, 30.0), w["model"],
                repo_root=w["root"], fixture=w["root"] / "fixture")
    w = _world(tmp_path / "b")
    with serve(slots=4, template="llama") as (url, _):
        with pytest.raises(Refusal, match="requires a server reporting 1 slot"):
            run(w["m3"], w["controls"], w["engine"], "qwen", "H-M3L1", Client(url, 30.0), w["model"],
                repo_root=w["root"], fixture=w["root"] / "fixture")
    assert not list((w["root"] / "corpus" / "requests").iterdir())


def test_probe_reports_each_change_and_records_nothing(tmp_path):
    w = _world(tmp_path, registered="")
    with serve(slots=4, template="llama") as (url, _):
        out = probe(w["m3"], w["controls"], "H-M3LD", ["T1", "T2"], Client(url, 30.0), fixture=w["root"] / "fixture")
        with pytest.raises(Refusal, match="unknown change"):
            probe(w["m3"], w["controls"], "H-M3LD", ["T9"], Client(url, 30.0), fixture=w["root"] / "fixture")
    t1, t2 = out["trials"]
    assert t1["predicted_reuse"] == 0 and t1["match"] and t1["render_diff"] is not None
    assert t2["render_diff"] is None and t2["predicted_reuse"] == t2["prompt_tokens"] - 1 and t2["match"]
    assert out["base_kwargs"] == {"date_string": "01 Oct 2026", "enable_thinking": True} and out["server"]["total_slots"] == 4
    assert not list((w["root"] / "corpus" / "requests").iterdir()) and not list((w["root"] / "corpus" / "live" / "m3").iterdir())
